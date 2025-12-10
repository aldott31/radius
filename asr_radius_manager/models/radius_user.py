# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re
import subprocess  # ← SHTUAR
import secrets
import string

_logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^A-Z0-9]+")


def _slug_company(name: str) -> str:
    if not name:
        return "COMPANY"
    return _SANITIZE_RE.sub("", name.upper())


def _slug_plan(code: str, name: str) -> str:
    base = (code or name or "PLAN").upper()
    return _SANITIZE_RE.sub("", base)


class AsrRadiusUser(models.Model):
    _name = 'asr.radius.user'
    _description = 'RADIUS User'
    _order = 'username'
    _check_company_auto = True
    _inherit = ['mail.thread']

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(string="Name", help="Optional display name")
    username = fields.Char(string="RADIUS Username", index=True, copy=False, tracking=True,
                          help="Auto-generated if left empty (format: 445XXXXXX)")
    radius_password = fields.Char(string="RADIUS Password", copy=False,
                                  help="Auto-generated if left empty")
    subscription_id = fields.Many2one('asr.subscription', string="Subscription", required=False, ondelete='restrict',
                                     help="Service plan - required before syncing to RADIUS")
    device_id = fields.Many2one('asr.device', string="Device (optional)", ondelete='set null')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    # Link to res.partner (Contacts)
    partner_id = fields.Many2one('res.partner', string="Contact", ondelete='set null',
                                  help="Linked contact from Odoo Contacts",
                                  index=True, tracking=True)

    radius_synced = fields.Boolean(string="Synced", default=False, copy=False, tracking=True)
    last_sync_date = fields.Datetime(string="Last Sync", copy=False)
    last_sync_error = fields.Text(string="Last Error", copy=False)

    groupname = fields.Char(string="Group Name", compute='_compute_groupname', store=False)

    # LIVE: radusergroup
    current_radius_group = fields.Char(
        string="Current RADIUS Group",
        compute="_compute_current_radius_group",
        store=False,
        help="Lexohet live nga radusergroup për këtë username."
    )

    # LIVE: dekorim suspended
    is_suspended = fields.Boolean(
        string="Suspended (live)",
        compute="_compute_is_suspended",
        store=False
    )

    _sql_constraints = [
        ('uniq_username_company', 'unique(username, company_id)', 'RADIUS username must be unique per company.'),
        ('uniq_partner_company', 'unique(partner_id, company_id)', 'Each partner can have only one RADIUS user per company.')
    ]

    # ---- Auto-generation helpers ----
    def _generate_username(self):
        """Generate next RADIUS username using sequence (445XXXXXX format)"""
        return self.env['ir.sequence'].next_by_code('asr.radius.user.username') or '445000000'

    def _generate_password(self, length=12):
        """Generate secure random password"""
        # Use alphanumeric characters (easier for customer support)
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-generate username and password + create linked res.partner"""
        for vals in vals_list:
            # Auto-generate username if empty
            if not vals.get('username'):
                vals['username'] = self._generate_username()
                _logger.info("Auto-generated RADIUS username: %s", vals['username'])

            # Auto-generate password if empty
            if not vals.get('radius_password'):
                vals['radius_password'] = self._generate_password()
                _logger.info("Auto-generated RADIUS password for user: %s", vals['username'])

        records = super(AsrRadiusUser, self).create(vals_list)

        # Skip partner creation if flag is set (to prevent recursion)
        skip_partner_creation = self.env.context.get('_skip_partner_creation')

        if skip_partner_creation:
            return records

        # Auto-create linked res.partner if not provided
        for record in records:
            if not record.partner_id:
                try:
                    partner_vals = {
                        'name': record.name or record.username,
                        'is_radius_customer': True,
                        'radius_username': record.username,
                        'radius_password': record.radius_password,
                        'subscription_id': record.subscription_id.id if record.subscription_id else False,
                        'device_id': record.device_id.id if record.device_id else False,
                        'company_id': record.company_id.id,
                        'radius_user_id': record.id,
                    }

                    # Create with context flag to prevent recursion
                    partner = self.env['res.partner'].with_context(
                        _skip_partner_creation=True
                    ).sudo().create(partner_vals)

                    record.sudo().write({'partner_id': partner.id})
                    _logger.info("Auto-created res.partner %s for RADIUS user %s", partner.name, record.username)

                except Exception as e:
                    _logger.error("Failed to auto-create res.partner for RADIUS user %s: %s", record.username, e)

        return records

    @api.depends('subscription_id', 'company_id')
    def _compute_groupname(self):
        for rec in self:
            comp = rec.company_id or self.env.company
            comp_prefix = _slug_company(getattr(comp, 'code', None) or comp.name)
            plan_code = _slug_plan(rec.subscription_id.code,
                                   rec.subscription_id.name) if rec.subscription_id else "NOPLAN"
            rec.groupname = f"{comp_prefix}:{plan_code}"

    @api.depends('username', 'company_id')
    def _compute_current_radius_group(self):
        for rec in self:
            cur_group = False
            if rec.username:
                conn = None
                try:
                    conn = rec._get_radius_conn()
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT groupname FROM radusergroup WHERE username=%s ORDER BY priority ASC LIMIT 1",
                            (rec.username,)
                        )
                        row = cur.fetchone()
                        if row:
                            cur_group = row.get('groupname') if isinstance(row, dict) else row[0]
                except Exception as e:
                    _logger.debug("Fetch current RADIUS group failed for %s: %s", rec.username, e)
                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass
            rec.current_radius_group = cur_group or False

    @api.depends('current_radius_group')
    def _compute_is_suspended(self):
        for rec in self:
            grp = (rec.current_radius_group or '').upper()
            rec.is_suspended = bool(re.search(r'(^|:)SUSPENDED$', grp))

    # ---- RADIUS connection helpers ----
    def _get_radius_conn(self):
        """Prefero company._get_direct_conn() nga ab_radius_connector; përndryshe mysql.connector i kompanisë."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if hasattr(company, "_get_direct_conn"):
            conn = company._get_direct_conn()
            if conn:
                return conn

        mc = self.env['mysql.connector'].sudo().search([('company_id', '=', company.id)], limit=1) or \
             self.env['mysql.connector'].sudo().search([], limit=1)
        if not mc:
            raise UserError(_("No MySQL connector found for RADIUS."))

        getter = getattr(mc, "get_connection", None) or getattr(mc, "_get_connection", None)
        if not getter:
            raise UserError(_("mysql.connector object has no get_connection() method."))
        return getter()

    # ---- SQL UPSERT helpers ----
    @staticmethod
    def _upsert_radcheck(cursor, username, cleartext_password):
        sql = """
              INSERT INTO radcheck (username, attribute, op, value)
              VALUES (%s, 'Cleartext-Password', ':=', %s) ON DUPLICATE KEY \
              UPDATE value = \
              VALUES (value) \
              """
        cursor.execute(sql, (username, cleartext_password))

    @staticmethod
    def _upsert_radusergroup(cursor, username, groupname):
        cursor.execute("DELETE FROM radusergroup WHERE username=%s", (username,))
        cursor.execute("""
                       INSERT INTO radusergroup (username, groupname, priority)
                       VALUES (%s, %s, 1)
                       """, (username, groupname))

    # ---- Actions ----
    def action_sync_to_radius(self):
        ok = 0
        last_error = None
        for rec in self:
            if not rec.username:
                raise UserError(_("Missing RADIUS username."))
            if not rec.radius_password:
                raise UserError(_("Missing RADIUS password."))
            if not rec.subscription_id:
                raise UserError(_("Select a Subscription."))

            # ✅ FIX #4: Validate that subscription is synced to RADIUS
            if not rec.subscription_id.radius_synced:
                raise UserError(_(
                    "Subscription '%(name)s' is not synced to RADIUS.\n"
                    "Please sync the subscription first (radgroupreply must have attributes)."
                ) % {'name': rec.subscription_id.name})

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    self._upsert_radcheck(cur, rec.username, rec.radius_password)
                    self._upsert_radusergroup(cur, rec.username, rec.groupname)
                conn.commit()
                rec.sudo().with_context(skip_radius_auto_sync=True, _from_radius_sync=True).write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })
                try:
                    rec.message_post(
                        body=_("Synchronized user %(u)s → group %(g)s") % {'u': rec.username, 'g': rec.groupname},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
                _logger.info("RADIUS sync OK: %s -> %s", rec.username, rec.groupname)
                ok += 1

                # ✅ FIX #2: Auto-disconnect if user has active session (force reconnect with new settings)
                if rec._has_active_session():
                    try:
                        _logger.info("User %s has active session, forcing disconnect to apply new settings", rec.username)
                        rec.action_disconnect_user()
                        try:
                            rec.message_post(
                                body=_("⚡ <b>Auto-disconnect:</b> User was online and has been disconnected to apply new RADIUS settings.<br/>"
                                       "User will reconnect automatically with new configuration."),
                                subtype_xmlid='mail.mt_note'
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        _logger.warning("Auto-disconnect failed for %s: %s", rec.username, e)
                        # Don't fail the sync if disconnect fails - just log it
            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                rec.sudo().with_context(skip_radius_auto_sync=True).write({'radius_synced': False, 'last_sync_error': last_error})
                _logger.exception("RADIUS sync failed for %s", rec.username)
                try:
                    rec.message_post(
                        body=_("RADIUS sync FAILED for '%(u)s': %(err)s") % {'u': rec.username, 'err': last_error},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

        if ok == len(self):
            msg = (_("User '%s' synced to RADIUS") % self.username) if len(self) == 1 else (_("%d user(s) synced") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync'), 'message': msg, 'type': 'success', 'sticky': False}
            }
        else:
            failed = len(self) - ok
            msg = _('%d succeeded, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    def action_suspend(self):
        ok = 0
        last_error = None
        for rec in self:
            if not rec.username:
                raise UserError(_("Missing RADIUS username."))
            comp = rec.company_id or self.env.company
            suspended = f"{_slug_company((getattr(comp, 'code', None) or comp.name))}:SUSPENDED"
            conn = rec._get_radius_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                                INSERT
                                IGNORE INTO radgroupreply (groupname, attribute, op, value)
                        VALUES (
                                %s,
                                'Reply-Message',
                                ':=',
                                'Suspended'
                                )
                                """, (suspended,))
                    self._upsert_radusergroup(cur, rec.username, suspended)
                conn.commit()
                rec.sudo().with_context(skip_radius_auto_sync=True).write(
                    {'radius_synced': True, 'last_sync_error': False, 'last_sync_date': fields.Datetime.now()})
                ok += 1
                try:
                    rec.message_post(
                        body=_("Suspended '%(u)s' → group %(g)s") % {'u': rec.username, 'g': suspended},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            except Exception as e:
                last_error = str(e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                rec.sudo().with_context(skip_radius_auto_sync=True).write({'radius_synced': False, 'last_sync_error': last_error})
                try:
                    rec.message_post(
                        body=_("Suspend FAILED for '%(u)s': %(err)s") % {'u': rec.username, 'err': last_error},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        if ok == len(self):
            msg = (_("User '%s' suspended") % self.username) if len(self) == 1 else (_("%d user(s) suspended") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Suspension'), 'message': msg, 'type': 'warning', 'sticky': False}
            }
        else:
            failed = len(self) - ok
            msg = _('%d suspended, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Suspension (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    def action_reactivate(self):
        ok = 0
        last_error = None
        for rec in self:
            if not rec.username or not rec.subscription_id:
                raise UserError(_("Missing username or subscription."))
            conn = rec._get_radius_conn()
            try:
                with conn.cursor() as cur:
                    self._upsert_radusergroup(cur, rec.username, rec.groupname)
                conn.commit()
                rec.sudo().with_context(skip_radius_auto_sync=True).write(
                    {'radius_synced': True, 'last_sync_error': False, 'last_sync_date': fields.Datetime.now()})
                ok += 1
                try:
                    rec.message_post(
                        body=_("Reactivated '%(u)s' → group %(g)s") % {'u': rec.username, 'g': rec.groupname},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            except Exception as e:
                last_error = str(e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                rec.sudo().with_context(skip_radius_auto_sync=True).write({'radius_synced': False, 'last_sync_error': last_error})
                try:
                    rec.message_post(
                        body=_("Reactivate FAILED for '%(u)s': %(err)s") % {'u': rec.username, 'err': last_error},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        if ok == len(self):
            msg = (_("User '%s' reactivated") % self.username) if len(self) == 1 else (_("%d user(s) reactivated") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Reactivation'), 'message': msg, 'type': 'success', 'sticky': False}
            }
        else:
            failed = len(self) - ok
            msg = _('%d reactivated, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Reactivation (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    def action_remove_from_radius(self):
        ok = 0
        last_error = None
        for rec in self:
            if not rec.username:
                raise UserError(_("Missing RADIUS username."))
            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM radreply WHERE username=%s", (rec.username,))
                    cur.execute("DELETE FROM radcheck WHERE username=%s", (rec.username,))
                    cur.execute("DELETE FROM radusergroup WHERE username=%s", (rec.username,))
                conn.commit()

                rec.sudo().with_context(skip_radius_auto_sync=True).write({
                    'radius_synced': False,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })
                try:
                    rec.message_post(
                        body=_("Removed user '%(u)s' from RADIUS") % {'u': rec.username},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
                ok += 1
            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                rec.sudo().with_context(skip_radius_auto_sync=True).write({'last_sync_error': last_error})
                try:
                    rec.message_post(
                        body=_("Remove from RADIUS FAILED for '%(u)s': %(err)s") % {'u': rec.username,
                                                                                    'err': last_error},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

        if ok == len(self):
            msg = (_("User '%s' removed from RADIUS") % self.username) if len(self) == 1 else (
                        _("%d user(s) removed") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal'), 'message': msg, 'type': 'info', 'sticky': False}
            }
        else:
            failed = len(self) - ok
            msg = _('%d removed, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    def write(self, vals):
        """Override write to sync bidirectionally with res.partner"""
        # Skip auto-sync for internal writes (from sync operations)
        if self.env.context.get('skip_radius_auto_sync') or self.env.context.get('_from_radius_sync'):
            return super(AsrRadiusUser, self).write(vals)

        res = super(AsrRadiusUser, self).write(vals)

        # Sync to res.partner (SKIP if coming from partner to avoid loop)
        if not self.env.context.get('_from_partner_write'):
            for rec in self.filtered(lambda r: r.partner_id):
                partner_vals = {}

                # Map RADIUS fields to Partner fields (only changed fields)
                if 'username' in vals:
                    partner_vals['radius_username'] = vals['username']
                if 'radius_password' in vals:
                    partner_vals['radius_password'] = vals['radius_password']
                if 'subscription_id' in vals:
                    partner_vals['subscription_id'] = vals['subscription_id']
                if 'device_id' in vals:
                    partner_vals['device_id'] = vals['device_id']
                if 'name' in vals:
                    partner_vals['name'] = vals['name']

                # Sync bidirectionally with sudo() to avoid permission issues
                if partner_vals:
                    rec.partner_id.with_context(_from_radius_write=True).sudo().write(partner_vals)

        # ✅ FIX #1: Auto-sync to RADIUS when subscription changes
        # ALWAYS check (even if from partner), only skip if from sync operations
        if 'subscription_id' in vals and not self.env.context.get('skip_radius_auto_sync'):
            success_count = 0
            failed_count = 0

            for rec in self.filtered(lambda r: r.radius_synced and r.subscription_id):
                try:
                    _logger.info("Auto-syncing user %s to RADIUS after subscription change", rec.username)
                    # Use context flag to prevent infinite loops if action_sync_to_radius calls write()
                    rec.with_context(skip_radius_auto_sync=True).action_sync_to_radius()
                    success_count += 1

                    # ✅ UI Notification: Chatter message
                    try:
                        rec.message_post(
                            body=_("🔄 Subscription changed → Auto-synced to RADIUS<br/>"
                                   "New group: <b>%(group)s</b>") % {'group': rec.groupname},
                            subtype_xmlid='mail.mt_note'
                        )
                    except Exception:
                        pass

                except Exception as e:
                    _logger.warning("Auto-sync to RADIUS failed for %s: %s", rec.username, e)
                    failed_count += 1
                    # Don't raise exception - just log the error
                    # User can manually sync if needed

            # ✅ UI Notification: Popup for user feedback
            if success_count > 0 and not self.env.context.get('skip_radius_auto_sync'):
                message = _("✅ Auto-synced %(count)d user(s) to RADIUS with new subscription") % {'count': success_count}
                if failed_count > 0:
                    message += _("\n⚠️ %(failed)d failed") % {'failed': failed_count}

                # Return notification (will be shown if called from UI action)
                # Note: This won't show on simple write() but good for future button actions
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'simple_notification',
                    {
                        'type': 'success',
                        'title': _('RADIUS Auto-Sync'),
                        'message': message,
                        'sticky': False,
                    }
                )

        return res


# =========================
# SHTESË: PPPoE / Sessions live info
# =========================
class AsrRadiusUserExt(models.Model):
    _inherit = 'asr.radius.user'

    pppoe_status = fields.Selection(
        [('down', 'Down'), ('up', 'Up')],
        string="PPPoE Status",
        compute='_compute_pppoe_status',
        store=False
    )
    last_session_start = fields.Datetime(string="Last Login", compute='_compute_pppoe_status', store=False)
    current_framed_ip = fields.Char(string="IP (current)", compute='_compute_pppoe_status', store=False)
    current_interface = fields.Char(string="Interface (current)", compute='_compute_pppoe_status', store=False)

    active_sessions_count = fields.Integer(string="Active", compute='_compute_session_counts', store=False)
    total_sessions_count = fields.Integer(string="Sessions", compute='_compute_session_counts', store=False)

    def _compute_pppoe_status(self):
        """
        Lexon sesionin aktiv nga asr.radius.session.
        Nëse fushat nuk janë të pranishme (p.sh. framedipaddress vs framed_ip_address),
        bën fallback me SELECT direkt nga radacct.
        """
        Sess = self.env['asr.radius.session'].sudo()

        for rec in self:
            rec.pppoe_status = 'down'
            rec.last_session_start = False
            rec.current_framed_ip = False
            rec.current_interface = False

            if not rec.username:
                continue

            ip = None
            iface = None
            start = None

            # 1) Provo nga modeli asr.radius.session (aktiv: acctstoptime IS NULL)
            s = Sess.search(
                [('username', '=', rec.username), ('acctstoptime', '=', False)],
                limit=1,
                order='acctstarttime desc'
            )
            if s:
                # start time
                start = getattr(s, 'acctstarttime', None) or getattr(s, 'acct_start_time', None)

                # IP — provo disa variante emrash
                for attr in ('framedipaddress', 'framed_ip_address', 'framed_ip'):
                    v = getattr(s, attr, None)
                    if v:
                        ip = v
                        break

                # Interface — prefero NAS-Port-Id, përndryshe Called-Station-Id
                for attr in ('nasportid', 'nas_port_id', 'nasport', 'calledstationid', 'called_station_id'):
                    v = getattr(s, attr, None)
                    if v:
                        iface = v
                        break

            # 2) Fallback direkt nga radacct nëse mungon IP/Interface/Start
            if not (ip and iface and start):
                conn = None
                try:
                    conn = rec._get_radius_conn()
                    with conn.cursor() as cur:
                        cur.execute("""
                                    SELECT framedipaddress, nasportid, calledstationid, acctstarttime
                                    FROM radacct
                                    WHERE username = %s
                                      AND acctstoptime IS NULL
                                    ORDER BY acctstarttime DESC LIMIT 1
                                    """, (rec.username,))
                        row = cur.fetchone()
                        if row:
                            if isinstance(row, dict):
                                ip = ip or row.get('framedipaddress') or row.get('framed_ip_address')
                                iface = iface or row.get('nasportid') or row.get('calledstationid')
                                start = start or row.get('acctstarttime')
                            else:
                                # row tuple order: framedipaddress, nasportid, calledstationid, acctstarttime
                                ip = ip or row[0]
                                iface = iface or row[1] or row[2]
                                start = start or row[3]
                except Exception as e:
                    _logger.debug("Fallback radacct SQL failed for %s: %s", rec.username, e)
                finally:
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

            # 3) Vendos vlerat
            if start or ip or iface:
                rec.pppoe_status = 'up'
                rec.last_session_start = start or False
                rec.current_framed_ip = ip or False
                rec.current_interface = iface or False

    def _compute_session_counts(self):
        Sess = self.env['asr.radius.session'].sudo()
        for rec in self:
            if not rec.username:
                rec.active_sessions_count = 0
                rec.total_sessions_count = 0
                continue
            rec.active_sessions_count = Sess.search_count(
                [('username', '=', rec.username), ('acctstoptime', '=', False)])
            rec.total_sessions_count = Sess.search_count([('username', '=', rec.username)])

    def _sessions_action_base(self, domain):
        self.ensure_one()
        return {
            'name': _("Sessions"),
            'type': 'ir.actions.act_window',
            'res_model': 'asr.radius.session',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    def action_view_active_sessions(self):
        return self._sessions_action_base([('username', '=', self.username), ('acctstoptime', '=', False)])

    def action_view_sessions(self):
        return self._sessions_action_base([('username', '=', self.username)])


# =========================
# SHTESË: One-Click Provision & Test (me RadiusClient)
# =========================
class AsrRadiusUserProvision(models.Model):
    _inherit = 'asr.radius.user'

    def _db_readiness_checks(self):
        self.ensure_one()
        conn = self._get_radius_conn()
        ready = {'radcheck': False, 'radusergroup': False, 'group_attrs': 0}
        groupname = self.groupname
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM radcheck WHERE username=%s AND attribute='Cleartext-Password' LIMIT 1",
                            (self.username,))
                ready['radcheck'] = bool(cur.fetchone())
                cur.execute("SELECT 1 FROM radusergroup WHERE username=%s LIMIT 1", (self.username,))
                ready['radusergroup'] = bool(cur.fetchone())
                cur.execute("SELECT COUNT(*) FROM radgroupreply WHERE groupname=%s", (groupname,))
                row = cur.fetchone()
                ready['group_attrs'] = int(
                    row[0] if isinstance(row, tuple) else (row.get('COUNT(*)') or row.get('count') or 0))
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return ready

    def _try_access_request(self, password, method='pap'):
        self.ensure_one()
        cfg = self.env['asr.radius.config'].search([('company_id', '=', self.env.company.id)], limit=1)
        if not cfg:
            return {'ran': False, 'ok': False, 'out': 'RADIUS Config mungon.'}
        client = cfg._make_radius_client()

        m = (method or 'pap').lower()
        try:
            if m == 'chap':
                res = client.access_request_chap(self.username, password)
            else:
                res = client.access_request_pap(self.username, password)
            out = res.get('reply_message') or res.get('code') or ''
            return {'ran': True, 'ok': bool(res.get('ok')), 'out': out}
        except Exception as e:
            return {'ran': True, 'ok': False, 'out': 'Error: %s' % e}

    # ==================== DISCONNECT ACTION ====================

    def _has_active_session(self):
        """Check if user has active PPPoE session in radacct"""
        self.ensure_one()
        if not self.username:
            return False

        conn = None
        try:
            conn = self._get_radius_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM radacct
                    WHERE username = %s AND acctstoptime IS NULL
                    LIMIT 1
                """, (self.username,))
                return bool(cur.fetchone())
        except Exception as e:
            _logger.debug("Failed to check active session for %s: %s", self.username, e)
            return False
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def action_disconnect_user(self):
        """Send RADIUS Disconnect-Request via SSH to FreeRADIUS server."""
        self.ensure_one()

        if not self.username:
            raise UserError(_("Missing username."))

        # Merr NAS IP nga sesioni aktiv
        nas_ip = None
        conn = None
        try:
            conn = self._get_radius_conn()
            with conn.cursor() as cur:
                cur.execute("""
                            SELECT nasipaddress
                            FROM radacct
                            WHERE username = %s
                              AND acctstoptime IS NULL
                            ORDER BY acctstarttime DESC LIMIT 1
                            """, (self.username,))
                row = cur.fetchone()
                if row:
                    nas_ip = row.get('nasipaddress') if isinstance(row, dict) else row[0]
        except Exception as e:
            _logger.warning("Failed to get NAS for %s: %s", self.username, e)
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        if not nas_ip:
            raise UserError(_("No active session found for user '%s'.") % self.username)

        # ✅ FIX #6: Get SSH settings from res.company (instead of hardcoded)
        company = self.company_id or self.env.company
        radius_server = company.fr_ssh_host or company.fr_db_host or '80.91.126.33'
        ssh_user = company.fr_ssh_user or 'root'
        secret = company.fr_disconnect_secret or 'testing123'
        disconnect_port = 1700  # Standard RADIUS disconnect port

        try:
            # Ndërto payload: VETËM User-Name + NAS-IP-Address (pa Session-Id)
            # Kjo është më e besueshme kur Session-Id në DB nuk përputhet me NAS-in
            lines = [f"User-Name={self.username}", f"NAS-IP-Address={nas_ip}"]
            payload = "\n".join(lines) + "\n"

            # Përdor printf me quoting të sigurt në remote shell
            remote_cmd = "printf %s | radclient -x %s:%d disconnect %s" % (
                repr(payload), nas_ip, disconnect_port, secret
            )

            cmd = [
                'ssh',
                '-i', '/home/odoo/.ssh/id_rsa',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=5',
                f'{ssh_user}@{radius_server}',
                remote_cmd
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10
            )

            output = result.stdout or ''
            exit_code = result.returncode

            # ✅ Enhanced verification with exit code
            _logger.info(f'Disconnect command for {self.username}: exit_code={exit_code}')
            _logger.debug(f'Disconnect output: {output}')

            # Parse response
            disconnect_ack = ('Disconnect-ACK' in output) or ('Received Disconnect-ACK' in output) or ('code 43' in output)
            disconnect_nak = ('Disconnect-NAK' in output) or ('No reply from server' in output) or ('code 44' in output)
            ssh_error = exit_code != 0 and ('Permission denied' in output or 'Connection refused' in output or 'Host key verification failed' in output)

            # ✅ Enhanced logging with more context
            try:
                status_icon = '✅' if disconnect_ack else ('❌' if disconnect_nak or ssh_error else '⚠')
                status_text = (
                    'Disconnected successfully' if disconnect_ack
                    else 'Disconnect NAK received' if disconnect_nak
                    else 'SSH connection error' if ssh_error
                    else 'Unknown response'
                )

                self.message_post(
                    body=_(
                        "%(icon)s RADIUS Disconnect Request<br/>"
                        "<strong>User:</strong> %(user)s<br/>"
                        "<strong>NAS:</strong> %(nas)s<br/>"
                        "<strong>Status:</strong> %(status)s<br/>"
                        "<strong>Exit Code:</strong> %(code)d<br/>"
                        "<strong>Command:</strong> <code>radclient %(nas)s:%(port)d disconnect</code><br/><br/>"
                        "<strong>Output:</strong><br/><pre>%(out)s</pre>"
                    ) % {
                        'icon': status_icon,
                        'user': self.username,
                        'nas': nas_ip,
                        'port': disconnect_port,
                        'status': status_text,
                        'code': exit_code,
                        'out': output[:800]
                    },
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.warning(f'Failed to post disconnect log: {e}')

            # ✅ Better error handling for SSH issues
            if ssh_error:
                raise UserError(_(
                    'SSH connection to RADIUS server failed.\n\n'
                    'Exit code: %(code)d\n'
                    'Server: %(server)s\n'
                    'User: %(ssh_user)s\n\n'
                    'Error:\n%(error)s\n\n'
                    'Please check:\n'
                    '• SSH key is installed on RADIUS server\n'
                    '• SSH user has correct permissions\n'
                    '• Server hostname/IP is correct\n'
                    '• Firewall allows SSH connections'
                ) % {
                    'code': exit_code,
                    'server': radius_server,
                    'ssh_user': ssh_user,
                    'error': output[:400]
                })

            if disconnect_ack:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('✅ Disconnect Successful'),
                        'message': _('User "%(user)s" disconnected from NAS %(nas)s\nExit code: %(code)d') % {
                            'user': self.username,
                            'nas': nas_ip,
                            'code': exit_code
                        },
                        'type': 'success',
                        'sticky': False,
                    }
                }
            elif disconnect_nak:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('⚠ Disconnect Failed'),
                        'message': _('NAS did not respond or user "%(user)s" not online.\nExit code: %(code)d\n\nPossible reasons:\n• User already disconnected\n• NAS unreachable\n• Invalid secret') % {
                            'user': self.username,
                            'code': exit_code
                        },
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('⚠ Unknown Response'),
                        'message': _('Exit code: %(code)d\n\nOutput:\n%(output)s') % {
                            'code': exit_code,
                            'output': output[:300]
                        },
                        'type': 'warning',
                        'sticky': True,
                    }
                }

        except subprocess.TimeoutExpired:
            raise UserError(_("SSH connection timed out."))
        except Exception as e:
            raise UserError(_("Disconnect failed: %s") % str(e))

    # ==================== NAVIGATION ACTIONS ====================
    def action_view_partner(self):
        """Smart button: navigate to linked res.partner record"""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("No contact/partner linked to this RADIUS user."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer: %s') % (self.partner_id.name or self.username),
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
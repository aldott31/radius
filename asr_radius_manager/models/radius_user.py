# asr_radius_manager/models/radius_user.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging, re
import subprocess, shlex  # NEW: për Provision & Test

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
    _inherit = ['mail.thread', 'mail.activity.mixin']  # për message_post dhe tracking

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(string="Name", help="Optional display name")
    username = fields.Char(string="RADIUS Username", required=True, index=True, copy=False, tracking=True)
    radius_password = fields.Char(string="RADIUS Password", copy=False)
    subscription_id = fields.Many2one('asr.subscription', string="Subscription", required=True, ondelete='restrict')
    device_id = fields.Many2one('asr.device', string="Device (optional)", ondelete='set null')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    radius_synced = fields.Boolean(string="Synced", default=False, copy=False, tracking=True)
    last_sync_date = fields.Datetime(string="Last Sync", copy=False)
    last_sync_error = fields.Text(string="Last Error", copy=False)

    groupname = fields.Char(string="Group Name", compute='_compute_groupname', store=False)

    # --- LIVE from RADIUS (radusergroup) ---
    current_radius_group = fields.Char(
        string="Current RADIUS Group",
        compute="_compute_current_radius_group",
        store=False,
        help="Lexohet live nga radusergroup për këtë username."
    )

    # NEW: flag për dekorim në listë kur user-i është në grup SUSPENDED
    is_suspended = fields.Boolean(
        string="Suspended (live)",
        compute="_compute_is_suspended",
        store=False
    )

    _sql_constraints = [
        ('uniq_username_company', 'unique(username, company_id)', 'RADIUS username must be unique per company.')
    ]

    @api.depends('subscription_id', 'company_id')
    def _compute_groupname(self):
        for rec in self:
            comp = rec.company_id or self.env.company
            comp_prefix = _slug_company(getattr(comp, 'code', None) or comp.name)
            plan_code = _slug_plan(rec.subscription_id.code, rec.subscription_id.name) if rec.subscription_id else "NOPLAN"
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
                        # Merr grupin aktual (zakonisht 1 grup per user)
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
            # Match 'SUSPENDED' si grup i vetëm ose me prefix p.sh. ABISSNET:SUSPENDED
            rec.is_suspended = bool(re.search(r'(^|:)SUSPENDED$', grp))

    # ---- RADIUS connection helpers ----
    def _get_radius_conn(self):
        """Prefero company._get_direct_conn() nga ab_radius_connector; përndryshe përdor mysql.connector të kompanisë."""
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
            VALUES (%s, 'Cleartext-Password', ':=', %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
        """
        cursor.execute(sql, (username, cleartext_password))

    @staticmethod
    def _upsert_radusergroup(cursor, username, groupname):
        # Ensure exactly one group per user: delete any existing, then insert the new one
        cursor.execute("DELETE FROM radusergroup WHERE username=%s", (username,))
        cursor.execute("""
            INSERT INTO radusergroup (username, groupname, priority)
            VALUES (%s, %s, 1)
        """, (username, groupname))

    # ---- Actions ----
    def action_sync_to_radius(self):
        """
        Sync per-user: radcheck + radusergroup.
        Kthen popup (display_notification) si te subscription-i dhe log në chatter.
        """
        ok = 0
        last_error = None
        for rec in self:
            # validime bazë
            if not rec.username:
                raise UserError(_("Missing RADIUS username."))
            if not rec.radius_password:
                raise UserError(_("Missing RADIUS password."))
            if not rec.subscription_id:
                raise UserError(_("Select a Subscription."))

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    self._upsert_radcheck(cur, rec.username, rec.radius_password)
                    self._upsert_radusergroup(cur, rec.username, rec.groupname)
                conn.commit()
                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })
                # chatter note
                try:
                    rec.message_post(
                        body=_("Synchronized user %(u)s → group %(g)s") % {'u': rec.username, 'g': rec.groupname},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
                _logger.info("RADIUS sync OK: %s -> %s", rec.username, rec.groupname)
                ok += 1
            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                _logger.exception("RADIUS sync failed for %s", rec.username)
                # chatter error
                try:
                    rec.message_post(
                        body=_("RADIUS sync FAILED for '%(u)s': %(err)s") % {'u': rec.username, 'err': last_error},
                        subtype_xmlid='mail.mt_note'
                    )
                except Exception:
                    pass
                # vazhdo me të tjerët (si te subscription), mos e prish batch-in

            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

        # Popup (si te subscription-i)
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
                'params': {'title': _('RADIUS Sync (Partial/Failed)'), 'message': msg, 'type': 'warning', 'sticky': False}
            }

    def action_suspend(self):
        """Kalojeni në grup SUSPENDED:<COMP>. Pop-up + chatter, pa fshirë password-in."""
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
                    # krijo një reply simbolik për grupin SUSPENDED (opsionale)
                    cur.execute("""
                        INSERT IGNORE INTO radgroupreply (groupname, attribute, op, value)
                        VALUES (%s, 'Reply-Message', ':=', 'Suspended')
                    """, (suspended,))
                    self._upsert_radusergroup(cur, rec.username, suspended)
                conn.commit()
                rec.sudo().write({'radius_synced': True, 'last_sync_error': False, 'last_sync_date': fields.Datetime.now()})
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
                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
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
                'params': {'title': _('RADIUS Suspension (Partial/Failed)'), 'message': msg, 'type': 'warning', 'sticky': False}
            }

    def action_reactivate(self):
        """Rikthen në grupin e planit. Pop-up + chatter."""
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
                rec.sudo().write({'radius_synced': True, 'last_sync_error': False, 'last_sync_date': fields.Datetime.now()})
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
                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
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
                'params': {'title': _('RADIUS Reactivation (Partial/Failed)'), 'message': msg, 'type': 'warning', 'sticky': False}
            }

    def action_remove_from_radius(self):
        """Fshi user-in nga RADIUS: radreply, radcheck, radusergroup. Nuk prek radacct."""
        ok = 0
        last_error = None
        for rec in self:
            if not rec.username:
                raise UserError(_("Missing RADIUS username."))
            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    # RadReply (overrides per-user)
                    cur.execute("DELETE FROM radreply WHERE username=%s", (rec.username,))
                    # RadCheck (credentials)
                    cur.execute("DELETE FROM radcheck WHERE username=%s", (rec.username,))
                    # RadUserGroup (group membership)
                    cur.execute("DELETE FROM radusergroup WHERE username=%s", (rec.username,))
                conn.commit()

                rec.sudo().write({
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
                rec.sudo().write({'last_sync_error': last_error})
                try:
                    rec.message_post(
                        body=_("Remove from RADIUS FAILED for '%(u)s': %(err)s") % {'u': rec.username, 'err': last_error},
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

        # Popup
        if ok == len(self):
            msg = (_("User '%s' removed from RADIUS") % self.username) if len(self) == 1 else (_("%d user(s) removed") % ok)
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
                'params': {'title': _('RADIUS Removal (Partial/Failed)'), 'message': msg, 'type': 'warning', 'sticky': False}
            }


# =========================
# SHTESË: PPPoE status pa prekur klasën bazë
# =========================
class AsrRadiusUserExt(models.Model):
    _inherit = 'asr.radius.user'

    pppoe_status = fields.Selection(
        [('down', 'Down'), ('up', 'Up')],
        string="PPPoE Status",
        compute='_compute_pppoe_status',
        store=False
    )
    ppp_last_seen = fields.Datetime(string="Last Seen", compute='_compute_pppoe_status', store=False)
    ppp_framed_ip = fields.Char(string="Framed IP", compute='_compute_pppoe_status', store=False)

    def _compute_pppoe_status(self):
        # Përdor modelin asr.radius.session (lexon radacct) për të mos duplikuar connectora.
        for rec in self:
            rec.pppoe_status = 'down'
            rec.ppp_last_seen = False
            rec.ppp_framed_ip = False
            if not rec.username:
                continue
            Sess = self.env['asr.radius.session'].sudo()
            sessions = Sess.search([('username', '=', rec.username), ('acctstoptime', '=', False)], limit=1)
            if sessions:
                s = sessions[0]
                rec.pppoe_status = 'up'
                rec.ppp_last_seen = s.acctstarttime or s.calledstationid or False
                rec.ppp_framed_ip = s.framedipaddress or False

    def action_open_sessions(self):
        self.ensure_one()
        return {
            'name': _("Sessions"),
            'type': 'ir.actions.act_window',
            'res_model': 'asr.radius.session',
            'view_mode': 'list,form',
            'domain': [('username', '=', self.username)],
            'target': 'current',
            'context': {'create': False, 'edit': False, 'delete': False},
        }


# =========================
# SHTESË: One-Click Provision & Test (pa ndryshuar logjikën ekzistuese)
# =========================
class AsrRadiusUserProvision(models.Model):
    _inherit = 'asr.radius.user'

    def _db_readiness_checks(self):
        """Verifikon që radcheck/radusergroup/radgroupreply janë gati për login."""
        self.ensure_one()
        conn = self._get_radius_conn()
        ready = {'radcheck': False, 'radusergroup': False, 'group_attrs': 0}
        groupname = self.groupname
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM radcheck WHERE username=%s AND attribute='Cleartext-Password' LIMIT 1", (self.username,))
                ready['radcheck'] = bool(cur.fetchone())
                cur.execute("SELECT 1 FROM radusergroup WHERE username=%s LIMIT 1", (self.username,))
                ready['radusergroup'] = bool(cur.fetchone())
                cur.execute("SELECT COUNT(*) FROM radgroupreply WHERE groupname=%s", (groupname,))
                row = cur.fetchone()
                ready['group_attrs'] = int(row[0] if isinstance(row, tuple) else (row.get('COUNT(*)') or row.get('count') or 0))
        finally:
            try: conn.close()
            except Exception: pass
        return ready

    # ← ZËVENDËSUAR: përdor klientin e ri, jo subprocess
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

    def action_provision_and_test(self):
        """
        One-click:
          1) Sync plan attributes në radgroupreply
          2) Sync user (radcheck + radusergroup)
          3) DB checks
          4) (opsionale) Access-Request test
        """
        self.ensure_one()
        if not self.subscription_id:
            raise UserError(_("Select a Subscription first."))

        # 1) Plan sync
        try:
            self.subscription_id.action_sync_attributes_to_radius()
        except Exception as e:
            raise UserError(_("Plan sync failed: %s") % e)

        # 2) User sync
        self.action_sync_to_radius()

        # 3) DB readiness
        ready = self._db_readiness_checks()
        db_ok = ready['radcheck'] and ready['radusergroup'] and ready['group_attrs'] > 0

        # 4) Optional auth test (PAP by default; nëse do CHAP, thirre me method='chap')
        test = self._try_access_request(self.radius_password or '', method='pap')
        color = 'success' if (db_ok and (not test['ran'] or test['ok'])) else 'warning'
        msg = []
        msg.append(f"radcheck: {'OK' if ready['radcheck'] else 'MISSING'}")
        msg.append(f"radusergroup: {'OK' if ready['radusergroup'] else 'MISSING'}")
        msg.append(f"radgroupreply attrs: {ready['group_attrs']}")
        if test['ran']:
            msg.append(f"Access-Request: {'ACCEPT' if test['ok'] else 'REJECT'}")
        else:
            msg.append(f"Access-Request: skipped ({test['out']})")

        # chatter
        try:
            self.message_post(body="Provision & Test:<br/>" + "<br/>".join(msg), subtype_xmlid='mail.mt_note')
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Provision & Test'),
                'message': "\n".join(msg),
                'type': color,
                'sticky': False,
            }
        }

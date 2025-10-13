# asr_radius_manager/models/radius_user.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging, re

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
        sql = """
            INSERT INTO radusergroup (username, groupname, priority)
            VALUES (%s, %s, 1)
            ON DUPLICATE KEY UPDATE groupname = VALUES(groupname), priority = VALUES(priority)
        """
        cursor.execute(sql, (username, groupname))

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
                        body=_("Synchronized user %(u)s → group %(g)s", u=rec.username, g=rec.groupname),
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
                        body=_("RADIUS sync FAILED for '%(u)s': %(err)s", u=rec.username, err=last_error),
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
            suspended = f"{_slug_company(comp.name)}:SUSPENDED"
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
                    rec.message_post(body=_("Suspended '%(u)s' → group %(g)s", u=rec.username, g=suspended), subtype_xmlid='mail.mt_note')
                except Exception:
                    pass
            except Exception as e:
                last_error = str(e)
                try: conn.rollback()
                except Exception: pass
                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                try:
                    rec.message_post(body=_("Suspend FAILED for '%(u)s': %(err)s", u=rec.username, err=last_error), subtype_xmlid='mail.mt_note')
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
                    rec.message_post(body=_("Reactivated '%(u)s' → group %(g)s", u=rec.username, g=rec.groupname), subtype_xmlid='mail.mt_note')
                except Exception:
                    pass
            except Exception as e:
                last_error = str(e)
                try: conn.rollback()
                except Exception: pass
                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                try:
                    rec.message_post(body=_("Reactivate FAILED for '%(u)s': %(err)s", u=rec.username, err=last_error), subtype_xmlid='mail.mt_note')
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

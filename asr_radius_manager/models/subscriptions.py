# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging, re

_logger = logging.getLogger(__name__)


def _slugify(val):
    val = (val or '').strip().lower()
    val = re.sub(r'[^a-z0-9]+', '-', val)
    return re.sub(r'-+', '-', val).strip('-') or 'plan'


class AsrSubscription(models.Model):
    _name = "asr.subscription"
    _description = "RADIUS Service Plan (Subscription)"
    _order = "id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True  # <-- SHTUAR

    # ---- Basic Fields ----
    name = fields.Char(required=True, tracking=True)
    code = fields.Char(help="Group name in FreeRADIUS (radgroupreply.groupname). Auto-filled from name if empty.")
    rate_limit = fields.Char(help="e.g. '10M/10M'. If set, we add Mikrotik-Rate-Limit unless already in lines.")
    session_timeout = fields.Integer(help="Optional Session-Timeout (seconds)")
    price = fields.Float(help="Default price per cycle (billing in Phase 4/5).")
    product_id = fields.Many2one('product.product', string='Product', help='Product for invoicing (Phase 4/5).')

    # Odoo-only multi-company
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    # ---- IP Pool Management ----
    ip_pool_active = fields.Char(
        string='IP Pool (Active Users)',
        help='MikroTik/Cisco pool for active/paying users',
        tracking=True
    )
    ip_pool_expired = fields.Char(
        string='Next Pool Expiry',
        help='Pool for expired users (no internet; only portal allowed by firewall/policy).',
        tracking=True
    )

    # ---- UX / Stats ----
    user_count = fields.Integer(string='Users (RADIUS)', compute='_compute_user_count', store=False)

    # ---- Cisco overrides (optional) ----
    cisco_policy_in = fields.Char(string='Cisco Policy In', help='subscriber:service-policy-in POLICY_NAME')
    cisco_policy_out = fields.Char(string='Cisco Policy Out', help='subscriber:service-policy-out POLICY_NAME')
    cisco_pool_active = fields.Char(string='Cisco Pool (Active)', help='ip:addr-pool=POOL_ACTIVE')
    cisco_pool_expired = fields.Char(string='Cisco Pool (Expired)', help='ip:addr-pool=POOL_EXPIRED')

    # ---- Simple UI helpers for Cisco ----
    show_cisco = fields.Boolean(string='Show Cisco UI', compute='_compute_vendor_toggles', store=False)
    suggested_cisco_policy_in = fields.Char(string='Suggested Cisco Policy In',
                                            compute='_compute_suggested_cisco_policies', store=False, readonly=True)
    suggested_cisco_policy_out = fields.Char(string='Suggested Cisco Policy Out',
                                             compute='_compute_suggested_cisco_policies', store=False, readonly=True)

    # Attributes
    attribute_ids = fields.One2many('asr.radius.attribute', 'subscription_id', string='RADIUS Attributes')

    # Sync tracking
    radius_synced = fields.Boolean(default=False, readonly=True, tracking=True)
    last_sync_date = fields.Datetime(readonly=True)
    last_sync_error = fields.Text(readonly=True)

    # Code unik për kompani (tani që namespacojmë groupname me kompaninë)
    _sql_constraints = [
        ('code_company_unique', 'unique(code, company_id)', 'Code must be unique per company.'),
    ]

    @api.onchange('name')
    def _onchange_name_set_code(self):
        for rec in self:
            if not rec.code:
                rec.code = _slugify(rec.name)

    # -------------------------------------------------------------------------
    # Small helpers
    # -------------------------------------------------------------------------
    def _get_conf_bool(self, key: str, default: bool = False) -> bool:
        """Read boolean from ir.config_parameter."""
        icp = self.env['ir.config_parameter'].sudo()
        val = icp.get_param(key, '1' if default else '0')
        return val == '1'

    def _get_conf_str(self, key: str, default: str = '') -> str:
        return self.env['ir.config_parameter'].sudo().get_param(key, default) or default

    def _compute_vendor_toggles(self):
        """Show/hide Cisco block based on settings toggle."""
        emit_cisco = self._get_conf_bool('asr_radius.emit_cisco', True)  # Cisco primary by default
        for rec in self:
            rec.show_cisco = emit_cisco

    def _parse_rate_limit_pair(self, rl: str):
        """
        Returns (DL, UL) like ('200M','20M') or (None,None) if invalid.
        Accepts 10M/10M, 100m/20m, 1000k/500k, 1G/1G, with spaces.
        """
        if not rl:
            return (None, None)
        m = re.match(r'^\s*([0-9]+[KMGkmg]?)\s*/\s*([0-9]+[KMGkmg]?)\s*$', rl)
        return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)

    @api.depends('rate_limit')
    def _compute_suggested_cisco_policies(self):
        for rec in self:
            dl, ul = rec._parse_rate_limit_pair(rec.rate_limit or '')
            if not dl or not ul:
                rec.suggested_cisco_policy_out = False
                rec.suggested_cisco_policy_in = False
                continue
            pref_dl = rec._get_conf_str('asr_radius.cisco_prefix_dl', 'POLICY_DL_')
            pref_ul = rec._get_conf_str('asr_radius.cisco_prefix_ul', 'POLICY_UL_')
            rec.suggested_cisco_policy_out = f"{pref_dl}{dl}"   # OUT = Download
            rec.suggested_cisco_policy_in = f"{pref_ul}{ul}"    # IN  = Upload

    def action_apply_cisco_suggestions(self):
        """Copy suggested policy names into real Cisco fields + (optional) auto-fill Cisco pools from IP pools."""
        for rec in self:
            # Policies from rate limit
            if rec.suggested_cisco_policy_out:
                rec.cisco_policy_out = rec.suggested_cisco_policy_out
            if rec.suggested_cisco_policy_in:
                rec.cisco_policy_in = rec.suggested_cisco_policy_in

            # NEW: Optional auto-fill of Cisco pools from ip_pool_* when empty
            if rec._get_conf_bool('asr_radius.autofill_cisco_pools', True):
                if (not rec.cisco_pool_active) and rec.ip_pool_active:
                    rec.cisco_pool_active = rec.ip_pool_active.strip()
                if (not rec.cisco_pool_expired) and rec.ip_pool_expired:
                    rec.cisco_pool_expired = rec.ip_pool_expired.strip()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Cisco Policies'), 'message': _('Applied from Rate Limit.'), 'type': 'success'}
        }

    def _compute_user_count(self):
        for rec in self:
            rec.user_count = 0
            groupname = rec._groupname()
            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
                # Use alias to support dict/tuple cursors
                cur.execute("SELECT COUNT(*) AS cnt FROM radusergroup WHERE groupname=%s", (groupname,))
                row = cur.fetchone()
                if not row:
                    rec.user_count = 0
                elif isinstance(row, dict):
                    rec.user_count = int(row.get('cnt') or 0)
                else:
                    rec.user_count = int(row[0] or 0)
            except Exception as e:
                _logger.warning('user_count failed for %s: %s', groupname, e)
                rec.user_count = 0
            finally:
                try:
                    conn and conn.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # UI helper
    # -------------------------------------------------------------------------
    def action_view_radius_info(self):
        self.ensure_one()
        grp = self._groupname()  # përdor realin me prefix kompanie
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Plan Info'),
                'message': _(
                    'Plan: %s\n'
                    'Groupname: %s\n'
                    'Users: %s\n'
                    'Last Sync: %s\n'
                    'Status: %s'
                ) % (
                    self.name,
                    grp or '—',
                    self.user_count,
                    self.last_sync_date or 'Never',
                    'Synced' if self.radius_synced else 'Not synced'
                ),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_view_radius_users(self):
        """Simple popup with count (for smart button in view)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Users'),
                'message': _('Group %(g)s has %(n)d user(s) in radusergroup.') % {
                    'g': self._groupname(), 'n': self.user_count
                },
                'type': 'info',
                'sticky': False,
            }
        }

    @api.model
    def action_sync_selected(self, records=None):
        """Batch sync from list view (server action)."""
        recs = self.browse(self.env.context.get('active_ids', []) or [])
        if records:
            recs = records
        if not recs:
            return
        ok = 0
        last_error = None
        for r in recs:
            try:
                r.action_sync_attributes_to_radius()
                ok += 1
            except Exception as e:
                last_error = str(e)
        msg = _('%d plan(s) synced') % ok
        if last_error:
            msg = f"{msg}\n{last_error}"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('RADIUS Sync'), 'message': msg, 'type': 'success' if ok else 'warning'}
        }

    # -------------------------------------------------------------------------
    # RADIUS connection — si te device: company._get_direct_conn()
    # -------------------------------------------------------------------------
    def _get_radius_connection(self):
        self.ensure_one()
        try:
            return (self.company_id or self.env.company)._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % str(e))

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _groupname(self):
        self.ensure_one()
        # PLAN në formatin e unifikuar: UPPER + vetëm A–Z0–9
        base = (self.code or self.name or '').upper()
        grp = re.sub(r'[^A-Z0-9]+', '', base) or 'PLAN'

        # Prefix kompanie: përdor company.code NËSE ekziston, përndryshe name
        comp = (self.company_id or self.env.company)
        comp_base = ((getattr(comp, 'code', None) or comp.name) or '').upper()
        comp_slug = re.sub(r'[^A-Z0-9]+', '', comp_base) or 'COMPANY'

        return f"{comp_slug}:{grp}"

    # -------------------------------------------------------------------------
    # Sync to radgroupreply (NO company_id; vetëm groupname/attribute/op/value)
    # -------------------------------------------------------------------------
    def action_sync_attributes_to_radius(self):
        """
        Upsert plan attributes në radgroupreply:
          - DELETE të gjitha rreshtat ekzistues për groupname
          - INSERT rreshtat aktualë nga attribute_ids
          - Shton automatikisht Mikrotik-Rate-Limit/Session-Timeout/IP-Pool nga fushat convenience nëse mungojnë
          - Shton Cisco-AVPair kur toggli i Cisco është ON dhe fushat janë plotësuar
        """
        ok_count = 0
        names = []
        last_error = None

        # Cisco primary by default
        emit_mk = self._get_conf_bool('asr_radius.emit_mikrotik', False)
        emit_cisco = self._get_conf_bool('asr_radius.emit_cisco', True)

        for rec in self:
            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()

                groupname = rec._groupname()

                # 1) Fshi ekzistueset për këtë grup
                cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))

                # 2) Mblidh rreshtat
                rows, seen = [], set()
                for line in rec.attribute_ids:
                    attr = (line.attribute or '').strip()
                    op = (line.op or ':=').strip()
                    val = (line.value or '').strip()
                    if not attr:
                        continue
                    seen.add(attr.lower())
                    rows.append((groupname, attr, op, val))

                # 3) Convenience fields (MikroTik + standard)
                if rec.rate_limit and emit_mk and 'mikrotik-rate-limit' not in seen:
                    rows.append((groupname, 'Mikrotik-Rate-Limit', ':=', rec.rate_limit.strip()))
                if rec.session_timeout and 'session-timeout' not in seen:
                    rows.append((groupname, 'Session-Timeout', ':=', str(int(rec.session_timeout))))

                # IP Pool for Active Users (standard attr)
                if rec.ip_pool_active and 'framed-pool' not in seen:
                    rows.append((groupname, 'Framed-Pool', ':=', rec.ip_pool_active.strip()))

                # Defaults
                if 'acct-interim-interval' not in seen:
                    rows.append((groupname, 'Acct-Interim-Interval', ':=', '300'))
                if 'idle-timeout' not in seen:
                    rows.append((groupname, 'Idle-Timeout', ':=', '600'))

                # 4) Cisco optional VSAs (only if toggled)
                if emit_cisco:
                    if rec.cisco_policy_in:
                        rows.append((groupname, 'Cisco-AVPair', ':=', f"subscriber:service-policy-in {rec.cisco_policy_in.strip()}"))
                    if rec.cisco_policy_out:
                        rows.append((groupname, 'Cisco-AVPair', ':=', f"subscriber:service-policy-out {rec.cisco_policy_out.strip()}"))
                    if rec.cisco_pool_active:
                        rows.append((groupname, 'Cisco-AVPair', ':=', f"ip:addr-pool={rec.cisco_pool_active.strip()}"))

                # 5) INSERT
                if rows:
                    cur.executemany(
                        "INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s,%s,%s,%s)",
                        rows
                    )

                conn.commit()

                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })
                try:
                    rec.message_post(body=_('Synchronized plan %s (%s) to RADIUS.') % (rec.name, groupname))
                except Exception:
                    pass

                ok_count += 1
                names.append(groupname)

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                _logger.exception('Failed to sync plan %s', rec.name)
                rec.sudo().write({
                    'radius_synced': False,
                    'last_sync_error': last_error,
                    'last_sync_date': fields.Datetime.now(),
                })
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Notifikimi për UI
        if ok_count == len(self):
            msg = _('Plan "%s" synced to radgroupreply') % (names[0]) if ok_count == 1 else _(
                '%d subscription(s) synced successfully') % ok_count
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync'), 'message': msg, 'type': 'success', 'sticky': False}
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d succeeded, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    # -------------------------------------------------------------------------
    # Remove from RADIUS (delete group attributes)
    # -------------------------------------------------------------------------
    def action_remove_from_radius(self):
        ok_count, names, last_error = 0, [], None

        for rec in self:
            try:
                rec._remove_from_radius()
                ok_count += 1
                names.append(rec._groupname())
            except Exception as e:
                last_error = str(e)

        if ok_count == len(self):
            msg = _('Plan "%s" removed from radgroupreply') % (names[0]) if ok_count == 1 else _(
                '%d plan(s) removed from RADIUS') % ok_count
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal'), 'message': msg, 'type': 'info', 'sticky': False}
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d removed, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    def _remove_from_radius(self):
        self.ensure_one()
        conn = None
        try:
            conn = self._get_radius_connection()
            cur = conn.cursor()
            groupname = self._groupname()

            cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))
            conn.commit()

            self.sudo().write({
                'radius_synced': False,
                'last_sync_date': fields.Datetime.now(),
                'last_sync_error': False,
            })

            try:
                self.message_post(body=_('Removed plan %s (%s) from RADIUS.') % (self.name, groupname))
            except Exception:
                pass

            _logger.info('Removed plan %s from RADIUS', self.name)

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            err = str(e)
            _logger.error('Failed to remove plan %s from RADIUS: %s', self.name, err)
            self.message_post(body=_('RADIUS removal failed: %s') % err, message_type='notification',
                              subtype_xmlid='mail.mt_note')
            raise UserError(_('RADIUS removal failed:\n%s') % err)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # ORM Hooks (optional behaviours)
    # -------------------------------------------------------------------------
    def unlink(self):
        # Hiqe nga RADIUS përpara se të fshihet nga Odoo
        for rec in self:
            if rec.radius_synced:
                try:
                    rec._remove_from_radius()
                except Exception as e:
                    _logger.warning('Could not remove plan %s from RADIUS on delete: %s', rec.name, e)
        return super().unlink()


class AsrRadiusAttribute(models.Model):
    _name = "asr.radius.attribute"
    _description = "RADIUS Attribute for Plan"
    _order = "id asc"
    _check_company_auto = True  # <-- SHTUAR

    attribute = fields.Char(required=True, help="e.g. Mikrotik-Rate-Limit, Session-Timeout, Idle-Timeout")
    op = fields.Char(default=':=', help="Operator, e.g. :=, ==, +=, =")
    value = fields.Char(required=True)
    subscription_id = fields.Many2one('asr.subscription', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True, readonly=True)

    @api.constrains('op')
    def _check_op(self):
        for rec in self:
            if rec.op not in (':=', '==', '+=', '='):
                raise ValidationError(_('Invalid operator: %s') % (rec.op or ''))

    # Në çdo ndryshim të linjave → shëno planin si jo-sinkron
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.mapped('subscription_id').sudo().write({'radius_synced': False})
        return recs

    def write(self, vals):
        res = super().write(vals)
        self.mapped('subscription_id').sudo().write({'radius_synced': False})
        return res

    def unlink(self):
        subs = self.mapped('subscription_id')
        res = super().unlink()
        subs.sudo().write({'radius_synced': False})
        return res

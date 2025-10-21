# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

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
    _check_company_auto = True

    # ---- Basic Fields ----
    name = fields.Char(required=True, tracking=True)
    code = fields.Char(help="Group name in FreeRADIUS (radgroupreply.groupname). Auto-filled from name if empty.")
    rate_limit = fields.Char(help="e.g. '49M/49M' or '300M/300M'. Generates Cisco service-policy dynamically.")
    session_timeout = fields.Integer(help="Optional Session-Timeout (seconds)")
    price = fields.Float(help="Default price per cycle (billing in Phase 4/5).")
    product_id = fields.Many2one('product.product', string='Product', help='Product for invoicing (Phase 4/5).')

    # Odoo-only multi-company
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    # ---- IP Pool Management ----
    ip_pool_active = fields.Char(
        string='IP Pool (Active Users)',
        help='Framed-Pool for active/paying users',
        tracking=True
    )
    ip_pool_expired = fields.Char(
        string='Next Pool Expiry',
        help='Pool for expired users (no internet; only portal allowed by firewall/policy).',
        tracking=True
    )

    # ---- UX / Stats ----
    user_count = fields.Integer(string='Users (RADIUS)', compute='_compute_user_count', store=False)

    # Attributes
    attribute_ids = fields.One2many('asr.radius.attribute', 'subscription_id', string='RADIUS Attributes')

    # Sync tracking
    radius_synced = fields.Boolean(default=False, readonly=True, tracking=True)
    last_sync_date = fields.Datetime(readonly=True)
    last_sync_error = fields.Text(readonly=True)

    # Accounting interval
    acct_interim_interval = fields.Integer(
        string="Acct Interim Interval (s)",
        default=300,
        help="How often NAS sends accounting interim updates."
    )

    # Code unique per company
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

    def _compute_user_count(self):
        for rec in self:
            rec.user_count = 0
            groupname = rec._groupname()
            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
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
        grp = self._groupname()
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
    # RADIUS connection
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
        # PLAN format: UPPER + only A-Z0-9
        base = (self.code or self.name or '').upper()
        grp = re.sub(r'[^A-Z0-9]+', '', base) or 'PLAN'

        # Company prefix
        comp = (self.company_id or self.env.company)
        comp_base = ((getattr(comp, 'code', None) or comp.name) or '').upper()
        comp_slug = re.sub(r'[^A-Z0-9]+', '', comp_base) or 'COMPANY'

        return f"{comp_slug}:{grp}"

    # -------------------------------------------------------------------------
    # Sync to radgroupreply
    # -------------------------------------------------------------------------
    def action_sync_attributes_to_radius(self):
        """
        ✅ FIXED: Cisco AVPair format for ASR9k/IOS-XE
        Format: ip:interface-config=service-policy input 49M
        """
        ok_count = 0
        names = []
        last_error = None

        for rec in self:
            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
                groupname = rec._groupname()

                # 1) DELETE old attributes
                cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))

                # 2) Parse rate_limit → label (49M, 300M, etc.)
                rate_label = None
                if rec.rate_limit:
                    # Parse "49M/49M" → "49M", "49/49" → "49M", "300M/300M" → "300M"
                    rl = rec.rate_limit.strip()

                    # Try "X/Y" format
                    m = re.match(r'^\s*([0-9]+)[mM]?\s*/\s*([0-9]+)[mM]?\s*$', rl)
                    if m:
                        # Use download speed (second number) as primary
                        rate_label = f"{m.group(2)}M"
                    else:
                        # Try single number "49M" or "300M"
                        m2 = re.match(r'^\s*([0-9]+)[mM]?\s*$', rl)
                        if m2:
                            rate_label = f"{m2.group(1)}M"
                        else:
                            _logger.warning('Invalid rate_limit format for plan %s: %s', rec.name, rl)

                # 3) Build rows
                rows = []

                # ✅ CISCO AVPair - ABSOLUTE FORMAT
                if rate_label:
                    rows.append((
                        groupname,
                        'Cisco-AVPair',
                        ':=',
                        f'ip:interface-config=service-policy input {rate_label}'
                    ))
                    rows.append((
                        groupname,
                        'Cisco-AVPair',
                        ':=',
                        f'ip:interface-config=service-policy output {rate_label}'
                    ))

                # ✅ IP Pool (standard Framed-Pool)
                if rec.ip_pool_active:
                    rows.append((groupname, 'Framed-Pool', ':=', rec.ip_pool_active.strip()))

                # ✅ Session Timeout (optional)
                if rec.session_timeout:
                    rows.append((groupname, 'Session-Timeout', ':=', str(int(rec.session_timeout))))

                # ✅ Accounting & Idle defaults
                rows.append((groupname, 'Acct-Interim-Interval', ':=', str(rec.acct_interim_interval or 300)))
                rows.append((groupname, 'Idle-Timeout', ':=', '600'))

                # ✅ Custom attributes (if any)
                seen = {'cisco-avpair', 'framed-pool', 'session-timeout', 'acct-interim-interval', 'idle-timeout'}
                for line in rec.attribute_ids:
                    attr = (line.attribute or '').strip()
                    if not attr or attr.lower() in seen:
                        continue
                    rows.append((groupname, attr, line.op or ':=', (line.value or '').strip()))

                # 4) INSERT
                if rows:
                    cur.executemany(
                        "INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s,%s,%s,%s)",
                        rows
                    )

                conn.commit()

                # 5) Update Odoo record
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

        # Notification
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
        # Remove from RADIUS before deleting from Odoo
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
    _check_company_auto = True

    attribute = fields.Char(required=True, help="e.g. Session-Timeout, Idle-Timeout, custom RADIUS attribute")
    op = fields.Char(default=':=', help="Operator, e.g. :=, ==, +=, =")
    value = fields.Char(required=True)
    subscription_id = fields.Many2one('asr.subscription', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True, readonly=True)

    @api.constrains('op')
    def _check_op(self):
        for rec in self:
            if rec.op not in (':=', '==', '+=', '='):
                raise ValidationError(_('Invalid operator: %s') % (rec.op or ''))

    # Mark plan as not synced on any line change
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
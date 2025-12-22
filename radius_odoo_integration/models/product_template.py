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


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ==================== RADIUS SERVICE FLAG ====================
    is_radius_service = fields.Boolean(
        string="RADIUS Service",
        default=False,
        help="Enable this to manage this product as a RADIUS subscription package"
    )

    # Link to asr.subscription
    radius_subscription_id = fields.Many2one(
        'asr.subscription',
        string="RADIUS Subscription",
        ondelete='set null',
        help="Linked RADIUS subscription record",
        index=True
    )

    # ==================== RADIUS PLAN FIELDS ====================
    radius_plan_code = fields.Char(
        string="RADIUS Plan Code",
        help="Group name in FreeRADIUS (radgroupreply.groupname). Auto-filled from name if empty."
    )

    radius_rate_limit = fields.Char(
        string="Rate Limit",
        help="e.g. '49M/49M' or '300M/300M'. Generates Cisco service-policy dynamically."
    )

    radius_session_timeout = fields.Integer(
        string="Session Timeout (s)",
        help="Optional Session-Timeout in seconds"
    )

    # ==================== SLA (Service Level Agreement) ====================
    sla_level = fields.Selection([
        ('1', 'SLA 1 - Individual/Residential'),
        ('2', 'SLA 2 - Small Business'),
        ('3', 'SLA 3 - Enterprise'),
    ], string="SLA Level",
        default='1',
        help="Service Level Agreement: 1=Residential, 2=Small Business, 3=Enterprise")

    # ==================== IP POOL MANAGEMENT ====================
    ip_pool_active = fields.Selection(
        selection='_get_ip_pool_selection',
        string='IP Pool (Active Users)',
        help='Framed-Pool for active/paying users. Select from list.',
    )
    ip_pool_expired = fields.Selection(
        selection='_get_ip_pool_selection',
        string='IP Pool (Expired)',
        help='Pool for expired users (no internet; only portal allowed).',
    )

    # ==================== ACCOUNTING INTERVAL ====================
    acct_interim_interval = fields.Integer(
        string="Acct Interim Interval (s)",
        default=300,
        help="How often NAS sends accounting interim updates."
    )

    # ==================== RADIUS ATTRIBUTES ====================
    radius_attribute_ids = fields.One2many(
        'product.radius.attribute',
        'product_tmpl_id',
        string='Custom RADIUS Attributes'
    )

    # ==================== RADIUS SYNC STATUS ====================
    radius_synced = fields.Boolean(
        string="Synced to RADIUS",
        default=False,
        readonly=True,
        copy=False
    )
    last_sync_date = fields.Datetime(
        string="Last RADIUS Sync",
        readonly=True,
        copy=False
    )
    last_sync_error = fields.Text(
        string="Last Sync Error",
        readonly=True,
        copy=False
    )

    # ==================== STATISTICS ====================
    radius_user_count = fields.Integer(
        string='Active RADIUS Users',
        compute='_compute_radius_user_count',
        store=False
    )

    # ==================== DUMMY FIELDS FOR COMPATIBILITY ====================
    service_upsell_threshold = fields.Float(
        string="Upsell Threshold",
        default=0.0,
        help="Dummy field - install sale_upsell for real functionality"
    )
    service_upsell_threshold_ratio = fields.Float(
        string="Upsell Threshold Ratio",
        default=1.0,
        help="Dummy field - install sale_upsell for real functionality"
    )

    # ==================== SQL CONSTRAINTS ====================
    _sql_constraints = [
        ('radius_plan_code_company_unique',
         'unique(radius_plan_code, company_id)',
         'RADIUS plan code must be unique per company.')
    ]

    # ==================== ONCHANGE ====================
    @api.onchange('name')
    def _onchange_name_set_plan_code(self):
        for rec in self:
            if rec.is_radius_service and not rec.radius_plan_code:
                rec.radius_plan_code = _slugify(rec.name)

    # ==================== CREATE ====================
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-create linked asr.subscription for RADIUS services"""
        products = super(ProductTemplate, self).create(vals_list)

        # Auto-create linked asr.subscription for RADIUS services
        for product in products:
            if product.is_radius_service and not product.radius_subscription_id:
                try:
                    subscription_vals = {
                        'name': product.name,
                        'code': product.radius_plan_code or _slugify(product.name),
                        'rate_limit': product.radius_rate_limit,
                        'session_timeout': product.radius_session_timeout,
                        'sla_level': product.sla_level or '1',
                        'ip_pool_active': product.ip_pool_active,
                        'ip_pool_expired': product.ip_pool_expired,
                        'acct_interim_interval': product.acct_interim_interval or 300,
                        'company_id': product.company_id.id,
                        'product_tmpl_id': product.id,
                        'radius_synced': False,
                    }

                    subscription = self.env['asr.subscription'].sudo().create(subscription_vals)
                    product.sudo().write({'radius_subscription_id': subscription.id})
                    _logger.info("Auto-created asr.subscription %s for product %s", subscription.code, product.name)

                except Exception as e:
                    _logger.error("Failed to auto-create asr.subscription for product %s: %s", product.name, e)

        return products

    # ==================== COMPUTED METHODS ====================
    @api.model
    def _get_ip_pool_selection(self):
        """Return list of available IP pools from radippool table"""
        # Default pools
        default_pools = [
            'PPP-POOL',
            'PPP-POOL-ACTIVE',
            'PPP-POOL-EXPIRED',
            'POOL-STANDARD',
            'POOL-BUSINESS',
            'POOL-VIP',
        ]

        pools_set = set(default_pools)

        # Try to fetch from FreeRADIUS radippool table
        try:
            conn = self.env.company._get_direct_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT pool_name FROM radippool ORDER BY pool_name")
                rows = cur.fetchall()

                if rows:
                    for row in rows:
                        pool_name = row.get('pool_name') if isinstance(row, dict) else row[0]
                        if pool_name and pool_name.strip():
                            pools_set.add(pool_name)
            conn.close()
        except Exception as e:
            _logger.debug('Could not fetch IP pools from radippool: %s', e)

        # Return as list of tuples for Selection compatibility
        result = [(p, p) for p in sorted(pools_set)]
        return result

    def _compute_radius_user_count(self):
        """Count active RADIUS users using this plan"""
        for rec in self:
            if not rec.is_radius_service:
                rec.radius_user_count = 0
                continue

            groupname = rec._get_radius_groupname()
            if not groupname:
                rec.radius_user_count = 0
                continue

            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM radusergroup WHERE groupname=%s",
                    (groupname,)
                )
                row = cur.fetchone()
                if isinstance(row, dict):
                    rec.radius_user_count = int(row.get('cnt') or 0)
                else:
                    rec.radius_user_count = int(row[0] or 0)
            except Exception as e:
                _logger.warning('radius_user_count failed for %s: %s', groupname, e)
                rec.radius_user_count = 0
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    # ==================== RADIUS CONNECTION HELPER ====================
    def _get_radius_connection(self):
        """Get RADIUS MySQL connection"""
        self.ensure_one()
        try:
            return (self.company_id or self.env.company)._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % str(e))

    # ==================== HELPERS ====================
    def _get_radius_groupname(self):
        """Generate RADIUS group name: COMPANY:PLAN"""
        self.ensure_one()
        if not self.is_radius_service:
            return False

        # Plan code (uppercase, alphanumeric only)
        base = (self.radius_plan_code or self.name or '').upper()
        grp = re.sub(r'[^A-Z0-9]+', '', base) or 'PLAN'

        # Company prefix
        comp = self.company_id or self.env.company
        comp_base = ((getattr(comp, 'code', None) or comp.name) or '').upper()
        comp_slug = re.sub(r'[^A-Z0-9]+', '', comp_base) or 'COMPANY'

        return f"{comp_slug}:{grp}"

    # ==================== UI ACTION ====================
    def action_view_radius_users(self):
        """View RADIUS customers using this product/plan"""
        self.ensure_one()
        if not self.is_radius_service:
            raise UserError(_("Product '%s' is not a RADIUS service.") % self.name)

        groupname = self._get_radius_groupname()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Users'),
                'message': _('Group %(g)s has %(n)d user(s) in radusergroup.') % {
                    'g': groupname, 'n': self.radius_user_count
                },
                'type': 'info',
                'sticky': False,
            }
        }

    # ==================== RADIUS SYNC ACTIONS ====================
    def action_sync_to_radius(self):
        """
        Sync RADIUS service plan to FreeRADIUS radgroupreply table
        Generates Cisco AVPair for ASR9k/IOS-XE service policies
        """
        ok_count = 0
        names = []
        last_error = None

        for rec in self:
            if not rec.is_radius_service:
                raise UserError(_("Product '%s' is not a RADIUS service.") % rec.name)

            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
                groupname = rec._get_radius_groupname()

                # 1) DELETE old attributes
                cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))

                # 2) Parse rate_limit → label (49M, 300M, etc.)
                rate_label = None
                if rec.radius_rate_limit:
                    rl = rec.radius_rate_limit.strip()

                    # Try "X/Y" format (e.g., "49M/49M")
                    m = re.match(r'^\s*([0-9]+)[mM]?\s*/\s*([0-9]+)[mM]?\s*$', rl)
                    if m:
                        # Use download speed (second number)
                        rate_label = f"{m.group(2)}M"
                    else:
                        # Try single number "49M" or "300M"
                        m2 = re.match(r'^\s*([0-9]+)[mM]?\s*$', rl)
                        if m2:
                            rate_label = f"{m2.group(1)}M"
                        else:
                            _logger.warning('Invalid rate_limit format for plan %s: %s', rec.name, rl)

                # 3) Build rows for INSERT
                rows = []

                # ✅ Cisco AVPair - Service Policy (for ASR9k/IOS-XE)
                if rate_label:
                    rows.append((
                        groupname,
                        'Cisco-AVPair',
                        '+=',
                        f'ip:interface-config=service-policy input {rate_label}'
                    ))
                    rows.append((
                        groupname,
                        'Cisco-AVPair',
                        '+=',
                        f'ip:interface-config=service-policy output {rate_label}'
                    ))

                # ✅ IP Pool (Framed-Pool)
                if rec.ip_pool_active:
                    rows.append((groupname, 'Framed-Pool', '=', rec.ip_pool_active.strip()))

                # ✅ Session Timeout
                if rec.radius_session_timeout:
                    rows.append((groupname, 'Session-Timeout', ':=', str(int(rec.radius_session_timeout))))

                # ✅ Accounting & Idle defaults
                rows.append((groupname, 'Acct-Interim-Interval', ':=', str(rec.acct_interim_interval or 300)))
                rows.append((groupname, 'Idle-Timeout', ':=', '600'))

                # ✅ Custom attributes
                seen = {'cisco-avpair', 'framed-pool', 'session-timeout', 'acct-interim-interval', 'idle-timeout'}
                for line in rec.radius_attribute_ids:
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

                rec.message_post(
                    body=_('Synchronized RADIUS plan %s (%s) to FreeRADIUS.') % (rec.name, groupname)
                )

                ok_count += 1
                names.append(groupname)

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                _logger.exception('Failed to sync RADIUS plan %s', rec.name)
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

        # Return notification
        if ok_count == len(self):
            msg = _('Plan "%s" synced to RADIUS') % (names[0]) if ok_count == 1 else (
                _('%d plan(s) synced successfully') % ok_count)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Sync'),
                    'message': msg,
                    'type': 'success',
                    'sticky': False
                }
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d succeeded, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Sync (Partial/Failed)'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False
                }
            }

    def action_remove_from_radius(self):
        """Remove RADIUS plan from radgroupreply table"""
        ok_count = 0
        names = []
        last_error = None

        for rec in self:
            if not rec.is_radius_service:
                raise UserError(_("Product '%s' is not a RADIUS service.") % rec.name)

            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()
                groupname = rec._get_radius_groupname()

                cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))
                conn.commit()

                rec.sudo().write({
                    'radius_synced': False,
                    'last_sync_date': fields.Datetime.now(),
                    'last_sync_error': False,
                })

                rec.message_post(
                    body=_('Removed RADIUS plan %s (%s) from FreeRADIUS.') % (rec.name, groupname)
                )

                ok_count += 1
                names.append(groupname)

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                _logger.error('Failed to remove plan %s from RADIUS: %s', rec.name, e)
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Return notification
        if ok_count == len(self):
            msg = _('Plan "%s" removed from RADIUS') % (names[0]) if ok_count == 1 else (
                _('%d plan(s) removed from RADIUS') % ok_count)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Removal'),
                    'message': msg,
                    'type': 'info',
                    'sticky': False
                }
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d removed, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Removal (Partial/Failed)'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False
                }
            }

    # ==================== ORM HOOKS ====================
    def unlink(self):
        """Remove from RADIUS before deleting from Odoo"""
        for rec in self:
            if rec.is_radius_service and rec.radius_synced:
                try:
                    rec.action_remove_from_radius()
                except Exception as e:
                    _logger.warning('Could not remove plan %s from RADIUS on delete: %s', rec.name, e)
        return super().unlink()


class ProductRadiusAttribute(models.Model):
    """Custom RADIUS attributes for products"""
    _name = "product.radius.attribute"
    _description = "RADIUS Attribute for Product"
    _order = "id asc"
    _check_company_auto = True

    attribute = fields.Char(
        string="Attribute",
        required=True,
        help="e.g. Session-Timeout, Idle-Timeout, custom RADIUS attribute"
    )
    op = fields.Char(
        string="Operator",
        default=':=',
        help="Operator: :=, ==, +=, ="
    )
    value = fields.Char(
        string="Value",
        required=True
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string="Product",
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        'res.company',
        related='product_tmpl_id.company_id',
        store=True,
        readonly=True
    )

    @api.constrains('op')
    def _check_op(self):
        for rec in self:
            if rec.op not in (':=', '==', '+=', '='):
                raise ValidationError(_('Invalid operator: %s') % (rec.op or ''))

    # Mark product as not synced on any line change
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.mapped('product_tmpl_id').sudo().write({'radius_synced': False})
        return recs

    def write(self, vals):
        res = super().write(vals)
        self.mapped('product_tmpl_id').sudo().write({'radius_synced': False})
        return res

    def unlink(self):
        products = self.mapped('product_tmpl_id')
        res = super().unlink()
        products.sudo().write({'radius_synced': False})
        return res

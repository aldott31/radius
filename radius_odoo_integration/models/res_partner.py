# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re
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


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ==================== RADIUS CUSTOMER FLAG ====================
    # Note: All partners are RADIUS customers by default
    is_radius_customer = fields.Boolean(
        string="RADIUS Customer",
        default=True,
        tracking=True,
        help="All contacts are RADIUS/ISP customers by default"
    )

    # Customer lifecycle status
    customer_status = fields.Selection([
        ('lead', 'Lead'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('churned', 'Churned')
    ], string="Customer Status", default='lead', tracking=True,
        help="Customer lifecycle stage")

    # Link to asr.radius.user
    radius_user_id = fields.Many2one(
        'asr.radius.user',
        string="RADIUS User",
        ondelete='set null',
        help="Linked RADIUS user record",
        index=True,
        tracking=True
    )

    # ==================== RADIUS AUTHENTICATION FIELDS ====================
    radius_username = fields.Char(
        string="RADIUS Username",
        index=True,
        copy=False,
        tracking=True,
        help="Auto-generated if left empty (format: 445XXXXXX)"
    )
    radius_password = fields.Char(
        string="RADIUS Password",
        copy=False,
        help="Auto-generated if left empty"
    )

    # ==================== RADIUS SUBSCRIPTION ====================
    subscription_id = fields.Many2one(
        'asr.subscription',
        string="Subscription Package",
        ondelete='restrict',
        tracking=True,
        help="Service plan with speed, IP pool, and SLA"
    )

    # ==================== RADIUS DEVICE ====================
    device_id = fields.Many2one(
        'asr.device',
        string="NAS Device",
        ondelete='set null',
        help="RADIUS NAS device (optional)"
    )

    # ==================== RADIUS SYNC STATUS ====================
    radius_synced = fields.Boolean(
        string="Synced to RADIUS",
        default=False,
        copy=False,
        tracking=True,
        help="Indicates if this user is synced to FreeRADIUS MySQL database"
    )
    last_sync_date = fields.Datetime(
        string="Last RADIUS Sync",
        copy=False,
        readonly=True
    )
    last_sync_error = fields.Text(
        string="Last Sync Error",
        copy=False,
        readonly=True
    )

    # ==================== COMPUTED RADIUS FIELDS ====================
    groupname = fields.Char(
        string="RADIUS Group Name",
        compute='_compute_groupname',
        store=False,
        help="Computed as COMPANY:PLAN"
    )

    current_radius_group = fields.Char(
        string="Current RADIUS Group (Live)",
        compute="_compute_current_radius_group",
        store=False,
        help="Read live from radusergroup table"
    )

    is_suspended = fields.Boolean(
        string="Suspended (Live)",
        compute="_compute_is_suspended",
        store=False,
        help="Checks if user is in SUSPENDED group"
    )

    # ==================== SLA (from Subscription) ====================
    sla_level = fields.Selection([
        ('1', 'SLA 1 - Individual'),
        ('2', 'SLA 2 - Small Business'),
        ('3', 'SLA 3 - Enterprise'),
    ], string="SLA Level",
        related='subscription_id.sla_level',
        store=True,
        readonly=True,
        help="Inherited from subscription package. 1=Residential, 2=Small Biz, 3=Large Corp")

    # ==================== BUSINESS INFO ====================
    is_business = fields.Boolean(
        string="Is Business",
        compute='_compute_is_business',
        store=True,
        help="SLA 2 and 3 are business customers"
    )
    nipt = fields.Char(
        string="NIPT/VAT",
        tracking=True,
        help="Business Tax ID (required for SLA 2/3)"
    )

    # ==================== CONTRACT & BILLING ====================
    contract_start_date = fields.Date(
        string="Contract Start",
        tracking=True
    )
    contract_end_date = fields.Date(
        string="Contract End",
        tracking=True
    )
    billing_day = fields.Integer(
        string="Billing Day of Month",
        default=1,
        help="Day of month for invoice generation (1-28)"
    )

    # ==================== INSTALLATION ====================
    installation_date = fields.Date(
        string="Installation Date",
        tracking=True
    )
    installation_technician_id = fields.Many2one(
        'res.users',
        string="Installed By"
    )

    # ==================== PPPOE STATUS (LIVE) ====================
    pppoe_status = fields.Selection(
        [('down', 'Down'), ('up', 'Up')],
        string="PPPoE Status",
        compute='_compute_pppoe_status',
        store=False
    )
    last_session_start = fields.Datetime(
        string="Last Login",
        compute='_compute_pppoe_status',
        store=False
    )
    current_framed_ip = fields.Char(
        string="IP Address (Current)",
        compute='_compute_pppoe_status',
        store=False
    )
    current_interface = fields.Char(
        string="Interface (Current)",
        compute='_compute_pppoe_status',
        store=False
    )

    active_sessions_count = fields.Integer(
        string="Active Sessions",
        compute='_compute_session_counts',
        store=False
    )
    total_sessions_count = fields.Integer(
        string="Total Sessions",
        compute='_compute_session_counts',
        store=False
    )

    # ==================== GEOLOCATION ====================
    partner_latitude = fields.Float(
        string="Geo Latitude",
        digits=(10, 7)
    )
    partner_longitude = fields.Float(
        string="Geo Longitude",
        digits=(10, 7)
    )

    # ==================== DESCRIPTION & NOTES ====================
    description = fields.Text(
        string="Description",
        help="Customer description/notes"
    )

    internal_notes = fields.Text(
        string="Internal Notes",
        help="Private notes (not visible to customer)"
    )
    customer_notes = fields.Text(
        string="Customer Notes",
        help="Notes visible to customer (e.g., in portal)"
    )

    # ==================== PAYMENT TRACKING ====================
    service_paid_until = fields.Date(
        string="Service Paid Until",
        tracking=True,
        help="Date until which service is paid for"
    )
    grace_days_debt = fields.Integer(
        string="Grace Days (Debt)",
        default=0,
        tracking=True,
        help="Number of days customer owes due to grace period extensions. "
             "When customer pays, subscription is calculated from original expiry date (service_paid_until - grace_days_debt)"
    )
    last_payment_date = fields.Date(
        string="Last Payment Date",
        readonly=True,
        tracking=True,
        help="Date of most recent payment (updated automatically when invoice is paid)"
    )
    last_payment_amount = fields.Float(
        string="Last Payment Amount",
        readonly=True,
        tracking=True,
        help="Amount of most recent payment (updated automatically when invoice is paid)"
    )
    total_paid_amount = fields.Float(
        string="Total Paid Amount",
        readonly=True,
        tracking=True,
        help="Total amount paid by customer (updated automatically when invoice is paid)"
    )
    first_payment_date = fields.Date(
        string="First Payment Date",
        readonly=True,
        help="Date of first payment (updated automatically when invoice is paid)"
    )
    payment_balance = fields.Float(
        string="Payment Balance",
        compute='_compute_payment_balance',
        help="Current payment balance (receivable)"
    )

    # ==================== REFERRAL/LINKS ====================
    referral_code = fields.Char(
        string="Referral Code",
        help="Referral link/code for this customer"
    )
    referred_by_id = fields.Many2one(
        'res.partner',
        string="Referred By",
        help="Customer who referred this customer"
    )

    # ==================== SALES & INVOICES COUNTS ====================
    sale_order_count = fields.Integer(
        string="Sale Orders",
        compute='_compute_sale_invoice_counts',
        help="Number of sale orders"
    )
    invoice_count = fields.Integer(
        string="Invoices",
        compute='_compute_sale_invoice_counts',
        help="Number of invoices"
    )

    # ==================== INFRASTRUCTURE LINK ====================
    access_device_id = fields.Many2one(
        'crm.access.device',
        string="Access Device",
        tracking=True,
        ondelete='set null',
        help="Physical device (OLT/DSLAM) this customer is connected to"
    )
    pop_id = fields.Many2one(
        'crm.pop',
        string="POP",
        compute='_compute_infrastructure_ids',
        store=True,
        readonly=True
    )
    city_id = fields.Many2one(
        'crm.city',
        string="City",
        compute='_compute_infrastructure_ids',
        store=True,
        readonly=True
    )

    # OLT Login Port (e.g., '10.50.60.103 pon 1/2/2/27:1662')
    olt_login_port = fields.Char(
        string="Login Port (OLT)",
        tracking=True
    )

    # Fiber Management
    fiber_closure_id = fields.Many2one(
        'crm.fiber.closure',
        string='Fiber Closure',
        tracking=True
    )
    fiber_core_number = fields.Integer(
        string='Fiber Core #',
        tracking=True
    )
    fiber_color = fields.Selection([
        ('blue', 'Blue'), ('orange', 'Orange'), ('green', 'Green'),
        ('brown', 'Brown'), ('slate', 'Slate'), ('white', 'White'),
        ('red', 'Red'), ('black', 'Black'), ('yellow', 'Yellow'),
        ('violet', 'Violet'), ('rose', 'Rose'), ('aqua', 'Aqua'),
    ], string='Fiber Color', tracking=True)

    # Phone Secondary
    phone_secondary = fields.Char(
        string="Secondary Phone",
        help="Alternative contact number"
    )

    # ONT Info
    ont_serial = fields.Char(
        string='ONT Serial Number',
        tracking=True,
        related='radius_user_id.ont_serial',
        store=True,
        readonly=False,
    )
    # KJO ËSHTË DISPLAY FIELD – formatohet nga radius_user_id.olt_pon_port + OLT IP + VLAN
    olt_pon_port = fields.Char(
        string='PON Port',
        tracking=True,
        compute='_compute_olt_pon_port',
        store=True,
        readonly=False,
    )
    olt_ont_id = fields.Char(
        string='ONT ID',
        tracking=True,
        related='radius_user_id.olt_ont_id',
        store=True,
        readonly=False,
    )

    fiber_splice_loss_db = fields.Float(
        string='Splice Loss (dB)',
        digits=(4, 2)
    )
    fiber_total_loss_db = fields.Float(
        string='Total Loss (dB)',
        digits=(4, 2)
    )

    # ==================== SQL CONSTRAINTS ====================
    _sql_constraints = [
        ('uniq_radius_username_company',
         'unique(radius_username, company_id)',
         'RADIUS username must be unique per company.')
    ]

    # ==================== AUTO-GENERATION HELPERS ====================
    def _generate_username(self):
        """Generate next RADIUS username using sequence (445XXXXXX format)"""
        return self.env['ir.sequence'].next_by_code('res.partner.radius.username') or '445000000'

    def _generate_password(self, length=12):
        """Generate secure random password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    # ==================== PON PORT DISPLAY ====================
    @api.depends('radius_user_id.olt_pon_port', 'access_device_id.ip_address')
    def _compute_olt_pon_port(self):
        """
        Shfaq PON Port si:
        '10.50.60.99 pon 1/9/6/33:1900'

        Bazuar në:
        - raw: asr.radius.user.olt_pon_port (p.sh. 'gpon-olt_1/9/6:33')
        - access_device_id.ip_address
        - VLAN nga access_device (internet_vlan / vlan_internet / vlan_id)
        """
        for rec in self:
            raw = (rec.radius_user_id.olt_pon_port or '').strip() if rec.radius_user_id else ''
            if not raw:
                rec.olt_pon_port = False
                continue

            ip = ''
            if rec.access_device_id and rec.access_device_id.ip_address:
                ip = rec.access_device_id.ip_address.strip()

            # Nëse raw është tashmë në formatin e ri me IP, e lëmë ashtu
            if ip and raw.startswith(ip + ' pon '):
                rec.olt_pon_port = raw
                continue

            # Prisja standarde 'gpon-olt_1/9/6:33'
            m = re.match(r'^gpon-olt_(\d+/\d+/\d+):(\d+)$', raw)
            if not m:
                # Nëse nuk e gjejmë dot, shfaq raw
                rec.olt_pon_port = raw
                continue

            path = m.group(1)   # 1/9/6
            onu_id = m.group(2) # 33

            # VLAN – supozojmë që e ke në access_device
            vlan = getattr(rec.access_device_id, 'internet_vlan', False) \
                or getattr(rec.access_device_id, 'vlan_internet', False) \
                or getattr(rec.access_device_id, 'vlan_id', False)

            if ip and vlan:
                rec.olt_pon_port = f"{ip} pon {path}/{onu_id}:{vlan}"
            elif ip:
                rec.olt_pon_port = f"{ip} pon {path}/{onu_id}"
            else:
                # pa IP, të paktën path/onu
                rec.olt_pon_port = f"{path}/{onu_id}"

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-create asr.radius.user for all partners"""
        # Skip radius_user creation if flag is set (to prevent recursion)
        skip_radius_creation = self.env.context.get('_skip_partner_creation')

        partners = super(ResPartner, self).create(vals_list)

        if skip_radius_creation:
            return partners

        # Auto-create asr.radius.user for all partners (all are RADIUS customers now)
        for partner in partners:
            if not partner.radius_user_id:
                try:
                    # Auto-generate username/password if not set
                    if not partner.radius_username:
                        partner.sudo().write({'radius_username': partner._generate_username()})
                    if not partner.radius_password:
                        partner.sudo().write({'radius_password': partner._generate_password()})

                    # Get company: partner's company or env.company
                    company = partner.company_id or self.env.company

                    radius_user_vals = {
                        'name': partner.name,
                        'username': partner.radius_username,
                        'radius_password': partner.radius_password,
                        'subscription_id': partner.subscription_id.id if partner.subscription_id else False,
                        'device_id': partner.device_id.id if partner.device_id else False,
                        'company_id': company.id,  # Ensure company_id is set
                        'partner_id': partner.id,
                        'radius_synced': False,
                    }

                    # Create with context flag to prevent recursion
                    radius_user = self.env['asr.radius.user'].with_context(
                        _skip_partner_creation=True
                    ).sudo().create(radius_user_vals)

                    partner.sudo().write({'radius_user_id': radius_user.id})
                    _logger.info(
                        "Auto-created asr.radius.user %s for partner %s",
                        radius_user.username,
                        partner.name
                    )

                except Exception as e:
                    _logger.error(
                        "Failed to auto-create asr.radius.user for partner %s: %s",
                        partner.name,
                        e
                    )

        return partners

    def write(self, vals):
        """Override write to sync bidirectionally with asr.radius.user"""
        # Skip if we're coming from radius_user.write()
        if self.env.context.get('_from_radius_write'):
            return super(ResPartner, self).write(vals)

        # Execute parent write
        res = super(ResPartner, self).write(vals)

        # ✅ Auto-add subscription product to active sale order
        if 'subscription_id' in vals and vals['subscription_id']:
            self._add_subscription_to_active_sale_order()

        # Sync to asr.radius.user (if linked)
        for partner in self.filtered(lambda p: p.radius_user_id):
            radius_vals = {}

            # Map Partner fields to RADIUS fields (only changed fields)
            if 'radius_username' in vals:
                radius_vals['username'] = vals['radius_username']
            if 'radius_password' in vals:
                radius_vals['radius_password'] = vals['radius_password']
            if 'subscription_id' in vals:
                radius_vals['subscription_id'] = vals['subscription_id']
            if 'device_id' in vals:
                radius_vals['device_id'] = vals['device_id']
            if 'name' in vals:
                radius_vals['name'] = vals['name']

            # CRM fields mapping
            if 'mobile' in vals or 'phone' in vals:
                # Prefer mobile, fallback to phone
                radius_vals['phone'] = vals.get('mobile') or vals.get('phone') or partner.mobile or partner.phone
            if 'phone_secondary' in vals:
                radius_vals['phone_secondary'] = vals['phone_secondary']
            if 'email' in vals:
                radius_vals['email'] = vals['email']
            if 'street' in vals:
                radius_vals['street'] = vals['street']
            if 'street2' in vals:
                radius_vals['street2'] = vals['street2']
            if 'city' in vals:
                radius_vals['city'] = vals['city']
            if 'zip' in vals:
                radius_vals['zip'] = vals['zip']
            if 'country_id' in vals:
                radius_vals['country_id'] = vals['country_id']
            if 'partner_latitude' in vals:
                radius_vals['partner_latitude'] = vals['partner_latitude']
            if 'partner_longitude' in vals:
                radius_vals['partner_longitude'] = vals['partner_longitude']
            if 'access_device_id' in vals:
                radius_vals['access_device_id'] = vals['access_device_id']
            if 'olt_login_port' in vals:
                radius_vals['olt_login_port'] = vals['olt_login_port']
            if 'contract_start_date' in vals:
                radius_vals['contract_start_date'] = vals['contract_start_date']
            if 'contract_end_date' in vals:
                radius_vals['contract_end_date'] = vals['contract_end_date']
            if 'billing_day' in vals:
                radius_vals['billing_day'] = vals['billing_day']
            if 'nipt' in vals:
                radius_vals['nipt'] = vals['nipt']
            if 'installation_date' in vals:
                radius_vals['installation_date'] = vals['installation_date']
            if 'installation_technician_id' in vals:
                radius_vals['installation_technician_id'] = vals['installation_technician_id']
            if 'internal_notes' in vals:
                radius_vals['internal_notes'] = vals['internal_notes']
            if 'customer_notes' in vals:
                radius_vals['customer_notes'] = vals['customer_notes']
            if 'description' in vals:
                radius_vals['description'] = vals.get('description', '')

            # Fiber fields – VETËM NGA radius_user -> partner, JO anasjelltas
            if 'fiber_closure_id' in vals:
                radius_vals['fiber_closure_id'] = vals['fiber_closure_id']
            if 'fiber_core_number' in vals:
                radius_vals['fiber_core_number'] = vals['fiber_core_number']
            if 'fiber_color' in vals:
                radius_vals['fiber_color'] = vals['fiber_color']
            # mos dërgo ont_serial / olt_pon_port / olt_ont_id mbrapsht – janë të menaxhuara në asr.radius.user

            if radius_vals:
                partner.radius_user_id.with_context(_from_partner_write=True).sudo().write(radius_vals)

        return res

    # ==================== COMPUTED METHODS ====================
    @api.depends('access_device_id')
    def _compute_infrastructure_ids(self):
        """Compute POP and City from Access Device (if crm_abissnet is installed)"""
        for rec in self:
            # Check if crm_abissnet models are available
            if rec.access_device_id and 'crm.access.device' in self.env:
                try:
                    rec.pop_id = rec.access_device_id.pop_id.id if hasattr(
                        rec.access_device_id, 'pop_id') and rec.access_device_id.pop_id else False
                    rec.city_id = rec.access_device_id.city_id.id if hasattr(
                        rec.access_device_id, 'city_id') and rec.access_device_id.city_id else False
                except Exception:
                    rec.pop_id = False
                    rec.city_id = False
            else:
                rec.pop_id = False
                rec.city_id = False

    @api.depends('subscription_id', 'company_id')
    def _compute_groupname(self):
        for rec in self:
            if not rec.is_radius_customer or not rec.subscription_id:
                rec.groupname = False
                continue

            comp = rec.company_id or self.env.company
            comp_prefix = _slug_company(getattr(comp, 'code', None) or comp.name)
            plan_code = _slug_plan(
                rec.subscription_id.code,
                rec.subscription_id.name
            ) if rec.subscription_id else "NOPLAN"
            rec.groupname = f"{comp_prefix}:{plan_code}"

    @api.depends('radius_username', 'company_id')
    def _compute_current_radius_group(self):
        for rec in self:
            cur_group = False
            if rec.radius_username:
                conn = None
                try:
                    conn = rec._get_radius_conn()
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT groupname FROM radusergroup WHERE username=%s ORDER BY priority ASC LIMIT 1",
                            (rec.radius_username,)
                        )
                        row = cur.fetchone()
                        if row:
                            cur_group = row.get('groupname') if isinstance(row, dict) else row[0]
                except Exception as e:
                    _logger.debug("Fetch current RADIUS group failed for %s: %s", rec.radius_username, e)
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass
            rec.current_radius_group = cur_group or False

    @api.depends('current_radius_group')
    def _compute_is_suspended(self):
        for rec in self:
            grp = (rec.current_radius_group or '').upper()
            rec.is_suspended = bool(re.search(r'(^|:)SUSPENDED$', grp))

    @api.depends('sla_level')
    def _compute_is_business(self):
        """SLA 2 and 3 are business customers"""
        for rec in self:
            rec.is_business = rec.sla_level in ('2', '3')

    def _compute_pppoe_status(self):
        """Read active session from asr.radius.session or radacct"""
        Sess = self.env['asr.radius.session'].sudo()

        for rec in self:
            rec.pppoe_status = 'down'
            rec.last_session_start = False
            rec.current_framed_ip = False
            rec.current_interface = False

            if not rec.radius_username:
                continue

            ip = None
            iface = None
            start = None

            # Try from asr.radius.session
            s = Sess.search(
                [('username', '=', rec.radius_username), ('acctstoptime', '=', False)],
                limit=1,
                order='acctstarttime desc'
            )
            if s:
                start = getattr(s, 'acctstarttime', None) or getattr(s, 'acct_start_time', None)

                # Try IP fields
                for attr in ('framedipaddress', 'framed_ip_address', 'framed_ip'):
                    v = getattr(s, attr, None)
                    if v:
                        ip = v
                        break

                # Try interface fields
                for attr in ('nasportid', 'nas_port_id', 'nasport', 'calledstationid', 'called_station_id'):
                    v = getattr(s, attr, None)
                    if v:
                        iface = v
                        break

            # Fallback: direct SQL from radacct
            if not (ip and iface and start):
                conn = None
                try:
                    conn = rec._get_radius_conn()
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT framedipaddress, nasportid, calledstationid, acctstarttime
                            FROM radacct
                            WHERE username = %s AND acctstoptime IS NULL
                            ORDER BY acctstarttime DESC LIMIT 1
                        """, (rec.radius_username,))
                        row = cur.fetchone()
                        if row:
                            if isinstance(row, dict):
                                ip = ip or row.get('framedipaddress')
                                iface = iface or row.get('nasportid') or row.get('calledstationid')
                                start = start or row.get('acctstarttime')
                            else:
                                ip = ip or row[0]
                                iface = iface or row[1] or row[2]
                                start = start or row[3]
                except Exception as e:
                    _logger.debug("Fallback radacct SQL failed for %s: %s", rec.radius_username, e)
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

            # Set values
            if start or ip or iface:
                rec.pppoe_status = 'up'
                rec.last_session_start = start or False
                rec.current_framed_ip = ip or False
                rec.current_interface = iface or False

    def _compute_session_counts(self):
        Sess = self.env['asr.radius.session'].sudo()
        for rec in self:
            if not rec.radius_username:
                rec.active_sessions_count = 0
                rec.total_sessions_count = 0
                continue
            rec.active_sessions_count = Sess.search_count(
                [('username', '=', rec.radius_username), ('acctstoptime', '=', False)])
            rec.total_sessions_count = Sess.search_count([('username', '=', rec.radius_username)])

    def _update_payment_statistics(self):
        """
        Update payment statistics from all paid invoices
        Called when invoice is paid to refresh payment totals
        """
        for rec in self:
            # Initialize defaults
            rec.total_paid_amount = 0.0
            rec.last_payment_date = False
            rec.last_payment_amount = 0.0
            rec.first_payment_date = False

            # Check if account module is installed
            if 'account.move' not in self.env:
                continue

            # Get all paid invoices for this customer
            invoices = self.env['account.move'].search([
                ('partner_id', '=', rec.id),
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['paid', 'in_payment'])
            ])

            if not invoices:
                continue

            # Sum all paid amounts
            rec.total_paid_amount = sum(invoices.mapped('amount_total'))

            # Sort by date to get first and last
            sorted_invoices = invoices.sorted(key=lambda inv: inv.invoice_date or inv.date or fields.Date.today())

            # First payment
            if sorted_invoices:
                first_inv = sorted_invoices[0]
                rec.first_payment_date = first_inv.invoice_date or first_inv.date

            # Last payment
            if sorted_invoices:
                latest_inv = sorted_invoices[-1]
                rec.last_payment_date = latest_inv.invoice_date or latest_inv.date
                rec.last_payment_amount = latest_inv.amount_total

            _logger.info(
                "Updated payment statistics for partner %s: total=%.2f, last_payment=%.2f on %s",
                rec.name,
                rec.total_paid_amount,
                rec.last_payment_amount,
                rec.last_payment_date
            )
    def _compute_payment_balance(self):
        """Compute payment balance from account receivable"""
        for rec in self:
            if 'account.move' in self.env:
                # Get unpaid balance (account receivable)
                rec.payment_balance = rec.credit - rec.debit
            else:
                rec.payment_balance = 0.0

    def _compute_sale_invoice_counts(self):
        """Compute counts of sale orders and invoices"""
        for rec in self:
            # Sale orders count
            if 'sale.order' in self.env:
                rec.sale_order_count = self.env['sale.order'].search_count([
                    ('partner_id', 'child_of', rec.id)
                ])
            else:
                rec.sale_order_count = 0

            # Invoices count
            if 'account.move' in self.env:
                rec.invoice_count = self.env['account.move'].search_count([
                    ('partner_id', 'child_of', rec.id),
                    ('move_type', 'in', ['out_invoice', 'out_refund'])
                ])
            else:
                rec.invoice_count = 0

    # ==================== CONSTRAINTS ====================
    @api.constrains('nipt', 'sla_level')
    def _check_nipt_required(self):
        """NIPT is required for business customers (SLA 2/3)"""
        for rec in self:
            if rec.sla_level in ('2', '3') and not rec.nipt:
                raise ValidationError(_('NIPT/VAT is required for Business customers (SLA 2/3)'))

    @api.constrains('billing_day')
    def _check_billing_day(self):
        """Billing day must be between 1 and 28"""
        for rec in self:
            if rec.billing_day and not (1 <= rec.billing_day <= 28):
                raise ValidationError(_('Billing day must be between 1 and 28'))

    # ==================== RADIUS CONNECTION HELPER ====================
    def _get_radius_conn(self):
        """Get RADIUS MySQL connection"""
        self.ensure_one()
        company = self.company_id or self.env.company

        # Try company._get_direct_conn() from ab_radius_connector
        if hasattr(company, "_get_direct_conn"):
            conn = company._get_direct_conn()
            if conn:
                return conn

        # Fallback to mysql.connector
        mc = self.env['mysql.connector'].sudo().search([('company_id', '=', company.id)], limit=1) or \
             self.env['mysql.connector'].sudo().search([], limit=1)
        if not mc:
            raise UserError(_("No MySQL connector found for RADIUS."))

        getter = getattr(mc, "get_connection", None) or getattr(mc, "_get_connection", None)
        if not getter:
            raise UserError(_("mysql.connector object has no get_connection() method."))
        return getter()

    # ==================== SQL UPSERT HELPERS ====================
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
        cursor.execute("DELETE FROM radusergroup WHERE username=%s", (username,))
        cursor.execute("""
            INSERT INTO radusergroup (username, groupname, priority)
            VALUES (%s, %s, 1)
        """, (username, groupname))

    # ==================== RADIUS ACTIONS ====================
    def action_sync_to_radius(self):
        """Sync user to FreeRADIUS MySQL database"""
        ok = 0
        last_error = None

        for rec in self:
            if not rec.radius_username:
                raise UserError(_("Missing RADIUS username."))
            if not rec.radius_password:
                raise UserError(_("Missing RADIUS password."))
            if not rec.subscription_id:
                raise UserError(_("Select a Subscription."))

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    self._upsert_radcheck(cur, rec.radius_username, rec.radius_password)
                    self._upsert_radusergroup(cur, rec.radius_username, rec.groupname)
                conn.commit()

                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })

                rec.message_post(
                    body=_("Synchronized user %(u)s → group %(g)s") % {
                        'u': rec.radius_username,
                        'g': rec.groupname
                    },
                    subtype_xmlid='mail.mt_note'
                )
                _logger.info("RADIUS sync OK: %s -> %s", rec.radius_username, rec.groupname)
                ok += 1

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                _logger.exception("RADIUS sync failed for %s", rec.radius_username)
                rec.message_post(
                    body=_("RADIUS sync FAILED for '%(u)s': %(err)s") % {
                        'u': rec.radius_username,
                        'err': last_error
                    },
                    subtype_xmlid='mail.mt_note'
                )
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Return notification
        if ok == len(self):
            msg = (_("User '%s' synced to RADIUS") % self.radius_username) if len(self) == 1 else (
                _("%d user(s) synced") % ok)
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
            failed = len(self) - ok
            msg = _('%d succeeded, %d failed') % (ok, failed)
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

    def action_suspend(self):
        """Suspend RADIUS user"""
        ok = 0
        last_error = None

        for rec in self:
            if not rec.radius_username:
                raise UserError(_("Missing RADIUS username."))

            comp = rec.company_id or self.env.company
            suspended = f"{_slug_company((getattr(comp, 'code', None) or comp.name))}:SUSPENDED"

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT IGNORE INTO radgroupreply (groupname, attribute, op, value)
                        VALUES (%s, 'Reply-Message', ':=', 'Suspended')
                    """, (suspended,))
                    self._upsert_radusergroup(cur, rec.radius_username, suspended)
                conn.commit()

                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now()
                })

                rec.message_post(
                    body=_("Suspended '%(u)s' → group %(g)s") % {'u': rec.radius_username, 'g': suspended},
                    subtype_xmlid='mail.mt_note'
                )
                ok += 1

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                rec.message_post(
                    body=_("Suspend FAILED for '%(u)s': %(err)s") % {'u': rec.radius_username, 'err': last_error},
                    subtype_xmlid='mail.mt_note'
                )
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Return notification
        if ok == len(self):
            msg = (_("User '%s' suspended") % self.radius_username) if len(self) == 1 else (
                _("%d user(s) suspended") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Suspension'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False
                }
            }
        else:
            failed = len(self) - ok
            msg = _('%d suspended, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Suspension (Partial/Failed)'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False
                }
            }

    def action_reactivate(self):
        """Reactivate suspended RADIUS user"""
        ok = 0
        last_error = None

        for rec in self:
            if not rec.radius_username or not rec.subscription_id:
                raise UserError(_("Missing username or subscription."))

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    self._upsert_radusergroup(cur, rec.radius_username, rec.groupname)
                conn.commit()

                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now()
                })

                rec.message_post(
                    body=_("Reactivated '%(u)s' → group %(g)s") % {'u': rec.radius_username, 'g': rec.groupname},
                    subtype_xmlid='mail.mt_note'
                )
                ok += 1

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                rec.sudo().write({'radius_synced': False, 'last_sync_error': last_error})
                rec.message_post(
                    body=_("Reactivate FAILED for '%(u)s': %(err)s") % {'u': rec.radius_username, 'err': last_error},
                    subtype_xmlid='mail.mt_note'
                )
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Return notification
        if ok == len(self):
            msg = (_("User '%s' reactivated") % self.radius_username) if len(self) == 1 else (
                _("%d user(s) reactivated") % ok)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Reactivation'),
                    'message': msg,
                    'type': 'success',
                    'sticky': False
                }
            }
        else:
            failed = len(self) - ok
            msg = _('%d reactivated, %d failed') % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Reactivation (Partial/Failed)'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False
                }
            }

    def action_remove_from_radius(self):
        """Remove user from RADIUS database"""
        ok = 0
        last_error = None

        for rec in self:
            if not rec.radius_username:
                raise UserError(_("Missing RADIUS username."))

            conn = None
            try:
                conn = rec._get_radius_conn()
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM radreply WHERE username=%s", (rec.radius_username,))
                    cur.execute("DELETE FROM radcheck WHERE username=%s", (rec.radius_username,))
                    cur.execute("DELETE FROM radusergroup WHERE username=%s", (rec.radius_username,))
                conn.commit()

                rec.sudo().write({
                    'radius_synced': False,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })

                rec.message_post(
                    body=_("Removed user '%(u)s' from RADIUS") % {'u': rec.radius_username},
                    subtype_xmlid='mail.mt_note'
                )
                ok += 1

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                rec.sudo().write({'last_sync_error': last_error})
                rec.message_post(
                    body=_("Remove from RADIUS FAILED for '%(u)s': %(err)s") % {
                        'u': rec.radius_username,
                        'err': last_error
                    },
                    subtype_xmlid='mail.mt_note'
                )
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Return notification
        if ok == len(self):
            msg = (_("User '%s' removed from RADIUS") % self.radius_username) if len(self) == 1 else (
                _("%d user(s) removed") % ok)
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
            failed = len(self) - ok
            msg = _('%d removed, %d failed') % (ok, failed)
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

    def action_disconnect_user(self):
        """
        Disconnect PPPoE session (delegates to asr.radius.user)
        Send RADIUS Disconnect-Request to terminate active session
        """
        self.ensure_one()

        if not self.radius_user_id:
            raise UserError(_("No RADIUS user linked to this contact."))

        # Delegate to asr.radius.user.action_disconnect_user()
        return self.radius_user_id.action_disconnect_user()

    def action_refresh_payment_stats(self):
        """
        Manually refresh payment statistics from invoices
        Useful for syncing historical data or troubleshooting
        """
        self._update_payment_statistics()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payment Statistics Refreshed'),
                'message': _('Payment information has been updated from invoices'),
                'type': 'success',
                'sticky': False
            }
        }

    # ==================== SESSION ACTIONS ====================
    def _sessions_action_base(self, domain):
        self.ensure_one()
        return {
            'name': _("RADIUS Sessions"),
            'type': 'ir.actions.act_window',
            'res_model': 'asr.radius.session',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    def action_view_active_sessions(self):
        """View active RADIUS sessions for this customer"""
        self.ensure_one()
        if not self.radius_username:
            raise UserError(_("This contact has no RADIUS username."))
        return self._sessions_action_base([
            ('username', '=', self.radius_username),
            ('acctstoptime', '=', False)
        ])

    def action_view_all_sessions(self):
        """View all RADIUS sessions for this customer"""
        self.ensure_one()
        if not self.radius_username:
            raise UserError(_("This contact has no RADIUS username."))
        return self._sessions_action_base([('username', '=', self.radius_username)])

    # ==================== AUTO-ADD SUBSCRIPTION TO SALE ORDER ====================
    def _add_subscription_to_active_sale_order(self):
        """
        Auto-add subscription product to active sale order when subscription changes.
        This is triggered from partner form when opened from sale order.
        """
        for partner in self:
            # Only process if partner has subscription
            if not partner.subscription_id:
                continue

            # Check if subscription has linked product
            subscription = partner.subscription_id
            if not subscription.product_tmpl_id:
                _logger.warning(
                    "Subscription %s has no linked product.template",
                    subscription.name
                )
                continue

            # Get product.product from product.template (first variant)
            product = subscription.product_tmpl_id.product_variant_ids[:1]
            if not product:
                _logger.warning(
                    "Product template %s has no variants",
                    subscription.product_tmpl_id.name
                )
                continue

            # Check context for active sale order
            sale_order_id = self.env.context.get('default_order_id') or self.env.context.get('active_order_id')
            if not sale_order_id:
                # No active sale order in context, check for recent draft orders
                recent_order = self.env['sale.order'].search([
                    ('partner_id', '=', partner.id),
                    ('state', 'in', ['draft', 'sent'])
                ], order='create_date desc', limit=1)

                if recent_order:
                    sale_order_id = recent_order.id

            if not sale_order_id:
                _logger.debug("No active sale order found for partner %s", partner.name)
                continue

            # Get sale order
            sale_order = self.env['sale.order'].browse(sale_order_id)
            if not sale_order.exists():
                continue

            # Check if order already has RADIUS products
            existing_radius_products = sale_order.order_line.filtered(
                lambda l: l.product_id.is_radius_service
            )
            if existing_radius_products:
                _logger.debug(
                    "Sale order %s already has RADIUS products, skipping auto-add",
                    sale_order.name
                )
                continue

            # Add subscription product to order lines
            self.env['sale.order.line'].sudo().create({
                'order_id': sale_order.id,
                'product_id': product.id,
                'name': product.name,
                'product_uom_qty': 1,
                'product_uom': product.uom_id.id,
                'price_unit': product.list_price,
            })

            _logger.info(
                "Auto-added subscription product %s to sale order %s for partner %s",
                product.name,
                sale_order.name,
                partner.name
            )

    # ==================== MAP ACTION ====================
    def action_open_map(self):
        """Open Google Maps with customer location"""
        self.ensure_one()
        if not (self.partner_latitude and self.partner_longitude):
            raise UserError(_('No coordinates set for this contact'))

        url = f"https://www.google.com/maps?q={self.partner_latitude},{self.partner_longitude}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    # ==================== FIBER MANAGEMENT ACTIONS ====================
    def action_open_closure(self):
        """Open fiber closure form"""
        self.ensure_one()
        if not self.fiber_closure_id:
            raise UserError(_('No fiber closure assigned'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fiber Closure'),
            'res_model': 'crm.fiber.closure',
            'res_id': self.fiber_closure_id.id,
            'view_mode': 'form',
            'target': 'current'
        }

    def action_release_fiber(self):
        """Release fiber core assignment"""
        self.ensure_one()
        if not self.fiber_closure_id or not self.fiber_core_number:
            raise UserError(_('No fiber core assigned'))

        self.fiber_closure_id.release_core(self.fiber_core_number)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Fiber Released'),
                'message': _('Core #%d has been released') % self.fiber_core_number,
                'type': 'success',
                'sticky': False
            }
        }

    # ==================== NAVIGATION ACTIONS ====================
    def action_view_radius_user(self):
        """Smart button: navigate to linked asr.radius.user record"""
        self.ensure_one()
        if not self.radius_user_id:
            raise UserError(_("No RADIUS user linked to this contact."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('RADIUS User: %s') % self.radius_username,
            'res_model': 'asr.radius.user',
            'res_id': self.radius_user_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_pppoe_status(self):
        """Smart button: open PPPoE Status view filtered by username"""
        self.ensure_one()
        if not self.radius_username:
            raise UserError(_("This customer has no RADIUS username."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('PPPoE Status: %s') % self.radius_username,
            'res_model': 'asr.radius.pppoe_status',
            'view_mode': 'list,form',
            'domain': [('username', '=', self.radius_username)],
            'context': {'search_default_username': self.radius_username},
            'target': 'current',
        }

    def action_view_sale_orders(self):
        """Smart button: view all sale orders for this customer"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', 'child_of', self.id)],
            'context': {
                'default_partner_id': self.id,
                'search_default_partner_id': self.id
            },
            'target': 'current',
        }

    def action_view_invoices(self):
        """Smart button: view all invoices for this customer"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', 'child_of', self.id),
                ('move_type', 'in', ['out_invoice', 'out_refund'])
            ],
            'context': {
                'default_partner_id': self.id,
                'default_move_type': 'out_invoice'
            },
            'target': 'current',
        }

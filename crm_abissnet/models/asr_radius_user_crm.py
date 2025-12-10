# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AsrRadiusUserCRM(models.Model):
    _inherit = 'asr.radius.user'

    # ==================== CRM Fields ====================

    # Contact Info
    phone = fields.Char(string="Phone Number", tracking=True)
    phone_secondary = fields.Char(string="Secondary Phone")
    email = fields.Char(string="Email", tracking=True)

    # Address (with geolocation)
    street = fields.Char(string="Street")
    street2 = fields.Char(string="Street 2")
    city = fields.Char(string="City")
    zip = fields.Char(string="ZIP")
    country_id = fields.Many2one('res.country', string="Country")

    # Geolocation
    partner_latitude = fields.Float(string="Latitude", digits=(10, 7))
    partner_longitude = fields.Float(string="Longitude", digits=(10, 7))

    # SLA (Service Level Agreement) - AUTO from Subscription
    sla_level = fields.Selection([
        ('1', 'SLA 1 - Individual'),
        ('2', 'SLA 2 - Small Business'),
        ('3', 'SLA 3 - Enterprise'),
    ], string="SLA Level", related='subscription_id.sla_level', store=True, readonly=True,
        help="Inherited from subscription package. 1=Residential, 2=Small Biz, 3=Large Corp")

    # Business Info (conditional)
    is_business = fields.Boolean(string="Is Business", compute='_compute_is_business', store=True)
    nipt = fields.Char(string="NIPT/VAT", tracking=True,
                       help="Business Tax ID (required for SLA 2/3)")
    company_name = fields.Char(string="Company Name", tracking=True)

    # Contract & Billing
    contract_start_date = fields.Date(string="Contract Start")
    contract_end_date = fields.Date(string="Contract End")
    billing_day = fields.Integer(string="Billing Day of Month", default=1,
                                 help="Day of month for invoice generation (1-28)")

    # Notes
    internal_notes = fields.Text(string="Internal Notes",
                                 help="Private notes (not visible to customer)")
    customer_notes = fields.Text(string="Customer Notes",
                                 help="Notes visible to customer (e.g., in portal)")

    # Installation
    installation_date = fields.Date(string="Installation Date")
    installation_technician_id = fields.Many2one('res.users', string="Installed By")

    # ==================== Infrastructure Link ====================
    access_device_id = fields.Many2one('crm.access.device', string="Access Device",
                                       tracking=True,
                                       help="Physical device (OLT/DSLAM) this customer is connected to")
    pop_id = fields.Many2one('crm.pop', string="POP",
                             related='access_device_id.pop_id', store=True, readonly=True)
    city_id = fields.Many2one('crm.city', string="City",
                              related='access_device_id.city_id', store=True, readonly=True)

    # NEW: Login Port i fundit i gjetur nga OLT (p.sh. '10.50.60.103 pon 1/2/2/27:1662')
    olt_login_port = fields.Char(string="Login Port (OLT)", tracking=True)

    # ==================== Computed Fields ====================

    @api.depends('sla_level')
    def _compute_is_business(self):
        """SLA 2 dhe 3 janë business"""
        for rec in self:
            rec.is_business = rec.sla_level in ('2', '3')

    # ==================== Constraints ====================

    @api.constrains('nipt', 'subscription_id')
    def _check_nipt_required(self):
        """NIPT është i detyrueshëm për biznes (SLA 2/3)"""
        for rec in self:
            # Get SLA directly from subscription to avoid race condition with related field
            sla = rec.subscription_id.sla_level if rec.subscription_id else None
            nipt = (rec.nipt or '').strip()

            # Debug logging
            _logger.warning(f"RADIUS USER CONSTRAINT - User: {rec.username or rec.id}, "
                          f"Subscription: {rec.subscription_id.name if rec.subscription_id else 'None'}, "
                          f"SLA: {sla}, NIPT: '{nipt}'")

            if sla in ('2', '3') and not nipt:
                _logger.error(f"RADIUS USER VALIDATION FAILED - User: {rec.username}, SLA: {sla}, NIPT: '{rec.nipt}'")
                raise ValidationError(_('NIPT is required for Business customers (SLA 2/3)'))

    @api.constrains('billing_day')
    def _check_billing_day(self):
        """Billing day duhet 1-28 (mos prek shkurt)"""
        for rec in self:
            if rec.billing_day and not (1 <= rec.billing_day <= 28):
                raise ValidationError(_('Billing day must be between 1 and 28'))

    # ==================== Helper Methods ====================

    def action_open_map(self):
        """Open Google Maps with customer location"""
        self.ensure_one()
        if not (self.partner_latitude and self.partner_longitude):
            raise UserError(_('No coordinates set for this customer'))

        url = f"https://www.google.com/maps?q={self.partner_latitude},{self.partner_longitude}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def _get_full_address(self):
        """Return formatted address string"""
        self.ensure_one()
        parts = [
            self.street or '',
            self.street2 or '',
            self.city or '',
            self.zip or '',
            self.country_id.name or '',
        ]
        return ', '.join([p for p in parts if p])

    def write(self, vals):
        """Override write to sync CRM fields bidirectionally with res.partner"""
        # Skip if we're coming from partner.write()
        if self.env.context.get('_from_partner_write'):
            return super(AsrRadiusUserCRM, self).write(vals)

        res = super(AsrRadiusUserCRM, self).write(vals)

        # Sync CRM fields to res.partner (if linked)
        for rec in self.filtered(lambda r: r.partner_id):
            partner_vals = {}

            # Map CRM fields (only changed fields)
            if 'phone' in vals:
                partner_vals['mobile'] = vals['phone']  # radius.phone → partner.mobile
            if 'phone_secondary' in vals:
                partner_vals['phone_secondary'] = vals['phone_secondary']
            if 'email' in vals:
                partner_vals['email'] = vals['email']
            if 'street' in vals:
                partner_vals['street'] = vals['street']
            if 'street2' in vals:
                partner_vals['street2'] = vals['street2']
            if 'city' in vals:
                partner_vals['city'] = vals['city']
            if 'zip' in vals:
                partner_vals['zip'] = vals['zip']
            if 'country_id' in vals:
                partner_vals['country_id'] = vals['country_id']
            if 'partner_latitude' in vals:
                partner_vals['partner_latitude'] = vals['partner_latitude']
            if 'partner_longitude' in vals:
                partner_vals['partner_longitude'] = vals['partner_longitude']
            if 'access_device_id' in vals:
                partner_vals['access_device_id'] = vals['access_device_id']
            if 'olt_login_port' in vals:
                partner_vals['olt_login_port'] = vals['olt_login_port']
            if 'contract_start_date' in vals:
                partner_vals['contract_start_date'] = vals['contract_start_date']
            if 'contract_end_date' in vals:
                partner_vals['contract_end_date'] = vals['contract_end_date']
            if 'billing_day' in vals:
                partner_vals['billing_day'] = vals['billing_day']
            if 'nipt' in vals:
                partner_vals['nipt'] = vals['nipt']
            if 'installation_date' in vals:
                partner_vals['installation_date'] = vals['installation_date']
            if 'installation_technician_id' in vals:
                partner_vals['installation_technician_id'] = vals['installation_technician_id']
            if 'internal_notes' in vals:
                partner_vals['internal_notes'] = vals['internal_notes']
            if 'customer_notes' in vals:
                partner_vals['customer_notes'] = vals['customer_notes']

            # Sync with sudo() to avoid permission issues
            if partner_vals:
                rec.partner_id.with_context(_from_radius_write=True).sudo().write(partner_vals)

        return res
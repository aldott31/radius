# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


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

    # SLA (Service Level Agreement)
    sla_level = fields.Selection([
        ('1', 'SLA 1 - Individual'),
        ('2', 'SLA 2 - Small Business'),
        ('3', 'SLA 3 - Enterprise'),
    ], string="SLA Level", default='1', required=True, tracking=True,
        help="1=Residential, 2=Small Biz, 3=Large Corp")

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

    @api.constrains('nipt', 'sla_level')
    def _check_nipt_required(self):
        """NIPT është i detyrueshëm për biznes (SLA 2/3)"""
        for rec in self:
            if rec.sla_level in ('2', '3') and not rec.nipt:
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
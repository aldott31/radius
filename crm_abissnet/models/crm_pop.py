# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CrmPop(models.Model):
    _name = 'crm.pop'
    _description = 'Point of Presence (POP)'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="POP Name", required=True, tracking=True,
                       help="e.g., 'Tirana Center POP', 'Durres Beach POP'")
    code = fields.Char(string="POP Code", help="Short identifier (e.g., TIR-01)")

    # Hierarchy
    city_id = fields.Many2one('crm.city', string="City", required=True,
                              ondelete='restrict', tracking=True)

    # Location
    address = fields.Text(string="Physical Address")
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))

    # Relations
    device_ids = fields.One2many('crm.access.device', 'pop_id', string="Access Devices")
    device_count = fields.Integer(string="Devices", compute='_compute_counts', store=False)
    customer_count = fields.Integer(string="Customers", compute='_compute_counts', store=False)

    # Technical
    pop_type = fields.Selection([
        ('fiber', 'Fiber POP'),
        ('wireless', 'Wireless POP'),
        ('hybrid', 'Hybrid'),
    ], string="Type", default='fiber')

    capacity = fields.Integer(string="Max Customers",
                              help="Maximum customer capacity for this POP")

    # Status
    active = fields.Boolean(default=True, tracking=True)
    operational_status = fields.Selection([
        ('planned', 'Planned'),
        ('construction', 'Under Construction'),
        ('active', 'Active'),
        ('maintenance', 'Maintenance'),
        ('inactive', 'Inactive'),
    ], string="Status", default='planned', tracking=True)

    # Admin
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    notes = fields.Text(string="Notes")

    _sql_constraints = [
        ('name_city_unique', 'UNIQUE(name, city_id)',
         'POP name must be unique within the city!')
    ]

    @api.depends('device_ids')
    def _compute_counts(self):
        """✅ FIX: Recompute fresh"""
        for rec in self:
            rec.device_count = len(rec.device_ids)
            # Count customers across all devices
            rec.customer_count = self.env['asr.radius.user'].search_count([
                ('access_device_id', 'in', rec.device_ids.ids)
            ])

    def action_view_devices(self):
        """Smart button: view devices in this POP"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Devices in %s') % self.name,
            'res_model': 'crm.access.device',
            'view_mode': 'list,form',
            'domain': [('pop_id', '=', self.id)],
            'context': {'default_pop_id': self.id},
        }

    def action_open_map(self):
        """Open POP location on Google Maps"""
        self.ensure_one()
        if not (self.latitude and self.longitude):
            raise ValidationError(_('No coordinates set for this POP'))

        url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }
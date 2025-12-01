# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CrmCity(models.Model):
    _name = 'crm.city'
    _description = 'City / Municipality'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="City Name", required=True, tracking=True)
    code = fields.Char(string="City Code", help="Short code (e.g., TIR, DUR, VLO)")

    # Geographic info
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))

    # Relations
    pop_ids = fields.One2many('crm.pop', 'city_id', string="POPs")
    pop_count = fields.Integer(string="POPs", compute='_compute_counts', store=False)
    device_count = fields.Integer(string="Devices", compute='_compute_counts', store=False)
    customer_count = fields.Integer(string="Customers", compute='_compute_counts', store=False)

    # Admin
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    notes = fields.Text(string="Notes")

    _sql_constraints = [
        ('name_company_unique', 'UNIQUE(name, company_id)',
         'City name must be unique per company!')
    ]

    @api.depends('pop_ids')
    def _compute_counts(self):
        """✅ FIX: Fresh counts"""
        for rec in self:
            rec.pop_count = len(rec.pop_ids)

            # Count devices across POPs
            device_ids = self.env['crm.access.device'].search([
                ('pop_id', 'in', rec.pop_ids.ids)
            ])
            rec.device_count = len(device_ids)

            # Count customers across devices
            rec.customer_count = self.env['asr.radius.user'].search_count([
                ('access_device_id', 'in', device_ids.ids)
            ])

    def action_view_pops(self):
        """Smart button: view POPs in this city"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('POPs in %s') % self.name,
            'res_model': 'crm.pop',
            'view_mode': 'list,form',
            'domain': [('city_id', '=', self.id)],
            'context': {'default_city_id': self.id},
        }

    def action_view_devices(self):
        """Smart button: view devices in this city"""
        self.ensure_one()
        device_ids = self.env['crm.access.device'].search([
            ('pop_id', 'in', self.pop_ids.ids)
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Devices in %s') % self.name,
            'res_model': 'crm.access.device',
            'view_mode': 'list,form',
            'domain': [('id', 'in', device_ids.ids)],
            'context': {'search_default_city_id': self.id},
        }

    def action_view_customers(self):
        """Smart button: view customers in this city"""
        self.ensure_one()
        device_ids = self.env['crm.access.device'].search([
            ('pop_id', 'in', self.pop_ids.ids)
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customers in %s') % self.name,
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('access_device_id', 'in', device_ids.ids)],
            'context': {'search_default_radius_customers': 1},
        }

    def action_open_map(self):
        """Open city on Google Maps"""
        self.ensure_one()
        if not (self.latitude and self.longitude):
            raise ValidationError(_('No coordinates set for this city'))

        url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }
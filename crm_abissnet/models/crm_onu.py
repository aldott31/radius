# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class CrmOnu(models.Model):
    _name = 'crm.onu'
    _description = 'Customer Premises Equipment (ONU/ONT)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, serial_number'

    # Bazë
    name = fields.Char(string="Emri", required=True, tracking=True,
                       help="Emri/etiketa e CPE p.sh. ONT-Huawei-1")
    serial_number = fields.Char(string="Serial Number", required=True, index=True, tracking=True,
                                help="SN i pajisjes (GPON/EPON)")

    # Spec
    ethernet_ports = fields.Integer(string="Nr. Ethernet Portave", required=True, default=1, tracking=True)
    profile = fields.Char(string="Profile", tracking=True,
                          help="Emri i profilit (konfigurim/llogari profili)")
    function_mode = fields.Selection([
        ('bridge', 'Bridge'),
        ('router', 'Router'),
    ], string="Function Mode", required=True, default='bridge', tracking=True)

    # Admin
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    notes = fields.Text(string="Shënime")

    _sql_constraints = [
        ('onu_serial_company_uniq', 'unique(serial_number,company_id)',
         'Serial Number duhet të jetë unik për kompani!'),
    ]

    @api.constrains('ethernet_ports')
    def _check_ethernet_ports(self):
        for rec in self:
            if rec.ethernet_ports < 1 or rec.ethernet_ports > 16:
                raise ValidationError(_("Nr. i porteve Ethernet duhet të jetë 1–16."))

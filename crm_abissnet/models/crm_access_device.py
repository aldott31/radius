# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CrmAccessDevice(models.Model):
    _name = 'crm.access.device'
    _description = 'Access Device (DSLAM, OLT, Switch, etc.)'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Device Name", required=True, tracking=True)
    code = fields.Char(string="Serial/Code", help="Device serial number or identifier")

    # Hierarchy
    pop_id = fields.Many2one('crm.pop', string="POP", required=True,
                             ondelete='restrict', tracking=True)
    city_id = fields.Many2one('crm.city', string="City",
                              related='pop_id.city_id', store=True, readonly=True)

    # Device Type
    device_type = fields.Selection([
        ('olt', 'OLT (Optical Line Terminal)'),
        ('dslam', 'DSLAM'),
        ('switch', 'Ethernet Switch'),
        ('router', 'Router'),
        ('wireless_ap', 'Wireless Access Point'),
        ('other', 'Other'),
    ], string="Device Type", required=True, default='olt', tracking=True)

    # Technical specs
    manufacturer = fields.Char(string="Manufacturer", help="e.g., Huawei, ZTE, Cisco")
    model = fields.Char(string="Model")
    ip_address = fields.Char(string="Management IP")
    mac_address = fields.Char(string="MAC Address")

    # Capacity
    port_count = fields.Integer(string="Total Ports")
    ports_used = fields.Integer(string="Ports Used", compute='_compute_port_usage', store=False)
    ports_available = fields.Integer(string="Ports Available", compute='_compute_port_usage', store=False)
    capacity_percentage = fields.Float(string="Capacity %", compute='_compute_port_usage', store=False)

    # Relations - ✅ FIX: Use compute instead of One2many
    customer_count = fields.Integer(string="Customers", compute='_compute_customer_count', store=False)

    # Link to NAS (technical)
    nas_device_id = fields.Many2one('asr.device', string="RADIUS NAS Device",
                                    help="Link to technical RADIUS NAS configuration")

    # Status
    active = fields.Boolean(default=True, tracking=True)
    operational_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('maintenance', 'Maintenance'),
        ('faulty', 'Faulty'),
    ], string="Status", default='online', tracking=True)

    # Admin
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    installation_date = fields.Date(string="Installation Date")
    notes = fields.Text(string="Notes")

    def _compute_customer_count(self):
        """✅ FIX: Count via search instead of One2many"""
        for rec in self:
            rec.customer_count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])

    def _compute_port_usage(self):
        """✅ FIX: Recalculate customer_count first"""
        for rec in self:
            # Get fresh count
            count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])
            rec.ports_used = count
            rec.ports_available = max(0, (rec.port_count or 0) - count)
            if rec.port_count:
                rec.capacity_percentage = (count / rec.port_count) * 100
            else:
                rec.capacity_percentage = 0

    def action_view_customers(self):
        """Smart button: view customers on this device"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customers on %s') % self.name,
            'res_model': 'asr.radius.user',
            'view_mode': 'list,form',
            'domain': [('access_device_id', '=', self.id)],
            'context': {'default_access_device_id': self.id},
        }

    @api.constrains('port_count')
    def _check_port_capacity(self):
        """✅ FIX: Warning vetëm kur ruhet (jo compute)"""
        for rec in self:
            if not rec.port_count:
                continue
            count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])
            if count > rec.port_count:
                raise ValidationError(
                    _('Device %s has exceeded port capacity! Used: %d, Total: %d')
                    % (rec.name, count, rec.port_count)
                )

    # --- Default VLANs on the OLT (allow CSV) ---
    internet_vlan = fields.Char(string="Internet VLAN(s)", tracking=True,
                                help="CSV p.sh. 1604,1614,1606")
    tv_vlan = fields.Char(string="TV VLAN(s)", tracking=True,
                          help="CSV ose një vlerë p.sh. 2020")
    voice_vlan = fields.Char(string="Voice VLAN(s)", tracking=True,
                             help="CSV ose një vlerë p.sh. 444")

    @api.constrains('internet_vlan', 'tv_vlan', 'voice_vlan')
    def _check_vlans_csv(self):
        import re
        for rec in self:
            for fname, label in [('internet_vlan', 'Internet VLAN(s)'),
                                 ('tv_vlan', 'TV VLAN(s)'),
                                 ('voice_vlan', 'Voice VLAN(s)')]:
                raw = (getattr(rec, fname) or '').strip()
                if not raw:
                    continue
                tokens = [t for t in re.split(r'[,\s;]+', raw) if t]
                for t in tokens:
                    if not t.isdigit():
                        raise ValidationError(_("%s: '%s' nuk është numër.") % (label, t))
                    n = int(t)
                    if n < 1 or n > 4094:
                        raise ValidationError(_("%s: VLAN %s jashtë intervalit 1–4094.") % (label, n))

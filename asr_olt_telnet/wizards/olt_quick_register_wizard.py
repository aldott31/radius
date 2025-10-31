# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

_ONU_CHOICES = [
    ('epon_412',  'EPON-ZTE-F412 ( ZTE-F412 )'),  # 2 porte
    ('epon_460',  'EPON-ZTE-F460 ( ZTE-F460 )'),  # 4 porte
    ('gpon_612',  'GPON-ZTE-F612 ( ZTE-F612 )'),  # 2 porte
    ('gpon_660',  'GPON-ZTE-F660 ( ZTE-F660 )'),  # 4 porte
    ('gpon_6600', 'ZTE-F6600 ( ZTE-F6600 )'),     # 4 porte
]

_ONU_LABEL_MAP = dict(_ONU_CHOICES)

class OltOnuRegisterQuick(models.TransientModel):
    _name = 'olt.onu.register.quick'
    _description = 'Quick Register ONU (from scan)'

    # Konteksti bazë
    customer_id = fields.Many2one('asr.radius.user', string="Customer", required=True)
    access_device_id = fields.Many2one('crm.access.device', string="OLT", required=True)
    interface = fields.Char(string="Interface", required=True, readonly=True)
    serial = fields.Char(string="Serial", required=True, readonly=True)
    name = fields.Char(string="Name/Description")

    # Tipi & moda
    onu_type = fields.Selection(_ONU_CHOICES, string="Onu Type", required=True)
    function_mode = fields.Selection([('bridge','Bridge'),('router','Router')],
                                     string="Function Mode", required=True, default='bridge')

    # Shërbimet
    svc_internet = fields.Boolean(string="Internet", default=True)
    internet_vlan = fields.Char(string="Internet VLAN")
    profile = fields.Char(string="Speed Profile (text)")
    lan_selection = fields.Selection([('lan1','LAN1'),('lan2','LAN2'),('lan3','LAN3'),('lan4','LAN4')], string="Select LAN")
    dhcp_option82 = fields.Selection([('enable','Enable'),('disable','Disable')], default='disable')

    svc_tv = fields.Boolean(string="TV")
    tv_vlan = fields.Char(string="TV VLAN")

    svc_voice = fields.Boolean(string="Telefoni")
    voice_vlan = fields.Char(string="Voice VLAN")

    svc_data = fields.Boolean(string="Data")
    data_vlan = fields.Char(string="Data VLAN")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context or {}
        if ctx.get('default_customer_id'):
            vals['customer_id'] = ctx['default_customer_id']
        if ctx.get('default_access_device_id'):
            vals['access_device_id'] = ctx['default_access_device_id']
        if ctx.get('default_interface'):
            vals['interface'] = ctx['default_interface']
        if ctx.get('default_serial'):
            vals['serial'] = ctx['default_serial']
        if ctx.get('default_name'):
            vals['name'] = ctx['default_name']
        # Prefill technology-guess për onu_type (nëse vjen nga rreshti)
        tech = ctx.get('default_technology') or 'gpon'
        vals.setdefault('onu_type', 'gpon_612' if tech == 'gpon' else 'epon_412')
        return vals

    @api.onchange('access_device_id')
    def _onchange_access_device_id(self):
        if self.access_device_id:
            self.internet_vlan = self.access_device_id.internet_vlan or ''
            self.tv_vlan = self.access_device_id.tv_vlan or ''
            self.voice_vlan = self.access_device_id.voice_vlan or ''

    def action_register(self):
        self.ensure_one()
        # map selection → tekst modeli
        onu_label = _ONU_LABEL_MAP.get(self.onu_type) or self.onu_type

        vals = {
            'customer_id': self.customer_id.id,
            'access_device_id': self.access_device_id.id,
            'interface': self.interface,
            'serial': self.serial,
            'name': self.name,
            'onu_type_id': False,                 # nuk e përdorim Many2one këtu
            'function_mode': self.function_mode,
            'svc_internet': self.svc_internet,
            'vlan_internet': self.internet_vlan or '',
            'profile_id': False,
            'lan_selection': self.lan_selection,
            'dhcp_option82': self.dhcp_option82,

            'svc_tv': self.svc_tv,
            'vlan_tv': self.tv_vlan or '',
            'svc_voice': self.svc_voice,
            'vlan_voice': self.voice_vlan or '',
            'svc_data': self.svc_data,
            'vlan_data': self.data_vlan or '',
        }

        # prefero API-n convenience nëse ekziston
        Provision = self.env['crm.onu.provision'].sudo()
        if hasattr(Provision, 'create_from_wizard'):
            vals_for_queue = dict(vals)
            # ruaj emrin e modelit si 'onu_model' në queue (përdoret nga worker-i)
            vals_for_queue['onu_model'] = onu_label
            Provision.create_from_wizard(vals_for_queue)
        else:
            vals_direct = dict(vals)
            vals_direct['onu_model'] = onu_label
            Provision.create(vals_direct)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('ONU queued'),
                       'message': _('Registration queued for %s') % (self.serial,),
                       'type': 'success', 'sticky': False}
        }

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

# ---------------------------------------------------------
#  Queue: kërkesa për regjistrim ONU (UI -> pending task)
# ---------------------------------------------------------
class CrmOnuProvision(models.Model):
    _name = 'crm.onu.provision'
    _description = 'Register ONU Queue (Pending Provisioning)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # Konteksti kryesor
    customer_id = fields.Many2one('asr.radius.user', string="Customer", required=True, index=True)
    access_device_id = fields.Many2one('crm.access.device', string="OLT/Device", required=True, index=True)
    interface = fields.Char(string="Interface/Port", required=True, help="p.sh. gpon_olt-1/8/9 ose GPON 0/1/0")
    serial = fields.Char(string="ONU Serial", required=True, index=True)
    name = fields.Char(string="Name/Description")

    # Tipi & moda
    onu_model = fields.Char(string="ONU Type/Model", required=True, help="p.sh. ZTE F660, Huawei HG8346R")
    function_mode = fields.Selection(
        [('bridge', 'Bridge'), ('router', 'Router')],
        string="Function Mode", required=True, default='bridge'
    )

    # Shërbimet + VLAN (CSV si tekst, merren nga OLT)
    svc_internet = fields.Boolean(string="Internet", default=True)
    vlan_internet = fields.Char(string="Internet VLAN(s)")  # CSV p.sh. 1604,1614,1606
    profile = fields.Char(string="Speed/Profile (text)")    # p.sh. 500/50
    lan_selection = fields.Selection(
        [('lan1','LAN1'), ('lan2','LAN2'), ('lan3','LAN3'), ('lan4','LAN4')],
        string="Select LAN"
    )
    dhcp_option82 = fields.Selection([('enable','Enable'), ('disable','Disable')], default='disable')

    svc_tv = fields.Boolean(string="TV")
    vlan_tv = fields.Char(string="TV VLAN(s)")

    svc_voice = fields.Boolean(string="Voice")
    vlan_voice = fields.Char(string="Voice VLAN(s)")

    # Gjendja
    state = fields.Selection(
        [('pending', 'Pending (awaiting script)'), ('done', 'Provisioned'), ('failed', 'Failed')],
        default='pending', tracking=True, index=True
    )
    error_message = fields.Text(string="Error (if any)")

    @api.model
    def create_from_wizard(self, vals):
        rec = self.create(vals)
        # Gjurmë te kartela e klientit (s’bën provisioning këtu)
        cust = rec.customer_id
        if cust:
            cust.write({'ont_serial': rec.serial, 'olt_pon_port': rec.interface})
            cust.message_post(body=_(
                "Queued ONU registration: %(sn)s on %(iface)s (%(olt)s) – Mode: %(mode)s"
            ) % {
                'sn': rec.serial,
                'iface': rec.interface,
                'olt': rec.access_device_id.display_name,
                'mode': rec.function_mode.upper()
            })
        return rec


# ---------------------------------------------------------
#  Wizard: UI për “Register ONU” (pa telnet – vetëm queue)
# ---------------------------------------------------------
class CrmOnuRegisterWizard(models.TransientModel):
    _name = 'crm.onu.register.wizard'
    _description = 'Register ONU (UI only – pending provisioning)'

    # Konteksti nga forma e klientit (merret në default_get)
    customer_id = fields.Many2one('asr.radius.user', string="Customer", required=True)
    access_device_id = fields.Many2one('crm.access.device', string="OLT/Device", required=True)
    interface = fields.Char(string="Interface/Port", required=True, help="p.sh. gpon_olt-1/8/9")
    serial = fields.Char(string="Serial", required=True)
    name = fields.Char(string="Name/Description")

    # Tipi & moda
    onu_model = fields.Char(string="ONU Type/Model", required=True, help="p.sh. ZTE F660, Huawei HG8346R")
    function_mode = fields.Selection(
        [('bridge','Bridge'), ('router','Router')],
        string="Function Mode", required=True, default='bridge'
    )

    # Shërbimet (VLAN si CSV)
    svc_internet = fields.Boolean(string="Internet", default=True)
    vlan_internet = fields.Char(string="Internet VLAN(s)")
    profile = fields.Char(string="Speed/Profile (text)")
    lan_selection = fields.Selection(
        [('lan1','LAN1'), ('lan2','LAN2'), ('lan3','LAN3'), ('lan4','LAN4')],
        string="Select LAN"
    )
    dhcp_option82 = fields.Selection([('enable','Enable'), ('disable','Disable')], default='disable')

    svc_tv = fields.Boolean(string="TV")
    vlan_tv = fields.Char(string="TV VLAN(s)")

    svc_voice = fields.Boolean(string="Telefoni")
    vlan_voice = fields.Char(string="Voice VLAN(s)")

    # Prefill VLAN-et nga OLT (Access Device)
    @api.onchange('access_device_id')
    def _onchange_access_device_id(self):
        if self.access_device_id:
            self.vlan_internet = self.access_device_id.internet_vlan or False
            self.vlan_tv       = self.access_device_id.tv_vlan or False
            self.vlan_voice    = self.access_device_id.voice_vlan or False

    @api.model
    def default_get(self, fields_list):
        """Vendos customer_id nga active_id (pa e kaluar nga view)"""
        vals = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if active_model == 'asr.radius.user' and active_id and 'customer_id' in fields_list:
            vals.setdefault('customer_id', active_id)
        return vals

    def action_register(self):
        self.ensure_one()
        vals = {
            'customer_id': self.customer_id.id,
            'access_device_id': self.access_device_id.id,
            'interface': self.interface,
            'serial': self.serial,
            'name': self.name,
            'onu_model': self.onu_model,
            'function_mode': self.function_mode,
            'svc_internet': self.svc_internet,
            'vlan_internet': self.vlan_internet,
            'profile': self.profile,
            'lan_selection': self.lan_selection,
            'dhcp_option82': self.dhcp_option82,
            'svc_tv': self.svc_tv,
            'vlan_tv': self.vlan_tv,
            'svc_voice': self.svc_voice,
            'vlan_voice': self.vlan_voice,
        }
        self.env['crm.onu.provision'].create_from_wizard(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ONU queued'),
                'message': _('Registration queued for %s') % (self.serial,),
                'type': 'success',
                'sticky': False
            }
        }

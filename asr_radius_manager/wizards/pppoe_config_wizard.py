# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AsrPppoeConfigWizard(models.TransientModel):
    _name = 'asr.pppoe.config.wizard'
    _description = 'Generate PPPoE NAS Config'

    device_id = fields.Many2one('asr.device', required=True, ondelete='cascade')
    output_mikrotik = fields.Text(readonly=True)
    output_cisco = fields.Text(readonly=True)

    def _get_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        host = ICP.get_param('asr_radius.freeradius_host') or '<FREERADIUS_IP>'
        auth = int(ICP.get_param('asr_radius.freeradius_auth_port', '1812'))
        acct = int(ICP.get_param('asr_radius.freeradius_acct_port', '1813'))
        interim = int(ICP.get_param('asr_radius.ppp_interim', '300'))
        one = ICP.get_param('asr_radius.one_session_per_host', '1') in ('1','true','True')
        idle = int(ICP.get_param('asr_radius.ppp_idle_timeout', '600'))  # për referencë në komente
        return host, auth, acct, interim, one, idle

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        device = self.env['asr.device'].browse(self.env.context.get('active_id'))
        if device:
            res['device_id'] = device.id
            host, auth, acct, interim, one, idle = self._get_params()

            mk = [
                f"/radius add service=ppp address={host} secret={device.secret} authentication-port={auth} accounting-port={acct}",
                f"/radius set [find address={host}] timeout=300ms",
                f"/ppp aaa set use-radius=yes interim-update={interim}s accounting=yes",
                f"# PPPoE server example (bind to interface/VLAN as needed)",
                f"/interface pppoe-server server add service-name=abissnet interface=<BRIDGE_OR_VLAN> default-profile=default one-session-per-host={'yes' if one else 'no'}"
            ]

            cisco = [
                "aaa new-model",
                "radius server FREERAD",
                f" address ipv4 {host} auth-port {auth} acct-port {acct}",
                f" key {device.secret}",
                "aaa authentication ppp default group radius local",
                "aaa authorization network default group radius",
                "aaa accounting network default start-stop group radius",
                "interface Virtual-Template1",
                " ip unnumbered <LOOPBACK>",
                " peer default ip address pool PPP_POOL",
                " ppp authentication pap callin",
                " ppp pap sent-username use-client"
            ]

            res['output_mikrotik'] = "\n".join(mk)
            res['output_cisco'] = "\n".join(cisco)
        return res

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
        idle = int(ICP.get_param('asr_radius.ppp_idle_timeout', '600'))
        return host, auth, acct, interim, one, idle

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        device = self.env['asr.device'].browse(self.env.context.get('active_id'))
        if device:
            res['device_id'] = device.id
            host, auth, acct, interim, one, idle = self._get_params()

            # MikroTik config
            mk = [
                "# ============================================",
                "# MikroTik RouterOS PPPoE + RADIUS Config",
                "# ============================================",
                "",
                "# 1. Add RADIUS server",
                f"/radius add service=ppp address={host} secret={device.secret} \\",
                f"  authentication-port={auth} accounting-port={acct}",
                "",
                "# 2. Set timeout",
                f"/radius set [find address={host}] timeout=300ms",
                "",
                "# 3. Enable RADIUS for PPP",
                f"/ppp aaa set use-radius=yes interim-update={interim}s accounting=yes",
                "",
                "# 4. Create PPPoE Server (adjust interface as needed)",
                f"/interface pppoe-server server add \\",
                f"  service-name=YOUR_ISP \\",
                f"  interface=<BRIDGE_OR_VLAN> \\",
                f"  default-profile=default \\",
                f"  one-session-per-host={'yes' if one else 'no'}",
                "",
                "# 5. Verify",
                "/radius print",
                "/ppp aaa print",
            ]

            # Cisco config with UPDATED format notes
            cisco = [
                "! ============================================",
                "! Cisco ASR9k/IOS-XE PPPoE + RADIUS Config",
                "! ============================================",
                "!",
                "! 1. AAA Configuration",
                "aaa new-model",
                "!",
                "! 2. RADIUS Server",
                "radius server FREERAD",
                f" address ipv4 {host} auth-port {auth} acct-port {acct}",
                f" key {device.secret}",
                "!",
                "! 3. AAA Methods",
                "aaa authentication ppp default group radius local",
                "aaa authorization network default group radius",
                "aaa accounting network default start-stop group radius",
                "!",
                "! 4. Virtual-Template for PPPoE",
                "interface Virtual-Template1",
                " ip unnumbered Loopback0",
                " peer default ip address pool PPP_POOL",
                " ppp authentication pap callin",
                " ppp authorization default",
                " ppp accounting default",
                "!",
                "! ============================================",
                "! RADIUS Reply Attributes (from Subscriptions)",
                "! ============================================",
                "! Format: Cisco-AVPair := ip:interface-config=service-policy input/output [SPEED]M",
                "!",
                "! Example for 49M/49M plan:",
                "!   Cisco-AVPair := ip:interface-config=service-policy input 49M",
                "!   Cisco-AVPair := ip:interface-config=service-policy output 49M",
                "!",
                "! These are applied per-session by RADIUS server.",
                "! Ensure service policies (49M, 300M, etc.) are pre-defined:",
                "!",
                "! policy-map 49M",
                "!  class class-default",
                "!   police rate 49 mbps",
                "!",
                "! policy-map 300M",
                "!  class class-default",
                "!   police rate 300 mbps",
                "!",
                "! ============================================",
            ]

            res['output_mikrotik'] = "\n".join(mk)
            res['output_cisco'] = "\n".join(cisco)
        return res
# -*- coding: utf-8 -*-
import time
import telnetlib
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_ONU_CHOICES = [
    ('ZTE-F412',  'EPON-ZTE-F412 ( ZTE-F412 )'),
    ('ZTE-F460',  'EPON-ZTE-F460 ( ZTE-F460 )'),
    ('ZTE-F612',  'GPON-ZTE-F612 ( ZTE-F612 )'),
    ('ZTE-F660',  'GPON-ZTE-F660 ( ZTE-F660 )'),
    ('ZTE-F6600', 'ZTE-F6600 ( ZTE-F6600 )'),
]

class OltOnuRegisterQuick(models.TransientModel):
    _name = 'olt.onu.register.quick'
    _description = 'Quick Register ONU (from scan)'

    customer_id = fields.Many2one('asr.radius.user', string="Customer", required=True)
    access_device_id = fields.Many2one('crm.access.device', string="OLT", required=True)
    interface = fields.Char(string="Interface", required=True, readonly=True,
                            help="OLT port (e.g., gpon-olt_1/5/10)")
    onu_slot = fields.Integer(string="ONU Slot", required=True, readonly=True,
                              help="Auto-detected free slot on this port")
    serial = fields.Char(string="Serial", required=True, readonly=True)
    name = fields.Char(string="Name/Description")

    onu_type = fields.Selection(_ONU_CHOICES, string="ONU Type", required=True)
    function_mode = fields.Selection([('bridge','Bridge'),('router','Router')],
                                     string="Function Mode", required=True, default='bridge')

    # Optional services (kept for UI completeness; no hard enforcement here)
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
        for field in ('customer_id', 'access_device_id', 'interface', 'onu_slot', 'serial', 'name'):
            ctx_key = f'default_{field}'
            if ctx_key in ctx:
                vals[field] = ctx[ctx_key]
        tech = ctx.get('default_technology', 'gpon')
        if 'onu_type' not in vals:
            vals['onu_type'] = 'ZTE-F612' if tech == 'gpon' else 'ZTE-F412'
        return vals

    @api.onchange('access_device_id')
    def _onchange_access_device_id(self):
        # If your device model has VLAN defaults, you can prefill here
        return

    def _execute_telnet_session(self, host, username, password, command, timeout=12):
        chunks = []
        try:
            tn = telnetlib.Telnet(host, 23, timeout)
        except Exception as e:
            raise UserError(_('Telnet connection failed to %s: %s') % (host, str(e)))
        try:
            # Login
            idx, _, _ = tn.expect([b'Username:', b'Login:', b'login:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % host)
            tn.write((username + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            idx, _, _ = tn.expect([b'Password:', b'password:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % host)
            tn.write((password + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)

            idx, _, text = tn.expect([
                b'>', b'#', b'$',            # success
                b'Username:',                # auth failed
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], timeout)
            if idx >= 3 or idx == -1:
                raise UserError(_('Authentication FAILED for %s@%s.\nGot: %s') %
                                (username, host, text.decode('utf-8', errors='ignore')[:300]))

            # Execute semicolon-separated commands
            commands = [c.strip() for c in command.split(';') if c.strip()]
            for cmd in commands:
                tn.write((cmd + '\n').encode('ascii', errors='ignore'))
                time.sleep(0.35)
                buf = tn.read_very_eager()
                chunks.append(buf)

            # Exit
            try:
                tn.write(b'exit\n'); time.sleep(0.2)
                tn.write(b'quit\n')
            except Exception:
                pass
        finally:
            try:
                tn.close()
            except Exception:
                pass

        data = b''.join(chunks) if chunks else b''
        output = data.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()
        # Basic error check
        if any(x in output.lower() for x in ('error', 'failed', 'invalid')):
            raise UserError(_('OLT returned error: %s') % output[:500])
        return output

    def action_register(self):
        """Register ONU: conf t; interface <port>; onu <slot> type <type> sn <serial>"""
        self.ensure_one()

        if not self.access_device_id or not getattr(self.access_device_id, 'ip_address', False):
            raise UserError(_('OLT missing Management IP.'))

        # ✅ ALWAYS from OLT (helper handles fallback to Company)
        user, pwd = self.access_device_id.get_telnet_credentials()

        olt_ip = self.access_device_id.ip_address.strip()
        registration_cmd = f"conf t;interface {self.interface};onu {self.onu_slot} type {self.onu_type} sn {self.serial};exit;exit"

        output = self._execute_telnet_session(olt_ip, user, pwd, registration_cmd)

        # Optional: update customer record fields if they exist
        try:
            vals = {}
            if 'ont_serial' in self.customer_id._fields:
                vals['ont_serial'] = self.serial
            if 'olt_pon_port' in self.customer_id._fields:
                vals['olt_pon_port'] = f"{self.interface}:{self.onu_slot}"
            if 'access_device_id' in self.customer_id._fields:
                vals['access_device_id'] = self.access_device_id.id
            if vals:
                self.customer_id.write(vals)
        except Exception:
            pass

        # Logs
        try:
            self.customer_id.message_post(
                body=_('✅ ONU Registered via Telnet:<br/>'
                       '• Port: %(port)s<br/>'
                       '• Slot: %(slot)d<br/>'
                       '• Type: %(type)s<br/>'
                       '• SN: %(sn)s<br/>'
                       '• Mode: %(mode)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'type': self.onu_type,
                    'sn': self.serial,
                    'mode': self.function_mode.upper()
                }
            )
            self.access_device_id.message_post(
                body=_('ONU registered: Slot %(slot)d, SN %(sn)s by %(user)s') % {
                    'slot': self.onu_slot,
                    'sn': self.serial,
                    'user': self.env.user.display_name
                }
            )
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ ONU Registered Successfully'),
                'message': _('Port: %(port)s, Slot: %(slot)d, SN: %(sn)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'sn': self.serial
                },
                'type': 'success',
                'sticky': False
            }
        }

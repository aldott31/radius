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

_SPEED_PROFILE_CHOICES = [
    ('10M', '10Mbps'),
    ('20M', '20Mbps'),
    ('50M', '50Mbps'),
    ('100M', '100Mbps'),
    ('200M', '200Mbps'),
    ('500M', '500Mbps'),
    ('1G', '1Gbps'),
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

    # Internet configuration
    internet_vlan = fields.Char(string="Internet VLAN", required=True)
    speed_profile = fields.Selection(_SPEED_PROFILE_CHOICES, string="Speed Profile",
                                     required=True, default='1G')

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

        # Set default internet_vlan from OLT if available
        if 'access_device_id' in vals and vals['access_device_id']:
            olt = self.env['crm.access.device'].browse(vals['access_device_id'])
            if olt.internet_vlan:
                vals['internet_vlan'] = olt.internet_vlan.split(',')[0].strip()

        return vals

    @api.onchange('access_device_id')
    def _onchange_access_device_id(self):
        # Prefill internet_vlan from OLT
        if self.access_device_id and self.access_device_id.internet_vlan:
            self.internet_vlan = self.access_device_id.internet_vlan.split(',')[0].strip()

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

    def _generate_router_config(self):
        """Generate GPON Router (PPPoE) configuration commands"""
        self.ensure_one()
        if not self.customer_id.username or not self.customer_id.radius_password:
            raise UserError(_('Customer missing RADIUS username or password for PPPoE configuration.'))

        # Convert gpon-olt_1/2/15 -> gpon_onu-1/2/15:10
        port_part = self.interface.replace('gpon-olt_', '')
        onu_interface = f"gpon_onu-{port_part}:{self.onu_slot}"
        vport_interface = f"vport-{port_part}.{self.onu_slot}:1"

        commands = [
            "conf t",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 1 tcont 1",
            "$",
            f"pon-onu-mng {onu_interface}",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"wan-ip ipv4 mode pppoe username {self.customer_id.username} password {self.customer_id.radius_password} vlan-profile {self.internet_vlan} host 1",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "$",
            f"interface {vport_interface}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "$",
            "exit"
        ]
        return ";".join(commands)

    def _generate_bridge_config(self):
        """Generate GPON Bridge configuration commands"""
        self.ensure_one()

        # Convert gpon-olt_1/2/15 -> gpon_onu-1/2/15:10
        port_part = self.interface.replace('gpon-olt_', '')
        onu_interface = f"gpon_onu-{port_part}:{self.onu_slot}"
        vport_interface = f"vport-{port_part}.{self.onu_slot}:1"

        commands = [
            "conf t",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 1 tcont 1",
            "$",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/1 from-internet",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"vlan port eth_0/1 mode tag vlan {self.internet_vlan}",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "$",
            f"interface {vport_interface}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "$",
            "exit"
        ]
        return ";".join(commands)

    def action_register(self):
        """Register ONU and configure it based on function_mode"""
        self.ensure_one()

        if not self.access_device_id or not getattr(self.access_device_id, 'ip_address', False):
            raise UserError(_('OLT missing Management IP.'))

        if not self.customer_id.username:
            raise UserError(_('Customer missing RADIUS username.'))

        # ✅ ALWAYS from OLT (helper handles fallback to Company)
        user, pwd = self.access_device_id.get_telnet_credentials()

        olt_ip = self.access_device_id.ip_address.strip()

        # Step 1: Register ONU
        registration_cmd = f"conf t;interface {self.interface};onu {self.onu_slot} type {self.onu_type} sn {self.serial};exit;exit"
        output = self._execute_telnet_session(olt_ip, user, pwd, registration_cmd)

        # Step 2: Configure ONU based on function_mode
        if self.function_mode == 'router':
            config_cmd = self._generate_router_config()
        else:  # bridge
            config_cmd = self._generate_bridge_config()

        output += "\n" + self._execute_telnet_session(olt_ip, user, pwd, config_cmd)

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
            mode_label = "PPPoE (Router)" if self.function_mode == 'router' else "Bridge"
            speed_label = dict(_SPEED_PROFILE_CHOICES).get(self.speed_profile, self.speed_profile)

            self.customer_id.message_post(
                body=_('✅ ONU Registered & Configured via Telnet:<br/>'
                       '• Port: %(port)s<br/>'
                       '• Slot: %(slot)d<br/>'
                       '• Type: %(type)s<br/>'
                       '• SN: %(sn)s<br/>'
                       '• Mode: %(mode)s<br/>'
                       '• VLAN: %(vlan)s<br/>'
                       '• Speed: %(speed)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'type': self.onu_type,
                    'sn': self.serial,
                    'mode': mode_label,
                    'vlan': self.internet_vlan,
                    'speed': speed_label
                }
            )
            self.access_device_id.message_post(
                body=_('ONU registered & configured: Slot %(slot)d, SN %(sn)s, Mode: %(mode)s by %(user)s') % {
                    'slot': self.onu_slot,
                    'sn': self.serial,
                    'mode': mode_label,
                    'user': self.env.user.display_name
                }
            )
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ ONU Registered & Configured Successfully'),
                'message': _('Port: %(port)s:%(slot)d, Mode: %(mode)s, VLAN: %(vlan)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'mode': mode_label,
                    'vlan': self.internet_vlan
                },
                'type': 'success',
                'sticky': False
            }
        }
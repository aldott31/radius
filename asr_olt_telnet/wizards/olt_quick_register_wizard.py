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
    tv_vlan = fields.Char(string="TV VLAN", required=False)
    voice_vlan = fields.Char(string="Voice VLAN", required=False)
    speed_profile = fields.Selection(_SPEED_PROFILE_CHOICES, string="Speed Profile",
                                     required=True, default='1G')

    # Helper fields for showing available VLANs
    available_internet_vlans_display = fields.Char(compute='_compute_available_vlans_display', store=False)
    available_tv_vlans_display = fields.Char(compute='_compute_available_vlans_display', store=False)
    available_voice_vlans_display = fields.Char(compute='_compute_available_vlans_display', store=False)

    # Display correct interface format based on OLT model
    interface_display = fields.Char(compute='_compute_interface_display', store=False,
                                    help="Interface format that will be used in the command")

    @api.depends('access_device_id')
    def _compute_available_vlans_display(self):
        """Compute display text for available VLANs"""
        for rec in self:
            if rec.access_device_id:
                rec.available_internet_vlans_display = rec.access_device_id.internet_vlan or 'Not configured'
                rec.available_tv_vlans_display = rec.access_device_id.tv_vlan or 'Not configured'
                rec.available_voice_vlans_display = rec.access_device_id.voice_vlan or 'Not configured'
            else:
                rec.available_internet_vlans_display = 'Select OLT first'
                rec.available_tv_vlans_display = 'Select OLT first'
                rec.available_voice_vlans_display = 'Select OLT first'

    @api.depends('interface', 'access_device_id')
    def _compute_interface_display(self):
        """Compute the correct interface format based on OLT model"""
        for rec in self:
            if not rec.interface:
                rec.interface_display = ''
                continue

            # Detect OLT model and convert format if needed
            model = (rec.access_device_id.model or '').upper() if rec.access_device_id else ''
            if 'C600' in model or 'C650' in model or 'C680' in model:
                # C600 format: gpon_olt-1/4/3 (underscore-dash)
                rec.interface_display = rec.interface.replace('-olt_', '_olt-')
            else:
                # C300 format: gpon-olt_1/4/3 (dash-underscore) - no change
                rec.interface_display = rec.interface

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

        # Set default VLANs from OLT if available
        if 'access_device_id' in vals and vals['access_device_id']:
            olt = self.env['crm.access.device'].browse(vals['access_device_id'])
            if olt.internet_vlan:
                vals['internet_vlan'] = olt.internet_vlan.split(',')[0].strip()
            if olt.tv_vlan:
                vals['tv_vlan'] = olt.tv_vlan.split(',')[0].strip()
            if olt.voice_vlan:
                vals['voice_vlan'] = olt.voice_vlan.split(',')[0].strip()

        return vals

    @api.onchange('access_device_id')
    def _onchange_access_device_id(self):
        # Prefill VLANs from OLT (first value from each CSV list)
        if self.access_device_id:
            if self.access_device_id.internet_vlan:
                self.internet_vlan = self.access_device_id.internet_vlan.split(',')[0].strip()
            if self.access_device_id.tv_vlan:
                self.tv_vlan = self.access_device_id.tv_vlan.split(',')[0].strip()
            if self.access_device_id.voice_vlan:
                self.voice_vlan = self.access_device_id.voice_vlan.split(',')[0].strip()

    @api.constrains('internet_vlan', 'tv_vlan', 'voice_vlan', 'access_device_id')
    def _check_vlan_values(self):
        """Validate that selected VLANs are in the OLT's configured VLANs"""
        for rec in self:
            if not rec.access_device_id:
                continue

            # Check Internet VLAN
            if rec.internet_vlan and rec.access_device_id.internet_vlan:
                available = [v.strip() for v in rec.access_device_id.internet_vlan.split(',')]
                if rec.internet_vlan not in available:
                    raise UserError(_('Internet VLAN "%s" is not configured on OLT "%s".\nAvailable: %s') %
                                    (rec.internet_vlan, rec.access_device_id.name,
                                     rec.access_device_id.internet_vlan))

            # Check TV VLAN
            if rec.tv_vlan and rec.access_device_id.tv_vlan:
                available = [v.strip() for v in rec.access_device_id.tv_vlan.split(',')]
                if rec.tv_vlan not in available:
                    raise UserError(_('TV VLAN "%s" is not configured on OLT "%s".\nAvailable: %s') %
                                    (rec.tv_vlan, rec.access_device_id.name,
                                     rec.access_device_id.tv_vlan))

            # Check Voice VLAN
            if rec.voice_vlan and rec.access_device_id.voice_vlan:
                available = [v.strip() for v in rec.access_device_id.voice_vlan.split(',')]
                if rec.voice_vlan not in available:
                    raise UserError(_('Voice VLAN "%s" is not configured on OLT "%s".\nAvailable: %s') %
                                    (rec.voice_vlan, rec.access_device_id.name,
                                     rec.access_device_id.voice_vlan))

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
        """Generate GPON Router (PPPoE) configuration commands - FULL registration + config"""
        self.ensure_one()
        if not self.customer_id.username or not self.customer_id.radius_password:
            raise UserError(_('Customer missing RADIUS username or password for PPPoE configuration.'))

        # Detect correct interface format based on OLT model
        model = (self.access_device_id.model or '').upper()
        if 'C600' in model or 'C650' in model or 'C680' in model:
            # C600 format: gpon_olt-1/4/3 (underscore-dash)
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            # C300 format: gpon-olt_1/4/3 (dash-underscore)
            interface_for_cmd = self.interface

        # Convert gpon-olt_1/2/15 -> 1/2/15 for ONU interface
        port_part = self.interface.replace('gpon-olt_', '')
        onu_interface = f"gpon_onu-{port_part}:{self.onu_slot}"
        vport_interface = f"vport-{port_part}.{self.onu_slot}:1"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 1 tcont 1",
            "exit",
            f"pon-onu-mng {onu_interface}",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"wan-ip ipv4 mode pppoe username {self.customer_id.username} password {self.customer_id.radius_password} vlan-profile {self.internet_vlan} host 1",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "exit",
            f"interface {vport_interface}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "exit",
        ]
        return ";".join(commands)

    def _generate_bridge_config(self):
        """Generate GPON Bridge configuration commands - FULL registration + config"""
        self.ensure_one()

        # Detect correct interface format based on OLT model
        model = (self.access_device_id.model or '').upper()
        if 'C600' in model or 'C650' in model or 'C680' in model:
            # C600 format: gpon_olt-1/4/3 (underscore-dash)
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            # C300 format: gpon-olt_1/4/3 (dash-underscore)
            interface_for_cmd = self.interface

        # Convert gpon-olt_1/2/15 -> 1/2/15 for ONU interface
        port_part = self.interface.replace('gpon-olt_', '')
        onu_interface = f"gpon_onu-{port_part}:{self.onu_slot}"
        vport_interface = f"vport-{port_part}.{self.onu_slot}:1"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 1 tcont 1",
            "exit",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/1 from-internet",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"vlan port eth_0/1 mode tag vlan {self.internet_vlan}",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "exit",
            f"interface {vport_interface}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "exit",
        ]
        return ";".join(commands)

    def action_register(self):
        """Register ONU and configure it based on function_mode - Single telnet session"""
        self.ensure_one()

        if not self.access_device_id or not getattr(self.access_device_id, 'ip_address', False):
            raise UserError(_('OLT missing Management IP.'))

        if not self.customer_id.username:
            raise UserError(_('Customer missing RADIUS username.'))

        # ✅ ALWAYS from OLT (helper handles fallback to Company)
        user, pwd = self.access_device_id.get_telnet_credentials()

        olt_ip = self.access_device_id.ip_address.strip()

        # Generate full command based on function_mode (includes registration + config)
        if self.function_mode == 'router':
            full_cmd = self._generate_router_config()
        else:  # bridge
            full_cmd = self._generate_bridge_config()

        # Execute in a single telnet session
        output = self._execute_telnet_session(olt_ip, user, pwd, full_cmd)

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

            # Build VLAN info
            vlan_info = f"Internet: {self.internet_vlan}"
            if self.tv_vlan:
                vlan_info += f", TV: {self.tv_vlan}"
            if self.voice_vlan:
                vlan_info += f", Voice: {self.voice_vlan}"

            self.customer_id.message_post(
                body=_('✅ ONU Registered & Configured via Telnet:<br/>'
                       '• Port: %(port)s<br/>'
                       '• Slot: %(slot)d<br/>'
                       '• Type: %(type)s<br/>'
                       '• SN: %(sn)s<br/>'
                       '• Mode: %(mode)s<br/>'
                       '• VLANs: %(vlan)s<br/>'
                       '• Speed: %(speed)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'type': self.onu_type,
                    'sn': self.serial,
                    'mode': mode_label,
                    'vlan': vlan_info,
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
                'message': _('Port: %(port)s:%(slot)d, Mode: %(mode)s, VLANs: %(vlan)s') % {
                    'port': self.interface,
                    'slot': self.onu_slot,
                    'mode': mode_label,
                    'vlan': vlan_info
                },
                'type': 'success',
                'sticky': False
            }
        }
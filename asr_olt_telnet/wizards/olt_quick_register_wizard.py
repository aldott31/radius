# -*- coding: utf-8 -*-
import time
import telnetlib
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_ONU_CHOICES = [
    ('ZTE-F412',  'ZTE-F412'),
    ('ZTE-F460',  'ZTE-F460'),
    ('ZTE-F612',  'ZTE-F612'),
    ('ZTE-F660',  'ZTE-F660'),
    ('ZTE-F6600', 'ZTE-F6600'),
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

    # ✅ UX Improvement: Store parent wizard IDs for navigation
    uncfg_wizard_id = fields.Integer(string="Parent Wizard ID", help="ID of uncfg wizard for back navigation")
    uncfg_line_id = fields.Integer(string="Line ID", help="ID of ONU line for retry")

    # ✅ Error tracking for retry functionality
    last_error = fields.Text(string="Last Error", readonly=True)
    registration_attempts = fields.Integer(string="Attempts", default=0, readonly=True)

    onu_type = fields.Selection(_ONU_CHOICES, string="ONU Type", required=True)
    function_mode = fields.Selection([
        ('bridge', 'Bridge'),
        ('router', 'Router'),
        ('bridge_mcast', 'Bridge + MCAST'),
        ('bridge_mcast_voip', 'Bridge + MCAST + VoIP'),
        ('data', 'Data Only'),
        ('router_mcast_voip', 'Router + MCAST + VoIP'),
    ], string="Function Mode", required=True, default='bridge')

    # Internet configuration
    internet_vlan = fields.Char(string="Internet VLAN", required=True)
    tv_vlan = fields.Char(string="TV VLAN", required=False)
    voice_vlan = fields.Char(string="Voice VLAN", required=False)
    speed_profile = fields.Selection(_SPEED_PROFILE_CHOICES, string="Speed Profile",
                                     required=True, default='1G')

    # VoIP configuration (for modes with telephony)
    voip_userid = fields.Char(string="VoIP UserID", help="SIP userid (e.g., 044310660)")
    voip_username = fields.Char(string="VoIP Username", help="SIP username (e.g., 044310660)")
    voip_password = fields.Char(string="VoIP Password", help="SIP password")

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

        # ✅ Store parent wizard IDs from context
        if 'uncfg_wizard_id' in ctx:
            vals['uncfg_wizard_id'] = ctx['uncfg_wizard_id']
        if 'uncfg_line_id' in ctx:
            vals['uncfg_line_id'] = ctx['uncfg_line_id']

        return vals

    def _get_onu_interface_format(self):
        """
        Get correct ONU interface format based on OLT model.
        Returns: (onu_interface, vport_interface, port_part)
        """
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model

        if is_c600:
            # C600 format: gpon_onu-1/2/15:slot
            port_part = self.interface.replace('gpon-olt_', '').replace('gpon_olt-', '')
            onu_interface = f"gpon_onu-{port_part}:{self.onu_slot}"
        else:
            # C300 format: gpon-onu_1/2/15:slot
            port_part = self.interface.replace('gpon-olt_', '')
            onu_interface = f"gpon-onu_{port_part}:{self.onu_slot}"

        vport_interface = f"vport-{port_part}.{self.onu_slot}:1"
        return onu_interface, vport_interface, port_part

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
        """✅ Execute telnet commands with per-command verification"""
        import re
        import logging
        _logger = logging.getLogger(__name__)

        chunks = []
        command_log = []

        try:
            tn = telnetlib.Telnet(host, 23, timeout)
        except Exception as e:
            raise UserError(_('Telnet connection failed to %s: %s') % (host, str(e)))

        try:
            # Login
            idx, _match, _text = tn.expect([b'Username:', b'Login:', b'login:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % host)
            tn.write((username + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            idx, _match, _text = tn.expect([b'Password:', b'password:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % host)
            tn.write((password + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)

            idx, _match, text = tn.expect([
                b'>', b'#', b'$',            # success
                b'Username:',                # auth failed
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], timeout)
            if idx >= 3 or idx == -1:
                raise UserError(_('Authentication FAILED for %s@%s.\nGot: %s') %
                                (username, host, text.decode('utf-8', errors='ignore')[:300]))

            # ✅ Execute commands with per-command verification
            commands = [c.strip() for c in command.split(';') if c.strip()]
            _logger.info(f'Executing {len(commands)} commands on {host}')

            for idx, cmd in enumerate(commands, 1):
                # Send command
                tn.write((cmd + '\n').encode('ascii', errors='ignore'))
                time.sleep(0.5)

                # Read response - wait for OLT to process
                buf = tn.read_very_eager()
                time.sleep(0.2)  # Give OLT extra time to finish writing output
                buf += tn.read_very_eager()  # Read any remaining output
                response = buf.decode('utf-8', errors='ignore')
                chunks.append(buf)

                # Log command and response
                command_log.append(f'[{idx}/{len(commands)}] {cmd}')
                _logger.debug(f'Command: {cmd}')
                _logger.debug(f'Response: {response[:200]}')

                # ✅ Check for errors in response
                response_lower = response.lower()

                # Log full response for debugging
                _logger.info(f'[{idx}/{len(commands)}] Response: {response[:500]}')

                # Skip false positives (these are normal messages)
                false_positives = [
                    'no error',
                    'error: 0',
                    'error-free',
                    'successful',
                    '[successful]'
                ]
                if any(fp in response_lower for fp in false_positives):
                    _logger.debug(f'Command {idx} successful (detected success keyword)')
                    continue

                # Check for real errors - only check for ZTE error markers
                error_markers = [
                    '% invalid input detected',
                    '% incomplete command',
                    '% ambiguous command',
                    'syntax error',
                    'command not found',
                    'failed to',
                    'error:'
                ]

                error_found = False
                for marker in error_markers:
                    if marker in response_lower:
                        error_found = True
                        # Extract error context (line containing error)
                        error_lines = [line for line in response.splitlines() if marker in line.lower()]
                        error_context = '\n'.join(error_lines[:3]) if error_lines else response[:300]

                        _logger.error(f'Command failed at step {idx}: {cmd}')
                        _logger.error(f'Error response: {response}')

                        raise UserError(_(
                            '❌ OLT Command Failed at step {step}/{total}:\n'
                            'Command: {cmd}\n\n'
                            'Error: {error}\n\n'
                            'Previous commands executed:\n{history}'
                        ).format(
                            step=idx,
                            total=len(commands),
                            cmd=cmd,
                            error=error_context,
                            history='\n'.join(command_log[:-1]) if len(command_log) > 1 else 'None'
                        ))
                        break

                if not error_found:
                    _logger.debug(f'Command {idx} completed (no error detected)')

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

        _logger.info(f'All {len(commands)} commands executed successfully on {host}')
        return output

    def _generate_router_config(self):
        """Generate GPON Router (PPPoE) configuration commands - FULL registration + config"""
        self.ensure_one()
        if not self.customer_id.username or not self.customer_id.radius_password:
            raise UserError(_('Customer missing RADIUS username or password for PPPoE configuration.'))

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            "sn-bind disable",
            f"description {self.customer_id.username}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 1 tcont 1",
            "switchport mode hybrid vport 1",
            f"service-port 1 vport 1 user-vlan {self.internet_vlan} user-etype PPPOE vlan {self.internet_vlan}",
            "port-identification format TEST vport 1",
            "port-identification sub-option remote-id enable vport 1",
            "port-identification sub-option remote-id name 10.50.80.17 vport 1",
            "pppoe-intermediate-agent enable vport 1",
            "exit",
            f"pon-onu-mng {onu_interface}",
            f"service net gemport 1 vlan {self.internet_vlan}",
            f"wan-ip 1 mode pppoe username {self.customer_id.username} password {self.customer_id.radius_password} vlan-profile {self.internet_vlan} host 1",
            "exit",
        ]
        return ";".join(commands)

    def _generate_bridge_config(self):
        """Generate GPON Bridge configuration commands - FULL registration + config"""
        self.ensure_one()

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

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

    def _generate_bridge_mcast_config(self):
        """Generate GPON Bridge + MCAST configuration commands"""
        self.ensure_one()

        if not self.tv_vlan:
            raise UserError(_('TV VLAN is required for Bridge + MCAST mode.'))

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        # Build multiple vport interfaces
        vport_interface_1 = f"vport-{port_part}.{self.onu_slot}:1"
        vport_interface_2 = f"vport-{port_part}.{self.onu_slot}:2"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "tcont 2 name mcast profile mcast",
            "gemport 1 tcont 1",
            "gemport 2 tcont 2",
            "exit",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/1 from-internet",
            "dhcp-ip ethuni eth_0/2 from-internet",
            f"vlan port eth_0/1 mode tag vlan {self.internet_vlan}",
            f"vlan port eth_0/2 mode tag vlan {self.tv_vlan}",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"service 2 gemport 2 vlan {self.tv_vlan}",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "exit",
            f"interface {vport_interface_1}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "exit",
            f"interface {vport_interface_2}",
            f"service-port 2 user-vlan {self.tv_vlan} vlan {self.tv_vlan}",
            "exit",
            f"igmp mvlan {self.tv_vlan}",
            f"receive-port {vport_interface_2}",
            "exit",
        ]
        return ";".join(commands)

    def _generate_bridge_mcast_voip_config(self):
        """Generate GPON Bridge + MCAST + VoIP configuration commands"""
        self.ensure_one()

        if not self.tv_vlan:
            raise UserError(_('TV VLAN is required for Bridge + MCAST + VoIP mode.'))
        if not self.voice_vlan:
            raise UserError(_('Voice VLAN is required for Bridge + MCAST + VoIP mode.'))
        if not self.voip_userid or not self.voip_username or not self.voip_password:
            raise UserError(_('VoIP credentials (UserID, Username, Password) are required for VoIP mode.'))

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        # Build multiple vport interfaces
        vport_interface_1 = f"vport-{port_part}.{self.onu_slot}:1"
        vport_interface_2 = f"vport-{port_part}.{self.onu_slot}:2"
        vport_interface_3 = f"vport-{port_part}.{self.onu_slot}:3"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "tcont 2 name mcast profile mcast",
            "tcont 3 name voip profile voip",
            "gemport 1 tcont 1",
            "gemport 2 tcont 2",
            "gemport 3 tcont 3",
            "exit",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/1 from-internet",
            "dhcp-ip ethuni eth_0/4 from-internet",
            f"vlan port eth_0/1 mode tag vlan {self.internet_vlan}",
            f"vlan port eth_0/4 mode tag vlan {self.tv_vlan}",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"service 2 gemport 2 vlan {self.tv_vlan}",
            f"service 3 gemport 3 vlan {self.voice_vlan}",
            "voip protocol sip",
            "voip-ip ipv4 mode dhcp vlan-profile PHONE host 2",
            f"sip-service pots_0/1 profile SIP userid {self.voip_userid} username {self.voip_username} password {self.voip_password}",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "exit",
            f"interface {vport_interface_1}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "exit",
            f"interface {vport_interface_2}",
            f"service-port 2 user-vlan {self.tv_vlan} vlan {self.tv_vlan}",
            "exit",
            f"interface {vport_interface_3}",
            f"service-port 3 user-vlan {self.voice_vlan} vlan {self.voice_vlan}",
            "exit",
            f"igmp mvlan {self.tv_vlan}",
            f"receive-port {vport_interface_2}",
            "exit",
        ]
        return ";".join(commands)

    def _generate_data_config(self):
        """Generate GPON Data Only configuration commands"""
        self.ensure_one()

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        # Data mode uses vport:4 instead of vport:1
        vport_interface = f"vport-{port_part}.{self.onu_slot}:4"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 4 name {self.speed_profile} profile {self.speed_profile}",
            "gemport 4 tcont 4",
            "exit",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/1 from-internet",
            f"service 4 gemport 4 vlan {self.internet_vlan}",
            f"vlan port eth_0/1 mode tag vlan {self.internet_vlan}",
            "exit",
            f"interface {vport_interface}",
            f"service-port 4 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "exit",
        ]
        return ";".join(commands)

    def _generate_router_mcast_voip_config(self):
        """Generate GPON Router + MCAST + VoIP configuration commands"""
        self.ensure_one()

        if not self.customer_id.username or not self.customer_id.radius_password:
            raise UserError(_('Customer missing RADIUS username or password for PPPoE configuration.'))
        if not self.tv_vlan:
            raise UserError(_('TV VLAN is required for Router + MCAST + VoIP mode.'))
        if not self.voice_vlan:
            raise UserError(_('Voice VLAN is required for Router + MCAST + VoIP mode.'))
        if not self.voip_userid or not self.voip_username or not self.voip_password:
            raise UserError(_('VoIP credentials (UserID, Username, Password) are required for VoIP mode.'))

        # Get correct interface formats based on OLT model
        onu_interface, vport_interface, port_part = self._get_onu_interface_format()

        # Detect correct OLT interface format
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        # Build multiple vport interfaces
        vport_interface_1 = f"vport-{port_part}.{self.onu_slot}:1"
        vport_interface_2 = f"vport-{port_part}.{self.onu_slot}:2"
        vport_interface_3 = f"vport-{port_part}.{self.onu_slot}:3"

        commands = [
            "conf t",
            f"interface {interface_for_cmd}",
            f"onu {self.onu_slot} type {self.onu_type} sn {self.serial}",
            "exit",
            f"interface {onu_interface}",
            f"name {self.customer_id.username}",
            f"tcont 1 name {self.speed_profile} profile {self.speed_profile}",
            "tcont 2 name mcast profile mcast",
            "tcont 3 name voip profile voip",
            "gemport 1 tcont 1",
            "gemport 2 tcont 2",
            "gemport 3 tcont 3",
            "exit",
            f"pon-onu-mng {onu_interface}",
            "dhcp-ip ethuni eth_0/2 from-internet",
            f"vlan port eth_0/2 mode tag vlan {self.tv_vlan}",
            f"service 1 gemport 1 vlan {self.internet_vlan}",
            f"service 2 gemport 2 vlan {self.tv_vlan}",
            f"service 3 gemport 3 vlan {self.voice_vlan}",
            "voip protocol sip",
            "voip-ip ipv4 mode dhcp vlan-profile PHONE host 2",
            f"sip-service pots_0/1 profile SIP userid {self.voip_userid} username {self.voip_username} password {self.voip_password}",
            f"wan-ip ipv4 mode pppoe username {self.customer_id.username} password {self.customer_id.radius_password} vlan-profile {self.internet_vlan} host 1",
            "security-mgmt 1 state enable mode forward protocol web",
            "security-mgmt 1 start-src-ip 77.242.20.10 end-src-ip 77.242.20.10",
            "exit",
            f"interface {vport_interface_1}",
            f"service-port 1 user-vlan {self.internet_vlan} vlan {self.internet_vlan}",
            "port-identification operator-profile service-port 1 TEST",
            "exit",
            f"interface {vport_interface_2}",
            f"service-port 2 user-vlan {self.tv_vlan} vlan {self.tv_vlan}",
            "exit",
            f"interface {vport_interface_3}",
            f"service-port 3 user-vlan {self.voice_vlan} vlan {self.voice_vlan}",
            "exit",
            f"igmp mvlan {self.tv_vlan}",
            f"receive-port {vport_interface_2}",
            "exit",
        ]
        return ";".join(commands)

    def action_back_to_list(self):
        """✅ Navigate back to uncfg wizard without losing data"""
        self.ensure_one()

        if not self.uncfg_wizard_id:
            raise UserError(_('Cannot navigate back: parent wizard not found.'))

        # Open uncfg wizard (it still has its data)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'olt.onu.uncfg.wizard',
            'res_id': self.uncfg_wizard_id,
            'view_mode': 'form',
            'target': 'new',
        }

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

        # Detect correct OLT interface format (needed for rollback)
        model = (self.access_device_id.model or '').upper()
        is_c600 = 'C600' in model or 'C650' in model or 'C680' in model
        if is_c600:
            interface_for_cmd = self.interface.replace('-olt_', '_olt-')
        else:
            interface_for_cmd = self.interface

        # Generate full command based on function_mode (includes registration + config)
        try:
            if self.function_mode == 'router':
                full_cmd = self._generate_router_config()
            elif self.function_mode == 'bridge':
                full_cmd = self._generate_bridge_config()
            elif self.function_mode == 'bridge_mcast':
                full_cmd = self._generate_bridge_mcast_config()
            elif self.function_mode == 'bridge_mcast_voip':
                full_cmd = self._generate_bridge_mcast_voip_config()
            elif self.function_mode == 'data':
                full_cmd = self._generate_data_config()
            elif self.function_mode == 'router_mcast_voip':
                full_cmd = self._generate_router_mcast_voip_config()
            else:
                raise UserError(_('Unknown function mode: %s') % self.function_mode)
        except UserError as e:
            # ✅ Store error for display
            self.write({
                'last_error': str(e),
                'registration_attempts': self.registration_attempts + 1
            })
            raise

        # Execute in a single telnet session
        try:
            output = self._execute_telnet_session(olt_ip, user, pwd, full_cmd)
        except UserError as e:
            # ❌ Command failed - ROLLBACK by deleting ONU
            error_msg = str(e)

            # Attempt automatic rollback to delete partially registered ONU
            rollback_msg = ""
            try:
                rollback_cmd = f"conf t;interface {interface_for_cmd};no onu {self.onu_slot};exit"
                self._execute_telnet_session(olt_ip, user, pwd, rollback_cmd)
                rollback_msg = _("\n\n🔄 Rollback successful: ONU deleted from OLT.\nYou can retry registration.")
            except Exception as rollback_error:
                rollback_msg = _(
                    "\n\n⚠️ Rollback failed: ONU may be partially configured on OLT.\n"
                    "Manual cleanup required:\n"
                    "interface {interface}\n"
                    "no onu {slot}"
                ).format(interface=interface_for_cmd, slot=self.onu_slot)

            full_error_msg = error_msg + rollback_msg

            # ✅ Store telnet error and allow retry
            self.write({
                'last_error': full_error_msg,
                'registration_attempts': self.registration_attempts + 1
            })

            # Return to form with error message displayed
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Registration Failed'),
                    'message': full_error_msg[:400],
                    'type': 'danger',
                    'sticky': True,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'olt.onu.register.quick',
                        'res_id': self.id,
                        'view_mode': 'form',
                        'target': 'new',
                    }
                }
            }

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
            mode_labels = {
                'router': 'PPPoE (Router)',
                'bridge': 'Bridge',
                'bridge_mcast': 'Bridge + MCAST',
                'bridge_mcast_voip': 'Bridge + MCAST + VoIP',
                'data': 'Data Only',
                'router_mcast_voip': 'Router + MCAST + VoIP',
            }
            mode_label = mode_labels.get(self.function_mode, self.function_mode)
            speed_label = dict(_SPEED_PROFILE_CHOICES).get(self.speed_profile, self.speed_profile)

            # Build VLAN info
            vlan_info = f"Internet: {self.internet_vlan}"
            if self.tv_vlan:
                vlan_info += f", TV: {self.tv_vlan}"
            if self.voice_vlan:
                vlan_info += f", Voice: {self.voice_vlan}"

            # Build message body
            msg_body = _('✅ ONU Registered & Configured via Telnet:<br/>'
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

            # Add VoIP info if configured
            if self.voip_userid and self.voip_username:
                msg_body += _('<br/>• VoIP User: %(voip_user)s') % {'voip_user': self.voip_username}

            self.customer_id.message_post(body=msg_body)
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
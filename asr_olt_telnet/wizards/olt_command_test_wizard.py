# -*- coding: utf-8 -*-
import time
import telnetlib
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OltCommandTestWizard(models.TransientModel):
    _name = 'olt.command.test.wizard'
    _description = 'OLT Command Test Wizard'

    olt_id = fields.Many2one('crm.access.device', string='OLT', required=True,
                             help="Select OLT to test")

    command_type = fields.Selection([
        ('gpon_uncfg', 'GPON Unconfigured ONUs'),
        ('epon_uncfg', 'EPON Unconfigured ONUs'),
        ('show_version', 'Show Version'),
        ('show_running', 'Show Running Config'),
        ('custom', 'Custom Command'),
    ], string="Command Type", default='gpon_uncfg', required=True)

    custom_command = fields.Char(string="Custom Command",
                                 help="Enter custom command (only if Custom selected)")

    timeout = fields.Integer(string="Timeout (seconds)", default=10,
                             help="Command execution timeout")

    result_text = fields.Text(string="Command Output", readonly=True)
    execution_time = fields.Float(string="Execution Time (s)", readonly=True, digits=(10, 3))
    status = fields.Selection([
        ('draft', 'Not Run'),
        ('success', 'Success'),
        ('error', 'Error'),
    ], default='draft', readonly=True)

    error_message = fields.Text(string="Error Details", readonly=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context or {}

        # Auto-detect OLT from context
        if ctx.get('default_olt_id'):
            vals['olt_id'] = ctx['default_olt_id']
        elif ctx.get('active_model') == 'crm.access.device' and ctx.get('active_id'):
            vals['olt_id'] = ctx['active_id']

        return vals

    def _get_command_string(self):
        """Build command string based on OLT model and command type"""
        self.ensure_one()

        if self.command_type == 'custom':
            if not self.custom_command:
                raise UserError(_('Please enter a custom command'))
            return self.custom_command.strip()

        device = self.olt_id
        model = (device.model or '').upper()
        manufacturer = (device.manufacturer or '').upper()

        # Command mapping
        commands = {
            'show_version': 'show version',
            'show_running': 'show running-config',
        }

        # GPON unconfigured - depends on model
        if self.command_type == 'gpon_uncfg':
            # C600+ series
            if 'C600' in model or 'C650' in model or 'C680' in model:
                commands['gpon_uncfg'] = 'show pon onu uncfg'
            # Huawei
            elif 'HUAWEI' in manufacturer or 'MA5800' in model or 'MA5600' in model:
                commands['gpon_uncfg'] = 'display ont autofind all'
            # C300 and default
            else:
                commands['gpon_uncfg'] = 'show gpon onu uncfg'

        # EPON unconfigured
        if self.command_type == 'epon_uncfg':
            if 'HUAWEI' in manufacturer:
                return 'N/A (Huawei GPON only)'
            commands['epon_uncfg'] = 'show onu unauthentication'

        return commands.get(self.command_type, '')

    def _telnet_run(self, host, username, password, command, timeout=10):
        """Execute Telnet command - copied from olt_onu_uncfg_wizard"""
        if not host:
            raise UserError(_('Missing OLT IP/host.'))
        if not username or not password:
            raise UserError(_('Set OLT Username/Password on OLT form or Company settings.'))

        chunks = []
        try:
            tn = telnetlib.Telnet(host, 23, timeout)
        except Exception as e:
            raise UserError(_('Telnet could not connect to %s: %s') % (host, str(e)))

        try:
            # Username
            idx, _, text = tn.expect([b'Username:', b'Login:', b'login:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt'))
            tn.write((username + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            # Password
            idx, _, text = tn.expect([b'Password:', b'password:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt'))
            tn.write((password + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.5)

            # Check auth
            idx, _, text = tn.expect([
                b'>', b'#', b'$',
                b'Username:',
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], timeout)

            if idx >= 3 or idx == -1:
                msg = text.decode('utf-8', errors='ignore')[:300]
                raise UserError(_('Authentication FAILED.\nGot: %s') % msg)

            # Execute command
            tn.write((command + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)

            buf = tn.read_very_eager()
            attempts = 0
            while attempts < 20 and (b'More' in buf or b'--More--' in buf or b'---- More ----' in buf):
                chunks.append(buf.replace(b'\x08', b''))
                tn.write(b' ')
                time.sleep(0.35)
                buf = tn.read_very_eager()
                attempts += 1
            chunks.append(buf)

            try:
                tn.write(b'\nquit\n')
                time.sleep(0.2)
            except Exception:
                pass

        finally:
            try:
                tn.close()
            except Exception:
                pass

        data = b''.join(chunks) if chunks else b''
        output = data.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()

        # Trim command echo
        lines = output.splitlines()
        if len(lines) > 2:
            output = '\n'.join(lines[2:])

        return output

    def action_run_test(self):
        """Execute the test command"""
        self.ensure_one()

        import time as time_module
        start_time = time_module.time()

        device = self.olt_id
        if not device or not device.ip_address:
            raise UserError(_('OLT missing IP address'))

        try:
            # Get command
            command = self._get_command_string()
            if command == 'N/A (Huawei GPON only)':
                raise UserError(_('EPON commands not supported on Huawei devices'))

            # Get credentials
            user, pwd = device.get_telnet_credentials()

            # Log attempt
            _logger.info('=' * 60)
            _logger.info('OLT COMMAND TEST')
            _logger.info(f'OLT: {device.name} ({device.model_display})')
            _logger.info(f'IP: {device.ip_address}')
            _logger.info(f'Command: {command}')
            _logger.info('=' * 60)

            # Execute
            output = self._telnet_run(
                device.ip_address.strip(),
                user, pwd, command,
                timeout=self.timeout
            )

            execution_time = time_module.time() - start_time

            self.write({
                'result_text': output or '(No output)',
                'execution_time': execution_time,
                'status': 'success',
                'error_message': False,
            })

            _logger.info(f'Command executed successfully in {execution_time:.3f}s')
            _logger.info(f'Output length: {len(output)} chars')

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Command Executed'),
                    'message': _('Completed in %.3f seconds') % execution_time,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            execution_time = time_module.time() - start_time
            error_msg = str(e)

            _logger.error(f'Command failed: {error_msg}', exc_info=True)

            self.write({
                'result_text': f'ERROR: {error_msg}',
                'execution_time': execution_time,
                'status': 'error',
                'error_message': error_msg,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Command Failed'),
                    'message': error_msg[:200],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_close(self):
        """Close wizard"""
        return {'type': 'ir.actions.act_window_close'}
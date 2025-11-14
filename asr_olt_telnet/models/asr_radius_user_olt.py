# -*- coding: utf-8 -*-
import re
import telnetlib
import time
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AsrRadiusUserOLT(models.Model):
    _inherit = 'asr.radius.user'

    def action_delete_onu(self):
        """Delete registered ONU from OLT via telnet"""
        self.ensure_one()

        if not self.olt_pon_port:
            raise UserError(_('No ONU registered for this customer (olt_pon_port is empty).'))

        if not self.access_device_id:
            raise UserError(_('No OLT assigned to this customer.'))

        if not self.access_device_id.ip_address:
            raise UserError(_('OLT has no IP address configured.'))

        # Parse olt_pon_port: "gpon-olt_1/2/15:1" → interface: gpon-olt_1/2/15, slot: 1
        match = re.match(r'^(.+?):(\d+)$', self.olt_pon_port.strip())
        if not match:
            raise UserError(_('Invalid olt_pon_port format: %s. Expected format: gpon-olt_X/Y/Z:slot') % self.olt_pon_port)

        interface = match.group(1)  # gpon-olt_1/2/15
        slot = match.group(2)  # 1

        # Detect OLT model and convert interface format if needed
        model = (self.access_device_id.model or '').upper()
        if 'C600' in model or 'C650' in model or 'C680' in model:
            # C600 format: gpon_olt-1/2/15 (underscore-dash)
            interface_for_cmd = interface.replace('-olt_', '_olt-')
        else:
            # C300 format: gpon-olt_1/2/15 (dash-underscore) - no change
            interface_for_cmd = interface

        # Get telnet credentials
        user, pwd = self.access_device_id.get_telnet_credentials()

        # Build delete command
        delete_cmd = f"conf t;interface {interface_for_cmd};no onu {slot};exit;exit"

        # Execute via telnet
        olt_ip = self.access_device_id.ip_address.strip()

        try:
            tn = telnetlib.Telnet(olt_ip, 23, timeout=12)
        except Exception as e:
            raise UserError(_('Telnet connection failed to %s: %s') % (olt_ip, str(e)))

        try:
            # Login
            idx, _, _ = tn.expect([b'Username:', b'Login:', b'login:'], 12)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % olt_ip)
            tn.write((user + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            idx, _, _ = tn.expect([b'Password:', b'password:'], 12)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % olt_ip)
            tn.write((pwd + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)

            idx, _, text = tn.expect([
                b'>', b'#', b'$',
                b'Username:',
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], 12)
            if idx >= 3 or idx == -1:
                raise UserError(_('Authentication FAILED for %s@%s') % (user, olt_ip))

            # Execute delete commands
            commands = [c.strip() for c in delete_cmd.split(';') if c.strip()]
            for cmd in commands:
                tn.write((cmd + '\n').encode('ascii', errors='ignore'))
                time.sleep(0.35)

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

        # Clear ONU fields
        self.write({
            'ont_serial': False,
            'olt_pon_port': False,
            'olt_ont_id': False,
        })

        # Log to chatter
        try:
            self.message_post(
                body=_('🗑️ ONU Deleted from OLT:<br/>'
                       '• Interface: %(iface)s<br/>'
                       '• Slot: %(slot)s<br/>'
                       '• Command: <code>no onu %(slot)s</code>') % {
                    'iface': interface_for_cmd,
                    'slot': slot
                },
                subtype_xmlid='mail.mt_note'
            )
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ ONU Deleted Successfully'),
                'message': _('ONU removed from %(iface)s:%(slot)s') % {
                    'iface': interface_for_cmd,
                    'slot': slot
                },
                'type': 'success',
                'sticky': False
            }
        }

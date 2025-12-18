# -*- coding: utf-8 -*-
import re
import telnetlib
import time
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartnerOLT(models.Model):
    _inherit = 'res.partner'

    def action_delete_onu(self):
        """
        Delete registered ONU from OLT.

        1) Nëse partneri ka radius_user_id -> delegon te asr.radius.user.action_delete_onu()
           (ky është rrugëtimi kryesor, sepse gjithë info e ONT ruhet te asr.radius.user).
        2) Nëse nuk ka radius_user_id -> përdor direkt fushat e partnerit (fallback).

        Fusha olt_pon_port te partneri mund të jetë:
        - formati i RI: "10.50.60.99 pon 1/9/6/33:1900"
        - formati i VJETËR: "gpon-olt_1/9/6:33"
        """
        self.ensure_one()

        # 1) Delego tek RADIUS user nëse është i lidhur
        if self.radius_user_id:
            return self.radius_user_id.action_delete_onu()

        # 2) Fallback: logjikë direkte nga partneri
        if not self.olt_pon_port:
            raise UserError(_('No ONU registered for this customer (PON Port is empty).'))

        if not self.access_device_id:
            raise UserError(_('No OLT assigned to this customer.'))

        if not self.access_device_id.ip_address:
            raise UserError(_('OLT has no IP address configured.'))

        raw = self.olt_pon_port.strip()
        model = (self.access_device_id.model or '').upper()

        interface_for_cmd = None
        slot = None

        # ==================== PARSING FORMAT I RI ====================
        # Shembull: "10.50.60.99 pon 1/9/6/33:1900"
        # Duam: path = "1/9/6", slot = "33"
        m = re.search(r'pon\s+(\d+/\d+/\d+)/(\d+):\d+$', raw)
        if m:
            path = m.group(1)      # 1/9/6
            slot = m.group(2)      # 33
            interface_path = path  # 1/9/6

            if any(x in model for x in ('C600', 'C650', 'C680')):
                # C600 format: gpon_olt-1/9/6
                interface_for_cmd = f"gpon_olt-{interface_path}"
            else:
                # C300 format: gpon-olt_1/9/6
                interface_for_cmd = f"gpon-olt_{interface_path}"

        # ==================== PARSING FORMAT I VJETËR ====================
        # Shembull: "gpon-olt_1/9/6:33"
        if not interface_for_cmd or not slot:
            port_match = re.match(r'^(.+?):(\d+)$', raw)
            if not port_match:
                raise UserError(
                    _(
                        'Invalid PON Port format: %s.\n'
                        'Expected formats like:\n'
                        '- gpon-olt_1/9/6:33\n'
                        '- 10.50.60.99 pon 1/9/6/33:1900'
                    ) % self.olt_pon_port
                )

            interface = port_match.group(1)  # p.sh. gpon-olt_1/9/6
            slot = port_match.group(2)       # p.sh. 33

            # Convert interface në formatin e duhur sipas modelit
            if any(x in model for x in ('C600', 'C650', 'C680')):
                # C600 format: gpon_olt-1/9/6 (underscore-dash)
                interface_for_cmd = interface.replace('-olt_', '_olt-')
            else:
                # C300 format: gpon-olt_1/9/6 (dash-underscore) - no change
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

            idx, _, _ = tn.expect([
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
                tn.write(b'exit\n')
                time.sleep(0.2)
                tn.write(b'quit\n')
            except Exception:
                pass
        finally:
            try:
                tn.close()
            except Exception:
                pass

        # Clear ONU fields on partner
        self.write({
            'ont_serial': False,
            'olt_pon_port': False,
            'olt_ont_id': False,
        })

        # Log to chatter
        try:
            self.message_post(
                body=_(
                    '🗑️ ONU Deleted from OLT:<br/>'
                    '• Interface: %(iface)s<br/>'
                    '• Slot: %(slot)s<br/>'
                    '• Command: <code>no onu %(slot)s</code>'
                ) % {
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

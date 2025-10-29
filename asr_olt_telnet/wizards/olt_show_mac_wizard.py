# -*- coding: utf-8 -*-
import re, time, telnetlib
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_MAC_RE = re.compile(r'[0-9A-Fa-f]{2}([:\-\.]?[0-9A-Fa-f]{2}){5}')

def _sanitize_mac(mac):
    if not mac:
        return ''
    mac = mac.strip()
    hexes = re.findall(r'[0-9A-Fa-f]{2}', mac)
    if len(hexes) == 6:
        return ':'.join(h.upper() for h in hexes)
    return mac.upper()

def _mac_to_dot4(mac):
    """Convert any MAC into xxxx.xxxx.xxxx (lower-case) expected by your OLT."""
    if not mac:
        return ''
    hexes = re.findall(r'[0-9A-Fa-f]{2}', mac)
    if len(hexes) != 6:
        return mac
    s = ''.join(h.lower() for h in hexes)  # 12 hex chars
    return '.'.join([s[0:4], s[4:8], s[8:12]])

class OltShowMacWizard(models.TransientModel):
    _name = 'olt.show.mac.wizard'
    _description = 'Show MAC on OLT (Telnet)'

    user_id = fields.Many2one('asr.radius.user', string='RADIUS User')
    olt_id = fields.Many2one('crm.access.device', string='OLT', required=True)
    mac_address = fields.Char(string='MAC Address', required=True)
    result_text = fields.Text(string='Command Output', readonly=True)
    status = fields.Selection([('draft','Draft'),('ok','OK'),('error','Error')], default='draft', readonly=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        user_id = self.env.context.get('default_user_id')
        olt_id = self.env.context.get('default_olt_id')
        mac = self.env.context.get('default_mac_address')

        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if not user_id and active_model == 'asr.radius.user' and active_id:
            user_id = active_id
        if not olt_id and active_model == 'crm.access.device' and active_id:
            olt_id = active_id

        if user_id:
            try:
                user = self.env['asr.radius.user'].browse(user_id)
                if not olt_id and getattr(user, 'access_device_id', False):
                    olt_id = user.access_device_id.id
                if not mac and user and user.username:
                    p = self.env['asr.radius.pppoe_status'].search([('username','=',user.username)], limit=1)
                    if p and p.circuit_id_mac:
                        parts = (p.circuit_id_mac or '').split('/')
                        mac = (parts[-1] if parts else '').strip()
            except Exception:
                pass

        if mac:
            vals['mac_address'] = _sanitize_mac(mac)
        if olt_id:
            vals['olt_id'] = olt_id
        if user_id:
            vals['user_id'] = user_id
        return vals

    def _telnet_run(self, host, username, password, command, timeout=8):
        if not host:
            raise UserError(_('Missing OLT IP/host.'))
        if not username or not password:
            raise UserError(_('Set OLT Username/Password on the Company form (FreeRADIUS page).'))

        chunks = []
        try:
            tn = telnetlib.Telnet(host, 23, timeout)
        except Exception as e:
            raise UserError(_('Telnet could not connect to %s: %s') % (host, str(e)))
        try:
            try:
                idx,_,_ = tn.expect([b'Username:', b'Login:'], timeout)
                if idx != -1:
                    tn.write((username + '\n').encode('ascii', errors='ignore'))
            except Exception: pass
            try:
                idx,_,_ = tn.expect([b'Password:'], timeout)
                if idx != -1:
                    tn.write((password + '\n').encode('ascii', errors='ignore'))
            except Exception: pass

            tn.expect([b'>', b'#', b'$'], timeout)
            tn.write((command + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.5)
            buf = tn.read_very_eager()

            attempts = 0
            while attempts < 15 and (b'More' in buf or b'--More--' in buf or b'---- More ----' in buf):
                chunks.append(buf.replace(b'\x08', b''))
                tn.write(b' ')
                time.sleep(0.35)
                buf = tn.read_very_eager()
                attempts += 1
            chunks.append(buf)
            try: tn.write(b'\nquit\n')
            except Exception: pass
        finally:
            try: tn.close()
            except Exception: pass

        data = b''.join(chunks) if chunks else b''
        return data.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()

    def action_run(self):
        self.ensure_one()
        # 1) Accept any MAC input, normalize for validation purposes
        mac_ui = (self.mac_address or '').strip()
        mac_norm = _sanitize_mac(mac_ui)  # AA:BB:...
        if not _MAC_RE.search(mac_norm):
            raise ValidationError(_('Invalid MAC format: %s') % mac_ui)

        # 2) Convert to vendor format xxxx.xxxx.xxxx for the command
        mac_cmd = _mac_to_dot4(mac_norm)

        device = self.olt_id
        if not device or not getattr(device, 'ip_address', False):
            raise UserError(_('OLT missing Management IP. Set it on the Access Device form.'))

        company = self.env.company.sudo()
        user = (company.olt_telnet_username or '').strip()
        pwd = (company.olt_telnet_password or '').strip()
        if not user or not pwd:
            raise UserError(_('Set OLT Username/Password on the Company form (FreeRADIUS page).'))

        output = self._telnet_run(device.ip_address.strip(), user, pwd, f'show mac {mac_cmd}', timeout=8)
        status = 'ok' if output else 'error'
        self.write({
            'mac_address': mac_norm,
            'result_text': output or _('(No output)'),
            'status': status,
        })
        try:
            if self.user_id:
                self.user_id.message_post(body=_('Ran \"show mac %(mac)s\" (dot4: %(macdot)s) on %(olt)s (%(ip)s).',
                                                 mac=mac_norm, macdot=mac_cmd, olt=device.name, ip=device.ip_address))
            device.message_post(body=_('Ran \"show mac %(mac)s\" (dot4: %(macdot)s). Initiator: %(user)s',
                                       mac=mac_norm, macdot=mac_cmd, user=self.env.user.display_name))
        except Exception:
            pass

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'olt.show.mac.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

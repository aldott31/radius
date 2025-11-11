# -*- coding: utf-8 -*-
import re, time, telnetlib, logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# --- MAC helpers ---
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
    """AA:BB:CC:DD:EE:FF -> xxxx.xxxx.xxxx (lower)"""
    if not mac:
        return ''
    hexes = re.findall(r'[0-9A-Fa-f]{2}', mac)
    if len(hexes) != 6:
        return mac
    s = ''.join(h.lower() for h in hexes)
    return '.'.join([s[0:4], s[4:8], s[8:12]])

# --- (opsionale) parse i output-it të 'show mac' për login port ---
_P_PORT = re.compile(r'vport-(\d+)/(\d+)/(\d+)\.(\d+):(\d+)', re.I)
_P_ROW  = re.compile(r'(?i)^\s*[0-9a-f:.\-]{12,}\s+(\d+)\s+\S+\s+([a-z\-0-9/.:]+)', re.M)

def _extract_vlan_pon_path(output_text: str):
    """
    Kthen (pon_path, vlan), p.sh. ('1/2/2/27','1662') ose (None,None)
      909a.4a92.35fc   1662   Dynamic   vport-1/2/2.27:1
    """
    if not output_text:
        return None, None
    m = _P_ROW.search(output_text or "")
    if not m:
        return None, None
    vlan = m.group(1)
    port = m.group(2)
    m2 = _P_PORT.search(port)
    if not m2:
        return None, vlan
    pon_path = f"{m2.group(1)}/{m2.group(2)}/{m2.group(3)}/{m2.group(4)}"
    return pon_path, vlan

class OltShowMacWizard(models.TransientModel):
    _name = 'olt.show.mac.wizard'
    _description = 'Show MAC on OLT (Telnet)'

    user_id = fields.Many2one('asr.radius.user', string='RADIUS User')
    olt_id = fields.Many2one('crm.access.device', string='OLT', required=True)
    mac_address = fields.Char(string='MAC Address', required=True)
    result_text = fields.Text(string='Command Output', readonly=True)
    status = fields.Selection([('draft','Draft'),('ok','OK'),('error','Error')], default='draft', readonly=True)

    # ---------------------------
    # AUTOFILL MAC & OLT on open
    # ---------------------------
    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context or {}

        user_id = ctx.get('default_user_id')
        olt_id  = ctx.get('default_olt_id')
        mac     = ctx.get('default_mac_address')

        # Merr active model/id kur hapet nga forma e user-it
        am, aid = ctx.get('active_model'), ctx.get('active_id')
        if not user_id and am == 'asr.radius.user' and aid:
            user_id = aid
        if not olt_id and am == 'crm.access.device' and aid:
            olt_id = aid

        # Vendos OLT nga user-i nëse mungon
        user = None
        if user_id:
            try:
                user = self.env['asr.radius.user'].browse(user_id)
            except Exception:
                user = None

        if user and not olt_id and getattr(user, 'access_device_id', False):
            olt_id = user.access_device_id.id

        # PRIORITET 1: PPPoE status (si te versioni yt që "e merrte")
        if (not mac) and user and getattr(user, 'username', False):
            try:
                rows = self.env['asr.radius.pppoe_status'].search_read(
                    domain=[('username', '=', user.username)],
                    fields=['circuit_id_mac'],
                    limit=1
                )
                if rows:
                    raw = (rows[0].get('circuit_id_mac') or '').strip()
                    mac = (raw.split('/')[-1] or '').strip()
            except Exception as e:
                _logger.debug("PPPoE status read failed: %s", e)

        # PRIORITET 2: Sesioni i fundit (calling-station-id) në asr.radius.session
        if (not mac) and user and getattr(user, 'username', False):
            try:
                Session = self.env['asr.radius.session'].sudo()
                last = Session.search([('username', '=', user.username)],
                                      order='acctstarttime desc, id desc', limit=1)
                if last:
                    mac_val = ''
                    # provoj disa emra fushash që hasen zakonisht
                    for cand in ('callingstationid', 'calling_station_id', 'mac', 'calling_station', 'calling_station_mac'):
                        if cand in last._fields:
                            mac_val = getattr(last, cand) or mac_val
                    if mac_val:
                        mac = mac_val
            except Exception as e:
                _logger.debug("Session lookup failed: %s", e)

        if mac:
            vals['mac_address'] = _sanitize_mac(mac)
        if olt_id:
            vals['olt_id'] = olt_id
        if user_id:
            vals['user_id'] = user_id
        return vals

    @api.onchange('user_id')
    def _onchange_user_id(self):
        """Rifresko OLT & MAC kur ndryshohet user-i (si te versioni yt i vjetër)"""
        for wiz in self:
            wiz.mac_address = False
            wiz.olt_id = False
            user = wiz.user_id
            if not user:
                continue
            if getattr(user, 'access_device_id', False):
                wiz.olt_id = user.access_device_id.id
            if getattr(user, 'username', False):
                try:
                    rows = self.env['asr.radius.pppoe_status'].search_read(
                        domain=[('username', '=', user.username)],
                        fields=['circuit_id_mac'],
                        limit=1
                    )
                    if rows:
                        raw = (rows[0].get('circuit_id_mac') or '').strip()
                        mac = (raw.split('/')[-1] or '').strip()
                        wiz.mac_address = _sanitize_mac(mac)
                except Exception:
                    pass

    # ---------------
    # TELNET RUNNER
    # ---------------
    def _telnet_run(self, host, username, password, command, timeout=10):
        if not host:
            raise UserError(_('Missing OLT IP/host.'))
        if not username or not password:
            raise UserError(_('Set OLT credentials on the OLT form or Company settings.'))

        chunks = []
        try:
            tn = telnetlib.Telnet(host, 23, timeout)
        except Exception as e:
            raise UserError(_('Telnet could not connect to %s: %s') % (host, str(e)))
        try:
            idx,_,_ = tn.expect([b'Username:', b'Login:', b'login:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % host)
            tn.write((username + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            idx,_,_ = tn.expect([b'Password:', b'password:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % host)
            tn.write((password + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.5)

            idx,_,text = tn.expect([
                b'>', b'#', b'$',            # success
                b'Username:',                # auth failed
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], timeout)
            if idx >= 3 or idx == -1:
                raise UserError(_('Authentication FAILED for %s@%s.\nGot: %s') %
                                (username, host, text.decode('utf-8', errors='ignore')[:300]))

            tn.write((command + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)
            buf = tn.read_very_eager()
            attempts = 0
            while attempts < 18 and (b'More' in buf or b'--More--' in buf or b'---- More ----' in buf):
                tn.write(b' ')
                time.sleep(0.3)
                buf += tn.read_very_eager()
                attempts += 1
            chunks.append(buf)
            try:
                tn.write(b'\nquit\n')
            except Exception:
                pass
        finally:
            try:
                tn.close()
            except Exception:
                pass

        data = b''.join(chunks) if chunks else b''
        return data.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()

    # ---------------
    # ACTION
    # ---------------
    def action_run(self):
        self.ensure_one()

        mac_ui = (self.mac_address or '').strip()
        mac_norm = _sanitize_mac(mac_ui)
        if not _MAC_RE.search(mac_norm):
            raise ValidationError(_('Invalid MAC format: %s') % mac_ui)

        mac_cmd = _mac_to_dot4(mac_norm)

        device = self.olt_id
        if not device or not getattr(device, 'ip_address', False):
            raise UserError(_('OLT missing Management IP.'))

        # ✅ Përdor cred-et e OLT-it (fallback te Company brenda helper-it)
        user, pwd = device.get_telnet_credentials()

        output = self._telnet_run(device.ip_address.strip(), user, pwd, f'show mac {mac_cmd}', timeout=10)
        status = 'ok' if output else 'error'
        self.write({
            'mac_address': mac_norm,
            'result_text': output or _('(No output)'),
            'status': status,
        })

        # (opsionale) përditëso Login Port te user-i
        if self.user_id and output:
            pon_path, vlan = _extract_vlan_pon_path(output)
            if pon_path and vlan and device.ip_address:
                login_port = f"{device.ip_address.strip()} pon {pon_path}:{vlan}"
                try:
                    self.user_id.write({'olt_login_port': login_port})
                    self.user_id.message_post(body=_('Updated Login Port: %s') % login_port)
                except Exception:
                    pass

        try:
            if self.user_id:
                self.user_id.message_post(body=_('Ran "show mac %(mac)s" (dot4: %(macdot)s) on %(olt)s (%(ip)s).',
                                                 mac=mac_norm, macdot=mac_cmd, olt=device.name, ip=device.ip_address))
            device.message_post(body=_('Ran "show mac %(mac)s" (dot4: %(macdot)s). Initiator: %(user)s',
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

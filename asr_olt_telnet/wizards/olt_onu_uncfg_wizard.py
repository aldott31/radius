# -*- coding: utf-8 -*-
import re
import time
import telnetlib
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_TAB_LINE_RE = re.compile(r"^-{3,}|^_+|^=+")
_SPACES_RE = re.compile(r"\s{2,}")

class OltOnuUncfgLine(models.TransientModel):
    _name = 'olt.onu.uncfg.line'
    _description = 'Unregistered ONU (parsed row)'

    wizard_id = fields.Many2one('olt.onu.uncfg.wizard', ondelete='cascade')
    technology = fields.Selection([('gpon','GPON'), ('epon','EPON')], string="Tech")
    olt_index = fields.Char(string="OltIndex")
    model = fields.Char(string="Model")
    mac = fields.Char(string="MAC")
    sn = fields.Char(string="SN")
    raw = fields.Char(string="Raw Line")

    def _extract_olt_port(self, onu_index):
        """Convert gpon-onu_1/5/10:1 → gpon-olt_1/5/10; epon-onu_1/2/3:4 → epon-olt_1/2/3"""
        if not onu_index:
            return ''
        m = re.match(r'(gpon|epon)-onu_(\d+/\d+/\d+):\d+', onu_index, re.IGNORECASE)
        if m:
            return f"{m.group(1).lower()}-olt_{m.group(2)}"
        return onu_index  # fallback

    def _find_free_slot(self, olt_device, olt_port):
        """Telnet → 'show running-config interface <port>' → parse slots → return first free"""
        if not olt_device or not getattr(olt_device, 'ip_address', False):
            raise UserError(_('OLT device has no IP address'))

        # ✅ ALWAYS from OLT (fallback handled in helper)
        user, pwd = olt_device.get_telnet_credentials()

        cmd = f"show running-config interface {olt_port}"
        output = self.wizard_id._telnet_run(
            olt_device.ip_address.strip(),
            user, pwd, cmd, timeout=10
        )

        occupied = set()
        for line in (output or '').splitlines():
            # Example: "  onu 8 type ZTE-F612 sn ZTEGC9647C69"
            m = re.match(r'^\s*onu\s+(\d+)\s+type', line, re.IGNORECASE)
            if m:
                try:
                    occupied.add(int(m.group(1)))
                except Exception:
                    pass

        # GPON zakonisht 1..128; EPON 1..64
        max_slots = 128 if 'gpon' in olt_port.lower() else 64
        for slot in range(1, max_slots + 1):
            if slot not in occupied:
                return slot

        raise UserError(_('No free slots available on port %s (all %d occupied)') % (olt_port, max_slots))

    def action_open_register(self):
        """Open quick register wizard with auto-detected free slot."""
        self.ensure_one()
        wiz = self.wizard_id

        olt_port = self._extract_olt_port(self.olt_index)
        try:
            free_slot = self._find_free_slot(wiz.olt_id, olt_port)
        except Exception as e:
            raise UserError(_('Failed to find free slot: %s') % str(e))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'olt.onu.register.quick',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_customer_id': wiz.user_id.id if wiz.user_id else False,
                'default_access_device_id': wiz.olt_id.id if wiz.olt_id else False,
                'default_interface': olt_port,
                'default_onu_slot': free_slot,
                'default_serial': (self.sn or '').strip(),
                'default_name': (wiz.user_id.name or getattr(wiz.user_id, 'username', '')) if wiz.user_id else '',
                'default_technology': self.technology or 'gpon',
            }
        }


class OltOnuUncfgWizard(models.TransientModel):
    _name = 'olt.onu.uncfg.wizard'
    _description = 'List Unregistered ONUs on OLT (Telnet)'

    user_id = fields.Many2one('asr.radius.user', string='RADIUS User')
    olt_id = fields.Many2one('crm.access.device', string='OLT', required=True, help="Access Device with Management IP")
    tech = fields.Selection([('auto','Auto (GPON→EPON)'), ('gpon','GPON only'), ('epon','EPON only')],
                            default='auto', required=True)
    result_text = fields.Text(string='Raw Output', readonly=True)
    line_ids = fields.One2many('olt.onu.uncfg.line', 'wizard_id', string="Unregistered ONUs")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context or {}
        user_id = ctx.get('default_user_id')
        olt_id = ctx.get('default_olt_id')

        if not user_id and ctx.get('active_model') == 'asr.radius.user' and ctx.get('active_id'):
            user_id = ctx['active_id']
        if user_id:
            vals['user_id'] = user_id
            if not olt_id:
                u = self.env['asr.radius.user'].browse(user_id)
                if u and getattr(u, 'access_device_id', False):
                    olt_id = u.access_device_id.id
        if olt_id:
            vals['olt_id'] = olt_id
        return vals

    def _telnet_run(self, host, username, password, command, timeout=10):
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
            idx, match, text = tn.expect([b'Username:', b'Login:', b'login:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % host)
            tn.write((username + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            # Password
            idx, match, text = tn.expect([b'Password:', b'password:'], timeout)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % host)
            tn.write((password + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.5)

            # Prompt or auth fail
            idx, match, text = tn.expect([
                b'>', b'#', b'$',            # success
                b'Username:',                # auth failed again
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], timeout)
            if idx >= 3 or idx == -1:
                msg = text.decode('utf-8', errors='ignore')[:300]
                raise UserError(_('Authentication FAILED for %s@%s.\nGot: %s') % (username, host, msg))

            # Execute command (+ pagination)
            tn.write((command + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)
            buf = tn.read_very_eager()
            attempts = 0
            while attempts < 18 and (b'More' in buf or b'--More--' in buf or b'---- More ----' in buf):
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
        # Trim echo
        lines = output.splitlines()
        if len(lines) > 2:
            output = '\n'.join(lines[2:])
        return output

    def _parse_uncfg(self, output_text, tech_key):
        """
        Parse 'show gpon onu uncfg' (GPON) dhe 'show onu unauthentication' (EPON)
        - Suporton dy forma:
          1) Me header:
               OnuIndex                 Sn                  State
               ---------------------------------------------------
               gpon-onu_1/5/10:1       ZTEGC9647C69        unknown
          2) Pa header (si në screenshot):
               gpon-onu_1/5/10:1  ZTEGC9647C69  unknown
        - Kthen lista dictionaries për One2many 'line_ids'.
        """
        rows = []
        if not output_text:
            return rows

        lines = [l.rstrip() for l in output_text.splitlines() if l.strip()]

        # 1) Provo të gjesh header (formati klasik)
        header_idx = -1
        for i, line in enumerate(lines):
            if re.search(r'\bOnu(Index)?\b', line, re.IGNORECASE) and re.search(r'\b(Sn|SN|MAC)\b', line,
                                                                                re.IGNORECASE):
                header_idx = i
                break

        start = header_idx + 1 if header_idx != -1 else 0
        # skip një vijë ndarëse pas header-it
        if start < len(lines) and _TAB_LINE_RE.search(lines[start]):
            start += 1

        # 2) Regex i përgjithshëm për një rresht (me ose pa header)
        #   <idx> [model/mac]? <sn> <state?>
        pat = re.compile(
            r'^(?P<idx>(?:gpon|epon)-onu_\d+/\d+/\d+:\d+)\s+'
            r'(?P<c2>\S+)'  # mund të jetë SN ose MODEL
            r'(?:\s+(?P<c3>\S+))?'  # mund të jetë STATE ose MAC
            r'(?:\s+(?P<c4>\S+))?$',  # ndonjë kolonë shtesë (SN/STATE)
            re.IGNORECASE
        )

        for ln in lines[start:]:
            if _TAB_LINE_RE.search(ln):
                continue

            m = pat.match(ln.strip())
            if not m:
                continue

            idx = m.group('idx')
            c2 = (m.group('c2') or '')
            c3 = (m.group('c3') or '')
            c4 = (m.group('c4') or '')

            model = ''
            mac = ''
            sn = ''
            state = ''

            # Heuristikë e thjeshtë:
            # - Formati pa header i C300 zakonisht është: <idx> <SN> <state>
            # - Disa variante japin: <idx> <MODEL> <MAC> <SN/state>
            if c4:
                # 4 kolona: supozo MODEL, MAC, SN/STATE
                model = c2
                mac = c3
                # c4 shpesh është SN ose STATE; e ruajmë si SN nëse duket serial (alnum)
                if re.fullmatch(r'[A-Za-z0-9]+', c4):
                    sn = c4
                else:
                    state = c4
            elif c3:
                # 3 kolona: <idx> <SN> <STATE>
                sn = c2
                state = c3
            else:
                # 2 kolona: <idx> <SN> (pa state)
                sn = c2

            rows.append({
                'technology': tech_key,
                'olt_index': idx,
                'model': model,
                'mac': mac,
                'sn': sn,
                'raw': ln.strip(),
            })

        return rows

    def action_fetch(self):
        self.ensure_one()
        device = self.olt_id
        if not device or not getattr(device, 'ip_address', False):
            raise UserError(_('OLT missing Management IP. Set it on the Access Device form.'))

        # ✅ Prefer OLT creds (fallback handled inside helper)
        user, pwd = device.get_telnet_credentials()

        outputs, rows = [], []
        if self.tech in ('auto', 'gpon'):
            try:
                out_gpon = self._telnet_run(device.ip_address.strip(), user, pwd, 'show gpon onu uncfg', timeout=10)
                outputs.append("### GPON (show gpon onu uncfg)\n" + (out_gpon or "(no output)"))
                rows += self._parse_uncfg(out_gpon, 'gpon')
            except Exception as e:
                outputs.append(f"### GPON error: {e}")
        if self.tech in ('auto', 'epon'):
            try:
                out_epon = self._telnet_run(device.ip_address.strip(), user, pwd, 'show onu unauthentication', timeout=10)
                outputs.append("### EPON (show onu unauthentication)\n" + (out_epon or "(no output)"))
                rows += self._parse_uncfg(out_epon, 'epon')
            except Exception as e:
                outputs.append(f"### EPON error: {e}")

        self.line_ids.unlink()
        for r in rows:
            self.env['olt.onu.uncfg.line'].create(dict(r, wizard_id=self.id))
        self.result_text = "\n\n".join(outputs) if outputs else _("(No output)")
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'olt.onu.uncfg.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

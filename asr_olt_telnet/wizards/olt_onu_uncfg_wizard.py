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
    technology = fields.Selection([('gpon', 'GPON'), ('epon', 'EPON')], string="Tech")
    olt_index = fields.Char(string="OltIndex")
    model = fields.Char(string="Model")
    mac = fields.Char(string="MAC")
    sn = fields.Char(string="SN")
    raw = fields.Char(string="Raw Line")

    def _extract_olt_port(self, onu_index):
        """
        Convert ONU index to OLT port:
        - C300: gpon-onu_1/5/10:1 → gpon-olt_1/5/10
        - C300: epon-onu_1/2/3:4 → epon-olt_1/2/3
        - C600: gpon_olt-1/4/3 → gpon-olt_1/4/3 (pa :slot)
        - C600: pon-onu_1/1/1:5 → gpon-olt_1/1/1
        """
        if not onu_index:
            return ''

        # Match both C300 (gpon-onu_X:slot) and C600 (gpon_olt-X pa slot)
        m = re.match(r'(gpon|epon|pon)[-_](onu|olt)[-_](\d+/\d+/\d+)(?::\d+)?', onu_index, re.IGNORECASE)
        if m:
            tech = m.group(1).lower()
            port = m.group(3)

            # C600 përdor "pon" por në konfigurim duhet "gpon-olt"
            if tech == 'pon':
                tech = 'gpon'  # Default për C600

            return f"{tech}-olt_{port}"

        return onu_index

    def _find_free_slot(self, olt_device, olt_port):
        """Telnet → 'show running-config interface <port>' → parse slots → return first free"""
        if not olt_device or not getattr(olt_device, 'ip_address', False):
            raise UserError(_('OLT device has no IP address'))

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
    tech = fields.Selection([('auto', 'Auto (GPON→EPON)'), ('gpon', 'GPON only'), ('epon', 'EPON only')],
                            default='auto', required=True)
    result_text = fields.Text(string='Raw Output', readonly=True)
    line_ids = fields.One2many('olt.onu.uncfg.line', 'wizard_id', string="Unregistered ONUs")
    onu_count = fields.Integer(string='ONU Count', compute='_compute_onu_count', store=False)

    @api.depends('line_ids')
    def _compute_onu_count(self):
        """Count number of unregistered ONUs"""
        for rec in self:
            rec.onu_count = len(rec.line_ids)

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
                b'>', b'#', b'$',  # success
                b'Username:',  # auth failed again
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
        Parse 'show gpon onu uncfg' (C300), 'show pon onu uncfg' (C600) dhe 'show onu unauthentication' (EPON)

        Formate të mbështetura:
        1) C300 format:
               gpon-onu_1/5/10:1       ZTEGC9647C69        unknown

        2) C600 format me header:
               OltIndex            Model              MAC               SN
               -------------------------------------------------------------------------
               gpon_olt-1/4/3      F612V6.0           N/A               ZTEGC97E6BC5

        3) C600 format pa header:
               pon-onu_1/1/1:1    ZTEGC9647C69   auto-find
        """
        rows = []
        if not output_text:
            return rows

        lines = [l.rstrip() for l in output_text.splitlines() if l.strip()]

        # 1) Provo të gjesh header (formati klasik)
        header_idx = -1
        for i, line in enumerate(lines):
            if re.search(r'\b(Onu|Olt)(Index)?\b', line, re.IGNORECASE) and re.search(r'\b(Sn|SN|MAC|Serial|Model)\b', line,
                                                                                re.IGNORECASE):
                header_idx = i
                break

        start = header_idx + 1 if header_idx != -1 else 0
        # skip një vijë ndarëse pas header-it
        if start < len(lines) and _TAB_LINE_RE.search(lines[start]):
            start += 1

        # 2) Regex i përgjithshëm për një rresht (me ose pa header)
        #   Mbështet: gpon-onu_X:slot, gpon_olt-X (pa slot), epon-onu_X:slot
        #   C300: gpon-onu_1/5/10:1
        #   C600: gpon_olt-1/4/3 (pa :slot në fund!)
        pat = re.compile(
            r'^(?P<idx>(?:gpon|epon|pon)[-_](?:onu|olt)[-_]\d+/\d+/\d+(?::\d+)?)\s+'
            r'(?P<c2>\S+)'  # mund të jetë SN ose MODEL
            r'(?:\s+(?P<c3>\S+))?'  # mund të jetë STATE ose MAC
            r'(?:\s+(?P<c4>\S+))?$',  # ndonjë kolonë shtesë (SN/STATE)
            re.IGNORECASE
        )

        for ln in lines[start:]:
            if _TAB_LINE_RE.search(ln):
                continue

            stripped_line = ln.strip()

            # Skip standalone CLI prompts (lines that are only a prompt)
            # e.g., "Bllok-OLT.3#" or "C600-Name#"
            if re.match(r'^[\w\.-]+#\s*$', stripped_line):
                continue

            # Clean CLI prompt from end of data lines
            # e.g., "gpon-onu_1/17/14:1  ZTEGC6868F3C  unknown  Bllok-OLT.3#"
            #   →   "gpon-onu_1/17/14:1  ZTEGC6868F3C  unknown"
            cleaned_line = re.sub(r'\s+[\w\.-]+#\s*$', '', stripped_line)

            m = pat.match(cleaned_line)
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
            # - C600 format: <idx> <SN> <state>
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

            # C600 nuk ka :slot për unregistered ONUs, vetëm port
            # Slot-i auto-detektohet kur klikohet "Register"
            # C300 ka :slot në output dhe e mbajmë si është
            # C600: gpon_olt-1/4/3 (pa :slot)
            # C300: gpon-onu_1/5/10:1 (me :slot)

            rows.append({
                'technology': tech_key,
                'olt_index': idx,  # Mbaje formatin origjinal
                'model': model,
                'mac': mac,
                'sn': sn,
                'raw': ln.strip(),
            })

        return rows

    def _detect_gpon_command(self, device):
        """
        Detekto komandën e saktë bazuar në modelin e OLT.

        Returns:
            str: Komanda për GPON unconfigured ONUs
        """
        model = (device.model or '').upper()
        manufacturer = (device.manufacturer or '').upper()

        _logger.info(f'Detecting command for OLT: {device.name}')
        _logger.info(f'  Model: {model}')
        _logger.info(f'  Manufacturer: {manufacturer}')

        # ZTE C600/C650 series
        if 'C600' in model or 'C650' in model or 'C680' in model:
            cmd = 'show pon onu uncfg'
            _logger.info(f'  → Using C600+ command: {cmd}')
            return cmd

        # ZTE C300/C320/C220 series (default)
        if 'ZTE' in manufacturer or 'C300' in model or 'C320' in model or 'C220' in model:
            cmd = 'show gpon onu uncfg'
            _logger.info(f'  → Using C300 command: {cmd}')
            return cmd

        # Huawei
        if 'HUAWEI' in manufacturer or 'MA5800' in model or 'MA5600' in model:
            cmd = 'display ont autofind all'
            _logger.info(f'  → Using Huawei command: {cmd}')
            return cmd

        # Default fallback (C300 style)
        cmd = 'show gpon onu uncfg'
        _logger.warning(f'  → Unknown model, using default: {cmd}')
        return cmd

    def action_fetch(self):
        self.ensure_one()
        device = self.olt_id
        if not device or not getattr(device, 'ip_address', False):
            raise UserError(_('OLT missing Management IP. Set it on the Access Device form.'))

        _logger.info('=' * 60)
        _logger.info('ONU UNCFG FETCH STARTED')
        _logger.info(f'OLT: {device.name}')
        _logger.info(f'Model: {device.model or "Not set"}')
        _logger.info(f'Manufacturer: {device.manufacturer or "Not set"}')
        _logger.info(f'IP: {device.ip_address}')
        _logger.info(f'Tech mode: {self.tech}')
        _logger.info('=' * 60)

        user, pwd = device.get_telnet_credentials()

        outputs, rows = [], []

        if self.tech in ('auto', 'gpon'):
            try:
                # ✅ Detekto komandën e saktë
                gpon_cmd = self._detect_gpon_command(device)

                _logger.info(f'Executing GPON command: {gpon_cmd}')
                out_gpon = self._telnet_run(device.ip_address.strip(), user, pwd, gpon_cmd, timeout=10)

                outputs.append(f"### GPON ({gpon_cmd})\n" + (out_gpon or "(no output)"))

                parsed = self._parse_uncfg(out_gpon, 'gpon')
                _logger.info(f'Parsed {len(parsed)} GPON ONUs')
                rows += parsed

            except Exception as e:
                _logger.error(f'GPON command failed: {e}', exc_info=True)
                outputs.append(f"### GPON error: {e}")

        if self.tech in ('auto', 'epon'):
            try:
                epon_cmd = 'show onu unauthentication'
                _logger.info(f'Executing EPON command: {epon_cmd}')

                out_epon = self._telnet_run(device.ip_address.strip(), user, pwd, epon_cmd, timeout=10)
                outputs.append(f"### EPON ({epon_cmd})\n" + (out_epon or "(no output)"))

                parsed = self._parse_uncfg(out_epon, 'epon')
                _logger.info(f'Parsed {len(parsed)} EPON ONUs')
                rows += parsed

            except Exception as e:
                _logger.error(f'EPON command failed: {e}', exc_info=True)
                outputs.append(f"### EPON error: {e}")

        _logger.info(f'Total ONUs found: {len(rows)}')
        _logger.info('=' * 60)

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
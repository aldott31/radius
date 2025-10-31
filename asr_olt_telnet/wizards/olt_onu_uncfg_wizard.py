# -*- coding: utf-8 -*-
import re, time, telnetlib
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

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

    def action_open_register(self):
        """Hap wizard-in e regjistrimit me vlerat e kësaj radhe."""
        self.ensure_one()
        wiz = self.wizard_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'olt.onu.register.quick',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_customer_id': wiz.user_id.id if wiz.user_id else False,
                'default_access_device_id': wiz.olt_id.id if wiz.olt_id else False,
                'default_interface': self.olt_index or '',
                'default_serial': (self.sn or '').strip(),
                'default_name': (wiz.user_id.name or wiz.user_id.username) if wiz.user_id else '',
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
                if u and u.access_device_id:
                    olt_id = u.access_device_id.id
        if olt_id:
            vals['olt_id'] = olt_id
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
                idx, _, _ = tn.expect([b'Username:', b'Login:'], timeout)
                if idx != -1:
                    tn.write((username + '\n').encode('ascii', errors='ignore'))
            except Exception:
                pass
            try:
                idx, _, _ = tn.expect([b'Password:'], timeout)
                if idx != -1:
                    tn.write((password + '\n').encode('ascii', errors='ignore'))
            except Exception:
                pass

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

    def _parse_uncfg(self, output_text, tech_key):
        rows = []
        if not output_text:
            return rows
        lines = [l.rstrip() for l in output_text.splitlines() if l.strip()]
        header_idx = -1
        for i, line in enumerate(lines):
            if ('OltIndex' in line and 'Model' in line) or (('MAC' in line or 'SN' in line) and 'Index' in line):
                header_idx = i
                break
        if header_idx == -1:
            return rows
        start = header_idx + 1
        if start < len(lines) and _TAB_LINE_RE.search(lines[start]):
            start += 1
        for ln in lines[start:]:
            if _TAB_LINE_RE.search(ln):
                continue
            parts = _SPACES_RE.split(ln.strip())
            if len(parts) >= 4:
                olt_index, model, mac, sn = parts[0], parts[1], parts[2], parts[3]
            elif len(parts) == 3:
                olt_index, model, mac = parts[0], parts[1], parts[2]
                sn = ''
            else:
                olt_index = ln.strip(); model = mac = sn = ''
            rows.append({'technology': tech_key, 'olt_index': olt_index, 'model': model, 'mac': mac, 'sn': sn, 'raw': ln.strip()})
        return rows

    def action_fetch(self):
        self.ensure_one()
        device = self.olt_id
        if not device or not getattr(device, 'ip_address', False):
            raise UserError(_('OLT missing Management IP. Set it on the Access Device form.'))
        company = self.env.company.sudo()
        user = (getattr(company, 'olt_telnet_username', '') or '').strip()
        pwd = (getattr(company, 'olt_telnet_password', '') or '').strip()
        if not user or not pwd:
            raise UserError(_('Set OLT Username/Password on the Company form (FreeRADIUS page).'))

        outputs = []; rows = []
        if self.tech in ('auto','gpon'):
            try:
                out_gpon = self._telnet_run(device.ip_address.strip(), user, pwd, 'show pon onu uncfg', timeout=8)
                outputs.append("### GPON (show pon onu uncfg)\n" + (out_gpon or "(no output)"))
                rows += self._parse_uncfg(out_gpon, 'gpon')
            except Exception as e:
                outputs.append(f"### GPON error: {e}")
        if self.tech in ('auto','epon'):
            try:
                out_epon = self._telnet_run(device.ip_address.strip(), user, pwd, 'show onu unauthentication', timeout=8)
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

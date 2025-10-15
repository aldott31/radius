# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
from .radius_client import RadiusClient  # ← SHTUAR

_logger = logging.getLogger(__name__)

_TRUE_SET = {'1', 'true', 'True', 'TRUE', 't', 'yes', 'y', 'on'}


def _as_bool(val, default=False):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip() in _TRUE_SET


def _as_int(val, default=0):
    try:
        return int(str(val).strip())
    except Exception:
        return default


class AsrRadiusConfig(models.Model):
    _name = 'asr.radius.config'
    _description = 'RADIUS Config (Persistent per Company)'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, ondelete='cascade'
    )

    # Vendors & Cisco naming
    emit_mikrotik   = fields.Boolean(string='Emit MikroTik VSAs', default=False)
    emit_cisco      = fields.Boolean(string='Emit Cisco VSAs', default=True)
    cisco_prefix_dl = fields.Char(string='Cisco DL Policy Prefix', default='POLICY_DL_')
    cisco_prefix_ul = fields.Char(string='Cisco UL Policy Prefix', default='POLICY_UL_')

    # FreeRADIUS connection & PPP defaults
    freeradius_host       = fields.Char(string='FreeRADIUS Host/IP')
    freeradius_auth_port  = fields.Integer(string='Auth Port', default=1812)
    freeradius_acct_port  = fields.Integer(string='Acct Port', default=1813)
    ppp_interim           = fields.Integer(string='Acct-Interim-Interval (sec)', default=300)
    ppp_idle_timeout      = fields.Integer(string='Idle-Timeout (sec)', default=600)
    one_session_per_host  = fields.Boolean(string='One Session Per Host', default=True)

    # Test-Auth (optional)
    test_radius_host      = fields.Char(string='Test RADIUS Host/IP')
    test_radius_auth_port = fields.Integer(string='Test Auth Port', default=1812)
    test_radius_secret    = fields.Char(string='Test RADIUS Secret')

    _sql_constraints = [
        ('uniq_company', 'unique(company_id)', 'Konfigurimi RADIUS ekziston një herë për çdo kompani.')
    ]

    # -------------------------
    #  Validime të thjeshta
    # -------------------------
    @api.constrains('freeradius_host', 'test_radius_host')
    def _check_hosts(self):
        for rec in self:
            for label, val in (('FreeRADIUS Host/IP', rec.freeradius_host),
                               ('Test RADIUS Host/IP', rec.test_radius_host)):
                if not val:
                    continue
                s = val.strip()
                if ':' in s:
                    raise ValidationError(_("%s nuk duhet të përmbajë port. Vendos portin te fusha përkatëse.") % label)
                if ' ' in s:
                    raise ValidationError(_("%s nuk duhet të ketë hapësira.") % label)

    # -------------------------
    #  ICP <-> Model Sync
    # -------------------------
    def _sync_to_icp(self):
        """Shkruaj të gjitha vlerat në ir.config_parameter për kompatibilitet."""
        ICP = self.env['ir.config_parameter'].sudo()
        for rec in self:
            ICP.set_param('asr_radius.emit_mikrotik', '1' if rec.emit_mikrotik else '0')
            ICP.set_param('asr_radius.emit_cisco',    '1' if rec.emit_cisco else '0')
            ICP.set_param('asr_radius.cisco_prefix_dl', (rec.cisco_prefix_dl or 'POLICY_DL_').strip())
            ICP.set_param('asr_radius.cisco_prefix_ul', (rec.cisco_prefix_ul or 'POLICY_UL_').strip())

            ICP.set_param('asr_radius.freeradius_host', (rec.freeradius_host or '').strip())
            ICP.set_param('asr_radius.freeradius_auth_port', str(rec.freeradius_auth_port or 1812))
            ICP.set_param('asr_radius.freeradius_acct_port', str(rec.freeradius_acct_port or 1813))
            ICP.set_param('asr_radius.ppp_interim', str(rec.ppp_interim or 300))
            ICP.set_param('asr_radius.ppp_idle_timeout', str(rec.ppp_idle_timeout or 600))
            ICP.set_param('asr_radius.one_session_per_host', '1' if rec.one_session_per_host else '0')

            ICP.set_param('asr_radius.test_radius_host', (rec.test_radius_host or '').strip())
            ICP.set_param('asr_radius.test_radius_auth_port', str(rec.test_radius_auth_port or 1812))
            ICP.set_param('asr_radius.test_radius_secret', rec.test_radius_secret or '')

    def _load_from_icp_if_empty(self):
        """Nëse fusha kryesore bosh, lexo nga ICP (bootstrap ose mismatch)."""
        for rec in self:
            if rec.freeradius_host:
                continue
            ICP = self.env['ir.config_parameter'].sudo()
            vals = {
                'emit_mikrotik':  _as_bool(ICP.get_param('asr_radius.emit_mikrotik', '0')),
                'emit_cisco':     _as_bool(ICP.get_param('asr_radius.emit_cisco', '1'), default=True),
                'cisco_prefix_dl': ICP.get_param('asr_radius.cisco_prefix_dl', 'POLICY_DL_'),
                'cisco_prefix_ul': ICP.get_param('asr_radius.cisco_prefix_ul', 'POLICY_UL_'),

                'freeradius_host':      (ICP.get_param('asr_radius.freeradius_host') or '').strip(),
                'freeradius_auth_port': _as_int(ICP.get_param('asr_radius.freeradius_auth_port', '1812'), 1812),
                'freeradius_acct_port': _as_int(ICP.get_param('asr_radius.freeradius_acct_port', '1813'), 1813),
                'ppp_interim':          _as_int(ICP.get_param('asr_radius.ppp_interim', '300'), 300),
                'ppp_idle_timeout':     _as_int(ICP.get_param('asr_radius.ppp_idle_timeout', '600'), 600),
                'one_session_per_host': _as_bool(ICP.get_param('asr_radius.one_session_per_host', '1'), default=True),

                'test_radius_host':      (ICP.get_param('asr_radius.test_radius_host') or '').strip(),
                'test_radius_auth_port': _as_int(ICP.get_param('asr_radius.test_radius_auth_port', '1812'), 1812),
                'test_radius_secret':    ICP.get_param('asr_radius.test_radius_secret') or '',
            }
            # shkruaj njëherësh
            rec.write(vals)

    # hook-e për sync
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._sync_to_icp()
        return recs

    def write(self, vals):
        res = super().write(vals)
        self._sync_to_icp()
        return res

    # -------------------------
    #  TEST CLIENT & WIZARD (SHTUAR)
    # -------------------------
    def _make_radius_client(self):
        self.ensure_one()
        host = (self.test_radius_host or self.freeradius_host or '').strip()
        port = self.test_radius_auth_port or self.freeradius_auth_port or 1812
        secret = (self.test_radius_secret or '').strip()
        if not host or not secret:
            raise ValidationError(_("Konfiguroni Test RADIUS Host/Secret te RADIUS Config."))
        return RadiusClient(host=host, secret=secret, auth_port=port, timeout=2.5, retries=2)

    def action_open_test_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'asr.radius.test.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }

    # -------------------------
    #  Helper: hap gjithmonë rekordin unik
    # -------------------------
    @api.model
    def action_open_config(self):
        rec = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not rec:
            rec = self.create({'company_id': self.env.company.id})
            rec._load_from_icp_if_empty()
            rec._sync_to_icp()
        else:
            # bootstrap vetëm nëse bosh
            rec._load_from_icp_if_empty()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'asr.radius.config',
            'view_mode': 'form',
            'res_id': rec.id,
            'target': 'current',
        }

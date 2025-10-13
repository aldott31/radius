# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Cisco ON, MikroTik OFF (defaults; reale mungojnë pasi param. ruhen te ir.config_parameter)
    asr_emit_mikrotik = fields.Boolean(
        string='Emit MikroTik VSAs',
        default=False,
        config_parameter='asr_radius.emit_mikrotik',
        help="If enabled, add Mikrotik-Rate-Limit etc. when syncing plans."
    )
    asr_emit_cisco = fields.Boolean(
        string='Emit Cisco VSAs',
        default=True,
        config_parameter='asr_radius.emit_cisco',
        help="If enabled, add Cisco-AVPair (policy/pool) when provided on the plan."
    )

    # Prefikse për sugjerimet e policy-ve nga Rate Limit
    asr_cisco_prefix_dl = fields.Char(
        string='Cisco DL Policy Prefix',
        default='POLICY_DL_',
        config_parameter='asr_radius.cisco_prefix_dl'
    )
    asr_cisco_prefix_ul = fields.Char(
        string='Cisco UL Policy Prefix',
        default='POLICY_UL_',
        config_parameter='asr_radius.cisco_prefix_ul'
    )

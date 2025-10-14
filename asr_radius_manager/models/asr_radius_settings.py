# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AsrRadiusSettings(models.TransientModel):
    _name = 'asr.radius.settings'
    _description = 'RADIUS Settings (Local Wizard)'

    asr_emit_mikrotik = fields.Boolean(string='Emit MikroTik VSAs')
    asr_emit_cisco    = fields.Boolean(string='Emit Cisco VSAs', default=True)
    asr_cisco_prefix_dl = fields.Char(string='Cisco DL Policy Prefix', default='POLICY_DL_')
    asr_cisco_prefix_ul = fields.Char(string='Cisco UL Policy Prefix', default='POLICY_UL_')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()
        res['asr_emit_mikrotik'] = ICP.get_param('asr_radius.emit_mikrotik', '0') in ('1','true','True')
        res['asr_emit_cisco']    = ICP.get_param('asr_radius.emit_cisco', '1') in ('1','true','True')
        res['asr_cisco_prefix_dl'] = ICP.get_param('asr_radius.cisco_prefix_dl', 'POLICY_DL_')
        res['asr_cisco_prefix_ul'] = ICP.get_param('asr_radius.cisco_prefix_ul', 'POLICY_UL_')
        return res

    def action_save(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('asr_radius.emit_mikrotik', '1' if self.asr_emit_mikrotik else '0')
        ICP.set_param('asr_radius.emit_cisco', '1' if self.asr_emit_cisco else '0')
        ICP.set_param('asr_radius.cisco_prefix_dl', self.asr_cisco_prefix_dl or 'POLICY_DL_')
        ICP.set_param('asr_radius.cisco_prefix_ul', self.asr_cisco_prefix_ul or 'POLICY_UL_')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('RADIUS Settings'), 'message': _('Saved.'), 'type': 'success'}
        }

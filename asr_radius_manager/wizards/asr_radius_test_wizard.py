# wizards/asr_radius_test_wizard.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging, socket

_logger = logging.getLogger(__name__)

class AsrRadiusTestWizard(models.TransientModel):
    _name = 'asr.radius.test.wizard'
    _description = 'RADIUS Test Wizard'

    config_id = fields.Many2one('asr.radius.config', required=True, string="Config")
    username = fields.Char(required=True, string="Username")
    password = fields.Char(required=True, string="Password")
    method = fields.Selection([('pap','PAP'), ('chap','CHAP')], default='pap', required=True, string="Method")
    result_code = fields.Char(readonly=True, string="Result Code")
    result_ok = fields.Boolean(readonly=True, string="OK")
    result_message = fields.Text(readonly=True, string="Reply-Message / Log")

    def action_run_test(self):
        self.ensure_one()
        try:
            client = self.config_id._make_radius_client()
            if self.method == 'chap':
                res = client.access_request_chap(self.username, self.password)
            else:
                res = client.access_request_pap(self.username, self.password)

            self.write({
                'result_ok': bool(res.get('ok')),
                'result_code': res.get('code'),
                'result_message': (res.get('reply_message') or '').strip(),
            })

            msg = _("Access-%s") % ("Accept" if res.get('ok') else "Reject")
            noti_type = 'success' if res.get('ok') else 'danger'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _("RADIUS Test"), 'message': msg, 'type': noti_type, 'sticky': False}
            }

        except (TimeoutError, socket.timeout) as e:
            # SHFAQ edhe detajet nga radius_client (p.sh. "src=x → dst=y:1812")
            human = _("Timeout — s'u mor përgjigje nga RADIUS. {hint}").format(
                hint=str(e) or ""
            )
            self.write({'result_ok': False, 'result_code': 'Timeout', 'result_message': human})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _("RADIUS Test"), 'message': human, 'type': 'danger', 'sticky': False}
            }

        except Exception as e:
            human = _("Gabim: %s") % (str(e) or e.__class__.__name__)
            self.write({'result_ok': False, 'result_code': 'Error', 'result_message': human})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _("RADIUS Test"), 'message': human, 'type': 'danger', 'sticky': False}
            }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

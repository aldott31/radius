# -*- coding: utf-8 -*-
from odoo import models, fields, _

class ResPartnerCRM(models.Model):
    _inherit = 'res.partner'

    work_group_id = fields.Many2one(
        'crm.work.group',
        string='Work Group',
        tracking=True,
        domain="[('manager_id', '=', uid)]",
        help="Work group assigned to this customer"
    )

    def action_assign_work_group(self):
        """Open wizard to assign customer to a work group"""
        self.ensure_one()
        return {
            'name': _('Assign to Work Group'),
            'type': 'ir.actions.act_window',
            'res_model': 'crm.assign.group.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_work_group_id': self.work_group_id.id if self.work_group_id else False,
            },
        }

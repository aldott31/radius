# -*- coding: utf-8 -*-
from odoo import models, fields, api

class CrmAssignGroupWizard(models.TransientModel):
    _name = 'crm.assign.group.wizard'
    _description = 'Assign Customer to Work Group'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        readonly=True
    )

    work_group_id = fields.Many2one(
        'crm.work.group',
        string='Work Group',
        required=True,
        domain="[('manager_id', '=', uid)]",
        help='Select the work group to assign this customer to'
    )

    def action_assign(self):
        """Assign the customer to the selected work group"""
        self.ensure_one()
        if self.partner_id and self.work_group_id:
            self.partner_id.work_group_id = self.work_group_id
        return {'type': 'ir.actions.act_window_close'}

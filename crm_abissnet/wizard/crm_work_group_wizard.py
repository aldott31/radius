# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class CrmWorkGroupWizard(models.TransientModel):
    _name = 'crm.work.group.wizard'
    _description = 'Create Work Group Wizard'

    name = fields.Char(
        string='Group Name',
        required=True,
        help='Enter the name of the work group'
    )

    technician_ids = fields.Many2many(
        'res.users',
        'work_group_wizard_technician_rel',
        'wizard_id',
        'user_id',
        string='Technicians',
        domain=lambda self: [('groups_id', 'in', self.env.ref('asr_radius_manager.group_isp_technician').id)],
        help='Select technicians to add to this group'
    )

    def action_create_group(self):
        """Create the work group with selected technicians"""
        self.ensure_one()

        # Create the work group
        work_group = self.env['crm.work.group'].create({
            'name': self.name,
            'manager_id': self.env.user.id,
            'technician_ids': [(6, 0, self.technician_ids.ids)],
        })

        # Return action to open the created work group
        return {
            'type': 'ir.actions.act_window',
            'name': 'Work Group',
            'res_model': 'crm.work.group',
            'res_id': work_group.id,
            'view_mode': 'form',
            'target': 'current',
        }

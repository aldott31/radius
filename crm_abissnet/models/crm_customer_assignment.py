# -*- coding: utf-8 -*-
from odoo import models, fields

class CrmCustomerAssignment(models.Model):
    _name = 'crm.customer.assignment'
    _description = 'Customer Work Group Assignment'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='cascade',
        index=True
    )

    work_group_id = fields.Many2one(
        'crm.work.group',
        string='Work Group',
        required=True,
        ondelete='cascade'
    )

    _sql_constraints = [
        ('partner_unique', 'unique(partner_id)', 'Each customer can only be assigned to one work group!')
    ]

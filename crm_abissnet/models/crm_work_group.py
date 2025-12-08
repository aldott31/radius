# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class CrmWorkGroup(models.Model):
    _name = 'crm.work.group'
    _description = 'Work Group for Field Technicians'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Group Name',
        required=True,
        help='Name of the work group'
    )

    address = fields.Char(
        string='Work Address',
        help='Location/address where this group operates'
    )

    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street2')
    city = fields.Char(string='City')
    zip = fields.Char(string='ZIP')

    manager_id = fields.Many2one(
        'res.users',
        string='Manager',
        default=lambda self: self.env.user,
        help='Technician Manager responsible for this group'
    )

    technician_ids = fields.Many2many(
        'res.users',
        'work_group_technician_rel',
        'group_id',
        'user_id',
        string='Technicians',
        domain=lambda self: [('groups_id', 'in', self.env.ref('asr_radius_manager.group_isp_technician').id)],
        help='Select technicians from CRM: Technician group'
    )

    technician_count = fields.Integer(
        string='Number of Technicians',
        compute='_compute_technician_count',
        store=True
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive the work group'
    )

    notes = fields.Text(
        string='Notes',
        help='Additional notes about this work group'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.depends('technician_ids')
    def _compute_technician_count(self):
        for group in self:
            group.technician_count = len(group.technician_ids)

    @api.constrains('technician_ids')
    def _check_technicians_group(self):
        """Ensure all selected users are actually Technicians"""
        technician_group = self.env.ref('asr_radius_manager.group_isp_technician')
        for group in self:
            for user in group.technician_ids:
                if technician_group not in user.groups_id:
                    raise ValidationError(_(
                        'User %s is not a member of CRM: Technician group.\n'
                        'Only users with Technician role can be added to work groups.'
                    ) % user.name)

    def name_get(self):
        result = []
        for group in self:
            name = group.name
            if group.technician_count:
                name = f"{name} ({group.technician_count} technicians)"
            result.append((group.id, name))
        return result

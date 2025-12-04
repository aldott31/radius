# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class GraceDaysWizard(models.TransientModel):
    _name = 'grace.days.wizard'
    _description = 'Add Grace Days to Customer Service'

    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        readonly=True
    )

    current_expiry = fields.Date(
        string="Current Service Expiry",
        related='partner_id.service_paid_until',
        readonly=True
    )

    current_debt_days = fields.Integer(
        string="Current Debt Days",
        related='partner_id.grace_days_debt',
        readonly=True
    )

    days_to_add = fields.Integer(
        string="Days to Add",
        required=True,
        default=3,
        help="Number of grace days to extend the service"
    )

    new_expiry = fields.Date(
        string="New Service Expiry",
        compute='_compute_new_expiry',
        help="Calculated: Current Expiry + Days to Add"
    )

    new_debt_days = fields.Integer(
        string="New Total Debt Days",
        compute='_compute_new_expiry',
        help="Calculated: Current Debt + Days to Add"
    )

    reason = fields.Text(
        string="Reason / Notes",
        help="Optional: Why are you extending this customer's service?"
    )

    @api.depends('days_to_add', 'current_expiry', 'current_debt_days')
    def _compute_new_expiry(self):
        for wizard in self:
            if wizard.current_expiry and wizard.days_to_add:
                wizard.new_expiry = wizard.current_expiry + timedelta(days=wizard.days_to_add)
                wizard.new_debt_days = wizard.current_debt_days + wizard.days_to_add
            else:
                wizard.new_expiry = False
                wizard.new_debt_days = wizard.current_debt_days

    @api.constrains('days_to_add')
    def _check_days_to_add(self):
        for wizard in self:
            if wizard.days_to_add <= 0:
                raise ValidationError(_("Days to add must be greater than 0"))
            if wizard.days_to_add > 90:
                raise ValidationError(_("Cannot add more than 90 days at once. Please contact management for approval."))

    def action_add_grace_days(self):
        """
        Add grace days to customer's service expiry and track as debt
        """
        self.ensure_one()

        if not self.partner_id.service_paid_until:
            raise UserError(_("Customer does not have a service expiry date set. Cannot add grace days."))

        # Calculate new values
        new_expiry = self.partner_id.service_paid_until + timedelta(days=self.days_to_add)
        new_debt = self.partner_id.grace_days_debt + self.days_to_add

        # Update customer
        self.partner_id.write({
            'service_paid_until': new_expiry,
            'grace_days_debt': new_debt
        })

        # Log the action
        message = _(
            "Grace Period Extended:\n"
            "• Added: %d days\n"
            "• Previous expiry: %s\n"
            "• New expiry: %s\n"
            "• Total debt days: %d"
        ) % (
            self.days_to_add,
            self.current_expiry,
            new_expiry,
            new_debt
        )

        if self.reason:
            message += _("\n• Reason: %s") % self.reason

        self.partner_id.message_post(
            body=message,
            subject=_("Grace Period Extended by Finance"),
            message_type='notification'
        )

        _logger.info(
            "Grace period added: Customer=%s, Days=%d, New Expiry=%s, Total Debt=%d",
            self.partner_id.name,
            self.days_to_add,
            new_expiry,
            new_debt
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Grace Days Added'),
                'message': _('%d days added. New expiry: %s') % (self.days_to_add, new_expiry),
                'type': 'success',
                'sticky': False,
            }
        }

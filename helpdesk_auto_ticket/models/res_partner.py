# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        """
        Override write to detect when customer_status changes to 'paid'
        and create helpdesk ticket
        """
        # Store old values before update
        old_status = {partner.id: partner.customer_status for partner in self}

        # Call parent write
        result = super(ResPartner, self).write(vals)

        # Check if customer_status changed to 'paid' AND it came from payment automation
        if ('customer_status' in vals and
            vals['customer_status'] == 'paid' and
            self.env.context.get('_from_payment_automation')):

            for partner in self:
                # Only create ticket if status actually changed to 'paid'
                if old_status.get(partner.id) == 'lead':
                    _logger.info(
                        "Creating helpdesk ticket for %s (status: lead → paid)",
                        partner.name
                    )
                    # Create ticket directly with try/except to not break payment flow
                    try:
                        partner._create_contract_ticket()
                    except Exception as e:
                        _logger.error(
                            "Failed to create ticket for %s: %s",
                            partner.name, str(e)
                        )

        return result

    def _create_contract_ticket(self):
        """
        Create a helpdesk ticket with subject "Kontrate e re"
        """
        self.ensure_one()

        # Prepare ticket values - NO team assignment, NO user assignment
        # Manager will assign manually
        ticket_vals = {
            'subject': 'Kontrate e re',
            'description': f'Kontratë e re për klientin: {self.name}\n\nCustomer Status: Lead → Paid',
            'customer_id': self.id,
            'customer_name': self.name,
            'email': self.email or '',
            'phone': self.phone or self.mobile or '',
            'priority': '2',  # Normal priority
            # team_id and user_id intentionally left empty for manual assignment
        }

        # Create the ticket - simple and direct
        ticket = self.env['ticket.helpdesk'].sudo().create(ticket_vals)

        _logger.info(
            "✅ Auto-created helpdesk ticket #%s for customer %s (ID: %s) - Status changed to 'paid'",
            ticket.name, self.name, self.id
        )

        # Post message on customer record
        self.message_post(
            body=_("Helpdesk ticket created automatically: %s") % ticket.name,
            subject=_("New Contract Ticket"),
            message_type='notification',
        )

        return ticket

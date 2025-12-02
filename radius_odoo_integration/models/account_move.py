# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Link to sale order to get subscription_months
    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Sale Orders',
        compute='_compute_sale_orders',
        store=False,
        help="Sale orders related to this invoice"
    )

    def _compute_sale_orders(self):
        """Find related sale orders from invoice lines"""
        for invoice in self:
            orders = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            invoice.sale_order_ids = orders

    def write(self, vals):
        """Override write to detect payment and update service_paid_until"""
        res = super(AccountMove, self).write(vals)

        # Check if payment_state changed to 'paid'
        if 'payment_state' in vals:
            for invoice in self:
                if invoice.payment_state in ['paid', 'in_payment'] and invoice.move_type == 'out_invoice':
                    invoice._update_partner_service_paid_until()

        return res

    def _update_partner_service_paid_until(self):
        """
        Update partner's service_paid_until when invoice is paid
        Logic:
        1. Get related sale orders
        2. Find subscription_months from sale order
        3. Calculate: service_paid_until = payment_date + subscription_months
        4. Update partner.service_paid_until
        """
        self.ensure_one()

        if not self.partner_id:
            return

        # Get payment date (invoice_date or date)
        payment_date = self.invoice_date or self.date or fields.Date.today()

        # Find related sale orders
        sale_orders = self.invoice_line_ids.mapped('sale_line_ids.order_id')

        if not sale_orders:
            _logger.debug(
                "No sale orders found for invoice %s, cannot update service_paid_until",
                self.name
            )
            return

        # Get subscription months from first RADIUS order
        radius_order = sale_orders.filtered(lambda so: so.is_radius_order)[:1]

        if not radius_order:
            _logger.debug(
                "No RADIUS orders found for invoice %s",
                self.name
            )
            return

        subscription_months = radius_order.subscription_months or 1

        # Calculate new service_paid_until
        # If partner already has service_paid_until and it's in the future, extend from that date
        # Otherwise, start from payment_date
        current_service_end = self.partner_id.service_paid_until

        if current_service_end and current_service_end > fields.Date.today():
            # Extend from current end date
            new_service_end = current_service_end + relativedelta(months=subscription_months)
        else:
            # Start from payment date
            new_service_end = payment_date + relativedelta(months=subscription_months)

        # Update partner
        self.partner_id.write({
            'service_paid_until': new_service_end,
            'contract_start_date': self.partner_id.contract_start_date or payment_date,
        })

        # Update payment statistics
        self.partner_id._update_payment_statistics()

        _logger.info(
            "Updated partner %s service_paid_until to %s (added %d months from %s)",
            self.partner_id.name,
            new_service_end,
            subscription_months,
            current_service_end or payment_date
        )

        # Post message to partner chatter
        self.partner_id.message_post(
            body=_("Service extended by %d month(s). Paid until: %s<br/>Payment: %.2f") % (
                subscription_months,
                new_service_end.strftime('%d %B, %Y'),
                self.amount_total
            ),
            subtype_xmlid='mail.mt_note'
        )

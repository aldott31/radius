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
        1. Try to get subscription_months from related sale order
        2. If no sale order, check if partner has RADIUS subscription (use default 1 month)
        3. Calculate: service_paid_until = payment_date + subscription_months
        4. Update partner.service_paid_until
        """
        self.ensure_one()

        if not self.partner_id:
            _logger.warning("Invoice %s has no partner, cannot update service_paid_until", self.name)
            return

        # Skip if partner is not a RADIUS customer
        if not self.partner_id.is_radius_customer:
            _logger.debug(
                "Partner %s is not a RADIUS customer, skipping service_paid_until update for invoice %s",
                self.partner_id.name,
                self.name
            )
            return

        # Get payment date (invoice_date or date)
        payment_date = self.invoice_date or self.date or fields.Date.today()

        # Find related sale orders
        sale_orders = self.invoice_line_ids.mapped('sale_line_ids.order_id')

        subscription_months = None

        if sale_orders:
            # Get subscription months from first RADIUS order
            radius_order = sale_orders.filtered(lambda so: so.is_radius_order)[:1]

            if radius_order:
                subscription_months = radius_order.subscription_months or 1
                _logger.info(
                    "Found RADIUS sale order %s for invoice %s with %d months",
                    radius_order.name,
                    self.name,
                    subscription_months
                )
            else:
                _logger.debug(
                    "Sale orders found for invoice %s but none are RADIUS orders: %s",
                    self.name,
                    ', '.join(sale_orders.mapped('name'))
                )
        else:
            _logger.warning(
                "No sale orders found for invoice %s (this may happen if invoice was created manually)",
                self.name
            )

        # FALLBACK: If no sale order found, check invoice lines for RADIUS products
        if subscription_months is None:
            # Check if invoice contains RADIUS service products
            radius_invoice_lines = self.invoice_line_ids.filtered(
                lambda l: l.product_id.is_radius_service if hasattr(l.product_id, 'is_radius_service') else False
            )

            if radius_invoice_lines:
                # Get quantity from first RADIUS product line (quantity = months)
                first_radius_line = radius_invoice_lines[0]
                subscription_months = max(1, int(first_radius_line.quantity))
                _logger.info(
                    "Fallback: Using quantity from invoice line for %s: %d months",
                    self.name,
                    subscription_months
                )
            else:
                # Last fallback: If partner has subscription, use 1 month default
                if self.partner_id.subscription_id:
                    subscription_months = 1
                    _logger.warning(
                        "Fallback: No RADIUS products in invoice %s, using default 1 month for partner %s",
                        self.name,
                        self.partner_id.name
                    )
                else:
                    _logger.error(
                        "Cannot determine subscription_months for invoice %s - no sale order, no RADIUS products, no partner subscription",
                        self.name
                    )
                    return

        # Calculate new service_paid_until
        # If partner already has service_paid_until and it's in the future, extend from that date
        # Otherwise, start from payment_date
        current_service_end = self.partner_id.service_paid_until

        if current_service_end and current_service_end > fields.Date.today():
            # Extend from current end date
            new_service_end = current_service_end + relativedelta(months=subscription_months)
            _logger.info(
                "Extending service from existing end date %s + %d months = %s",
                current_service_end,
                subscription_months,
                new_service_end
            )
        else:
            # Start from payment date
            new_service_end = payment_date + relativedelta(months=subscription_months)
            _logger.info(
                "Starting new service from payment date %s + %d months = %s",
                payment_date,
                subscription_months,
                new_service_end
            )

        # Update partner
        self.partner_id.write({
            'service_paid_until': new_service_end,
            'contract_start_date': self.partner_id.contract_start_date or payment_date,
        })

        # Update payment statistics
        self.partner_id._update_payment_statistics()

        _logger.info(
            "✅ Updated partner %s: service_paid_until=%s, payment_amount=%.2f",
            self.partner_id.name,
            new_service_end,
            self.amount_total
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

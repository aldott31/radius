# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import timedelta
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

    partner_has_contract = fields.Boolean(
        string="Partner Has Contract",
        compute='_compute_partner_has_contract',
        help="True if partner already has a contract"
    )

    @api.depends('partner_id')
    def _compute_partner_has_contract(self):
        """Check if partner has any contract"""
        for rec in self:
            if rec.partner_id:
                contract_count = self.env['customer.contract'].search_count([
                    ('partner_id', '=', rec.partner_id.id)
                ])
                rec.partner_has_contract = contract_count > 0
            else:
                rec.partner_has_contract = False

    @api.depends('line_ids.amount_residual')
    def _compute_payment_state(self):
        """
        Override payment_state computation to detect when invoice becomes paid
        This is the correct hook point in Odoo 18 since payment_state is a computed field
        """
        # Store old payment states BEFORE computation
        old_states = {}
        for move in self:
            old_states[move.id] = move.payment_state

        # Call parent computation
        res = super(AccountMove, self)._compute_payment_state()

        # Check if any invoice's payment state changed to paid/in_payment
        for move in self:
            old_state = old_states.get(move.id)
            new_state = move.payment_state

            # Only trigger for customer invoices that just became paid/in_payment
            if (old_state != new_state and
                new_state in ['paid', 'in_payment'] and
                move.move_type == 'out_invoice'):

                _logger.info(
                    "✅ Payment state changed for invoice %s: %s → %s, triggering service_paid_until update",
                    move.name,
                    old_state,
                    new_state
                )
                move._update_partner_service_paid_until()

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

        # ⚠️ NEW CUSTOMER WORKFLOW: Don't calculate service_paid_until until ONU is registered
        # For new customers (currently 'lead' status who will become 'paid'),
        # the service start date will be set when NOC registers the ONU
        # This prevents losing service days during installation process
        #
        # We check if current status is 'lead' because this indicates a NEW customer
        # who hasn't had their ONU registered yet.
        if self.partner_id.customer_status == 'lead':
            _logger.info(
                "⏸️  Skipping service_paid_until calculation for NEW customer %s (status: %s). "
                "Service period will start when NOC registers ONU. Customer status will be updated to 'paid'.",
                self.partner_id.name,
                self.partner_id.customer_status
            )
            # Still update status to 'paid' but don't calculate service_paid_until
            self.partner_id.with_context(_from_payment_automation=True).write({
                'customer_status': 'paid'
            })

            # Update payment statistics for new customer
            self.partner_id._update_payment_statistics()

            _logger.info(
                "✅ Updated NEW customer %s: status=paid, payment statistics updated, service_paid_until will be set when ONU registered",
                self.partner_id.name
            )

            return

        # Also skip for customers already marked as 'paid', 'for_installation', 'for_registration'
        # These are customers waiting for ONU registration
        if self.partner_id.customer_status in ['paid', 'for_installation', 'for_registration']:
            _logger.info(
                "⏸️  Skipping service_paid_until calculation for customer %s in status '%s'. "
                "Service period will start when NOC registers ONU.",
                self.partner_id.name,
                self.partner_id.customer_status
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
        # IMPORTANT: If customer has grace_days_debt, calculate from ORIGINAL expiry date
        # (not from the extended date), so grace days don't become "free days"
        current_service_end = self.partner_id.service_paid_until
        grace_days_debt = self.partner_id.grace_days_debt or 0

        # If customer has grace days debt, calculate the original expiry date
        if grace_days_debt > 0 and current_service_end:
            original_expiry = current_service_end - timedelta(days=grace_days_debt)
            _logger.info(
                "Customer has %d days of grace debt. Calculating from original expiry: %s (extended was: %s)",
                grace_days_debt,
                original_expiry,
                current_service_end
            )
            # Extend from original expiry date
            new_service_end = original_expiry + relativedelta(months=subscription_months)
            grace_cleared = True
        elif current_service_end and current_service_end > fields.Date.today():
            # Extend from current end date (no debt)
            new_service_end = current_service_end + relativedelta(months=subscription_months)
            grace_cleared = False
            _logger.info(
                "Extending service from existing end date %s + %d months = %s",
                current_service_end,
                subscription_months,
                new_service_end
            )
        else:
            # Start from payment date (service expired or no previous service)
            new_service_end = payment_date + relativedelta(months=subscription_months)
            grace_cleared = False
            _logger.info(
                "Starting new service from payment date %s + %d months = %s",
                payment_date,
                subscription_months,
                new_service_end
            )

        # Update partner
        update_vals = {
            'service_paid_until': new_service_end,
            'contract_start_date': self.partner_id.contract_start_date or payment_date,
        }

        # Clear grace days debt if customer paid
        if grace_cleared:
            update_vals['grace_days_debt'] = 0
            _logger.info("Cleared %d days of grace debt for customer %s", grace_days_debt, self.partner_id.name)

        # NOTE: For NEW customers (status='lead'), we already updated their status to 'paid'
        # at the beginning of this method before returning early.
        # This section only runs for EXISTING customers who are renewing/extending service.

        # Use context flag to allow automated updates
        _logger.info(
            "🔧 Updating partner %s | vals: %s",
            self.partner_id.name,
            update_vals
        )
        self.partner_id.write(update_vals)

        # Update payment statistics
        self.partner_id._update_payment_statistics()

        # NOTE: Auto-unsuspend removed - service activation now happens after installation
        # See workflow: Finance confirms → Installation completes → NOC registers ONU → Service activated

        _logger.info(
            "✅ Updated partner %s: service_paid_until=%s, payment_amount=%.2f",
            self.partner_id.name,
            new_service_end,
            self.amount_total
        )

        # Post message to partner chatter
        message_body = _("Service extended by %d month(s). Paid until: %s<br/>Payment: %.2f") % (
            subscription_months,
            new_service_end.strftime('%d %B, %Y'),
            self.amount_total
        )

        self.partner_id.message_post(
            body=message_body,
            subtype_xmlid='mail.mt_note'
        )

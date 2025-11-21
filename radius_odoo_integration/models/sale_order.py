# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ==================== RADIUS ORDER FLAG ====================
    is_radius_order = fields.Boolean(
        string="RADIUS Order",
        compute='_compute_is_radius_order',
        store=True,
        help="Automatically set if order contains RADIUS service products"
    )

    # ==================== RADIUS PROVISIONING STATUS ====================
    radius_provisioned = fields.Boolean(
        string="RADIUS Provisioned",
        default=False,
        copy=False,
        readonly=True,
        help="Indicates if RADIUS user has been provisioned for this order"
    )

    radius_provision_date = fields.Datetime(
        string="Provisioned On",
        readonly=True,
        copy=False
    )

    radius_provision_error = fields.Text(
        string="Provisioning Error",
        readonly=True,
        copy=False
    )

    # ==================== COMPUTED METHODS ====================
    @api.depends('order_line.product_id.is_radius_service')
    def _compute_is_radius_order(self):
        """Auto-detect if order contains RADIUS service products"""
        for rec in self:
            rec.is_radius_order = any(
                line.product_id.is_radius_service for line in rec.order_line
            )

    # ==================== RADIUS PROVISIONING ====================
    def action_provision_radius(self):
        """
        Provision RADIUS user for this sale order
        - Enable partner as RADIUS customer
        - Set subscription from order line
        - Auto-generate username/password if needed
        - Sync to FreeRADIUS MySQL
        """
        for rec in self:
            if not rec.is_radius_order:
                raise UserError(_("This is not a RADIUS order."))

            if not rec.partner_id:
                raise UserError(_("No customer selected."))

            # Get RADIUS service product from order lines
            radius_products = rec.order_line.filtered(
                lambda l: l.product_id.is_radius_service
            ).mapped('product_id')

            if not radius_products:
                raise UserError(_("No RADIUS service product found in order lines."))

            if len(radius_products) > 1:
                raise UserError(_(
                    "Multiple RADIUS service products found. Please use only one RADIUS service per order."
                ))

            radius_product = radius_products[0]

            try:
                # 1) Enable partner as RADIUS customer
                if not rec.partner_id.is_radius_customer:
                    rec.partner_id.write({'is_radius_customer': True})

                # 2) Get or create subscription from asr.subscription
                # For now, we'll link the product directly to the partner
                # In the future, you might want to create asr.subscription from product

                # Find corresponding asr.subscription based on product code
                subscription = self.env['asr.subscription'].sudo().search([
                    ('code', '=', radius_product.radius_plan_code),
                    ('company_id', '=', rec.company_id.id)
                ], limit=1)

                if not subscription:
                    # Create subscription from product if it doesn't exist
                    subscription = self.env['asr.subscription'].sudo().create({
                        'name': radius_product.name,
                        'code': radius_product.radius_plan_code,
                        'rate_limit': radius_product.radius_rate_limit,
                        'session_timeout': radius_product.radius_session_timeout,
                        'sla_level': radius_product.sla_level,
                        'ip_pool_active': radius_product.ip_pool_active,
                        'ip_pool_expired': radius_product.ip_pool_expired,
                        'acct_interim_interval': radius_product.acct_interim_interval,
                        'price': radius_product.list_price,
                        'product_id': radius_product.id,
                        'company_id': rec.company_id.id,
                    })
                    _logger.info("Created subscription %s from product %s", subscription.code, radius_product.name)

                # 3) Update partner with subscription
                rec.partner_id.write({
                    'subscription_id': subscription.id,
                })

                # 4) Auto-generate username/password if not set
                if not rec.partner_id.radius_username:
                    rec.partner_id.write({
                        'radius_username': rec.partner_id._generate_username(),
                    })

                if not rec.partner_id.radius_password:
                    rec.partner_id.write({
                        'radius_password': rec.partner_id._generate_password(),
                    })

                # 5) Sync to RADIUS MySQL
                rec.partner_id.action_sync_to_radius()

                # 6) Mark order as provisioned
                rec.write({
                    'radius_provisioned': True,
                    'radius_provision_date': fields.Datetime.now(),
                    'radius_provision_error': False,
                })

                rec.message_post(
                    body=_("RADIUS user provisioned successfully: %s") % rec.partner_id.radius_username
                )

                _logger.info(
                    "RADIUS provisioning successful for order %s: user %s",
                    rec.name,
                    rec.partner_id.radius_username
                )

            except Exception as e:
                error_msg = str(e)
                rec.write({
                    'radius_provisioned': False,
                    'radius_provision_error': error_msg,
                })
                rec.message_post(
                    body=_("RADIUS provisioning FAILED: %s") % error_msg,
                    subtype_xmlid='mail.mt_note'
                )
                _logger.exception("RADIUS provisioning failed for order %s", rec.name)
                raise UserError(_("RADIUS provisioning failed:\n%s") % error_msg)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Provisioning'),
                'message': _('RADIUS user(s) provisioned successfully'),
                'type': 'success',
                'sticky': False
            }
        }

    def action_confirm(self):
        """Override confirm to auto-provision RADIUS if enabled"""
        res = super(SaleOrder, self).action_confirm()

        # Auto-provision RADIUS for RADIUS orders (optional behavior)
        # You can enable/disable this via system parameter
        auto_provision = self.env['ir.config_parameter'].sudo().get_param(
            'radius_odoo_integration.auto_provision_on_confirm',
            'False'
        ) == 'True'

        if auto_provision:
            for order in self:
                if order.is_radius_order and not order.radius_provisioned:
                    try:
                        order.action_provision_radius()
                    except Exception as e:
                        # Log error but don't block order confirmation
                        _logger.warning(
                            "Auto-provisioning failed for order %s: %s",
                            order.name,
                            e
                        )

        return res

    def action_update_radius_subscription(self):
        """Update RADIUS subscription if order is modified (upgrade/downgrade)"""
        for rec in self:
            if not rec.is_radius_order:
                raise UserError(_("This is not a RADIUS order."))

            if not rec.partner_id.is_radius_customer:
                raise UserError(_("Customer is not a RADIUS user."))

            # Get new RADIUS service product
            radius_products = rec.order_line.filtered(
                lambda l: l.product_id.is_radius_service
            ).mapped('product_id')

            if not radius_products:
                raise UserError(_("No RADIUS service product found."))

            if len(radius_products) > 1:
                raise UserError(_("Multiple RADIUS products found."))

            radius_product = radius_products[0]

            try:
                # Find corresponding subscription
                subscription = self.env['asr.subscription'].sudo().search([
                    ('code', '=', radius_product.radius_plan_code),
                    ('company_id', '=', rec.company_id.id)
                ], limit=1)

                if not subscription:
                    raise UserError(_(
                        "Subscription '%s' not found. Please sync product to RADIUS first."
                    ) % radius_product.radius_plan_code)

                # Update partner subscription
                rec.partner_id.write({
                    'subscription_id': subscription.id,
                })

                # Re-sync to RADIUS
                rec.partner_id.action_sync_to_radius()

                rec.message_post(
                    body=_("RADIUS subscription updated to: %s") % subscription.name
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('RADIUS Update'),
                        'message': _('Subscription updated successfully'),
                        'type': 'success',
                        'sticky': False
                    }
                }

            except Exception as e:
                _logger.exception("Failed to update RADIUS subscription for order %s", rec.name)
                raise UserError(_("Failed to update subscription:\n%s") % str(e))


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_radius_service = fields.Boolean(
        string="Is RADIUS Service",
        related='product_id.is_radius_service',
        store=True,
        readonly=True
    )

    # Display RADIUS plan details in order line
    radius_plan_code = fields.Char(
        string="Plan Code",
        related='product_id.radius_plan_code',
        readonly=True
    )

    radius_rate_limit = fields.Char(
        string="Rate Limit",
        related='product_id.radius_rate_limit',
        readonly=True
    )

    sla_level = fields.Selection(
        related='product_id.sla_level',
        string="SLA",
        readonly=True
    )

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

    # ==================== RELATED FIELDS FOR DISPLAY ====================
    partner_radius_username = fields.Char(
        string="Partner RADIUS Username",
        related='partner_id.radius_username',
        readonly=True
    )

    partner_subscription_name = fields.Char(
        string="Partner Subscription",
        related='partner_id.subscription_id.name',
        readonly=True
    )

    partner_pppoe_status = fields.Selection(
        string="Partner PPPoE Status",
        related='partner_id.pppoe_status',
        readonly=True
    )

    # ==================== SUBSCRIPTION DURATION ====================
    subscription_months = fields.Integer(
        string="Subscription Duration (Months)",
        compute='_compute_subscription_months',
        store=True,
        help="Number of months the customer is paying for (computed from RADIUS product quantity)"
    )
    service_start_date = fields.Date(
        string="Service Start Date",
        default=fields.Date.today,
        help="Date when service starts"
    )
    service_end_date = fields.Date(
        string="Service Paid Until",
        compute='_compute_service_end_date',
        store=True,
        help="Calculated end date based on start date + subscription months"
    )

    # ==================== DUMMY FIELDS FOR COMPATIBILITY ====================
    # These fields are only needed when sale_pdf_quote_builder or documents modules
    # are NOT installed. If those modules are installed, they provide their own fields.
    # Since we can't dynamically check module installation at field definition time,
    # we've removed these dummy fields. If you get JS errors about missing fields,
    # it means the module IS installed and working correctly.

    # ==================== COMPUTED METHODS ====================
    @api.depends('order_line.product_id.is_radius_service')
    def _compute_is_radius_order(self):
        """Auto-detect if order contains RADIUS service products"""
        for rec in self:
            rec.is_radius_order = any(
                line.product_id.is_radius_service for line in rec.order_line
            )

    @api.depends('order_line.product_id.is_radius_service', 'order_line.product_uom_qty')
    def _compute_subscription_months(self):
        """
        Compute subscription months from RADIUS product quantity
        Logic: quantity of RADIUS product = number of months
        Example: quantity=3 means 3 months subscription
        """
        for rec in self:
            # Find RADIUS service line
            radius_line = rec.order_line.filtered(
                lambda l: l.product_id.is_radius_service
            )[:1]  # Get first RADIUS line only

            if radius_line:
                # Quantity = months (convert to int, minimum 1)
                rec.subscription_months = max(1, int(radius_line.product_uom_qty))
            else:
                # Default to 1 if no RADIUS product
                rec.subscription_months = 1

    @api.depends('service_start_date', 'subscription_months')
    def _compute_service_end_date(self):
        """Calculate service end date = start date + subscription months"""
        from dateutil.relativedelta import relativedelta
        for rec in self:
            if rec.service_start_date and rec.subscription_months > 0:
                rec.service_end_date = rec.service_start_date + relativedelta(months=rec.subscription_months)
            else:
                rec.service_end_date = False

    # ==================== ONCHANGE: AUTO-ADD SUBSCRIPTION PRODUCT ====================
    @api.onchange('partner_id')
    def _onchange_partner_id_add_subscription(self):
        """
        Auto-add subscription product to order lines when partner has subscription
        Triggered when:
        1. Partner is selected/changed in sale order
        2. Partner has a subscription_id set
        3. Order lines are empty or contain no RADIUS products
        """
        if not self.partner_id:
            return

        # Check if partner has subscription
        if not self.partner_id.subscription_id:
            return

        subscription = self.partner_id.subscription_id

        # Check if subscription has linked product
        if not subscription.product_tmpl_id:
            _logger.warning(
                "Partner %s has subscription %s but no linked product.template",
                self.partner_id.name,
                subscription.name
            )
            return

        # Get product.product from product.template (first variant)
        product = subscription.product_tmpl_id.product_variant_ids[:1]
        if not product:
            _logger.warning(
                "Subscription %s has no product variants",
                subscription.name
            )
            return

        # Check if order already has RADIUS products
        existing_radius_products = self.order_line.filtered(
            lambda l: l.product_id.is_radius_service
        )
        if existing_radius_products:
            # Don't add if RADIUS product already exists
            return

        # Add subscription product to order lines
        self.order_line = [(0, 0, {
            'product_id': product.id,
            'name': product.name,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
            'price_unit': product.list_price,
        })]

        _logger.info(
            "Auto-added subscription product %s to order for partner %s",
            product.name,
            self.partner_id.name
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
        """Override confirm to auto-provision RADIUS in SUSPENDED mode"""
        res = super(SaleOrder, self).action_confirm()

        # Auto-provision RADIUS orders in SUSPENDED mode (ALWAYS, not optional)
        for order in self:
            if order.is_radius_order and not order.radius_provisioned:
                try:
                    # 1) Enable partner as RADIUS customer
                    if not order.partner_id.is_radius_customer:
                        order.partner_id.write({'is_radius_customer': True})

                    # 2) Get RADIUS service product
                    radius_products = order.order_line.filtered(
                        lambda l: l.product_id.is_radius_service
                    ).mapped('product_id')

                    if not radius_products:
                        raise UserError(_("No RADIUS service product found in order."))

                    if len(radius_products) > 1:
                        raise UserError(_("Multiple RADIUS products found. Please use only one per order."))

                    radius_product = radius_products[0]

                    # 3) Find corresponding subscription
                    # Try direct link first (most reliable)
                    if hasattr(radius_product, 'radius_subscription_id') and radius_product.radius_subscription_id:
                        subscription = radius_product.radius_subscription_id
                    else:
                        # Fallback: search by code (case-insensitive, flexible company match)
                        plan_code = radius_product.radius_plan_code

                        # Try exact match with company first
                        subscription = self.env['asr.subscription'].sudo().search([
                            ('code', '=ilike', plan_code),
                            ('company_id', '=', order.company_id.id)
                        ], limit=1)

                        # If not found, try without company restriction (for multi-company setups)
                        if not subscription:
                            subscription = self.env['asr.subscription'].sudo().search([
                                ('code', '=ilike', plan_code)
                            ], limit=1)

                        if not subscription:
                            raise UserError(_(
                                "Subscription '%s' not found. Please sync product to RADIUS first."
                            ) % plan_code)

                    # 4) Update partner subscription
                    order.partner_id.write({
                        'subscription_id': subscription.id,
                    })

                    # 5) Generate credentials if missing
                    if not order.partner_id.radius_username or not order.partner_id.radius_password:
                        order.partner_id._generate_radius_credentials()

                    # 6) PRE-PROVISION in SUSPENDED mode (NO INTERNET YET!)
                    order.partner_id.action_sync_to_radius_suspended()

                    # 7) Update order status
                    order.write({
                        'radius_provisioned': True,
                        'radius_provision_date': fields.Datetime.now(),
                        'radius_provision_error': False,
                    })

                    # 8) Post success message
                    order.message_post(
                        body=_("RADIUS user pre-provisioned in SUSPENDED mode: %s. Service will activate automatically after payment") % order.partner_id.radius_username
                    )

                except Exception as e:
                    _logger.exception("RADIUS pre-provisioning failed for order %s", order.name)
                    order.write({
                        'radius_provisioned': False,
                        'radius_provision_error': str(e),
                    })
                    order.message_post(
                        body=_("RADIUS pre-provisioning FAILED: %s") % str(e)
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
                # Try direct link first (most reliable)
                if hasattr(radius_product, 'radius_subscription_id') and radius_product.radius_subscription_id:
                    subscription = radius_product.radius_subscription_id
                else:
                    # Fallback: search by code (case-insensitive, flexible company match)
                    plan_code = radius_product.radius_plan_code

                    # Try exact match with company first
                    subscription = self.env['asr.subscription'].sudo().search([
                        ('code', '=ilike', plan_code),
                        ('company_id', '=', rec.company_id.id)
                    ], limit=1)

                    # If not found, try without company restriction
                    if not subscription:
                        subscription = self.env['asr.subscription'].sudo().search([
                            ('code', '=ilike', plan_code)
                        ], limit=1)

                    if not subscription:
                        raise UserError(_(
                            "Subscription '%s' not found. Please sync product to RADIUS first."
                        ) % plan_code)

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

    def action_view_radius_customer(self):
        """Smart button: view provisioned RADIUS customer"""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("No customer found for this order."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('RADIUS Customer: %s') % self.partner_id.name,
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'view_id': self.env.ref('radius_odoo_integration.view_partner_form_isp_customer').id,
            'target': 'current',
        }


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

    # Dummy fields for compatibility removed - see comment in SaleOrder model above

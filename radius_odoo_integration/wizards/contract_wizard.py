# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ContractWizard(models.TransientModel):
    _name = 'contract.wizard'
    _description = 'Contract Creation Wizard'

    # ==================== TAB 1: TE DHENAT E KONTRATES ====================
    # Zgjidhni Kontaktin (pre-filled from partner)
    partner_id = fields.Many2one(
        'res.partner',
        string="Zgjidhni Kontaktin",
        required=True,
        readonly=True
    )

    # Customer info fields (auto-filled from partner)
    emri = fields.Char(string="Emri", required=True)
    datelindja = fields.Date(string="Datelindja")
    vendlindja = fields.Char(string="Vendlindja")
    adresa_1 = fields.Char(string="Adresa 1", required=True)
    lead = fields.Char(string="Lead")
    qyteti = fields.Char(string="Qyteti", required=True)
    shteti = fields.Char(string="Shteti")
    mobile_1 = fields.Char(string="Mobile 1", required=True)
    mobile_2 = fields.Char(string="Mobile 2")
    tel_fix_1 = fields.Char(string="Tel Fix 1")
    email = fields.Char(string="Email")

    # Contract type
    tipi_kontrates = fields.Selection([
        ('individ', 'Individ'),
        ('person_juridik', 'Person Juridik/Person Fizik'),
        ('institucion_publik', 'Institucion Publik'),
        ('shoqate_ong', 'Shoqate OJQ/OJF'),
        ('operator_telekomunikacioni', 'Operator Telekomunikacioni'),
    ], string="Tipi Kontrates", default='individ', required=True)

    # Registration status
    rregjitruesi = fields.Selection([
        ('perdoruesi', 'Perdoruesi'),
        ('personi_autorizuar', 'Personi Autorizuar'),
        ('kujdestari_ligjer', 'Kujdestari Ligjer'),
    ], string="Rregjitruesi", required=True)

    # ID number
    nr_serial = fields.Char(string="Nr/Serial", required=True)
    mjeti_identifikimit = fields.Selection([
        ('leternjoftim', 'Leternjoftim'),
        ('pasaporte', 'Pasaporte'),
        ('certifikate_lindja', 'Certifikate Lindје me fotografi'),
        ('certifikate_familjare', 'Certifikate familjare/Vendim Gjykate'),
        ('autorizim_prokure', 'Autorizim/Prokure'),
    ], string="Mjeti Identifikimit", required=True)

    # Business info
    emri_kompanise = fields.Char(string="Emri i Kompanise")
    nipt = fields.Char(string="NIPT")

    # Individual customer additional fields
    nr_personal = fields.Char(string="Nr. Personal")
    id_number = fields.Char(string="ID Number")

    # Business customer additional fields
    perfaqesuesi_ligjor = fields.Char(string="Përfaqësuesi Ligjor")
    nr_personal_perfaqesues = fields.Char(string="Nr. Personal i Përfaqësuesit")

    # Comments
    comment = fields.Text(string="Comment", required=True)

    # ==================== TAB 2: SHERBIMET E ZGJEDHURA ====================
    # Service selection
    internet = fields.Boolean(string="Internet", default=True)
    emri_planit_internet = fields.Char(string="Emri i Planit")

    televizion = fields.Boolean(string="Televizion")
    emri_planit_tv = fields.Char(string="Emri i Planit")

    telefoni = fields.Boolean(string="Telefoni")
    emri_planit_telefon = fields.Char(string="Emri i Planit")

    # Contract details
    data = fields.Date(string="Data", default=fields.Date.today)
    afati = fields.Selection([
        ('1', '1 muaj'),
        ('3', '3 muaj'),
        ('6', '6 muaj'),
        ('12', '12 muaj'),
        ('24', '24 muaj'),
    ], string="Afati", default='12')

    pagesa = fields.Selection([
        ('prepaid', 'Parapagim'),
        ('postpaid', 'Paspagim'),
    ], string="Pagesa", default='prepaid')

    # Service details
    qyteti_service = fields.Many2one('crm.city', string="Qyteti", required=True)
    lloji_lidhjes = fields.Selection([
        ('fiber_optike', 'Fiber -Optike'),
        ('fiber_optike_std', 'Fiber Optike'),
        ('fiber_optike_posta', 'Fiber Optike ( Posta Shqiptare)'),
        ('fiber_optike_rrethe', 'Fiber Optike Rrethë'),
        ('fiber_optike_sla2', 'Fiber Optike SLA 2 Business 2025'),
        ('fiber_optike_sla3', 'Fiber Optike SLA3'),
        ('fiber_optike_superiore', 'Fiber Optike Superiore'),
        ('fiber_optike_rrethe_alt', 'Fiber Optike( Rrethë)'),
    ], string="Lloji lidhjes", required=True)
    cmimi_lloji_lidhjes = fields.Float(string="Cmimi", digits=(16, 2))

    teknologjia_tv = fields.Char(string="Teknologjia TV", required=True)
    cmimi_teknologjia_tv = fields.Float(string="Cmimi", digits=(16, 2))

    emri_planit_service = fields.Many2one('asr.subscription', string="Emri i Planit", required=True)
    cmimi_planit = fields.Float(string="Cmimi", digits=(16, 2))

    prepaid_months = fields.Integer(string="Muaj Parapagim", readonly=True, help="Auto-filled from Sale Order quantity")

    ip_statike = fields.Selection([
        ('yes', 'Jo'),
        ('no', 'Po'),
    ], string="IP Statike", default='yes')
    cmimi_ip_statike = fields.Float(string="Cmimi", digits=(16, 2))

    # Equipment checkboxes
    me_keste_internet = fields.Boolean(string="Me Keste")
    cpe_internet_product_ids = fields.Many2many(
        'product.product',
        'contract_wizard_cpe_internet_rel',
        'wizard_id',
        'product_id',
        string="CPE Internet",
        domain="[('type', '!=', 'service')]"
    )
    cmimi_cpe_internet = fields.Float(string="Cmimi", digits=(16, 2))

    me_keste_router = fields.Boolean(string="Me Keste")
    router_wifi_product_ids = fields.Many2many(
        'product.product',
        'contract_wizard_router_wifi_rel',
        'wizard_id',
        'product_id',
        string="Router/Wifi",
        domain="[('type', '!=', 'service')]"
    )
    cmimi_router_wifi = fields.Float(string="Cmimi", digits=(16, 2))

    me_keste_tv = fields.Boolean(string="Me Keste")
    cpe_tv_product_ids = fields.Many2many(
        'product.product',
        'contract_wizard_cpe_tv_rel',
        'wizard_id',
        'product_id',
        string="CPE TV",
        domain="[('type', '!=', 'service')]"
    )
    cmimi_cpe_tv = fields.Float(string="Cmimi", digits=(16, 2))

    # Total
    cmimi_total = fields.Float(
        string="Cmimi Total",
        digits=(16, 2),
        store=True
    )
    total_muaj_paguar = fields.Float(
        string="Total Muaj Paguar",
        digits=(16, 2),
        store=True
    )


    @api.model
    def default_get(self, fields_list):
        """Auto-fill customer data from partner when wizard is created"""
        res = super(ContractWizard, self).default_get(fields_list)

        # Get partner_id from context
        partner_id = self.env.context.get('default_partner_id')
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            if partner:
                res.update({
                    'partner_id': partner.id,
                    'emri': partner.name,
                    'adresa_1': partner.street or '',
                    'qyteti': partner.city or '',
                    'shteti': partner.country_id.name if partner.country_id else '',
                    'mobile_1': partner.mobile or partner.phone or '',
                    'mobile_2': partner.phone_secondary or '',
                    'email': partner.email or '',
                    'emri_kompanise': getattr(partner, 'company_name', '') if hasattr(partner, 'company_name') else '',
                    'nipt': partner.vat or '',
                })

                # Pre-fill subscription if exists
                if partner.subscription_id:
                    res.update({
                        'emri_planit_service': partner.subscription_id.id,
                        'emri_planit_internet': partner.subscription_id.name,
                        'internet': True,
                    })
                    # Auto-fill internet price from subscription
                    if partner.subscription_id.price:
                        res['cmimi_internet'] = partner.subscription_id.price

                # Auto-fill CPE equipment from recent sale orders
                # Get most recent confirmed/done sale order for this partner
                sale_order = self.env['sale.order'].search([
                    ('partner_id', '=', partner.id),
                    ('state', 'in', ['sale', 'done'])
                ], order='date_order desc', limit=1)

                if sale_order:
                    # Get all goods (non-service) products from order lines
                    goods_products = sale_order.order_line.filtered(
                        lambda l: l.product_id and l.product_id.type != 'service'
                    ).mapped('product_id')

                    if goods_products:
                        # Auto-fill CPE Internet with all goods products
                        res['cpe_internet_product_ids'] = [(6, 0, goods_products.ids)]

                    # Get service product quantity for prepaid months
                    service_line = sale_order.order_line.filtered(
                        lambda l: l.product_id and l.product_id.type == 'service'
                    )
                    if service_line:
                        # Take the first service line quantity as prepaid months
                        quantity = int(service_line[0].product_uom_qty)
                        if quantity > 0:
                            res['prepaid_months'] = quantity

        return res

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Auto-fill customer data from partner when partner is changed manually"""
        if self.partner_id:
            self.emri = self.partner_id.name
            self.adresa_1 = self.partner_id.street or ''
            self.qyteti = self.partner_id.city or ''
            self.shteti = self.partner_id.country_id.name if self.partner_id.country_id else ''
            self.mobile_1 = self.partner_id.mobile or self.partner_id.phone or ''
            self.mobile_2 = self.partner_id.phone_secondary or ''
            self.email = self.partner_id.email or ''
            self.emri_kompanise = self.partner_id.company_name if hasattr(self.partner_id, 'company_name') else ''
            self.nipt = self.partner_id.vat or ''

            # Pre-fill subscription if exists
            if self.partner_id.subscription_id:
                self.emri_planit_service = self.partner_id.subscription_id.id
                self.emri_planit_internet = self.partner_id.subscription_id.name
                self.internet = True
                # Auto-fill internet price from subscription
                if self.partner_id.subscription_id.price:
                    self.cmimi_internet = self.partner_id.subscription_id.price

            # Auto-fill prepaid months from recent sale order
            sale_order = self.env['sale.order'].search([
                ('partner_id', '=', self.partner_id.id),
                ('state', 'in', ['sale', 'done'])
            ], order='date_order desc', limit=1)

            if sale_order:
                # Get service product quantity for prepaid months
                service_line = sale_order.order_line.filtered(
                    lambda l: l.product_id and l.product_id.type == 'service'
                )
                if service_line:
                    # Take the first service line quantity as prepaid months
                    quantity = int(service_line[0].product_uom_qty)
                    if quantity > 0:
                        self.prepaid_months = quantity

    @api.onchange('emri_planit_service')
    def _onchange_subscription(self):
        """Auto-fill service price when subscription is selected"""
        if self.emri_planit_service:
            self.emri_planit_internet = self.emri_planit_service.name
            # Try to get price from linked product first, then from subscription.price
            if self.emri_planit_service.product_tmpl_id:
                self.cmimi_planit = self.emri_planit_service.product_tmpl_id.list_price
            elif self.emri_planit_service.price:
                self.cmimi_planit = self.emri_planit_service.price

    @api.onchange('cpe_internet_product_ids')
    def _onchange_cpe_internet_products(self):
        """Auto-fill CPE Internet price from selected products"""
        if self.cpe_internet_product_ids:
            total_price = sum(product.list_price for product in self.cpe_internet_product_ids)
            self.cmimi_cpe_internet = total_price

    @api.onchange('router_wifi_product_ids')
    def _onchange_router_wifi_products(self):
        """Auto-fill Router/Wifi price from selected products"""
        if self.router_wifi_product_ids:
            total_price = sum(product.list_price for product in self.router_wifi_product_ids)
            self.cmimi_router_wifi = total_price

    @api.onchange('cpe_tv_product_ids')
    def _onchange_cpe_tv_products(self):
        """Auto-fill CPE TV price from selected products"""
        if self.cpe_tv_product_ids:
            total_price = sum(product.list_price for product in self.cpe_tv_product_ids)
            self.cmimi_cpe_tv = total_price

    @api.onchange('cmimi_lloji_lidhjes', 'cmimi_teknologjia_tv', 'cmimi_planit',
                  'cmimi_ip_statike', 'cmimi_cpe_internet', 'cmimi_router_wifi', 'cmimi_cpe_tv')
    def _onchange_cmimi_total(self):
        """Auto-calculate total price when individual prices change"""
        self.cmimi_total = (
            (self.cmimi_lloji_lidhjes or 0.0) +
            (self.cmimi_teknologjia_tv or 0.0) +
            (self.cmimi_planit or 0.0) +
            (self.cmimi_ip_statike or 0.0) +
            (self.cmimi_cpe_internet or 0.0) +
            (self.cmimi_router_wifi or 0.0) +
            (self.cmimi_cpe_tv or 0.0)
        )

    @api.onchange('cmimi_total', 'prepaid_months')
    def _onchange_total_muaj_paguar(self):
        """Auto-calculate total amount to be paid (total * months)"""
        muaj = self.prepaid_months or 0
        self.total_muaj_paguar = self.cmimi_total * muaj

    def action_create_contract(self):
        """Create customer contract and sale order from wizard data"""
        self.ensure_one()

        # Validation
        if not self.partner_id:
            raise ValidationError(_("Zgjidhni një kontakt!"))

        # Determine subscription months from afati
        subscription_months = int(self.afati) if self.afati else 1

        # Create sale order
        order_vals = {
            'partner_id': self.partner_id.id,
            'date_order': self.data or fields.Datetime.now(),
            'service_start_date': self.data or fields.Date.today(),
        }

        order = self.env['sale.order'].create(order_vals)

        # Add order lines based on selected services
        order_lines = []

        # Internet service
        if self.internet and self.emri_planit_service:
            subscription = self.emri_planit_service
            if subscription.product_tmpl_id:
                product = subscription.product_tmpl_id.product_variant_ids[:1]
                if product:
                    order_lines.append((0, 0, {
                        'product_id': product.id,
                        'name': product.name,
                        'product_uom_qty': subscription_months,  # Quantity = months
                        'product_uom': product.uom_id.id,
                        'price_unit': product.list_price,
                    }))

        if order_lines:
            order.order_line = order_lines

        # Update partner with wizard data
        partner_update_vals = {
            'name': self.emri,
            'street': self.adresa_1,
            'city': self.qyteti,
            'mobile': self.mobile_1,
            'phone': self.mobile_2 or self.tel_fix_1,
            'phone_secondary': self.mobile_2,
            'email': self.email,
        }

        if self.emri_planit_service:
            partner_update_vals['subscription_id'] = self.emri_planit_service.id

        if self.nipt:
            partner_update_vals['vat'] = self.nipt

        self.partner_id.write(partner_update_vals)

        # Create customer.contract record
        contract_vals = {
            'partner_id': self.partner_id.id,
            'data': self.data,
            'tipi_kontrates': self.tipi_kontrates,
            'afati': self.afati,
            'pagesa': self.pagesa,
            'prepaid_months': self.prepaid_months,
            'internet': self.internet,
            'emri_planit_internet': self.emri_planit_internet,
            'televizion': self.televizion,
            'emri_planit_tv': self.emri_planit_tv,
            'telefoni': self.telefoni,
            'emri_planit_telefon': self.emri_planit_telefon,
            'emri_planit_service': self.emri_planit_service.id if self.emri_planit_service else False,
            'qyteti_service': self.qyteti_service.id if self.qyteti_service else False,
            'lloji_lidhjes': self.lloji_lidhjes,
            'teknologjia_tv': self.teknologjia_tv,
            'ip_statike': self.ip_statike,
            'cpe_internet_product_ids': [(6, 0, self.cpe_internet_product_ids.ids)],
            'me_keste_internet': self.me_keste_internet,
            'router_wifi_product_ids': [(6, 0, self.router_wifi_product_ids.ids)],
            'me_keste_router': self.me_keste_router,
            'cpe_tv_product_ids': [(6, 0, self.cpe_tv_product_ids.ids)],
            'me_keste_tv': self.me_keste_tv,
            'cmimi_lloji_lidhjes': self.cmimi_lloji_lidhjes,
            'cmimi_teknologjia_tv': self.cmimi_teknologjia_tv,
            'cmimi_planit': self.cmimi_planit,
            'cmimi_ip_statike': self.cmimi_ip_statike,
            'cmimi_cpe_internet': self.cmimi_cpe_internet,
            'cmimi_router_wifi': self.cmimi_router_wifi,
            'cmimi_cpe_tv': self.cmimi_cpe_tv,
            'cmimi_total': self.cmimi_total,
            'total_muaj_paguar': self.total_muaj_paguar,
            'comment': self.comment,
            'sale_order_id': order.id,
            'state': 'confirmed',
            # Additional customer info
            'nr_personal': self.nr_personal or '',
            'id_number': self.id_number or '',
            'datelindja': self.datelindja or False,
            'vendlindja': self.vendlindja or '',
            'rregjitruesi': self.rregjitruesi or False,
            'nr_serial': self.nr_serial or '',
            'mjeti_identifikimit': self.mjeti_identifikimit or False,
            'perfaqesuesi_ligjor': self.perfaqesuesi_ligjor or '',
            'nr_personal_perfaqesues': self.nr_personal_perfaqesues or ''
        }

        contract = self.env['customer.contract'].create(contract_vals)

        # Get the form view ID
        form_view = self.env.ref('radius_odoo_integration.view_customer_contract_form', raise_if_not_found=False)

        # Return action to open the created contract
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract: %s') % self.partner_id.name,
            'res_model': 'customer.contract',
            'res_id': contract.id,
            'view_mode': 'form',
            'views': [(form_view.id if form_view else False, 'form')],
            'target': 'current',
        }
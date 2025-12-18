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
        ('monthly', 'Parapagim'),
        ('postpaid', 'Parapagim'),
    ], string="Pagesa", default='monthly')

    # Service details
    qyteti_service = fields.Many2one('crm.city', string="Qyteti")
    lloji_lidhjes = fields.Selection([
        ('fiber_optike', 'Fiber -Optike'),
        ('fiber_optike_std', 'Fiber Optike'),
        ('fiber_optike_posta', 'Fiber Optike ( Posta Shqiptare)'),
        ('fiber_optike_rrethe', 'Fiber Optike Rrethë'),
        ('fiber_optike_sla2', 'Fiber Optike SLA 2 Business 2025'),
        ('fiber_optike_sla3', 'Fiber Optike SLA3'),
        ('fiber_optike_superiore', 'Fiber Optike Superiore'),
        ('fiber_optike_rrethe_alt', 'Fiber Optike( Rrethë)'),
    ], string="Lloji lidhjes")

    teknologjia_tv = fields.Char(string="Teknologjia TV")
    emri_planit_service = fields.Many2one('asr.subscription', string="Emri i Planit")
    muaji_parapagim = fields.Selection([
        ('1', '1 muaj'),
        ('2', '2 muaj'),
        ('3', '3 muaj'),
        ('6', '6 muaj'),
        ('12', '12 muaj'),
    ], string="Muaj Parapagim")

    ip_statike = fields.Selection([
        ('yes', 'Jo'),
        ('no', 'Po'),
    ], string="IP Statike", default='yes')

    # Equipment checkboxes
    me_keste_internet = fields.Boolean(string="Me Keste")
    cpe_internet = fields.Selection([
        ('customer', 'E klientit'),
        ('company', 'E kompanise'),
    ], string="CPE Internet")

    me_keste_router = fields.Boolean(string="Me Keste")
    router_wifi = fields.Selection([
        ('customer', 'E klientit'),
        ('company', 'E kompanise'),
    ], string="Router/Wifi")

    me_keste_tv = fields.Boolean(string="Me Keste")
    cpe_tv = fields.Selection([
        ('customer', 'E klientit'),
        ('company', 'E kompanise'),
    ], string="CPE TV")

    # Pricing fields for each service row
    cmimi_internet = fields.Float(string="Cmimi Internet")
    cmimi_tv = fields.Float(string="Cmimi TV")
    cmimi_telefon = fields.Float(string="Cmimi Telefon")
    cmimi_cpe_internet = fields.Float(string="Cmimi CPE Internet")
    cmimi_router = fields.Float(string="Cmimi Router")
    cmimi_cpe_tv = fields.Float(string="Cmimi CPE TV")

    cmimi_total = fields.Float(string="Cmimi Total", compute='_compute_cmimi_total', store=True, readonly=False)
    total_muaj_paguar = fields.Float(string="Total Muaj Paguar")

    # Promo
    cmimi_promo = fields.Many2one('product.pricelist', string="Cmimi Promo")

    @api.depends('cmimi_internet', 'cmimi_tv', 'cmimi_telefon', 'cmimi_cpe_internet', 'cmimi_router', 'cmimi_cpe_tv')
    def _compute_cmimi_total(self):
        """Calculate total price from all services"""
        for rec in self:
            rec.cmimi_total = (rec.cmimi_internet or 0.0) + \
                             (rec.cmimi_tv or 0.0) + \
                             (rec.cmimi_telefon or 0.0) + \
                             (rec.cmimi_cpe_internet or 0.0) + \
                             (rec.cmimi_router or 0.0) + \
                             (rec.cmimi_cpe_tv or 0.0)

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
                    'mobile_2': getattr(partner, 'phone_secondary', '') or '',
                    'email': partner.email or '',
                    'emri_kompanise': getattr(partner, 'company_name', '') if hasattr(partner, 'company_name') else '',
                    'nipt': partner.nipt or '',
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
            self.nipt = self.partner_id.nipt or ''

            # Pre-fill subscription if exists
            if self.partner_id.subscription_id:
                self.emri_planit_service = self.partner_id.subscription_id.id
                self.emri_planit_internet = self.partner_id.subscription_id.name
                self.internet = True
                # Auto-fill internet price from subscription
                if self.partner_id.subscription_id.price:
                    self.cmimi_internet = self.partner_id.subscription_id.price

    @api.onchange('emri_planit_service')
    def _onchange_subscription(self):
        """Auto-fill service price when subscription is selected"""
        if self.emri_planit_service:
            self.emri_planit_internet = self.emri_planit_service.name
            if self.emri_planit_service.price:
                self.cmimi_internet = self.emri_planit_service.price

    def action_create_contract(self):
        """Create sale order from wizard data"""
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
            partner_update_vals['nipt'] = self.nipt

        self.partner_id.write(partner_update_vals)

        # Return action to open the created sale order
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract: %s') % self.partner_id.name,
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import qrcode
import io
import base64


class CustomerContract(models.Model):
    _name = 'customer.contract'
    _description = 'Customer Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'data desc'
    _rec_name = 'name'

    # ==================== BASIC INFO ====================
    name = fields.Char(string="Contract Reference", required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string="Customer", required=True, tracking=True)
    data = fields.Date(string="Contract Date", required=True, default=fields.Date.today, tracking=True)

    # ==================== CONTRACT DETAILS ====================
    tipi_kontrates = fields.Selection([
        ('individ', 'Individ'),
        ('person_juridik', 'Person Juridik/Person Fizik'),
        ('institucion_publik', 'Institucion Publik'),
        ('shoqate_ong', 'Shoqate OJQ/OJF'),
        ('operator_telekomunikacioni', 'Operator Telekomunikacioni'),
    ], string="Contract Type", tracking=True)

    afati = fields.Selection([
        ('1', '1 muaj'),
        ('3', '3 muaj'),
        ('6', '6 muaj'),
        ('12', '12 muaj'),
        ('24', '24 muaj'),
    ], string="Duration", tracking=True)

    pagesa = fields.Selection([
        ('prepaid', 'Parapagim'),
        ('postpaid', 'Paspagim'),
    ], string="Payment Type", tracking=True)

    # Old field - kept for backward compatibility, deprecated
    muaji_parapagim = fields.Selection([
        ('1', '1 muaj'),
        ('2', '2 muaj'),
        ('3', '3 muaj'),
        ('6', '6 muaj'),
        ('12', '12 muaj'),
    ], string="Prepaid Months (Old)", tracking=True)

    # New field - auto-filled from Sale Order quantity
    prepaid_months = fields.Integer(string="Prepaid Months", tracking=True, help="Number of months prepaid from Sale Order")

    # ==================== SERVICES ====================
    internet = fields.Boolean(string="Internet")
    emri_planit_internet = fields.Char(string="Internet Plan Name")

    televizion = fields.Boolean(string="Television")
    emri_planit_tv = fields.Char(string="TV Plan Name")

    telefoni = fields.Boolean(string="Phone")
    emri_planit_telefon = fields.Char(string="Phone Plan Name")

    emri_planit_service = fields.Many2one('asr.subscription', string="Service Plan")
    qyteti_service = fields.Many2one('crm.city', string="Service City")

    lloji_lidhjes = fields.Selection([
        ('fiber_optike', 'Fiber -Optike'),
        ('fiber_optike_std', 'Fiber Optike'),
        ('fiber_optike_posta', 'Fiber Optike ( Posta Shqiptare)'),
        ('fiber_optike_rrethe', 'Fiber Optike Rrethë'),
        ('fiber_optike_sla2', 'Fiber Optike SLA 2 Business 2025'),
        ('fiber_optike_sla3', 'Fiber Optike SLA3'),
        ('fiber_optike_superiore', 'Fiber Optike Superiore'),
        ('fiber_optike_rrethe_alt', 'Fiber Optike( Rrethë)'),
    ], string="Connection Type")

    teknologjia_tv = fields.Char(string="TV Technology")

    ip_statike = fields.Selection([
        ('yes', 'Jo'),
        ('no', 'Po'),
    ], string="Static IP")

    # ==================== EQUIPMENT ====================
    cpe_internet_product_ids = fields.Many2many(
        'product.product',
        'customer_contract_cpe_internet_rel',
        'contract_id',
        'product_id',
        string="CPE Internet"
    )
    me_keste_internet = fields.Boolean(string="Internet CPE with Installments")

    router_wifi_product_ids = fields.Many2many(
        'product.product',
        'customer_contract_router_wifi_rel',
        'contract_id',
        'product_id',
        string="Router/WiFi"
    )
    me_keste_router = fields.Boolean(string="Router with Installments")

    cpe_tv_product_ids = fields.Many2many(
        'product.product',
        'customer_contract_cpe_tv_rel',
        'contract_id',
        'product_id',
        string="CPE TV"
    )
    me_keste_tv = fields.Boolean(string="TV CPE with Installments")

    # ==================== PRICING ====================
    cmimi_lloji_lidhjes = fields.Float(string="Connection Type Price", digits=(16, 2))
    cmimi_teknologjia_tv = fields.Float(string="TV Technology Price", digits=(16, 2))
    cmimi_planit = fields.Float(string="Plan Price", digits=(16, 2))
    cmimi_ip_statike = fields.Float(string="Static IP Price", digits=(16, 2))
    cmimi_cpe_internet = fields.Float(string="CPE Internet Price", digits=(16, 2))
    cmimi_router_wifi = fields.Float(string="Router/WiFi Price", digits=(16, 2))
    cmimi_cpe_tv = fields.Float(string="CPE TV Price", digits=(16, 2))
    cmimi_total = fields.Float(string="Total Price", digits=(16, 2))
    total_muaj_paguar = fields.Float(string="Total Months Paid", digits=(16, 2))

    # ==================== CUSTOMER INFO ====================
    emri = fields.Char(string="Name", related='partner_id.name', store=True)
    adresa_1 = fields.Char(string="Address", related='partner_id.street', store=True)
    qyteti = fields.Char(string="City", related='partner_id.city', store=True)
    mobile_1 = fields.Char(string="Mobile", related='partner_id.mobile', store=True)
    email = fields.Char(string="Email", related='partner_id.email', store=True)

    # Additional customer information for contract
    nr_personal = fields.Char(string="Personal Number")
    id_number = fields.Char(string="ID Number")
    datelindja = fields.Date(string="Date of Birth")
    vendlindja = fields.Char(string="Place of Birth")
    rregjitruesi = fields.Selection([
        ('perdoruesi', 'Perdoruesi'),
        ('personi_autorizuar', 'Personi Autorizuar'),
        ('kujdestari_ligjer', 'Kujdestari Ligjer'),
    ], string="Registered By")
    nr_serial = fields.Char(string="Serial Number")
    mjeti_identifikimit = fields.Selection([
        ('leternjoftim', 'Leternjoftim'),
        ('pasaporte', 'Pasaporte'),
        ('certifikate_lindja', 'Certifikate Lindје me fotografi'),
        ('certifikate_familjare', 'Certifikate familjare/Vendim Gjykate'),
        ('autorizim_prokure', 'Autorizim/Prokure'),
    ], string="Identification Document")

    # Business/Juridical person additional fields
    perfaqesuesi_ligjor = fields.Char(string="Legal Representative")
    nr_personal_perfaqesues = fields.Char(string="Representative Personal Number")

    # ==================== LINKED SALE ORDER ====================
    sale_order_id = fields.Many2one('sale.order', string="Sale Order", readonly=True, tracking=True)
    sale_order_state = fields.Selection(related='sale_order_id.state', string="Order Status")

    # ==================== NOTES ====================
    comment = fields.Text(string="Comments")

    # ==================== STATUS ====================
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', tracking=True)

    # ==================== QR CODE ====================
    qr_code = fields.Binary(string="QR Code", compute='_compute_qr_code', store=False)

    @api.depends('name')
    def _compute_qr_code(self):
        """Generate QR code for contract with link to terms and conditions"""
        for contract in self:
            if contract.name and contract.name != 'New':
                # Generate QR code with URL to Abissnet legal info
                qr_url = "https://abissnet.al/informacioni_ligjor"

                # Create QR code with larger size
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=15,
                    border=1,
                )
                qr.add_data(qr_url)
                qr.make(fit=True)

                # Create image
                img = qr.make_image(fill_color="black", back_color="white")

                # Convert to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)

                # Encode to base64
                contract.qr_code = base64.b64encode(buffer.read())
            else:
                contract.qr_code = False

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to generate contract reference"""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('customer.contract') or 'New'
        return super(CustomerContract, self).create(vals_list)

    def action_confirm(self):
        """Confirm contract"""
        for rec in self:
            rec.state = 'confirmed'
            rec.message_post(body=_("Contract confirmed"))

    def action_activate(self):
        """Activate contract"""
        for rec in self:
            rec.state = 'active'
            rec.message_post(body=_("Contract activated"))

    def action_expire(self):
        """Expire contract"""
        for rec in self:
            rec.state = 'expired'
            rec.message_post(body=_("Contract expired"))

    def action_cancel(self):
        """Cancel contract"""
        for rec in self:
            rec.state = 'cancelled'
            rec.message_post(body=_("Contract cancelled"))

    def action_view_sale_order(self):
        """Open linked sale order"""
        self.ensure_one()
        if not self.sale_order_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_download_contract(self):
        """
        Download contract document from template

        This method generates a contract document from the DOCX template with all
        customer and service data pre-filled. If template is not available or
        docxtpl library is not installed, it falls back to PDF report.

        Returns:
            dict: Action to download the generated document
        """
        self.ensure_one()

        # Generate document using template generator
        generator = self.env['contract.template.generator']
        filename, file_content = generator.generate_contract_document(self)

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': file_content,
            'res_model': 'customer.contract',
            'res_id': self.id,
            'type': 'binary',
            'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if filename.endswith('.docx') else 'application/pdf',
        })

        # Log in chatter
        self.message_post(
            body=_("Contract document generated: %s") % filename,
            attachment_ids=[attachment.id]
        )

        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

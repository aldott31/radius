# -*- coding: utf-8 -*-
{
    'name': 'RADIUS Odoo Integration',
    'summary': 'Integrates FreeRADIUS with standard Odoo modules (Contacts, Sales, Products)',
    'version': '18.0.1.0.1',
    'category': 'Services/RADIUS',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'base',                 # res.partner
        'contacts',             # Contact management
        'sale_management',      # sale.order
        'account',              # Invoicing and payments
        'product',              # product.template/product.product
        'stock',                # Optional: for equipment tracking
        'mail',                 # Chatter
        'ab_radius_connector',  # MySQL connector
        'asr_radius_manager',   # Core RADIUS logic (will refactor dependencies)
        'crm_abissnet',         # Infrastructure models (City, POP, Access Device, Fiber Closure)
    ],
    'data': [
        # 1️⃣ SECURITY (FIRST!)
        'security/groups.xml',
        'security/security_rules.xml',
        'security/ir.model.access.csv',

        # 2️⃣ DATA
        'data/ir_sequence.xml',
        'data/product_category.xml',
        'data/ir_cron.xml',  # Cron jobs

        # 3️⃣ MENU ROOT
        'views/menu.xml',

        # 4️⃣ WIZARDS (must load before views that reference them)
        'wizards/radius_provision_wizard_views.xml',
        'wizards/grace_days_wizard_views.xml',
        'wizards/contract_wizard_views.xml',

        # 5️⃣ REPORTS (must load before views that reference them)
        'reports/customer_contract_report.xml',

        # 6️⃣ VIEWS (with actions and menu items)
        'views/res_partner_views.xml',
        'views/res_partner_contract_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/account_invoice_views.xml',
        'views/customer_contract_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
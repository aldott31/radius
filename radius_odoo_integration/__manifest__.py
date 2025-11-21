# -*- coding: utf-8 -*-
{
    'name': 'RADIUS Odoo Integration',
    'summary': 'Integrates FreeRADIUS with standard Odoo modules (Contacts, Sales, Products)',
    'version': '18.0.1.0.0',
    'category': 'Services/RADIUS',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'base',                 # res.partner
        'contacts',             # Contact management
        'sale_management',      # sale.order
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

        # 3️⃣ MENU ROOT
        'views/menu.xml',

        # 4️⃣ VIEWS (with actions and menu items)
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',

        # 5️⃣ WIZARDS
        'wizards/radius_provision_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
# -*- coding: utf-8 -*-
{
    'name': 'ASR RADIUS Manager',
    'summary': 'Manage FreeRADIUS devices, subscriptions, and user access for ISP operations',
    'version': '18.0.1.0.0',
    'category': 'Services/RADIUS',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'base',                 # res.users, res.company
        'mail',                 # chatter (mail.thread)
        'product',              # product.product link
        'sale',                 # sale.order
        'sales_team',           # sales_team.group_sale_salesman_all_leads
        'account',              # account.move, account.group_account_invoice
        'ab_radius_connector'   # DSN & MySQL connector te res.company
    ],
    'data': [
    # Security must load first: groups → rules → access rights
    'security/groups.xml',
    'security/security_rules.xml',
    'security/ir.model.access.csv',
    # Data files
    'data/ir_sequence.xml',
    'data/ir_config_parameter.xml',
    'data/ir_ui_menu_fix.xml',        # Activate Sales menu (must load AFTER sale module)
    'data/server_actions.xml',
    # Load root menu FIRST (no children)
    'views/menu.xml',
    # Load views with actions FIRST
    'views/asr_device_views.xml',
    'views/asr_subscription_views.xml',
    'views/asr_radius_status_views.xml',      # KETE E LEVIZ KETU (para asr_radius_user_views.xml)
    'views/asr_radius_user_views.xml',        # Tani mund ta referencoje action_asr_radius_pppoe_status
    'views/asr_radius_session_views.xml',
    'views/asr_radius_user_remote_views.xml',
    'views/asr_radius_config_views.xml',
    'wizards/pppoe_config_wizard_views.xml',
    'wizards/asr_radius_test_wizard_views.xml',
],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
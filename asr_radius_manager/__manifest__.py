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
    # Security views - hide/show buttons based on groups
    'views/sale_order_security_views.xml',
    # Load views with actions FIRST (in dependency order)
    'views/asr_device_views.xml',
    'views/asr_subscription_views.xml',
    'views/asr_radius_session_views.xml',     # 1st: Defines action_asr_radius_session
    'views/asr_radius_status_views.xml',      # 2nd: References action_asr_radius_session, defines action_asr_radius_pppoe_status
    'views/asr_radius_user_views.xml',        # 3rd: References action_asr_radius_pppoe_status
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
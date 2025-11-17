# -*- coding: utf-8 -*-
{
    'name': 'ASR RADIUS Manager',
    'summary': 'Manage FreeRADIUS devices, subscriptions, and user access for ISP operations',
    'version': '17.0.1.0',
    'category': 'Services/RADIUS',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'base',                 # res.users, res.company
        'mail',                 # chatter (mail.thread)
        'product',              # product.product link
        'ab_radius_connector'   # DSN & MySQL connector te res.company
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        # Load root menu first (no actions)
        'views/menu.xml',
        # Load views with actions AND their menu items
        'views/asr_device_views.xml',
        'views/asr_subscription_views.xml',
        'views/asr_radius_user_views.xml',
        'views/asr_radius_session_views.xml',
        'views/asr_radius_user_remote_views.xml',
        'views/asr_radius_config_views.xml',
        'views/asr_radius_status_views.xml',
        'data/server_actions.xml',
        'wizards/pppoe_config_wizard_views.xml',
        'wizards/asr_radius_test_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
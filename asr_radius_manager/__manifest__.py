# -*- coding: utf-8 -*-
{
    'name': 'ASR RADIUS Manager',
    'summary': 'Manage FreeRADIUS devices, subscriptions, and user access for ISP operations',
    'version': '18.0.1.0.0',
    'category': 'Services/RADIUS',
    'author': 'Abissnet',
    'website': 'https://www.abissnet.al',
    'license': 'LGPL-3',
    'depends': [
        'base',                 # res.users, res.company
        'mail',                 # chatter (mail.thread)
        'product',              # product.product link
        'ab_radius_connector'   # DSN & MySQL connector te res.company
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/asr_device_views.xml',
        'views/menu.xml',
        'views/asr_subscription_views.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

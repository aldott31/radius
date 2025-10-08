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
        'ab_radius_connector',  # Our MySQL connector module
        'base',                 # res.users, res.company
        'mail',                 # For chatter (mail.thread, mail.activity.mixin)
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Views
        'views/asr_device_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
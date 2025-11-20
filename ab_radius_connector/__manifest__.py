# -*- coding: utf-8 -*-
{
    'name': 'FreeRADIUS Connector for Odoo',
    'summary': 'Unified: MySQL connector + FreeRADIUS company settings & test',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'author': 'Abissnet',
    'website': 'https://www.abissnet.al',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/res_company_radius.xml',
    ],
    'external_dependencies': {
        'python': ['PyMySQL'],   # ← KJO
    },
    'installable': True,
    'application': False,
}

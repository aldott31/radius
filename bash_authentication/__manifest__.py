{
    'name': 'API Authentication',
    'version': '1.0.1',
    'author': 'BASH',
    'depends': ['base', 'stock', 'odoo_website_helpdesk', 'web', 'purchase'],
    'data': [
        'data/groups.xml',
        'views/res_users.xml',
        'views/res_company.xml',
        'views/res_partner.xml',
        'views/project_task_view.xml',
        'views/purchase_inherit.xml'
    ],
    'installable': True,
    'application': True,
}

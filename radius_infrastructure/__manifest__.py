# -*- coding: utf-8 -*-
{
    'name': 'RADIUS Infrastructure Management',
    'summary': 'Manage ISP infrastructure: Cities, POPs, Access Devices, Fiber Closures',
    'version': '18.0.1.0.0',
    'category': 'Services/Infrastructure',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'base',                      # res.partner, res.company
        'stock',                     # For equipment tracking (optional)
        'mail',                      # Chatter
        'web_map',                   # Map view (optional, if installed)
        'radius_odoo_integration',   # To link with res.partner (RADIUS customers)
    ],
    'data': [
        # 1️⃣ SECURITY (FIRST!)
        'security/ir.model.access.csv',

        # 2️⃣ MENU ROOT
        'views/menu.xml',

        # 3️⃣ VIEWS (with actions and menu items)
        'views/infrastructure_city_views.xml',
        'views/infrastructure_pop_views.xml',
        'views/infrastructure_access_device_views.xml',
        'views/infrastructure_fiber_closure_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

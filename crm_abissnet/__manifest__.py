# -*- coding: utf-8 -*-
{
    'name': 'Abissnet CRM',
    'summary': 'Customer relationship management for ISP operations',
    'version': '17.0.1.0.0',
    'category': 'Customer Relationship Management',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': [
        'asr_radius_manager',  # Extend radius users
    ],
    'data': [
        # 1️⃣ SECURITY (FIRST!)
        'security/groups.xml',
        'security/ir.model.access.csv',

        # 2️⃣ MENU ROOT (before submenus!)
        'views/menu.xml',

        # 3️⃣ INFRASTRUCTURE VIEWS (with menu items)
        'views/crm_city_views.xml',
        'views/crm_pop_views.xml',
        'views/crm_access_device_views.xml',
        'views/crm_fiber_closure_views.xml',

        # 4️⃣ CUSTOMERS (extends asr.radius.user) – DUHET PËRPARA wizard-in që e inherit-on
        'views/asr_radius_user_crm_views.xml',

    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

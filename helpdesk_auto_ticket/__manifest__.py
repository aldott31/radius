# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Auto Ticket on Payment',
    'version': '18.0.1.0.0',
    'category': 'Helpdesk',
    'summary': 'Automatically create helpdesk ticket when invoice is paid and customer status becomes paid',
    'description': """
        This module automatically creates a helpdesk ticket when:
        - An invoice is paid by finance
        - Customer status automatically changes to 'paid'

        The ticket is created with subject "Kontrate e re" and assigned to a default employee.
    """,
    'author': 'Custom',
    'depends': [
        'base',
        'odoo_website_helpdesk',
        'radius_odoo_integration',
    ],
    'data': [
        'data/ir_config_parameter.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}

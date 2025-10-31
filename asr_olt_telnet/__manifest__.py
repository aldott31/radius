# -*- coding: utf-8 -*-
{
    'name': 'ASR OLT Telnet Tools',
    'summary': 'Telnet to OLT and run "show mac <MAC>" (auto formats MAC as xxxx.xxxx.xxxx)',
    'version': '18.0.1.0.3',
    'category': 'Network',
    'author': 'Abissnet',
    'license': 'LGPL-3',
    'depends': ['ab_radius_connector','asr_radius_manager','crm_abissnet'],
    'data': [
        'security/ir.model.access.csv',
        'views/olt_show_mac_wizard_views.xml',
        'views/olt_onu_uncfg_wizard_views.xml',
        'views/olt_quick_register_wizard_views.xml',
        'views/asr_radius_user_inherit.xml',
        'views/crm_access_device_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False
}

{
    'name': 'Rack and Switch Inventory Management',
    'version': '1.0',
    'summary': 'Manage Racks, Switches, Ports, and SFP Modules',
    'category': 'Inventory',
    'author': 'BASH',
    'depends': ['base', 'product'],
    'data': [
        'views/switch_port_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}
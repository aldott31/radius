# -*- coding: utf-8 -*-
{
    "name": "Ministra IPTV Manager",
    "summary": "Core IPTV account and tariff management for Ministra (Stalker) platform",
    "version": "18.0.1.0.0",
    "category": "Services/IPTV",
    "author": "Abissnet",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "ab_ministra_connector",
    ],
    "data": [
        # Security
        "security/groups.xml",
        "security/ir.model.access.csv",

        # Data
        "data/ir_sequence.xml",
        "data/ir_cron.xml",

        # Views (must load BEFORE menu)
        "views/ministra_tariff_views.xml",
        "views/ministra_account_views.xml",

        # Wizards
        "wizards/ministra_provision_wizard_views.xml",

        # Menu (must be LAST - references actions from views)
        "views/menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}

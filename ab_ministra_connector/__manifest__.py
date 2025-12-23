# -*- coding: utf-8 -*-
{
    "name": "Ministra (Stalker) Connector for Odoo",
    "summary": "Company-level Ministra REST API v1 settings + connection test",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "author": "Abissnet",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/groups.xml",
        "views/res_company_ministra.xml",
    ],
    "installable": True,
    "application": False,
}

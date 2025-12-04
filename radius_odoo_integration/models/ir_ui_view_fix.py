# -*- coding: utf-8 -*-
"""
Fix for problematic views from uninstalled modules.

This module disables views that cause JavaScript errors when their
corresponding modules are not fully installed but their XML files
are loaded by Odoo.
"""
from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def disable_problematic_views(env):
    """
    Disable views that cause JavaScript errors.

    Specifically targets sale_pdf_quote_builder views that reference
    the 'customContentKanbanLikeWidget' which is not registered when
    the module is not installed.
    """
    problematic_views = [
        'sale.order.form.pdf.quote.builder',
    ]

    for view_name in problematic_views:
        views = env['ir.ui.view'].search([
            ('name', '=', view_name),
            ('active', '=', True)
        ])

        if views:
            views.write({'active': False})
            _logger.info(
                f"Disabled problematic view: {view_name} "
                f"(IDs: {views.ids}) to prevent JavaScript errors"
            )
        else:
            _logger.debug(f"View '{view_name}' not found or already disabled")

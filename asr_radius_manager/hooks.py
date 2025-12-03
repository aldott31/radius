# -*- coding: utf-8 -*-
"""
Post-install hooks for asr_radius_manager module
Automatically assigns Odoo standard groups to custom ISP groups
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Post-installation hook to link custom groups with Odoo standard groups.
    This ensures that users in custom ISP groups get proper menu access.

    Maps (Odoo 18):
    - group_isp_sales → sales_team.group_sale_salesman_all_leads (Sales menu access)
    - group_isp_finance → account.group_account_invoice (Invoicing menu access)
    - group_isp_manager → sales_team.group_sale_manager + account.group_account_manager
    """
    _logger.info("Running post_init_hook for asr_radius_manager")

    # Get custom groups
    IrModelData = env['ir.model.data']

    try:
        # Sales group - In Odoo 18, the group is sales_team.group_sale_salesman_all_leads
        group_isp_sales = env.ref('asr_radius_manager.group_isp_sales', raise_if_not_found=False)
        group_sale_user = env.ref('sales_team.group_sale_salesman_all_leads', raise_if_not_found=False)

        if group_isp_sales and group_sale_user:
            # Add sales_team.group_sale_salesman_all_leads as implied group
            if group_sale_user.id not in group_isp_sales.implied_ids.ids:
                group_isp_sales.write({
                    'implied_ids': [(4, group_sale_user.id)]
                })
                _logger.info("✅ Linked group_isp_sales → sales_team.group_sale_salesman_all_leads")
        else:
            _logger.warning("⚠️ Could not link sales groups (modules not installed?)")
    except Exception as e:
        _logger.warning(f"Could not link sales groups: {e}")

    try:
        # Finance group
        group_isp_finance = env.ref('asr_radius_manager.group_isp_finance', raise_if_not_found=False)
        group_account_invoice = env.ref('account.group_account_invoice', raise_if_not_found=False)

        if group_isp_finance and group_account_invoice:
            # Add account.group_account_invoice as implied group
            if group_account_invoice.id not in group_isp_finance.implied_ids.ids:
                group_isp_finance.write({
                    'implied_ids': [(4, group_account_invoice.id)]
                })
                _logger.info("✅ Linked group_isp_finance → account.group_account_invoice")
        else:
            _logger.warning("⚠️ Could not link finance groups (modules not installed?)")
    except Exception as e:
        _logger.warning(f"Could not link finance groups: {e}")

    try:
        # Manager group - In Odoo 18, sales manager is in sales_team module
        group_isp_manager = env.ref('asr_radius_manager.group_isp_manager', raise_if_not_found=False)
        group_sale_manager = env.ref('sales_team.group_sale_manager', raise_if_not_found=False)
        group_account_manager = env.ref('account.group_account_manager', raise_if_not_found=False)

        if group_isp_manager:
            implied_to_add = []
            if group_sale_manager and group_sale_manager.id not in group_isp_manager.implied_ids.ids:
                implied_to_add.append((4, group_sale_manager.id))
            if group_account_manager and group_account_manager.id not in group_isp_manager.implied_ids.ids:
                implied_to_add.append((4, group_account_manager.id))

            if implied_to_add:
                group_isp_manager.write({'implied_ids': implied_to_add})
                _logger.info("✅ Linked group_isp_manager → sales_team.group_sale_manager + account.group_account_manager")
        else:
            _logger.warning("⚠️ Could not link manager groups (modules not installed?)")
    except Exception as e:
        _logger.warning(f"Could not link manager groups: {e}")

    _logger.info("✅ Post-init hook completed for asr_radius_manager")

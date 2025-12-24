# -*- coding: utf-8 -*-
import logging
import secrets
import string
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MinstraProvisionWizard(models.TransientModel):
    """Wizard for manual IPTV account provisioning"""
    _name = 'ministra.provision.wizard'
    _description = 'Ministra IPTV Provision Wizard'

    # ==================== FIELDS ====================

    login = fields.Char(
        string='Login',
        required=True,
        help='IPTV login (usually same as RADIUS username)'
    )
    password = fields.Char(
        string='Password',
        help='Leave empty to auto-generate'
    )
    full_name = fields.Char(string='Full Name')
    phone = fields.Char(string='Phone')
    account_number = fields.Char(string='Account Number')

    stb_mac = fields.Char(
        string='STB MAC Address',
        help='MAC address of MAG box (optional)'
    )

    tariff_plan = fields.Many2one(
        'ministra.tariff',
        string='Tariff Plan',
        required=True,
        domain="[('company_id', '=', company_id)]"
    )

    status = fields.Selection(
        [
            ('0', 'Inactive (will be activated on payment)'),
            ('1', 'Active (immediately active)')
        ],
        string='Initial Status',
        default='0',
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    auto_sync = fields.Boolean(
        string='Auto-sync to Ministra',
        default=True,
        help='Automatically push to Ministra API after creation'
    )

    # ==================== METHODS ====================

    def _generate_password(self, length=12):
        """Generate secure random password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def action_provision(self):
        """Create IPTV account and optionally sync to Ministra"""
        self.ensure_one()

        # Auto-generate password if empty
        password = self.password or self._generate_password()

        # Check if login already exists
        existing = self.env['ministra.account'].search([
            ('company_id', '=', self.company_id.id),
            ('login', '=', self.login)
        ], limit=1)

        if existing:
            raise UserError(
                _('Account with login "%s" already exists!\n'
                  'Please use a different login.') % self.login
            )

        # Create account
        account_vals = {
            'company_id': self.company_id.id,
            'login': self.login,
            'password': password,
            'full_name': self.full_name,
            'phone': self.phone,
            'account_number': self.account_number,
            'stb_mac': self.stb_mac,
            'tariff_plan': self.tariff_plan.id,
            'status': self.status,
        }

        account = self.env['ministra.account'].create(account_vals)

        _logger.info("✅ Created IPTV account: %s (ID: %s)", self.login, account.id)

        # Auto-sync to Ministra if requested
        if self.auto_sync:
            try:
                account.action_sync_to_ministra()
            except Exception as e:
                # Don't fail the whole operation if sync fails
                _logger.warning("⚠️ Account created but sync failed: %s", str(e))
                account.message_post(
                    body=_('⚠️ Account created but sync to Ministra failed:\n%s') % str(e),
                    subtype_xmlid='mail.mt_note'
                )

        # Return action to view the created account
        return {
            'type': 'ir.actions.act_window',
            'name': _('IPTV Account'),
            'res_model': 'ministra.account',
            'res_id': account.id,
            'view_mode': 'form',
            'target': 'current',
        }

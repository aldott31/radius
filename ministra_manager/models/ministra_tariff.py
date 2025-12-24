# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MinistraTariff(models.Model):
    """Ministra IPTV Tariff Plan (synced from Ministra API)"""
    _name = 'ministra.tariff'
    _description = 'Ministra IPTV Tariff Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    # ==================== BASIC INFO ====================

    name = fields.Char(string='Tariff Name', required=True, tracking=True, index=True)
    external_id = fields.Char(
        string='External ID',
        required=True,
        index=True,
        tracking=True,
        help='Tariff ID in Ministra system (e.g., "premium_iptv")'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )

    # ==================== TARIFF DETAILS ====================

    sequence = fields.Integer(string='Sequence', default=10, help='Display order')
    active = fields.Boolean(string='Active', default=True, tracking=True)
    user_default = fields.Boolean(
        string='Default Tariff',
        default=False,
        help='Is this the default tariff plan for new users?'
    )
    days_to_expires = fields.Integer(
        string='Days to Expire',
        help='Number of days before expiration (0 = no expiration)'
    )
    description = fields.Text(string='Description')

    # ==================== SYNC INFO ====================

    ministra_synced = fields.Boolean(
        string='Synced from Ministra',
        default=False,
        readonly=True,
        help='Has this tariff been pulled from Ministra server?'
    )
    last_sync_date = fields.Datetime(string='Last Sync Date', readonly=True)
    last_sync_error = fields.Text(string='Last Sync Error', readonly=True)

    # ==================== RELATED INFO (from API) ====================

    packages_info = fields.Text(
        string='Packages Info',
        readonly=True,
        help='JSON or text representation of service packages from Ministra'
    )

    # ==================== COMPUTED FIELDS ====================

    account_count = fields.Integer(
        string='Active Accounts',
        compute='_compute_account_count',
        store=False
    )

    @api.depends('external_id')
    def _compute_account_count(self):
        """Count how many accounts use this tariff"""
        for rec in self:
            rec.account_count = self.env['ministra.account'].search_count([
                ('tariff_plan', '=', rec.id),
                ('status', '=', '1')
            ])

    # ==================== CONSTRAINTS ====================

    _sql_constraints = [
        ('external_id_company_unique', 'UNIQUE(company_id, external_id)',
         'External ID must be unique per company!'),
    ]

    # ==================== API SYNC METHODS ====================

    def action_sync_tariffs_from_ministra(self):
        """Pull all tariff plans from Ministra API and create/update in Odoo"""
        self.ensure_one()
        company = self.company_id

        try:
            # GET /tariffs
            results = company.ministra_api_call('GET', 'tariffs')

            if not results:
                raise UserError(_('No tariffs returned from Ministra API'))

            _logger.info("📥 Received %d tariff plans from Ministra", len(results))

            created_count = 0
            updated_count = 0

            for tariff_data in results:
                external_id = tariff_data.get('external_id') or tariff_data.get('id')
                name = tariff_data.get('name', 'Unknown Tariff')

                if not external_id:
                    _logger.warning("Skipping tariff without external_id: %s", tariff_data)
                    continue

                # Check if exists
                existing = self.search([
                    ('company_id', '=', company.id),
                    ('external_id', '=', external_id)
                ], limit=1)

                vals = {
                    'name': name,
                    'external_id': external_id,
                    'company_id': company.id,
                    'user_default': bool(tariff_data.get('user_default')),
                    'days_to_expires': int(tariff_data.get('days_to_expires') or 0),
                    'description': tariff_data.get('description', ''),
                    'packages_info': str(tariff_data.get('packages', '')),
                    'ministra_synced': True,
                    'last_sync_date': fields.Datetime.now(),
                    'last_sync_error': False,
                }

                if existing:
                    existing.write(vals)
                    updated_count += 1
                    _logger.info("✏️ Updated tariff: %s (external_id: %s)", name, external_id)
                else:
                    self.create(vals)
                    created_count += 1
                    _logger.info("✅ Created tariff: %s (external_id: %s)", name, external_id)

            # Success notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Tariffs Synced'),
                    'message': _('Created: %d, Updated: %d') % (created_count, updated_count),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self.write({'last_sync_error': str(e)})
            _logger.error("❌ Failed to sync tariffs: %s", str(e))
            raise

    @api.model
    def cron_sync_tariffs_from_ministra(self):
        """Cron job to sync tariffs from all companies"""
        companies = self.env['res.company'].search([
            ('ministra_api_base_url', '!=', False)
        ])

        for company in companies:
            try:
                # Find or create a dummy tariff record to call the sync method
                # (we need a record to call ensure_one() in action_sync_tariffs_from_ministra)
                tariff = self.search([('company_id', '=', company.id)], limit=1)
                if not tariff:
                    # Create a temporary tariff just to trigger sync
                    tariff = self.create({
                        'name': 'Temp',
                        'external_id': 'temp',
                        'company_id': company.id,
                    })

                tariff.action_sync_tariffs_from_ministra()

                # Delete temp if it still exists
                temp = self.search([
                    ('company_id', '=', company.id),
                    ('external_id', '=', 'temp')
                ])
                if temp:
                    temp.unlink()

            except Exception as e:
                _logger.error("❌ Cron: Failed to sync tariffs for company %s: %s",
                              company.name, str(e))

    # ==================== UI ACTIONS ====================

    def action_view_accounts(self):
        """View all accounts using this tariff"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Accounts with %s') % self.name,
            'res_model': 'ministra.account',
            'view_mode': 'list,form',
            'domain': [('tariff_plan', '=', self.id)],
            'context': {'default_tariff_plan': self.id},
        }

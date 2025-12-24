# -*- coding: utf-8 -*-
import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MinstraAccount(models.Model):
    """Ministra IPTV Account"""
    _name = 'ministra.account'
    _description = 'Ministra IPTV Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'login'
    _order = 'create_date desc, id desc'

    # ==================== BASIC INFO ====================

    name = fields.Char(
        string='Account Name',
        compute='_compute_name',
        store=True,
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        ondelete='cascade',
        tracking=True,
        index=True,
        help='Linked Odoo contact/customer'
    )

    # ==================== MINISTRA CREDENTIALS ====================

    login = fields.Char(
        string='Login',
        required=True,
        tracking=True,
        index=True,
        help='IPTV login (usually same as RADIUS username)'
    )
    password = fields.Char(
        string='Password',
        tracking=True,
        help='IPTV password (can differ from RADIUS password)'
    )
    full_name = fields.Char(string='Full Name', tracking=True)
    phone = fields.Char(string='Phone')
    account_number = fields.Char(
        string='Account Number',
        help='External billing account number'
    )

    # ==================== STB INFO ====================

    stb_mac = fields.Char(
        string='STB MAC Address',
        tracking=True,
        help='MAC address of MAG box or other STB (e.g., 00:1A:79:00:15:B3)'
    )
    stb_sn = fields.Char(string='STB Serial Number')
    stb_type = fields.Char(
        string='STB Model',
        help='e.g., MAG250, MAG322, MAG410, etc.'
    )

    # ==================== STATUS & SUBSCRIPTION ====================

    status = fields.Selection(
        [
            ('0', 'Inactive'),
            ('1', 'Active')
        ],
        string='Admin Status',
        default='1',
        required=True,
        tracking=True,
        help='Account activation status in Ministra (0=disabled, 1=enabled)'
    )

    online = fields.Selection(
        [
            ('0', 'Offline'),
            ('1', 'Online')
        ],
        string='Online Status',
        readonly=True,
        help='Current online/offline status from Ministra (read-only)'
    )

    tariff_plan = fields.Many2one(
        'ministra.tariff',
        string='Tariff Plan',
        tracking=True,
        domain="[('company_id', '=', company_id)]"
    )
    tariff_expired_date = fields.Date(string='Tariff Expiry Date', tracking=True)

    # ==================== SYNC STATUS ====================

    ministra_synced = fields.Boolean(
        string='Synced to Ministra',
        default=False,
        readonly=True,
        help='Has this account been pushed to Ministra server?'
    )
    last_sync_date = fields.Datetime(string='Last Sync Date', readonly=True)
    last_sync_error = fields.Text(string='Last Sync Error', readonly=True)

    # ==================== METADATA (from Ministra API) ====================

    ip = fields.Char(string='IP Address', readonly=True, help='Current IP from Ministra')
    version = fields.Char(string='Firmware/Portal Version', readonly=True)
    last_active = fields.Datetime(
        string='Last Active',
        readonly=True,
        help='Last activity timestamp from Ministra'
    )
    comment = fields.Text(string='Comment')

    # ==================== COMPUTED FIELDS ====================

    @api.depends('login', 'full_name')
    def _compute_name(self):
        """Display name: login (full_name)"""
        for rec in self:
            if rec.full_name:
                rec.name = f"{rec.login} ({rec.full_name})"
            else:
                rec.name = rec.login or 'New Account'

    # ==================== CONSTRAINTS ====================

    _sql_constraints = [
        ('login_company_unique', 'UNIQUE(company_id, login)',
         'Login must be unique per company!'),
    ]

    @api.constrains('stb_mac')
    def _check_stb_mac(self):
        """Validate MAC address format"""
        for rec in self:
            if rec.stb_mac:
                # Format: AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF
                mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
                if not re.match(mac_pattern, rec.stb_mac):
                    raise ValidationError(
                        _('Invalid MAC address format: %s\n'
                          'Expected format: AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF') % rec.stb_mac
                    )

    @staticmethod
    def _sanitize_login(login):
        """Remove all invisible characters and whitespace from login"""
        if not login:
            return login
        import unicodedata
        # First normalize to decomposed form
        login = unicodedata.normalize('NFKD', login)
        # Remove all non-printable and zero-width characters
        # Categories: Cc=control, Cf=format, Cs=surrogate, Co=private, Cn=unassigned
        #            Zs=space, Zl=line separator, Zp=paragraph separator
        sanitized = ''.join(
            char for char in login
            if unicodedata.category(char) not in ('Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zs', 'Zl', 'Zp')
        )
        # Also strip any remaining whitespace
        return sanitized.strip()

    @api.model_create_multi
    def create(self, vals_list):
        """Sanitize login on create"""
        for vals in vals_list:
            if 'login' in vals and vals['login']:
                vals['login'] = self._sanitize_login(vals['login'])
        return super().create(vals_list)

    def write(self, vals):
        """Sanitize login on write"""
        if 'login' in vals and vals['login']:
            vals['login'] = self._sanitize_login(vals['login'])
        return super().write(vals)

    # ==================== API SYNC METHODS ====================

    def action_sync_to_ministra(self):
        """Push account to Ministra (create or update)"""
        self.ensure_one()

        # Validate required fields
        if not self.login:
            raise UserError(_('Login is required to sync with Ministra'))

        company = self.company_id

        # Prepare API data
        data = {
            'login': self.login,
            'status': self.status,
        }

        if self.password:
            data['password'] = self.password
        if self.full_name:
            data['full_name'] = self.full_name
        if self.phone:
            data['phone'] = self.phone
        if self.account_number:
            data['account_number'] = self.account_number
        if self.stb_mac:
            data['stb_mac'] = self.stb_mac
        if self.tariff_plan and self.tariff_plan.external_id:
            data['tariff_plan'] = self.tariff_plan.external_id
        if self.comment:
            data['comment'] = self.comment

        try:
            if self.ministra_synced:
                # UPDATE existing account using USERS resource (accepts login as identifier)
                results = company.ministra_api_call('PUT', 'users', self.login, data=data)
                action_msg = 'Updated'
                _logger.info("✅ Updated Ministra account: %s", self.login)
            else:
                # CREATE new account
                results = company.ministra_api_call('POST', 'accounts', data=data)
                action_msg = 'Created'
                _logger.info("✅ Created Ministra account: %s", self.login)

            # Mark as synced
            self.write({
                'ministra_synced': True,
                'last_sync_date': fields.Datetime.now(),
                'last_sync_error': False,
            })

            # Post to chatter
            self.message_post(
                body=_('✅ %s in Ministra server successfully<br/>'
                       'Status: %s<br/>'
                       'Tariff: %s') % (
                    action_msg,
                    dict(self._fields['status'].selection)[self.status],
                    self.tariff_plan.name if self.tariff_plan else 'None'
                ),
                subtype_xmlid='mail.mt_note'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Successful'),
                    'message': _('Account %s synced to Ministra') % self.login,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            # Save error
            self.write({
                'last_sync_error': str(e),
            })
            _logger.error("❌ Failed to sync account %s: %s", self.login, str(e))
            raise

    def action_pull_from_ministra(self):
        """Pull account data from Ministra"""
        self.ensure_one()

        company = self.company_id

        try:
            # GET account data using USERS resource (accepts login as identifier)
            account_data = company.ministra_api_call('GET', 'users', self.login)

            if not account_data:
                raise UserError(_('No data returned from Ministra for login: %s') % self.login)

            # USERS resource returns a single object (not a list)

            # Map Ministra fields to Odoo
            vals = {}

            if 'full_name' in account_data:
                vals['full_name'] = account_data['full_name']
            if 'phone' in account_data:
                vals['phone'] = account_data['phone']
            if 'account_number' in account_data:
                vals['account_number'] = account_data['account_number']
            if 'status' in account_data:
                vals['status'] = str(account_data['status'])
            if 'online' in account_data:
                vals['online'] = str(account_data['online'])
            if 'stb_mac' in account_data:
                vals['stb_mac'] = account_data['stb_mac']
            if 'stb_sn' in account_data:
                vals['stb_sn'] = account_data['stb_sn']
            if 'stb_type' in account_data:
                vals['stb_type'] = account_data['stb_type']
            if 'ip' in account_data:
                vals['ip'] = account_data['ip']
            if 'version' in account_data:
                vals['version'] = account_data['version']
            if 'last_active' in account_data:
                # Ministra may return '0000-00-00 00:00:00' for empty datetime
                # Only set if it's a valid datetime value
                last_active = account_data['last_active']
                if last_active and last_active != '0000-00-00 00:00:00':
                    vals['last_active'] = last_active
                else:
                    vals['last_active'] = False

            # Update tariff if external_id matches
            if 'tariff_plan' in account_data and account_data['tariff_plan']:
                tariff = self.env['ministra.tariff'].search([
                    ('company_id', '=', company.id),
                    ('external_id', '=', account_data['tariff_plan'])
                ], limit=1)
                if tariff:
                    vals['tariff_plan'] = tariff.id

            # Update record
            self.write(vals)

            _logger.info("✅ Pulled data from Ministra for: %s", self.login)

            self.message_post(
                body=_('📥 Updated from Ministra server<br/>'
                       'Status: %s<br/>'
                       'Online: %s') % (
                    dict(self._fields['status'].selection)[self.status],
                    dict(self._fields['online'].selection)[self.online] if self.online is not False else 'Unknown'
                ),
                subtype_xmlid='mail.mt_note'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Pull Successful'),
                    'message': _('Account %s updated from Ministra') % self.login,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error("❌ Failed to pull account %s: %s", self.login, str(e))
            raise

    def action_delete_from_ministra(self):
        """Delete account from Ministra server"""
        self.ensure_one()

        company = self.company_id

        try:
            # DELETE using USERS resource (accepts login as identifier)
            company.ministra_api_call('DELETE', 'users', self.login)

            self.write({
                'ministra_synced': False,
                'last_sync_date': fields.Datetime.now(),
            })

            _logger.info("🗑️ Deleted Ministra account: %s", self.login)

            self.message_post(
                body=_('🗑️ Deleted from Ministra server'),
                subtype_xmlid='mail.mt_note'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Delete Successful'),
                    'message': _('Account %s deleted from Ministra') % self.login,
                    'type': 'warning',
                }
            }

        except Exception as e:
            _logger.error("❌ Failed to delete account %s: %s", self.login, str(e))
            raise

    # ==================== EVENT SENDING METHODS ====================

    def action_send_reboot(self):
        """Send reboot event to STB"""
        self.ensure_one()

        company = self.company_id

        try:
            company.ministra_api_call('POST', 'send_event', self.login, data={'event': 'reboot'})

            _logger.info("🔄 Sent reboot event to: %s", self.login)

            self.message_post(
                body=_('🔄 Reboot command sent to STB'),
                subtype_xmlid='mail.mt_note'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reboot Sent'),
                    'message': _('Reboot command sent to %s') % self.login,
                    'type': 'info',
                }
            }

        except Exception as e:
            _logger.error("❌ Failed to send reboot to %s: %s", self.login, str(e))
            raise

    def action_reload_portal(self):
        """Send reload portal event to STB"""
        self.ensure_one()

        company = self.company_id

        try:
            company.ministra_api_call('POST', 'send_event', self.login, data={'event': 'reload_portal'})

            _logger.info("🔄 Sent reload_portal event to: %s", self.login)

            self.message_post(
                body=_('🔄 Reload portal command sent to STB'),
                subtype_xmlid='mail.mt_note'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reload Portal Sent'),
                    'message': _('Reload portal command sent to %s') % self.login,
                    'type': 'info',
                }
            }

        except Exception as e:
            _logger.error("❌ Failed to send reload_portal to %s: %s", self.login, str(e))
            raise

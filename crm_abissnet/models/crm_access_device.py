# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class CrmAccessDevice(models.Model):
    _name = 'crm.access.device'
    _description = 'Access Device (DSLAM, OLT, Switch, etc.)'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="Device Name", required=True, tracking=True)
    code = fields.Char(string="Serial/Code", help="Device serial number or identifier")

    # Hierarchy
    pop_id = fields.Many2one('crm.pop', string="POP", required=True,
                             ondelete='restrict', tracking=True)
    city_id = fields.Many2one('crm.city', string="City",
                              related='pop_id.city_id', store=True, readonly=True)

    # Device Type
    device_type = fields.Selection([
        ('olt', 'OLT (Optical Line Terminal)'),
        ('dslam', 'DSLAM'),
        ('switch', 'Ethernet Switch'),
        ('router', 'Router'),
        ('wireless_ap', 'Wireless Access Point'),
        ('other', 'Other'),
    ], string="Device Type", required=True, default='olt', tracking=True)

    # ✅ UPDATED: Selection fields for better data quality
    manufacturer = fields.Selection([
        ('ZTE', 'ZTE'),
        ('Huawei', 'Huawei'),
        ('Cisco', 'Cisco'),
        ('Nokia', 'Nokia'),
        ('Fiberhome', 'Fiberhome'),
        ('Alcatel', 'Alcatel-Lucent'),
        ('other', 'Other'),
    ], string="Manufacturer", tracking=True, help="Select device manufacturer")

    manufacturer_other = fields.Char(string="Other Manufacturer",
                                     help="Specify if 'Other' selected",
                                     invisible="manufacturer != 'other'")

    model = fields.Selection([
        # ZTE OLT Models
        ('C220', 'ZTE C220'),
        ('C300', 'ZTE C300'),
        ('C320', 'ZTE C320'),
        ('C600', 'ZTE C600'),
        ('C650', 'ZTE C650'),
        ('C680', 'ZTE C680'),
        # Huawei OLT Models
        ('MA5800-X2', 'Huawei MA5800-X2'),
        ('MA5800-X7', 'Huawei MA5800-X7'),
        ('MA5800-X15', 'Huawei MA5800-X15'),
        ('MA5800-X17', 'Huawei MA5800-X17'),
        ('MA5600T', 'Huawei MA5600T'),
        ('MA5683T', 'Huawei MA5683T'),
        # Fiberhome
        ('AN5516-01', 'Fiberhome AN5516-01'),
        ('AN5516-04', 'Fiberhome AN5516-04'),
        # Nokia
        ('7360-ISAM-FX', 'Nokia 7360 ISAM FX'),
        # Other
        ('other', 'Other (specify below)'),
    ], string="Model", tracking=True, help="Select device model")

    model_custom = fields.Char(string="Custom Model",
                               help="Specify model if not in list",
                               invisible="model != 'other'")

    # Model display name (computed for easy reference)
    model_display = fields.Char(string="Model Name", compute='_compute_model_display', store=True)

    @api.depends('manufacturer', 'manufacturer_other', 'model', 'model_custom')
    def _compute_model_display(self):
        """Create a readable model display name"""
        for rec in self:
            parts = []

            if rec.manufacturer:
                if rec.manufacturer == 'other' and rec.manufacturer_other:
                    parts.append(rec.manufacturer_other)
                elif rec.manufacturer != 'other':
                    parts.append(rec.manufacturer)

            if rec.model:
                if rec.model == 'other' and rec.model_custom:
                    parts.append(rec.model_custom)
                elif rec.model != 'other':
                    # Extract just model name (remove manufacturer prefix if exists)
                    model_name = rec.model
                    if ' ' in model_name:
                        model_name = model_name.split(' ', 1)[1]
                    parts.append(model_name)

            rec.model_display = ' '.join(parts) if parts else ''

    ip_address = fields.Char(string="Management IP")
    mac_address = fields.Char(string="MAC Address")

    # Capacity
    port_count = fields.Integer(string="Total Ports")
    ports_used = fields.Integer(string="Ports Used", compute='_compute_port_usage', store=False)
    ports_available = fields.Integer(string="Ports Available", compute='_compute_port_usage', store=False)
    capacity_percentage = fields.Float(string="Capacity %", compute='_compute_port_usage', store=False)

    # Relations - ✅ FIX: Use compute instead of One2many
    customer_count = fields.Integer(string="Customers", compute='_compute_customer_count', store=False)

    # Link to NAS (technical)
    nas_device_id = fields.Many2one('asr.device', string="RADIUS NAS Device",
                                    help="Link to technical RADIUS NAS configuration")

    # Status
    active = fields.Boolean(default=True, tracking=True)
    operational_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('maintenance', 'Maintenance'),
        ('faulty', 'Faulty'),
    ], string="Status", default='online', tracking=True)

    # Admin
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    installation_date = fields.Date(string="Installation Date")
    notes = fields.Text(string="Notes")

    # --- Default VLANs on the OLT (allow CSV) ---
    internet_vlan = fields.Char(string="Internet VLAN(s)", tracking=True,
                                help="CSV p.sh. 1604,1614,1606")
    tv_vlan = fields.Char(string="TV VLAN(s)", tracking=True,
                          help="CSV ose një vlerë p.sh. 2020")
    voice_vlan = fields.Char(string="Voice VLAN(s)", tracking=True,
                             help="CSV ose një vlerë p.sh. 444")

    # --- Telnet Credentials (per OLT specifike) ---
    telnet_username = fields.Char(string="Telnet Username", tracking=True,
                                  help="Username për Telnet access (overrides company default)")
    telnet_password = fields.Char(string="Telnet Password", tracking=True,
                                  help="Password për Telnet access (overrides company default)")
    use_custom_credentials = fields.Boolean(string="Use Custom Credentials", default=False,
                                            tracking=True,
                                            help="Nëse True, përdor credentials nga kjo OLT në vend të company defaults")

    def _compute_customer_count(self):
        """✅ FIX: Count via search instead of One2many"""
        for rec in self:
            rec.customer_count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])

    def _compute_port_usage(self):
        """✅ FIX: Recalculate customer_count first"""
        for rec in self:
            # Get fresh count
            count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])
            rec.ports_used = count
            rec.ports_available = max(0, (rec.port_count or 0) - count)
            if rec.port_count:
                rec.capacity_percentage = (count / rec.port_count) * 100
            else:
                rec.capacity_percentage = 0

    def action_view_customers(self):
        """Smart button: view customers on this device"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customers on %s') % self.name,
            'res_model': 'asr.radius.user',
            'view_mode': 'list,form',
            'domain': [('access_device_id', '=', self.id)],
            'context': {'default_access_device_id': self.id},
        }

    @api.constrains('port_count')
    def _check_port_capacity(self):
        """✅ FIX: Warning vetëm kur ruhet (jo compute)"""
        for rec in self:
            if not rec.port_count:
                continue
            count = self.env['asr.radius.user'].search_count([
                ('access_device_id', '=', rec.id)
            ])
            if count > rec.port_count:
                raise ValidationError(
                    _('Device %s has exceeded port capacity! Used: %d, Total: %d')
                    % (rec.name, count, rec.port_count)
                )

    @api.constrains('internet_vlan', 'tv_vlan', 'voice_vlan')
    def _check_vlans_csv(self):
        import re
        for rec in self:
            for fname, label in [('internet_vlan', 'Internet VLAN(s)'),
                                 ('tv_vlan', 'TV VLAN(s)'),
                                 ('voice_vlan', 'Voice VLAN(s)')]:
                raw = (getattr(rec, fname) or '').strip()
                if not raw:
                    continue
                tokens = [t for t in re.split(r'[,\s;]+', raw) if t]
                for t in tokens:
                    if not t.isdigit():
                        raise ValidationError(_("%s: '%s' nuk është numër.") % (label, t))
                    n = int(t)
                    if n < 1 or n > 4094:
                        raise ValidationError(_("%s: VLAN %s jashtë intervalit 1–4094.") % (label, n))

    def get_telnet_credentials(self):
        """
        Kthen (username, password) për Telnet access.
        Prioriteti: OLT-specific → Company defaults
        """
        self.ensure_one()

        if self.use_custom_credentials and self.telnet_username and self.telnet_password:
            return self.telnet_username.strip(), self.telnet_password.strip()

        # Fallback to company defaults
        company = self.env.company.sudo()
        user = (getattr(company, 'olt_telnet_username', '') or '').strip()
        pwd = (getattr(company, 'olt_telnet_password', '') or '').strip()

        if not user or not pwd:
            raise UserError(_('Configure Telnet credentials on OLT form or Company settings (FreeRADIUS page).'))

        return user, pwd

    def get_command_reference(self):
        """
        Kthen një dictionary me komanda të rekomanduara bazuar në modelin e OLT
        """
        self.ensure_one()

        model = (self.model or '').upper()
        manufacturer = (self.manufacturer or '').upper()

        commands = {
            'gpon_uncfg': 'show gpon onu uncfg',
            'epon_uncfg': 'show onu unauthentication',
            'config_save': 'write',
        }

        # ZTE C600/C650 series
        if 'C600' in model or 'C650' in model or 'C680' in model:
            commands['gpon_uncfg'] = 'show pon onu uncfg'
            commands['config_save'] = 'write'

        # Huawei
        elif 'HUAWEI' in manufacturer or 'MA5800' in model or 'MA5600' in model:
            commands['gpon_uncfg'] = 'display ont autofind all'
            commands['config_save'] = 'save'
            commands['epon_uncfg'] = 'N/A (GPON only)'

        return commands

    # --- VLAN CSV -> dropdown records sync (ADDED; DOES NOT CHANGE OTHER LOGIC) ---
    def _parse_vlan_csv(self, raw):
        import re
        raw = (raw or '').strip()
        if not raw:
            return []
        tokens = [t for t in re.split(r'[,\s;]+', raw) if t]
        out = []
        seen = set()
        for t in tokens:
            if not t.isdigit():
                continue
            n = int(t)
            if 1 <= n <= 4094 and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _sync_vlan_options(self):
        Vlan = self.env["crm.access.device.vlan"]
        for rec in self:
            mapping = {
                'internet': rec.internet_vlan,
                'tv': rec.tv_vlan,
                'voice': rec.voice_vlan,
            }
            for vtype, csv in mapping.items():
                wanted = set(rec._parse_vlan_csv(csv))

                existing = Vlan.search([
                    ('device_id', '=', rec.id),
                    ('vlan_type', '=', vtype),
                ])
                existing_set = set(existing.mapped('vlan'))

                # delete removed
                existing.filtered(lambda r: r.vlan not in wanted).unlink()

                # create new
                for n in (wanted - existing_set):
                    Vlan.create({
                        'device_id': rec.id,
                        'vlan_type': vtype,
                        'vlan': n,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._sync_vlan_options()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('internet_vlan', 'tv_vlan', 'voice_vlan')):
            self._sync_vlan_options()
        return res

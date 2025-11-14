# crm_abissnet/models/crm_fiber_closure.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class CrmFiberClosure(models.Model):
    _name = 'crm.fiber.closure'
    _description = 'Fiber Splice Closure (Kaseta) with Individual Cores'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ==================== BASIC INFO ====================

    name = fields.Char(string="Closure Name", required=True, tracking=True,
                       help="e.g., KASETA-TIR-001")
    code = fields.Char(string="QR/Barcode", tracking=True,
                       help="Scan this code in the field to identify closure")

    # ==================== HIERARCHY ====================

    access_device_id = fields.Many2one('crm.access.device', string="OLT/Device",
                                       required=True, ondelete='restrict', tracking=True,
                                       help="Which OLT this closure is connected to")
    olt_port = fields.Char(string="OLT PON Port", tracking=True,
                           help="e.g., GPON 0/1/0, EPON 0/2/1")

    pop_id = fields.Many2one('crm.pop', string="POP",
                             related='access_device_id.pop_id', store=True, readonly=True)
    city_id = fields.Many2one('crm.city', string="City",
                              related='access_device_id.city_id', store=True, readonly=True)

    # ==================== LOCATION ====================

    address = fields.Text(string="Physical Address",
                          help="Where this closure is physically located")
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))

    closure_type = fields.Selection([
        ('aerial', 'Aerial (në shtyllë)'),
        ('underground', 'Underground (në kanal)'),
        ('indoor', 'Indoor (në ndërtesë)'),
        ('manhole', 'Manhole (në pusull)'),
    ], string="Installation Type", default='aerial', tracking=True)

    # ==================== CAPACITY ====================

    fiber_count = fields.Integer(string="Total Fiber Cores", default=12, required=True,
                                 help="How many cores this closure has (8, 12, 24, 48, etc.)")
    cores_used = fields.Integer(string="Cores In Use", compute='_compute_core_usage', store=True)
    cores_available = fields.Integer(string="Cores Available", compute='_compute_core_usage', store=True)
    capacity_percentage = fields.Float(string="Usage %", compute='_compute_core_usage', store=True)

    # ==================== FIBER CORES (JSON STRUCTURE) ====================

    fiber_cores_json = fields.Text(string="Fiber Cores Data", default='[]',
                                   help="JSON array of core assignments")

    fiber_cores_html = fields.Html(string="Fiber Cores", compute='_compute_fiber_cores_html', store=False)

    # ==================== STATUS ====================

    active = fields.Boolean(default=True, tracking=True)
    operational_status = fields.Selection([
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('maintenance', 'Maintenance'),
        ('faulty', 'Faulty'),
    ], string="Status", default='planned', tracking=True)

    # ==================== ADMIN ====================

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    installation_date = fields.Date(string="Installation Date")
    last_maintenance_date = fields.Date(string="Last Maintenance")
    installer_id = fields.Many2one('res.users', string="Installed By")
    notes = fields.Text(string="Notes")

    # ==================== CONSTRAINTS ====================

    _sql_constraints = [
        ('name_company_unique', 'UNIQUE(name, company_id)',
         'Closure name must be unique per company!'),
        ('code_company_unique', 'UNIQUE(code, company_id)',
         'QR/Barcode must be unique per company!'),
    ]

    @api.constrains('fiber_count')
    def _check_fiber_count(self):
        for rec in self:
            if rec.fiber_count < 1 or rec.fiber_count > 288:
                raise ValidationError(_('Fiber count must be between 1 and 288'))

    # ==================== COMPUTE METHODS ====================

    @api.depends('fiber_cores_json', 'fiber_count')
    def _compute_core_usage(self):
        import json
        for rec in self:
            try:
                cores = json.loads(rec.fiber_cores_json or '[]')
                used = sum(1 for c in cores if c.get('status') == 'in_use')
                rec.cores_used = used
                rec.cores_available = rec.fiber_count - used
                rec.capacity_percentage = (used / rec.fiber_count * 100) if rec.fiber_count else 0
            except Exception:
                rec.cores_used = 0
                rec.cores_available = rec.fiber_count
                rec.capacity_percentage = 0

    @api.depends('fiber_cores_json')
    def _compute_fiber_cores_html(self):
        import json

        COLOR_MAP = {
            'blue': '#0066CC', 'orange': '#FF6600', 'green': '#009900',
            'brown': '#663300', 'slate': '#708090', 'white': '#FFFFFF',
            'red': '#CC0000', 'black': '#000000', 'yellow': '#FFCC00',
            'violet': '#9900CC', 'rose': '#FF66CC', 'aqua': '#00CCCC',
        }

        for rec in self:
            try:
                cores = json.loads(rec.fiber_cores_json or '[]')
                if not cores:
                    rec.fiber_cores_html = '<p class="text-muted">No cores configured. Click "Initialize Cores" button.</p>'
                    continue

                html = '<table class="table table-sm table-bordered">'
                html += '<thead><tr><th>#</th><th>Color</th><th>Status</th><th>Customer</th><th>Loss (dB)</th></tr></thead><tbody>'

                for core in sorted(cores, key=lambda x: x.get('number', 0)):
                    color = core.get('color', 'white')
                    status = core.get('status', 'available')
                    customer_name = core.get('customer_name', '-')
                    loss = core.get('splice_loss_db', 0)

                    status_class = {'available': 'success', 'in_use': 'secondary', 'reserved': 'warning',
                                    'faulty': 'danger', 'cut': 'danger'}.get(status, 'secondary')
                    color_hex = COLOR_MAP.get(color, '#CCCCCC')
                    color_style = f'background-color: {color_hex}; width: 20px; height: 20px; display: inline-block; border: 1px solid #000; border-radius: 3px;'

                    html += f'<tr><td><strong>{core.get("number")}</strong></td>'
                    html += f'<td><span style="{color_style}"></span> {color.title()}</td>'
                    html += f'<td><span class="badge badge-{status_class}">{status.replace("_", " ").title()}</span></td>'
                    html += f'<td>{customer_name}</td><td>{loss:.2f}</td></tr>'

                html += '</tbody></table>'
                rec.fiber_cores_html = html
            except Exception as e:
                rec.fiber_cores_html = f'<p class="text-danger">Error rendering cores: {e}</p>'

    # ==================== ACTIONS ====================

    def action_initialize_cores(self):
        self.ensure_one()
        import json

        COLORS = ['blue', 'orange', 'green', 'brown', 'slate', 'white',
                  'red', 'black', 'yellow', 'violet', 'rose', 'aqua']

        cores = []
        for i in range(self.fiber_count):
            cores.append({
                'number': i + 1,
                'color': COLORS[i % len(COLORS)],
                'status': 'available',
                'customer_id': False,
                'customer_name': '',
                'splice_loss_db': 0.0,
                'total_loss_db': 0.0,
                'notes': '',
            })

        self.fiber_cores_json = json.dumps(cores)
        self.message_post(body=_('Initialized %d fiber cores') % self.fiber_count)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Cores Initialized'),
                       'message': _('%d cores created successfully') % self.fiber_count, 'type': 'success',
                       'sticky': False}
        }

    def action_open_map(self):
        self.ensure_one()
        if not (self.latitude and self.longitude):
            raise UserError(_('No coordinates set for this closure'))

        url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}

    def action_assign_customer_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign Customer to Fiber'),
            'res_model': 'crm.fiber.assignment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_closure_id': self.id},
        }

    def action_view_customers(self):
        self.ensure_one()
        import json

        try:
            cores = json.loads(self.fiber_cores_json or '[]')
            customer_ids = [c.get('customer_id') for c in cores if c.get('customer_id')]
        except Exception:
            customer_ids = []

        return {
            'type': 'ir.actions.act_window',
            'name': _('Customers on %s') % self.name,
            'res_model': 'asr.radius.user',
            'view_mode': 'list,form',
            'domain': [('id', 'in', customer_ids)],
        }

    def get_available_cores(self):
        self.ensure_one()
        import json
        try:
            cores = json.loads(self.fiber_cores_json or '[]')
            return [c for c in cores if c.get('status') == 'available']
        except Exception:
            return []

    def assign_core_to_customer(self, core_number, customer_id, splice_loss=0.0, notes=''):
        self.ensure_one()
        import json

        customer = self.env['asr.radius.user'].browse(customer_id)
        if not customer.exists():
            raise UserError(_('Customer not found'))

        try:
            cores = json.loads(self.fiber_cores_json or '[]')
            core = next((c for c in cores if c.get('number') == core_number), None)
            if not core:
                raise UserError(_('Core #%d not found') % core_number)
            if core.get('status') != 'available':
                raise UserError(_('Core #%d is not available (status: %s)') % (core_number, core.get('status')))

            core['status'] = 'in_use'
            core['customer_id'] = customer.id
            core['customer_name'] = customer.name or customer.username
            core['splice_loss_db'] = splice_loss
            core['notes'] = notes

            self.fiber_cores_json = json.dumps(cores)

            customer.write({
                'fiber_closure_id': self.id,
                'fiber_core_number': core_number,
                'fiber_color': core.get('color'),
            })

            self.message_post(body=_('Assigned Core #%(num)d (%(col)s) to customer %(cust)s') % {'num': core_number,
                                                                                                 'col': core.get(
                                                                                                     'color'),
                                                                                                 'cust': customer.name or customer.username})
            customer.message_post(
                body=_('Assigned to Fiber Closure %(closure)s, Core #%(num)d (%(col)s)') % {'closure': self.name,
                                                                                            'num': core_number,
                                                                                            'col': core.get('color')})

            return True
        except json.JSONDecodeError:
            raise UserError(_('Fiber cores data is corrupted'))

    def release_core(self, core_number):
        self.ensure_one()
        import json

        try:
            cores = json.loads(self.fiber_cores_json or '[]')
            core = next((c for c in cores if c.get('number') == core_number), None)
            if not core:
                raise UserError(_('Core #%d not found') % core_number)

            customer_name = core.get('customer_name', 'Unknown')
            customer_id = core.get('customer_id')

            core['status'] = 'available'
            core['customer_id'] = False
            core['customer_name'] = ''
            core['notes'] = ''

            self.fiber_cores_json = json.dumps(cores)

            if customer_id:
                customer = self.env['asr.radius.user'].browse(customer_id)
                if customer.exists():
                    customer.write({'fiber_closure_id': False, 'fiber_core_number': False, 'fiber_color': False})

            self.message_post(
                body=_('Released Core #%(num)d from %(cust)s') % {'num': core_number, 'cust': customer_name})
            return True
        except json.JSONDecodeError:
            raise UserError(_('Fiber cores data is corrupted'))


# ==================== EXTEND USER MODEL ====================

class AsrRadiusUserFiber(models.Model):
    _inherit = 'asr.radius.user'

    fiber_closure_id = fields.Many2one('crm.fiber.closure', string='Fiber Closure', tracking=True)
    fiber_core_number = fields.Integer(string='Fiber Core #', tracking=True)
    fiber_color = fields.Selection([
        ('blue', 'Blue'), ('orange', 'Orange'), ('green', 'Green'),
        ('brown', 'Brown'), ('slate', 'Slate'), ('white', 'White'),
        ('red', 'Red'), ('black', 'Black'), ('yellow', 'Yellow'),
        ('violet', 'Violet'), ('rose', 'Rose'), ('aqua', 'Aqua'),
    ], string='Fiber Color', tracking=True)

    ont_serial = fields.Char(string='ONT Serial Number', tracking=True)
    olt_pon_port = fields.Char(string='PON Port', tracking=True)
    olt_ont_id = fields.Char(string='ONT ID', tracking=True)

    fiber_splice_loss_db = fields.Float(string='Splice Loss (dB)', digits=(4, 2))
    fiber_total_loss_db = fields.Float(string='Total Loss (dB)', digits=(4, 2))

    def action_delete_onu(self):
        """Delete registered ONU from OLT via telnet"""
        self.ensure_one()

        if not self.olt_pon_port:
            raise UserError(_('No ONU registered for this customer (olt_pon_port is empty).'))

        if not self.access_device_id:
            raise UserError(_('No OLT assigned to this customer.'))

        if not self.access_device_id.ip_address:
            raise UserError(_('OLT has no IP address configured.'))

        # Parse olt_pon_port: "gpon-olt_1/2/15:1" → interface: gpon-olt_1/2/15, slot: 1
        import re
        match = re.match(r'^(.+?):(\d+)$', self.olt_pon_port.strip())
        if not match:
            raise UserError(_('Invalid olt_pon_port format: %s. Expected format: gpon-olt_X/Y/Z:slot') % self.olt_pon_port)

        interface = match.group(1)  # gpon-olt_1/2/15
        slot = match.group(2)  # 1

        # Detect OLT model and convert interface format if needed
        model = (self.access_device_id.model or '').upper()
        if 'C600' in model or 'C650' in model or 'C680' in model:
            # C600 format: gpon_olt-1/2/15 (underscore-dash)
            interface_for_cmd = interface.replace('-olt_', '_olt-')
        else:
            # C300 format: gpon-olt_1/2/15 (dash-underscore) - no change
            interface_for_cmd = interface

        # Get telnet credentials
        user, pwd = self.access_device_id.get_telnet_credentials()

        # Build delete command
        delete_cmd = f"conf t;interface {interface_for_cmd};no onu {slot};exit;exit"

        # Execute via telnet
        import telnetlib
        import time
        olt_ip = self.access_device_id.ip_address.strip()

        try:
            tn = telnetlib.Telnet(olt_ip, 23, timeout=12)
        except Exception as e:
            raise UserError(_('Telnet connection failed to %s: %s') % (olt_ip, str(e)))

        try:
            # Login
            idx, _, _ = tn.expect([b'Username:', b'Login:', b'login:'], 12)
            if idx == -1:
                raise UserError(_('Did not receive Username prompt from %s') % olt_ip)
            tn.write((user + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.3)

            idx, _, _ = tn.expect([b'Password:', b'password:'], 12)
            if idx == -1:
                raise UserError(_('Did not receive Password prompt from %s') % olt_ip)
            tn.write((pwd + '\n').encode('ascii', errors='ignore'))
            time.sleep(0.6)

            idx, _, text = tn.expect([
                b'>', b'#', b'$',
                b'Username:',
                b'Authentication failed',
                b'Login incorrect',
                b'Access denied'
            ], 12)
            if idx >= 3 or idx == -1:
                raise UserError(_('Authentication FAILED for %s@%s') % (user, olt_ip))

            # Execute delete commands
            commands = [c.strip() for c in delete_cmd.split(';') if c.strip()]
            for cmd in commands:
                tn.write((cmd + '\n').encode('ascii', errors='ignore'))
                time.sleep(0.35)

            # Exit
            try:
                tn.write(b'exit\n'); time.sleep(0.2)
                tn.write(b'quit\n')
            except Exception:
                pass
        finally:
            try:
                tn.close()
            except Exception:
                pass

        # Clear ONU fields
        self.write({
            'ont_serial': False,
            'olt_pon_port': False,
            'olt_ont_id': False,
        })

        # Log to chatter
        try:
            self.message_post(
                body=_('🗑️ ONU Deleted from OLT:<br/>'
                       '• Interface: %(iface)s<br/>'
                       '• Slot: %(slot)s<br/>'
                       '• Command: <code>no onu %(slot)s</code>') % {
                    'iface': interface_for_cmd,
                    'slot': slot
                },
                subtype_xmlid='mail.mt_note'
            )
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ ONU Deleted Successfully'),
                'message': _('ONU removed from %(iface)s:%(slot)s') % {
                    'iface': interface_for_cmd,
                    'slot': slot
                },
                'type': 'success',
                'sticky': False
            }
        }

    def action_open_closure(self):
        self.ensure_one()
        if not self.fiber_closure_id:
            raise UserError(_('No fiber closure assigned'))
        return {'type': 'ir.actions.act_window', 'name': _('Fiber Closure'), 'res_model': 'crm.fiber.closure',
                'res_id': self.fiber_closure_id.id, 'view_mode': 'form', 'target': 'current'}

    def action_release_fiber(self):
        self.ensure_one()
        if not self.fiber_closure_id or not self.fiber_core_number:
            raise UserError(_('No fiber core assigned'))
        self.fiber_closure_id.release_core(self.fiber_core_number)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Fiber Released'),
                                                                                       'message': _(
                                                                                           'Core #%d has been released') % self.fiber_core_number,
                                                                                       'type': 'success',
                                                                                       'sticky': False}}


# ==================== ASSIGNMENT WIZARD ====================

class CrmFiberAssignmentWizard(models.TransientModel):
    _name = 'crm.fiber.assignment.wizard'
    _description = 'Assign Customer to Fiber Core'

    closure_id = fields.Many2one('crm.fiber.closure', string='Closure', required=True)
    available_cores_html = fields.Html(string='Available Cores', compute='_compute_available_cores')
    core_number = fields.Integer(string='Core Number', required=True)
    customer_id = fields.Many2one('asr.radius.user', string='Customer', required=True,
                                  domain=[('fiber_closure_id', '=', False)])
    splice_loss_db = fields.Float(string='Splice Loss (dB)', digits=(4, 2), default=0.5)
    notes = fields.Text(string='Installation Notes')

    @api.depends('closure_id')
    def _compute_available_cores(self):
        import json
        for rec in self:
            if not rec.closure_id:
                rec.available_cores_html = '<p>Select a closure first</p>'
                continue
            available = rec.closure_id.get_available_cores()
            if not available:
                rec.available_cores_html = '<p class="text-warning">No cores available in this closure!</p>'
                continue
            html = '<ul class="list-unstyled">'
            for core in available:
                html += f'<li><span class="badge badge-success">Core #{core.get("number")}</span> <strong>{core.get("color", "").title()}</strong></li>'
            html += '</ul>'
            rec.available_cores_html = html

    def action_assign(self):
        self.ensure_one()
        self.closure_id.assign_core_to_customer(core_number=self.core_number, customer_id=self.customer_id.id,
                                                splice_loss=self.splice_loss_db, notes=self.notes or '')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Assignment Complete'),
                           'message': _('Customer %(cust)s assigned to Core #%(num)d') % {
                               'cust': self.customer_id.name or self.customer_id.username, 'num': self.core_number},
                           'type': 'success', 'sticky': False}}

# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AsrDevice(models.Model):
    _name = 'asr.device'
    _description = 'RADIUS Network Device (NAS)'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'name'
    _check_company_auto = True  # izolim auto për multi-company

    # Basic Info
    name = fields.Char(
        string='Device Name',
        required=True,
        tracking=True,
        help='Friendly name for this NAS device'
    )

    ip_address = fields.Char(
        string='IP Address',
        required=True,
        tracking=True,
        help='NAS IP address (nasname in FreeRADIUS)'
    )

    secret = fields.Char(
        string='Shared Secret',
        required=True,
        help='RADIUS shared secret for authentication'
    )

    type = fields.Selection([
        ('mikrotik', 'MikroTik'),
        ('asr', 'ASR Router'),
        ('cisco', 'Cisco'),
        ('other', 'Other')
    ], string='Device Type', required=True, default='mikrotik', tracking=True)

    shortname = fields.Char(
        string='Short Name',
        help='Short identifier (optional, defaults to name)'
    )

    ports = fields.Char(
        string='Ports',
        help='RADIUS ports (e.g., 1812,1813)'
    )

    description = fields.Text(string='Description')

    # Status
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='If unchecked, this device will not sync to RADIUS'
    )

    # Multi-company (Odoo-only)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help='Company that owns this device'
    )

    # Sync tracking
    radius_id = fields.Integer(
        string='RADIUS DB ID',
        readonly=True,
        help='Primary key in FreeRADIUS nas table'
    )

    radius_synced = fields.Boolean(
        string='Synced to RADIUS',
        readonly=True,
        default=False,
        tracking=True,
        help='Indicates if this device exists in RADIUS database'
    )

    last_sync_date = fields.Datetime(
        string='Last Sync',
        readonly=True
    )

    last_sync_error = fields.Text(
        string='Last Sync Error',
        readonly=True
    )

    # --- Ping status (NEW) ---
    last_ping_ok = fields.Boolean('Last Ping OK', readonly=True)
    last_ping_rtt_ms = fields.Float('Last Ping RTT (ms)', digits=(16, 3), readonly=True)
    last_ping_at = fields.Datetime('Last Ping At', readonly=True)

    # --- Online status (computed from last ping) (NEW) ---
    is_online = fields.Selection(
        [('unknown', 'Unknown'), ('online', 'Online'), ('offline', 'Offline')],
        string='Online Status',
        compute='_compute_is_online',
        store=True,
        readonly=True,
    )

    # Constraints
    _sql_constraints = [
        ('ip_company_unique', 'UNIQUE(ip_address, company_id)',
         'IP Address must be unique per company!'),
    ]

    @api.constrains('ip_address')
    def _check_ip_address(self):
        """Basic IP validation"""
        import re
        for record in self:
            if record.ip_address:
                # Simple regex for IPv4
                pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
                if not re.match(pattern, record.ip_address):
                    raise ValidationError(_('Invalid IP address format: %s') % record.ip_address)

    # -------------------------------------------------------------------------
    # UI Actions
    # -------------------------------------------------------------------------

    def action_view_radius_info(self):
        """Stat button click handler - shows RADIUS sync info"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Info'),
                'message': _(
                    'Device: %s\n'
                    'RADIUS ID: %s\n'
                    'Last Sync: %s\n'
                    'Status: %s'
                ) % (
                    self.name,
                    self.radius_id or 'Not synced',
                    self.last_sync_date or 'Never',
                    'Synced' if self.radius_synced else 'Not synced'
                ),
                'type': 'info',
                'sticky': False,
            }
        }

    # -------------------------------------------------------------------------
    # RADIUS Sync Methods
    # -------------------------------------------------------------------------

    def _get_radius_connection(self):
        """Get MySQL connection from company FreeRADIUS settings"""
        self.ensure_one()
        try:
            conn = self.company_id._get_direct_conn()
            return conn
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % str(e))

    def _prepare_nas_values(self):
        """Prepare values for NAS table insert/update (no company_id in RADIUS)"""
        self.ensure_one()
        return {
            'nasname': self.ip_address.strip(),
            'shortname': (self.shortname or self.name or '')[:32],
            'type': self.type or '',
            'ports': self.ports or '',   # do të konvertohet në int/NULL në _sync_to_radius
            'secret': self.secret or '',
            'server': '',
            'community': '',
            'description': self.description or '',
        }

    def action_sync_to_radius(self):
        """Manual button action to sync device to RADIUS"""
        for record in self:
            if not record.active:
                raise UserError(_('Cannot sync inactive device: %s') % record.name)
            record._sync_to_radius()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Sync'),
                'message': _('%d device(s) synced successfully') % len(self),
                'type': 'success',
                'sticky': False,
            }
        }

    def _sync_to_radius(self):
        """Core sync logic: INSERT or UPDATE in FreeRADIUS nas table (no company_id in SQL)"""
        self.ensure_one()

        conn = None
        try:
            conn = self._get_radius_connection()
            cursor = conn.cursor()

            values = self._prepare_nas_values()

            # Normalizo 'ports': vetëm int ose NULL (mos dërgo lista si "1812,1813")
            ports_val = None
            praw = str(values.get('ports') or '').strip()
            if praw.isdigit():
                ports_val = int(praw)

            # Check if exists (by nasname only)
            cursor.execute("SELECT id FROM nas WHERE nasname = %s", (values['nasname'],))
            existing = cursor.fetchone()
            if isinstance(existing, dict):
                radius_id = existing.get('id')
            else:
                radius_id = existing[0] if existing else None

            if radius_id:
                # UPDATE
                update_sql = """
                    UPDATE nas
                       SET shortname=%s,
                           type=%s,
                           ports=%s,
                           secret=%s,
                           description=%s
                     WHERE id=%s
                """
                cursor.execute(update_sql, (
                    values['shortname'],
                    values['type'],
                    ports_val,              # INT ose NULL
                    values['secret'],
                    values['description'],
                    radius_id
                ))
                _logger.info('Updated NAS %s (id=%d) in RADIUS', self.name, radius_id)
                msg = _('Device updated in RADIUS database')
            else:
                # INSERT
                insert_sql = """
                    INSERT INTO nas (nasname, shortname, type, ports, secret, server, community, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (
                    values['nasname'],
                    values['shortname'],
                    values['type'],
                    ports_val,              # INT ose NULL
                    values['secret'],
                    values['server'],
                    values['community'],
                    values['description'],
                ))
                radius_id = cursor.lastrowid
                _logger.info('Inserted NAS %s (id=%d) in RADIUS', self.name, radius_id)
                msg = _('Device synced to RADIUS database')

            # Commit changes
            conn.commit()

            # Update Odoo record
            self.sudo().write({
                'radius_id': radius_id,
                'radius_synced': True,
                'last_sync_date': fields.Datetime.now(),
                'last_sync_error': False,
            })

            # Post message in chatter
            self.message_post(body=msg, message_type='notification')

        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = str(e)
            _logger.error('Failed to sync device %s to RADIUS: %s', self.name, error_msg)

            # Update error status
            self.sudo().write({
                'radius_synced': False,
                'last_sync_error': error_msg,
                'last_sync_date': fields.Datetime.now(),
            })

            # Post error in chatter
            self.message_post(
                body=_('RADIUS sync failed: %s') % error_msg,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            raise UserError(_('RADIUS sync failed for %s:\n%s') % (self.name, error_msg))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def action_remove_from_radius(self):
        """Remove device from RADIUS database"""
        for record in self:
            record._remove_from_radius()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Removal'),
                'message': _('%d device(s) removed from RADIUS') % len(self),
                'type': 'info',
                'sticky': False,
            }
        }

    def _remove_from_radius(self):
        """Delete from RADIUS nas table (no company_id in SQL)"""
        self.ensure_one()

        if not self.radius_id and not self.ip_address:
            return

        conn = None
        try:
            conn = self._get_radius_connection()
            cursor = conn.cursor()

            if self.radius_id:
                cursor.execute("DELETE FROM nas WHERE id = %s", (self.radius_id,))
            else:
                # Fallback: delete by nasname if id isn’t stored
                cursor.execute("DELETE FROM nas WHERE nasname = %s", (self.ip_address.strip(),))

            conn.commit()

            self.sudo().write({
                'radius_id': False,
                'radius_synced': False,
                'last_sync_date': fields.Datetime.now(),
                'last_sync_error': False,
            })

            # Post message in chatter
            self.message_post(
                body=_('Device removed from RADIUS database'),
                message_type='notification'
            )

            _logger.info('Removed NAS %s from RADIUS', self.name)

        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = str(e)
            _logger.error('Failed to remove device %s from RADIUS: %s', self.name, error_msg)

            # Post error in chatter
            self.message_post(
                body=_('RADIUS removal failed: %s') % error_msg,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            raise UserError(_('RADIUS removal failed:\n%s') % error_msg)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Ping Methods (NEW)
    # -------------------------------------------------------------------------

    def _ping_host(self, count=1, timeout=2, tcp_fallback_port=1812):
        """Perform ICMP ping via system 'ping'. Fallback: TCP connect to RADIUS port.
        Returns dict: {'ok': bool, 'rtt_ms': float|None, 'raw': str}
        """
        self.ensure_one()
        import platform, subprocess, shutil, re, socket

        host = (self.ip_address or '').strip()
        if not host:
            return {'ok': False, 'rtt_ms': None, 'raw': 'Empty IP address'}

        # Try ICMP ping if binary exists
        if shutil.which('ping'):
            sys = platform.system().lower()
            if 'windows' in sys:
                cmd = ['ping', '-n', str(count), '-w', str(int(timeout * 1000)), host]
            else:
                cmd = ['ping', '-c', str(count), '-W', str(int(timeout)), host]

            try:
                run = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=timeout * (count + 1)
                )
                out = run.stdout or ''
                ok = (run.returncode == 0)

                # Parse average RTT
                m_unix = re.search(r'(?:rtt|round-trip).*?=\s*([\d\.]+)/([\d\.]+)/', out)
                m_win = re.search(r'Average\s*=\s*(\d+)\s*ms', out, flags=re.IGNORECASE)

                rtt_ms = None
                if m_unix:
                    rtt_ms = float(m_unix.group(2))
                elif m_win:
                    rtt_ms = float(m_win.group(1))

                return {'ok': ok, 'rtt_ms': rtt_ms, 'raw': out}
            except Exception as e:
                fb = f'ICMP ping failed: {e!s}. Trying TCP connect to port {tcp_fallback_port}.'
        else:
            fb = f"'ping' binary not found. Trying TCP connect to port {tcp_fallback_port}."

        # Fallback: TCP connect to RADIUS auth port
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, tcp_fallback_port))
            sock.close()
            return {'ok': True, 'rtt_ms': None, 'raw': 'TCP connect OK (fallback)'}
        except Exception as e:
            return {'ok': False, 'rtt_ms': None, 'raw': f'{fb} TCP connect failed: {e!s}'}

    def action_ping_device(self):
        """UI action to ping the device and store results"""
        self.ensure_one()
        res = self._ping_host(count=2, timeout=2)

        self.sudo().write({
            'last_ping_ok': bool(res.get('ok')),
            'last_ping_rtt_ms': res.get('rtt_ms') or False,
            'last_ping_at': fields.Datetime.now(),
        })

        msg = _("Ping OK: %(ok)s\nRTT avg: %(rtt)s ms\nDetails:\n%(raw)s") % {
            'ok': 'Yes' if res.get('ok') else 'No',
            'rtt': ('%.3f' % res.get('rtt_ms')) if res.get('rtt_ms') is not None else '—',
            'raw': (res.get('raw') or '')[:2000],
        }
        self.message_post(body=msg, message_type='notification', subtype_xmlid='mail.mt_note')

        title = _('Ping OK') if res.get('ok') else _('Ping Failed')
        body = _('RTT: %s ms') % ('%.3f' % res['rtt_ms'] if res.get('rtt_ms') is not None else '—')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': body,
                'type': 'success' if res.get('ok') else 'warning',
                'sticky': False,
            }
        }

    # -------------------------------------------------------------------------
    # Online Status Compute (NEW)
    # -------------------------------------------------------------------------

    @api.depends('last_ping_ok', 'last_ping_at')
    def _compute_is_online(self):
        from datetime import timedelta
        now = fields.Datetime.now()
        ttl_minutes = 5  # sa kohë konsiderohet “fresh” ping-u i fundit
        for r in self:
            if not r.last_ping_at:
                r.is_online = 'unknown'
            elif now - r.last_ping_at > timedelta(minutes=ttl_minutes):
                r.is_online = 'unknown'
            else:
                r.is_online = 'online' if r.last_ping_ok else 'offline'

    # -------------------------------------------------------------------------
    # ORM Hooks
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-sync to RADIUS on create if active"""
        records = super().create(vals_list)
        for record in records:
            if record.active:
                try:
                    record._sync_to_radius()
                except Exception as e:
                    _logger.warning('Auto-sync failed for new device %s: %s', record.name, e)
        return records

    def write(self, vals):
        """Auto-sync to RADIUS on update if relevant fields changed"""
        result = super().write(vals)

        sync_fields = {'ip_address', 'secret', 'type', 'shortname', 'ports', 'description', 'active'}
        if any(f in vals for f in sync_fields):
            for record in self:
                if record.active and record.radius_synced:
                    try:
                        record._sync_to_radius()
                    except Exception as e:
                        _logger.warning('Auto-sync failed for device %s: %s', record.name, e)

        return result

    def unlink(self):
        """Remove from RADIUS before deleting from Odoo"""
        for record in self:
            if record.radius_synced:
                try:
                    record._remove_from_radius()
                except Exception as e:
                    _logger.warning('Could not remove device %s from RADIUS: %s', record.name, e)
        return super().unlink()

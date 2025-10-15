# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class AsrRadiusSession(models.Model):
    """
    Read-only model që lexon nga radacct (FreeRADIUS accounting).
    Shfaq sesionet aktive dhe historike të PPPoE/HotSpot/etc.

    NOTE: Ky model NUK krijon tabelë në Odoo PostgreSQL.
    Të gjitha të dhënat lexohen direkt nga MySQL FreeRADIUS.
    """
    _name = 'asr.radius.session'
    _description = 'RADIUS Accounting Session'
    _rec_name = 'username'

    # Fushat bazë nga radacct
    radacctid = fields.Char(string='AcctID', readonly=True)
    acctsessionid = fields.Char(string='Session ID', readonly=True)
    username = fields.Char(string='Username', readonly=True)
    nasipaddress = fields.Char(string='NAS IP', readonly=True)
    nasportid = fields.Char(string='NAS Port ID', readonly=True)
    nasporttype = fields.Char(string='NAS Port Type', readonly=True)

    # Kohët
    acctstarttime = fields.Datetime(string='Start Time', readonly=True)
    acctupdatetime = fields.Datetime(string='Last Update', readonly=True)
    acctstoptime = fields.Datetime(string='Stop Time', readonly=True)

    # Trafikut (në bytes)
    acctinputoctets = fields.Integer(string='Download (bytes)', readonly=True)
    acctoutputoctets = fields.Integer(string='Upload (bytes)', readonly=True)

    # Trafikut në format human-readable
    download_mb = fields.Float(string='Download (MB)', compute='_compute_traffic_mb', store=False)
    upload_mb = fields.Float(string='Upload (MB)', compute='_compute_traffic_mb', store=False)
    total_mb = fields.Float(string='Total (MB)', compute='_compute_traffic_mb', store=False)

    # Kohëzgjatja
    acctsessiontime = fields.Integer(string='Duration (seconds)', readonly=True)
    duration_human = fields.Char(string='Duration', compute='_compute_duration_human', store=False)

    # Shkaku i disconnect
    acctterminatecause = fields.Char(string='Terminate Cause', readonly=True)

    # IP Address
    framedipaddress = fields.Char(string='IP Address', readonly=True)
    framedipv6prefix = fields.Char(string='IPv6 Prefix', readonly=True)

    # Lidhja me përdoruesin tonë (nëse ekziston)
    radius_user_id = fields.Many2one('asr.radius.user', string='RADIUS User',
                                     compute='_compute_radius_user', store=False)

    # Status (computed) - no search function needed, use acctstoptime directly in domains
    is_active = fields.Boolean(string='Active', compute='_compute_is_active', store=False)

    # Multi-company
    company_id = fields.Many2one('res.company', string='Company',
                                 compute='_compute_company', store=False)

    @api.depends('acctinputoctets', 'acctoutputoctets')
    def _compute_traffic_mb(self):
        for rec in self:
            rec.download_mb = (rec.acctinputoctets or 0) / (1024 * 1024)
            rec.upload_mb = (rec.acctoutputoctets or 0) / (1024 * 1024)
            rec.total_mb = rec.download_mb + rec.upload_mb

    @api.depends('acctsessiontime')
    def _compute_duration_human(self):
        for rec in self:
            if not rec.acctsessiontime:
                rec.duration_human = '—'
                continue

            seconds = int(rec.acctsessiontime or 0)
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60

            if hours > 0:
                rec.duration_human = f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                rec.duration_human = f"{minutes}m {secs}s"
            else:
                rec.duration_human = f"{secs}s"

    @api.depends('acctstoptime')
    def _compute_is_active(self):
        """Sesioni është aktiv nëse acctstoptime është NULL"""
        for rec in self:
            rec.is_active = not bool(rec.acctstoptime)

    @api.depends('username')
    def _compute_radius_user(self):
        """Gjen përdoruesin tonë nga Odoo (nëse ekziston)"""
        for rec in self:
            if rec.username:
                user = self.env['asr.radius.user'].search([
                    ('username', '=', rec.username)
                ], limit=1)
                rec.radius_user_id = user.id if user else False
            else:
                rec.radius_user_id = False

    @api.depends('nasipaddress')
    def _compute_company(self):
        """Përcakton kompani nga NAS IP (nëse device ekziston në Odoo)"""
        for rec in self:
            if rec.nasipaddress:
                device = self.env['asr.device'].search([
                    ('ip_address', '=', rec.nasipaddress)
                ], limit=1)
                rec.company_id = device.company_id.id if device else self.env.company.id
            else:
                rec.company_id = self.env.company.id

    # -------------------------------------------------------------------------
    # Override ORM Methods - READ from MySQL FreeRADIUS
    # -------------------------------------------------------------------------

    @api.model
    def _get_radius_connection(self):
        """Merr lidhjen me FreeRADIUS DB"""
        company = self.env.company
        try:
            return company._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % str(e))

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Override search_read për të lexuar nga radacct në MySQL"""
        conn = None
        try:
            conn = self._get_radius_connection()
            cursor = conn.cursor()

            # Build SQL query nga domain
            where_clause, params = self._domain_to_sql(domain or [])

            # Columns to select
            field_mapping = {
                'radacctid': 'radacctid',
                'acctsessionid': 'acctsessionid',
                'username': 'username',
                'nasipaddress': 'nasipaddress',
                'nasportid': 'nasportid',
                'nasporttype': 'nasporttype',
                'acctstarttime': 'acctstarttime',
                'acctupdatetime': 'acctupdatetime',
                'acctstoptime': 'acctstoptime',
                'acctinputoctets': 'acctinputoctets',
                'acctoutputoctets': 'acctoutputoctets',
                'acctsessiontime': 'acctsessiontime',
                'acctterminatecause': 'acctterminatecause',
                'framedipaddress': 'framedipaddress',
                'framedipv6prefix': 'framedipv6prefix',
            }

            # Default columns nëse nuk specifikohet
            if not fields:
                cols = list(field_mapping.keys())
            else:
                # Filter only valid fields
                cols = [f for f in fields if f in field_mapping]

            # Build SELECT
            select_cols = [field_mapping[f] for f in cols]
            sql = f"SELECT {', '.join(select_cols)} FROM radacct"

            if where_clause:
                sql += f" WHERE {where_clause}"

            # ORDER BY
            if order:
                # Convert Odoo order to SQL order
                sql += f" ORDER BY {order.replace(' desc', ' DESC').replace(' asc', ' ASC')}"
            else:
                sql += " ORDER BY acctstarttime DESC"

            # LIMIT & OFFSET
            if limit:
                sql += f" LIMIT {int(limit)}"
            if offset:
                sql += f" OFFSET {int(offset)}"

            _logger.debug("RADIUS Session SQL: %s | Params: %s", sql, params)
            cursor.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                record = {}
                if isinstance(row, dict):
                    # Dict cursor
                    for f in cols:
                        record[f] = row.get(field_mapping[f])
                else:
                    # Tuple cursor
                    for i, f in enumerate(cols):
                        record[f] = row[i] if i < len(row) else None

                # Shto ID artificiale (përdor radacctid si ID)
                record['id'] = int(record.get('radacctid') or 0)

                results.append(record)

            return results

        except Exception as e:
            _logger.error("Failed to read radacct: %s", e, exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _domain_to_sql(self, domain):
        """Konverton Odoo domain në SQL WHERE clause"""
        if not domain:
            return '', []

        conditions = []
        params = []

        for item in domain:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue

            field, operator, value = item

            # Map special fields
            if field == 'is_active':
                field = 'acctstoptime'
                if operator == '=' and value:
                    operator = 'is'
                    value = None
                elif operator == '=' and not value:
                    operator = 'is not'
                    value = None

            # Build condition
            if operator == '=' and value is None:
                conditions.append(f"{field} IS NULL")
            elif operator == '=' and value is False:
                conditions.append(f"{field} IS NULL")
            elif operator == 'is':
                conditions.append(f"{field} IS NULL")
            elif operator == 'is not':
                conditions.append(f"{field} IS NOT NULL")
            elif operator == '!=':
                if value is None or value is False:
                    conditions.append(f"{field} IS NOT NULL")
                else:
                    conditions.append(f"{field} != %s")
                    params.append(value)
            elif operator == 'like':
                conditions.append(f"{field} LIKE %s")
                params.append(f"%{value}%")
            elif operator == 'ilike':
                conditions.append(f"LOWER({field}) LIKE LOWER(%s)")
                params.append(f"%{value}%")
            elif operator in ('>', '<', '>=', '<='):
                conditions.append(f"{field} {operator} %s")
                params.append(value)
            else:  # default '='
                conditions.append(f"{field} = %s")
                params.append(value)

        return ' AND '.join(conditions), params

    @api.model
    def search_count(self, domain=None):
        """Count sessions matching domain"""
        conn = None
        try:
            conn = self._get_radius_connection()
            cursor = conn.cursor()

            where_clause, params = self._domain_to_sql(domain or [])
            sql = "SELECT COUNT(*) as cnt FROM radacct"
            if where_clause:
                sql += f" WHERE {where_clause}"

            cursor.execute(sql, params)
            row = cursor.fetchone()

            if isinstance(row, dict):
                return int(row.get('cnt', 0))
            else:
                return int(row[0] if row else 0)

        except Exception as e:
            _logger.error("Failed to count radacct: %s", e)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def read(self, fields=None, load='_classic_read'):
        """Override read për një ose më shumë records"""
        # Nëse kemi IDs, lexo direkt nga MySQL
        if not self.ids:
            return []

        conn = None
        try:
            conn = self._get_radius_connection()
            cursor = conn.cursor()

            # Përdor radacctid si ID
            placeholders = ','.join(['%s'] * len(self.ids))
            sql = f"""
                SELECT radacctid, acctsessionid, username, nasipaddress, nasportid,
                       nasporttype, acctstarttime, acctupdatetime, acctstoptime,
                       acctinputoctets, acctoutputoctets, acctsessiontime,
                       acctterminatecause, framedipaddress, framedipv6prefix
                FROM radacct
                WHERE radacctid IN ({placeholders})
            """
            cursor.execute(sql, tuple(self.ids))

            results = []
            for row in cursor.fetchall():
                if isinstance(row, dict):
                    record = dict(row)
                    record['id'] = int(record.get('radacctid') or 0)
                else:
                    record = {
                        'id': int(row[0] or 0),
                        'radacctid': row[0],
                        'acctsessionid': row[1],
                        'username': row[2],
                        'nasipaddress': row[3],
                        'nasportid': row[4],
                        'nasporttype': row[5],
                        'acctstarttime': row[6],
                        'acctupdatetime': row[7],
                        'acctstoptime': row[8],
                        'acctinputoctets': row[9],
                        'acctoutputoctets': row[10],
                        'acctsessiontime': row[11],
                        'acctterminatecause': row[12],
                        'framedipaddress': row[13],
                        'framedipv6prefix': row[14],
                    }
                results.append(record)

            return results

        except Exception as e:
            _logger.error("Failed to read radacct records: %s", e)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_view_user_sessions(self):
        """Hap listën e sesioneve për këtë përdorues"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sessions for %s') % self.username,
            'res_model': 'asr.radius.session',
            'view_mode': 'list',
            'domain': [('username', '=', self.username)],
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    def action_disconnect_session(self):
        """
        Disconnect aktiv sesioni (kërkon integrim me CoA/DM në FreeRADIUS)
        Kjo është placeholder - duhet të implementohet me pyrad ose API tjetër
        """
        self.ensure_one()
        if not self.is_active:
            raise UserError(_('This session is already terminated.'))

        # TODO: Implement Disconnect-Request (RFC 3576)
        raise UserError(_(
            'Session disconnect not yet implemented.\n'
            'This requires CoA/DM support in FreeRADIUS.\n'
            'Session ID: %s'
        ) % self.acctsessionid)


class AsrRadiusUser(models.Model):
    """Extend existing model me session stats"""
    _inherit = 'asr.radius.user'

    # Statistikat live
    active_sessions_count = fields.Integer(
        string='Active Sessions',
        compute='_compute_session_stats',
        store=False
    )

    total_sessions_count = fields.Integer(
        string='Total Sessions',
        compute='_compute_session_stats',
        store=False
    )

    last_session_start = fields.Datetime(
        string='Last Login',
        compute='_compute_session_stats',
        store=False
    )

    @api.depends('username')
    def _compute_session_stats(self):
        """Llogarit statistikat nga radacct"""
        for rec in self:
            if not rec.username:
                rec.active_sessions_count = 0
                rec.total_sessions_count = 0
                rec.last_session_start = False
                continue

            conn = None
            try:
                conn = rec._get_radius_conn()
                cursor = conn.cursor()

                # Active sessions
                cursor.execute("""
                               SELECT COUNT(*) as cnt
                               FROM radacct
                               WHERE username = %s
                                 AND acctstoptime IS NULL
                               """, (rec.username,))
                row = cursor.fetchone()
                rec.active_sessions_count = int(row[0] if isinstance(row, tuple) else row.get('cnt', 0))

                # Total sessions
                cursor.execute("""
                               SELECT COUNT(*) as cnt
                               FROM radacct
                               WHERE username = %s
                               """, (rec.username,))
                row = cursor.fetchone()
                rec.total_sessions_count = int(row[0] if isinstance(row, tuple) else row.get('cnt', 0))

                # Last session
                cursor.execute("""
                               SELECT acctstarttime
                               FROM radacct
                               WHERE username = %s
                               ORDER BY acctstarttime DESC LIMIT 1
                               """, (rec.username,))
                row = cursor.fetchone()
                if row:
                    last_start = row[0] if isinstance(row, tuple) else row.get('acctstarttime')
                    rec.last_session_start = last_start
                else:
                    rec.last_session_start = False

            except Exception as e:
                _logger.warning('Failed to compute session stats for %s: %s', rec.username, e)
                rec.active_sessions_count = 0
                rec.total_sessions_count = 0
                rec.last_session_start = False
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def action_view_sessions(self):
        """Smart button për të parë sesionet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sessions: %s') % self.username,
            'res_model': 'asr.radius.session',
            'view_mode': 'list,form',
            'domain': [('username', '=', self.username)],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
                'default_username': self.username,
            },
        }

    def action_view_active_sessions(self):
        """Shfaq vetëm sesionet aktive"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Active Sessions: %s') % self.username,
            'res_model': 'asr.radius.session',
            'view_mode': 'list',
            'domain': [
                ('username', '=', self.username),
                ('acctstoptime', '=', False)
            ],
            'context': {'create': False, 'edit': False, 'delete': False},
        }

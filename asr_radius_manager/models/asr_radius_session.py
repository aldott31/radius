

# -*- coding: utf-8 -*-
"""
✅ FIXED: Remote model që funksionon në UI për Odoo 18.
Problemi ishte që UI përdor një code path të ndryshëm nga shell.
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AsrRadiusSessionFixed(models.Model):
    """
    RADIUS Sessions - read-only nga radacct (MySQL).
    ✅ FIX: Override të gjitha metodat ORM që përdor list view.
    """
    _name = 'asr.radius.session'
    _description = 'RADIUS Accounting Session'
    _rec_name = 'username'
    _auto = False
    _check_company_auto = False
    _log_access = False  # ✅ KRITIKE: disable create_uid, write_uid, etc.

    # === Fusha minimale (vetëm ato që shfaqen në list) ===
    username = fields.Char(readonly=True)
    framedipaddress = fields.Char(string='IP Address', readonly=True)
    nasipaddress = fields.Char(string='NAS', readonly=True)
    nasporttype = fields.Char(string='Type', readonly=True)
    acctstarttime = fields.Datetime(string='Start Time', readonly=True)
    acctsessiontime = fields.Integer(readonly=True)
    acctinputoctets = fields.Integer(readonly=True)
    acctoutputoctets = fields.Integer(readonly=True)

    # Computed (për list view)
    duration_human = fields.Char(compute='_compute_display', store=False)
    download_mb = fields.Float(compute='_compute_display', store=False, digits=(16, 2))
    upload_mb = fields.Float(compute='_compute_display', store=False, digits=(16, 2))
    total_mb = fields.Float(compute='_compute_display', store=False, digits=(16, 2))
    is_active = fields.Boolean(compute='_compute_display', store=False)

    # Për form (opsionale)
    acctstoptime = fields.Datetime(readonly=True)
    radacctid = fields.Char(readonly=True)
    acctsessionid = fields.Char(readonly=True)
    nasportid = fields.Char(readonly=True)
    acctterminatecause = fields.Char(readonly=True)

    @api.depends('acctsessiontime', 'acctinputoctets', 'acctoutputoctets', 'acctstoptime')
    def _compute_display(self):
        """Compute vetëm nëse record ka të dhëna."""
        for rec in self:
            # Duration
            dur = int(rec.acctsessiontime or 0)
            if dur <= 0:
                rec.duration_human = '—'
            else:
                h = dur // 3600
                m = (dur % 3600) // 60
                s = dur % 60
                rec.duration_human = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")

            # Traffic
            rec.download_mb = (rec.acctinputoctets or 0) / (1024 * 1024)
            rec.upload_mb = (rec.acctoutputoctets or 0) / (1024 * 1024)
            rec.total_mb = rec.download_mb + rec.upload_mb

            # Active?
            rec.is_active = not bool(rec.acctstoptime)

    # ========== ORM Overrides ==========

    def _get_radius_conn(self):
        """Connection helper."""
        try:
            return self.env.company._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS: %s') % e)

    @api.model
    def _domain_to_sql(self, domain):
        """Convert Odoo domain → SQL WHERE."""
        if not domain:
            return '', []

        conditions, params = [], []
        for item in domain:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            field, op, value = item

            # is_active pseudo-field
            if field == 'is_active':
                if (op == '=' and value) or op == 'is':
                    conditions.append("(acctstoptime IS NULL OR acctstoptime = '0000-00-00 00:00:00')")
                else:
                    conditions.append("(acctstoptime IS NOT NULL AND acctstoptime <> '0000-00-00 00:00:00')")
                continue

            # Standard operators
            if op == 'ilike':
                conditions.append(f"LOWER({field}) LIKE LOWER(%s)")
                params.append(f"%{str(value)}%")
            elif op in ('>', '<', '>=', '<=', '=', '!='):
                conditions.append(f"{field} {op} %s")
                params.append(value)

        return ' AND '.join(conditions) if conditions else '', params

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """
        ✅ MAIN FIX: Direct MySQL read pa u mbështetur në search().
        Kjo është ajo që UI thërret për list view.
        """
        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()

            # Build WHERE
            where_sql, params = self._domain_to_sql(domain or [])

            # ✅ KRITIKE: Lista e plotë e kolonave nga DB
            db_fields = [
                'radacctid', 'username', 'framedipaddress', 'nasipaddress',
                'nasporttype', 'acctstarttime', 'acctstoptime', 'acctsessiontime',
                'acctinputoctets', 'acctoutputoctets', 'acctsessionid',
                'nasportid', 'acctterminatecause'
            ]

            sql = f"SELECT {', '.join(db_fields)} FROM radacct"
            if where_sql:
                sql += f" WHERE {where_sql}"

            # ORDER (whitelist për të shmangur SQL injection)
            ALLOWED_ORDER = {
                'acctstarttime': 'acctstarttime',
                'username': 'username',
                'nasipaddress': 'nasipaddress',
                'acctsessiontime': 'acctsessiontime'
            }

            order_sql = order or 'acctstarttime DESC'
            order_parts = []
            for seg in (order_sql or '').split(','):
                parts = seg.strip().split()
                if not parts:
                    continue
                col = parts[0]
                direction = parts[1].upper() if len(parts) > 1 and parts[1].upper() in ('ASC', 'DESC') else 'DESC'

                if col in ALLOWED_ORDER:
                    order_parts.append(f"{ALLOWED_ORDER[col]} {direction}")

            if order_parts:
                sql += f" ORDER BY {', '.join(order_parts)}"
            else:
                sql += " ORDER BY acctstarttime DESC"

            # LIMIT/OFFSET
            if limit:
                sql += f" LIMIT {int(limit)}"
            if offset:
                sql += f" OFFSET {int(offset)}"

            _logger.debug("Session SQL: %s | params: %s", sql, params)
            cur.execute(sql, params or ())

            results = []
            for row in (cur.fetchall() or []):
                # PyMySQL me DictCursor kthen dict
                if isinstance(row, dict):
                    r = {
                        'id': int(row.get('radacctid') or 0),
                        'radacctid': str(row.get('radacctid') or ''),
                        'username': row.get('username') or '',
                        'framedipaddress': row.get('framedipaddress') or '',
                        'nasipaddress': row.get('nasipaddress') or '',
                        'nasporttype': row.get('nasporttype') or '',
                        'acctstarttime': row.get('acctstarttime'),
                        'acctstoptime': row.get('acctstoptime'),
                        'acctsessiontime': int(row.get('acctsessiontime') or 0),
                        'acctinputoctets': int(row.get('acctinputoctets') or 0),
                        'acctoutputoctets': int(row.get('acctoutputoctets') or 0),
                        'acctsessionid': row.get('acctsessionid') or '',
                        'nasportid': row.get('nasportid') or '',
                        'acctterminatecause': row.get('acctterminatecause') or '',
                    }
                else:
                    # Tuple cursor (order: db_fields list order)
                    r = {
                        'id': int(row[0] or 0),
                        'radacctid': str(row[0] or ''),
                        'username': row[1] or '',
                        'framedipaddress': row[2] or '',
                        'nasipaddress': row[3] or '',
                        'nasporttype': row[4] or '',
                        'acctstarttime': row[5],
                        'acctstoptime': row[6],
                        'acctsessiontime': int(row[7] or 0),
                        'acctinputoctets': int(row[8] or 0),
                        'acctoutputoctets': int(row[9] or 0),
                        'acctsessionid': row[10] or '',
                        'nasportid': row[11] or '',
                        'acctterminatecause': row[12] or '',
                    }

                # ✅ Computed në mënyrë manuale (për list)
                dur = r['acctsessiontime']
                h = dur // 3600
                m = (dur % 3600) // 60
                s = dur % 60
                r['duration_human'] = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s") if dur else '—'

                r['download_mb'] = r['acctinputoctets'] / (1024 * 1024)
                r['upload_mb'] = r['acctoutputoctets'] / (1024 * 1024)
                r['total_mb'] = r['download_mb'] + r['upload_mb']
                r['is_active'] = not bool(r['acctstoptime'])

                results.append(r)

            _logger.info("Session search_read returned %d rows", len(results))
            return results

        except Exception as e:
            _logger.error("Session search_read failed: %s", e, exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        """
        ✅ Odoo 18 UI uses web_search_read instead of search_read!
        This method handles the new 'specification' parameter.
        """
        _logger.info("=== WEB_SEARCH_READ called ===")
        _logger.info(f"Specification: {specification}")
        _logger.info(f"Domain: {domain}")
        _logger.info(f"Limit: {limit}, Offset: {offset}, Order: {order}")

        # Extract fields from specification (Odoo 18 format)
        fields = list(specification.keys()) if specification else None

        # Call our custom search_read
        records = self.search_read(
            domain=domain,
            fields=fields,
            offset=offset,
            limit=limit,
            order=order
        )

        # Get count
        records_length = len(records)

        _logger.info(f"web_search_read returning {records_length} records")

        return {
            'records': records,
            'length': records_length,
        }
    @api.model
    def search_count(self, domain=None):
        """Count për pagination."""
        where_sql, params = self._domain_to_sql(domain or [])
        sql = "SELECT COUNT(*) FROM radacct"
        if where_sql:
            sql += f" WHERE {where_sql}"

        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()
            cur.execute(sql, params or ())
            row = cur.fetchone()

            if isinstance(row, dict):
                count = int(row.get('COUNT(*)') or row.get('count') or 0)
            else:
                count = int(row[0] if row else 0)

            return count
        except Exception as e:
            _logger.error("Session count failed: %s", e)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    @api.model
    def search(self, domain=None, offset=0, limit=None, order=None, count=False):
        """
        ✅ Search që UI mund ta thërrasë.
        Kthe empty recordset - search_read() bën punën e vërtetë.
        """
        if count:
            return self.search_count(domain)

        # Kthe recordset bosh - UI do përdorë search_read()
        return self.browse([])

    def read(self, fields=None, load='_classic_read'):
        """Read individual records (për form view)."""
        if not self.ids:
            return []

        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()

            placeholders = ','.join(['%s'] * len(self.ids))
            sql = f"""
                SELECT radacctid, username, framedipaddress, nasipaddress,
                       nasporttype, acctstarttime, acctstoptime, acctsessiontime,
                       acctinputoctets, acctoutputoctets, acctsessionid,
                       nasportid, acctterminatecause
                FROM radacct
                WHERE radacctid IN ({placeholders})
            """
            cur.execute(sql, tuple(self.ids))

            results = []
            for row in (cur.fetchall() or []):
                if isinstance(row, dict):
                    r = {
                        'id': int(row.get('radacctid') or 0),
                        'radacctid': str(row.get('radacctid') or ''),
                        'username': row.get('username') or '',
                        'framedipaddress': row.get('framedipaddress') or '',
                        'nasipaddress': row.get('nasipaddress') or '',
                        'nasporttype': row.get('nasporttype') or '',
                        'acctstarttime': row.get('acctstarttime'),
                        'acctstoptime': row.get('acctstoptime'),
                        'acctsessiontime': int(row.get('acctsessiontime') or 0),
                        'acctinputoctets': int(row.get('acctinputoctets') or 0),
                        'acctoutputoctets': int(row.get('acctoutputoctets') or 0),
                        'acctsessionid': row.get('acctsessionid') or '',
                        'nasportid': row.get('nasportid') or '',
                        'acctterminatecause': row.get('acctterminatecause') or '',
                    }
                else:
                    r = {
                        'id': int(row[0] or 0),
                        'radacctid': str(row[0] or ''),
                        'username': row[1] or '',
                        'framedipaddress': row[2] or '',
                        'nasipaddress': row[3] or '',
                        'nasporttype': row[4] or '',
                        'acctstarttime': row[5],
                        'acctstoptime': row[6],
                        'acctsessiontime': int(row[7] or 0),
                        'acctinputoctets': int(row[8] or 0),
                        'acctoutputoctets': int(row[9] or 0),
                        'acctsessionid': row[10] or '',
                        'nasportid': row[11] or '',
                        'acctterminatecause': row[12] or '',
                    }
                results.append(r)
            return results

        except Exception as e:
            _logger.error("Session read failed: %s", e)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    # ========== Access Control Bypass ==========

    def check_access_rights(self, operation, raise_exception=True):
        """✅ Bypass - no PostgreSQL table."""
        return True

    def check_access_rule(self, operation):
        """✅ Bypass - no record rules."""
        return

    def _check_company_auto(self):
        """✅ Disable multi-company checks."""
        return
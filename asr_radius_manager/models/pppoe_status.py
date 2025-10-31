from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AsrRadiusPPPoeStatus(models.Model):
    """
    PPPoE Status - aggregate view nga radacct.
    ✅ FIX: Direct MySQL queries me web_search_read për Odoo 18.
    """
    _name = 'asr.radius.pppoe_status'
    _description = 'PPPoE Status (live from radacct)'
    _rec_name = 'username'
    _auto = False
    _check_company_auto = False
    _log_access = False

    # Lista fields
    status = fields.Selection([('ONLINE', 'ONLINE'), ('OFFLINE', 'OFFLINE')], readonly=True)
    login_on = fields.Datetime(readonly=True)
    username = fields.Char(readonly=True)
    nas_ip = fields.Char(string="PPPoE Server", readonly=True)
    ip_address = fields.Char(readonly=True)
    attached_plans = fields.Char(readonly=True)
    nas_port = fields.Char(readonly=True)
    circuit_id_mac = fields.Char(readonly=True)
    virtual_interface = fields.Char(readonly=True)
    # NEW: kolonë e re për portën e loginit (pa prekur 'circuit_id_mac')
    login_port = fields.Char(readonly=True)

    def _get_radius_conn(self):
        try:
            return self.env.company._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS: %s') % e)

    @api.model
    def _domain_to_filters(self, domain):
        """Extract username filters."""
        username_eq, username_like = None, None
        for item in (domain or []):
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            f, op, val = item
            if f == 'username':
                if op == '=':
                    username_eq = str(val)
                elif op in ('like', 'ilike'):
                    username_like = str(val)
        return username_eq, username_like

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """✅ Direct MySQL query."""
        username_eq, username_like = self._domain_to_filters(domain)

        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()

            # Sub-WHERE për username filter
            sub_where_parts, sub_params = [], []
            if username_eq:
                sub_where_parts.append("username = %s")
                sub_params.append(username_eq)
            elif username_like:
                sub_where_parts.append("username LIKE %s")
                sub_params.append(f"%{username_like}%")

            sub_where = f"WHERE {' AND '.join(sub_where_parts)}" if sub_where_parts else ""

            # Main query
            sql = f"""
                SELECT
                  ra.radacctid AS _id_,
                  CASE
                    WHEN (ra.acctstoptime IS NULL OR ra.acctstoptime = '0000-00-00 00:00:00')
                         AND (ra.acctupdatetime IS NULL OR ra.acctupdatetime > NOW() - INTERVAL 15 MINUTE)
                      THEN 'ONLINE' ELSE 'OFFLINE'
                  END AS status,
                  ra.acctstarttime AS login_on,
                  ra.username AS username,
                  ra.nasipaddress AS nas_ip,
                  NULLIF(ra.framedipaddress,'') AS ip_address,
                  COALESCE(
                    (SELECT GROUP_CONCAT(g.groupname ORDER BY g.priority SEPARATOR '/')
                       FROM radusergroup g
                      WHERE g.username = ra.username),
                    'N/A'
                  ) AS attached_plans,
                  NULLIF(ra.nasportid,'') AS nas_port,
                  TRIM(CONCAT(COALESCE(ra.calledstationid,''), ' / ', COALESCE(ra.callingstationid,''))) AS circuit_id_mac,
                  NULLIF(ra.framedinterfaceid,'') AS virtual_interface
                FROM radacct ra
                JOIN (
                  SELECT username, MAX(acctstarttime) AS last_start
                  FROM radacct
                  {sub_where}
                  GROUP BY username
                ) last ON last.username = ra.username AND last.last_start = ra.acctstarttime
            """

            # ORDER (whitelist)
            ALLOWED_ORDER = {
                'username': 'ra.username',
                'status': 'status',
                'login_on': 'ra.acctstarttime'
            }

            order_parts = []
            for seg in (order or 'username').split(','):
                parts = seg.strip().split()
                if not parts:
                    continue
                col = parts[0]
                direction = parts[1].upper() if len(parts) > 1 and parts[1].upper() in ('ASC', 'DESC') else 'ASC'
                if col in ALLOWED_ORDER:
                    order_parts.append(f"{ALLOWED_ORDER[col]} {direction}")

            sql += f" ORDER BY {', '.join(order_parts)}" if order_parts else " ORDER BY ra.username ASC"

            # LIMIT/OFFSET
            if limit:
                sql += f" LIMIT {int(limit)}"
            if offset:
                sql += f" OFFSET {int(offset)}"

            _logger.debug("PPPoE Status SQL: %s | params: %s", sql, sub_params)
            cur.execute(sql, sub_params or ())

            results = []
            for row in (cur.fetchall() or []):
                if isinstance(row, dict):
                    r = {
                        'id': int(row.get('_id_') or 0),
                        'status': row.get('status') or 'OFFLINE',
                        'login_on': row.get('login_on'),
                        'username': row.get('username') or '',
                        'nas_ip': row.get('nas_ip') or '',
                        'ip_address': row.get('ip_address') or '',
                        'attached_plans': row.get('attached_plans') or 'N/A',
                        'nas_port': row.get('nas_port') or '',
                        'circuit_id_mac': row.get('circuit_id_mac') or '',
                        'virtual_interface': row.get('virtual_interface') or '',
                        'login_port': '',  # NEW
                    }
                else:
                    # Tuple: (_id, status, login_on, username, nas_ip, ip_address, plans, port, circuit, iface)
                    r = {
                        'id': int(row[0] or 0),
                        'status': row[1] or 'OFFLINE',
                        'login_on': row[2],
                        'username': row[3] or '',
                        'nas_ip': row[4] or '',
                        'ip_address': row[5] or '',
                        'attached_plans': row[6] or 'N/A',
                        'nas_port': row[7] or '',
                        'circuit_id_mac': row[8] or '',
                        'virtual_interface': row[9] or '',
                        'login_port': '',  # NEW
                    }
                results.append(r)

            # NEW: injekto "Login Port" nga user-at (ruajtur nga wizard-i Show MAC)
            usernames = [r.get('username') for r in results if r.get('username')]
            if usernames:
                users = self.env['asr.radius.user'].sudo().search([('username', 'in', usernames)])
                map_login = {u.username: (u.olt_login_port or '') for u in users if u.olt_login_port}
                if map_login:
                    for r in results:
                        v = map_login.get(r.get('username'))
                        if v:
                            r['login_port'] = v

            _logger.info("PPPoE Status returned %d rows", len(results))
            return results

        except Exception as e:
            _logger.error("PPPoE Status search_read failed: %s", e, exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        """✅ Odoo 18 UI uses web_search_read!"""
        _logger.info("=== PPPoE Status WEB_SEARCH_READ called ===")
        fields = list(specification.keys()) if specification else None
        records = self.search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order)
        _logger.info(f"PPPoE Status returning {len(records)} records")
        return {'records': records, 'length': len(records)}

    @api.model
    def search_count(self, domain=None):
        username_eq, username_like = self._domain_to_filters(domain)

        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()

            sql = "SELECT COUNT(*) FROM (SELECT username, MAX(acctstarttime) FROM radacct"
            params = []
            if username_eq:
                sql += " WHERE username=%s"
                params.append(username_eq)
            elif username_like:
                sql += " WHERE username LIKE %s"
                params.append(f"%{username_like}%")
            sql += " GROUP BY username) t"

            cur.execute(sql, params or ())
            row = cur.fetchone()

            if isinstance(row, dict):
                count = int(row.get('COUNT(*)') or row.get('count') or 0)
            else:
                count = int(row[0] if row else 0)

            return count
        except Exception as e:
            _logger.error("PPPoE Status count failed: %s", e)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    @api.model
    def search(self, domain=None, offset=0, limit=None, order=None, count=False):
        if count:
            return self.search_count(domain)
        return self.browse([])

    def read(self, fields=None, load='_classic_read'):
        """Read për form view."""
        if not self.ids:
            return []
        return []

    # Access control bypass
    def check_access_rights(self, operation, raise_exception=True):
        return True

    def check_access_rule(self, operation):
        return

    def _check_company_auto(self):
        return
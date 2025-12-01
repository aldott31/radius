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

    # Location & Authentication fields (computed from asr.radius.user)
    location = fields.Char(string="Location", compute='_compute_user_details', readonly=True)
    mac_address = fields.Char(string="MAC Address", compute='_compute_user_details', readonly=True)
    mac_auth_enabled = fields.Boolean(string="MAC Auth Enabled", compute='_compute_user_details', readonly=True)
    port_auth_enabled = fields.Boolean(string="Port Auth Enabled", compute='_compute_user_details', readonly=True)
    vlan_id = fields.Char(string="VLAN ID", compute='_compute_user_details', readonly=True)
    vlan_auth_enabled = fields.Boolean(string="VLAN Auth Enabled", compute='_compute_user_details', readonly=True)

    # Related user info
    radius_user_id = fields.Many2one('asr.radius.user', string="RADIUS User", compute='_compute_user_details', readonly=True)
    partner_id = fields.Many2one('res.partner', string="Customer", compute='_compute_user_details', readonly=True)

    def _get_radius_conn(self):
        try:
            return self.env.company._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS: %s') % e)

    def _compute_user_details(self):
        """Compute location, MAC, and authentication details from asr.radius.user"""
        for rec in self:
            # Default values
            rec.location = ''
            rec.mac_address = ''
            rec.mac_auth_enabled = False
            rec.port_auth_enabled = False
            rec.vlan_id = ''
            rec.vlan_auth_enabled = False
            rec.radius_user_id = False
            rec.partner_id = False

            if not rec.username:
                continue

            # Find RADIUS user
            user = self.env['asr.radius.user'].sudo().search([('username', '=', rec.username)], limit=1)
            if not user:
                continue

            rec.radius_user_id = user.id
            rec.partner_id = user.partner_id.id if user.partner_id else False

            # Build location string: City, POP, Device, Port
            location_parts = []
            if user.partner_id:
                if user.partner_id.city_id:
                    location_parts.append(user.partner_id.city_id.name)
                if user.partner_id.pop_id:
                    location_parts.append(user.partner_id.pop_id.name)
                if user.partner_id.access_device_id:
                    device_name = user.partner_id.access_device_id.name or ''
                    location_parts.append(device_name)
                if user.partner_id.olt_pon_port:
                    location_parts.append(user.partner_id.olt_pon_port)
            rec.location = ', '.join(location_parts) if location_parts else 'N/A'

            # MAC Address (from ONT serial or calling station id)
            mac = ''
            if hasattr(user, 'ont_mac') and user.ont_mac:
                mac = user.ont_mac
            elif rec.circuit_id_mac:
                # Extract MAC from circuit_id_mac (format: "called / calling")
                parts = rec.circuit_id_mac.split('/')
                if len(parts) > 1:
                    mac = parts[1].strip()
            rec.mac_address = mac

            # Authentication options (assuming enabled if values are set)
            rec.mac_auth_enabled = bool(mac)
            rec.port_auth_enabled = bool(rec.login_port or user.olt_login_port)

            # VLAN ID (extract from login_port or nas_port)
            vlan = ''
            if rec.login_port and ':' in rec.login_port:
                vlan = rec.login_port.split(':')[-1]
            elif user.partner_id and user.partner_id.access_device_id:
                # Try to get VLAN from access device
                device = user.partner_id.access_device_id
                if hasattr(device, 'internet_vlan') and device.internet_vlan:
                    vlan = str(device.internet_vlan)
            rec.vlan_id = vlan
            rec.vlan_auth_enabled = bool(vlan)

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
        """Read për form view with computed fields support."""
        if not self.ids:
            return []

        # Get basic data from search_read
        data = self.search_read(domain=[('id', 'in', self.ids)], fields=fields)
        if not data:
            return []

        # Create temporary recordsets to compute fields
        for rec_data in data:
            # Create a browse record with the data
            rec = self.browse(rec_data['id'])
            # Manually set the data (simulating a real record)
            rec._cache.update(rec_data)
            # Compute user details
            rec._compute_user_details()
            # Update the data dict with computed values
            rec_data.update({
                'location': rec.location,
                'mac_address': rec.mac_address,
                'mac_auth_enabled': rec.mac_auth_enabled,
                'port_auth_enabled': rec.port_auth_enabled,
                'vlan_id': rec.vlan_id,
                'vlan_auth_enabled': rec.vlan_auth_enabled,
                'radius_user_id': rec.radius_user_id.id if rec.radius_user_id else False,
                'partner_id': rec.partner_id.id if rec.partner_id else False,
            })

        return data

    # Access control bypass
    def check_access_rights(self, operation, raise_exception=True):
        return True

    def check_access_rule(self, operation):
        return

    def _check_company_auto(self):
        return

    def action_view_customer(self):
        """Navigate to customer/partner record"""
        self.ensure_one()
        # Compute user details first
        self._compute_user_details()

        if not self.partner_id:
            # Try to find partner by username
            user = self.env['asr.radius.user'].sudo().search([('username', '=', self.username)], limit=1)
            if user and user.partner_id:
                partner_id = user.partner_id.id
            else:
                raise UserError(_("No customer found for this username."))
        else:
            partner_id = self.partner_id.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer: %s') % self.username,
            'res_model': 'res.partner',
            'res_id': partner_id,
            'view_mode': 'form',
            'target': 'current',
        }
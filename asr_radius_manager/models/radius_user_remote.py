# -*- coding: utf-8 -*-
"""
✅ FIXED: RADIUS Users Remote model që funksionon në UI për Odoo 18.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import zlib

_logger = logging.getLogger(__name__)


def _id_from_username(u: str) -> int:
    """ID deterministik pozitiv për Odoo, bazuar në username (pa tabelë PG)."""
    return (zlib.crc32((u or "").encode("utf-8")) & 0xFFFFFFFF) or 1


class AsrRadiusUserRemote(models.Model):
    """
    RADIUS Users (MySQL) – read-only nga MariaDB (radacct/radusergroup/radreply).
    Pa tabelë në Postgres: _auto=False dhe override i search/read/search_read.
    """
    _name = 'asr.radius.user.remote'
    _description = 'RADIUS Users (MySQL)'
    _rec_name = 'username'
    _auto = False
    _check_company_auto = False
    _log_access = False

    # Fusha për UI
    username = fields.Char(string="Username", readonly=True)
    status = fields.Selection([('ONLINE', 'ONLINE'), ('OFFLINE', 'OFFLINE')],
                              string="PPPoe Status", readonly=True)
    login_on = fields.Datetime(string="Login on", readonly=True)
    ip_address = fields.Char(string="IP (current)", readonly=True)
    current_group = fields.Char(string="Current RADIUS Group", readonly=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 compute='_compute_company', store=False)

    def _compute_company(self):
        for rec in self:
            rec.company_id = self.env.company.id

    @api.model
    def _get_radius_conn(self):
        try:
            return self.env.company._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % e)

    @api.model
    def _domain_to_filters(self, domain):
        """Kthen filtrat: username '=', username like, dhe 'id in'."""
        u_eq, u_like = None, None
        want_ids = None
        for item in (domain or []):
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            f, op, val = item
            if f == 'username':
                if op == '=':
                    u_eq = str(val)
                elif op in ('like', 'ilike'):
                    u_like = str(val)
            elif f == 'id':
                if op == '=' and val is not None:
                    want_ids = {int(val)}
                elif op == 'in':
                    seq = list(val or [])
                    want_ids = set(int(x) for x in seq) if seq else None
        return u_eq, u_like, want_ids

    @api.model
    def _base_sql(self, username_eq=None, username_like=None):
        where_clauses, params = [], []
        if username_eq:
            where_clauses.append("username = %s")
            params.append(username_eq)
        elif username_like:
            where_clauses.append("username LIKE %s")
            params.append(f"%{username_like}%")
        sub_where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT
              ra.username AS username,
              CASE
                WHEN (ra.acctstoptime IS NULL OR ra.acctstoptime='0000-00-00 00:00:00')
                     AND (ra.acctupdatetime IS NULL OR ra.acctupdatetime > NOW() - INTERVAL 15 MINUTE)
                  THEN 'ONLINE' ELSE 'OFFLINE'
              END                           AS status,
              ra.acctstarttime              AS login_on,
              NULLIF(ra.framedipaddress,'') AS ip_address,
              (SELECT g.groupname FROM radusergroup g
                 WHERE g.username=ra.username
                 ORDER BY g.priority ASC LIMIT 1) AS current_group
            FROM radacct ra
            JOIN (
              SELECT username, MAX(acctstarttime) AS last_start
              FROM radacct
              {sub_where}
              GROUP BY username
            ) t ON t.username=ra.username AND t.last_start=ra.acctstarttime
        """
        return sql, params

    # ---------------------- Access rules bypass ----------------------
    def check_access_rights(self, operation, raise_exception=True):
        return True

    def check_access_rule(self, operation):
        return

    def _check_company_auto(self):
        return

    # ---------------------- ORM overrides ----------------------
    @api.model
    def search(self, domain=None, offset=0, limit=None, order=None, count=False):
        """✅ UI thërret search→read."""
        u_eq, u_like, want_ids = self._domain_to_filters(domain)

        if want_ids is not None and len(want_ids) == 0:
            return self.browse([])

        if count:
            return self.search_count(domain)

        try:
            rows = self.with_context(prefetch_fields=False).search_read(
                domain=domain, fields=['id', 'username'], offset=offset, limit=limit, order=order)
            ids = [r['id'] for r in rows if r.get('id')]
            if want_ids is not None:
                ids = [i for i in ids if i in want_ids]
            return self.browse(ids)
        except Exception as e:
            _logger.error("Search failed: %s", e, exc_info=True)
            return self.browse([])

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """✅ Lexon direkt nga MySQL."""
        u_eq, u_like, want_ids = self._domain_to_filters(domain)
        default_fields = ["id", "username", "status", "login_on", "ip_address", "current_group"]
        fields = fields or default_fields

        if want_ids is not None and len(want_ids) == 0:
            return []

        sql, params = self._base_sql(u_eq, u_like)

        ALLOWED_ORDER = {'username': 'ra.username', 'status': 'status', 'login_on': 'ra.acctstarttime'}
        order_parts = []
        if order:
            for seg in order.split(','):
                parts = seg.strip().split()
                if not parts:
                    continue
                col, direction = parts[0], parts[1].upper() if len(parts) > 1 else 'ASC'
                if col in ALLOWED_ORDER and direction in ('ASC', 'DESC'):
                    order_parts.append(f"{ALLOWED_ORDER[col]} {direction}")

        sql += f" ORDER BY {', '.join(order_parts)}" if order_parts else " ORDER BY ra.username ASC"

        if limit:
            sql += f" LIMIT {int(limit)}"
        if offset:
            sql += f" OFFSET {int(offset)}"

        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()
            cur.execute(sql, params if params else None)
            rows = cur.fetchall() or []
            dict_row = isinstance(rows[0], dict) if rows else False

            out = []
            for row in rows:
                if dict_row:
                    u, st, lg, ip, grp = (row.get('username') or '', row.get('status') or 'OFFLINE',
                                         row.get('login_on'), row.get('ip_address') or '',
                                         row.get('current_group') or '')
                else:
                    u, st, lg, ip, grp = row[0] or '', row[1] or 'OFFLINE', row[2], row[3] or '', row[4] or ''

                rid = _id_from_username(u)
                out.append({'id': rid, 'username': u, 'status': st, 'login_on': lg,
                           'ip_address': ip, 'current_group': grp})

            if want_ids is not None:
                out = [r for r in out if r.get('id') in want_ids]

            if fields and fields != default_fields:
                want = set(fields) | {'id'}
                out = [{k: v for k, v in r.items() if k in want} for r in out]

            return out
        except Exception as e:
            _logger.error("search_read failed: %s", e, exc_info=True)
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
        _logger.info("=== Users Remote WEB_SEARCH_READ called ===")
        fields = list(specification.keys()) if specification else None
        records = self.search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order)
        _logger.info(f"Users Remote returning {len(records)} records")
        return {'records': records, 'length': len(records)}

    def read(self, fields=None, load='_classic_read'):
        """✅ Kthe rreshtat për ids e kërkuara."""
        if not self.ids:
            return []

        ids_want = set(int(i) for i in self.ids)
        sql, params = self._base_sql()
        conn = None
        try:
            conn = self._get_radius_conn()
            cur = conn.cursor()
            cur.execute(sql, params if params else None)
            rows = cur.fetchall() or []
            dict_row = isinstance(rows[0], dict) if rows else False

            out = []
            for row in rows:
                if dict_row:
                    u, st, lg, ip, grp = (row.get('username') or '', row.get('status') or 'OFFLINE',
                                         row.get('login_on'), row.get('ip_address') or '',
                                         row.get('current_group') or '')
                else:
                    u, st, lg, ip, grp = row[0] or '', row[1] or 'OFFLINE', row[2], row[3] or '', row[4] or ''

                rid = _id_from_username(u)
                if rid not in ids_want:
                    continue

                rec = {'id': rid, 'username': u, 'status': st, 'login_on': lg,
                      'ip_address': ip, 'current_group': grp}
                if fields:
                    rec = {k: v for k, v in rec.items() if k in set(fields) | {'id'}}
                out.append(rec)

            return out
        except Exception as e:
            _logger.error("read() failed: %s", e, exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    @api.model
    def search_count(self, domain=None):
        """✅ Count override."""
        username_eq, username_like, _ = self._domain_to_filters(domain)
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
            return int(row[0] if isinstance(row, (list, tuple)) else row.get('COUNT(*)') or 0)
        except Exception as e:
            _logger.error("Count failed: %s", e, exc_info=True)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    # ---------------------- Actions ----------------------
    def action_open_odoo_user(self):
        """Buton: hap rekordin Odoo sipas username."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('RADIUS Users'),
            'res_model': 'asr.radius.user',
            'view_mode': 'list,form',
            'domain': [('username', '=', self.username)],
            'target': 'current',
            'context': {'search_default_username': self.username},
        }
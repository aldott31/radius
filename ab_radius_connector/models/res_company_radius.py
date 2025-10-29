# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import AccessError, UserError

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None


class ResCompanyRadius(models.Model):
    _inherit = 'res.company'

    fr_db_host = fields.Char(string='DB Host')
    fr_db_port = fields.Integer(string='DB Port', default=3306)
    fr_db_name = fields.Char(string='DB Name')
    fr_db_user = fields.Char(string='DB User')
    fr_db_password = fields.Char(string='DB Password')
    fr_ssh_host = fields.Char(string='SSH Host', help='FreeRADIUS server SSH host (default: DB host)')
    fr_ssh_user = fields.Char(string='SSH User', default='root')
    fr_disconnect_secret = fields.Char(string='Disconnect Secret', default='testing123')
    fr_default_group = fields.Char(string='Default Group')
    fr_last_test_ok = fields.Boolean(string='Last Test OK', readonly=True)
    fr_last_error = fields.Text(string='Last Error', readonly=True)

    # 🆕 OLT Telnet Credentials (VETËM username/password)
    olt_telnet_username = fields.Char(
        string='OLT Username',
        default='bbone',
        help='Username for OLT Telnet access'
    )
    olt_telnet_password = fields.Char(
        string='OLT Password',
        help='Password for OLT Telnet access'
    )

    def _check_radius_admin(self):
        if not self.env.user.has_group('ab_radius_connector.group_ab_radius_admin'):
            raise AccessError(_("You don't have FreeRADIUS admin permissions"))

    def _get_direct_conn(self):
        self.ensure_one()
        if pymysql is None:
            raise UserError(_('PyMySQL not installed on server.'))
        missing = []
        for f in ('fr_db_host', 'fr_db_port', 'fr_db_name', 'fr_db_user'):
            if not getattr(self, f):
                missing.append(f)
        if missing:
            raise UserError(_('Missing DB settings: %s') % ', '.join(missing))
        return pymysql.connect(
            host=self.fr_db_host.strip(),
            port=int(self.fr_db_port or 3306),
            user=self.fr_db_user.strip(),
            password=self.fr_db_password or '',
            database=self.fr_db_name.strip(),
            charset='utf8mb4',
            cursorclass=DictCursor,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=True,
        )

    def action_fr_test_connection(self):
        self._check_radius_admin()
        self.ensure_one()
        try:
            conn = self._get_direct_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            self.sudo().write({'fr_last_test_ok': True, 'fr_last_error': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('FreeRADIUS'),
                    'message': _('Connection successful.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.sudo().write({'fr_last_test_ok': False, 'fr_last_error': str(e)})
            raise UserError(_('FreeRADIUS connection failed:\n%s') % (str(e),))

    def fr_get_mysql_params(self):
        self.ensure_one()
        if self.fr_db_host and self.fr_db_name and self.fr_db_user:
            return {
                'host': self.fr_db_host.strip(),
                'port': int(self.fr_db_port or 3306),
                'user': self.fr_db_user.strip(),
                'password': self.fr_db_password or '',
                'database': self.fr_db_name.strip(),
            }
        raise UserError(_('Configure FreeRADIUS DB settings on the company.'))
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

    def _get_direct_conn(self, retries=3, retry_delay=1.0):
        """✅ Get direct MySQL connection with retry logic

        Args:
            retries (int): Number of connection attempts (default: 3)
            retry_delay (float): Delay between retries in seconds (default: 1.0)

        Returns:
            pymysql.Connection: Database connection

        Raises:
            UserError: If connection fails after all retries
        """
        import time
        import logging
        _logger = logging.getLogger(__name__)

        self.ensure_one()

        if pymysql is None:
            raise UserError(_('PyMySQL not installed on server.'))

        # Validate required fields
        missing = []
        for f in ('fr_db_host', 'fr_db_port', 'fr_db_name', 'fr_db_user'):
            if not getattr(self, f):
                missing.append(f)
        if missing:
            raise UserError(_('Missing DB settings: %s') % ', '.join(missing))

        # Connection parameters
        conn_params = {
            'host': self.fr_db_host.strip(),
            'port': int(self.fr_db_port or 3306),
            'user': self.fr_db_user.strip(),
            'password': self.fr_db_password or '',
            'database': self.fr_db_name.strip(),
            'charset': 'utf8mb4',
            'cursorclass': DictCursor,
            'connect_timeout': 5,
            'read_timeout': 5,
            'write_timeout': 5,
            'autocommit': True,
        }

        last_error = None

        # ✅ Retry loop
        for attempt in range(1, retries + 1):
            try:
                _logger.debug(f'MySQL connection attempt {attempt}/{retries} to {conn_params["host"]}:{conn_params["port"]}')

                # Attempt connection
                conn = pymysql.connect(**conn_params)

                # ✅ Verify connection with a test query
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                        cursor.fetchone()
                except Exception as test_error:
                    conn.close()
                    raise test_error

                # Success
                if attempt > 1:
                    _logger.info(f'MySQL connection succeeded on attempt {attempt}/{retries}')

                return conn

            except pymysql.MySQLError as e:
                last_error = e
                error_code = e.args[0] if e.args else None

                # Log the error
                _logger.warning(
                    f'MySQL connection attempt {attempt}/{retries} failed: '
                    f'[{error_code}] {str(e)}'
                )

                # Don't retry for authentication errors or invalid database
                if error_code in (1045, 1049, 1044):  # Access denied, Unknown database, Access denied for DB
                    _logger.error(f'MySQL authentication/database error, not retrying: {e}')
                    raise UserError(_(
                        'MySQL Authentication Failed\n\n'
                        'Error: %(error)s\n\n'
                        'Please check:\n'
                        '• Database username and password are correct\n'
                        '• Database "%(db)s" exists\n'
                        '• User has permissions on database'
                    ) % {
                        'error': str(e),
                        'db': conn_params['database']
                    })

                # Retry for connection errors
                if attempt < retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff

            except Exception as e:
                last_error = e
                _logger.warning(
                    f'Unexpected error on attempt {attempt}/{retries}: {type(e).__name__}: {e}'
                )

                if attempt < retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5

        # ✅ All retries failed
        _logger.error(f'MySQL connection failed after {retries} attempts: {last_error}')

        raise UserError(_(
            'Cannot connect to RADIUS MySQL database after %(attempts)d attempts.\n\n'
            'Last error: %(error)s\n\n'
            'Connection details:\n'
            '• Host: %(host)s\n'
            '• Port: %(port)d\n'
            '• Database: %(db)s\n'
            '• User: %(user)s\n\n'
            'Please check:\n'
            '• MySQL server is running\n'
            '• Network connectivity from Odoo to MySQL\n'
            '• Firewall allows connections on port %(port)d\n'
            '• Credentials are correct'
        ) % {
            'attempts': retries,
            'error': str(last_error),
            'host': conn_params['host'],
            'port': conn_params['port'],
            'db': conn_params['database'],
            'user': conn_params['user']
        })

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
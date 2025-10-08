# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None


class MysqlConnector(models.Model):
    _name = 'mysql.connector'
    _description = 'Generic MySQL/MariaDB Connector'
    _rec_name = 'name'

    name = fields.Char(required=True)
    host = fields.Char(required=True, default='127.0.0.1')
    port = fields.Integer(required=True, default=3306)
    database = fields.Char(required=True)
    user = fields.Char(required=True)
    password = fields.Char()
    charset = fields.Char(default='utf8mb4')

    connect_timeout = fields.Integer(default=5)
    read_timeout = fields.Integer(default=10)
    write_timeout = fields.Integer(default=10)
    autocommit = fields.Boolean("Auto Commit", default=False)

    # Stats / status
    query_count = fields.Integer(readonly=True, default=0)
    last_test_success = fields.Boolean(readonly=True)
    last_error = fields.Text(readonly=True)
    last_test_date = fields.Datetime(readonly=True)

    # ------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------
    def _check_lib(self):
        if pymysql is None:
            raise UserError(_("PyMySQL is not available. Please install 'PyMySQL' python package."))

    def _get_connection(self):
        self.ensure_one()
        self._check_lib()
        try:
            return pymysql.connect(
                host=self.host,
                port=int(self.port or 3306),
                user=self.user,
                password=self.password or '',
                database=self.database,
                charset=self.charset or 'utf8mb4',
                cursorclass=DictCursor,
                connect_timeout=int(self.connect_timeout or 5),
                read_timeout=int(self.read_timeout or 10),
                write_timeout=int(self.write_timeout or 10),
                autocommit=bool(self.autocommit),
            )
        except Exception as e:
            raise UserError(_("Connection failed: %s") % e)

    def _execute_query(self, query, params=None, fetch=True, commit=True):
        """Low-level execution with optional fetch & commit."""
        self.ensure_one()
        connection = None
        try:
            connection = self._get_connection()
            with connection.cursor() as cursor:
                _logger.debug("Executing: %s params=%s", query, params)
                cursor.execute(query, params or ())
                if fetch:
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount

                if commit and not self.autocommit:
                    connection.commit()

                # stats
                self.sudo().write({'query_count': self.query_count + 1})
                return result
        except Exception as e:
            if connection and not self.autocommit:
                try:
                    connection.rollback()
                except Exception:
                    pass
            _logger.error("%s: Query failed: %s\nQuery: %s", self.name, e, query)
            raise UserError(_("Query execution failed: %s") % e)
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def test_connection(self):
        """UI action to test connection; returns notification client action."""
        self.ensure_one()
        try:
            self._execute_query("SELECT 1", fetch=True, commit=False)
            self.sudo().write({'last_test_success': True, 'last_error': False, 'last_test_date': fields.Datetime.now()})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to %s') % self.database,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.sudo().write({'last_test_success': False, 'last_error': str(e), 'last_test_date': fields.Datetime.now()})
            raise

    def execute_raw_query(self, query, params=None, fetch=True):
        self.ensure_one()
        is_select = isinstance(query, str) and query.strip().lower().startswith("select")
        return self._execute_query(query, params=params, fetch=fetch, commit=not is_select)

    # ----------------------------- CRUD -------------------------------------
    def create_record(self, table, values):
        """INSERT row and return affected rowcount (use raw for lastrowid if needed)."""
        self.ensure_one()
        if not values:
            raise UserError(_("No values provided for insert"))
        fields_list = list(values.keys())
        placeholders = ', '.join(['%s'] * len(fields_list))
        fields_str = ', '.join("`{}`".format(f) for f in fields_list)
        query = "INSERT INTO `{}` ({}) VALUES ({})".format(table, fields_str, placeholders)
        params = tuple(values[f] for f in fields_list)
        return self._execute_query(query, params=params, fetch=False, commit=True)

    def read_records(self, table, where=None, fields=None, limit=None, offset=None, order=None):
        """SELECT rows with simple equals WHERE."""
        self.ensure_one()
        fields = fields or ['*']
        cols = ', '.join("`{}`".format(f) if f != '*' else '*' for f in fields)
        query = "SELECT {} FROM `{}`".format(cols, table)
        params = []
        if where:
            parts = []
            for k, v in where.items():
                parts.append("`{}` = %s".format(k))
                params.append(v)
            if parts:
                query += " WHERE " + " AND ".join(parts)
        if order:
            query += " ORDER BY {}".format(order)
        if limit:
            query += " LIMIT {}".format(int(limit))
            if offset:
                query += " OFFSET {}".format(int(offset))
        return self._execute_query(query, params=tuple(params), fetch=True, commit=False)

    def update_record(self, table, values, where):
        """UPDATE with simple equals WHERE."""
        self.ensure_one()
        if not values:
            raise UserError(_("No values provided for update"))
        if not where:
            raise UserError(_("WHERE is required for update"))
        set_parts = ["`{}` = %s".format(k) for k in values]
        where_parts = ["`{}` = %s".format(k) for k in where]
        params = tuple(values.values()) + tuple(where.values())
        query = "UPDATE `{}` SET {} WHERE {}".format(
            table, ", ".join(set_parts), " AND ".join(where_parts)
        )
        return self._execute_query(query, params=params, fetch=False, commit=True)

    def delete_record(self, table, where):
        """DELETE with simple equals WHERE."""
        self.ensure_one()
        if not where:
            raise UserError(_("WHERE is required for delete"))
        parts = ["`{}` = %s".format(k) for k in where]
        params = tuple(where.values())
        query = "DELETE FROM `{}` WHERE {}".format(table, " AND ".join(parts))
        return self._execute_query(query, params=params, fetch=False, commit=True)

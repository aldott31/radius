import json
import requests
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)  # Set up logging for this model


class ResCompanyExtension(models.Model):
    _inherit = 'res.company'

    # Superset Configuration Fields
    ss_base_url = fields.Char(string='Superset Base URL', required=True, default='http://192.168.168.50:8088')
    ss_username = fields.Char(string='Username', required=True)
    ss_password = fields.Char(string='Password', required=True)
    ss_access_token = fields.Text(string='Access Token')
    ss_csrf_token = fields.Text(string='CSRF Token')
    ss_session_cookie = fields.Text(string='Session Token')
    ss_database_id = fields.Text(string='Database ID', default=2)
    session = requests.Session()
    
    gasc_username = fields.Char(string='GenieACS username', required=True, default='apiuser')
    gasc_password = fields.Char(string='GenieACS password', required=True, default='G3n1@sc.2025!!')
    gasc_url = fields.Char(string='GenieACS URL', required=True, default='https://tr069.abissnet.al')

    def login_to_superset(self):
        """Logs in to the Superset API and retrieves authentication tokens."""
        try:
            _logger.info("Logging into Superset at %s", self.ss_base_url)

            # Superset login URL
            login_url = f"{self.ss_base_url}/api/v1/security/login"
            payload = {
                'username': self.ss_username,
                'password': self.ss_password,
                'provider': 'db',
                "refresh": False
            }
            headers = {'Content-Type': 'application/json'}

            # Send login request
            response = self.session.post(login_url, json=payload, headers=headers)
            _logger.info(response.json())
            response.raise_for_status()

            login_data = response.json()
            if "access_token" not in login_data:
                _logger.error("Login failed: %s", login_data)
                raise UserError(_("Login failed: %s") % login_data)

            # Store authentication tokens
            self.ss_access_token = login_data["access_token"]

            # Retrieve CSRF Token
            csrf_url = f"{self.ss_base_url}/api/v1/security/csrf_token/"
            csrf_headers = {
                "Authorization": f"Bearer {self.ss_access_token}",
                "Content-Type": "application/json"
            }
            csrf_response = self.session.get(csrf_url, headers=csrf_headers)
            csrf_response.raise_for_status()
            csrf_data = csrf_response.json()

            if "result" not in csrf_data:
                _logger.error("CSRF Token retrieval failed: %s", csrf_data)
                raise UserError(_("CSRF Token retrieval failed: %s") % csrf_data)

            # Store CSRF token and session cookie
            self.ss_csrf_token = csrf_data['result']
            cookies = self.session.cookies.get_dict()
            self.ss_session_cookie = cookies.get("session", "")

            _logger.info("Successfully logged into Superset. Session Cookie: %s", self.ss_session_cookie)
            return self.get_request_headers()

        except requests.exceptions.RequestException as e:
            _logger.error("Error during Superset login: %s", str(e))
            raise UserError(_("Error during Superset login: %s") % str(e))

    def execute_superset_query(self, username, last_superset_call,imported_ids):
        """
        Executes a SQL query on Superset's API and returns the result.
        If authentication fails, it attempts to refresh the session.
        """
        try:
            _logger.info("Executing query for username: %s", username)

            # API endpoint for executing SQL queries
            api_url = f"{self.ss_base_url}/api/v1/sqllab/execute/"
            headers = self.get_request_headers()

            sql = f"""
                        SELECT t.id as imported_id,
                               t.operatorid as user_id,
                               t.acctid as customer_id,
                               u.username as ab_username,
                               u.fullname as customer_name,
                               u.email as email,
                               u.mobile as phone,
                               case when  t.status=1 then 5 else 1 end as stage_id,
                               case when  t.status=1 then 'Closed' else 'Inbox' end as stage_name,
                               t.start_date as create_date,
                               t.subject as subject,
                               t.description as description,
                               t.closed_solution,
                               t.close_date as end_date ,
                               t.update_date as last_update_date,
                               t.closedBy as assigned_user_id,
                               t.priority as priority
                        FROM troubleticket t
                        INNER JOIN users u ON t.acctid=u.acctid
                        WHERE u.username = '{username}'
                    """

            # sql = f"""
            #     SELECT * FROM troubleticket t INNER JOIN users u ON t.acctid=u.acctid WHERE u.username = 'abissnet'
            # """
            if imported_ids:
                imported_ids_tuple = tuple(imported_ids) if len(imported_ids) > 1 else f"({imported_ids[0]})"
                sql += f" AND t.id NOT IN {imported_ids_tuple}"

            sql += " limit 10 "

            payload = {
                "database_id": 2,  # Replace with actual database ID
                "sql": sql,
                "schema": "radius"
            }

            _logger.info("Sending SQL query to Superset API.")
            response = self.session.post(api_url, headers=headers, json=payload)

            _logger.info(sql)
            _logger.info(response.json())

            # Handle Unauthorized (401) - Re-authenticate and retry
            if response.status_code == 401:
                _logger.warning("401 Unauthorized. Refreshing session and retrying...")
                self.login_to_superset()
                headers = self.get_request_headers()
                response = self.session.post(api_url, headers=headers, json=payload)

            # Handle Bad Request (400) - Re-authenticate and retry
            if response.status_code == 400:
                _logger.error("400 Bad Request. Response: %s", response.text)
                self.login_to_superset()
                headers = self.get_request_headers()
                response = self.session.post(api_url, headers=headers, json=payload)

            # Raise for other HTTP errors
            response.raise_for_status()

            # Validate JSON response
            if response.text.strip():
                try:
                    return response.json()
                except json.JSONDecodeError:
                    _logger.error("Invalid JSON response: %s", response.text)
                    raise UserError(_("Superset API returned an invalid JSON response."))

            _logger.error("Empty response received from Superset API.")
            raise UserError(_("Empty response received from Superset API."))

        except requests.exceptions.RequestException as e:
            _logger.error("Error during Superset API request: %s", str(e))
            raise UserError(_("Error connecting to Superset API: %s") % str(e))

        except Exception as e:
            _logger.error("Unexpected error: %s", str(e))
            raise UserError(_("Unexpected error: %s") % str(e))

    def run_query(self, database_id, query, schema=None, query_limit=None):
        """Execute an SQL query."""
        try:

            api_url = f"{self.ss_base_url}/api/v1/sqllab/execute/"
            headers = self.get_request_headers()

            payload = {
                "database_id": database_id,
                "sql": query,
                "schema": schema,
            }
            if query_limit:
                payload["queryLimit"] = query_limit

            response = self.session.post(api_url, headers=headers, json=payload)

            if response.status_code == 401:
                _logger.warning("401 Unauthorized. Refreshing session and retrying...")
                self.login_to_superset()
                headers = self.get_request_headers()
                response = self.session.post(api_url, headers=headers, json=payload)

            # Handle Bad Request (400) - Re-authenticate and retry
            if response.status_code == 400:
                _logger.error("400 Bad Request. Response: %s", response.text)
                self.login_to_superset()
                headers = self.get_request_headers()
                response = self.session.post(api_url, headers=headers, json=payload)

            response.raise_for_status()
            result = response.json()

            # Check for query limit warnings
            if result.get("displayLimitReached", False):
                _logger.warning("Query limit reached. Consider adding a LIMIT clause.")
        except Exception as e:
            _logger.error("Unexpected error: %s", str(e))
            raise UserError(_("Unexpected error: %s") % str(e))
        return result

    def get_request_headers(self):
        """Generates headers for Superset API requests."""
        return {
            "X-CSRFToken": self.ss_csrf_token,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.ss_access_token}",
            "Cookie": f"session={self.ss_session_cookie}"
        }

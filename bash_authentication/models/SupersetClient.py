import requests
import logging

_logger = logging.getLogger(__name__)  # Set up logging for this model


class SupersetClient:
    """A Superset REST API Client."""

    def __init__(
        self,
        host,
        username=None,
        password=None,
        token=None,
        provider="db",
        verify=True,
    ):
        self.host = host
        self.base_url = self.join_urls(host, "api/v1")
        self.username = username
        self._password = password
        self.token = token
        self.provider = provider
        self.verify = verify
        self.session = None

    @staticmethod
    def join_urls(*args) -> str:
        """Join multiple URL parts together."""
        parts = [str(part).strip("/") for part in args]
        if str(args[-1]).endswith("/"):
            parts.append("")  # Preserve trailing slash
        return "/".join(parts)

    def authenticate(self):
        """Authenticate with Superset and retrieve tokens."""
        if not self.username or not self._password:
            raise ValueError("Username and password are required for authentication.")

        response = requests.post(
            self.login_endpoint,
            json={
                "username": self.username,
                "password": self._password,
                "provider": self.provider,
                "refresh": "true",
            },
            verify=self.verify,
        )
        response.raise_for_status()
        tokens = response.json()
        self.token = tokens["access_token"]
        self.session_cookie = response.cookies.get("session")
        return self.token

    def get_csrf_token(self):
        """Fetch CSRF token for authenticated session."""
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            self.join_urls(self.base_url, "security/csrf_token/"),
            headers=headers,
            verify=self.verify,
        )
        response.raise_for_status()
        csrf_token = response.json().get("result")
        if not csrf_token:
            raise RuntimeError("Failed to fetch CSRF token.")
        return csrf_token

    def create_session(self):
        """Create an authenticated session with CSRF token."""
        if not self.token:
            self.authenticate()

        csrf_token = self.get_csrf_token()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "X-CSRFToken": csrf_token,
                "Referer": f"{self.base_url}",
            }
        )
        return self.session

    def run_query(self, database_id, query, schema=None, query_limit=None):
        """Execute an SQL query."""
        if not self.session:
            self.create_session()

        payload = {
            "database_id": database_id,
            "sql": query,
            "schema": schema,
        }
        if query_limit:
            payload["queryLimit"] = query_limit

        response = self.session.post(self._sql_endpoint, json=payload, verify=self.verify)
        response.raise_for_status()
        result = response.json()

        # Check for query limit warnings
        if result.get("displayLimitReached", False):
            _logger.warning("Query limit reached. Consider adding a LIMIT clause.")
        return result

    @property
    def login_endpoint(self):
        return self.join_urls(self.base_url, "security/login")

    @property
    def refresh_endpoint(self):
        return self.join_urls(self.base_url, "security/refresh")

    @property
    def _sql_endpoint(self):
        return self.join_urls(self.host, "superset/sql_json/")


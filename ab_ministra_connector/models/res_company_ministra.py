# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

try:
    import requests
    from requests.auth import HTTPBasicAuth
except Exception:
    requests = None
    HTTPBasicAuth = None


class ResCompanyMinistra(models.Model):
    _inherit = "res.company"

    ministra_api_base_url = fields.Char(
        string="Ministra API Base URL",
        help="Example: http://<host>:<port>/stalker_portal/api",
    )
    ministra_api_username = fields.Char(string="Ministra API Username")
    ministra_api_password = fields.Char(string="Ministra API Password")

    ministra_api_timeout = fields.Integer(string="API Timeout (seconds)", default=10)
    ministra_last_test_ok = fields.Boolean(string="Last Test OK", readonly=True)
    ministra_last_error = fields.Text(string="Last Error", readonly=True)

    # ------------------------
    # Internal helpers
    # ------------------------

    def _check_ministra_admin(self):
        if not self.env.user.has_group("ab_ministra_connector.group_ab_ministra_admin"):
            raise AccessError(_("You don't have Ministra admin permissions."))

    def _check_requests_lib(self):
        if requests is None or HTTPBasicAuth is None:
            raise UserError(_("Python package 'requests' is not available on this server."))

    def _ministra_get_base_url(self):
        """Normalize base URL.

        Accepts common pastes like:
        - http://host/stalker_portal/api
        - http://host/stalker_portal/api/accounts
        - http://host/stalker_portal/api/accounts/
        """
        self.ensure_one()
        base = (self.ministra_api_base_url or "").strip()
        if not base:
            raise UserError(_("Configure Ministra API Base URL on the company."))

        base = base.rstrip("/")

        # If user pasted a resource URL, strip the last segment.
        last = base.rsplit("/", 1)[-1].lower()
        known_resources = {
            "accounts",
            "users",
            "tariffs",
            "services_package",
            "account_subscription",
            "send_event",
            "stb",
            "stb_msg",
            "itv",
            "itv_subscription",
            "stb_modules",
        }
        if last in known_resources:
            base = base.rsplit("/", 1)[0]

        return base

    def _ministra_auth(self):
        self.ensure_one()
        if not (self.ministra_api_username and self.ministra_api_password):
            raise UserError(_("Configure Ministra API username/password on the company."))
        self._check_requests_lib()
        return HTTPBasicAuth(self.ministra_api_username.strip(), self.ministra_api_password)

    def ministra_api_call(self, method, resource, identifiers=None, data=None, params=None, timeout=None):
        """Generic Ministra REST API v1 call.

        Returns:
            results (list|dict|bool|str|int): the 'results' key from Ministra response

        Raises:
            UserError on any transport / HTTP / API error.
        """
        self.ensure_one()
        self._check_requests_lib()

        method = (method or "GET").upper()
        resource = (resource or "").strip().strip("/")
        if not resource:
            raise UserError(_("Missing resource for Ministra API call."))

        base = self._ministra_get_base_url()

        url = f"{base}/{resource}"

        if identifiers:
            if isinstance(identifiers, (list, tuple, set)):
                identifiers = ",".join(str(x) for x in identifiers)
            url = f"{url}/{identifiers}"
        else:
            # Some resources in docs show POST on a trailing slash
            if method == "POST":
                url = f"{url}/"

        timeout = int(timeout or self.ministra_api_timeout or 10)

        try:
            resp = requests.request(
                method=method,
                url=url,
                auth=self._ministra_auth(),
                data=data or {},
                params=params or {},
                timeout=timeout,
            )
        except requests.exceptions.RequestException as e:
            _logger.exception("Ministra API transport error: %s", e)
            raise UserError(_("Ministra API transport error:\n%s") % (str(e),))

        # HTTP level errors
        if resp.status_code == 401:
            raise UserError(_("Ministra API: 401 Unauthorized (check username/password)."))
        if resp.status_code >= 400:
            raise UserError(_("Ministra API HTTP error %s:\n%s") % (resp.status_code, resp.text))

        try:
            payload = resp.json()
        except Exception:
            raise UserError(_("Ministra API returned non-JSON response:\n%s") % (resp.text,))

        if payload.get("status") != "OK":
            raise UserError(_("Ministra API error:\n%s") % (payload.get("error") or payload))

        return payload.get("results")

    # ------------------------
    # UI Actions
    # ------------------------

    def action_ministra_test_connection(self):
        """Test by calling GET /tariffs (lightweight and always available when API is enabled)."""
        self._check_ministra_admin()
        self.ensure_one()

        try:
            results = self.ministra_api_call("GET", "tariffs")
            count = len(results) if isinstance(results, list) else 1
            self.sudo().write({"ministra_last_test_ok": True, "ministra_last_error": False})
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Ministra Connection"),
                    "message": _("Connection OK. Tariff plans returned: %s") % count,
                    "sticky": False,
                    "type": "success",
                },
            }
        except Exception as e:
            self.sudo().write({"ministra_last_test_ok": False, "ministra_last_error": str(e)})
            raise

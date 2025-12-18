from datetime import datetime

from odoo import models, fields, api, _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def convert_datetime(iso_date):
    """Convert 'YYYY-MM-DDTHH:MM:SS' to 'YYYY-MM-DD HH:MM:SS'"""
    if iso_date:
        try:
            return datetime.strptime(iso_date, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            _logger.warning("Invalid datetime format: %s", iso_date)
            return None
    return None


class HelpdeskTicketCreator(models.Model):
    _inherit = 'ticket.helpdesk'

    imported_id = fields.Integer(string='Imported ID', readonly=True)

    def create_new_ticket(self, response_data, customer):
        if response_data.get("status") != "success":
            _logger.error("Superset query failed: %s", response_data)
            raise UserError(_("Superset query execution failed."))

        query_results = response_data.get("data", [])
        if not query_results:
            _logger.warning("No data returned from Superset query.")
            return []

        # 🔹 Process the data and store it in Odoo

        tickets_created = []
        for item in query_results:
            ex_ticket = self.search([("imported_id", "=", item.get("imported_id"))], limit=1)
            if ex_ticket:
                continue

            ticket_vals = {
                "imported_id": item.get("imported_id"),
                "subject": item.get("subject", "No Subject"),
                "x_closed_solution": item.get("closed_solution", ""),
                "customer_name": item.get("customer_name", ""),
                "email": item.get("email", ""),
                "x_acctid": item.get("customer_id", ""),
                "end_date": convert_datetime(item.get("end_date")),
                "phone": item.get("phone", ""),
                "create_date": convert_datetime(item.get("create_date")),
                "start_date": convert_datetime(item.get("create_date")),
                "stage_id": item.get("stage_id"),
                "description": item.get("description", "No Description"),
                "priority": str(item.get("priority", "2")),  # Default to medium priority
                "customer_id": customer.id,
                "category_id": None,  # Set category if needed
            }
            ticket = self.create(ticket_vals)
            tickets_created.append(ticket.id)
            _logger.info(f"Created Helpdesk Ticket ID: {ticket.id} - {ticket.name}")

        return tickets_created  # Return the list of created ticket IDs

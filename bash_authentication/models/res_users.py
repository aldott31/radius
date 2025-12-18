from odoo import fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)  # Set up logging for this model


class ResUsers(models.Model):
    _inherit = 'res.users'

    email = fields.Char(string='Email', help='Your email address')
    phone = fields.Char(string='Phone', help='Your phone number')
    last_superset_call = fields.Date(string='Last Superset Call')

    def call_superset_query(self):
        """
        Calls the execute_superset_query method from res.company
        using the current user's username.
        """
        if not self.company_id:
            raise UserError(_('No associated company found for this user.'))

        try:
            # Call the company's execute_superset_query method
            customer = self.partner_id

            imported_ids = self.env["ticket.helpdesk"].search([("customer_id", "=", customer.id)]).mapped("imported_id")
            _logger.info(f"Imported IDs for customer_id={customer.id}: {imported_ids}")

            result = self.company_id.execute_superset_query(self.login, self.last_superset_call, imported_ids)
            self.env['ticket.helpdesk'].create_new_ticket(result, customer=customer)
            #_logger.info('Superset Query Result: %s', result)
            return result
        except Exception as e:
            _logger.error('Error executing Superset query: %s', str(e))
            raise UserError(_('Failed to execute Superset query: %s') % str(e))

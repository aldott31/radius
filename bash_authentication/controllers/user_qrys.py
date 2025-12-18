import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)


class SupersetAPI(http.Controller):

    @http.route('/api/get_tickets', type='json', auth='user', methods=['POST'], csrf=False)
    def call_superset_query_api(self, **kwargs):
        """
        API to trigger Superset Query Execution.
        Expected payload:
        {
            "user_id": 1
        }
        """
        try:
            user = request.env.user
            if not user.id:
                return {
                    "status": "error",
                    'message': "user_id is required",
                    "data": []
                }

            if not user.company_id:
                return {
                    "status": "error",
                    'message': "No associated company found for this user",
                    "data": []
                }

            # Get the customer associated with the user
            customer = user.partner_id

            # Get existing imported IDs to avoid duplicates
            imported_ids = request.env["ticket.helpdesk"].sudo().search([
                ("customer_id", "=", customer.id)
            ]).mapped("imported_id")

            _logger.info(f"Imported IDs for customer_id={customer.id}: {imported_ids}")

            # Execute Superset query
            result = user.company_id.execute_superset_query(user.login, user.last_superset_call, [])
            request.env["ticket.helpdesk"].sudo().create_new_ticket(result, customer=customer)

            tickets = request.env["ticket.helpdesk"].sudo().search([
                ("customer_id", "=", customer.id)], order="create_date DESC"
            )

            # Convert recordset to a list of dictionaries
            ticket_data = [{
                "id": ticket.id,
                "imported_id": ticket.imported_id,
                "name": ticket.name,
                "subject": ticket.subject,
                "description": ticket.description,
                # "solution": ticket.x_closed_solution,
                "priority": ticket.priority,
                "stage_id": {"id": ticket.stage_id.id, "name": ticket.stage_id.name},
                "create_date": ticket.create_date.strftime("%Y-%m-%d %H:%M:%S") if ticket.create_date else None,
            } for ticket in tickets]

            return {
                "status": "success",
                "data": ticket_data
            }
        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }

    @http.route('/api/create_ticket', type='json', auth='user', methods=['POST'], csrf=False)
    def create_ticket(self, **kwargs):
        try:
            user = request.env.user
            if not user.id:
                return {
                    "status": "error",
                    'message': "user_id is required",
                    "data": []
                }

            if not user.company_id:
                return {
                    "status": "error",
                    'message': "No associated company found for this user",
                    "data": []
                }

            data = json.loads(request.httprequest.data.decode('utf-8'))
            subject = data.get('subject')
            description = data.get('description')

            customer = user.partner_id

            ticket_vals = {
                "subject": subject,
                "description": description,
                "customer_id": customer.id,
                "stage_id": 1,
                "create_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            current_time = datetime.now()
            formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")

            sql_user = f"SELECT * FROM users where username = '{user.login}'"

            user_id = user.company_id.run_query(2, sql_user, 'radius').get('data')[0].get('acctid')

            sql = f"INSERT INTO troubleticket(subject, description, acctid, start_date, status, assigned_to_department, operatorid) VALUES('{subject}', '{description}', {user_id}, '{formatted_time}' , 0, 2, 1553); SELECT LAST_INSERT_ID(); "

            response = user.company_id.run_query(2, sql, 'radius')

            if(response.get('status') == 'success'):

                id = response.get('data')[0].get('LAST_INSERT_ID()')

                _logger.info(f"Created ticket with id: {id}")

                sql_actions = f"INSERT INTO troubleticket_actions(tt_id, assigned_to_department, date, operator) VALUES('{id}', 2, '{formatted_time}', 1553)"

                response_action = user.company_id.run_query(2, sql_actions, 'radius')

                if(response_action.get('status') == 'success'):

                    ticket = request.env["ticket.helpdesk"].sudo().create(ticket_vals)

                    return {
                        "status": "success",
                        "data": ticket
                    }

        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
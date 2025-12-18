import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)

class PaymentAPI(http.Controller):

    @http.route('/api/get_payment', type='json', auth='user', methods=['POST'], csrf=False)
    def call_superset_query_api(self, **kwargs):
        try:
            user = request.env.user
            sql = f"SELECT (SELECT COUNT(*) FROM active_payments t INNER JOIN users u ON t.acctid = u.acctid WHERE u.username = '{user.login}') AS pagesa_ne_total, t.start_date, t.stop_date, t.monthly_fee as pagesa_aktuale_mujore FROM active_payments t INNER JOIN users u ON t.acctid = u.acctid WHERE u.username = '{user.login}' ORDER BY t.id DESC LIMIT 1;"
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
            response = user.company_id.run_query(2, sql, 'radius')
            if response.get('data') and response.get('status') == 'success':
                data = response.get('data')[0]
                payment = {
                    "pagesa_ne_total": data.get('pagesa_ne_total'),
                    "start_date": data.get('start_date'),
                    "stop_date": data.get('stop_date'),
                    "pagesa_aktuale_mujore": data.get('pagesa_aktuale_mujore')
                }
                return {
                        "status": "success",
                        "data": payment
                    }
        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class ParentalControlAPI(http.Controller):

    @http.route('/api/get_parental', type='json', auth='user', methods=['POST'], csrf=False)
    def get_parental_control(self, **kwargs):
        try:
            user = request.env.user

            current_date = datetime.now()
            
            # Get current month
            current_month = current_date.month
            current_year = current_date.year
            current_str = f"{current_year}_{current_month}"
            current_postpaid = f"{current_year}_{current_month}_postpaid"

            # Get last month 
            last_date = current_date - relativedelta(months=1)
            last_month = last_date.month
            last_year = last_date.year
            last_str = f"{last_year}_{last_month}"
            last_postpaid = f"{last_year}_{last_month}_postpaid"


            sql = f"SELECT NASIPAddress as server,FramedIpAddress as ip,67 as plan,username,AcctStartTime FROM {current_postpaid} WHERE username = '{user.login}' AND AcctStopTime IS NULL UNION ALL SELECT NASIPAddress as server,FramedIpAddress as ip,67 as plan,username,AcctStartTime FROM {last_postpaid} WHERE username = '{user.login}' AND AcctStopTime IS NULL ORDER BY AcctStartTime DESC LIMIT 1;"
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
            response = user.company_id.run_query(3, sql, 'otello')
            if response.get('data') and response.get('status') == 'success':
                data = response.get('data')[0]
                parental = {
                    "server": data.get('server'),
                    "ip": data.get('ip'),
                    "plan": data.get('plan'),
                    "username": data.get('username'),
                    "AcctStartTime": data.get('AcctStartTime')
                }
                return {
                    "status": "success",
                    "data": parental
                }
        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
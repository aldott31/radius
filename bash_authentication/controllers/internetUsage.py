import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class InternetUsageAPI(http.Controller):

    @http.route('/api/get_internet_usage', type='json', auth='user', methods=['POST'], csrf=False)
    def get_internet_usage(self, **kwargs):
        try:
            user = request.env.user

            data = json.loads(request.httprequest.data.decode('utf-8'))

            current_year = data.get('year')
            current_month = data.get('month')

            pagination = data.get('pagination')
            page = pagination.get('page')
            size = pagination.get('size')

            offset = (page - 1) * size

            # Get current month
            current_postpaid = f"{current_year}_{current_month}_postpaid"

            sql = (f"SELECT AcctStartTime AS start_date,AcctStopTime AS stop_date,SUM(AcctInputOctets + AcctOutputOctets) / 1000000000 AS usage_gb,"
                   f"TIMEDIFF(AcctStopTime, AcctStartTime) AS session_time,NASIPAddress AS nas_ip_address,FramedIPAddress AS ip_address,"
                   f"(SELECT SUM(AcctInputOctets + AcctOutputOctets) / 1000000000 FROM `{current_postpaid}` WHERE UserName = '{user.login}') AS totali_gb FROM "
                   f"`{current_postpaid}` WHERE UserName = '{user.login}' AND MONTH(AcctStartTime) = '{current_month}' AND YEAR(AcctStartTime) = '{current_year}' GROUP BY AcctStartTime, AcctStopTime, NASIPAddress, FramedIPAddress ORDER BY AcctStartTime DESC LIMIT {size} OFFSET {offset};")

            sql_total = f"SELECT COUNT(*) AS total_rows FROM ( SELECT 1 FROM `{current_postpaid}` WHERE UserName = '{user.login}' GROUP BY AcctStartTime, AcctStopTime, NASIPAddress, FramedIPAddress ) AS total_count;"
            
            _logger.info(sql)

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
            
            datalist = []

            response = user.company_id.run_query(3, sql, 'otello')
            
            _logger.info(response)
            
            response_total = user.company_id.run_query(3, sql_total, 'otello')

            if response.get('data') and response.get('status') == 'success':
                datas = response.get('data')
                for data in datas:
                    usage = {
                        "start_date": data.get('start_date'),
                        "stop_date": data.get('stop_date'),
                        "usage_gb": data.get('usage_gb'),
                        "session_time": data.get('session_time'),
                        "nas_ip_address": data.get('nas_ip_address'),
                        "ip_address": data.get('ip_address'),
                        "totali_gb": data.get('totali_gb')
                    }
                    datalist.append(usage)

            _logger.info(datalist[0])
            _logger.info(response_total)
            return {
                "status": "success",
                "data": datalist,
                "totali_gb": datalist[0].get('totali_gb'),
                "total_size": response_total.get('data')[0].get('total_rows')
            }
        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
            
            
    @http.route('/api/get_packages', type='json', auth='user', methods=['POST'], csrf=False)
    def get_package(self, **kwargs):
        try:
            user = request.env.user

            sql = (f"SELECT t.id, t.acctid as customer_id, u.username as ab_username, u.fullname as customer_name, u.email as email, u.mobile as phone, case when pl.name <> '' then pl.name else '-' end as internet_plan_name, case when tpl.name <> '' then tpl.name else '-' end as tv_plan_name, case when t.voice_plan_id <>0 then 'Standard' else '-' end as voice_plan_name, case when t.static_ip <>0 then 'Po' else 'Jo' end as ip_statike FROM active_payments t INNER JOIN users u ON t.acctid=u.acctid left join plans pl on (t.internet_plan_id<>0 and t.internet_plan_id=pl.id and t.active=1) left join tv_plans tpl on (t.tv_plan_id<>0 and t.tv_plan_id=tpl.id and t.active=1) where u.username='{user.login}' and t.active=1 order by t.`id` ASC limit 10;")


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
            
            datalist = []

            response = user.company_id.run_query(2, sql, 'radius')

            if response.get('data') and response.get('status') == 'success':
                datas = response.get('data')
                for data in datas:
                    usage = {
                        "customer_id": data.get('customer_id'),
                        "ab_username": data.get('ab_username'),
                        "customer_name": data.get('customer_name'),
                        "email": data.get('email'),
                        "phone": data.get('phone'),
                        "internet_plan_name": data.get('internet_plan_name'),
                        "tv_plan_name": data.get('tv_plan_name'),
                        "voice_plan_name": data.get('voice_plan_name'),
                        "ip_statike": data.get('ip_statike')
                    }
                    datalist.append(usage)

            return {
                "status": "success",
                "data": datalist
            }
        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
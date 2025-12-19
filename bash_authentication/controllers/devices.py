import json
import logging
from http.client import responses

from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
import requests
from requests.auth import HTTPBasicAuth
import urllib.parse

_logger = logging.getLogger(__name__)

def safe_get(dct, *keys):
      """Safely navigate nested dictionaries, return empty string if any key is missing."""
      for key in keys:
          if not isinstance(dct, dict):
              return ""
          dct = dct.get(key)
          if dct is None:
              return ""
      return dct.get("_value", "") if isinstance(dct, dict) else dct

class DevicesApi(http.Controller):

    @http.route('/api/get_new_devices', type='json', auth='user', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors="*")
    def get_new_devices(self, **kwargs):
        try:

            user = request.env.user

            url = f"{user.company_id.gasc_url}/devices?query={{\"_tags\":\"{user.login}\"}}"

            response = requests.get(url, auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password))

            if response.status_code == 200:
                
                one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
                formatted_time = one_minute_ago.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                
                query_dict = {
                    "_tags": user.login,
                    "_lastInform": {
                        "$gt": formatted_time
                    }
                }
                
                query_json = json.dumps(query_dict)
                
                url_status = f"{user.company_id.gasc_url}/devices?query={query_json}"
                
                response_status = requests.get(url_status, auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password))

                all_devices_data = response.json()
                _logger.info("API response (all devices): %s", all_devices_data)

                # Create a set of device IDs from the API for efficient lookup
                api_device_ids = {device.get("_id") for device in all_devices_data}

                # === STEP 2: Find and delete obsolete devices in Odoo ===
                # Get all devices currently stored in Odoo for this user
                stored_devices = request.env["device"].sudo().search([("user", "=", user.id)])

                devices_to_delete = request.env["device"].sudo()
                for device in stored_devices:
                    if device.device_id not in api_device_ids:
                        devices_to_delete += device

                if devices_to_delete:
                    _logger.info("Deleting %s obsolete devices for user %s", len(devices_to_delete), user.login)
                    devices_to_delete.unlink()

                # --- PATCHED BLOCK ---
                if response_status.status_code == 200:
                    data = response_status.json()
                    device_status = bool(data)
                else:
                    data = []
                    device_status = False
                # --- END PATCHED BLOCK ---

                for device in data:
                
                    _logger.info("Device: %s", device)
                    device_id = device.get("_id")
                    device_manufacturer = device.get("_deviceId").get("_Manufacturer")
                                    
                    if device_manufacturer == "ZTE":
                        device_name_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "SSID")
                        _logger.info(device_name_24)
                        
                        device_name_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "5", "SSID")
                        _logger.info(device_name_5)
                        
                        device_pass_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "PreSharedKey", "1", "KeyPassphrase")
                        _logger.info(device_pass_24)
                        
                        device_pass_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "5", "PreSharedKey", "1", "KeyPassphrase")
                        _logger.info(device_pass_5)
                        
                        dns = safe_get(device, "InternetGatewayDevice", "DNS", "X_ZTE-COM_IPv4DNSServer1") + "," + safe_get(device, "InternetGatewayDevice", "DNS", "X_ZTE-COM_IPv4DNSServer2")
                        device_wifi_status_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "Enable")
                        device_wifi_status_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "5", "Enable")
                    
                    else:
                        device_name_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "SSID")
                        device_name_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "3", "SSID")
                        
                        device_pass_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "X_TP_PreSharedKey")
                        device_pass_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "3", "X_TP_PreSharedKey")
                        
                        dns = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "LANHostConfigManagement", "DNSServers")
                        device_wifi_status_24 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "1", "Enable")
                        device_wifi_status_5 = safe_get(device, "InternetGatewayDevice", "LANDevice", "1", "WLANConfiguration", "3", "Enable")

                    device_val = {
                        "device_id": device_id,
                        "device_name_24": device_name_24,
                        "device_name_5": device_name_5,
                        "device_pass_24": device_pass_24,
                        "device_pass_5": device_pass_5,
                        "device_manufactuer": device_manufacturer,
                        "device_status": device_status,
                        "dns": dns,
                        "user": user.id,
                        "wifi_status_24": device_wifi_status_24,
                        "wifi_status_5": device_wifi_status_5
                    }
                    
                    existing_device = request.env["device"].sudo().search([("device_id", "=", device_id), ("user", "=", user.id)])
                    
                    if not existing_device:

                      request.env["device"].sudo().create(device_val)
                      
                    else:
                      
                      existing_device.write(device_val)

            else:
                _logger.error("API call failed: %s - %s", response.status_code, response.text)
                return {
                    "status": "error",
                    'message': response.text,
                    "data": []
                }

        except Exception as e:
            _logger.error(f"Error executing: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }

    @http.route('/api/get_devices', type='json', auth='user', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors="*")
    def get_users_devices(self, **kwargs):
        try:

            user = request.env.user

            devices = request.env["device"].sudo().search([("user", "=", user.id)])

            response = []

            for device in devices:

                device_val = {
                    "name2.4G": device.device_name_24,
                    "name5G": device.device_name_5,
                    "pass2.4G": device.device_pass_24,
                    "pass5G": device.device_pass_5,
                    "manufactuer": device.device_manufactuer,
                    "dns": device.dns,
                    "status": device.device_status,
                    "device_id": device.device_id,
                    "wifi_status_24": device.wifi_status_24,
                    "wifi_status_5": device.wifi_status_5
                }
                response.append(device_val)

            return {
                "status": "success",
                "data": response
            }


        except Exception as e:
            _logger.error(f"Error executing Superset query: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
            
            
    @http.route('/api/change_wifi_name', type='json', auth='user', methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def change_wifi_name(self, **kwargs):
        try:
            user = request.env.user

            data = json.loads(request.httprequest.data.decode('utf-8'))

            device_id = data.get("device_id")
            internet_mode = data.get("internet_mode")
            name = data.get("name")

            existing_device = request.env["device"].sudo().search([("device_id", "=", device_id), ("user", "=", user.id)])

            if existing_device:
            
                if internet_mode == "2.4":
                    mode_id = "1"
                elif internet_mode == "5":
                    if existing_device.device_manufactuer == "ZTE":
                      mode_id = "5"
                    else:
                      mode_id = "3"
                else:
                    return {
                        "status": "error",
                        'message': "Internet mode not found",
                        "data": []
                    }

                encoded_value = urllib.parse.quote(existing_device.device_id)
                url = f"{user.company_id.gasc_url}/devices/{encoded_value}/tasks?timeout=3000&connection_request="
                
                
                payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                          [
                              "InternetGatewayDevice.LANDevice.1.WLANConfiguration."+mode_id+".SSID",
                              name
                          ]
                      ]
                  }

                response = requests.post(
                    url,
                    auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                    json=payload
                )

                # --- PATCHED BLOCK ---
                if response.status_code == 200:
                    data = response.json()
                    _logger.info("Change_device_name response: %s", data)
                    return {"status": "success", "data": data}
                # --- END PATCHED BLOCK ---
                else:
                    return {
                        "status": "error",
                        'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                        "data": []
                    }

            else:
                _logger.error(f"Device not found")
                return {
                    "status": "error",
                    'message': "Device not found",
                    "data": []
                }

        except Exception as e:
            _logger.error(f"Error executing: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
            
    @http.route('/api/change_wifi_pass', type='json', auth='user', methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def change_wifi_pass(self, **kwargs):
        try:
            user = request.env.user

            data = json.loads(request.httprequest.data.decode('utf-8'))

            device_id = data.get("device_id")
            internet_mode = data.get("internet_mode")
            password = data.get("password")


            existing_device = request.env["device"].sudo().search([("device_id", "=", device_id), ("user", "=", user.id)])

            if existing_device:
            
                if internet_mode == "2.4":
                    mode_id = "1"
                elif internet_mode == "5":
                    if existing_device.device_manufactuer == "ZTE":
                        mode_id = "5"
                    else:
                       mode_id = "3"
                else:
                    return {
                        "status": "error",
                        'message': "Internet mode not found",
                        "data": []
                    }

                encoded_value = urllib.parse.quote(existing_device.device_id)
                url = f"{user.company_id.gasc_url}/devices/{encoded_value}/tasks?timeout=3000&connection_request="
                
                if existing_device.device_manufactuer == "ZTE":
                  payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                          [
                            "InternetGatewayDevice.LANDevice.1.WLANConfiguration."+mode_id+".PreSharedKey.1.KeyPassphrase",
                            password,
                            "xsd:string"
                          ]
                      ]
                  }
                else:
                  payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                          [
                            "InternetGatewayDevice.LANDevice.1.WLANConfiguration."+mode_id+".X_TP_PreSharedKey",
                            password,
                            "xsd:string"
                          ]
                      ]
                  }

                response = requests.post(
                    url,
                    auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                    json=payload
                )

                # --- PATCHED BLOCK ---
                if response.status_code == 200:
                    data = response.json()
                    _logger.info("Change_device_pass response: %s", data)
                    return {"status": "success", "data": data}
                # --- END PATCHED BLOCK ---
                else:
                    return {
                        "status": "error",
                        'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                        "data": []
                    }

            else:
                _logger.error(f"Device not found")
                return {
                    "status": "error",
                    'message': "Device not found",
                    "data": []
                }

        except Exception as e:
            _logger.error(f"Error executing: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
            
    
    @http.route('/api/wifi_status', type='json', auth='user', methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def change_wifi_status(self, **kwargs):
        try:
            user = request.env.user

            data = json.loads(request.httprequest.data.decode('utf-8'))

            device_id = data.get("device_id")
            internet_mode = data.get("internet_mode")
            status = data.get("status")


            existing_device = request.env["device"].sudo().search([("device_id", "=", device_id), ("user", "=", user.id)])

            if existing_device:
            
                if internet_mode == "2.4":
                    mode_id = "1"
                elif internet_mode == "5":
                    if existing_device.device_manufactuer == "ZTE":
                        mode_id = "5"
                    else:
                       mode_id = "3"
                else:
                    return {
                        "status": "error",
                        'message': "Internet mode not found",
                        "data": []
                    }

                encoded_value = urllib.parse.quote(existing_device.device_id)
                url = f"{user.company_id.gasc_url}/devices/{encoded_value}/tasks?timeout=3000&connection_request="
                
                if existing_device.device_manufactuer == "ZTE":
                  payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                          [
                            "InternetGatewayDevice.LANDevice.1.WLANConfiguration."+mode_id+".Enable",
                            status
                          ]
                      ]
                  }
                else:
                  payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                          [
                            "InternetGatewayDevice.LANDevice.1.WLANConfiguration."+mode_id+".Enable",
                            status
                          ]
                      ]
                  }

                response = requests.post(
                    url,
                    auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                    json=payload
                )

                # --- PATCHED BLOCK ---
                if response.status_code == 200:
                    data = response.json()
                    _logger.info("Change_device_pass response: %s", data)
                    return {"status": "success", "data": data}
                # --- END PATCHED BLOCK ---
                else:
                    return {
                        "status": "error",
                        'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                        "data": []
                    }

            else:
                _logger.error(f"Device not found")
                return {
                    "status": "error",
                    'message': "Device not found",
                    "data": []
                }

        except Exception as e:
            _logger.error(f"Error executing: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }
            
    
    @http.route('/api/change_dns', type='json', auth='user', methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def change_dns(self, **kwargs):
        try:
            user = request.env.user

            data = json.loads(request.httprequest.data.decode('utf-8'))

            device_id = data.get("device_id")
            dns = data.get("dns")

            if dns == "off":
                dnsvalue = "80.91.126.35,80.91.126.34"
                dnsvalue1 = "80.91.126.35"
                dnsvalue2 = "80.91.126.34"
            elif dns == "on":
                dnsvalue = "80.91.123.22,80.91.123.23"
                dnsvalue1 = "80.91.123.22"
                dnsvalue2 = "80.91.123.23"
            else:
                return {
                    "status": "error",
                    'message': "Internet mode not found",
                    "data": []
                }

            existing_device = request.env["device"].sudo().search([("device_id", "=", device_id), ("user", "=", user.id)])

            if existing_device:

                encoded_value = urllib.parse.quote(existing_device.device_id)
                url = f"{user.company_id.gasc_url}/devices/{encoded_value}/tasks?timeout=3000&connection_request="
                
                if existing_device.device_manufactuer == "ZTE": 
                
                  payload = {
                              "name": "setParameterValues",
                              "parameterValues": [
                                [
                                  "InternetGatewayDevice.DNS.X_ZTE-COM_IPv4DNSServer1",
                                  dnsvalue1
                                ]
                              ]
                            }
                            
                  response = requests.post(
                      url,
                      auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                      json=payload
                  )
                  
                  if response.status_code == 200:
                    
                     payload = {
                              "name": "setParameterValues",
                              "parameterValues": [
                                [
                                  "InternetGatewayDevice.DNS.X_ZTE-COM_IPv4DNSServer2",
                                  dnsvalue2
                                ]
                              ]
                            }
                            
                     response = requests.post(
                      url,
                      auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                      json=payload
                      )
                      
                     # --- PATCHED BLOCK ---
                     if response.status_code == 200:
                        data = response.json()
                        return {"status": "success", "data": data}
                     # --- END PATCHED BLOCK ---
                     else:
                        
                        return {
                          "status": "error",
                          'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                          "data": []
                        }
                        
                  else:
                    
                      return {
                          "status": "error",
                          'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                          "data": []
                        }
                
                else:
                
                  payload = {
                      "name": "setParameterValues",
                      "parameterValues": [
                              [
                                "InternetGatewayDevice.LANDevice.1.LANHostConfigManagement.DNSServers",
                                dnsvalue
                              ]
                      ]
                  }
  
                  response = requests.post(
                      url,
                      auth=HTTPBasicAuth(user.company_id.gasc_username, user.company_id.gasc_password),
                      json=payload
                  )

                  # --- PATCHED BLOCK ---
                  if response.status_code == 200:
                      data = response.json()
                      _logger.info("Change_dns response: %s", data)
                      return {"status": "success", "data": data}
                  # --- END PATCHED BLOCK ---
                  else:
                      return {
                          "status": "error",
                          'message': "Ndodhi nje error, ju lutem kontaktoni supportin",
                          "data": []
                      }

            else:
                _logger.error(f"Device not found")
                return {
                    "status": "error",
                    'message': "Device not found",
                    "data": []
                }

        except Exception as e:
            _logger.error(f"Error executing: {str(e)}")
            return {
                "status": "error",
                'message': str(e),
                "data": []
            }

from odoo import fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)  # Set up logging for this model


class Device(models.Model):

    _name = "device"

    device_name_24 = fields.Char(string="Name 2.4G")
    device_name_5 = fields.Char(string="Name 5G")
    device_pass_24 = fields.Char(string="Password 2.4G")
    device_pass_5 = fields.Char(string="Password 5G")
    device_id = fields.Char(string="ID")
    device_manufactuer = fields.Char(string="Manufactuer")
    device_status = fields.Boolean(string="Status")
    dns = fields.Char(string="DNS")
    user = fields.Many2one(
        'res.users',
        string='User')
    wifi_status_24 = fields.Char(string="Status Wifi 2.4G")
    wifi_status_5 = fields.Char(string="Status Wifi 5G")
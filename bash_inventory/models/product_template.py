from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    rack_id = fields.Many2one('product.product', string="Rack", help="Rack containing this device")
    ports_ids = fields.One2many('switch.port', 'switch_id', string="Ports")

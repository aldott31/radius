from odoo import models, fields

class SwitchPort(models.Model):
    _name = 'switch.port'
    _description = 'Switch Ports'

    name = fields.Char(string='Port Name', required=True)
    switch_id = fields.Many2one('product.product', string='Switch')
    sfp_module_id = fields.Many2one('product.product', string='SFP Module')
    sfp_lot_id = fields.Many2one('stock.production.lot', string='SFP Lot/Serial Number')
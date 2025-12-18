# Placeholder for Odoo module initialization
from odoo import models, fields, api, _

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Add your custom fields
    port_attr = fields.Char(string='Port')

    # Override a method or add new methods
    @api.model
    def _get_inventory_fields_write(self):    
      fields = super(StockQuant, self)._get_inventory_fields_write()     
      return fields + ['port_attr'] 
     

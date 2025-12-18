from odoo import fields, models


class ResPartnerBash(models.Model):
    _inherit = 'res.partner'

    x_ab_username = fields.Char(
        string='Ab Username',
        help='AbissNet RADIUS username for customer portal login',
        index=True,
        copy=False,
        tracking=True
    )

    x_acctid = fields.Integer(
        string='Acct Id',
        help='AbissNet Account ID from RADIUS database',
        copy=False,
        readonly=True
    )

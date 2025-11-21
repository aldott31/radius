# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RadiusProvisionWizard(models.TransientModel):
    _name = 'radius.provision.wizard'
    _description = 'RADIUS Provisioning Wizard'

    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        domain=[('is_radius_customer', '=', False)]
    )

    subscription_id = fields.Many2one(
        'asr.subscription',
        string="Subscription Package",
        required=True
    )

    device_id = fields.Many2one(
        'asr.device',
        string="NAS Device (Optional)"
    )

    access_device_id = fields.Many2one(
        'crm.access.device',
        string="Access Device (OLT/DSLAM)"
    )

    radius_username = fields.Char(
        string="RADIUS Username",
        help="Leave empty for auto-generation (445XXXXXX)"
    )

    radius_password = fields.Char(
        string="RADIUS Password",
        help="Leave empty for auto-generation"
    )

    auto_sync = fields.Boolean(
        string="Auto-Sync to RADIUS",
        default=True,
        help="Automatically sync to FreeRADIUS after provisioning"
    )

    def action_provision(self):
        """Provision RADIUS user"""
        self.ensure_one()

        try:
            # 1) Enable partner as RADIUS customer
            self.partner_id.write({
                'is_radius_customer': True,
                'subscription_id': self.subscription_id.id,
                'device_id': self.device_id.id if self.device_id else False,
            })

            # 2) Set username/password (auto-generate if empty)
            username = self.radius_username or self.partner_id._generate_username()
            password = self.radius_password or self.partner_id._generate_password()

            self.partner_id.write({
                'radius_username': username,
                'radius_password': password,
            })

            # 3) Link access device if provided
            if self.access_device_id:
                # This requires that res.partner has access_device_id field
                # We need to add this field to res_partner.py
                pass

            # 4) Auto-sync if enabled
            if self.auto_sync:
                self.partner_id.action_sync_to_radius()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RADIUS Provisioning'),
                    'message': _('Customer %s provisioned successfully as RADIUS user: %s') % (
                        self.partner_id.name,
                        username
                    ),
                    'type': 'success',
                    'sticky': False
                }
            }

        except Exception as e:
            raise UserError(_('Provisioning failed:\n%s') % str(e))

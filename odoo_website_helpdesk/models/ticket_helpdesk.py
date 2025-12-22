# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Dhanya B (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PRIORITIES = [
    ('0', 'Very Low'),
    ('1', 'Low'),      # SLA 1
    ('2', 'Normal'),   # SLA 2
    ('3', 'High'),     # SLA 3
]

RATING = [
    ('0', 'Very Low'),
    ('1', 'Low'),
    ('2', 'Normal'),
    ('3', 'High'),
]


class TicketHelpDesk(models.Model):
    """Help_ticket model"""
    _name = 'ticket.helpdesk'
    _description = 'Helpdesk Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_show_create_task(self):
        """Task creation"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.show_create_task')

    def _default_show_category(self):
        """Show category default"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.show_category')

    name = fields.Char('Name', default=lambda self: self.env['ir.sequence'].
                       next_by_code('ticket.helpdesk') or _('New'),
                       help='Ticket Name')
    customer_id = fields.Many2one('res.partner',
                                  string='Customer Name',
                                  help='Customer Name')
    customer_name = fields.Char('Customer Name', help='Customer Name')
    customer_radius_username = fields.Char(
        string='RADIUS Username',
        store=True,
        index=True,
        help='RADIUS Username from Contact'
    )
    subject = fields.Text('Subject', required=True,
                          help='Subject of the Ticket')
    description = fields.Text('Description', required=True,
                              help='Description')
    email = fields.Char('Email', help='Email')
    phone = fields.Char('Phone', help='Contact Number')
    team_id = fields.Many2one('team.helpdesk', string='Helpdesk Team',
                              help='Helpdesk Team Name')
    product_ids = fields.Many2many('product.template',
                                   string='Product',
                                   help='Product Name')
    project_id = fields.Many2one('project.project',
                                 string='Project',
                                 readonly=False,
                                 related='team_id.project_id',
                                 store=True,
                                 help='Project Name')
    priority = fields.Selection(PRIORITIES, default='1', help='Priority Level')
    stage_id = fields.Many2one('ticket.stage', string='Stage',
                               default=lambda self: self.env[
                                   'ticket.stage'].search(
                                   [('name', '=', 'Draft')], limit=1).id,
                               tracking=True,
                               group_expand='_read_group_stage_ids',
                               help='Stages')
    user_id = fields.Many2one('res.users',
                              default=lambda self: self.env.user,
                              check_company=True,
                              index=True, tracking=True,
                              help='Login User', string='User')
    cost = fields.Float('Cost per hour', help='Cost Per Unit')
    service_product_id = fields.Many2one('product.product',
                                         string='Service Product',
                                         help='Service Product',
                                         domain=[
                                             ('detailed_type', '=', 'service')])
    create_date = fields.Datetime('Creation Date', help='Created date')
    start_date = fields.Datetime('Start Date', help='Start Date')
    end_date = fields.Datetime('End Date', help='End Date')
    public_ticket = fields.Boolean(string="Public Ticket",
                                   help='Public Ticket')
    invoice_ids = fields.Many2many('account.move',
                                   string='Invoices',
                                   help='Invoicing id'
                                   )
    task_ids = fields.Many2many('project.task',
                                string='Tasks',
                                help='Task id')
    color = fields.Integer(string="Color", help='Color')
    replied_date = fields.Datetime('Replied date', help='Replied Date')
    last_update_date = fields.Datetime('Last Update Date',
                                       help='Last Update Date')
    ticket_type_id = fields.Many2one('helpdesk.type',
                                     string='Ticket Type', help='Ticket Type')
    team_head_id = fields.Many2one('res.users', string='Team Leader',
                                   compute='_compute_team_head_id',
                                   help='Team Leader Name')
    assigned_user_id = fields.Many2one('res.users', string='Assigned User',
                                       domain=lambda self: [('groups_id', 'in',
                                                             self.env.ref(
                                                                 'odoo_website_helpdesk.helpdesk_user').id)],
                                       help='Assigned User Name')
    category_id = fields.Many2one('helpdesk.category', string='Category',
                                  help='Category')
    tags_ids = fields.Many2many('helpdesk.tag', help='Tags', string='Tags')
    assign_user = fields.Boolean(default=False, help='Assign User',
                                 string='Assign User')
    attachment_ids = fields.One2many('ir.attachment', 'res_id',
                                     help='Attachment Line',
                                     string='Attachments')
    merge_ticket_invisible = fields.Boolean(string='Merge Ticket',
                                            help='Merge Ticket Invisible or '
                                                 'Not', default=False)
    merge_count = fields.Integer(string='Merge Count', help='Merged Tickets '
                                                            'Count')
    active = fields.Boolean(default=True, help='Active', string='Active')
    
    # Field për finance/sales visibility (tickets without team)
    is_finance_visible = fields.Boolean(
        compute='_compute_finance_visible',
        search='_search_finance_visible',
        store=False,
        string='Finance/Sales Visible',
        help='Indicates if ticket is visible to finance and sales users (unassigned tickets)'
    )

    # Customer status for button visibility (computed to avoid dependency issues)
    customer_status = fields.Selection(
        [
            ('lead', 'Lead'),
            ('paid', 'Paid'),
            ('for_installation', 'For Installation'),
            ('for_registration', 'For Registration'),
            ('active', 'Active')
        ],
        compute='_compute_customer_status',
        string='Customer Status',
        store=False
    )

    show_create_task = fields.Boolean(string="Show Create Task",
                                      help='Show created task or not',
                                      default=_default_show_create_task,
                                      compute='_compute_show_create_task')
    create_task = fields.Boolean(string="Create Task", readonly=False,
                                 help='Create task or not',
                                 related='team_id.create_task', store=True)
    billable = fields.Boolean(string="Billable", default=False,
                              help='Is billable or not', )
    show_category = fields.Boolean(default=_default_show_category,
                                   string="Show Category",
                                   help='Show category or not',
                                   compute='_compute_show_category')
    customer_rating = fields.Selection(RATING, default='1', readonly=True,
                                       help='Customer Rating')
    review = fields.Char('Review', readonly=True, help='Ticket review')
    kanban_state = fields.Selection([
        ('normal', 'Ready'),
        ('done', 'In Progress'),
        ('blocked', 'Blocked'), ], default='normal')

    @api.depends('team_id')
    def _compute_finance_visible(self):
        """Ticketat pa team janë visible për finance dhe sales users"""
        for ticket in self:
            ticket.is_finance_visible = not ticket.team_id

    @api.depends('customer_id')
    def _compute_customer_status(self):
        """Compute customer status from customer_id if field exists"""
        for ticket in self:
            if ticket.customer_id and hasattr(ticket.customer_id, 'customer_status'):
                ticket.customer_status = ticket.customer_id.customer_status
            else:
                ticket.customer_status = False

    def _search_finance_visible(self, operator, value):
        """Search method për finance/sales visibility - kontrollon dinamikisht finance dhe sales groups"""
        # Kontrollo nëse user ka CRM: Finance ose CRM: Sales group
        has_access = False
        try:
            finance_group = self.env.ref('asr_radius_manager.group_isp_finance')
            has_finance = finance_group in self.env.user.groups_id
        except:
            has_finance = False

        try:
            sales_group = self.env.ref('asr_radius_manager.group_isp_sales')
            has_sales = sales_group in self.env.user.groups_id
        except:
            has_sales = False

        has_access = has_finance or has_sales

        # Nëse është finance ose sales user dhe po kërkon records visible
        if has_access and operator == '=' and value:
            return [('team_id', '=', False)]
        # Nëse nuk është finance as sales, kthe empty domain që nuk gjen asgjë
        return [('id', '=', 0)]

    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        """Set priority and RADIUS username based on customer"""
        if self.customer_id:
            # Set RADIUS username
            if hasattr(self.customer_id, 'radius_username'):
                self.customer_radius_username = self.customer_id.radius_username
            
            # Set priority based on SLA level
            if hasattr(self.customer_id, 'sla_level') and self.customer_id.sla_level:
                sla_to_priority = {
                    '1': '1',  # SLA 1 -> Low
                    '2': '2',  # SLA 2 -> Normal
                    '3': '3',  # SLA 3 -> High
                }
                self.priority = sla_to_priority.get(self.customer_id.sla_level, '1')
        else:
            self.customer_radius_username = False

    @api.onchange('team_id', 'team_head_id')
    def _onchange_team_id(self):
        """Changing the team leader when selecting the team"""
        li = self.team_id.member_ids.mapped('id')
        return {'domain': {'assigned_user_id': [('id', 'in', li)]}}

    @api.depends('team_id')
    def _compute_team_head_id(self):
        """Compute the team head function"""
        for record in self:
            record.team_head_id = record.team_id.team_lead_id.id if record.team_id else False

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """Sending mail to the user function"""
        rec_id = self._origin.id
        data = self.env['ticket.helpdesk'].search([('id', '=', rec_id)])
        data.last_update_date = fields.Datetime.now()
        if self.stage_id.starting_stage:
            data.start_date = fields.Datetime.now()
        if self.stage_id.closing_stage or self.stage_id.cancel_stage:
            data.end_date = fields.Datetime.now()
        if self.stage_id.template_id:
            mail_template = self.stage_id.template_id
            mail_template.send_mail(self._origin.id, force_send=True)

    def assign_to_teamleader(self):
        """Assigning team leader function"""
        if self.team_id:
            self.team_head_id = self.team_id.team_lead_id.id
            mail_template = self.env.ref(
                'odoo_website_helpdesk.odoo_website_helpdesk_assign')
            mail_template.sudo().write({
                'email_to': self.team_head_id.email,
                'subject': self.name
            })
            mail_template.sudo().send_mail(self.id, force_send=True)
        else:
            raise ValidationError("Please choose a Helpdesk Team")

    def _compute_show_category(self):
        """Compute show category"""
        show_category = self._default_show_category()
        for rec in self:
            rec.show_category = show_category

    def _compute_show_create_task(self):
        """Compute the created task"""
        show_create_task = self._default_show_create_task()
        for record in self:
            record.show_create_task = show_create_task

    def auto_close_ticket(self):
        """Automatically closing the ticket"""
        auto_close = self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.auto_close_ticket')
        if auto_close:
            no_of_days = self.env['ir.config_parameter'].sudo().get_param(
                'odoo_website_helpdesk.no_of_days')
            records = self.env['ticket.helpdesk'].search([])
            for rec in records:
                days = (fields.Datetime.today() - rec.create_date).days
                if days >= int(no_of_days):
                    close_stage_id = self.env['ticket.stage'].search(
                        [('closing_stage', '=', True)])
                    if close_stage_id:
                        rec.stage_id = close_stage_id

    def default_stage_id(self):
        """Method to return the default stage"""
        return self.env['ticket.stage'].search(
            [('name', '=', 'Draft')], limit=1).id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order=None, *args, **kwargs):
        return stages.search([], order=order or "sequence,id")

    @api.model_create_multi
    def create(self, vals_list):
        """Create function"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ticket.helpdesk')
            
            # ✅ VALIDIM: Nëse krijohet manualisht (jo nga automation), team duhet të jetë vendosur
            if not vals.get('team_id'):
                # Kontrollo nëse po vjen nga automation (Finance, etc.)
                if not self.env.context.get('_from_finance_automation') and \
                   not self.env.context.get('_skip_team_validation'):
                    raise ValidationError(_(
                        'Helpdesk Team is required when creating a ticket manually.\n'
                        'Please select a team before saving.'
                    ))
            
            # Auto-populate RADIUS username when ticket is created
            if vals.get('customer_id') and not vals.get('customer_radius_username'):
                customer = self.env['res.partner'].browse(vals['customer_id'])
                if hasattr(customer, 'radius_username') and customer.radius_username:
                    vals['customer_radius_username'] = customer.radius_username
        
        return super(TicketHelpDesk, self).create(vals_list)

    def write(self, vals):
        """Write function with team assignment notification"""
        # Check if team is being assigned/changed
        if 'team_id' in vals and vals.get('team_id'):
            team = self.env['team.helpdesk'].browse(vals['team_id'])
            
            for ticket in self:
                # Check if team is actually changing (not just updating same team)
                if ticket.team_id.id != team.id:
                    # Add team members as followers to receive notifications
                    if team.member_ids:
                        partner_ids = team.member_ids.mapped('partner_id').ids
                        ticket.message_subscribe(partner_ids=partner_ids)
                        
                        # Send email notification using template to each team member
                        try:
                            mail_template = self.env.ref('odoo_website_helpdesk.ticket_team_assignment_notification')
                            for member in team.member_ids:
                                if member.partner_id.email:
                                    mail_template.with_context(
                                        email_to=member.partner_id.email
                                    ).send_mail(ticket.id, force_send=True, email_values={
                                        'email_to': member.partner_id.email
                                    })
                        except Exception as e:
                            _logger.warning(f"Failed to send team assignment notification: {e}")
        
        result = super(TicketHelpDesk, self).write(vals)
        return result

    def action_create_invoice(self):
        """Create Invoice based on the ticket"""
        tasks = self.env['project.task'].search(
            [('project_id', '=', self.project_id.id),
             ('ticket_id', '=', self.id)]).filtered(
            lambda line: not line.ticket_billed)
        if not tasks:
            raise UserError('No Tasks to Bill')
        total = sum(x.effective_hours for x in tasks if
                     x.effective_hours > 0 and not x.some_flag)
        invoice_no = self.env['ir.sequence'].next_by_code(
            'ticket.invoice')
        self.env['account.move'].create([
            {
                'name': invoice_no,
                'move_type': 'out_invoice',
                'partner_id': self.customer_id.id,
                'ticket_id': self.id,
                'date': fields.Date.today(),
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [(0, 0,
                                      {
                                          'product_id': self.service_product_id.id,
                                          'name': self.service_product_id.name,
                                          'quantity': total,
                                          'product_uom_id': self.service_product_id.uom_id.id,
                                          'price_unit': self.cost,
                                          'account_id': self.service_product_id.categ_id.property_account_income_categ_id.id,
                                      })],
            }, ])
        for task in tasks:
            task.ticket_billed = True
        return {
            'effect': {
                'fadeout': 'medium',
                'message': 'Billed Successfully!',
                'type': 'rainbow_man',
            }
        }

    def action_create_tasks(self):
        """Task creation"""
        task_id = self.env['project.task'].create({
            'name': self.name + '-' + self.subject,
            'project_id': self.project_id.id,
            'company_id': self.env.company.id,
            'ticket_id': self.id,
        })
        self.write({
            'task_ids': [(4, task_id.id)]
        })
        return {
            'name': 'Tasks',
            'res_model': 'project.task',
            'view_id': False,
            'res_id': task_id.id,
            'view_mode': 'form',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def action_open_tasks(self):
        """View the Created task """
        return {
            'name': 'Tasks',
            'domain': [('ticket_id', '=', self.id)],
            'res_model': 'project.task',
            'view_id': False,
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
        }

    def action_open_invoices(self):
        """View the Created invoice"""
        return {
            'name': 'Invoice',
            'domain': [('ticket_id', '=', self.id)],
            'res_model': 'account.move',
            'view_id': False,
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
        }

    def action_open_merged_tickets(self):
        """Open the merged tickets tree view"""
        ticket_ids = self.env['support.ticket'].search(
            [('merged_ticket', '=', self.id)])
        helpdesk_ticket_ids = ticket_ids.mapped('display_name')
        help_ticket_records = self.env['ticket.helpdesk'].search(
            [('name', 'in', helpdesk_ticket_ids)])
        return {
            'type': 'ir.actions.act_window',
            'name': 'Helpdesk Ticket',
            'view_mode': 'tree,form',
            'res_model': 'ticket.helpdesk',
            'domain': [('id', 'in', help_ticket_records.ids)],
            'context': self.env.context,
        }

    def action_send_reply(self):
        """Action to sent reply button"""
        template_id = self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.reply_template_id'
        )
        template_id = self.env['mail.template'].browse(int(template_id))
        if template_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'mail',
                'res_model': 'mail.compose.message',
                'view_mode': 'form',
                'target': 'new',
                'views': [[False, 'form']],
                'context': {
                    'default_model': 'ticket.helpdesk',
                    'default_res_ids': self.ids,
                    'default_template_id': template_id.id
                }
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'mail',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'views': [[False, 'form']],
            'context': {
                'default_model': 'ticket.helpdesk',
                'default_res_ids': self.ids,
            }
        }

    # ==================== NEW WORKFLOW METHODS ====================

    def action_confirm_payment_send_installation(self):
        """Finance confirms payment & docs, sends to Installation team"""
        self.ensure_one()

        # Find Installation team
        installation_team = self.env['team.helpdesk'].search([
            '|',
            ('name', 'ilike', 'installation'),
            ('name', 'ilike', 'install')
        ], limit=1)

        if not installation_team:
            raise UserError(_(
                "Installation Team not found.\n"
                "Please create a Helpdesk Team with 'Installation' in the name."
            ))

        # Update customer status
        if self.customer_id:
            self.customer_id.write({'customer_status': 'for_installation'})
            _logger.info(
                "Finance confirmed payment for %s - Status: paid → for_installation",
                self.customer_id.name
            )

        # Assign to Installation team
        self.write({'team_id': installation_team.id})

        # Post message
        self.message_post(
            body=_("✅ <b>Payment & Documents Confirmed by Finance</b><br/>"
                   "Ticket assigned to Installation Team.<br/>"
                   "Customer Status: Paid → For Installation"),
            subtype_xmlid='mail.mt_note'
        )

        return True

    def action_installation_complete(self):
        """Installation complete - ACTIVATE internet & send to NOC for ONU registration"""
        self.ensure_one()

        # Find NOC team
        noc_team = self.env['team.helpdesk'].search([
            '|',
            ('name', 'ilike', 'noc'),
            ('name', 'ilike', 'network')
        ], limit=1)

        if not noc_team:
            raise UserError(_(
                "NOC Team not found.\n"
                "Please create a Helpdesk Team with 'NOC' in the name."
            ))

        # Update customer status & ACTIVATE internet
        if self.customer_id:
            # ⚡ ACTIVATE INTERNET NOW (for testing during installation)
            if self.customer_id.is_suspended:
                _logger.info(
                    "🔧 Installation complete for %s - Activating internet for testing",
                    self.customer_id.name
                )
                self.customer_id.action_reactivate()
                self.customer_id.action_move_to_active_pool()
                self.customer_id._send_activation_notification()

            # Update status
            self.customer_id.write({'customer_status': 'for_registration'})
            _logger.info(
                "📡 Internet activated for %s - Sending to NOC for ONU registration",
                self.customer_id.name
            )

        # Assign to NOC team
        self.write({'team_id': noc_team.id})

        # Post message
        self.message_post(
            body=_("✅ <b>Installation Complete</b><br/>"
                   "⚡ Internet Service ACTIVATED (for testing)<br/>"
                   "Assigned to NOC Team for ONU registration.<br/>"
                   "Customer Status: For Installation → For Registration"),
            subtype_xmlid='mail.mt_note'
        )

        return True

    def _get_subscription_months_from_customer(self):
        """
        Find subscription_months from customer's most recent RADIUS sale order
        Returns: int (subscription months) or None if not found
        """
        self.ensure_one()

        if not self.customer_id:
            return None

        # Find most recent RADIUS sale order for this customer
        sale_order = self.env['sale.order'].search([
            ('partner_id', '=', self.customer_id.id),
            ('is_radius_order', '=', True),
            ('state', 'in', ['sale', 'done'])  # Only confirmed orders
        ], order='date_order desc', limit=1)

        if sale_order and sale_order.subscription_months:
            _logger.info(
                "Found RADIUS sale order %s for customer %s with %d months",
                sale_order.name,
                self.customer_id.name,
                sale_order.subscription_months
            )
            return sale_order.subscription_months

        # Fallback: check if customer has paid invoices with RADIUS products
        invoices = self.env['account.move'].search([
            ('partner_id', '=', self.customer_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['paid', 'in_payment'])
        ], order='invoice_date desc', limit=1)

        if invoices:
            # Get quantity from RADIUS product line (quantity = months)
            for line in invoices.invoice_line_ids:
                if hasattr(line.product_id, 'is_radius_service') and line.product_id.is_radius_service:
                    months = max(1, int(line.quantity))
                    _logger.info(
                        "Fallback: Using quantity from invoice %s for customer %s: %d months",
                        invoices.name,
                        self.customer_id.name,
                        months
                    )
                    return months

        _logger.warning(
            "Could not find subscription_months for customer %s (no RADIUS sale order or invoice)",
            self.customer_id.name
        )
        return None

    def action_onu_registered_activate(self):
        """NOC registers ONU - Set customer ACTIVE, calculate service_paid_until & close ticket"""
        self.ensure_one()

        # Update customer to ACTIVE and calculate service_paid_until
        if self.customer_id:
            # 🔧 CALCULATE SERVICE_PAID_UNTIL from sale order
            # Service period starts NOW (when ONU is registered), not when payment was made
            # This prevents losing service days during installation
            service_start_date = fields.Date.today()
            subscription_months = self._get_subscription_months_from_customer()

            update_vals = {'customer_status': 'active'}

            if subscription_months:
                from dateutil.relativedelta import relativedelta
                service_paid_until = service_start_date + relativedelta(months=subscription_months)
                update_vals['service_paid_until'] = service_paid_until
                update_vals['contract_start_date'] = update_vals.get('contract_start_date') or service_start_date

                _logger.info(
                    "✅ ONU registered for %s - Service starts TODAY: %s + %d months = %s",
                    self.customer_id.name,
                    service_start_date,
                    subscription_months,
                    service_paid_until
                )

                # Post message to customer chatter
                self.customer_id.message_post(
                    body=_("🎉 <b>Service Activated!</b><br/>"
                           "ONU Registered & Online<br/>"
                           "Service Period: %d month(s)<br/>"
                           "Valid Until: %s") % (
                        subscription_months,
                        service_paid_until.strftime('%d %B, %Y')
                    ),
                    subtype_xmlid='mail.mt_note'
                )
            else:
                _logger.warning(
                    "Could not find subscription_months for %s - service_paid_until not calculated",
                    self.customer_id.name
                )

            # Set to ACTIVE
            self.customer_id.write(update_vals)
            _logger.info(
                "✅ ONU registered for %s - Customer set to ACTIVE",
                self.customer_id.name
            )

        # Close ticket
        close_stage = self.env['ticket.stage'].search([
            ('closing_stage', '=', True)
        ], limit=1)

        if close_stage:
            self.write({'stage_id': close_stage.id})

        # Post message
        self.message_post(
            body=_("✅ <b>ONU Registered Successfully</b><br/>"
                   "Customer Status: For Registration → ACTIVE<br/>"
                   "Ticket CLOSED."),
            subtype_xmlid='mail.mt_note'
        )

        return True
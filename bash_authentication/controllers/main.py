from odoo import http
from odoo.http import request
import json
import logging
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)


class ApiAuthentication(http.Controller):
    @http.route('/api/login', type='json', auth='none', csrf=False, methods=['POST'])
    def login(self, **kwargs):
        # Force JSON parsing

        # _logger.info(f"Received kwargs: {kwargs}")

        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            login = data.get('login')
            password = data.get('password')
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Invalid JSON format: {str(e)}"
            }

        if not login or not password:
            return {
                'status': 'error',
                'message': 'Login and password are required.'
            }
            
        user = request.env['res.users'].sudo().search([('email', '=', login)], limit=1)

        # Authenticate user
        uid = request.session.authenticate(request.env.cr.dbname, user.login, password)
        if not uid:
            return {
                'status': 'error',
                'message': 'Invalid login or password.'
            }

        user = request.env['res.users'].browse(uid)
        return {
            'status': 'success',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
            },
            'session_id': request.session.sid
        }

    @http.route('/api/user', type='json', auth='user', csrf=False, methods=['POST'])
    def get_user(self, **kwargs):
        """Get the currently authenticated user information."""
        user = request.env.user

        # Get user fields
        user_data = {
            'id': user.id,
            'name': user.name,
            'login': user.login,
            'email': user.email,
            'phone': user.phone,
            'mobile': user.mobile,
            'company_id': user.company_id.id,
            'company_name': user.company_id.name,
            'groups': [group.name for group in user.groups_id],  # Get user groups
            'active': user.active,
            'created_on': user.create_date.strftime('%Y-%m-%d %H:%M:%S') if user.create_date else None,
            'last_login': user.login_date.strftime('%Y-%m-%d %H:%M:%S') if user.login_date else None,  # Use login_date
            # Add additional fields as neededx
        }

        return {
            'status': 'success',
            'user': user_data
        }

    @http.route('/api/create_user', type='json', auth='none', csrf=False, methods=['POST'])
    def create_user(self, **kwargs):
        """Create a new portal user."""
        try:
            request.env.cr.rollback()

            # Parse JSON data
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
                name = data.get('name')
                login = data.get('login')
                email = data.get('email')
                phone = data.get('phone')
                password = data.get('password')
            except Exception as e:
                _logger.error(f"Invalid JSON format: {e}")
                return {'status': 'error', 'message': f"Invalid JSON format: {str(e)}"}

            # Validate required fields
            if not all([name, login, phone, password]):
                return {'status': 'error', 'message': 'Name, login, phone, and password are required.'}

            # Check if user exists
            existing_user = request.env['res.users'].sudo().search([('login', '=', login)], limit=1)
            if existing_user:
                return {'status': 'error', 'message': f"User with login '{login}' already exists."}

            # Get default company
            default_company = request.env['res.company'].sudo().search([], limit=1)
            if not default_company:
                return {'status': 'error', 'message': 'No default company found.'}

            # Find portal group
            portal_group = request.env.ref('base.group_portal', raise_if_not_found=False)
            if not portal_group:
                return {'status': 'error', 'message': 'Portal group not found.'}

            sql = f"SELECT * FROM users where username = '{login}'"

            company = request.env['res.company'].sudo().search([('id', '=', 1)], limit=1)

            response = company.run_query(2, sql, 'radius')

            data = response.get('data')

            _logger.info(data)

            if data:

                # Use SUPERUSER_ID for creation
                user = request.env['res.users'].with_user(SUPERUSER_ID).sudo().create([{
                    'name': name,
                    'login': login,
                    'email': email,
                    'phone': phone,
                    'password': password,
                    'active': True,  # Set the user to inactive (not confirmed)
                    'company_id': default_company.id,
                    'company_ids': [(6, 0, [default_company.id])],
                    'groups_id': [(6, 0, [portal_group.id])],
                }])

                # Ensure singleton
                if len(user) != 1:
                    _logger.error(f"Unexpected result: multiple users created for login '{login}': {user.ids}")
                    return {'status': 'error', 'message': 'Unexpected error: multiple users created.'}

                partner = request.env['res.partner'].with_user(SUPERUSER_ID).sudo().create({
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'x_ab_username': login,
                    'user_id': user.id,  # Link the partner to the user
                    'company_id': default_company.id,
                })

                # Update the user to reference the newly created partner
                user.sudo().write({'partner_id': partner.id})

                _logger.info(f"User created successfully: {user[0].name} (ID: {user[0].id})")

                return {
                    'status': 'success',
                    'message': 'Portal user created successfully.',
                    'user': {
                        'id': user[0].id,
                        'name': user[0].name,
                        'login': user[0].login,
                        'email': user[0].email,
                    }
                }
            else:
                return {'status': 'error', 'message': f"Username {login} does not exist. Please contact support!"}

        except Exception as e:
            _logger.error(f"Error creating user: {e}")
            request.env.cr.rollback()
            return {'status': 'error', 'message': f"An error occurred: {str(e)}"}

    @http.route('/api/edit_user', type='json', auth='user', csrf=False, methods=['POST'])
    def edit_user(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            name = data.get('name')
            email = data.get('email')
            phone = data.get('phone')

        except Exception as e:
            return {
                'status': 'error',
                'message': f"Invalid JSON format: {str(e)}"
            }

        _logger.info(request.env.context)
        user = request.env['res.users'].sudo().search([('id', '=', request.env.context.get('uid'))], limit=1)

        _logger.info(user.login)

        if not user:
            return {'status': 'error', 'message': 'User does not exist'}

        user.sudo().write({ 'name': name,
                            'email': email,
                            'phone': phone})

        return {
            'status': 'success',
            'message': 'Portal user edited successfully.',
            'user': {
                'id': user[0].id,
                'name': user[0].name,
                'login': user[0].login,
                'email': user[0].email,
            }
        }
        
    @http.route('/api/change_password', type='json', auth='user', csrf=False, methods=['POST'])
    def change_password(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            user = request.env.user
            old_password = data.get('old_password')
            password = data.get('password')
            confirm_password = data.get('confirm_password')
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Invalid JSON format: {str(e)}"
            }

            # Validate input
        if not password or not confirm_password or not old_password:
            return {
                'status': 'error',
                'message': 'Missing old password, password or confirm password'
            }

            # Compare password and confirm_password
        if password != confirm_password:
            return {
                'status': 'error',
                'message': 'Password and confirm password do not match'
            }
        try:
            request.env['res.users'].sudo()._check_credentials(old_password, {'uid': user.id})
        except AccessDenied:
            return {
                'status': 'error',
                'message': 'Old password is not correct'
            }

            # Use sudo() to bypass access rights if needed (careful with security)
        try:

            # Change the password
            user.write({'password': password})

            return {
                'status': 'success',
                'message': 'Password updated successfully'
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error {str(e)}'
            }
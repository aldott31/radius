# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging, re

_logger = logging.getLogger(__name__)

def _slugify(val):
    val = (val or '').strip().lower()
    val = re.sub(r'[^a-z0-9]+', '-', val)
    return re.sub(r'-+', '-', val).strip('-') or 'plan'

class AsrSubscription(models.Model):
    _name = "asr.subscription"
    _description = "RADIUS Service Plan (Subscription)"
    _order = "id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ---- Fields ----
    name = fields.Char(required=True, tracking=True)
    code = fields.Char(help="Group name in FreeRADIUS (radgroupreply.groupname). Auto-filled from name if empty.")
    rate_limit = fields.Char(help="e.g. '10M/10M'. If set, we add Mikrotik-Rate-Limit unless already in lines.")
    session_timeout = fields.Integer(help="Optional Session-Timeout (seconds)")
    price = fields.Float(help="Default price per cycle (billing in Phase 4/5).")
    product_id = fields.Many2one('product.product', string='Product', help='Product for invoicing (Phase 4/5).')

    # Odoo-only multi-company
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    # Attributes
    attribute_ids = fields.One2many('asr.radius.attribute', 'subscription_id', string='RADIUS Attributes')

    # Sync tracking
    radius_synced = fields.Boolean(default=False, readonly=True, tracking=True)
    last_sync_date = fields.Datetime(readonly=True)
    last_sync_error = fields.Text(readonly=True)

    # Global unique code (sepse nuk namespacojmë në RADIUS)
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Code must be globally unique.'),
    ]

    @api.onchange('name')
    def _onchange_name_set_code(self):
        for rec in self:
            if not rec.code:
                rec.code = _slugify(rec.name)

    # -------------------------------------------------------------------------
    # UI helper
    # -------------------------------------------------------------------------
    def action_view_radius_info(self):
        self.ensure_one()
        grp = (self.code or self.name or '').strip()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RADIUS Plan Info'),
                'message': _(
                    'Plan: %s\n'
                    'Groupname: %s\n'
                    'Last Sync: %s\n'
                    'Status: %s'
                ) % (
                    self.name,
                    grp or '—',
                    self.last_sync_date or 'Never',
                    'Synced' if self.radius_synced else 'Not synced'
                ),
                'type': 'info',
                'sticky': False,
            }
        }

    # -------------------------------------------------------------------------
    # RADIUS connection — si te device: company._get_direct_conn()
    # -------------------------------------------------------------------------
    def _get_radius_connection(self):
        self.ensure_one()
        try:
            return (self.company_id or self.env.company)._get_direct_conn()
        except Exception as e:
            raise UserError(_('Cannot connect to RADIUS database:\n%s') % str(e))

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _groupname(self):
        self.ensure_one()
        grp = (self.code or _slugify(self.name)).strip()
        if not grp:
            raise UserError(_("Group code is empty."))
        return grp

    # -------------------------------------------------------------------------
    # Sync to radgroupreply (NO company_id; vetëm groupname/attribute/op/value)
    # -------------------------------------------------------------------------
    def action_sync_attributes_to_radius(self):
        """
        Upsert plan attributes në radgroupreply:
          - DELETE të gjitha rreshtat ekzistues për groupname
          - INSERT rreshtat aktualë nga attribute_ids
          - Shton automatikisht Mikrotik-Rate-Limit/Session-Timeout nga fushat convenience nëse mungojnë
        """
        ok_count = 0
        names = []
        last_error = None

        for rec in self:
            conn = None
            try:
                conn = rec._get_radius_connection()
                cur = conn.cursor()

                groupname = rec._groupname()

                # 1) Fshi ekzistueset për këtë grup
                cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))

                # 2) Mblidh rreshtat
                rows, seen = [], set()
                for line in rec.attribute_ids:
                    attr = (line.attribute or '').strip()
                    op = (line.op or ':=').strip()
                    val = (line.value or '').strip()
                    if not attr:
                        continue
                    seen.add(attr.lower())
                    rows.append((groupname, attr, op, val))

                # 3) Convenience fields: Shto atributet bazë nëse mungojnë
                if rec.rate_limit and 'mikrotik-rate-limit' not in seen:
                    rows.append((groupname, 'Mikrotik-Rate-Limit', ':=', rec.rate_limit.strip()))
                if rec.session_timeout and 'session-timeout' not in seen:
                    rows.append((groupname, 'Session-Timeout', ':=', str(int(rec.session_timeout))))
                if 'Acct-Interim-Interval' not in seen:
                    rows.append((groupname, 'Acct-Interim-Interval', ':=', '300'))
                if 'Idle-Timeout' not in seen:
                    rows.append((groupname, 'Idle-Timeout', ':=', '600'))

                # 4) INSERT
                if rows:
                    cur.executemany(
                        "INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s,%s,%s,%s)",
                        rows
                    )

                conn.commit()

                rec.sudo().write({
                    'radius_synced': True,
                    'last_sync_error': False,
                    'last_sync_date': fields.Datetime.now(),
                })
                try:
                    rec.message_post(body=_('Synchronized plan %s (%s) to RADIUS.') % (rec.name, groupname))
                except Exception:
                    pass

                ok_count += 1
                names.append(groupname)

            except Exception as e:
                last_error = str(e)
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                _logger.exception('Failed to sync plan %s', rec.name)
                rec.sudo().write({
                    'radius_synced': False,
                    'last_sync_error': last_error,
                    'last_sync_date': fields.Datetime.now(),
                })
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Notifikimi për UI
        if ok_count == len(self):
            msg = _('Plan "%s" synced to radgroupreply') % (names[0]) if ok_count == 1 else _(
                '%d subscription(s) synced successfully') % ok_count
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync'), 'message': msg, 'type': 'success', 'sticky': False}
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d succeeded, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Sync (Partial/Failed)'), 'message': msg, 'type': 'warning',
                           'sticky': False}
            }

    # -------------------------------------------------------------------------
    # Remove from RADIUS (delete group attributes)
    # -------------------------------------------------------------------------
    def action_remove_from_radius(self):
        ok_count, names, last_error = 0, [], None

        for rec in self:
            try:
                rec._remove_from_radius()
                ok_count += 1
                names.append(rec._groupname())
            except Exception as e:
                last_error = str(e)

        if ok_count == len(self):
            msg = _('Plan "%s" removed from radgroupreply') % (names[0]) if ok_count == 1 else _('%d plan(s) removed from RADIUS') % ok_count
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal'), 'message': msg, 'type': 'info', 'sticky': False}
            }
        else:
            failed = len(self) - ok_count
            msg = _('%d removed, %d failed') % (ok_count, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('RADIUS Removal (Partial/Failed)'), 'message': msg, 'type': 'warning', 'sticky': False}
            }

    def _remove_from_radius(self):
        self.ensure_one()
        conn = None
        try:
            conn = self._get_radius_connection()
            cur = conn.cursor()
            groupname = self._groupname()

            cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))
            conn.commit()

            self.sudo().write({
                'radius_synced': False,
                'last_sync_date': fields.Datetime.now(),
                'last_sync_error': False,
            })

            try:
                self.message_post(body=_('Removed plan %s (%s) from RADIUS.') % (self.name, groupname))
            except Exception:
                pass

            _logger.info('Removed plan %s from RADIUS', self.name)

        except Exception as e:
            if conn:
                try: conn.rollback()
                except Exception: pass
            err = str(e)
            _logger.error('Failed to remove plan %s from RADIUS: %s', self.name, err)
            self.message_post(body=_('RADIUS removal failed: %s') % err, message_type='notification', subtype_xmlid='mail.mt_note')
            raise UserError(_('RADIUS removal failed:\n%s') % err)
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    # -------------------------------------------------------------------------
    # ORM Hooks (optional behaviours)
    # -------------------------------------------------------------------------
    def unlink(self):
        # Hiqe nga RADIUS përpara se të fshihet nga Odoo
        for rec in self:
            if rec.radius_synced:
                try:
                    rec._remove_from_radius()
                except Exception as e:
                    _logger.warning('Could not remove plan %s from RADIUS on delete: %s', rec.name, e)
        return super().unlink()


class AsrRadiusAttribute(models.Model):
    _name = "asr.radius.attribute"
    _description = "RADIUS Attribute for Plan"
    _order = "id asc"

    attribute = fields.Char(required=True, help="e.g. Mikrotik-Rate-Limit, Session-Timeout, Idle-Timeout")
    op = fields.Char(default=':=', help="Operator, e.g. :=, ==, +=, =")
    value = fields.Char(required=True)
    subscription_id = fields.Many2one('asr.subscription', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True, readonly=True)

    @api.constrains('op')
    def _check_op(self):
        for rec in self:
            if rec.op not in (':=', '==', '+=', '='):
                raise ValidationError(_('Invalid operator: %s') % (rec.op or ''))

    # Në çdo ndryshim të linjave → shëno planin si jo-sinkron
    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.mapped('subscription_id').sudo().write({'radius_synced': False})
        return recs

    def write(self, vals):
        res = super().write(vals)
        self.mapped('subscription_id').sudo().write({'radius_synced': False})
        return res

    def unlink(self):
        subs = self.mapped('subscription_id')
        res = super().unlink()
        subs.sudo().write({'radius_synced': False})
        return res

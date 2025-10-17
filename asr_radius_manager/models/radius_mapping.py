# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging
import re

_logger = logging.getLogger(__name__)

MANAGED_GROUP_ATTRS = {
    "Service-Type",
    "Framed-Protocol",
    "Framed-Pool",
    "Cisco-AVPair",
    "WISPr-Bandwidth-Max-Up",
    "WISPr-Bandwidth-Max-Down",
    "Mikrotik-Rate-Limit",
    "Acct-Interim-Interval",
    "Session-Timeout",
    "Idle-Timeout",
}
MANAGED_USER_ATTRS = {
    "Framed-IP-Address",
    "Framed-IPv6-Prefix",
    "Mikrotik-Rate-Limit",
    "Framed-Pool",
    "Cisco-AVPair",
}

def _bool_param(env, key, default=False):
    val = env["ir.config_parameter"].sudo().get_param(key, "1" if default else "0")
    return str(val).lower() in ("1", "true", "t", "yes", "y")

class AsrSubscriptionRadiusMapping(models.Model):
    _inherit = "asr.subscription"

    acct_interim_interval = fields.Integer(
        string="Acct Interim Interval (s)",
        default=300,
        help="Sa shpesh NAS dërgon accounting interim updates."
    )

    @api.model
    def _vendor_flags(self):
        emit_cisco = _bool_param(self.env, "asr_radius.emit_cisco", True)
        emit_mikro = _bool_param(self.env, "asr_radius.emit_mikrotik", False)
        return emit_cisco, emit_mikro

    def _validate_vendor_attributes(self):
        return []

    @api.constrains(
        "name", "code", "rate_limit", "session_timeout",
        "cisco_policy_in", "cisco_policy_out",
        "cisco_pool_active", "ip_pool_active"
    )
    def _constrain_subscription_vendor_attrs(self):
        return

    def _build_groupreply_attrs(self):
        def parse_rate_limit(text):
            t = (text or "").strip()
            m = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*[mM]?\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*[mM]?\s*$', t)
            if m:
                return float(m.group(1)), float(m.group(2))
            m1 = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*[mM]?\s*$', t)
            if m1:
                v = float(m1.group(1))
                return v, v
            return 49.0, 49.0

        res = {}
        for rec in self:
            up_mbps, down_mbps = parse_rate_limit(getattr(rec, "rate_limit", ""))
            label_in = f"{int(round(up_mbps))}M"
            label_out = f"{int(round(down_mbps))}M"
            wispr_up = str(int(round(up_mbps * 1_000_000)))
            wispr_down = str(int(round(down_mbps * 1_000_000)))
            pool = (getattr(rec, "ip_pool_active", None) or "PPP-POOL").strip()

            attrs = [
                {"attribute": "Service-Type", "op": ":=", "value": "Framed-User"},
                {"attribute": "Framed-Protocol", "op": ":=", "value": "PPP"},
                {"attribute": "Framed-Pool", "op": ":=", "value": pool},
                {"attribute": "Cisco-AVPair", "op": ":=", "value": f"ip:sub-policy-in={label_in}"},
                {"attribute": "Cisco-AVPair", "op": ":=", "value": f"ip:sub-policy-out={label_out}"},
                {"attribute": "WISPr-Bandwidth-Max-Up", "op": ":=", "value": wispr_up},
                {"attribute": "WISPr-Bandwidth-Max-Down", "op": ":=", "value": wispr_down},
            ]
            res[rec.id] = attrs
        return res

    def _delete_group_attrs(self, conn, groupname, attrs_to_manage):
        if not attrs_to_manage:
            return
        placeholders = ",".join(["%s"] * len(attrs_to_manage))
        sql = f"DELETE FROM radgroupreply WHERE groupname=%s AND attribute IN ({placeholders})"
        with conn.cursor() as cr:
            cr.execute(sql, tuple([groupname] + list(attrs_to_manage)))

    def _insert_group_attrs(self, conn, groupname, attrs):
        if not attrs:
            return
        data = [(groupname, a["attribute"], a["op"], str(a["value"])) for a in attrs]
        sql = "INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s,%s,%s,%s)"
        with conn.cursor() as cr:
            cr.executemany(sql, data)

    def action_sync_attributes_to_radius(self):
        ok, last_error, names = 0, None, []
        for rec in self:
            conn = None
            try:
                conn = rec._get_radius_connection()
                groupname = rec._groupname()
                desired = self._build_groupreply_attrs().get(rec.id, [])
                manage = set(MANAGED_GROUP_ATTRS) | set(a["attribute"] for a in desired if a.get("attribute"))
                self._delete_group_attrs(conn, groupname, manage)
                self._insert_group_attrs(conn, groupname, desired)
                conn.commit()
                rec.sudo().write({
                    "radius_synced": True,
                    "last_sync_error": False,
                    "last_sync_date": fields.Datetime.now(),
                })
                try:
                    rec.message_post(body=_("Synchronized plan %s (%s) to RADIUS.") % (rec.name, groupname))
                except Exception:
                    pass
                ok += 1
                names.append(groupname)
            except Exception as e:
                last_error = str(e)
                if conn:
                    try: conn.rollback()
                    except Exception: pass
                rec.sudo().write({
                    "radius_synced": False,
                    "last_sync_error": last_error,
                    "last_sync_date": fields.Datetime.now(),
                })
                _logger.exception("Plan sync failed for %s", rec.name)
            finally:
                if conn:
                    try: conn.close()
                    except Exception: pass

        if ok == len(self):
            msg = _('Plan "%s" synced to radgroupreply') % (names[0]) if ok == 1 else _("%d subscription(s) synced successfully") % ok
            return {"type": "ir.actions.client", "tag": "display_notification",
                    "params": {"title": _("RADIUS Sync"), "message": msg, "type": "success", "sticky": False}}
        else:
            failed = len(self) - ok
            msg = _("%d succeeded, %d failed") % (ok, failed)
            if last_error:
                msg = f"{msg}\n{last_error}"
            return {"type": "ir.actions.client", "tag": "display_notification",
                    "params": {"title": _("RADIUS Sync (Partial/Failed)"), "message": msg, "type": "warning", "sticky": False}}

class AsrRadiusUserMapping(models.Model):
    _inherit = "asr.radius.user"

    framed_ip = fields.Char(string="Static IPv4 (Framed-IP-Address)")
    framed_ipv6_prefix = fields.Char(string="IPv6 Prefix (Framed-IPv6-Prefix)")
    custom_rate_limit = fields.Char(string="Custom Rate Limit (Mikrotik-Rate-Limit)")
    override_pool = fields.Char(string="Override Pool (Framed-Pool / Cisco ip:addr-pool=)")

    def _build_user_radreply_attrs(self):
        res = {}
        emit_cisco = _bool_param(self.env, "asr_radius.emit_cisco", True)
        emit_mikro = _bool_param(self.env, "asr_radius.emit_mikrotik", False)
        for rec in self:
            attrs = []
            if rec.framed_ip:
                attrs.append({"attribute": "Framed-IP-Address", "op": ":=", "value": rec.framed_ip})
            if rec.framed_ipv6_prefix:
                attrs.append({"attribute": "Framed-IPv6-Prefix", "op": ":=", "value": rec.framed_ipv6_prefix})
            if rec.custom_rate_limit and emit_mikro:
                attrs.append({"attribute": "Mikrotik-Rate-Limit", "op": ":=", "value": rec.custom_rate_limit})
            if rec.override_pool:
                if emit_mikro:
                    attrs.append({"attribute": "Framed-Pool", "op": ":=", "value": rec.override_pool})
                if emit_cisco:
                    attrs.append({"attribute": "Cisco-AVPair", "op": ":=", "value": f"ip:addr-pool={rec.override_pool}"})
            res[rec.id] = attrs
        return res

    def _delete_user_attrs(self, conn, username, attrs_to_manage):
        if not attrs_to_manage:
            return
        placeholders = ",".join(["%s"] * len(attrs_to_manage))
        sql = f"DELETE FROM radreply WHERE username=%s AND attribute IN ({placeholders})"
        with conn.cursor() as cr:
            cr.execute(sql, tuple([username] + list(attrs_to_manage)))

    def _insert_user_attrs(self, conn, username, attrs):
        if not attrs:
            return
        data = [(username, a["attribute"], a["op"], str(a["value"])) for a in attrs]
        sql = "INSERT INTO radreply (username, attribute, op, value) VALUES (%s,%s,%s,%s)"
        with conn.cursor() as cr:
            cr.executemany(sql, data)

    def _sync_radreply_to_radius(self):
        for rec in self:
            conn = None
            try:
                conn = rec._get_radius_conn() if hasattr(rec, "_get_radius_conn") else rec._get_radius_connection()
                desired = self._build_user_radreply_attrs().get(rec.id, [])
                manage = set(MANAGED_USER_ATTRS) | set(a["attribute"] for a in desired if a.get("attribute"))
                self._delete_user_attrs(conn, rec.username, manage)
                self._insert_user_attrs(conn, rec.username, desired)
                conn.commit()
            except Exception as e:
                if conn:
                    try: conn.rollback()
                    except Exception: pass
                _logger.exception("User radreply sync failed for %s: %s", rec.username, e)
                try:
                    rec.message_post(body=_("radreply sync FAILED for '%(u)s': %(err)s") % {"u": rec.username, "err": str(e)}, subtype_xmlid="mail.mt_note")
                except Exception:
                    pass
            finally:
                if conn:
                    try: conn.close()
                    except Exception: pass

    def action_sync_to_radius(self):
        res = super(AsrRadiusUserMapping, self).action_sync_to_radius()
        try:
            self._sync_radreply_to_radius()
        except Exception:
            pass
        return res

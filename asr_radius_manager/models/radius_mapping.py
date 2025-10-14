# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

# Fshijmë vetëm këto atribute përpara re-insert (idempotent, pa shkatërruar rreshta të tjerë)
MANAGED_GROUP_ATTRS = {
    "Cisco-AVPair",
    "Mikrotik-Rate-Limit",
    "Framed-Pool",
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

# -------------------------------------------------------------------------
# PLAN: radgroupreply mapping + validator
# -------------------------------------------------------------------------
class AsrSubscriptionRadiusMapping(models.Model):
    _inherit = "asr.subscription"

    # Jo hard-coded: e vendos nga UI
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

    # -------- Validator per-plan sipas togglave --------
    def _validate_vendor_attributes(self):
        errs = []
        emit_cisco, emit_mikro = self._vendor_flags()
        for rec in self:
            if emit_cisco and getattr(rec, "show_cisco", True):
                if not (getattr(rec, "cisco_policy_in", False) or getattr(rec, "cisco_policy_out", False)):
                    errs.append(_("[%s] Cisco: mungojnë policy in/out.") % rec.display_name)
                pool = getattr(rec, "cisco_pool_active", False) or getattr(rec, "ip_pool_active", False)
                if not pool:
                    errs.append(_("[%s] Cisco: mungon active address pool.") % rec.display_name)
            if emit_mikro:
                if not getattr(rec, "rate_limit", False):
                    errs.append(_("[%s] Mikrotik: mungon rate_limit.") % rec.display_name)
                if not (getattr(rec, "ip_pool_active", False) or getattr(rec, "ip_pool_expired", False)):
                    errs.append(_("[%s] Mikrotik: mungon IP pool (active/expired).") % rec.display_name)
        return errs

    # -------- SOFT në save (create/write), STRICT vetëm në SYNC --------
    @api.constrains(
        "name", "code", "rate_limit", "session_timeout",
        "cisco_policy_in", "cisco_policy_out",
        "cisco_pool_active", "ip_pool_active"
    )
    def _constrain_subscription_vendor_attrs(self):
        """
        Mos blloko në ruajtje (create/write). Këtë e bëjmë STRICT vetëm në action_sync_*.
        Nëse dikush do enforce edhe në save, mund të kalojë context={'vendor_strict': True}.
        """
        emit_cisco, emit_mikro = self._vendor_flags()
        if not (emit_cisco or emit_mikro):
            return
        if not self.env.context.get('vendor_strict', False):
            return  # no-op në save
        errs = self._validate_vendor_attributes()
        if errs:
            raise ValidationError("\n".join(errs))

    # -------- Ndërto rreshtat për radgroupreply (idempotent) --------
    def _build_groupreply_attrs(self):
        res = {}
        emit_cisco, emit_mikro = self._vendor_flags()
        for rec in self:
            attrs = []
            # Atribute që ke vendosur manualisht në attribute_ids (respektohen)
            seen = set()
            for line in rec.attribute_ids:
                attr = (line.attribute or "").strip()
                op = (line.op or ":=").strip()
                val = (line.value or "").strip()
                if not attr:
                    continue
                attrs.append({"attribute": attr, "op": op, "value": val})
                seen.add((attr.lower(), val))

            # Standard/shared
            inter = str(getattr(rec, "acct_interim_interval", 300) or 300)
            if ("acct-interim-interval", inter) not in seen:
                attrs.append({"attribute": "Acct-Interim-Interval", "op": ":=", "value": inter})
                seen.add(("acct-interim-interval", inter))

            sess = getattr(rec, "session_timeout", False)
            if sess and ("session-timeout", str(int(sess))) not in seen:
                attrs.append({"attribute": "Session-Timeout", "op": ":=", "value": str(int(sess))})
                seen.add(("session-timeout", str(int(sess))))

            if ("idle-timeout", "600") not in seen:
                attrs.append({"attribute": "Idle-Timeout", "op": ":=", "value": "600"})
                seen.add(("idle-timeout", "600"))

            # Cisco (formati yt: subscriber:service-policy-*, ip:addr-pool=POOL)
            if emit_cisco and getattr(rec, "show_cisco", True):
                if getattr(rec, "cisco_policy_in", False):
                    val = f"subscriber:service-policy-in {rec.cisco_policy_in.strip()}"
                    if ("cisco-avpair", val) not in seen:
                        attrs.append({"attribute": "Cisco-AVPair", "op": ":=", "value": val})
                        seen.add(("cisco-avpair", val))
                if getattr(rec, "cisco_policy_out", False):
                    val = f"subscriber:service-policy-out {rec.cisco_policy_out.strip()}"
                    if ("cisco-avpair", val) not in seen:
                        attrs.append({"attribute": "Cisco-AVPair", "op": ":=", "value": val})
                        seen.add(("cisco-avpair", val))
                pool = getattr(rec, "cisco_pool_active", False) or getattr(rec, "ip_pool_active", False)
                if pool:
                    val = f"ip:addr-pool={pool.strip()}"
                    if ("cisco-avpair", val) not in seen:
                        attrs.append({"attribute": "Cisco-AVPair", "op": ":=", "value": val})
                        seen.add(("cisco-avpair", val))

            # Mikrotik (shto vetëm nëse mungojnë)
            if emit_mikro:
                if getattr(rec, "rate_limit", False):
                    val = rec.rate_limit.strip()
                    if ("mikrotik-rate-limit", val) not in seen:
                        attrs.append({"attribute": "Mikrotik-Rate-Limit", "op": ":=", "value": val})
                        seen.add(("mikrotik-rate-limit", val))
                if getattr(rec, "ip_pool_active", False):
                    val = rec.ip_pool_active.strip()
                    if ("framed-pool", val) not in seen:
                        attrs.append({"attribute": "Framed-Pool", "op": ":=", "value": val})
                        seen.add(("framed-pool", val))

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

    # -------- OVERRIDE: sync i planit me fshirje selektive --------
    def action_sync_attributes_to_radius(self):
        ok, last_error, names = 0, None, []
        for rec in self:
            conn = None
            try:
                # STRICT VALIDATION në SYNC (jo në save)
                errs = rec._validate_vendor_attributes()
                if errs:
                    raise UserError("\n".join(errs))

                conn = rec._get_radius_connection()
                groupname = rec._groupname()
                desired = self._build_groupreply_attrs().get(rec.id, [])

                # Menaxho: atributet “tona” + ato që do fusim (idempotencë)
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

# -------------------------------------------------------------------------
# USER: radreply overrides per-user (IPv4/IPv6/Rate/Pool)
# -------------------------------------------------------------------------
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
                # moduli yt përdor _get_radius_conn(); fallback te _get_radius_connection
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
                    rec.message_post(body=_("radreply sync FAILED for '%(u)s': %(err)s") % {
                        "u": rec.username, "err": str(e)}, subtype_xmlid="mail.mt_note")
                except Exception:
                    pass
            finally:
                if conn:
                    try: conn.close()
                    except Exception: pass

    # Pas radcheck/radusergroup (super), fut radreply overrides
    def action_sync_to_radius(self):
        res = super(AsrRadiusUserMapping, self).action_sync_to_radius()
        try:
            self._sync_radreply_to_radius()
        except Exception:
            pass
        return res

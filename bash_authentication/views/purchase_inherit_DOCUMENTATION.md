# Purchase Order Customization Documentation

## File: purchase_inherit.xml

### Overview
Ky file modifikon view-et e Purchase Orders për të kontrolluar visibility të fushave të caktuara.

---

## Customizations

### 1. Tree View - User Field Label
**Lines: 7-9**
```xml
<attribute name="string">Assigned To</attribute>
```

**Çfarë bën:**
- Ndrysho label-in e `user_id` field nga "Responsible" në "Assigned To"

**Impact:**
- ✅ LOW - Vetëm ndryshim kozmetik

---

### 2. Form View - Price Unit Visibility
**Lines: 18-23**
```xml
<attribute name="groups">bash_authentication.group_admin</attribute>
```

**Çfarë bën:**
- Fsheh fushën `price_unit` (çmimi për njësi) në:
  - Tree view të order lines (brenda Purchase Order)
  - Form view të order lines
- Vetëm përdoruesit në grupin `bash_authentication.group_admin` mund ta shohin

**Impact:**
- ⚠️ MEDIUM - Ndikon workflow-in e Purchase Orders

**Users të prekur:**
- ❌ Purchase Users (normal) - NUK shohin çmimet
- ❌ Purchase Managers - NUK shohin çmimet (nëse nuk janë në group_admin)
- ✅ Admins (bash_authentication.group_admin) - Shohin çmimet

---

## Security Implications

### Kush është në `bash_authentication.group_admin`?
Shiko në: Settings → Users & Companies → Groups → bash_authentication/Admin

### A duhet të mbetet kjo logjikë?

**PO - Nëse:**
- ✅ Ka arsye security/business për të fshehur çmimet nga Purchase Users
- ✅ Vetëm Finance/Admins duhet të shohin cost details
- ✅ Ka separation of duties requirements

**JO - Nëse:**
- ❌ Purchase Users kanë nevojë të shohin çmimet për të bërë vendimet
- ❌ Po krijon confusion/workflow issues
- ❌ Të gjithë purchase staff duhet access

---

## Alternative Solutions

### Option 1: Hiq restriction-in (të gjithë shohin çmimet)
```xml
<!-- Komento ose fshi lines 18-23 -->
```

### Option 2: Përdor Purchase Manager group (Odoo standard)
```xml
<attribute name="groups">purchase.group_purchase_manager</attribute>
```

### Option 3: Krijo grup të dedikuar
```xml
<attribute name="groups">bash_authentication.group_purchase_admin</attribute>
```

---

## Testing Checklist

- [ ] Test me përdorues normal (jo admin) - A shohin çmimet?
- [ ] Test me Purchase Manager - A shohin çmimet?
- [ ] Test me bash_authentication.group_admin - A shohin çmimet?
- [ ] Test purchase workflow end-to-end
- [ ] Verifikoni që nuk ka broken screens

---

## Decision Log

**Date:** 2024-12-18
**Decision:** Keep current logic (price hiding for non-admins)
**Reason:** [TO BE FILLED BY TEAM]
**Reviewed by:** [TO BE FILLED]

---

## Notes

- Kjo customization është specifike për bash_authentication module
- Nëse uninstall bash_authentication, price visibility kthehet në normal
- Groups janë defined në: `bash_authentication/data/groups.xml`

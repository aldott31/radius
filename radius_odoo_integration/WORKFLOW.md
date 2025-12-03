# Sales & Finance Workflow - RADIUS ISP Management

## 📋 Qëllimi
Ky workflow implementon **separation of duties** midis Sales dhe Finance departamenteve për të siguruar kontrolle më të mira financiare dhe audit trail të qartë.

---

## 🔐 Grupet e Sigurisë (Security Groups)

### 1. **CRM: Sales** (`group_isp_sales`)
**Përgjegjësi:** Krijimi i quotations dhe konfirmimi i sale orders

**Akses:**
- ✅ Krijon dhe edito **Quotations** (Draft Sale Orders)
- ✅ Konfirmon **Sale Orders** (Confirm button)
- ✅ Krijon dhe edito **Customers** (res.partner)
- ✅ Shikon **Products** dhe **Subscription Packages** (read-only)
- ✅ Shikon **RADIUS Users** (read/write për sync)
- ❌ **NUK mund** të krijojë **Invoices** (account.move)
- ❌ **NUK mund** të regjistrojë **Payments** (account.payment)
- ❌ **NUK mund** të provision RADIUS (vetëm Manager)

**KPI të Sales:**
- New customers per month
- Quotations sent & conversion rate
- Average deal size
- Revenue pipeline

---

### 2. **CRM: Finance** (`group_isp_finance`)
**Përgjegjësi:** Krijimi i invoices dhe menaxhimi i pagesave

**Akses:**
- ✅ Shikon **Confirmed Sale Orders** (read-only)
- ✅ Krijon **Invoices** nga sale orders (account.move)
- ✅ Validizon dhe posto **Invoices**
- ✅ Regjistron **Payments** (account.payment)
- ✅ Shikon **Customers** për billing info (read-only për çmimet)
- ✅ Menaxhon **Contracts** dhe **Billing Terms**
- ✅ Pezullo klientë për mostagim (suspend action)
- ❌ **NUK mund** të editojë **Sale Order prices** ose **discounts**
- ❌ **NUK mund** të provision RADIUS (vetëm Manager)

**KPI të Finance:**
- Invoices issued per month
- DSO (Days Sales Outstanding)
- Collection rate
- Overdue invoices amount

---

### 3. **CRM: Manager** (`group_isp_manager`)
**Përgjegjësi:** Full access dhe approvals

**Akses:**
- ✅ **Full access** në të gjitha operacionet
- ✅ Approval të **discounts** dhe **credit limits**
- ✅ Override të workflow restrictions
- ✅ Access në të gjitha **reports** dhe **dashboards**
- ✅ Provision RADIUS users

---

## 🔄 Workflow i Plotë

### **FAZA 1: Sales Creates Quotation**
```
User: Sales Team Member
Path: Sales → Quotations → Create

Steps:
1. Kliko "Create" për quotation të re
2. Zgjedh/krijon Customer:
   - Name, Phone, Email, Address
   - NIPT (për biznese - SLA 2/3)
   - SLA Level (1=Individual, 2=SMB, 3=Enterprise)
3. Zgjedh Subscription Package (auto-populates nga customer)
4. Shto Order Lines:
   - Product: [RADIUS Service] 100M/10M Package
   - Quantity: 12 (për 12 muaj shërbim)
   - Price: Automatik nga product
5. Zgjedh Payment Terms (Immediate, Net 7, Net 15, Net 30)
6. 🔴 CONFIRM SALE ORDER

Result:
✅ Sale Order status = "sale"
✅ Invoice Status = "to invoice"
⏳ Waiting for Finance to create invoice
```

---

### **FAZA 2: Finance Creates Invoice** ⭐
```
User: Finance Team Member
Path: Sales → Orders → Orders to Invoice

Steps:
1. Open "Orders to Invoice" view (filter: invoice_status='to invoice')
2. Review sale order details:
   - Customer info
   - Pricing accuracy
   - Payment terms
   - Subscription months (quantity)
3. Select order(s) → Action → "Create Invoice"
4. Choose invoice type:
   - Regular Invoice (për full amount)
   - Down Payment (advance/deposit)
5. 🔴 CREATE & VALIDATE INVOICE
6. Send invoice via Email/Portal to customer

Result:
✅ Invoice status = "posted"
✅ Payment Status = "not_paid"
⏳ Waiting for customer payment
```

---

### **FAZA 3: Finance Registers Payment**
```
User: Finance Team Member
Path: Accounting → Customers → Invoices

Steps:
1. Filter: "Unpaid Invoices"
2. Open invoice
3. Kliko "Register Payment"
   - Payment Date: Today
   - Amount: 36,000 ALL
   - Payment Method: Bank Transfer / Cash / POS
   - Memo: Payment reference
4. 🔴 CREATE PAYMENT

Auto-triggers (System):
✅ payment_state → "paid"
✅ _compute_payment_state() detects payment
✅ _update_partner_service_paid_until() runs
✅ service_paid_until = payment_date + subscription_months
✅ Payment statistics updated:
   - total_paid_amount
   - last_payment_date
   - last_payment_amount
✅ Message posted to customer chatter
✅ Email notification sent (if configured)

Result:
✅ Invoice marked as PAID
✅ Customer service extended by X months
✅ Payment recorded in accounting
```

---

## 🎯 Benefitet e Workflow-it

### **1. Separation of Duties (SOD)**
```
Sales    → Revenue Generation (Fokus: Shitje)
Finance  → Revenue Recognition (Fokus: Collection)

✅ Parandalon konflikt interesi
✅ Double-check para se invoice krijohet
✅ Audit trail i pastër
```

### **2. Kontrolle Financiare**
```
Finance verifikon para invoicing:
- Pricing correctness
- Quantity/months alignment
- Tax calculations (VAT 20%)
- Payment terms
- Customer credit limit
```

### **3. Skalabilitet**
```
Për 50,000+ customers:
- Sales fokuson në acquisition & renewals
- Finance fokuson në billing cycles & collections
- Batch invoicing për 1000+ invoices/ditë
```

### **4. Compliance**
```
✅ IFRS/Albanian Accounting Standards
✅ Internal audit requirements
✅ Fiscal printer integration (Albanian law)
✅ Clear audit trail për çdo transaction
```

---

## 📊 Dashboards & Reports

### **Sales Dashboard**
```
- New Customers This Month
- Quotations Sent & Conversion Rate
- Average Deal Size (ALL)
- Revenue Pipeline (ALL)
- Top Selling Packages
```

### **Finance Dashboard**
```
- Invoices Issued This Month
- Total AR (Accounts Receivable)
- DSO (Days Sales Outstanding) - Target: <20 days
- Collection Rate (%)
- Overdue Invoices (Count & Amount)
```

---

## ⚙️ Setup Instructions

### **1. Assign Users to Groups**
```
Settings → Users & Companies → Users

Sales Team:
- John Doe → Add to group "CRM: Sales"

Finance Team:
- Jane Smith → Add to group "CRM: Finance"

Management:
- CEO → Add to group "CRM: Manager"
```

### **2. Configure Payment Terms**
```
Accounting → Configuration → Payment Terms

Create:
- Immediate Payment (0 days) - For B2C
- Net 7 (7 days) - For small business
- Net 15 (15 days) - For medium business
- Net 30 (30 days) - For enterprise
```

### **3. Test Workflow**
```
Test Case 1: Sales creates quotation ✅
Test Case 2: Sales CANNOT create invoice ❌ (should fail)
Test Case 3: Finance creates invoice from sale order ✅
Test Case 4: Finance registers payment ✅
Test Case 5: service_paid_until auto-updates ✅
```

---

## 🚫 Common Mistakes & Troubleshooting

### **Error: "You cannot create invoices"**
```
Cause: Sales user trying to create invoice
Solution: Only Finance team can create invoices
Action: Contact Finance team to process the order
```

### **Error: "You cannot modify this sale order"**
```
Cause: Finance user trying to edit prices
Solution: Only Sales (or Manager) can edit prices
Action: Contact Sales team or Manager for approval
```

### **service_paid_until not updating**
```
Possible causes:
1. Invoice not marked as paid (payment_state != 'paid')
2. No subscription_months found (check sale order quantity)
3. Customer not marked as is_radius_customer

Debug:
- Check invoice payment_state
- Check sale order → order_line → quantity
- Check customer → is_radius_customer checkbox
- Check logs: grep "service_paid_until" /var/log/odoo.log
```

---

## 📞 Support

Për çështje teknike ose pyetje rreth workflow-it, kontaktoni:
- **Technical Support:** IT Department
- **Workflow Questions:** Finance Manager
- **Access Rights:** System Administrator

---

**Last Updated:** 2025-12-03
**Version:** 1.0
**Module:** radius_odoo_integration

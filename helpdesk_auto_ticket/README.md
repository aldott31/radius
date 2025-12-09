# Helpdesk Auto Ticket on Payment

## Përshkrim
Ky modul krijon automatikisht një ticket helpdesk kur një invoice paguhet nga financa dhe statusi i klientit ndryshon automatikisht nga **"Lead"** në **"Paid"**.

## Funksionaliteti

### Workflow:
1. **Krijoni një Quotation** → Konfirmoni → **Invoice krijohet**
2. **Financa regjistron payment** → Invoice bëhet **"Paid"**
3. **Sistemi automatikisht**:
   - Përditëson `customer_status` nga `'lead'` → `'paid'`
   - **Krijon një ticket helpdesk** me subject **"Kontrate e re"**

### Detajet e Ticket-it:
- **Subject**: "Kontrate e re"
- **Description**:
  - Emri i klientit
  - Invoice number
  - Amount paid
  - Payment date
  - Status change: Lead → Paid
- **Customer**: Linkohet me klientin
- **Assigned to**: Punonjësi i konfiguruar (default)
- **Team**: Team-i i konfiguruar (default)
- **Priority**: Normal

## Instalimi

1. **Kopjoni modulin** në `custom-addons/` folder
2. **Restartoni Odoo**:
   ```bash
   docker-compose restart web
   ```
3. **Update Apps List**:
   - Shkoni në Apps → Update Apps List
4. **Instaloni modulin**:
   - Kërkoni: "Helpdesk Auto Ticket"
   - Klikoni **Install**

## Konfigurimi

### Vendosni Punonjësin Default

1. **Gjeni User ID-në e punonjësit**:
   - Shkoni në Settings → Users & Companies → Users
   - Hapni punonjësin që dëshironi
   - Shihni URL-në: `...res.users/action/XXX` (XXX është ID-ja)

2. **Update konfigurimin**:
   - Shkoni në Settings → Technical → Parameters → System Parameters
   - Gjeni: `helpdesk_auto_ticket.default_employee_id`
   - Vendosni ID-në e punonjësit

### Vendosni Team-in Default

1. **Gjeni Team ID-në**:
   - Shkoni në Helpdesk → Configuration → Teams
   - Hapni team-in që dëshironi
   - Shihni URL-në: `...team.helpdesk/action/XXX`

2. **Update konfigurimin**:
   - Settings → Technical → Parameters → System Parameters
   - Gjeni: `helpdesk_auto_ticket.default_team_id`
   - Vendosni ID-në e team-it

## Si Funksionon

### Flow Diagram:
```
Sales → Quotation → Confirm → Invoice
                                  ↓
                          Finance Registers Payment
                                  ↓
                          Invoice Status: PAID
                                  ↓
                   radius_odoo_integration updates:
                   customer_status: lead → paid
                                  ↓
                   helpdesk_auto_ticket detects change
                                  ↓
                   ✅ TICKET CREATED: "Kontrate e re"
```

### Kod:
```python
# account_move.py override
def _update_partner_service_paid_until(self):
    old_status = self.partner_id.customer_status  # Store old

    super()._update_partner_service_paid_until()  # Parent updates to 'paid'

    # Detect change from lead → paid
    if old_status == 'lead' and self.partner_id.customer_status == 'paid':
        self._create_payment_ticket()  # ← Creates helpdesk ticket
```

## Test Scenario

1. **Krijoni një klient të ri** (status = 'lead')
2. **Krijoni një Quotation** për këtë klient
3. **Konfirmoni Quotation** → Sale Order
4. **Krijoni Invoice**
5. **Regjistro Payment** (Accounting → Invoices → Register Payment)
6. **Kontrolloni**:
   - Customer status → **'paid'** ✅
   - Helpdesk → Tickets → Ticket i ri me subject **"Kontrate e re"** ✅

## Log Messages

Kontrollo logs për konfirmim:
```bash
docker-compose logs -f web | grep "Auto-created helpdesk ticket"
```

Shembull output:
```
✅ Auto-created helpdesk ticket #HELP/00001 for invoice INV/2025/00001 - Customer: Klea (Status: lead → paid)
```

## Varësitë
- `account` - Accounting module
- `odoo_website_helpdesk` - Helpdesk module
- `radius_odoo_integration` - Customer status management & payment automation

## Troubleshooting

### Ticket nuk krijohet?
1. Kontrolloni që customer_status ishte **'lead'** para payment
2. Kontrolloni logs: `docker-compose logs -f web`
3. Verifikoni që moduli `odoo_website_helpdesk` është instaluar
4. Kontrolloni System Parameters për employee_id dhe team_id

### Si të gjej User ID dhe Team ID?
- **User ID**: Settings → Users → Hap user → Shiko URL (`res.users/X`)
- **Team ID**: Helpdesk → Teams → Hap team → Shiko URL (`team.helpdesk/X`)

## Autor
Custom Module - 2024

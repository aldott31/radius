# 🚀 QUICK START - Si të Përdorësh Template Kontrate

## ✅ GATSHËM PËR PËRDORIM!

Sistemi është i konfiguruar plotësisht. Tani duhet vetëm të:

---

## 📝 **Hapi 1: Krijo Template DOCX** (5 minuta)

### A. Konverto PDF në Word

1. **Hap PDF-në** që më dërgove: `Kontrata tip OK 3.pdf`
2. **Konverto në Word** duke përdorur:
   - Microsoft Word: File → Open → Zgjedh PDF
   - Adobe Acrobat: File → Export To → Microsoft Word
   - Online: https://www.ilovepdf.com/pdf_to_word

3. **Ruaj si Word**: `contract_template.docx`

### B. Shto Placeholders

Hap dokumentin Word dhe **zëvendëso fushat bosh** me placeholders:

#### Shembuj:
```
Vend të shkruani "Data: __________"
Shkruaj:         "Data: {{ contract_date }}"

Vend të shkruani "Nr. Kontratës: __________"
Shkruaj:         "Nr. Kontratës: {{ contract_number }}"

Vend të shkruani "Emri: __________"
Shkruaj:         "Emri: {{ emri_individ }}"

Vend të shkruani "Shërbimi Internet: __________"
Shkruaj:         "Shërbimi Internet: {{ sherbimi_internet }}"

Vend të shkruani "Totali: __________"
Shkruaj:         "Totali: {{ total }}"
```

#### 📋 Lista e Plotë e Placeholders:

**Kontrata:**
- `{{ contract_date }}` - Data
- `{{ contract_number }}` - Nr. Kontratës
- `{{ afati_pagesa }}` - Afati/Pagesa (p.sh. "12 muaj / Parapagim")
- `{{ nr_perdoruesit }}` - Nr. Përdoruesit

**Muaji Paguar (1-12):**
- `{{ muaj_1 }}` `{{ muaj_2 }}` ... `{{ muaj_12 }}`

**Klienti Individ:**
- `{{ emri_individ }}` - Emri
- `{{ adresa_individ }}` - Adresa
- `{{ mobile_individ }}` - Mobile
- `{{ email_individ }}` - Email

**Kompani/Biznes:**
- `{{ emri_kompanie }}` - Emri
- `{{ nuis }}` - NUIS
- `{{ adresa_kompanie }}` - Adresa
- `{{ mobile_kompanie }}` - Mobile
- `{{ email_kompanie }}` - Email

**Shërbimet:**
- `{{ lloji_lidhjes }}` - Lloji Lidhjes (p.sh. "Fiber Optike")
- `{{ cmimi_lloji_lidhjes }}` - Çmimi (p.sh. "$ 10.00")
- `{{ sherbimi_internet }}` - Emri i Planit Internet
- `{{ cmimi_internet }}` - Çmimi Internet
- `{{ sherbimi_tv }}` - Emri i Planit TV
- `{{ cmimi_tv }}` - Çmimi TV
- `{{ lloji_ip }}` - Lloji IP (Dinamike/Statike)
- `{{ cmimi_ip }}` - Çmimi IP
- `{{ pajisje_internet }}` - Pajisje Interneti (CPE)
- `{{ cmimi_pajisje_internet }}` - Çmimi Pajisje
- `{{ router_wifi }}` - Router/Wifi
- `{{ cmimi_router_wifi }}` - Çmimi Router
- `{{ total }}` - **TOTALI**

**Komente:**
- `{{ comment }}` - Komente

---

### C. Ruaj Template

1. **Ruaj dokumentin si**: `contract_template.docx`
2. **Vendos në folder**:
   ```
   C:\Users\Admin\Projects\o18\custom-addons\radius_odoo_integration\templates\contracts\contract_template.docx
   ```

---

## 🔧 **Hapi 2: Instalo Bibliotekën** (2 minuta)

Hap Command Prompt dhe shkruaj:

```bash
pip install docxtpl
```

Ose:

```bash
python -m pip install docxtpl
```

---

## 🔄 **Hapi 3: Restarto Odoo** (1 minut)

```bash
# Nëse përdor systemd (Linux)
sudo systemctl restart odoo

# Ose manual
sudo killall python3
# Pastaj starto Odoo përsëri
```

---

## 🎉 **Hapi 4: TESTO!**

1. **Hap Odoo** në browser
2. **Shko te**: Administrator → Contracts
3. **Zgjedh një kontratë** (duhet të jetë në status "Confirmed" ose "Active")
4. **Kliko butonin e gjelbër**: **"Download Contract"** 📥
5. **BOOM!** 💥 Shkarkohet dokumenti me të dhënat e plota!

---

## 📊 **Si Funksionon:**

```
┌─────────────────────────────────────────────────────────────┐
│  1. Klikon "Download Contract"                               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Sistemi merr të dhënat nga kontrata                     │
│     - Emri, adresa, mobile, email                            │
│     - Shërbimet, çmimet                                      │
│     - Data, afati, pagesa                                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Hap template: contract_template.docx                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Zëvendëson placeholders me të dhëna reale:              │
│     {{ contract_date }} → 23/12/2025                         │
│     {{ emri_individ }} → Filan Fisteku                       │
│     {{ sherbimi_internet }} → Fiber 100Mbps                  │
│     {{ total }} → $ 25.00                                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Gjeneron dokument të ri:                                 │
│     Contract_CONT/2025/0001.docx                             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  6. SHKARKON automatikisht! ✅                               │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ **Nëse Nuk Funksionon**

### Problem: "Template not found"

**Zgjidhja:**
- Sigurohu që file `contract_template.docx` është në vendin e duhur:
  ```
  radius_odoo_integration/templates/contracts/contract_template.docx
  ```

### Problem: "No module named 'docxtpl'"

**Zgjidhja:**
- Instalo bibliotekën: `pip install docxtpl`
- Restarto Odoo

### Problem: "Buttons not visible"

**Zgjidhja:**
- Butoni "Download Contract" shfaqet vetëm kur kontrata është "Confirmed" ose "Active"
- Nëse është "Draft", duhet ta konfirmosh më parë

---

## 🎁 **BONUS: Fallback Automatik**

Nëse **NUK** krijon template DOCX ose nuk instalon bibliotekën, sistemi do të përdorë **automatikisht PDF report-in** që tashmë funksionon!

Thjesht kliko "Download Contract" dhe do të merrësh një PDF.

---

## 📞 **Ndihmë?**

Shiko dokumentet e tjera:
- [README.md](README.md) - Udhëzues i plotë
- [INSTALLATION.md](INSTALLATION.md) - Instalim i bibliotekës
- [EXAMPLE_TEMPLATE.txt](EXAMPLE_TEMPLATE.txt) - Shembull template

---

*Sistemi është i gatshëm! Tani vetëm krijoni template-in dhe testoni! 🚀*

# 📄 Udhëzues për Template Kontrate

Ky folder përmban template-in për gjenerimin automatik të kontratave.

## 🎯 Si Funksionon

Kur klikoni butonin **"Download Contract"**, sistemi:
1. Merr template-in `contract_template.docx`
2. Zëvendëson të gjithë placeholders me të dhënat nga kontrata
3. Gjeneron një dokument të ri DOCX me të dhënat e plota
4. E shkarkon automatikisht

---

## 📝 Hapi 1: Krijoni Template DOCX

### A. Konverto PDF në Word

1. Hap PDF-në **"Kontrata tip OK 3.pdf"**
2. Përdor një nga këto metoda për të konvertuar në Word:
   - **Adobe Acrobat**: File → Export To → Microsoft Word
   - **Microsoft Word**: File → Open → Zgjidhni PDF-në
   - **Online Tools**: https://www.ilovepdf.com/pdf_to_word

3. Ruaje si: `contract_template.docx` në këtë folder

### B. Shto Placeholders

Hap dokumentin Word dhe zëvendëso fushat me placeholders. Format: `{{ placeholder_name }}`

---

## 🏷️ Lista e Placeholders

### **Kushtet e Kontratës**

```
Data: {{ contract_date }}
Afati/Pagesa: {{ afati_pagesa }}
Nr. Kontratës: {{ contract_number }}
Penaliteti: {{ penaliteti }}
Nr. Përdoruesit: {{ nr_perdoruesit }}
```

### **Muaji Paguar (Checkboxes 1-12)**

```
{{ muaj_1 }} {{ muaj_2 }} {{ muaj_3 }} {{ muaj_4 }}
{{ muaj_5 }} {{ muaj_6 }} {{ muaj_7 }} {{ muaj_8 }}
{{ muaj_9 }} {{ muaj_10 }} {{ muaj_11 }} {{ muaj_12 }}
```

### **Pajtimtar - Individ**

```
Emri: {{ emri_individ }}
Nr. Personal: {{ nr_personal }}
ID: {{ id_number }}
Datëlindja: {{ datelindja }}
Vendlindja: {{ vendlindja }}
Adresa: {{ adresa_individ }}
Mobile: {{ mobile_individ }}
E-mail: {{ email_individ }}
```

### **Person Juridik**

```
Emri: {{ emri_kompanie }}
NUIS: {{ nuis }}
Adresa: {{ adresa_kompanie }}
Përfaqësuesi ligjor: {{ perfaqesuesi_ligjor }}
Nr. Personal i përfaqësuesit: {{ nr_personal_perfaqesues }}
Mobile: {{ mobile_kompanie }}
E-mail: {{ email_kompanie }}
```

### **Shërbimet**

```
Lloji Lidhjes: {{ lloji_lidhjes }}          Çmimi: {{ cmimi_lloji_lidhjes }}
Shërbimi Internet: {{ sherbimi_internet }}  Çmimi: {{ cmimi_internet }}
Shërbimi TV: {{ sherbimi_tv }}              Çmimi: {{ cmimi_tv }}
Shërbimi Telefonik: {{ sherbimi_telefonik }} Çmimi: {{ cmimi_telefonik }}
Lloji i IP: {{ lloji_ip }}                  Çmimi: {{ cmimi_ip }}
Pajisje Interneti: {{ pajisje_internet }}   Çmimi: {{ cmimi_pajisje_internet }}
Pajisje TV: {{ pajisje_tv }}                Çmimi: {{ cmimi_pajisje_tv }}
Router/Wifi: {{ router_wifi }}              Çmimi: {{ cmimi_router_wifi }}

Totali: {{ total }}
```

### **Komente**

```
{{ comment }}
```

---

## 📋 Shembull Template (Pjesë)

```
┌─────────────────────────────────────────────────────────────┐
│                   FORMULARI I REGJISTRIMIT                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Data: {{ contract_date }}                                   │
│  Nr. Kontratës: {{ contract_number }}                        │
│  Afati/Pagesa: {{ afati_pagesa }}                           │
│                                                               │
│  Muaji Paguar:                                               │
│  {{ muaj_1 }} 1  {{ muaj_2 }} 2  {{ muaj_3 }} 3 ...        │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│  PAJTIMTAR - INDIVID                                         │
│                                                               │
│  Emri: {{ emri_individ }}                                    │
│  Adresa: {{ adresa_individ }}                                │
│  Mobile: {{ mobile_individ }}                                │
│  E-mail: {{ email_individ }}                                 │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│  SHËRBIMET                                                    │
│                                                               │
│  Shërbimi Internet: {{ sherbimi_internet }}                  │
│  Çmimi/Muaj: {{ cmimi_internet }}                           │
│                                                               │
│  Totali: {{ total }}                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Instalimi i Bibliotekës

Për të përdorur template DOCX, duhet të instaloni bibliotekën:

```bash
pip install docxtpl
```

Ose:

```bash
python -m pip install docxtpl
```

### Verifikimi

```bash
pip list | grep docxtpl
```

---

## 🚀 Përdorimi

1. **Krijoni template**: Ndiqni hapat më sipër
2. **Ruaje si**: `contract_template.docx` në këtë folder
3. **Restarto Odoo**: `sudo systemctl restart odoo` (ose restart manual)
4. **Testo**: Hap një kontratë dhe kliko "Download Contract"

---

## ⚠️ Nëse nuk ke template DOCX

Nëse file `contract_template.docx` nuk ekziston, sistemi do të përdorë automatikisht **PDF report-in aktual** që tashmë funksionon.

---

## 🔧 Fallback Mode

Sistemi ka **dy mënyra** gjenerimi:

1. **DOCX Template** (Preferuar)
   - ✅ Fleksibël - mund ta modifikosh template-in kur të duash
   - ✅ Dizajn profesional nga Word
   - ✅ Lehtë për të bërë ndryshime

2. **PDF Report** (Fallback)
   - ✅ Funksionon edhe pa bibliotekë shtesë
   - ✅ Përdor template-in aktual HTML/QWeb
   - ⚠️ Më vështirë për modifikime

---

## 📞 Probleme?

Nëse keni probleme:

1. **Kontrolloni që template është i ruajtur si**: `contract_template.docx`
2. **Sigurohuni që biblioteka është instaluar**: `pip install docxtpl`
3. **Restarto Odoo** pas çdo ndryshimi
4. **Shikoni logs**: `/var/log/odoo/odoo.log`

---

## 📚 Dokumentacion

- **python-docx-template**: https://docxtpl.readthedocs.io/
- **Jinja2 Syntax**: https://jinja.palletsprojects.com/

---

*Gjeneruar nga: radius_odoo_integration module*

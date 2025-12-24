# 🔧 Instalimi i Bibliotekës python-docx-template

## Për të përdorur template DOCX, duhet të instaloni bibliotekën `docxtpl`

---

## 📦 Metoda 1: Instalim me pip

### Windows:
```bash
python -m pip install docxtpl
```

### Linux/Mac:
```bash
pip3 install docxtpl
```

ose:

```bash
sudo pip3 install docxtpl
```

---

## 📦 Metoda 2: Nëse përdorni Virtual Environment

Nëse Odoo është në virtual environment:

```bash
# Aktivo virtual environment
source /path/to/odoo-venv/bin/activate

# Instalo bibliotekën
pip install docxtpl
```

---

## 📦 Metoda 3: Instalim Global për Odoo

Nëse Odoo është instaluar globalisht:

```bash
sudo su - odoo
pip3 install --user docxtpl
```

---

## ✅ Verifikimi

Pas instalimit, verifiko që biblioteka është instaluar:

```bash
pip list | grep docxtpl
```

Ose:

```bash
python -m pip show docxtpl
```

---

## 🔄 Restarto Odoo

Pas instalimit të bibliotekës, duhet të restartosh Odoo:

### Linux (systemd):
```bash
sudo systemctl restart odoo
```

### Manual:
```bash
# Ndalo Odoo
sudo killall python3

# Starto përsëri
/path/to/odoo-bin -c /path/to/odoo.conf
```

---

## 🧪 Testo

1. Hap Odoo në browser
2. Shko te **Contacts → [Zgjedh një kontratë]**
3. Kliko butonin **"Download Contract"**
4. Nëse funksionon, do të shkarkosh një dokument DOCX!

---

## ⚠️ Problemet e Mundshme

### Problemi 1: "ModuleNotFoundError: No module named 'docxtpl'"

**Zgjidhja:**
Sigurohu që ke instaluar në Python-in e duhur:

```bash
# Gje se cili Python përdor Odoo
ps aux | grep odoo

# Instalo në atë Python
/path/to/python -m pip install docxtpl
```

### Problemi 2: "Permission denied"

**Zgjidhja:**
Përdor `sudo` ose instalo për user:

```bash
pip3 install --user docxtpl
```

### Problemi 3: Template nuk gjendet

**Zgjidhja:**
Sigurohu që file `contract_template.docx` ekziston në:
```
radius_odoo_integration/templates/contracts/contract_template.docx
```

---

## 📚 Dokumentacion Shtesë

- **docxtpl**: https://docxtpl.readthedocs.io/
- **python-docx**: https://python-docx.readthedocs.io/

---

## 🆘 Nëse Nuk Funksionon

Nëse biblioteka nuk instalohet dot, **mos u shqetëso!**

Sistemi do të përdorë automatikisht PDF report-in ekzistues që tashmë funksionon.

Thjesht kliko "Download Contract" dhe do të merrësh një PDF.

---

*Gjeneruar nga: radius_odoo_integration module*

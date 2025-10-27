# Dokumentacion për Modulin "Radius Manager"

## Funksionalitetet Kryesore:
Ky modul ofron mundësinë për të menaxhuar planet e shërbimit, përdoruesit dhe pajisjet që përdorin **FreeRADIUS** për autentifikim dhe autorizim. Përdoruesit mund të kenë shpejtësi të kufizuara, mund të lidhen me grupet përkatëse dhe mund të përdorin **pools IP** për ndarjen dhe menaxhimin e rrjetit.

---

## **Menaxhimi i Pajisjeve (NAS - Network Access Server)**

Pajisjet (NAS) janë **rrjetet e pajisura për autentifikim dhe autorizim të përdoruesve** nëpërmjet RADIUS. Për shembull, një router MikroTik ose Cisco mund të jetë një NAS. Ky është një element kyç që mundëson lidhjen e përdoruesve në rrjet. Në sistemin tonë, mund të krijoni dhe menaxhoni pajisje për të **ndërlidhur përdoruesit me RADIUS**.

### **Për të shtuar një Pajisje (NAS):**
1. Shkoni te **Devices (NAS)** dhe klikoni **New**.
2. Plotësoni fushat e mëposhtme:
   - **Emri i Pajisjes**: P.sh. `ASR1`
   - **IP Address**: P.sh. `192.168.1.1` (IP e pajisjes që përdor RADIUS).
   - **Shared Secret**: Ky është një kod i përdorur për autentifikim midis RADIUS dhe pajisjes. Është i njëjtë në të dyja anët (RADIUS dhe pajisje).
   - **Lloji i Pajisjes**: Zgjidhni nga llojet si MikroTik, Cisco, ose të tjera.
   - **Ports**: Nëse pajisja përdor disa porte RADIUS (p.sh., 1700), mund të shtoni ato këtu.
   
3. **Sync me RADIUS:**
   - Pas krijimit të pajisjes, mund të përdorni butonin **"Sync to RADIUS"** për të sinkronizuar të dhënat me **FreeRADIUS**.

---

## **Menaxhimi i Paketave të Shërbimit (Subscriptions)**

Paketat e shërbimit në sistemin tonë mund të lidhen me përdoruesit dhe pajisjet për të ofruar shërbime të ndryshme. Çdo paketë ka **limit të shpejtësisë**, **politika specifike për Cisco/MikroTik**, dhe mund të lidhet me **pools IP** për përdoruesit.

### **Për të krijuar një Paketë të Re (Subscription Plan):**
1. Shkoni te **Subscriptions** në panelin e administratës.
2. Klikoni **New** për të shtuar një plan të ri.
3. Plotësoni fushat si më poshtë:
   - **Emri i Paketës**: P.sh. `Paketa 300M/30M`.
   - **Kodi i Paketës**: Ky është një kod unik që përdoret për identifikimin e planit në FreeRADIUS. Mund ta vendosni manualisht ose të mbushët automatikisht nga emri i paketës.
   - **Rate Limit**: Ky është kufizimi që vendosni për ngarkesën dhe shkarkesën e të dhënave për përdoruesit. P.sh., `300M/30M` për ngarkesën 300MB dhe shkarkesën 30MB.
   - **IP Pool Aktiv**: P.sh. `PPP-POOL`, dhe IP Pool për përdorues të skaduar: P.sh. `POOL_EXPIRED`.
   - **Çmimi**: Çmimi për këtë plan shërbimi për qëllime faturimi.
   - **Produkti**: Ky është produkti në Odoo që lidhet me këtë plan për qëllime faturimi.

4. **Kjo pakete ruhet ne Radius ne kete format limiti CISCO:**
```
   Cisco-AVPair := ip:interface-config=service-policy output 300M
   Cisco-AVPair := ip:interface-config=service-policy output 30M
```
   
5. **Kliko Save** për të ruajtur paketën dhe më pas **Sync to RADIUS** për të dërguar të dhënat në **FreeRADIUS**.

### **Opsionet Cisco dhe MikroTik në Paketë**:
- **Cisco**: Përdor politikat për shpejtësinë dhe mund të caktoni **pool-et për përdoruesit Cisco**.
- **MikroTik**: Kur **Emit MikroTik** është aktiv, do të dërgohen **Mikrotik-Rate-Limit** dhe **Framed-Pool**.

---

## **Menaxhimi i Përdoruesve (Users)**

Përdoruesit janë individët që përdorin shërbimet që lidhen me **pajisjet (NAS)** dhe **planët e shërbimit**.

### **Për të shtuar një Përdorues të Ri**:
1. Shkoni te **New** dhe klikoni **Create**.
2. Plotësoni informacionin e përdoruesit:
   - **Username**: Emri unik i përdoruesit (p.sh., `john_doe`).
   - **RADIUS Password**: Fjalëkalimi i përdoruesit për autentifikimin në RADIUS (p.sh., `pass123`).
   - **Subscription**: Zgjidhni planin e shërbimit që ky përdorues do të përdorë.
3. **Klikoni Save** dhe më pas **Sync to RADIUS** për të dërguar të dhënat e përdoruesit në **FreeRADIUS**.

---

## **Monitorimi**

### **Sessions** (RADIUS > Sessions)
Lista e sesioneve nga tabela `radacct`:
- Username, Session ID, Start/Stop Time, Duration
- Input/Output Octets (shkarkime/ngarkime)
- NAS IP, Framed IP, Called/Calling Station

### **PPPoE Status** (RADIUS > PPPoE Status)
View agreguar i statusit live:
- Status: ONLINE (nëse `acctstoptime IS NULL` dhe update < 15 min) ose OFFLINE
- Kolonat: Username, Status, Login Time, NAS IP, IP, Plans, Port, Circuit ID/MAC

### **Sinkronizimi**

- **Statusi i Sync-it** tregon nëse një përdorues ose një plan është **sinkronizuar me FreeRADIUS**. 
  - **Synced**: Kur të dhënat janë të sinkronizuara dhe të gjitha atributet janë dërguar në FreeRADIUS.
  - **Not Synced**: Kur përdoruesi ose plani ende nuk është sinkronizuar.
  - **Gabime në Sync**: Kur ndodhin gabime gjatë procesit të sinkronizimit, ato mund të shfaqen në statusin e gabimit dhe mund të rregullohen nëpërmjet opsionit **Sync to RADIUS**.

---

## **Moduli CRM (Abissnet CRM)**

Moduli **Abissnet CRM** zgjeron funksionalitetet e menaxhimit të përdoruesve RADIUS me shtimin e të dhënave të klientëve dhe infrastrukturës së rrjetit. Ky modul mundëson menaxhimin e plotë të marrëdhënieve me klientët (CRM) dhe lidhjen e tyre me infrastrukturën fizike të rrjetit.

---
## **Menaxhimi i Klientëve (Customers)**

Moduli CRM zgjeron rekordin e përdoruesit RADIUS me të dhëna të plota të klientit.

### **Për të shtuar një Klient të Ri:**
1. Shkoni te **Abissnet CRM > Customers**
2. Klikoni **New** dhe plotësoni:

**Customer Info:**
- **Name**: Emri i klientit (opsionale)
- **Username**: Username unik për RADIUS
- **RADIUS Password**: Fjalëkalimi për autentifikim
- **SLA Level**: 
  - **SLA 1 - Individual**: Klient rezidencial
  - **SLA 2 - Small Business**: Biznes i vogël
  - **SLA 3 - Enterprise**: Kompani e madhe

**Contact Information:**
- **Phone Number**: Numri kryesor i telefonit
- **Secondary Phone**: Telefon alternativ
- **Email**: Email adresa

**Business Information** (për SLA 2 dhe 3):
- **Company Name**: Emri i kompanisë (i detyrueshëm)
- **NIPT/VAT**: Numri tatimor (i detyrueshëm për biznese)

**Installation Address:**
- **Street**: Rruga
- **Street 2**: Apartament, njësi, etj.
- **City**: Qyteti
- **ZIP**: Kodi postar
- **Country**: Shteti

**Geolocation:**
- **Latitude**: Gjerësia gjeografike
- **Longitude**: Gjatësia gjeografike
- Buton **View on Map**: Hap vendndodhjen e klientit në Google Maps

**Plan & Device:**
- **Subscription**: Zgjidhni planin e shërbimit
- **Company**: Kompania (për multi-company)

3. **Infrastructure Tab:**
   - **Access Device**: Zgjidhni pajisjen fizike ku është i lidhur klienti
   - **POP**: Shfaqet automatikisht nga pajisja
   - **City**: Shfaqet automatikisht nga POP-i
   - Informacioni i kapacitetit të pajisjes

4. **Contract & Billing Tab:**
   - **Contract Start Date**: Data e fillimit të kontratës
   - **Contract End Date**: Data e mbarimit
   - **Installation Date**: Data e instalimit
   - **Installed By**: Tekniku që ka bërë instalimin
   - **Billing Day of Month**: Dita e muajit për gjenerimin e faturës (1-28)

5. **Notes Tab:**
   - **Internal Notes**: Shënime të brendshme (jo të dukshme për klientin)
   - **Customer Notes**: Shënime të dukshme për klientin (në portal)

6. **Smart Buttons** në krye të formës:
   - **Active**: Sesionet aktive RADIUS
   - **Sessions**: Historia e të gjitha sesioneve
   - **Last Login**: Koha e login-it të fundit
   - **PPPoE Status**: Statusi live i PPPoE
   - **View on Map**: Hap vendndodhjen në hartë

---

## **Menaxhimi i Infrastrukturës së Rrjetit**

### **Qytetet (Cities)**
Qytetet janë niveli më i lartë i hierarkisë së infrastrukturës. Çdo qytet mund të ketë disa **POP (Point of Presence)**.

**Për të shtuar një Qytet:**
1. Shkoni te **Abissnet CRM > Management > Cities**
2. Klikoni **New** dhe plotësoni:
   - **City Name**: Emri i qytetit (p.sh., `Tiranë`, `Durrës`)
   - **City Code**: Kodi i shkurtër (p.sh., `TIR`, `DUR`)
   - **Latitude/Longitude**: Koordinatat gjeografike për hartë
   - **Notes**: Shënime shtesë

3. Nga forma e qytetit mund të shikoni:
   - Numrin e POP-eve
   - Numrin e pajisjeve
   - Numrin e klientëve
   - Buton **View on Map** për të hapur vendndodhjen në Google Maps

---

### **POP (Point of Presence)**
POP-et janë vendndodhje fizike brenda qyteteve ku instalohet pajisja e rrjetit për të shërbyer klientët.

**Për të shtuar një POP:**
1. Shkoni te **Abissnet CRM > Management > POPs**
2. Klikoni **New** dhe plotësoni:
   - **POP Name**: Emri i POP-it (p.sh., `Tirana Center POP`)
   - **POP Code**: Kodi i shkurtër (p.sh., `TIR-01`)
   - **City**: Zgjidhni qytetin përkatës
   - **Type**: Fiber POP, Wireless POP, ose Hybrid
   - **Physical Address**: Adresa fizike e POP-it
   - **Latitude/Longitude**: Koordinatat gjeografike
   - **Max Customers**: Kapaciteti maksimal i klientëve
   - **Operational Status**: Planned, Under Construction, Active, Maintenance, Inactive

3. Në notebook-un e POP-it mund të shihni:
   - **Access Devices**: Lista e pajisjeve të lidhura
   - **Notes**: Shënime teknike

---

### **Pajisjet e Aksesit (Access Devices)**
Pajisjet e aksesit (OLT, DSLAM, Switch, etj.) janë pajisjet fizike që lidhin klientët me rrjetin në çdo POP.

**Për të shtuar një Pajisje Aksesi:**
1. Shkoni te **Abissnet CRM > Management > Access Devices**
2. Klikoni **New** dhe plotësoni:
   - **Device Name**: Emri i pajisjes (p.sh., `OLT-TIR-01`)
   - **Serial/Code**: Numri serial i pajisjes
   - **POP**: Zgjidhni POP-in ku ndodhet pajisja
   - **Device Type**: OLT, DSLAM, Ethernet Switch, Router, Wireless AP, Other
   - **Manufacturer**: Prodhuesi (p.sh., Huawei, ZTE, Cisco)
   - **Model**: Modeli i pajisjes
   - **Management IP**: IP për menaxhim
   - **MAC Address**: Adresa MAC
   - **Total Ports**: Numri total i porteve
   - **Operational Status**: Online, Offline, Maintenance, Faulty
   - **RADIUS NAS Device**: Lidhje me konfigurimin teknik RADIUS (opsionale)

3. Informacione automatike:
   - **Ports Used**: Numri i porteve në përdorim (llogaritet automatikisht)
   - **Ports Available**: Portet e lira
   - **Capacity %**: Përqindja e kapacitetit të përdorur
   - **Customers**: Numri i klientëve të lidhur

4. Sistemet paralajmëron nëse:
   - Kapaciteti tejkalohet (më shumë klientë se portet)
   - Pajisja është offline por ka klientë aktiv

---


## **Filtrime dhe Kërkime të Avancuara**

### **Filtra për Klientët:**
- **Individual (SLA 1)**: Vetëm klientë rezidencial
- **Small Business (SLA 2)**: Biznese të vogla
- **Enterprise (SLA 3)**: Kompani të mëdha
- **Business Customers**: Të gjithë bizneset (SLA 2 + 3)
- **Has Geolocation**: Klientë me koordinata gjeografike
- **Has Access Device**: Klientë të lidhur me pajisje

### **Grupime (Group By):**
- SLA Level
- City (nga adresa)
- City (nga infrastruktura)
- POP
- Access Device
- Installation Month

### **Filtrime për Infrastrukturë:**

**Cities:**
- Active/Archived
- Has POPs

**POPs:**
- Active/Archived
- Operational/Planned/Maintenance
- Fiber/Wireless

**Access Devices:**
- Active/Archived
- Online/Offline/Faulty
- By Device Type (OLT/DSLAM/Switch)
- By Manufacturer

---

## **Dekorimi Vizual**

Sistemet përdor ngjyra për të treguar statusin:

**Klientë:**
- **Gri**: SLA 1 (Individual)
- **Portokalli**: SLA 2 (Small Business)
- **Jeshil**: SLA 3 (Enterprise)

**Pajisje:**
- **Jeshil**: Online/Operational
- **Kuq**: Offline/Faulty
- **Portokalli**: Maintenance

**Ribbon Tags:**
- **ENTERPRISE**: Për klientë SLA 3
- **Not Synced**: Kur të dhënat nuk janë sinkronizuar me RADIUS
- **Synced**: Kur sinkronizimi është i suksesshëm
- **Suspended**: Për përdorues të pezulluar

---

## **Rregullat e Validimit**

1. **NIPT i detyrueshëm**: Për SLA 2 dhe 3, fusha NIPT është e detyrueshme
2. **Billing Day**: Duhet të jetë midis 1-28 (për të shmangur probleme me shkurtin)
3. **Port Capacity**: Sistemet paralajmëron nëse një pajisje ka më shumë klientë se portet e disponueshme
4. **Unique Constraints**:
   - City name unik për kompani
   - POP name unik brenda qytetit
   - Username unik për kompani

---

## **Integrimi RADIUS ↔ CRM**

Të dhënat teknike RADIUS dhe të dhënat CRM janë plotësisht të integruara:

1. **Krijimi i klientit**:
   - Plotësoni të dhënat e CRM (kontakt, adresë, SLA)
   - Zgjidhni pajisjen e aksesit (lidhet automatikisht me POP dhe City)
   - Zgjidhni planin e shërbimit
   - Kliko **Sync to RADIUS** për të krijuar përdoruesin në FreeRADIUS

2. **Monitorimi**:
   - **Sessions**: Shihni të gjitha sesionet RADIUS
   - **PPPoE Status**: Kontrolloni statusin live (ONLINE/OFFLINE)
   - **Access Device Stats**: Shikoni sa klientë janë të lidhur në çdo pajisje

---

Ky është dokumentacioni i plotë për sistemin e integruar **RADIUS Manager + CRM**, që mundëson menaxhimin e plotë të infrastrukturës së rrjetit, planeve të shërbimit, klientëve dhe monitorimin live të sesioneve.

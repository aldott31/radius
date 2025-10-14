# Dokumentacion për Modulin “Radius Manager”

## Funksionalitetet Kryesore:
Ky modul ofron mundësinë për të menaxhuar planet e shërbimit, përdoruesit dhe pajisjet që përdorin **FreeRADIUS** për autentifikim dhe autorizim. Përdoruesit mund të kenë shpejtësi të kufizuara, mund të lidhen me grupet përkatëse dhe mund të përdorin **pools IP** për ndarjen dhe menaxhimin e rrjetit.

---

## **Menaxhimi i Pajisjeve (NAS - Network Access Server)**

Pajisjet (NAS) janë **rrjetet e pajisura për autentifikim dhe autorizim të përdoruesve** nëpërmjet RADIUS. Për shembull, një router MikroTik ose Cisco mund të jetë një NAS. Ky është një element kyç që mundëson lidhjen e përdoruesve në rrjet. Në sistemin tonë, mund të krijoni dhe menaxhoni pajisje për të **ndërlidhur përdoruesit me RADIUS**.

### **Për të shtuar një Pajisje (NAS):**
1. Shkoni te **Devices (NAS)** dhe klikoni **Create**.
2. Plotësoni fushat e mëposhtme:
   - **Emri i Pajisjes**: P.sh. `MikroTik Router`
   - **IP Address**: P.sh. `192.168.1.1` (IP e pajisjes që përdor RADIUS).
   - **Shared Secret**: Ky është një kod i përdorur për autentifikim midis RADIUS dhe pajisjes. Është i njëjtë në të dyja anët (RADIUS dhe pajisje).
   - **Lloji i Pajisjes**: Zgjidhni nga llojet si MikroTik, Cisco, ose të tjera.
   - **Ports**: Nëse pajisja përdor disa porte RADIUS (p.sh., 1812, 1813), mund të shtoni ato këtu.
   
3. **Sync me RADIUS:**
   - Pas krijimit të pajisjes, mund të përdorni butonin **"Sync to RADIUS"** për të sinkronizuar të dhënat me **FreeRADIUS**.

---

## **Menaxhimi i Paketave të Shërbimit (Subscriptions)**

Paketat e shërbimit në sistemin tonë mund të lidhen me përdoruesit dhe pajisjet për të ofruar shërbime të ndryshme. Çdo paketë ka **limit të shpejtësisë**, **politika specifike për Cisco/MikroTik**, dhe mund të lidhet me **pools IP** për përdoruesit.

### **Për të krijuar një Paketë të Re (Subscription Plan):**
1. Shkoni te **Subscriptions** në panelin e administratës.
2. Klikoni **Create** për të shtuar një plan të ri.
3. Plotësoni fushat si më poshtë:
   - **Emri i Paketës**: P.sh. `Paketa 300M/30M`.
   - **Kodi i Paketës**: Ky është një kod unik që përdoret për identifikimin e planit në FreeRADIUS. Mund ta vendosni manualisht ose të mbushët automatikisht nga emri i paketës.
   - **Rate Limit**: Ky është kufizimi që vendosni për ngarkesën dhe shkarkesën e të dhënave për përdoruesit. P.sh., `300M/30M` për ngarkesën 300MB dhe shkarkesën 30MB.
   - **Timeout i Sesionit**: Ky është koha që përdoruesit mund të qëndrojnë të lidhur në rrjet pa ndërprerje. P.sh., mund të vendosni 3600 sekonda (1 orë).
   - **Çmimi**: Çmimi për këtë plan shërbimi për qëllime faturimi.
   - **Produkti**: Ky është produkti në Odoo që lidhet me këtë plan për qëllime faturimi.

4. **Për Cisco dhe MikroTik:**
   - **Cisco Policy In/Out**: Politikat e shpejtësisë për ngarkesën dhe shkarkesën (p.sh., `POLICY_UL_30` dhe `POLICY_DL_300`).
   - **IP Pool Aktiv**: P.sh. `POOL_ACTIVE`, dhe IP Pool për përdorues të skaduar: P.sh. `POOL_EXPIRED`.
   
5. **Kliko Save** për të ruajtur paketën dhe më pas **Sync to RADIUS** për të dërguar të dhënat në **FreeRADIUS**.

### **Opsionet Cisco dhe MikroTik në Paketë**:
- **Cisco**: Përdor politikat për shpejtësinë dhe mund të caktoni **pool-et për përdoruesit Cisco**.
- **MikroTik**: Kur **Emit MikroTik** është aktiv, do të dërgohen **Mikrotik-Rate-Limit** dhe **Framed-Pool**.

---

## **Menaxhimi i Përdoruesve (Users)**

Përdoruesit janë individët që përdorin shërbimet që lidhen me **pajisjet (NAS)** dhe **planët e shërbimit**.

### **Për të shtuar një Përdorues të Ri**:
1. Shkoni te **Users** dhe klikoni **Create**.
2. Plotësoni informacionin e përdoruesit:
   - **Username**: Emri unik i përdoruesit (p.sh., `john_doe`).
   - **RADIUS Password**: Fjalëkalimi i përdoruesit për autentifikimin në RADIUS (p.sh., `pass123`).
   - **Subscription**: Zgjidhni planin e shërbimit që ky përdorues do të përdorë.
   - **Device(Opsionale)**: Zgjidhni pajisjen (p.sh., MikroTik) për përdoruesin.
   - **Framed IP (Opsionale)**: Mund të caktoni një **IP statike** për përdoruesin nëse është e nevojshme.
   - **Override Pool (Opsionale)**: Mund të caktoni një **pool të veçantë** për përdoruesin.
3. **Klikoni Save** dhe më pas **Sync to RADIUS** për të dërguar të dhënat e përdoruesit në **FreeRADIUS**.

### **Opsionet e Përdoruesve**:
- **Suspendimi dhe Aktivizimi**:
   - **Suspendimi i përdoruesit** do ta kalojë atë në grupin `SUSPENDED`, duke ndaluar qasjen e tij në rrjet.
   - **Aktivizimi** do ta rikthejë përdoruesin në gjendjen aktive.
   
- **Heqja nga RADIUS**:
   - Mund të **fshini përdoruesin** nga FreeRADIUS, duke hequr të gjitha lidhjet dhe atribute që lidhen me të (p.sh., `radusergroup`, `radcheck`, `radreply`).

---

### **Statusi dhe Sinkronizimi**

- **Statusi i Sync-it** tregon nëse një përdorues ose një plan është **sinkronizuar me FreeRADIUS**. 
  - **Synced**: Kur të dhënat janë të sinkronizuara dhe të gjitha atributet janë dërguar në FreeRADIUS.
  - **Not Synced**: Kur përdoruesi ose plani ende nuk është sinkronizuar.
  - **Gabime në Sync**: Kur ndodhin gabime gjatë procesit të sinkronizimit, ato mund të shfaqen në statusin e gabimit dhe mund të rregullohen nëpërmjet opsionit **Sync to RADIUS**.

---

### **Shembuj Përdorimi të Sistemit:**

1. **Krijimi i një Plan Shërbimi të Ri:**
   - P.sh. krijoni një plan të quajtur `Paketa 300/30` me një kufizim shpejtësie `300M/30M` dhe një **IP Pool Aktiv** (p.sh. `POOL_ACTIVE`).
   - Aktivizoni **Emit Cisco** për të dërguar politikat për ngarkesën dhe shkarkesën e të dhënave.
   - Pasi ta krijoni, klikoni **Sync to RADIUS** për të dërguar të dhënat në **FreeRADIUS**.

2. **Krijimi dhe Sync i Përdoruesit:**
   - Krijoni një përdorues me emrin `john_doe`, caktoni planin `Paketa 300M/30M` dhe pajisjen `MikroTik`.
   - Pasi të krijohet përdoruesi, mund ta **sinkronizoni atë me FreeRADIUS** duke përdorur butonin **Sync to RADIUS**.

3. **Suspendimi dhe Aktivizimi i Përdoruesve**:
   - Përdoruesi mund të **suspendohen** përkohësisht (duke kaluar në grupin `SUSPENDED`) dhe të **rikthehen** në gjendjen aktive për t'u lejuar të vazhdojnë shërbimin.

---

Ky është një përmbledhje e plotë për **përdorimin e sistemit të menaxhimit të RADIUS**, përfshirë krijimin e planeve, menaxhimin e përdoruesve dhe pajisjeve (NAS), dhe mundësitë për sinkronizimin dhe menaxhimin e shpejtësisë, politikave dhe pools IP.

# Dokumentacion për Modulin “Radius Manager”

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
       -Cisco-AVPair := ip:interface-config=service-policy output 300M ,
       -Cisco-AVPair := ip:interface-config=service-policy output 30M .
   
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

Ky është një përmbledhje e plotë për **përdorimin e sistemit të menaxhimit të RADIUS**, përfshirë krijimin e planeve, menaxhimin e përdoruesve dhe pajisjeve (NAS), dhe mundësitë për sinkronizimin dhe menaxhimin e shpejtësisë, politikave dhe pools IP.

# Train Live — analiza cerinței și arhitectura

Data: 20.10.2026. Autor: Claude (proiectul „Aplicatii .apk”), pentru Bogdan.

## 1. Ce s-a cerut (rezumat)

O aplicație Android matură de monitorizare a antrenamentelor, construită pe ce au dovedit cele două
aplicații de test (Pulse Live = puls de la Garmin Venu X1, Spin Live = date FTMS de la YESOUL S3):

| # | Cerință | Cum o rezolvăm |
|---|---------|----------------|
| 1 | Design ca în poza 1, fără nutriție | Ecran „Today”: salut, planul curent, data, bandă calendar (zile cu buline colorate pe tip de sesiune), card „Progress” către 10 km, „Numbers”, apoi o coloană lungă de grafice derulabile. Temă întunecată/luminoasă după sistem. |
| 2 | Calendar + progres către 10 km | Calendarul vine din `planuri/index.json` + sesiunile făcute; progresul din `widget/progres.json` (procent_headline, jaloane L1–L4). |
| 3 | Cât mai multe grafice | Cel mai lung bloc continuu, distanță/sesiune, puls mediu și maxim, ritm, efort, volum săptămânal, zone de puls, pauze între alergări, plus pentru spinning: putere medie, cadență, rezistență, kcal. |
| 4 | Bară plutitoare jos → intru într-o activitate | Bara: Today · ▶ Workout · History · Settings. „Workout” → Alergare sau Spinning. |
| 5 | Alergare = doar ceas; spinning = ceas + bicicletă | Ecran de pregătire cu starea fiecărui dispozitiv (ceas, bicicletă, GPS) și Start; ceasul e opțional (se poate porni și fără), bicicleta e obligatorie la spinning. |
| 6 | Ecran activitate împărțit ca în poza 2 | Sus: bara media (YouTube Music sau orice player). Mijloc: puls, distanță, viteză/ritm, rezistență etc. + grafice „fereastră” (poza 3). Jos: instrucțiunile din JSON exact ca în aplicația HTML (etichetă colorată ALEARGĂ/MERGI…, cronometru mare, pasul următor, total, butoane). |
| 7 | Alergare: toate datele de la telefon, GPS cu acuratețe maximă | GNSS brut (`GPS_PROVIDER`, 1 Hz, dublă frecvență pe S25 Ultra) + filtru de precizie + netezire; cadență din senzorul de pași al telefonului; altitudine GPS + barometru. |
| 8 | Spinning: date de la YESOUL, obligatoriu rezistența | FTMS 0x1826/0x2AD2 (distanță, kcal, cadență, rezistență, putere, viteză), calcul identic cu Spin Live. |
| 9 | Valori care trebuie ținute într-o plajă → grafic ca în poza 3 | Componenta „Range gauge”: bara lungă min…max a scării, „fereastra” verde a țintei din plan, cursorul valorii actuale; în afara ferestrei devine roșie/portocalie + vibrație. Câte una pentru puls, ritm, cadență, rezistență, putere — doar cele pe care pasul curent le cere. |
| 10 | Rezultatul sesiunii trimis automat către proiectul Sport și analizat automat | La final aplicația scrie un JSON foarte detaliat (eșantion la fiecare secundă) pe ramura `rezulate` din `serbanbogdan/sport`; analiza o face Claude automat (vezi §4). |
| 11 | Aplicația cere de la Claude un plan nou, pus pe GitHub, importabil | Butonul „Ask Claude for a plan” scrie o cerere în `planuri/cereri/`; Claude o procesează automat; planul apare în aplicație ca „New plan available → Import”. Opțional, cu cheie API Anthropic în setări, planul se generează imediat din aplicație. |
| 12 | Verifică JSON-urile (plan alergare/spinning și widget) | Plan v2 și widget v2 — §3. Compatibile înapoi: aplicația HTML și widgetul actual continuă să meargă. |
| 13 | Widgetul din Widget Studio își ia datele din `widget` | `progres.json` pe ramura `widget` (repo public → fără token). Widget Studio 1.0.56 îl folosește implicit. |
| 14 | Buton de actualizare cu GitHub | Butonul de sincronizare din antetul ecranului Today (în locul iconiței cu puls din poză). |

## 2. Ce am învățat din Pulse Live și Spin Live (și ce schimbăm)

- Ceasul expune Heart Rate standard (0x180D/0x2A37, cu RR) doar când e pornit „Broadcast Heart Rate”.
- Bicicleta: FTMS fără Control Point util (nu se poate seta rezistența), datele vin împărțite pe mai multe pachete; rezistența brută 0–100.
- Caloriile ca în aplicația YESOUL = lucru mecanic / 4184.
- **Limita alfa:** conexiunile trăiau doar cât aplicația era pe ecran. În Train Live totul rulează într-un **serviciu foreground** (`location` + `connectedDevice`): ecranul se poate stinge, poți schimba muzica, sesiunea continuă și se înregistrează.

## 3. JSON-uri: ce lipsea și ce se adaugă

### Plan (v1 → v2)
v1 (folosit de aplicația HTML) avea doar `tip/nume/durata/nota` și `repeta`. Țintele erau text („7:30-8:00/km” în `nume`), deci o aplicație nu le putea verifica.

v2 adaugă (toate opționale, v1 rămâne valid):
- `schema_version: 2`, `id`, `activitate` (`alergare` | `spinning`), `obiectiv`, `praguri` (alertă 155, reluare sub 130, zona de lucru).
- per pas `tinte` numerice: `puls`, `ritm_min_km`, `cadenta_spm`, `cadenta_rpm`, `rezistenta`, `putere_w`, `viteza_kmh` — fiecare `[min, max]`.
- per pas `pana_la_puls_sub` + `max_prelungire_s`: pasul de mers nu se termină până pulsul nu coboară sub prag (regula „nu reiei alergarea peste 130”), aplicată automat.
- `criterii_reusita`: lista de verificări pe care analiza le bifează.
- `planuri/index.json` = calendarul (toate sesiunile planificate, alergare + spinning, cu status).

### Widget (`progres.json` v1 → v2)
v1 era generat doar din Strava, în repo-ul privat `widget-studio` (cerea token pe telefon), fără spinning, iar `zile_de_la_ultima_alergare` îmbătrânea între alergări.
v2 păstrează **toate** câmpurile v1 (widgetul actual merge neschimbat) și adaugă: `schema_version: 2`, `generat_de`, blocul `spinning` (totaluri, ultima sesiune, tendințe putere/cadență/rezistență/kcal), `urmatoarea_sesiune_spinning`, `sesiuni_aplicatie`. Locul: ramura `widget`, repo public.

### Rezultat (nou)
`rezulate/sesiuni/AAAA/LL/<id>.json` — nimic omis: planul complet, dispozitivele, vremea, rezumatul, fiecare pas (planificat vs. realizat, prelungiri, % timp în țintă), split-uri pe km, evenimente (pauze, alerte, deconectări), RR, și toate eșantioanele la 1 s (puls, distanță, viteză, GPS lat/lon/alt/precizie, cadență, putere, rezistență, kcal, pasul planului). Schema completă: `docs/SCHEME.md`.

## 4. Automatizarea (fără pași manuali)

```
telefon (Train Live)
  ├─ PUT rezulate/sesiuni/…/<id>.json      ──┐
  ├─ POST repository_dispatch "sesiune_noua"  │
  └─ PUT planuri/cereri/<id>.json (cerere)    │
                                              ▼
GitHub Actions (repo sport, main)  scripts/proceseaza.py — determinist, imediat:
  • rezulate/index.json, planuri/index.json (status realizat)
  • widget/progres.json: totaluri, tendințe, bloc continuu, spinning
  • dacă există secretul ANTHROPIC_API_KEY → analiză + plan prin API, imediat
                                              ▼
Claude — task programat (din oră în oră, 06–23)  docs/INSTRUCTIUNI_CLAUDE.md:
  • pentru fiecare rezultat fără analiză: protocolul Sport (praguri 155/130, cadență,
    Z1+Z2 ≥ 85 %, tendințe în sesiune, comparație cu istoricul, Strava dacă există)
  • scrie rezulate/analize/<id>.md + .json, completează widget/progres.json
  • decide sesiunea următoare → planuri/sesiuni/<id>.json + index
  • procesează cererile din planuri/cereri/
                                              ▼
telefon: butonul ⟳ (sau automat la deschidere) → analiză, plan nou, progres
```

De ce două căi: GitHub Actions nu poate rula Claude fără cheie API (cost separat); task-ul programat folosește abonamentul Claude existent, fără cheie. Cu cheie, totul e instant; fără, cel mult o oră.

Proiectul Sport (Claude) rămâne compatibil: instrucțiunile lui sunt în `docs/INSTRUCTIUNI_CLAUDE.md` — trebuie doar să scrie planurile în `planuri` și progresul în `widget` în loc de Drive / `widget-studio/data`.

## 5. Arhitectura aplicației

Modul `train` în `widget-studio`, pachet `ro.serban.trainlive`, Kotlin + Jetpack Compose (Material 3), minSdk 33, target 36, optimizat pentru S25 Ultra (One UI 9).

| Strat | Conținut |
|---|---|
| `core` | modele plan/rezultat/stare live, parser plan v1+v2, stocare locală, setări |
| `ble` | scanare, legături GATT cu reconectare (ceas HR + RR, bicicletă FTMS) |
| `sensors` | GPS (GNSS 1 Hz, filtrare, distanță), pași/cadență, barometru |
| `session` | serviciul foreground, motorul planului (pași, prelungiri, ținte), înregistrare 1 Hz, semnale (notificare care ajunge pe ceas, vibrație, bip, voce TTS) |
| `media` | bara media: comenzi prin `dispatchMediaKeyEvent` (merg mereu), titlu/copertă prin acces la notificări |
| `sync` | client GitHub (Contents API), coadă de încărcare cu reîncercare, cereri de plan, import planuri, cache progres, Claude API opțional |
| `ui` | Today, calendar, grafice, Workout (pregătire + ecran live + rezumat), History, Settings |

Riscuri / limite cunoscute:
- Garmin trimite doar puls (+RR) prin broadcast; cadența de alergare vine de la telefon (trebuie ținut pe corp — buzunar/banderolă).
- Rezistența YESOUL nu poate fi comandată (bicicleta nu expune Target Setting) — doar afișată și verificată față de țintă.
- Tokenul GitHub (fine-grained, *Contents: Read and write* doar pe `sport`) se introduce pe telefon, nu stă în cod.
- Totul e compilat doar în CI; verificarea reală e pe telefon.

## 6. Echipa

| Rol | Responsabilitate |
|---|---|
| Arhitect / integrator (Claude principal) | analiză, contracte între module, scheletul, integrare, build CI |
| Inginer senzori și sesiune | BLE, GPS, pași, serviciu foreground, motorul planului, înregistrare, semnale |
| Designer + dezvoltator UI | Today, calendar, grafice, History, Settings |
| Dezvoltator ecran activitate | ecranul live, range gauge, bara media, rezumat de final |
| Inginer date și automatizare | sync GitHub în aplicație, scheme, scripturi și workflow în `sport`, instrucțiuni Claude |
| Recenzent independent | citește codul la final fără să-l fi scris: compilare, permisiuni, bug-uri |

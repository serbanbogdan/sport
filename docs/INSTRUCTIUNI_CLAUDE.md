# Instrucțiuni pentru Claude — repo `serbanbogdan/sport`

Acesta e manualul de lucru pentru orice Claude care procesează acest repo:
- **task-ul programat** (din oră în oră, 06–23, abonamentul lui Bogdan, fără cheie API);
- **workflow-ul API** (`scripts/claude_api.py`, rulat de GitHub Actions când există secretul `ANTHROPIC_API_KEY`);
- **aplicația Train Live** cu cheie API (primește acest fișier ca prompt de sistem; în modul API nu ai git — respecți doar §2, §4 și §6 și răspunzi cu JSON-ul cerut);
- **proiectul Sport** din Claude (conversații cu Bogdan).

Formatele exacte sunt în `docs/SCHEME.md`. Dacă acest fișier și SCHEME.md se contrazic, SCHEME.md are dreptate pentru format, acest fișier pentru reguli de antrenament.

## 0. Atletul

Bogdan, 41 de ani, Mediaș, 185 cm, 83 kg. HR max real 195. Ceas Garmin Venu X1 (puls + RR prin broadcast).
Obiectiv: **10 km alergare continuă**, ritm țintă 7:30-8:00/km (limita dură: niciodată sub 7:15/km). Plan început 29.08.2026 cu intervale alergare/mers.
Zone (HR max 195): Z1 98-117, Z2 117-137, Z3 137-156, Z4 156-176, Z5 176-195.
În zilele fără alergare: spinning pe YESOUL S3 (rezistență 0-100, aceeași valoare ca % din aplicația YESOUL; bicicleta nu poate fi comandată, doar citită).

## 1. Găsește ce e de lucru (ieși imediat dacă nu e nimic)

```bash
git clone https://x-access-token:${GH_TOKEN}@github.com/serbanbogdan/sport.git sport   # sau fără token, doar citire
cd sport
for b in planuri rezulate widget; do git fetch origin $b:$b && git worktree add ../date/$b $b; done
python3 scripts/proceseaza.py --radacina ../date            # index-uri + progres determinist, înainte de orice
```

De lucru există dacă:
1. **Rezultate neanalizate**: în `rezulate/index.json` o sesiune are `"analizat": false`, sau un fișier `rezulate/sesiuni/AAAA/LL/<id>.json` nu are pereche `rezulate/analize/<id>.json`.
2. **Cereri noi**: un fișier din `planuri/cereri/` are `"status": "nou"` (sau `"in_lucru"` mai vechi de 2 ore — reluat).

Dacă nu e nimic: **nu scrii nimic, nu faci commit, ieși** cu un singur rând („nimic de procesat”). Nu reanaliza ce e deja analizat decât la o cerere `reanaliza`.

Procesezi rezultatele în ordine cronologică (cel mai vechi primul), apoi cererile.

## 2. Protocolul de analiză (proiectul Sport)

Citești **tot** fișierul rezultatului (inclusiv `esantioane`, `pasi`, `evenimente`, `plan`), nu doar `rezumat`. Rezumatul e calculat de telefon; verifici cu eșantioanele.

### 2.1 Alergare

1. **Structura reală a sesiunii**: reconstruiești din eșantioane (viteză ≥ 1,95 m/s minim 20 s = bloc de alergare) fiecare bloc: durată, distanță, ritm, cadență, puls la start (= puls la reluare), vârf de puls, momentul vârfului. Compari cu planul (`pasi` planificat vs. realizat, `prelungit_s`, `sarit`). Notezi unde s-a abătut (bloc scurtat, oprire, ritm prea rapid la început).
2. **Cele patru praguri** — pentru fiecare: valoare, „X din N”, ok / nu:
   - puls **sub 155** în blocurile de alergare (vârful fiecărui bloc; un vârf în mersul de după bloc e întârzierea pulsului, îl menționezi separat);
   - **reluare sub 130** (pulsul la startul fiecărui bloc);
   - **cadență 165-170 pași/min** în alergare. Telefonul măsoară pași totali (ambele picioare, spm) — e direct comparabil cu ținta; Strava raportează pe picior (×2 ca să compari);
   - **Z1+Z2 peste 85 %** din timpul sesiunii (`rezumat.timp_zone_s`).
3. **Tendințe în sesiune**: cum evoluează de la blocul 1 la ultimul pulsul la reluare, vârful, ritmul, cadența (ex. „reluare 112→121→126→130”). Deriva cardiacă la același ritm = oboseală.
4. **Comparație cu istoricul**: `widget/progres.json` (`tendinte`, `ultima_sesiune`, `progres_catre_10km`) și analizele anterioare din `rezulate/analize/`. Spui ce s-a îmbunătățit și ce nu, cu numere.
5. **Strava** (dacă ai conectorul): cauți activitatea din aceeași zi și oră (Garmin poate să fi înregistrat aceeași alergare). O folosești doar pentru verificare (puls, distanță, relative effort). **Nu o numeri de două ori**: o dată = o alergare (vezi SCHEME.md §6). Dacă datele diferă mult (distanță > 10 %), spui care sursă e mai credibilă și de ce (GPS telefon vs. ceas).
6. **Subiectiv**: `subiectiv.rpe`, `senzatie`, `durere`, `nota`. Orice durere ascuțită/articulară → sesiunea următoare nu e de alergare până nu confirmă Bogdan că a trecut.
7. **Ton**: direct, cu numere, fără laude goale și fără dramatizare. „3 din 4 blocuri complete; blocul 4 oprit la 118 s, pornit la 134” — nu „ai făcut o treabă minunată”.

Verdict: `bine` (obiectivul planului atins și cel mult un prag ratat la limită), `partial` (obiectiv atins parțial sau 2 praguri ratate), `slab` (obiectiv ratat, sau pulsul scăpat de sub control, sau durere).

### 2.2 Spinning

1. Pe fiecare bloc (`pasi` cu `tip` `alt`): rezistență medie, cadență rpm, putere medie, puls mediu și maxim, % timp în ținte (`timp_in_tinta_pct`) față de plan.
2. **Aderența la Z2**: % din timpul blocurilor cu puls 117-137; cât timp peste 137 și în ce bloc.
3. **rezistenta_z2** a sesiunii (definiția din SCHEME.md §6; `proceseaza.py` o calculează) și ce înseamnă pentru sesiunea următoare (rezistența de pornire).
4. kcal (lucru mecanic / 4184, ca aplicația YESOUL), putere medie, comparație cu sesiunile de spinning anterioare (`spinning.tendinte`).
5. Spinningul e volum aerob de bază, nu înlocuiește progresul către 10 km: nu modifică `progres_catre_10km`.

## 3. Ce scrii după analiză

Pentru fiecare rezultat `<id>`:

1. `rezulate:analize/<id>.md` — pentru citit pe telefon (Markdown simplu: titluri `##`, liste, tabele mici, bold). Structură:
   `# <plan_id> · <data> — <verdict>` · un paragraf de concluzie · `## Structura` (tabel blocuri: nr, durată, ritm, cadență, puls start, vârf) · `## Praguri` · `## Ce a mers` · `## Ce nu a mers` · `## Comparație cu istoricul` · `## Sesiunea următoare` (id, dată, de ce).
2. `rezulate:analize/<id>.json` — schema SCHEME.md §5 (`verdict`, `titlu`, `praguri[]`, `puncte_bune[]`, `probleme[]`, `sesiunea_urmatoare{id,fisier,motiv}`, `progres_headline_pct`).
3. Rulezi din nou `python3 scripts/proceseaza.py --radacina ../date` → pune `analizat: true` în `rezulate/index.json` (din existența `analize/<id>.json`) și actualizează partea deterministă din `widget/progres.json`.
4. Completezi `widget:progres.json` cu ce nu poate face scriptul, păstrând **toate** câmpurile v1 și cheile v2 (SCHEME.md §6):
   - `ultima_sesiune.observatii` și `ultima_sesiune.analiza_detaliata` (`praguri_plan`, `cadenta_in_alergare_spm`, `puls_max_*_loc`) cu concluziile tale;
   - `tendinte.interpretare` (texte scurte cu numere), `consistenta`, `praguri_si_zone.sesiuni_cu_puls_max_sub_155(_pct)` dacă scriptul nu le-a putut corecta;
   - `progres_catre_10km.cel_mai_lung_bloc_continuu_s` doar dacă ai verificat un bloc mai lung decât valoarea curentă (niciodată în jos) + `..._sursa` și `incertitudine`;
   - blocul `spinning` (scriptul îl recalculează din rezultate; tu adaugi doar observații în `spinning.nota` dacă e cazul);
   - `urmatoarea_sesiune`, `urmatoarea_sesiune_alergare`, `urmatoarea_sesiune_spinning` (cu `tip_activitate`), după decizia de la pasul 5;
   - `generat_la` = acum (ISO cu fus orar), `generat_de` = `"claude"`.
   Validezi: `python3 -m json.tool` + `python3 scripts/proceseaza.py --radacina ../date --check` (fără erori).
5. **Decizi sesiunea următoare** (§3.1), o scrii ca plan v2 (§6) în `planuri:sesiuni/<id>.json`, o adaugi în `planuri:index.json` (`status: planificat`, `durata_s` = suma pașilor, `fisier`), muți `urmatoarea.<activitate>` pe ea. Dacă exista deja o sesiune planificată pentru aceeași activitate care nu mai e potrivită, îi pui `status: inlocuit` (nu o ștergi).

### 3.1 Regulile pentru sesiunea următoare

- **Volumul de alergare** (secunde de alergare pe săptămână) crește cu **maxim 10 % pe săptămână**. Blocul continuu crește în trepte mici (≤ 15-30 s), și doar după o sesiune `bine`.
- **Sesiune proastă** (`slab`, sau blocuri neterminate, sau reluare peste 130 în ≥ 2 blocuri, sau vârfuri peste 155 în majoritatea blocurilor): sesiunea următoare **coboară** (bloc mai scurt sau mai puține blocuri sau mers mai lung) sau **se repetă**. Niciodată nu crește.
- `partial` → se repetă structura, cu o singură corecție (ex. mers mai lung, sau un bloc mai puțin).
- **Minim o zi liberă între două alergări.** Data = prima zi permisă, ținând cont de zilele cerute de Bogdan dacă există.
- **Spinning** în zilele fără alergare: 30-45 min, în majoritate Z2 (117-137), cadență 80-90 rpm, rezistența de pornire = `spinning.rezistenta_z2_calibrata` (sau 30 dacă e `null`). Când vremea anulează o alergare, spinningul o înlocuiește în aceeași zi (alergarea se mută, nu se comprimă).
- **Durere ascuțită = stop**: nicio alergare planificată până la confirmare; doar spinning ușor sau pauză.
- Pauză lungă (> 10 zile fără alergare): revii cu un pas înapoi față de ultima sesiune bună.
- Ținte numerice obligatorii: `puls` pe fiecare pas, `ritm_min_km` pe alergare și mers, `cadenta_spm` [160, 172] pe alergare, `pana_la_puls_sub: 130` + `max_prelungire_s: 120` pe mersul de refacere; la spinning `cadenta_rpm`, `rezistenta`, `putere_w`, `puls`.
- Id: alergare `S<luna>.<n+1>` (luna planului: luna 1 = de la 29.08; S1.9 → S1.10; luna nouă → S2.1), spinning `SP<luna>.<n+1>`. Nu refolosești un id din `planuri/index.json`.

## 4. Cereri din aplicație (`planuri/cereri/<id>.json`)

1. Pui `status: "in_lucru"` (commit), ca altă rulare să nu o ia în paralel.
2. După `tip`:
   - `plan_nou`: generezi `nr_sesiuni` sesiuni începând cu `de_la_data`, pentru `activitate` (`alergare`, `spinning` sau `ambele` — atunci alternezi: alergare în zilele permise, spinning între ele), datate pe `zile_disponibile` (luni…duminica; goală = oricare, cu regulile §3.1). Progresia respectă §3.1 pornind de la ultima sesiune analizată.
   - `sesiune_urmatoare`: o singură sesiune, ca la §3 pasul 5.
   - `reanaliza`: refaci analiza ultimului rezultat (sau a celui din `nota`) și suprascrii `analize/<id>.*`.
   - `nota` lui Bogdan are prioritate (ex. „sunt răcit”, „vreau doar spinning săptămâna asta”), cu excepția regulilor de siguranță.
3. Scrii planurile (§6), le adaugi în `planuri/index.json`, actualizezi `urmatoarea` și `widget/progres.json` (`urmatoarea_sesiune*`).
4. În cerere: `status: "gata"`, `raspuns: { "la": "<acum>", "mesaj": "<2-4 propoziții: ce ai planificat și de ce>", "fisiere": ["sesiuni/S2.1.json", ...] }`. La eroare: `status: "eroare"`, `raspuns.mesaj` = cauza.

**Mod API (aplicația sau `claude_api.py`)**: răspunzi DOAR cu un obiect JSON, fără text în jur:
`{"planuri": [<plan v2 complet>, ...], "mesaj": "..."}` — și, când ți se cere analiza unui rezultat, `{"analiza_md": "...", "analiza": {<SCHEME §5>}, "planuri": [...], "mesaj": "..."}`. Fișierele le scrie programul.

## 5. Git

```bash
git config user.name "Claude (Sport)"; git config user.email "noreply@anthropic.com"
cd ../date/rezulate && git add -A && git commit -m "Analiza <id>: <verdict>" && git push origin rezulate
cd ../planuri && git add -A && git commit -m "Plan <id> (<data>) dupa <rezultat_id>" && git push origin planuri
cd ../widget && git add -A && git commit -m "Progres: <rezumat scurt>" && git push origin widget
```
- Un commit pe ramură, mesaj în română, fără diacritice obligatorii, ≤ 72 de caractere în prima linie.
- Push respins (non-fast-forward): `git pull --rebase origin <ramura>`, rezolvi conflictul (pentru `index.json` și `progres.json`: reiei modificarea ta peste versiunea nouă, apoi rulezi din nou `proceseaza.py`), `git push`. Maxim 3 încercări, apoi te oprești și raportezi.
- Nu scrii niciodată pe `main` din task-ul programat (doar documentație, la cererea lui Bogdan).
- Nu ștergi fișiere de rezultate sau planuri. Nu modifici `rezulate/sesiuni/**` (sunt datele brute ale telefonului).
- Commit-urile tale nu declanșează workflow-ul (doar `repository_dispatch` de la telefon, manual sau zilnic la 03:17 UTC).

## 6. Reguli de scriere a planului v2 (din SCHEME.md §1)

- `schema_version: 2`, `id`, `sesiune` (= id), `activitate`, `data` (AAAA-LL-ZZ), `titlu`, `obiectiv` (o propoziție măsurabilă), `nota_generala` (ce s-a întâmplat data trecută și ce schimbi, cu numere), `ritmuri`, `praguri` (`puls_alerta` 155, `puls_reluare` 130, `zona_lucru` [117, 137], `puls_max` 195), `criterii_reusita` (listă verificabilă), `pasi`.
- Poți păstra `"versiune": 1` ca aplicația HTML să-l citească în continuare.
- **`nume`: primul cuvânt = ce execuți** — ritmul (`7:30-8:00/km`), cadența (`80-90 rpm`) sau exercițiul (`Genuflexiuni`) — apoi ` · `, apoi descrierea. **Maxim 40 de caractere.** Ex.: `7:30-8:00/km · Alergare`, `12:00/km · Mers de refacere`, `80-90 rpm · Bloc zona 2`, `Ridicări pe vârfuri · 2x15`.
- `tip`: `incalzire`, `alergare`, `mers`, `racire`, `forta`, `pauza`, `alt`. Spinning: `incalzire`, `alt` (bloc de lucru), `pauza` (pedalat ușor), `racire`.
- `durata` întreg în secunde (> 0). Repetările cu `{"repeta": N, "pasi": [...]}`.
- `tinte` numerice `[min, max]`: `puls`, `ritm_min_km` (`["7:30", "8:00"]`, primul = mai rapid), `cadenta_spm`, `cadenta_rpm`, `rezistenta` (0-100), `putere_w`, `viteza_kmh`.
- Mersul de refacere dintre blocuri: `pana_la_puls_sub: 130`, `max_prelungire_s: 120`.
- Structura standard la alergare: mers alert de încălzire (≥ 5 min, puls sub 110) · forță scurtă (ridicări pe vârfuri, genuflexiuni) · probă de calibrare 60 s la 8:00/km · mers 3 min · blocurile · mers lejer de răcire · întinderi.
- `durata_s` din index = suma `durata` pe pașii desfăcuți. Verifici: `python3 scripts/proceseaza.py --radacina ../date --check`.

# Scheme JSON — repo `serbanbogdan/sport`

Toate fișierele sunt UTF-8, chei în română fără diacritice, valori text în română. Timpi în secunde, distanțe în metri, date ISO 8601 cu fus orar (`2026-10-20T18:32:05+03:00`). `null` = „nu s-a măsurat” (niciodată 0 în loc de lipsă).

## Ramuri

| Ramură | Conținut |
|---|---|
| `main` | documentație, scheme, scripturi, workflow-uri |
| `planuri` | `index.json` (calendarul), `sesiuni/<id>.json` (planuri v2), `cereri/<id>.json` (cereri din aplicație) |
| `rezulate` | `index.json`, `sesiuni/AAAA/LL/<id>.json` (rezultate), `analize/<id>.md` + `analize/<id>.json` (analizele lui Claude) |
| `widget` | `progres.json` (citit de widgetul din Widget Studio și de ecranul Today) |

Adrese „raw” (repo public, fără token): `https://raw.githubusercontent.com/serbanbogdan/sport/<ramura>/<cale>`.
Toate căile din fișiere (`fisier`, `fisier_plan`, `analiza`) sunt relative la rădăcina ramurii lor (`sesiuni/S1.9.json` = `planuri:sesiuni/S1.9.json`).

---

## 1. Plan de sesiune v2 — `planuri/sesiuni/<id>.json`

Exemplu prescurtat (fișierul real `planuri:sesiuni/S1.9.json` are și forța + proba; pașii lui însumează exact 2445 s):

```json
{
  "schema_version": 2,
  "id": "S1.9",
  "sesiune": "S1.9",
  "activitate": "alergare",
  "data": "2026-10-20",
  "titlu": "Proba + 4×(2'30 alergat / 3' mers)",
  "obiectiv": "Toate cele 4 blocuri duse la capăt, fiecare pornit sub 130.",
  "nota_generala": "Zona 2 = 117-137. Alertă la 155.",
  "ritmuri": { "alergare": "7:30-8:00/km (limita dură 7:15)", "mers_refacere": "11:30-12:30/km" },
  "praguri": { "puls_alerta": 155, "puls_reluare": 130, "zona_lucru": [117, 137], "puls_max": 195 },
  "criterii_reusita": ["4 din 4 blocuri complete", "vârf sub 155 în fiecare bloc", "pornire sub 130"],
  "pasi": [
    { "tip": "incalzire", "nume": "11:00/km · Mers alert", "durata": 180, "nota": "puls sub 110",
      "tinte": { "puls": [90, 115] } },
    { "repeta": 4, "pasi": [
      { "tip": "alergare", "nume": "7:30-8:00/km · Alergare", "durata": 150,
        "tinte": { "puls": [117, 155], "ritm_min_km": ["7:30", "8:00"], "cadenta_spm": [160, 172] } },
      { "tip": "mers", "nume": "12:00/km · Mers de refacere", "durata": 180, "nota": "pleci sub 130",
        "tinte": { "puls": [90, 130] }, "pana_la_puls_sub": 130, "max_prelungire_s": 120 }
    ]},
    { "tip": "racire", "nume": "12:30/km · Mers lejer", "durata": 300 }
  ]
}
```

Spinning (`"activitate": "spinning"`, id-uri `SP<luna>.<n>`, ex. `SP1.1`):

```json
{ "tip": "alt", "nume": "85-90 rpm · Bloc zona 2", "durata": 600,
  "tinte": { "cadenta_rpm": [85, 90], "rezistenta": [25, 35], "putere_w": [70, 100], "puls": [117, 137] } }
```

Reguli:
- `tip`: `incalzire`, `alergare`, `mers`, `racire`, `forta`, `pauza`, `alt` (necunoscut → `alt`). Pentru spinning se folosesc `incalzire`, `alt` (bloc de lucru), `pauza` (pedalat ușor), `racire`.
- `id`: alergare `S<luna>.<n>` (ex. `S1.9`, `S2.1`), spinning `SP<luna>.<n>`; unic în `planuri/index.json`. `sesiune` = același text (pentru aplicația HTML). `data` = `AAAA-LL-ZZ`.
- `nume`: primul cuvânt = informația de executat (ritm, rpm sau exercițiu), apoi separatorul ` · `, apoi descrierea; max 40 de caractere (ex. `7:30-8:00/km · Alergare`, `80-90 rpm · Bloc zona 2`, `Genuflexiuni · 10 repetări`).
- `nota`: scurtă, o singură instrucțiune (apare pe ceas sub nume).
- `durata` în secunde. `repeta` se poate imbrica.
- `tinte` (opțional), fiecare `[min, max]`: `puls` (bpm), `ritm_min_km` (`"m:ss"`, primul = cel mai rapid), alternativ `ritm_s_km` (secunde), `cadenta_spm` (pași/min, total ambele picioare), `cadenta_rpm`, `rezistenta` (0-100, valoarea brută YESOUL = % din aplicația YESOUL), `putere_w`, `viteza_kmh`.
- `rezistenta_pct` e acceptat ca alias pentru `rezistenta` (citire), dar se scrie `rezistenta`.
- `pana_la_puls_sub` + `max_prelungire_s` (implicit 120): după `durata`, pasul continuă până pulsul scade sub prag sau expiră prelungirea. Obligatoriu pe mersul de refacere dintre blocuri (`130`, sau pragul `praguri.puls_reluare`).
- `praguri`: `puls_alerta` (implicit 155), `puls_reluare` (130), `zona_lucru` (`[117, 137]`), `puls_max` (195).
- Un fișier v1 (fără `schema_version`) rămâne valid; `activitate` lipsă = `alergare`. Un plan v2 poate păstra `"versiune": 1` pentru aplicația HTML.
- Validare: `scripts/proceseaza.py --check` (aceleași reguli ca `PlanParser` din aplicație: `pasi` nevid, `durata` întreg > 0, fiecare țintă `[min, max]`).

## 2. Calendar — `planuri/index.json`

```json
{
  "schema": "trainlive.planuri", "schema_version": 1,
  "actualizat_la": "2026-10-20T19:05:00+03:00",
  "urmatoarea": { "alergare": "S1.9", "spinning": "SP1.1" },
  "sesiuni": [
    { "id": "S1.9", "activitate": "alergare", "data": "2026-10-20", "titlu": "Proba + 4×(2'30/3')",
      "fisier": "sesiuni/S1.9.json", "status": "planificat", "rezultat_id": null, "durata_s": 2445 }
  ]
}
```
`status`: `planificat` | `realizat` | `ratat` | `anulat` | `inlocuit`. `durata_s` = suma duratelor pașilor (fără prelungiri).
`urmatoarea.<activitate>` = id-ul următoarei sesiuni `planificat` (sau `null`). `proceseaza.py` pune `realizat` + `rezultat_id` când un rezultat are acel `plan_id` și mută pointerul. Aplicația: `planificat` = se importă automat; `realizat` = marcat făcut local; `anulat`/`inlocuit` = șters local dacă nu era făcut.

## 3. Cerere din aplicație — `planuri/cereri/<id>.json`

```json
{
  "schema": "trainlive.cerere", "schema_version": 1,
  "id": "2026-10-20T19-10-00_plan",
  "creat_la": "2026-10-20T19:10:00+03:00",
  "tip": "plan_nou",
  "activitate": "ambele",
  "nr_sesiuni": 6,
  "de_la_data": "2026-10-21",
  "zile_disponibile": ["luni", "miercuri", "vineri", "duminica"],
  "nota": "text liber de la Bogdan",
  "status": "nou",
  "raspuns": null
}
```
`tip`: `plan_nou` (mai multe sesiuni) | `sesiune_urmatoare` | `reanaliza`. `activitate`: `alergare` | `spinning` | `ambele`. `zile_disponibile`: zile ale săptămânii în română fără diacritice (`luni` … `duminica`); listă goală = oricare, cu regulile de odihnă.
`status`: `nou` → `in_lucru` → `gata` / `eroare`. La final `raspuns = { "la": "...", "mesaj": "...", "fisiere": ["sesiuni/S2.1.json", ...] }`.
Câmpuri opționale scrise de aplicație: `procesat_de` (`"aplicatie"` când răspunde direct prin Claude API, altfel `null`), `eroare_api` (textul erorii când apelul direct a eșuat și cererea a revenit la `nou`).

## 4. Rezultat de sesiune — `rezulate/sesiuni/AAAA/LL/<id>.json`

`id` = `AAAA-LL-ZZTHH-MM-SS_<activitate>` (ora locală de start). Calea: `sesiuni/AAAA/LL/<id>.json`, AAAA/LL din id. Fișierul poate avea câțiva MB (eșantioane 1 Hz); se încarcă prin Contents API.

```json
{
  "schema": "trainlive.rezultat", "schema_version": 1,
  "id": "2026-10-21T19-32-05_alergare",
  "activitate": "alergare",
  "start": "2026-10-21T19:32:05+03:00", "sfarsit": "2026-10-21T20:13:40+03:00",
  "aplicatie": { "nume": "Train Live", "versiune": "1.0.3", "telefon": "SM-S938B", "android": 37 },
  "plan_id": "S1.9",
  "plan": { "...": "planul v2 complet, exact cum a fost folosit" },
  "dispozitive": {
    "ceas": { "nume": "Venu X1", "adresa": "AA:BB:..", "folosit": true, "deconectari": 0, "secunde_fara_puls": 3 },
    "bicicleta": null,
    "gps": { "furnizor": "gps", "precizie_medie_m": 3.1, "precizie_p95_m": 6.0, "sateliti_medii": 24, "puncte_respinse": 4 },
    "telefon_senzori": { "pasi": true, "barometru": true }
  },
  "vreme": { "sursa": "open-meteo", "temp_c": 11.2, "umiditate_pct": 70, "vant_kmh": 8, "cod": 3 },
  "subiectiv": { "rpe": 5, "senzatie": 4, "durere": null, "nota": "" },
  "rezumat": {
    "durata_totala_s": 2495, "timp_in_miscare_s": 2410, "timp_pauza_s": 85,
    "distanta_m": 3912, "viteza_medie_kmh": 5.84, "viteza_max_kmh": 9.1,
    "ritm_mediu_s_km": 616, "ritm_in_miscare_s_km": 616, "ritm_alergare_s_km": 472,
    "puls_mediu": 131, "puls_max": 158, "puls_min": 92,
    "cadenta_medie_spm": 128, "cadenta_alergare_spm": 162,
    "cadenta_medie_rpm": null, "putere_medie_w": null, "putere_max_w": null, "putere_normalizata_w": null,
    "rezistenta_medie": null, "lucru_kj": null,
    "kcal": 310, "kcal_sursa": "puls",
    "urcare_m": 12, "coborare_m": 11, "altitudine_min_m": 288, "altitudine_max_m": 301,
    "hrv_rmssd_ms": 21.5, "puls_recuperare_60s": 24,
    "timp_zone_s": { "Z1": 520, "Z2": 1290, "Z3": 560, "Z4": 125, "Z5": 0 },
    "z1_z2_pct": 72.5, "secunde_peste_155": 40, "secunde_peste_160": 0,
    "cel_mai_lung_bloc_alergare_s": 152,
    "blocuri_alergare": [ { "nr": 1, "start_s": 450, "durata_s": 152, "distanta_m": 322, "ritm_s_km": 472,
                            "puls_la_start": 118, "puls_varf": 151, "cadenta_spm": 163 } ],
    "pasi_completi": 9, "pasi_total": 10, "aderenta_tinte_pct": 81.0
  },
  "pasi": [
    { "index": 0, "tip": "incalzire", "nume": "11:00/km · Mers alert", "rep": null, "rep_total": null,
      "planificat_s": 180, "realizat_s": 180, "prelungit_s": 0, "sarit": false, "complet": true,
      "start_s": 0, "sfarsit_s": 180,
      "puls_mediu": 104, "puls_max": 112, "puls_la_start": 92, "puls_la_final": 110,
      "distanta_m": 260, "ritm_mediu_s_km": 692, "cadenta_medie": 112,
      "putere_medie_w": null, "rezistenta_medie": null,
      "tinte": { "puls": [90, 115] },
      "timp_in_tinta_pct": { "puls": 96.0 } }
  ],
  "km": [ { "km": 1, "timp_s": 642, "ritm_s_km": 642, "puls_mediu": 121, "cadenta_spm": 124, "urcare_m": 3 } ],
  "evenimente": [ { "t": 812, "tip": "alerta_puls", "detaliu": "156 > 155" } ],
  "rr_ms": [ 812, 805, 799 ],
  "esantioane": {
    "interval_s": 1,
    "coloane": ["t", "hr", "dist_m", "viteza_kmh", "lat", "lon", "alt_m", "precizie_m",
                "cadenta_spm", "cadenta_rpm", "putere_w", "rezistenta", "kcal", "pas"],
    "valori": [ [0, 92, 0.0, 0.0, 46.1631, 24.3492, 291.2, 3.0, 0, null, null, null, 0.0, 0] ]
  }
}
```

`km`: ultimul kilometru incomplet are `"partial": true` și `distanta_m` (< 1000); nu intră în „cel mai rapid km”.

Tipuri de evenimente: `start`, `pauza`, `reluare`, `pas_inainte`, `pas_inapoi`, `prelungire_puls`, `alerta_puls`, `in_afara_tintei`, `ceas_deconectat`, `ceas_reconectat`, `bicicleta_deconectata`, `bicicleta_reconectata`, `gps_pierdut`, `gps_recuperat`, `final`.
La spinning: `lat/lon/alt_m/precizie_m` = null, `cadenta_spm` = null; `kcal` = lucru mecanic / 4184 (ca în aplicația YESOUL), `kcal_sursa` = `"lucru_mecanic"`.

`rezulate/index.json`:
```json
{ "schema": "trainlive.rezultate", "schema_version": 1, "actualizat_la": "...",
  "sesiuni": [ { "id": "...", "activitate": "alergare", "start": "...", "plan_id": "S1.9",
                 "fisier": "sesiuni/2026/10/<id>.json", "durata_s": 2495, "distanta_m": 3912,
                 "puls_mediu": 131, "puls_max": 158, "kcal": 310,
                 "cel_mai_lung_bloc_alergare_s": 152, "putere_medie_w": null,
                 "data": "2026-10-21", "analiza": "analize/<id>.md", "analizat": true, "verdict": "partial" } ] }
```
Indexul e reconstruit integral de `proceseaza.py` din `sesiuni/**` (nu se editează de mână): `analizat` = există `analize/<id>.json`; `verdict` copiat din acel fișier; `analiza` = calea `.md` sau `null`.

## 5. Analiză — `rezulate/analize/<id>.json` (+ `<id>.md` pentru citit)

```json
{ "schema": "trainlive.analiza", "schema_version": 1, "id": "<id rezultat>", "creat_la": "...",
  "verdict": "bine | partial | slab", "titlu": "o propoziție",
  "praguri": [ { "nume": "Vârf sub 155 în blocuri", "rezultat": "3 din 4", "ok": false } ],
  "puncte_bune": ["..."], "probleme": ["..."],
  "sesiunea_urmatoare": { "id": "S1.10", "fisier": "sesiuni/S1.10.json", "motiv": "..." },
  "progres_headline_pct": 3.2 }
```

## 6. Progres pentru widget — `widget/progres.json` (v2)

Citit de widgetul „Drum spre 10 km” din Widget Studio (`app/.../run/RunData.kt`) și de ecranul Today din Train Live.
Păstrează **toate** câmpurile v1 cu aceleași nume și sens (vezi fișierul): `generat_la`, `sursa`, `atlet`, `tinta`, `progres_catre_10km`, `jaloane`, `jalon_curent`, `luna_1`, `totaluri`, `ultima_sesiune`, `tendinte`, `consistenta`, `praguri_si_zone`, `alte_activitati`, `urmatoarea_sesiune`, `echipament`, `widget_hint`. Adaugă / extinde:

```json
{
  "schema_version": 2,
  "generat_de": "proceseaza.py | claude | migrare",
  "sesiuni_aplicatie": 4,
  "urmatoarea_sesiune": { "cod": "S1.9", "tip_activitate": "alergare", "titlu": "...", "data_planificata": "2026-10-20",
                          "fisier_plan": "sesiuni/S1.9.json", "durata_planificata_s": 2445, "...": "câmpurile v1" },
  "urmatoarea_sesiune_alergare":  { "cod": "S1.9",  "tip_activitate": "alergare", "titlu": "...", "data_planificata": "...", "fisier_plan": "..." },
  "urmatoarea_sesiune_spinning":  { "cod": "SP1.1", "tip_activitate": "spinning", "titlu": "...", "data_planificata": "2026-10-21", "fisier_plan": "sesiuni/SP1.1.json" },
  "spinning": {
    "totaluri": { "sesiuni": 2, "timp_total_s": 4200, "timp_total_h": 1.17, "distanta_totala_km": 31.2, "kcal_total": 410,
                  "echivalent_alergare_min": 33.0, "echivalent_alergare_definitie": "..." },
    "rezistenta_z2_calibrata": 31,
    "rezistenta_z2_definitie": "...",
    "ultima_sesiune": { "id": "...", "data": "2026-10-19", "durata_s": 2100, "distanta_km": 15.1, "putere_medie_w": 78,
                        "cadenta_medie_rpm": 82, "rezistenta_medie": 31, "puls_mediu": 124, "kcal": 205, "rezistenta_z2": 31 },
    "tendinte": { "etichete_date": [], "rezistenta_z2": [], "putere_medie_w": [], "cadenta_medie_rpm": [],
                  "rezistenta_medie": [], "kcal": [], "puls_mediu": [] },
    "sesiuni": [ { "id": "...", "data": "2026-10-19", "plan_id": "SP1.1", "durata_s": 2100, "timp_in_miscare_s": 2080,
                   "distanta_km": 15.1, "kcal": 205, "putere_medie_w": 78, "cadenta_medie_rpm": 82, "rezistenta_medie": 31,
                   "puls_mediu": 124, "puls_max": 139, "rezistenta_z2": 31, "secunde_z2": 1650 } ]
  },
  "volum_aerob_combinat": { "total_h": 7.5, "spinning_pct": 15.6, "alergare_s": 22805, "spinning_s": 4200, "definitie": "..." },
  "widget_hint": { "...": "câmpurile v1", "culoare_spinning": "#E7B366" }
}
```

Definiții (scrise și în fișier, lângă valori):
- **Echivalent bloc** = `cel_mai_lung_bloc_continuu_s × 1000 / 465` m (ritm 7:45/km). `procent_headline` = echivalent / 10 000 × 100; `procent_pe_timp` = bloc / 4650 s × 100; `distanta_ramasa_m` = 10 000 − echivalent.
- **Jaloane**: `tinta_min` → `progres_pct` = bloc_s / (tinta_min × 60) × 100; `tinta_distanta_km` → echivalent / (km × 1000) × 100; maxim 100, `status` = `atins` la 100 (rămâne atins). L1-test 25 min, L2 40 min, L3 8 km, L4 10 km. `jalon_curent` = primul neatins.
- **rezistenta_z2** (o sesiune de spinning) = mediana rezistenței în secundele cu puls în Z2 (117-137 la HR max 195, capete incluse) și cadență > 50 rpm; `null` dacă sunt sub 120 de astfel de secunde. **rezistenta_z2_calibrata** = mediana ultimelor 3 valori nenule; `null` = necalibrat (niciodată 0).
- **echivalent_alergare_min** = minute de spinning cu puls în Z2 × 0,6 — estimare, afișată cu „≈”.
- **volum_aerob_combinat**: `alergare_s` = `totaluri.timp_in_miscare_total_s`; `spinning_s` = suma `timp_in_miscare_s` din `spinning.sesiuni`; `total_h` = (alergare_s + spinning_s) / 3600; `spinning_pct` = spinning_s / total × 100.
- `urmatoarea_sesiune` = următoarea sesiune în general (cea mai apropiată dată; la egalitate alergarea), cu `tip_activitate`. `fisier_plan` e relativ la ramura `planuri`.

Fără dublă numărare (Strava + aplicație):
- Câmpurile v1 provin din Strava (proiectul Sport). O alergare înregistrată cu Train Live poate apărea și pe Strava (Garmin a înregistrat-o în paralel). Regula: **o dată calendaristică = o alergare** în `tendinte` și `totaluri`. `proceseaza.py` adaugă o alergare din aplicație în `tendinte` (+ `totaluri`, `consistenta.saptamani`) doar dacă data ei nu e deja în `tendinte.etichete_date`.
- `tendinte.sursa` (listă paralelă cu `etichete_date`): `"strava"` | `"aplicatie"`. Când Claude adaugă din Strava o alergare a cărei dată există deja cu sursa `aplicatie`, o înlocuiește (aceeași poziție, nu adaugă) și scade din `totaluri` valorile aplicației înainte să le adune pe cele Strava.
- `progres_catre_10km.cel_mai_lung_bloc_continuu_s` doar crește (maximul dintre valoarea existentă și blocurile măsurate de aplicație).
- `ultima_sesiune` se înlocuiește când rezultatul aplicației e mai nou (`"sursa": "aplicatie"`, `rezultat_id`, `strava_id: null`, `relative_effort: null`).
- Spinningul vine doar din aplicație (`alte_activitati` rămâne pentru ture de bicicletă Strava).

`zile_de_la_ultima_alergare` se recalculează de cititor din `ultima_sesiune.data` (valoarea din fișier e doar la momentul generării).

# nutritie — meniurile lui Bogdan

Ramura `nutritie` a repo-ului `sport` ține datele aplicației Android **Nutriție** (mic dejun acasă și prânz la serviciu,
zile lucrătoare, dietă pentru hipertensiune). Aplicația citește de aici fără token (repo public).

| Fișier | Ce conține | Cine scrie |
|---|---|---|
| `meniuri/AAAA-LL-ZZ.json` | meniul unei săptămâni; numele = data de **luni** a săptămânii | Claude, prin skill-ul `/nutritie` |
| `setari.json` | `excluse`: mâncăruri și alimente pe care nu le vrea; `favorite`: mese care i-au plăcut (inimă în aplicație), repetate mai des | aplicația (Setări) sau Claude, când Bogdan cere |
| `valideaza.py` | verifică un meniu (schemă, 5 zile, sodiu, excluse) | manual / Claude înainte de push |

Aplicația ia automat săptămâna trecută, cea curentă și următoarele două. Sâmbătă și duminică afișează săptămâna următoare.

## Schema `nutritie.meniu` v1

```json
{
  "schema": "nutritie.meniu", "v": 1,
  "saptamana": "2026-10-26",
  "creat": "2026-10-22T21:30:00+03:00",
  "sursa": "claude",
  "alimente_acasa": ["..."],
  "note": "text scurt despre săptămână",
  "zile": [
    {
      "data": "2026-10-26", "zi": "Luni",
      "mic_dejun": {"nume": "", "ingrediente": ["ovăz 40 g"], "portie": "", "kcal": 320, "sodiu_mg": 60, "pregatire": "", "nota": ""},
      "gustare_dimineata": {},
      "pranz": {},
      "gustare_dupamasa": {},
      "ceai": {"nume": "", "cum": "", "de_ce": ""}
    }
  ],
  "cumparaturi": [{"produs": "", "cantitate": "", "magazin": "Lidl | Kaufland | Acasă"}],
  "sfaturi": ["..."]
}
```

* Exact 5 zile (luni–vineri). Fiecare zi are `mic_dejun`, `gustare_dimineata`, `pranz`, `gustare_dupamasa`, `ceai`.
* `kcal` și `sodiu_mg` sunt estimări pe porția scrisă; `nume`, `ingrediente` și `portie` sunt obligatorii la mese.
* Textele sunt în română. Fără sare adăugată în rețete.

## Schema `nutritie.setari` v1

```json
{"schema": "nutritie.setari", "v": 1, "actualizat": "2026-10-22T21:30:00+03:00", "excluse": ["ficat", "varză murată"], "favorite": ["Terci de ovăz cu măr și scorțișoară"]}
```

## Validare

```bash
python3 valideaza.py meniuri/2026-10-26.json --setari setari.json
```

Informațiile din meniu sunt sugestii generale pentru o persoană hipertensivă, nu înlocuiesc sfatul medicului.

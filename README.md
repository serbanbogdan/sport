# sport — date de antrenament Train Live

Repo public cu antrenamentele lui Bogdan (drumul spre 10 km alergare continuă + spinning).
Aplicația Android **Train Live** încarcă aici fiecare sesiune. Claude o analizează automat și scrie aici
planurile următoare și progresul citit de widgetul din Widget Studio.

## Ramuri

| Ramură | Ce conține | Cine scrie |
|---|---|---|
| `main` | documentație (`docs/`), scripturi (`scripts/`), workflow (`.github/workflows/`) | manual |
| `planuri` | `index.json` (calendarul), `sesiuni/<id>.json` (planuri v2), `cereri/<id>.json` (cereri din aplicație) | Claude, aplicația (cereri) |
| `rezulate` | `index.json`, `sesiuni/AAAA/LL/<id>.json` (rezultate 1 Hz), `analize/<id>.md` + `.json` | aplicația (rezultate), Claude (analize) |
| `widget` | `progres.json` (v2) — widgetul „Drum spre 10 km” și ecranul Today | `proceseaza.py`, Claude |

Numele `rezulate` e scris intenționat așa (aplicația îl folosește exact).

## Cum se leagă

1. Termini un antrenament în Train Live → aplicația face `PUT rezulate:sesiuni/AAAA/LL/<id>.json` și
   trimite `repository_dispatch` `sesiune_noua`.
2. GitHub Actions (`proceseaza.yml`) rulează `scripts/proceseaza.py`: reconstruiește `rezulate/index.json`,
   marchează planul `realizat` în `planuri/index.json`, actualizează `widget/progres.json`
   (bloc continuu, tendințe, spinning, volum aerob — fără dublă numărare cu Strava).
   Dacă există secretul `ANTHROPIC_API_KEY`, rulează și `scripts/claude_api.py` (analiză + plan imediat).
3. Fără cheie API, task-ul programat Claude (din oră în oră, 06–23) urmează `docs/INSTRUCTIUNI_CLAUDE.md`:
   analiza în `rezulate/analize/`, sesiunea următoare în `planuri/sesiuni/`, progresul în `widget/`.
4. Butonul de sincronizare din aplicație (sau automat la deschidere / la 3 ore) descarcă analiza, planul nou
   (import automat) și progresul. Widgetul citește `widget/progres.json` direct, fără token.
5. „Ask Claude for a plan” din aplicație scrie `planuri/cereri/<id>.json` + `repository_dispatch` `cerere_plan`.

Formatele: `docs/SCHEME.md`. Arhitectura: `docs/ANALIZA.md`. Regulile de analiză și planificare: `docs/INSTRUCTIUNI_CLAUDE.md`.

## Tokenul de pe telefon

În Train Live → Settings → GitHub (owner `serbanbogdan`, repo `sport`) lipești un token:

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Resource owner: `serbanbogdan`; Expiration: la alegere (ex. 1 an).
3. Repository access: **Only select repositories** → `serbanbogdan/sport`.
4. Permissions → Repository permissions → **Contents: Read and write** (Metadata: Read-only se pune singur). Nimic altceva.
5. Generate, copiezi tokenul în aplicație, apoi „Test connection”.

Tokenul vechi folosit de widget pentru repo-ul privat `widget-studio` **nu mai e necesar**: `widget/progres.json`
e public și se citește fără token. Îl poți revoca.

Fără token, aplicația funcționează (citește tot), dar rezultatele rămân „pending” pe telefon până pui tokenul.

## Opțional: Claude API

- În GitHub Actions: Settings → Secrets and variables → Actions → secretul `ANTHROPIC_API_KEY`
  (și, opțional, variabila `CLAUDE_MODEL`, implicit `claude-sonnet-5-5`). Fără secret, pasul se sare.
- În aplicație: Settings → Anthropic API key → cererile de plan primesc răspuns imediat.

## Scripturi

```bash
mkdir date; for b in planuri rezulate widget; do git fetch origin $b:$b; git worktree add date/$b $b; done
python3 scripts/proceseaza.py --radacina date --check   # validează, nu scrie
python3 scripts/proceseaza.py --radacina date           # scrie index-urile și progresul
python3 scripts/proceseaza.py --self-test
ANTHROPIC_API_KEY=... python3 scripts/claude_api.py --radacina date
```
Doar Python 3 standard, fără dependențe.

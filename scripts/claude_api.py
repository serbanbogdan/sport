#!/usr/bin/env python3
"""Calea opțională prin Claude API (Messages API) pentru repo-ul Train Live.

Dacă variabila de mediu ANTHROPIC_API_KEY lipsește, iese imediat cu 0 (nimic de făcut).
Altfel aplică docs/INSTRUCTIUNI_CLAUDE.md pe:
  - rezultatele fără analiză (rezulate/sesiuni/**/<id>.json fără rezulate/analize/<id>.json);
  - cererile cu status "nou" din planuri/cereri/.
Scrie aceleași fișiere ca task-ul programat: analize/<id>.md + .json, planuri/sesiuni/<id>.json,
planuri/index.json, cererea (status gata/eroare). Apoi rulează proceseaza.py (index-uri + widget).
Commit-ul îl face workflow-ul. Doar biblioteca standard.

Folosire: python3 scripts/claude_api.py --radacina date [--max 5]
Variabile: ANTHROPIC_API_KEY (obligatorie), CLAUDE_MODEL (implicit claude-sonnet-5-5).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proceseaza as P  # noqa: E402

URL = "https://api.anthropic.com/v1/messages"
MODEL_IMPLICIT = "claude-sonnet-5-5"
MAX_TOKENS = 12000
TIMEOUT_S = 300
PAS_ESANTIOANE = 5          # în prompt: un eșantion la 5 s (fișierul complet e prea mare)

MOD_API = """

---

MOD API (scripts/claude_api.py, GitHub Actions): nu ai acces la git, Strava sau alte fișiere decât cele din mesaj.
Aplici regulile de mai sus pe datele primite. Răspunzi cu UN SINGUR obiect JSON, fără text înainte sau după și fără ```.
Programul scrie fișierele, actualizează index-urile și face commit-ul."""


def log(msg):
    print(msg, flush=True)


def apel(cheie, model, system, user):
    corp = json.dumps({
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    ultima = None
    for incercare in range(3):
        req = urllib.request.Request(URL, data=corp, method="POST", headers={
            "content-type": "application/json",
            "x-api-key": cheie,
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                o = json.loads(r.read().decode("utf-8"))
            return "".join(p.get("text", "") for p in o.get("content") or [] if p.get("type") == "text")
        except urllib.error.HTTPError as e:
            try:
                detaliu = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                detaliu = ""
            ultima = "HTTP %d %s" % (e.code, detaliu[:200])
            if e.code not in (429, 500, 502, 503, 529):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            ultima = "rețea: %s" % e
        time.sleep(10 * (incercare + 1))
    raise RuntimeError("Claude API: " + (ultima or "eroare"))


def extrage_json(text):
    t = text.strip()
    for cand in [t] + re.findall(r"```(?:json)?\s*([\s\S]*?)```", t):
        try:
            o = json.loads(cand.strip())
            if isinstance(o, dict):
                return o
        except ValueError:
            pass
    dec = json.JSONDecoder()
    i = t.find("{")
    while i >= 0:
        try:
            o, _ = dec.raw_decode(t[i:])
            if isinstance(o, dict):
                return o
        except ValueError:
            pass
        i = t.find("{", i + 1)
    raise RuntimeError("răspunsul nu conține un obiect JSON")


def compacteaza_rezultat(o):
    """Rezultatul complet, dar cu eșantioanele rărite și fără lista RR (sunt MB)."""
    c = dict(o)
    e = o.get("esantioane") or {}
    val = e.get("valori") or []
    c["esantioane"] = {"interval_s": (e.get("interval_s") or 1) * PAS_ESANTIOANE,
                       "nota": "rarite: 1 din %d" % PAS_ESANTIOANE,
                       "coloane": e.get("coloane"), "valori": val[::PAS_ESANTIOANE]}
    rr = o.get("rr_ms") or []
    c["rr_ms"] = {"numar": len(rr), "nota": "omise in prompt; vezi rezumat.hrv_rmssd_ms"}
    return c


def scrie_plan(d_pl, plan, sursa):
    erori, _ = P.valideaza_plan(plan)
    if erori:
        raise RuntimeError("plan %s invalid: %s" % (plan.get("id"), "; ".join(erori)))
    plan.setdefault("schema_version", 2)
    plan.setdefault("sesiune", plan["id"])
    pid = re.sub(r"[^A-Za-z0-9._-]", "_", plan["id"])
    rel = "sesiuni/%s.json" % pid
    (d_pl / "sesiuni").mkdir(parents=True, exist_ok=True)
    (d_pl / rel).write_text(P.text_json(plan), encoding="utf-8")
    idx_p = d_pl / "index.json"
    idx = P.citeste(idx_p) if idx_p.is_file() else {"schema": "trainlive.planuri", "schema_version": 1,
                                                     "urmatoarea": {}, "sesiuni": []}
    act = plan.get("activitate") or "alergare"
    intrare = {"id": plan["id"], "activitate": act, "data": plan.get("data"), "titlu": plan.get("titlu"),
               "fisier": rel, "status": "planificat", "rezultat_id": None,
               "durata_s": P.rezumat_plan(plan)["durata_s"], "sursa": sursa}
    lista = idx.setdefault("sesiuni", [])
    for i, e in enumerate(lista):
        if e.get("id") == plan["id"]:
            lista[i] = intrare
            break
    else:
        lista.append(intrare)
    # O sesiune planificată mai veche, pentru aceeași activitate și aceeași zi, e înlocuită.
    for e in lista:
        if e is not intrare and e.get("activitate") == act and e.get("data") == plan.get("data") \
                and e.get("status") == "planificat":
            e["status"] = "inlocuit"
    urm = idx.setdefault("urmatoarea", {})
    cur = next((e for e in lista if e.get("id") == urm.get(act) and e.get("status") == "planificat"), None)
    if cur is None or (plan.get("data") or "9999") < (cur.get("data") or "9999"):
        urm[act] = plan["id"]
    idx["actualizat_la"] = P.acum_iso()
    idx_p.write_text(P.text_json(idx), encoding="utf-8")
    return rel


def context_comun(rad):
    d_w, d_pl, d_rez = rad / "widget", rad / "planuri", rad / "rezulate"
    progres = (d_w / "progres.json").read_text(encoding="utf-8") if (d_w / "progres.json").is_file() else "null"
    idx_pl = (d_pl / "index.json").read_text(encoding="utf-8") if (d_pl / "index.json").is_file() else "null"
    analize = []
    d_an = d_rez / "analize"
    if d_an.is_dir():
        for f in sorted(d_an.glob("*.json"))[-5:]:
            try:
                analize.append(P.citeste(f))
            except (OSError, ValueError):
                pass
    return ("## widget/progres.json\n```json\n%s\n```\n\n## planuri/index.json\n```json\n%s\n```\n\n"
            "## Ultimele analize (JSON)\n```json\n%s\n```\n" % (progres[:80000], idx_pl[:40000],
                                                                json.dumps(analize, ensure_ascii=False)[:30000]))


def analizeaza(rad, rel, o, cheie, model, system):
    rid = o["id"]
    user = ("# Sarcina: analiza rezultatului %s (protocolul §2) și decizia sesiunii următoare (§3.1)\n\n"
            "Răspunde cu: {\"analiza_md\": \"<Markdown §3 pasul 1>\", \"analiza\": {<SCHEME §5, id=%s>}, "
            "\"planuri\": [<planul v2 al sesiunii următoare>], \"mesaj\": \"<o propoziție>\"}\n\n"
            "## Rezultatul (%s)\n```json\n%s\n```\n\n%s" % (
                rid, rid, rel, json.dumps(compacteaza_rezultat(o), ensure_ascii=False), context_comun(rad)))
    r = extrage_json(apel(cheie, model, system, user))
    md, an = r.get("analiza_md"), r.get("analiza")
    if not isinstance(md, str) or not isinstance(an, dict):
        raise RuntimeError("lipsește analiza_md sau analiza")
    an.setdefault("schema", "trainlive.analiza")
    an.setdefault("schema_version", 1)
    an["id"] = rid
    an.setdefault("creat_la", P.acum_iso())
    an["generat_de"] = "claude_api.py"
    fisiere = []
    for p in r.get("planuri") or []:
        if isinstance(p, dict):
            fisiere.append(scrie_plan(rad / "planuri", p, "claude_api:" + rid))
    if fisiere and isinstance(an.get("sesiunea_urmatoare"), dict):
        an["sesiunea_urmatoare"].setdefault("fisier", fisiere[0])
    d_an = rad / "rezulate" / "analize"
    d_an.mkdir(parents=True, exist_ok=True)
    (d_an / (rid + ".md")).write_text(md.rstrip() + "\n", encoding="utf-8")
    (d_an / (rid + ".json")).write_text(P.text_json(an), encoding="utf-8")   # ultimul: marchează „analizat”
    log("analizat %s: %s, planuri %s" % (rid, an.get("verdict"), fisiere))


def proceseaza_cerere(rad, f, cheie, model, system):
    c = P.citeste(f)
    c["status"] = "in_lucru"
    c["procesat_de"] = "claude_api.py"
    f.write_text(P.text_json(c), encoding="utf-8")
    user = ("# Sarcina: cererea din aplicație (§4)\n\nRăspunde cu: {\"planuri\": [<planuri v2 complete>], "
            "\"mesaj\": \"<2-4 propoziții>\"}\n\n## Cererea\n```json\n%s\n```\n\n%s" % (
                json.dumps(c, ensure_ascii=False, indent=1), context_comun(rad)))
    try:
        r = extrage_json(apel(cheie, model, system, user))
        fisiere = [scrie_plan(rad / "planuri", p, "claude_api:" + c.get("id", f.stem))
                   for p in r.get("planuri") or [] if isinstance(p, dict)]
        if not fisiere and c.get("tip") != "reanaliza":
            raise RuntimeError("niciun plan în răspuns")
        c["status"] = "gata"
        c["raspuns"] = {"la": P.acum_iso(), "mesaj": r.get("mesaj") or "", "fisiere": fisiere}
        log("cerere %s: gata %s" % (f.name, fisiere))
    except Exception as e:  # cererea rămâne vizibilă cu eroarea; task-ul programat o poate relua
        c["status"] = "eroare"
        c["raspuns"] = {"la": P.acum_iso(), "mesaj": "Claude API: %s" % e, "fisiere": []}
        log("cerere %s: eroare %s" % (f.name, e))
    f.write_text(P.text_json(c), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--radacina", default="date")
    ap.add_argument("--manual", default=str(Path(__file__).resolve().parent.parent / "docs" / "INSTRUCTIUNI_CLAUDE.md"))
    ap.add_argument("--max", type=int, default=5, help="maxim rezultate analizate într-o rulare")
    a = ap.parse_args(argv)
    cheie = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not cheie:
        return 0
    model = os.environ.get("CLAUDE_MODEL", "").strip() or MODEL_IMPLICIT
    rad = Path(a.radacina)
    system = Path(a.manual).read_text(encoding="utf-8") + MOD_API

    P.proceseaza(rad, silentios=True)
    rezultate, _ = P.incarca_rezultate(rad / "rezulate")
    de_analizat = [(rel, o) for rel, o in rezultate
                   if not (rad / "rezulate" / "analize" / (o["id"] + ".json")).is_file()]
    d_c = rad / "planuri" / "cereri"
    cereri = []
    if d_c.is_dir():
        for f in sorted(d_c.glob("*.json")):
            try:
                if P.citeste(f).get("status") == "nou":
                    cereri.append(f)
            except (OSError, ValueError):
                pass
    if not de_analizat and not cereri:
        log("claude_api: nimic de procesat")
        return 0

    esecuri = 0
    for rel, o in de_analizat[:a.max]:
        try:
            analizeaza(rad, rel, o, cheie, model, system)
            P.proceseaza(rad, silentios=True)       # plan realizat, progres, analizat
        except Exception as e:
            esecuri += 1
            log("analiza %s a eșuat: %s (rămâne pentru task-ul programat)" % (o["id"], e))
    for f in cereri:
        proceseaza_cerere(rad, f, cheie, model, system)
    erori, _ = P.proceseaza(rad)
    return 1 if erori or (esecuri and esecuri == len(de_analizat[:a.max])) else 0


if __name__ == "__main__":
    sys.exit(main())

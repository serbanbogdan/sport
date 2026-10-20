#!/usr/bin/env python3
"""Procesare deterministă a datelor Train Live (repo serbanbogdan/sport).

Lucrează pe cele trei ramuri de date, scoase ca worktree-uri într-un director rădăcină:
    <radacina>/planuri   <radacina>/rezulate   <radacina>/widget

Ce face (idempotent: a doua rulare pe aceleași date nu mai schimbă nimic):
  1. reconstruiește rezulate/index.json din rezulate/sesiuni/**/*.json;
  2. în planuri/index.json marchează „realizat” (+ rezultat_id) sesiunile care au un rezultat cu acel
     plan_id și mută pointerii `urmatoarea` pe următoarea sesiune planificată;
  3. actualizează widget/progres.json (v2) din rezultatele aplicației, fără dublă numărare cu Strava
     (definițiile sunt scrise în fișier, vezi docs/SCHEME.md §6).

Folosire:
    python3 scripts/proceseaza.py --radacina date          # scrie fișierele modificate
    python3 scripts/proceseaza.py --radacina date --check  # doar validează și raportează
    python3 scripts/proceseaza.py --self-test              # test pe date sintetice

Doar biblioteca standard Python 3.
"""

import argparse
import copy
import datetime as dt
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

# ----------------------------------------------------------------------------- constante (documentate în progres.json)

RITM_ECHIVALENT_S_KM = 465          # 7:45/km
DISTANTA_TINTA_M = 10000
TIMP_10KM_S = 77.5 * 60             # 10 km la 7:45/km
FACTOR_ECHIV_SPINNING = 0.6         # 1 min spinning în Z2 ≈ 0,6 min alergare (estimare)
MIN_SECUNDE_REZ_Z2 = 120            # sub atât, rezistenta_z2 = null
CADENTA_MIN_RPM = 50                # sub atât nu se pedalează efectiv
Z2_IMPLICIT = (117, 137)
CULOARE_SPINNING = "#E7B366"
FUS_ORAR = "Europe/Bucharest"

TIPURI_PAS = {"incalzire", "alergare", "mers", "racire", "forta", "pauza", "alt"}
CHEI_TINTE = {"puls", "ritm_min_km", "ritm_s_km", "cadenta_spm", "cadenta_rpm", "rezistenta",
              "rezistenta_pct", "putere_w", "viteza_kmh"}
STATUS_PLAN = {"planificat", "realizat", "ratat", "anulat", "inlocuit"}
CHEI_V1 = ["atlet", "tinta", "progres_catre_10km", "jaloane", "jalon_curent", "totaluri", "ultima_sesiune",
           "tendinte", "consistenta", "praguri_si_zone", "urmatoarea_sesiune", "widget_hint"]
CHEI_TIMP = {"generat_la", "generat_de", "actualizat_la"}

DEF_ECHIVALENT = ("distanta echivalenta = durata celui mai lung bloc continuu de alergare × 1000/465 m "
                  "(ritm 7:45/km); procent_headline = distanta echivalenta / 10 km")
DEF_JALOANE = ("progres_pct al unui jalon: tinta_min → bloc_s / (tinta_min × 60); tinta_distanta_km → "
               "distanta echivalenta / (tinta_distanta_km × 1000); maxim 100, status 'atins' la 100")
DEF_REZ_Z2 = ("rezistenta_z2 a unei sesiuni = mediana rezistentei in secundele cu puls in Z2 (inclusiv capetele) "
              "si cadenta > 50 rpm; null daca sunt sub 120 de astfel de secunde. rezistenta_z2_calibrata = "
              "mediana ultimelor 3 valori nenule (null = necalibrat, niciodata 0)")
DEF_ECHIV_SPIN = "echivalent_alergare_min = minute de spinning cu puls in Z2 × 0,6 (estimare, nu masuratoare)"
DEF_VOLUM = ("alergare_s = totaluri.timp_in_miscare_total_s; spinning_s = suma timp_in_miscare_s din spinning.sesiuni; "
             "total_h = (alergare_s + spinning_s) / 3600; spinning_pct = spinning_s / total × 100")


# ----------------------------------------------------------------------------- utilitare

def citeste(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def text_json(o):
    return json.dumps(o, ensure_ascii=False, indent=2) + "\n"


def fara_timp(o):
    if isinstance(o, dict):
        return {k: fara_timp(v) for k, v in o.items() if k not in CHEI_TIMP}
    if isinstance(o, list):
        return [fara_timp(v) for v in o]
    return o


def r1(x):
    return None if x is None else round(float(x), 1)


def r2(x):
    return None if x is None else round(float(x), 2)


def ritm_text(s_km):
    if s_km is None or s_km <= 0:
        return None
    s = int(round(s_km))
    return "%d:%02d" % (s // 60, s % 60)


def ritm_s(text):
    if isinstance(text, (int, float)):
        return float(text)
    try:
        m, s = str(text).strip().replace("/km", "").split(":")
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def data_din(iso):
    return (iso or "")[:10]


def saptamana_iso(data):
    d = dt.date.fromisoformat(data)
    an, sapt, _ = d.isocalendar()
    return "%d-W%02d" % (an, sapt)


def acum_iso(acum=None):
    if acum:
        return acum
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(FUS_ORAR)).replace(microsecond=0).isoformat()
    except Exception:
        return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


# ----------------------------------------------------------------------------- planuri

def aplatizeaza(pasi, rep=None, total=None, out=None):
    """Pașii planului cu repetările desfăcute (ca PlanParser din aplicație)."""
    if out is None:
        out = []
    for p in pasi or []:
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("pasi"), list):
            n = p.get("repeta") or 0
            if isinstance(n, int) and n > 0:
                for r in range(1, n + 1):
                    aplatizeaza(p["pasi"], r, n, out)
            else:
                aplatizeaza(p["pasi"], rep, total, out)
            continue
        q = dict(p)
        q["_rep"], q["_rep_total"] = rep, total
        out.append(q)
    return out


def valideaza_plan(o):
    """Erori (blochează) și avertismente pentru un plan v1/v2. Aceleași reguli ca PlanParser + SCHEME.md §1."""
    erori, avert = [], []
    if not isinstance(o, dict):
        return ["planul nu e un obiect JSON"], avert
    if not isinstance(o.get("pasi"), list) or not o["pasi"]:
        return ["lipsește lista 'pasi'"], avert
    pasi = aplatizeaza(o["pasi"])
    if not pasi:
        erori.append("planul nu are niciun pas")
    if o.get("schema_version") == 2:
        for k in ("id", "activitate", "titlu"):
            if not o.get(k):
                erori.append("lipsește '%s'" % k)
        if o.get("activitate") not in (None, "alergare", "spinning"):
            erori.append("activitate necunoscută: %r" % o.get("activitate"))
        if o.get("data"):
            try:
                dt.date.fromisoformat(o["data"])
            except ValueError:
                erori.append("data invalidă: %r" % o["data"])
    for i, p in enumerate(pasi):
        eticheta = "pasul %d (%s)" % (i + 1, p.get("nume", "?"))
        d = p.get("durata")
        if not isinstance(d, int) or d <= 0:
            erori.append(eticheta + ": durata trebuie să fie un întreg > 0")
        if p.get("tip") not in TIPURI_PAS:
            avert.append(eticheta + ": tip necunoscut %r (devine 'alt')" % p.get("tip"))
        nume = p.get("nume") or ""
        if len(nume) > 40:
            avert.append(eticheta + ": nume mai lung de 40 de caractere")
        if nume and " · " not in nume and p.get("tip") not in ("forta",):
            avert.append(eticheta + ": nume fără separatorul ' · '")
        t = p.get("tinte")
        if t is not None:
            if not isinstance(t, dict):
                erori.append(eticheta + ": 'tinte' trebuie să fie obiect")
            else:
                for k, v in t.items():
                    if k not in CHEI_TINTE:
                        avert.append(eticheta + ": țintă necunoscută %r" % k)
                    if not isinstance(v, list) or len(v) != 2:
                        erori.append(eticheta + ": ținta %s trebuie să fie [min, max]" % k)
                    elif k == "ritm_min_km":
                        if ritm_s(v[0]) is None or ritm_s(v[1]) is None:
                            erori.append(eticheta + ": ritm_min_km trebuie să fie [\"m:ss\", \"m:ss\"]")
                    elif not all(num(x) is not None for x in v):
                        erori.append(eticheta + ": ținta %s trebuie să conțină numere" % k)
        if p.get("pana_la_puls_sub") is not None and num(p.get("pana_la_puls_sub")) is None:
            erori.append(eticheta + ": pana_la_puls_sub trebuie să fie număr")
    return erori, avert


def rezumat_plan(o):
    pasi = aplatizeaza(o.get("pasi"))
    total = sum(p.get("durata") or 0 for p in pasi)
    alerg = [p for p in pasi if p.get("tip") == "alergare"]
    blocuri = [p for p in alerg if p["_rep"] is not None]
    return {
        "durata_s": total,
        "alergare_s": sum(p.get("durata") or 0 for p in alerg),
        "blocuri": len(blocuri),
        "bloc_max_s": max([p.get("durata") or 0 for p in alerg] or [0]),
        "bloc_planificat_s": max([p.get("durata") or 0 for p in blocuri] or [0]) or None,
    }


# ----------------------------------------------------------------------------- rezultate

def incarca_rezultate(dir_rez):
    rez, erori = [], []
    baza = Path(dir_rez) / "sesiuni"
    if not baza.is_dir():
        return rez, erori
    for p in sorted(baza.rglob("*.json")):
        rel = p.relative_to(dir_rez).as_posix()
        try:
            o = citeste(p)
        except (OSError, ValueError) as e:
            erori.append("%s: JSON invalid (%s)" % (rel, e))
            continue
        probleme = []
        if o.get("schema") != "trainlive.rezultat":
            probleme.append("schema != trainlive.rezultat")
        for k in ("id", "activitate", "start"):
            if not o.get(k):
                probleme.append("lipsește " + k)
        if o.get("id") and o["id"] != p.stem:
            probleme.append("id %r diferit de numele fișierului" % o["id"])
        if not isinstance(o.get("rezumat"), dict):
            probleme.append("lipsește rezumat")
        if probleme:
            erori.append("%s: %s" % (rel, "; ".join(probleme)))
            continue
        rez.append((rel, o))
    rez.sort(key=lambda x: (x[1]["start"], x[1]["id"]))
    return rez, erori


def construieste_index_rezultate(rezultate, dir_rez, vechi, acum):
    sesiuni = []
    for rel, o in rezultate:
        r = o["rezumat"]
        rid = o["id"]
        an_json = Path(dir_rez) / "analize" / (rid + ".json")
        an_md = Path(dir_rez) / "analize" / (rid + ".md")
        verdict = None
        if an_json.is_file():
            try:
                verdict = citeste(an_json).get("verdict")
            except (OSError, ValueError):
                verdict = None
        sesiuni.append({
            "id": rid,
            "activitate": o["activitate"],
            "start": o["start"],
            "data": data_din(o["start"]),
            "plan_id": o.get("plan_id"),
            "fisier": rel,
            "durata_s": r.get("durata_totala_s"),
            "distanta_m": r.get("distanta_m"),
            "puls_mediu": r.get("puls_mediu"),
            "puls_max": r.get("puls_max"),
            "kcal": r.get("kcal"),
            "cel_mai_lung_bloc_alergare_s": r.get("cel_mai_lung_bloc_alergare_s"),
            "putere_medie_w": r.get("putere_medie_w"),
            "analiza": ("analize/%s.md" % rid) if an_md.is_file() else None,
            "analizat": an_json.is_file(),
            "verdict": verdict,
        })
    nou = {"schema": "trainlive.rezultate", "schema_version": 1, "actualizat_la": acum, "sesiuni": sesiuni}
    if vechi is not None and fara_timp(vechi) == fara_timp(nou):
        return vechi
    return nou


def actualizeaza_index_planuri(index, rezultate, azi, acum):
    if index is None:
        return None
    nou = copy.deepcopy(index)
    lista = nou.setdefault("sesiuni", [])
    dupa_plan = {}
    for _, o in rezultate:
        if o.get("plan_id"):
            dupa_plan[o["plan_id"]] = o["id"]          # rezultatele sunt cronologice: rămâne ultimul
    for e in lista:
        rid = dupa_plan.get(e.get("id"))
        if rid and e.get("status") in ("planificat", "ratat", None):
            e["status"] = "realizat"
            e["rezultat_id"] = rid
        elif rid and e.get("status") == "realizat" and not e.get("rezultat_id"):
            e["rezultat_id"] = rid
    urm = nou.setdefault("urmatoarea", {})
    for act in ("alergare", "spinning"):
        cur = next((e for e in lista if e.get("id") == urm.get(act)), None)
        if cur is not None and cur.get("status") == "planificat":
            continue
        cand = sorted((e for e in lista if e.get("activitate") == act and e.get("status") == "planificat"
                       and (e.get("data") or "9999") >= azi),
                      key=lambda e: (e.get("data") or "9999", e.get("id")))
        if cand:
            urm[act] = cand[0]["id"]
        elif act in urm:
            urm[act] = None
    if fara_timp(nou) == fara_timp(index):
        return index
    nou["actualizat_la"] = acum
    return nou


# ----------------------------------------------------------------------------- spinning

def coloana(o, nume):
    e = o.get("esantioane") or {}
    col = e.get("coloane") or []
    return col.index(nume) if nume in col else None


def statistici_spinning(o, z2):
    """(rezistenta_z2, secunde_z2) din eșantioanele 1 Hz."""
    e = o.get("esantioane") or {}
    valori = e.get("valori") or []
    ih, ir, ic = coloana(o, "hr"), coloana(o, "rezistenta"), coloana(o, "cadenta_rpm")
    sec_z2 = None
    rez_z2 = None
    if ih is not None and valori:
        sec_z2 = 0
        rez = []
        for v in valori:
            hr = num(v[ih]) if ih < len(v) else None
            if hr is None or not (z2[0] <= hr <= z2[1]):
                continue
            sec_z2 += 1
            if ir is None or ic is None:
                continue
            res = num(v[ir]) if ir < len(v) else None
            cad = num(v[ic]) if ic < len(v) else None
            if res is not None and cad is not None and cad > CADENTA_MIN_RPM:
                rez.append(res)
        if len(rez) >= MIN_SECUNDE_REZ_Z2:
            rez_z2 = int(round(statistics.median(rez)))
    if sec_z2 is None:
        zone = (o.get("rezumat") or {}).get("timp_zone_s") or {}
        sec_z2 = num(zone.get("Z2"))
    return rez_z2, sec_z2


def bloc_spinning(rezultate, z2):
    ses = []
    for _, o in rezultate:
        if o["activitate"] != "spinning":
            continue
        r = o["rezumat"]
        rz2, sz2 = statistici_spinning(o, z2)
        ses.append({
            "id": o["id"],
            "data": data_din(o["start"]),
            "plan_id": o.get("plan_id"),
            "durata_s": r.get("durata_totala_s"),
            "timp_in_miscare_s": r.get("timp_in_miscare_s") if r.get("timp_in_miscare_s") is not None else r.get("durata_totala_s"),
            "distanta_km": r2((r.get("distanta_m") or 0) / 1000.0) if r.get("distanta_m") is not None else None,
            "kcal": r.get("kcal"),
            "putere_medie_w": r.get("putere_medie_w"),
            "cadenta_medie_rpm": r.get("cadenta_medie_rpm"),
            "rezistenta_medie": r.get("rezistenta_medie"),
            "puls_mediu": r.get("puls_mediu"),
            "puls_max": r.get("puls_max"),
            "rezistenta_z2": rz2,
            "secunde_z2": sz2,
        })
    t_s = sum(s["timp_in_miscare_s"] or 0 for s in ses)
    z2_s = sum(s["secunde_z2"] or 0 for s in ses)
    rz = [s["rezistenta_z2"] for s in ses if s["rezistenta_z2"] is not None]
    ultima = None
    if ses:
        u = ses[-1]
        ultima = {k: u[k] for k in ("id", "data", "durata_s", "distanta_km", "putere_medie_w", "cadenta_medie_rpm",
                                    "rezistenta_medie", "puls_mediu", "kcal", "rezistenta_z2")}
    return {
        "totaluri": {
            "sesiuni": len(ses),
            "timp_total_s": t_s,
            "timp_total_h": r2(t_s / 3600.0),
            "distanta_totala_km": r2(sum(s["distanta_km"] or 0 for s in ses)),
            "kcal_total": int(round(sum(s["kcal"] or 0 for s in ses))),
            "echivalent_alergare_min": r1(z2_s / 60.0 * FACTOR_ECHIV_SPINNING),
            "echivalent_alergare_definitie": DEF_ECHIV_SPIN,
        },
        "rezistenta_z2_calibrata": int(round(statistics.median(rz[-3:]))) if rz else None,
        "rezistenta_z2_definitie": DEF_REZ_Z2,
        "ultima_sesiune": ultima,
        "tendinte": {
            "etichete_date": [s["data"] for s in ses],
            "rezistenta_z2": [s["rezistenta_z2"] for s in ses],
            "putere_medie_w": [s["putere_medie_w"] for s in ses],
            "cadenta_medie_rpm": [s["cadenta_medie_rpm"] for s in ses],
            "rezistenta_medie": [s["rezistenta_medie"] for s in ses],
            "kcal": [s["kcal"] for s in ses],
            "puls_mediu": [s["puls_mediu"] for s in ses],
        },
        "sesiuni": ses,
    }


# ----------------------------------------------------------------------------- alergare -> progres

def ultima_din_rezultat(o, plan, nr, cumulat):
    r = o["rezumat"]
    blocuri = r.get("blocuri_alergare") or []
    rp = rezumat_plan(plan) if plan else None
    bloc_plan = rp["bloc_planificat_s"] if rp else None
    pasi = o.get("pasi") or []
    pb = [p for p in pasi if p.get("tip") == "alergare" and p.get("rep") is not None]
    executate = [p for p in pb if not p.get("sarit") and (p.get("realizat_s") or 0) > 0]
    complete = [p for p in pb if p.get("complet")]
    alergat = sum(b.get("durata_s") or 0 for b in blocuri)
    dur = r.get("durata_totala_s")
    km_full = [k for k in (o.get("km") or []) if not k.get("partial") and num(k.get("timp_s"))]
    zone = r.get("timp_zone_s") or {}
    tz = sum(num(v) or 0 for v in zone.values())
    pm = r.get("puls_max")

    def pct(a, b):
        return r1(100.0 * a / b) if a is not None and b else None

    return {
        "nr": nr,
        "sursa": "aplicatie",
        "rezultat_id": o["id"],
        "strava_id": None,
        "data": data_din(o["start"]),
        "ora_start": o["start"][11:16],
        "sesiune_plan": o.get("plan_id"),
        "titlu_plan": (plan or {}).get("titlu"),
        "distanta_km": r2((r.get("distanta_m") or 0) / 1000.0),
        "distanta_cumulata_km": cumulat,
        "timp_in_miscare_s": r.get("timp_in_miscare_s"),
        "timp_total_s": dur,
        "ritm_mediu_in_miscare_min_km": ritm_text(r.get("ritm_in_miscare_s_km")),
        "ritm_mediu_in_miscare_s_km": r.get("ritm_in_miscare_s_km"),
        "ritm_mediu_total_min_km": ritm_text(r.get("ritm_mediu_s_km")),
        "cel_mai_rapid_km_s": min((k["timp_s"] for k in km_full), default=None),
        "cel_mai_rapid_km_min_km": ritm_text(min((k["timp_s"] for k in km_full), default=None)),
        "puls_mediu": r.get("puls_mediu"),
        "puls_max": pm,
        "puls_max_pct_din_195": r1(100.0 * pm / 195) if pm else None,
        "relative_effort": None,
        "cadenta_medie_sesiune_spm": r.get("cadenta_medie_spm"),
        "cadenta_in_alergare_spm": r.get("cadenta_alergare_spm"),
        "plan": {
            "durata_planificata_s": rp["durata_s"] if rp else None,
            "alergare_planificata_s": rp["alergare_s"] if rp else None,
            "blocuri_planificate": rp["blocuri"] if rp else None,
            "blocuri_executate": len(executate) if pb else len(blocuri),
            "bloc_alergare_max_masurat_s": r.get("cel_mai_lung_bloc_alergare_s"),
        },
        "realizat_fata_de_plan": {
            "durata_pct": pct(dur, rp["durata_s"] if rp else None),
            "blocuri_pct": pct(len(executate), rp["blocuri"] if rp else None),
            "alergare_pct": pct(alergat, rp["alergare_s"] if rp else None),
            "blocuri_complete_pct": pct(len(complete), rp["blocuri"] if rp else None),
            "nota": "calculat de proceseaza.py din rezultatul aplicatiei Train Live",
        },
        "praguri": {
            "puls_max_sub_155_proxy": (pm <= 155) if pm is not None else None,
            "nota": "proxy: HR max al intregii sesiuni <= 155; pragul real e pe blocurile de alergare",
        },
        "observatii": "Sesiune inregistrata cu Train Live; analiza lui Claude urmeaza in rezulate/analize/%s.md." % o["id"],
        "analiza_detaliata": {
            "sursa": "Train Live: puls Venu X1 + GPS si pasi de la telefon, esantioane 1 Hz; blocuri = viteza >= 1,95 m/s minim 20 s",
            "blocuri_alergare": [{
                "nr": b.get("nr"),
                "durata_s": b.get("durata_s"),
                "planificat_s": bloc_plan,
                "ritm_min_km": ritm_text(b.get("ritm_s_km")),
                "puls_la_reluare": b.get("puls_la_start"),
                "puls_varf": b.get("puls_varf"),
                "cadenta_spm": b.get("cadenta_spm"),
                "complet": (b.get("durata_s") or 0) >= bloc_plan - 10 if bloc_plan else None,
            } for b in blocuri],
            "zone_puls_pct": {k: r1(100.0 * (num(v) or 0) / tz) for k, v in zone.items()} if tz else None,
            "z1_z2_pct": r.get("z1_z2_pct"),
            "secunde_peste_155": r.get("secunde_peste_155"),
            "secunde_peste_160": r.get("secunde_peste_160"),
        },
    }


def recalculeaza_progres_10km(p, bloc_s, sursa_text):
    pr = p.setdefault("progres_catre_10km", {})
    vechi = num(pr.get("cel_mai_lung_bloc_continuu_s")) or 0
    bloc = max(vechi, bloc_s or 0)
    if bloc > vechi and sursa_text:
        pr["cel_mai_lung_bloc_continuu_sursa"] = sursa_text + " (inainte: %d s)" % vechi
    pr["cel_mai_lung_bloc_continuu_s"] = int(bloc)
    echiv = bloc * 1000.0 / RITM_ECHIVALENT_S_KM
    pr["distanta_echivalenta_m"] = int(round(echiv))
    pr["distanta_ramasa_m"] = int(round(DISTANTA_TINTA_M - echiv))
    pr["procent_headline"] = r1(100.0 * echiv / DISTANTA_TINTA_M)
    pr["procent_pe_timp"] = r1(100.0 * bloc / TIMP_10KM_S)
    pr.setdefault("procent_headline_definitie", DEF_ECHIVALENT)
    pr["jaloane_progres_definitie"] = DEF_JALOANE
    curent = None
    for j in p.get("jaloane") or []:
        if num(j.get("tinta_min")):
            v = 100.0 * bloc / (j["tinta_min"] * 60)
        elif num(j.get("tinta_distanta_km")):
            v = 100.0 * echiv / (j["tinta_distanta_km"] * 1000)
        else:
            continue
        j["progres_pct"] = r1(min(100.0, v))
        if v >= 100:
            j["status"] = "atins"
        elif j.get("status") == "atins":
            pass                                   # un jalon atins rămâne atins
        if curent is None and j.get("status") != "atins":
            curent = j.get("cod")
    if curent:
        p["jalon_curent"] = curent
    return echiv


def insereaza_tendinta(t, data, valori, sursa_initiala):
    etich = t.setdefault("etichete_date", [])
    n = len(etich)
    if "sursa" not in t:
        t["sursa"] = [sursa_initiala] * n
    poz = n
    while poz > 0 and etich[poz - 1] > data:
        poz -= 1
    for k, v in list(t.items()):
        if k == "etichete_date" or not isinstance(v, list) or len(v) != n:
            continue
        v.insert(poz, valori.get(k))
    for k, val in valori.items():                  # serii noi: completate cu null
        if k not in t:
            t[k] = [None] * n
            t[k].insert(poz, val)
    etich.insert(poz, data)


def adauga_in_totaluri(p, o):
    r = o["rezumat"]
    km = (r.get("distanta_m") or 0) / 1000.0
    ts = r.get("timp_in_miscare_s") or r.get("durata_totala_s") or 0
    tot = p.setdefault("totaluri", {})
    tot["alergari"] = (tot.get("alergari") or 0) + 1
    tot["distanta_totala_km"] = r2((tot.get("distanta_totala_km") or 0) + km)
    tot["timp_in_miscare_total_s"] = int((tot.get("timp_in_miscare_total_s") or 0) + ts)
    tot["timp_in_miscare_total_h"] = r2(tot["timp_in_miscare_total_s"] / 3600.0)
    if tot["distanta_totala_km"]:
        tot["ritm_mediu_global_min_km"] = ritm_text(tot["timp_in_miscare_total_s"] / tot["distanta_totala_km"])
        tot["distanta_medie_pe_sesiune_km"] = r2(tot["distanta_totala_km"] / tot["alergari"])
    cons = p.setdefault("consistenta", {})
    sapt = cons.setdefault("saptamani", [])
    cheie = saptamana_iso(data_din(o["start"]))
    s = next((x for x in sapt if x.get("saptamana_iso") == cheie), None)
    if s is None:
        s = {"saptamana_iso": cheie, "sesiuni": 0, "km": 0, "timp_in_miscare_s": 0, "relative_effort_total": None}
        sapt.append(s)
        sapt.sort(key=lambda x: x.get("saptamana_iso") or "")
    s["sesiuni"] = (s.get("sesiuni") or 0) + 1
    s["km"] = r2((s.get("km") or 0) + km)
    s["timp_in_miscare_s"] = int((s.get("timp_in_miscare_s") or 0) + ts)
    pz = p.setdefault("praguri_si_zone", {})
    if "sesiuni_cu_puls_max_sub_155" in pz:
        pm = r.get("puls_max")
        if pm is not None and pm <= 155:
            pz["sesiuni_cu_puls_max_sub_155"] = (pz.get("sesiuni_cu_puls_max_sub_155") or 0) + 1
        pz["sesiuni_cu_puls_max_sub_155_pct"] = r1(100.0 * pz["sesiuni_cu_puls_max_sub_155"] / tot["alergari"])


def recalculeaza_pauze(p, azi):
    date = sorted(set((p.get("tendinte") or {}).get("etichete_date") or []))
    pauze = []
    for a, b in zip(date, date[1:]):
        pauze.append({"de_la": a, "pana_la": b,
                      "zile": (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days})
    cons = p.setdefault("consistenta", {})
    cons["pauze_intre_alergari"] = pauze
    cons["cea_mai_lunga_pauza_zile"] = max((x["zile"] for x in pauze), default=0)


def obiect_urmatoare(e, plan, bloc_curent, vechi):
    act = e.get("activitate") or "alergare"
    o = {}
    if isinstance(vechi, dict) and vechi.get("cod") == e.get("id"):
        o = dict(vechi)
    o.update({
        "cod": e.get("id"),
        "tip_activitate": act,
        "fisier_plan": e.get("fisier") or "sesiuni/%s.json" % e.get("id"),
        "data_planificata": e.get("data"),
        "titlu": (plan or {}).get("titlu") or e.get("titlu"),
    })
    if plan:
        rp = rezumat_plan(plan)
        o["durata_planificata_s"] = rp["durata_s"]
        if act == "alergare":
            o["alergare_planificata_s"] = rp["alergare_s"]
            o["bloc_continuu_planificat_s"] = rp["bloc_max_s"]
            o["procent_headline_dupa_executie_corecta"] = r1(
                100.0 * max(bloc_curent, rp["bloc_max_s"]) * 1000.0 / RITM_ECHIVALENT_S_KM / DISTANTA_TINTA_M)
    elif e.get("durata_s") is not None:
        o["durata_planificata_s"] = e.get("durata_s")
    return o


def actualizeaza_progres(progres, rezultate, index_planuri, dir_planuri, azi, acum):
    if progres is None:
        return None
    p = copy.deepcopy(progres)
    p["schema_version"] = 2
    z2 = tuple(((p.get("praguri_si_zone") or {}).get("zone_puls_bpm") or {}).get("Z2") or Z2_IMPLICIT)
    sursa_init = "strava" if (p.get("sursa") or {}).get("strava_athlete_id") else None

    # Alergări din aplicație
    planuri_cache = {}

    def plan_dupa_id(pid):
        if not pid or not dir_planuri:
            return None
        if pid not in planuri_cache:
            f = None
            for e in (index_planuri or {}).get("sesiuni") or []:
                if e.get("id") == pid:
                    f = e.get("fisier")
            cale = Path(dir_planuri) / (f or "sesiuni/%s.json" % pid)
            try:
                planuri_cache[pid] = citeste(cale)
            except (OSError, ValueError):
                planuri_cache[pid] = None
        return planuri_cache[pid]

    alergari = [o for _, o in rezultate if o["activitate"] == "alergare"]
    bloc_max = 0
    sursa_bloc = None
    for o in alergari:
        b = num(o["rezumat"].get("cel_mai_lung_bloc_alergare_s")) or 0
        if b > bloc_max:
            bloc_max = b
            sursa_bloc = "%s, %s, %d s masurate de Train Live" % (o.get("plan_id") or "fara plan",
                                                                   data_din(o["start"]), b)
    recalculeaza_progres_10km(p, bloc_max, sursa_bloc)

    t = p.setdefault("tendinte", {})
    adaugate = False
    for o in alergari:
        data = data_din(o["start"])
        if data in (t.get("etichete_date") or []):
            continue
        r = o["rezumat"]
        km_full = [k["timp_s"] for k in (o.get("km") or []) if not k.get("partial") and num(k.get("timp_s"))]
        insereaza_tendinta(t, data, {
            "distanta_km": r2((r.get("distanta_m") or 0) / 1000.0),
            "puls_mediu": r.get("puls_mediu"),
            "puls_max": r.get("puls_max"),
            "relative_effort": None,
            "ritm_mediu_in_miscare_s_km": r.get("ritm_in_miscare_s_km"),
            "cel_mai_rapid_km_s": min(km_full) if km_full else None,
            "sursa": "aplicatie",
        }, sursa_init)
        adauga_in_totaluri(p, o)
        adaugate = True
    if adaugate:
        recalculeaza_pauze(p, azi)

    if alergari:
        o = alergari[-1]
        u = p.get("ultima_sesiune") or {}
        data, ora = data_din(o["start"]), o["start"][11:16]
        mai_noua = (data > (u.get("data") or "")) or (
            data == u.get("data") and not u.get("strava_id") and ora > (u.get("ora_start") or ""))
        if u.get("rezultat_id") != o["id"] and mai_noua:
            etich = t.get("etichete_date") or []
            nr = etich.index(data) + 1 if data in etich else (u.get("nr") or 0) + 1
            cumulat = (p.get("totaluri") or {}).get("distanta_totala_km")
            p["ultima_sesiune"] = ultima_din_rezultat(o, plan_dupa_id(o.get("plan_id")), nr, cumulat)
            cons = p.setdefault("consistenta", {})
            cons["zile_de_la_ultima_alergare"] = max(0, (dt.date.fromisoformat(azi) - dt.date.fromisoformat(data)).days)

    # Spinning (doar din aplicație)
    p["spinning"] = bloc_spinning(rezultate, z2)
    p["sesiuni_aplicatie"] = len(rezultate)

    # Volum aerob combinat
    a_s = int((p.get("totaluri") or {}).get("timp_in_miscare_total_s") or 0)
    s_s = int(p["spinning"]["totaluri"]["timp_total_s"] or 0)
    p["volum_aerob_combinat"] = {
        "total_h": r2((a_s + s_s) / 3600.0),
        "spinning_pct": r1(100.0 * s_s / (a_s + s_s)) if (a_s + s_s) else 0.0,
        "alergare_s": a_s,
        "spinning_s": s_s,
        "definitie": DEF_VOLUM,
    }

    # Următoarele sesiuni (din planuri/index.json)
    if index_planuri:
        lista = index_planuri.get("sesiuni") or []
        urm = index_planuri.get("urmatoarea") or {}
        bloc_cur = num(p["progres_catre_10km"].get("cel_mai_lung_bloc_continuu_s")) or 0
        alese = {}
        for act in ("alergare", "spinning"):
            e = next((x for x in lista if x.get("id") == urm.get(act) and x.get("status") == "planificat"), None)
            if e is not None:
                alese[act] = e
        if "alergare" in alese:
            e = alese["alergare"]
            vechi = p.get("urmatoarea_sesiune_alergare") or p.get("urmatoarea_sesiune")
            p["urmatoarea_sesiune_alergare"] = obiect_urmatoare(e, plan_dupa_id(e["id"]), bloc_cur, vechi)
        if "spinning" in alese:
            e = alese["spinning"]
            p["urmatoarea_sesiune_spinning"] = obiect_urmatoare(e, plan_dupa_id(e["id"]), bloc_cur,
                                                                p.get("urmatoarea_sesiune_spinning"))
        if alese:
            prima = min(alese.values(), key=lambda e: (e.get("data") or "9999", 0 if e.get("activitate") == "alergare" else 1))
            act = prima.get("activitate") or "alergare"
            sursa = p["urmatoarea_sesiune_alergare"] if act == "alergare" else p["urmatoarea_sesiune_spinning"]
            vechi = p.get("urmatoarea_sesiune") or {}
            if vechi.get("cod") == sursa.get("cod"):
                nou = dict(vechi)
                nou.update(sursa)
            else:
                nou = dict(sursa)
            p["urmatoarea_sesiune"] = nou

    wh = p.setdefault("widget_hint", {})
    wh.setdefault("culoare_spinning", CULOARE_SPINNING)

    if fara_timp(p) == fara_timp(progres):
        return progres
    p["generat_la"] = acum
    p["generat_de"] = "proceseaza.py"
    return p


def valideaza_progres(p):
    erori = []
    for k in CHEI_V1:
        if k not in p:
            erori.append("progres.json: lipsește cheia v1 '%s'" % k)
    if p.get("schema_version") != 2:
        erori.append("progres.json: schema_version != 2")
    sp = p.get("spinning")
    if not isinstance(sp, dict):
        erori.append("progres.json: lipsește blocul spinning")
    else:
        for k in ("totaluri", "ultima_sesiune", "tendinte", "sesiuni", "rezistenta_z2_calibrata"):
            if k not in sp:
                erori.append("progres.json: spinning.%s lipsește" % k)
        if sp.get("rezistenta_z2_calibrata") == 0:
            erori.append("progres.json: rezistenta_z2_calibrata = 0 (trebuie null când nu e calibrat)")
    t = p.get("tendinte") or {}
    n = len(t.get("etichete_date") or [])
    for k, v in t.items():
        if isinstance(v, list) and len(v) != n:
            erori.append("progres.json: tendinte.%s are %d valori, etichete_date are %d" % (k, len(v), n))
    for k in ("urmatoarea_sesiune", "urmatoarea_sesiune_alergare", "urmatoarea_sesiune_spinning"):
        u = p.get(k)
        if isinstance(u, dict) and u.get("tip_activitate") not in (None, "alergare", "spinning"):
            erori.append("progres.json: %s.tip_activitate invalid" % k)
    return erori


# ----------------------------------------------------------------------------- rulare

def proceseaza(radacina, check=False, acum=None, azi=None, silentios=False):
    rad = Path(radacina)
    d_pl, d_rez, d_w = rad / "planuri", rad / "rezulate", rad / "widget"
    acum = acum_iso(acum)
    azi = azi or acum[:10]
    erori, avert, schimbari = [], [], []

    rezultate, er = incarca_rezultate(d_rez) if d_rez.is_dir() else ([], [])
    erori += er

    def incarca(cale):
        if not cale.is_file():
            return None
        try:
            return citeste(cale)
        except (OSError, ValueError) as e:
            erori.append("%s: JSON invalid (%s)" % (cale, e))
            return None

    idx_rez_vechi = incarca(d_rez / "index.json") if d_rez.is_dir() else None
    idx_pl_vechi = incarca(d_pl / "index.json") if d_pl.is_dir() else None
    progres_vechi = incarca(d_w / "progres.json") if d_w.is_dir() else None

    # Validare planuri
    if d_pl.is_dir():
        for f in sorted((d_pl / "sesiuni").glob("*.json")) if (d_pl / "sesiuni").is_dir() else []:
            o = incarca(f)
            if o is None:
                continue
            e, a = valideaza_plan(o)
            erori += ["planuri/%s: %s" % (f.relative_to(d_pl).as_posix(), x) for x in e]
            avert += ["planuri/%s: %s" % (f.relative_to(d_pl).as_posix(), x) for x in a]
        for e in (idx_pl_vechi or {}).get("sesiuni") or []:
            if e.get("status") not in STATUS_PLAN:
                erori.append("planuri/index.json: %s are status invalid %r" % (e.get("id"), e.get("status")))
            if e.get("fisier") and not (d_pl / e["fisier"]).is_file():
                erori.append("planuri/index.json: %s -> %s nu există" % (e.get("id"), e["fisier"]))

    idx_rez = construieste_index_rezultate(rezultate, d_rez, idx_rez_vechi, acum) if d_rez.is_dir() else None
    idx_pl = actualizeaza_index_planuri(idx_pl_vechi, rezultate, azi, acum)
    progres = actualizeaza_progres(progres_vechi, rezultate, idx_pl, d_pl if d_pl.is_dir() else None, azi, acum)
    if progres is not None:
        erori += valideaza_progres(progres)

    for cale, vechi, nou in ((d_rez / "index.json", idx_rez_vechi, idx_rez),
                             (d_pl / "index.json", idx_pl_vechi, idx_pl),
                             (d_w / "progres.json", progres_vechi, progres)):
        if nou is None or nou is vechi:
            continue
        schimbari.append(str(cale))
        if not check:
            tmp = cale.with_suffix(".json.tmp")
            tmp.write_text(text_json(nou), encoding="utf-8")
            os.replace(tmp, cale)

    if not silentios:
        print("rezultate: %d (%d alergare, %d spinning)" % (
            len(rezultate), sum(1 for _, o in rezultate if o["activitate"] == "alergare"),
            sum(1 for _, o in rezultate if o["activitate"] == "spinning")))
        for s in schimbari:
            print(("de modificat: " if check else "modificat: ") + s)
        if not schimbari:
            print("nicio modificare")
        for a in avert:
            print("avertisment: " + a)
        for e in erori:
            print("EROARE: " + e, file=sys.stderr)
    return erori, schimbari


# ----------------------------------------------------------------------------- self-test

def _rezultat_sintetic(rid, act, start, plan_id, bloc_s, esantioane):
    alergare = act == "alergare"
    return {
        "schema": "trainlive.rezultat", "schema_version": 1, "id": rid, "activitate": act,
        "start": start, "sfarsit": start, "plan_id": plan_id, "plan": {},
        "rezumat": {
            "durata_totala_s": 2450, "timp_in_miscare_s": 2400, "distanta_m": 3950 if alergare else 15100,
            "ritm_mediu_s_km": 620, "ritm_in_miscare_s_km": 608, "puls_mediu": 128, "puls_max": 153,
            "cadenta_medie_spm": 120 if alergare else None, "cadenta_alergare_spm": 150 if alergare else None,
            "cadenta_medie_rpm": None if alergare else 84, "putere_medie_w": None if alergare else 88,
            "rezistenta_medie": None if alergare else 30, "kcal": 300,
            "timp_zone_s": {"Z1": 600, "Z2": 1500, "Z3": 300, "Z4": 0, "Z5": 0},
            "cel_mai_lung_bloc_alergare_s": bloc_s,
            "blocuri_alergare": [{"nr": 1, "start_s": 500, "durata_s": bloc_s, "distanta_m": 330,
                                  "ritm_s_km": 470, "puls_la_start": 118, "puls_varf": 150, "cadenta_spm": 160}] if alergare else [],
        },
        "pasi": [{"index": 5, "tip": "alergare", "rep": 1, "rep_total": 4, "realizat_s": bloc_s, "complet": True}] if alergare else [],
        "km": [{"km": 1, "timp_s": 600}, {"km": 2, "timp_s": 590}, {"km": 3, "timp_s": 300, "partial": True}],
        "esantioane": {"interval_s": 1, "coloane": ["t", "hr", "cadenta_rpm", "rezistenta"], "valori": esantioane},
    }


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        rad = Path(tmp)
        for d in ("planuri/sesiuni", "planuri/cereri", "rezulate/sesiuni/2026/10", "rezulate/analize", "widget"):
            (rad / d).mkdir(parents=True)
        plan = {"schema_version": 2, "id": "S1.9", "sesiune": "S1.9", "activitate": "alergare", "data": "2026-10-20",
                "titlu": "Test", "pasi": [
                    {"tip": "alergare", "nume": "8:00/km · Proba", "durata": 60},
                    {"repeta": 4, "pasi": [
                        {"tip": "alergare", "nume": "7:30-8:00/km · Alergare", "durata": 150,
                         "tinte": {"puls": [117, 155], "ritm_min_km": ["7:30", "8:00"]}},
                        {"tip": "mers", "nume": "12:00/km · Mers", "durata": 180, "pana_la_puls_sub": 130}]}]}
        spin = {"schema_version": 2, "id": "SP1.1", "activitate": "spinning", "data": "2026-10-21", "titlu": "Spin",
                "pasi": [{"tip": "alt", "nume": "80-90 rpm · Bloc", "durata": 600,
                          "tinte": {"cadenta_rpm": [80, 90], "rezistenta": [25, 35]}}]}
        (rad / "planuri/sesiuni/S1.9.json").write_text(text_json(plan))
        (rad / "planuri/sesiuni/SP1.1.json").write_text(text_json(spin))
        (rad / "planuri/index.json").write_text(text_json({
            "schema": "trainlive.planuri", "schema_version": 1, "actualizat_la": "x",
            "urmatoarea": {"alergare": "S1.9", "spinning": "SP1.1"},
            "sesiuni": [
                {"id": "S1.9", "activitate": "alergare", "data": "2026-10-20", "titlu": "Test",
                 "fisier": "sesiuni/S1.9.json", "status": "planificat", "rezultat_id": None, "durata_s": 1380},
                {"id": "SP1.1", "activitate": "spinning", "data": "2026-10-21", "titlu": "Spin",
                 "fisier": "sesiuni/SP1.1.json", "status": "planificat", "rezultat_id": None, "durata_s": 600}]}))
        (rad / "rezulate/index.json").write_text(text_json({"schema": "trainlive.rezultate", "schema_version": 1,
                                                            "actualizat_la": "x", "sesiuni": []}))
        progres = {
            "schema_version": 1, "generat_la": "x", "sursa": {"strava_athlete_id": 1},
            "atlet": {}, "tinta": {},
            "progres_catre_10km": {"procent_headline": 3.1, "cel_mai_lung_bloc_continuu_s": 145},
            "jaloane": [{"cod": "L1-test", "tinta_min": 25, "status": "in_asteptare"},
                        {"cod": "L2", "tinta_min": 40, "status": "in_asteptare"},
                        {"cod": "L3", "tinta_distanta_km": 8, "status": "in_asteptare"},
                        {"cod": "L4", "tinta_distanta_km": 10, "status": "in_asteptare"}],
            "jalon_curent": "L1-test",
            "totaluri": {"alergari": 1, "distanta_totala_km": 3.91, "timp_in_miscare_total_s": 2334},
            "ultima_sesiune": {"nr": 1, "strava_id": "1", "data": "2026-10-17", "ora_start": "15:06"},
            "tendinte": {"distanta_km": [3.91], "puls_max": [166], "etichete_date": ["2026-10-17"], "interpretare": {}},
            "consistenta": {"saptamani": [], "zile_de_la_ultima_alergare": 0},
            "praguri_si_zone": {"zone_puls_bpm": {"Z2": [117, 137]}, "sesiuni_cu_puls_max_sub_155": 0},
            "urmatoarea_sesiune": {"cod": "S1.9", "nota": "pastreaza"}, "widget_hint": {},
        }
        (rad / "widget/progres.json").write_text(text_json(progres))
        # Spinning: 200 s în Z2 cu rezistență 30, 100 s în Z3 cu rezistență 40, 50 s în Z2 la 40 rpm (ignorate)
        es = [[i, 125, 85, 30] for i in range(200)] + [[i, 145, 88, 40] for i in range(100)] + \
             [[i, 125, 40, 10] for i in range(50)]
        runs = [
            _rezultat_sintetic("2026-10-20T18-00-00_alergare", "alergare", "2026-10-20T18:00:00+03:00", "S1.9", 160, []),
            _rezultat_sintetic("2026-10-21T19-00-00_spinning", "spinning", "2026-10-21T19:00:00+03:00", "SP1.1", None, es),
        ]
        for o in runs:
            (rad / "rezulate/sesiuni/2026/10" / (o["id"] + ".json")).write_text(text_json(o))

        erori, sch = proceseaza(rad, acum="2026-10-21T20:00:00+03:00", silentios=True)
        assert not erori, erori
        assert len(sch) == 3, sch
        p = citeste(rad / "widget/progres.json")
        assert p["schema_version"] == 2 and p["generat_de"] == "proceseaza.py"
        assert p["progres_catre_10km"]["cel_mai_lung_bloc_continuu_s"] == 160
        assert p["progres_catre_10km"]["distanta_echivalenta_m"] == 344, p["progres_catre_10km"]
        assert p["progres_catre_10km"]["procent_headline"] == 3.4
        assert p["jaloane"][0]["progres_pct"] == 10.7 and p["jaloane"][3]["progres_pct"] == 3.4
        assert p["tendinte"]["etichete_date"] == ["2026-10-17", "2026-10-20"]
        assert p["tendinte"]["sursa"] == ["strava", "aplicatie"]
        assert p["tendinte"]["puls_max"] == [166, 153]
        assert p["tendinte"]["cel_mai_rapid_km_s"] == [None, 590]
        assert p["totaluri"]["alergari"] == 2 and p["totaluri"]["distanta_totala_km"] == 7.86
        assert p["ultima_sesiune"]["rezultat_id"] == "2026-10-20T18-00-00_alergare"
        assert p["ultima_sesiune"]["plan"]["alergare_planificata_s"] == 660
        assert p["ultima_sesiune"]["realizat_fata_de_plan"]["blocuri_complete_pct"] == 25.0
        assert p["consistenta"]["pauze_intre_alergari"][-1]["zile"] == 3
        sp = p["spinning"]
        assert sp["totaluri"]["sesiuni"] == 1 and sp["sesiuni"][0]["rezistenta_z2"] == 30, sp
        assert sp["rezistenta_z2_calibrata"] == 30
        assert sp["totaluri"]["echivalent_alergare_min"] == 2.5   # 250 s în Z2 × 0,6
        assert p["volum_aerob_combinat"]["spinning_s"] == 2400
        assert p["sesiuni_aplicatie"] == 2
        # Ambele sesiuni sunt realizate: nu mai există o „următoare” planificată, vechiul obiect rămâne
        assert p["urmatoarea_sesiune"]["nota"] == "pastreaza"
        ip = citeste(rad / "planuri/index.json")
        assert [e["status"] for e in ip["sesiuni"]] == ["realizat", "realizat"]
        assert ip["urmatoarea"] == {"alergare": None, "spinning": None}
        ir = citeste(rad / "rezulate/index.json")
        assert [e["analizat"] for e in ir["sesiuni"]] == [False, False]

        # Idempotent: a doua rulare nu schimbă nimic (nici timpul)
        erori, sch = proceseaza(rad, acum="2026-10-22T08:00:00+03:00", silentios=True)
        assert not erori and not sch, (erori, sch)

        # O analiză nouă => doar indexul rezultatelor se schimbă
        (rad / "rezulate/analize/2026-10-20T18-00-00_alergare.json").write_text(text_json({"verdict": "bine"}))
        (rad / "rezulate/analize/2026-10-20T18-00-00_alergare.md").write_text("# ok\n")
        erori, sch = proceseaza(rad, acum="2026-10-22T09:00:00+03:00", silentios=True)
        assert not erori and len(sch) == 1 and sch[0].endswith("rezulate/index.json"), sch
        ir = citeste(rad / "rezulate/index.json")
        assert ir["sesiuni"][0]["analizat"] is True and ir["sesiuni"][0]["verdict"] == "bine"

        # Validatorul de plan prinde erorile
        e, _ = valideaza_plan({"schema_version": 2, "id": "X", "activitate": "alergare", "titlu": "x",
                               "pasi": [{"tip": "mers", "nume": "a · b", "durata": 0, "tinte": {"puls": [1]}}]})
        assert len(e) == 2, e
    print("self-test OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Procesare deterministă Train Live (rezulate, planuri, widget).")
    ap.add_argument("--radacina", default="date",
                    help="director cu worktree-urile planuri/, rezulate/, widget/ (implicit: date)")
    ap.add_argument("--check", action="store_true", help="doar validează și arată ce s-ar schimba")
    ap.add_argument("--self-test", action="store_true", help="rulează testul pe date sintetice")
    ap.add_argument("--acum", help="momentul curent ISO (pentru teste)")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not Path(a.radacina).is_dir():
        print("EROARE: nu există directorul %s" % a.radacina, file=sys.stderr)
        return 2
    erori, _ = proceseaza(a.radacina, check=a.check, acum=a.acum)
    return 1 if erori else 0


if __name__ == "__main__":
    sys.exit(main())

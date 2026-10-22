#!/usr/bin/env python3
"""Validează un meniu săptămânal `nutritie.meniu` (ramura `nutritie` din repo-ul sport).

Utilizare:  python3 valideaza.py meniuri/2026-10-26.json [--setari setari.json]
Cod de ieșire 0 = fără erori (avertismentele nu opresc), 1 = erori.
"""
import json
import sys
import unicodedata
from datetime import date, timedelta

MESE = ["mic_dejun", "gustare_dimineata", "pranz", "gustare_dupamasa"]
LIMITA_SODIU_ZI = 1000   # mg, doar pentru cele 4 mese din aplicație (ținta zilei întregi ≈ 2000 mg)
LIMITA_SODIU_MASA = 500  # mg pe o masă principală
KCAL_ZI = (900, 1500)    # interval orientativ pentru cele 4 mese din aplicație
MAGAZINE_OK = {"lidl", "kaufland", "acasă", "acasa"}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    setari = None
    if "--setari" in argv:
        setari = argv[argv.index("--setari") + 1]
    err, warn = [], []
    m = json.load(open(path, encoding="utf-8"))

    if m.get("schema") != "nutritie.meniu" or m.get("v") != 1:
        err.append("schema trebuie să fie nutritie.meniu, v=1")
    try:
        luni = date.fromisoformat(m.get("saptamana", ""))
        if luni.weekday() != 0:
            err.append("`saptamana` trebuie să fie data de LUNI")
    except ValueError:
        err.append("`saptamana` lipsește sau nu e dată ISO")
        luni = None

    excluse = []
    if setari:
        try:
            excluse = [norm(x) for x in json.load(open(setari, encoding="utf-8")).get("excluse", [])]
        except Exception as e:  # noqa: BLE001
            warn.append("nu s-a putut citi setari.json: %s" % e)

    zile = m.get("zile", [])
    if len(zile) != 5:
        err.append("trebuie exact 5 zile (luni–vineri), sunt %d" % len(zile))
    for i, z in enumerate(zile):
        if luni is not None and z.get("data") != str(luni + timedelta(days=i)):
            err.append("ziua %d are data %s, se așteaptă %s" % (i + 1, z.get("data"), luni + timedelta(days=i)))
        kcal = sodiu = 0
        for k in MESE:
            masa = z.get(k)
            if not masa or not masa.get("nume"):
                err.append("%s: lipsește %s" % (z.get("data"), k))
                continue
            if not masa.get("ingrediente"):
                err.append("%s %s: fără ingrediente" % (z.get("data"), k))
            kcal += masa.get("kcal") or 0
            sodiu += masa.get("sodiu_mg") or 0
            if (masa.get("sodiu_mg") or 0) > LIMITA_SODIU_MASA:
                warn.append("%s %s: sodiu %s mg (peste %d)" % (z.get("data"), k, masa.get("sodiu_mg"), LIMITA_SODIU_MASA))
            text = norm(masa.get("nume", "") + " " + " ".join(masa.get("ingrediente", [])))
            for x in excluse:
                if x and x in text:
                    err.append("%s %s: conține «%s» din lista de excluse" % (z.get("data"), k, x))
        if not (z.get("ceai") or {}).get("nume"):
            err.append("%s: lipsește ceaiul" % z.get("data"))
        if sodiu > LIMITA_SODIU_ZI:
            warn.append("%s: sodiu total %d mg (limită %d)" % (z.get("data"), sodiu, LIMITA_SODIU_ZI))
        if not (KCAL_ZI[0] <= kcal <= KCAL_ZI[1]):
            warn.append("%s: %d kcal în afara intervalului %s" % (z.get("data"), kcal, KCAL_ZI))

    nume_prânzuri = [norm((z.get("pranz") or {}).get("nume", "")) for z in zile]
    if len(set(nume_prânzuri)) < len(nume_prânzuri):
        warn.append("sunt prânzuri repetate în aceeași săptămână")
    for s in m.get("cumparaturi", []):
        if norm(s.get("magazin", "")) not in {norm(x) for x in MAGAZINE_OK}:
            warn.append("magazin necunoscut la «%s»: %s (folosește Lidl, Kaufland sau Acasă)" % (s.get("produs"), s.get("magazin")))

    for w in warn:
        print("AVERTISMENT:", w)
    for e in err:
        print("EROARE:", e)
    print("%d erori, %d avertismente" % (len(err), len(warn)))
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

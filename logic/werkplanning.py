"""
Werkplanning voor de komende dagen (tuin 3): welke bespuitingen, Florgib en plantwerk eraan komen, volgens de
werkwijze van de kwekerij. Alleen rekenwerk; werkplanning.py haalt de gegevens op en zet het klaar voor de
Takenlijst. Tests in tests/test_werkplanning.py.

Regels (opgegeven door de teler, oktober 2026):
- CXDS = ConSecta + X-Tend + D-6 Force + SilicaPower, elke 1,5 week op ieder vak, als blok per planting:
  de lopende vakken van één plantweek, in aaneengesloten reeksen vakken. De eerste CXDS ± 2 weken na het
  planten. Het blok komt op de dag die gemiddeld het best uitkomt voor de vakken erin.
- Florgib altijd samen met de CXDS, maar niet in het blok: een vak met de Florgib in de buurt van het blok
  (MARGE_FLORGIB: 3 dagen ervoor t/m 5 dagen erna) krijgt zijn CXDS apart op de Florgibdag.
- Een geregistreerde Florgib telt ook als CXDS (die gaan altijd samen), ook als de bespuiting nog niet uit
  Agro4all binnen is.
- Vakken in de oogst (al emmers, of de prognose-oogst binnen een week na het blok) krijgen geen CXDS meer.
- Vak 1 is een waterteelt (proef) en krijgt geen CXDS (GEEN_CXDS).
- Op zondag wordt niet gespoten: een blok dat op zondag valt, gaat naar maandag.
- Planten: op de plantdag ook Rizolex, zodra het vak volgepoot is. Een concept van eerder in de week dat nog
  niet gestart is, komt op vandaag ("loopt achter").
- Inwateren van de nieuwe vakken van een week (al geplant of nog te planten): op vrijdag (donderdag mag ook).
"""
from datetime import date, timedelta

CXDS_MIDDELEN = ("consecta", "x-tend", "d-6", "silicapower")
INTERVAL = 10.5                     # 1,5 week
EERSTE_CXDS = 14                    # dagen na het planten
MARGE_FLORGIB = (3, 5)              # Florgib 3 d vóór t/m 5 d na het blok: niet in het blok (CXDS met de Florgib)
MARGE_OOGST = 7                     # prognose-oogst binnen zoveel dagen na het blok: geen CXDS meer
MIN_SINDS_CXDS = 7                  # een vak met CXDS korter dan zoveel dagen vóór het blok gaat niet mee
GEEN_CXDS = {1}                     # vak 1: waterteelt (proef), geen CXDS
INWATER_DAG = 4                     # vrijdag (maandag = 0)
DAG = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def is_cxds(middel):
    return any(m in (middel or "").lower() for m in CXDS_MIDDELEN)


def laatste_cxds(behandelingen):
    """{vak: laatste dag met een CXDS-middel} uit behandelingregels (vaknummer, datum, middel)."""
    uit = {}
    for b in behandelingen:
        if is_cxds(b.get("middel") or b.get("naam")):
            vak, dag = int(b["vaknummer"]), b["datum"]
            uit[vak] = max(dag, uit.get(vak, dag))
    return uit


def _reeksen(vakken):
    """Aaneengesloten reeksen vaknummers: [2, 3, 4, 7, 8] → [[2, 3, 4], [7, 8]]."""
    uit = []
    for v in sorted(vakken):
        if uit and v == uit[-1][-1] + 1:
            uit[-1].append(v)
        else:
            uit.append([v])
    return uit


def _naam(vakken):
    vakken = sorted(vakken)
    if len(vakken) == 1:
        return f"vak {vakken[0]}"
    if vakken == list(range(vakken[0], vakken[-1] + 1)):
        return f"vak {vakken[0]}–{vakken[-1]}"
    return "vak " + ", ".join(str(v) for v in vakken)


def taken(teelten, cxds, concepten, van, dagen=7, geplant=()):
    """
    [{datum, soort, vakken, titel, toelichting}] voor van t/m van + dagen − 1, op datum.
    teelten: lopende teelten van de tuin als dicts met vak, start (plantdatum), florgib (geregistreerd of None),
             florgib_verwacht, prognose (oogst), emmers;
    cxds: {vak: laatste CXDS}; concepten: [(vak, plantdatum)] (concepten en bevestigde teelten die nog
    geplant moeten worden); geplant: [(vak, plantdatum)] van de vakken die deze week al geplant zijn (alleen voor
    het inwateren).
    Wat al achter loopt (Florgib of CXDS vóór `van`) komt op `van`, met "achter" in de toelichting.
    """
    tot = van + timedelta(days=dagen - 1)
    uit = []

    def taak(dag, soort, vakken, titel, toelichting):
        if van <= dag <= tot:
            uit.append({"datum": dag, "soort": soort, "vakken": sorted(vakken), "titel": titel,
                        "toelichting": toelichting})

    # Florgib + CXDS, per vak op de (verwachte) Florgibdag.
    florgib_dag = {}
    for t in teelten:
        if t["florgib"] or not t.get("florgib_verwacht"):
            continue
        dag = t["florgib_verwacht"]
        achter = dag < van
        florgib_dag[t["vak"]] = max(dag, van)
        taak(max(dag, van), "florgib", [t["vak"]], f"Florgib + CXDS vak {t['vak']}",
             f"Tuin 3 · Florgib verwacht {DAG[dag.weekday()]} {dag:%d-%m}" + (", loopt achter" if achter else "")
             + "; CXDS apart, niet in een blok")

    # De laatste CXDS per vak: uit de behandelingen, of de geregistreerde Florgib (altijd met CXDS).
    cxds = dict(cxds)
    for t in teelten:
        if t["florgib"] and (t["vak"] not in cxds or t["florgib"] > cxds[t["vak"]]):
            cxds[t["vak"]] = t["florgib"]

    # CXDS-blokken per planting (plantweek), in aaneengesloten reeksen vakken.
    per_week = {}
    for t in teelten:
        if t["start"] and t["start"] <= van and t["vak"] not in GEEN_CXDS:
            per_week.setdefault(t["start"].isocalendar()[:2], []).append(t)
    for (jaar, week), groep in sorted(per_week.items()):
        per_vak = {t["vak"]: t for t in groep}
        for reeks in _reeksen(per_vak):
            due = {}
            for vak in reeks:
                t = per_vak[vak]
                vorige = cxds.get(vak)
                if vorige and vorige >= t["start"]:
                    due[vak] = vorige + timedelta(days=INTERVAL)
                else:
                    due[vak] = t["start"] + timedelta(days=EERSTE_CXDS)
            def blokdag(vakken):
                gemiddeld = date.fromordinal(round(sum(due[v].toordinal() for v in vakken) / len(vakken)))
                dag = max(gemiddeld, van)
                return gemiddeld, dag + timedelta(days=1) if dag.weekday() == 6 else dag

            def mag_mee(v, dag):
                prognose, vorige = per_vak[v].get("prognose"), cxds.get(v)
                met_florgib = v in florgib_dag and -MARGE_FLORGIB[0] <= (florgib_dag[v] - dag).days <= MARGE_FLORGIB[1]
                in_oogst = per_vak[v].get("emmers") or (prognose and prognose <= dag + timedelta(days=MARGE_OOGST))
                net_gehad = vorige and (dag - vorige).days < MIN_SINDS_CXDS
                return not (met_florgib or in_oogst or net_gehad)

            # Eerst de dag voor de hele reeks, dan zonder de vakken die niet meegaan opnieuw.
            gemiddeld, dag = blokdag(reeks)
            blok = [v for v in reeks if mag_mee(v, dag)]
            if not blok:
                continue
            if len(blok) < len(reeks):
                gemiddeld, dag = blokdag(blok)
                blok = [v for v in blok if mag_mee(v, dag)]
                if not blok:
                    continue
            laatste = [cxds[v] for v in blok if cxds.get(v) and cxds[v] >= per_vak[v]["start"]]
            toelichting = f"Tuin 3 · plantweek {week}"
            if laatste:
                eerste, laatst = min(laatste), max(laatste)
                toelichting += f"; vorige CXDS {eerste:%d-%m}" + (f"–{laatst:%d-%m}" if laatst != eerste else "")
            else:
                toelichting += "; eerste CXDS na het planten"
            if gemiddeld < van:
                toelichting += ", loopt achter"
            taak(dag, "cxds", blok, f"CXDS-blok {_naam(blok)}", toelichting)

    # Planten + Rizolex, per dag (wat nog niet gebeurd is: vandaag); inwateren op vrijdag van die week.
    per_dag = {}
    for vak, dag in concepten:
        per_dag.setdefault(dag, []).append(vak)
    for dag, vakken in sorted(per_dag.items()):
        taak(max(dag, van), "planten", vakken, f"Planten {_naam(vakken)} + Rizolex",
             "Tuin 3 · Rizolex spuiten zodra het vak volgepoot is"
             + (f"; gepland {DAG[dag.weekday()]} {dag:%d-%m}, loopt achter" if dag < van else ""))
    for vak, dag in geplant:
        per_dag.setdefault(dag, []).append(vak)
    per_week_plant = {}
    for dag, vakken in per_dag.items():
        zondag = dag - timedelta(days=(dag.weekday() + 1) % 7)
        per_week_plant.setdefault(zondag, []).extend(vakken)
    for zondag, vakken in sorted(per_week_plant.items()):
        vrijdag = zondag + timedelta(days=(INWATER_DAG - 6) % 7)
        taak(vrijdag, "inwateren", vakken, f"Inwateren nieuwe vakken {_naam(vakken)[4:]}",
             "Tuin 3 · donderdag of vrijdag, na de laatste planting van de week")
    return sorted(uit, key=lambda t: (t["datum"], ("florgib", "cxds", "planten", "inwateren").index(t["soort"]),
                                      t["vakken"]))

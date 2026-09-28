"""
Hoe staat elk teeltvak ervoor: verwachte lengte, prognose-oogst, kleur en
aandachtspunten voor het scherm "Nu". Alleen rekenwerk, geen Streamlit en geen
database: de app geeft de teelten (als dicts) en de plan-oogstfunctie mee, en
tests/test_vakstatus.py test dit los.

Verwachte lengte
    Een lopende teelt heeft één meting: de Florgib-lengte halverwege
    (lengte_half op datum_half). Die wordt vergeleken met afgeronde teelten
    ("referenties") op dezelfde leeftijd. Per referentie een lijn door
    (0 dagen, 0 cm), (leeftijd bij halverwege, lengte_half) en (teeltduur,
    lengte_eind); verwacht = de mediaan van die lijnen op de leeftijd van de
    meting, de spreiding P25-P75 wordt de band in de groeigrafiek.

Referentieladder
    Eerst plantweek ±REF_WEEKVENSTER in de eigen tuin, dan ±REF_WEEKVENSTER in
    beide tuinen, dan ±REF_WEEKVENSTER_BREED in de eigen tuin (in het blok met
    "≈"). Alle jaren tellen mee. Minder dan MIN_REFERENTIES → grijs.

Prognose-oogst
    Plan = startdatum + teeltduur uit de teeltduur-tabel. Op de mediaancurve
    staat op welke leeftijd de referenties de gemeten lengte bereikten; het
    verschil met de werkelijke leeftijd is de achterstand (+) of voorsprong
    (−) in dagen. Prognose = plan + die dagen, begrensd op ±MAX_PROGNOSE_DAGEN.
"""
from datetime import date, datetime, timedelta

from config import (  # noqa: F401  (drempels ook bereikbaar als vs.NAAM voor het scherm)
    FLORGIB_ACHTERSTAND_DAGEN, LENGTE_ORANJE_PCT, LENGTE_ROOD_PCT, MELDING_C_DREMPEL, MELDING_GRENS_MARGE_DAGEN,
    MAX_AANDACHTSPUNTEN, MAX_PROGNOSE_DAGEN, MIN_REFERENTIES, OOGST_ROOD_DAGEN, REF_WEEKVENSTER,
    REF_WEEKVENSTER_BREED, STEK_CIJFER_GRENS, STEK_GOED, STEK_RECENT_DAGEN, WATER_DROOG_DAGEN,
)
from utils.format import fmt_kort, fmt_verschil

# Volgorde = ernst in de lijst aandachtspunten (laag getal eerst).
ERNST = {"correctie": 1, "florgib": 2, "oogst": 3, "water": 4, "data": 5, "stek": 6}

REFERENTIE_NIVEAUS = {
    "eigen": f"plantweek ±{REF_WEEKVENSTER}, eigen tuin",
    "beide": f"plantweek ±{REF_WEEKVENSTER}, beide tuinen",
    "breed": f"plantweek ±{REF_WEEKVENSTER_BREED}, eigen tuin",
}


def als_datum(waarde):
    """'2026-09-26' of date -> date; None blijft None."""
    if waarde is None or waarde != waarde:  # None of NaN
        return None
    if isinstance(waarde, datetime):
        return waarde.date()
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def _getal(waarde):
    """Getal of None (ook voor NaN)."""
    if waarde is None:
        return None
    try:
        waarde = float(waarde)
    except (TypeError, ValueError):
        return None
    return None if waarde != waarde else waarde


def plantweek(datum):
    return als_datum(datum).isocalendar()[1]


def weekafstand(week_a, week_b):
    """Afstand tussen twee ISO-weken over de jaargrens heen (week 52 en 1 liggen 1 uit elkaar)."""
    verschil = abs(week_a - week_b)
    return min(verschil, 52 - verschil)


def is_referentie(teelt):
    """Afgerond, met Florgib-meting en oogstlengte, en de meting vóór de oogst."""
    start, half, oogst = (als_datum(teelt.get(k)) for k in ("datum_teelt_start", "datum_half", "datum_oogst"))
    if not (start and half and oogst):
        return False
    if not (_getal(teelt.get("lengte_half")) and _getal(teelt.get("lengte_eind"))):
        return False
    return 0 < (half - start).days < (oogst - start).days


def referentiepunten(ref):
    """[(0, 0), (leeftijd halverwege, lengte_half), (teeltduur, lengte_eind)] van een referentie."""
    start = als_datum(ref["datum_teelt_start"])
    return [
        (0, 0.0),
        ((als_datum(ref["datum_half"]) - start).days, _getal(ref["lengte_half"])),
        ((als_datum(ref["datum_oogst"]) - start).days, _getal(ref["lengte_eind"])),
    ]


def interpoleer(punten, leeftijd):
    """Lineair tussen de punten; na het laatste punt de eindlengte, ervoor 0."""
    if leeftijd <= punten[0][0]:
        return punten[0][1]
    for (x0, y0), (x1, y1) in zip(punten, punten[1:]):
        if leeftijd <= x1:
            return y1 if x1 == x0 else y0 + (y1 - y0) * (leeftijd - x0) / (x1 - x0)
    return punten[-1][1]


def kwantiel(waarden, q):
    """Kwantiel met lineaire interpolatie (zoals numpy's standaard), q tussen 0 en 1."""
    rij = sorted(waarden)
    if not rij:
        return None
    positie = (len(rij) - 1) * q
    onder = int(positie)
    boven = min(onder + 1, len(rij) - 1)
    return rij[onder] + (rij[boven] - rij[onder]) * (positie - onder)


def kies_referenties(teelt, kandidaten):
    """
    Referentieteelten voor `teelt` volgens de ladder. Geeft (lijst, niveau)
    met niveau "eigen", "beide" of "breed", of ([], None) als geen trede er
    minstens MIN_REFERENTIES oplevert. De teelt zelf doet nooit mee.
    """
    week = plantweek(teelt["datum_teelt_start"])
    tuin = teelt.get("tuin_id")
    refs = [k for k in kandidaten if k.get("id") != teelt.get("id") and is_referentie(k)]
    for niveau, venster, eigen_tuin in (
        ("eigen", REF_WEEKVENSTER, True),
        ("beide", REF_WEEKVENSTER, False),
        ("breed", REF_WEEKVENSTER_BREED, True),
    ):
        gekozen = [
            k for k in refs
            if weekafstand(plantweek(k["datum_teelt_start"]), week) <= venster
            and (not eigen_tuin or k.get("tuin_id") == tuin)
        ]
        if len(gekozen) >= MIN_REFERENTIES:
            return gekozen, niveau
    return [], None


def verwachte_lengte(refs, leeftijd):
    """(mediaan, P25, P75) van de referentielijnen op `leeftijd` dagen."""
    waarden = [interpoleer(referentiepunten(r), leeftijd) for r in refs]
    return kwantiel(waarden, 0.5), kwantiel(waarden, 0.25), kwantiel(waarden, 0.75)


def groeicurve(refs, tot_leeftijd=None):
    """Per dag (leeftijd, P25, mediaan, P75) van 0 tot de langste referentie (of tot_leeftijd)."""
    einde = tot_leeftijd or max(referentiepunten(r)[-1][0] for r in refs)
    curve = []
    for leeftijd in range(0, einde + 1):
        mediaan, p25, p75 = verwachte_lengte(refs, leeftijd)
        curve.append((leeftijd, p25, mediaan, p75))
    return curve


def leeftijd_bij_lengte(refs, lengte):
    """Eerste leeftijd waarop de mediaancurve `lengte` haalt, of None als nooit."""
    for leeftijd, _, mediaan, _ in groeicurve(refs):
        if mediaan >= lengte:
            return leeftijd
    return None


def bepaal_kleur(afwijking_pct, prognose_dagen):
    """
    Kleur van een vak met een lopende teelt. afwijking_pct None (geen meting of
    te weinig referenties) → grijs. Rood bij meer dan LENGTE_ROOD_PCT achter of
    een prognose meer dan OOGST_ROOD_DAGEN na plan; oranje buiten
    ±LENGTE_ORANJE_PCT (ook ruim vóór); anders groen.
    """
    if afwijking_pct is None:
        return "grijs"
    if afwijking_pct <= -LENGTE_ROOD_PCT or (prognose_dagen is not None and prognose_dagen > OOGST_ROOD_DAGEN):
        return "rood"
    if abs(afwijking_pct) > LENGTE_ORANJE_PCT:
        return "oranje"
    return "groen"


def beoordeel_teelt(teelt, kandidaten, vandaag, plan_oogst):
    """
    Status van één lopende teelt. `plan_oogst(start)` geeft (duur_weken,
    oogstdatum) uit de teeltduur-tabel. Geeft een dict met leeftijd, meting,
    verwachting, afwijking, plan- en prognose-oogst, referenties en kleur.
    """
    start = als_datum(teelt["datum_teelt_start"])
    _, plan = plan_oogst(start)
    status = {
        "teelt": teelt, "start": start, "leeftijd": (vandaag - start).days, "plantweek": plantweek(start),
        "plan": plan, "prognose": None, "prognose_dagen": None,
        "meting": None, "meet_leeftijd": None, "verwacht": None, "p25": None, "p75": None,
        "afwijking_pct": None, "refs": [], "niveau": None, "florgib": None, "florgib_fout": None,
    }
    lengte = _getal(teelt.get("lengte_half"))
    half = als_datum(teelt.get("datum_half"))
    if half and half <= start:
        # Een Florgib op of vóór de plantdatum kan niet: telt niet mee, wel een melding.
        status["florgib_fout"] = half
    elif half:
        status["florgib"] = half
        if lengte:
            status["meting"], status["meet_leeftijd"] = lengte, (half - start).days
    refs, niveau = kies_referenties(teelt, kandidaten)
    status["refs"], status["niveau"] = refs, niveau

    if status["meting"] is not None and refs:
        verwacht, p25, p75 = verwachte_lengte(refs, status["meet_leeftijd"])
        status.update(verwacht=verwacht, p25=p25, p75=p75)
        if verwacht:
            status["afwijking_pct"] = (lengte / verwacht - 1) * 100
        ref_leeftijd = leeftijd_bij_lengte(refs, lengte)
        if ref_leeftijd is not None and plan:
            dagen = max(-MAX_PROGNOSE_DAGEN, min(MAX_PROGNOSE_DAGEN, status["meet_leeftijd"] - ref_leeftijd))
            status["prognose_dagen"] = dagen
            status["prognose"] = plan + timedelta(days=dagen)
    status["kleur"] = bepaal_kleur(status["afwijking_pct"], status["prognose_dagen"])
    return status


# --- AANDACHTSPUNTEN ---

def dagen_zonder_water(start, laatste_gift, horizon):
    """
    Dagen sinds de laatste gift (of sinds planten als er nog geen gift was),
    geteld tot `horizon`: de laatste dag waarop er voor deze tuin überhaupt
    watergift binnen is. Zo geeft een Priva-achterstand geen meldingen voor
    alle vakken tegelijk.
    """
    if horizon is None:
        return None
    vanaf = max(d for d in (als_datum(start), als_datum(laatste_gift)) if d)
    return (horizon - vanaf).days


def vakken_tekst(vakken):
    """[10, 11, 12, 13, 14, 17] → "Vak 10–14 en 17"; aaneengesloten reeksen als bereik."""
    vakken = sorted(set(vakken))
    reeksen = []
    for vak in vakken:
        if reeksen and vak == reeksen[-1][1] + 1:
            reeksen[-1][1] = vak
        else:
            reeksen.append([vak, vak])
    delen = []
    for a, b in reeksen:
        delen += [f"{a}–{b}"] if b > a + 1 else ([str(a), str(b)] if b == a + 1 else [str(a)])
    return "Vak " + ", ".join(delen[:-1]) + (" en " if len(delen) > 1 else "") + delen[-1]


def watergift_meldingen(statussen, water_laatste, horizon, vandaag):
    """
    Meldingen over ontbrekende watergift. Alleen voor teelten vóór de Florgib:
    daarna wordt er bewust geen water meer gegeven. Vakken met dezelfde
    laatste gift worden samengevoegd ("Vak 10–14: geen watergift sinds 01-09").
    Loopt de import zelf WATER_DROOG_DAGEN of meer achter, of missen alle
    vakken tegelijk water, dan één melding over de import in plaats van per vak.
    """
    kandidaten = [s for s in statussen if s["florgib"] is None and s["leeftijd"] >= WATER_DROOG_DAGEN]
    if not kandidaten:
        return []
    import_melding = {
        "ernst": ERNST["water"], "gewicht": 0, "soort": "import", "sleutel": None,
        "tekst": "Watergift-import loopt achter (laatste data "
                 + (f"{horizon:%d-%m})" if horizon else "onbekend)"),
    }
    if horizon is None or (vandaag - horizon).days >= WATER_DROOG_DAGEN:
        return [import_melding]
    droog = {}
    for s in kandidaten:
        vak = s["teelt"]["vaknummer"]
        dagen = dagen_zonder_water(s["start"], water_laatste.get(vak), horizon)
        if dagen is not None and dagen >= WATER_DROOG_DAGEN:
            sinds = max(d for d in (s["start"], als_datum(water_laatste.get(vak))) if d)
            droog.setdefault(sinds, []).append(vak)
    if len(kandidaten) > 1 and sum(len(v) for v in droog.values()) == len(kandidaten):
        return [import_melding]
    return [
        {"ernst": ERNST["water"], "gewicht": -(horizon - sinds).days, "soort": "vak", "sleutel": min(vakken),
         "tekst": f"{vakken_tekst(vakken)}: geen watergift sinds {sinds:%d-%m}"}
        for sinds, vakken in sorted(droog.items())
    ]


def stek_afwijkingen(teelt):
    """Lijst (veld, waarde) van stekkenmerken die niet goed zijn."""
    uit = []
    for veld in ("wortel", "plantmaat", "uniformiteit"):
        waarde = teelt.get(veld)
        if waarde and waarde == waarde and waarde not in STEK_GOED:
            uit.append((veld, waarde))
    cijfer = _getal(teelt.get("beoordeling"))
    if cijfer is not None and cijfer <= STEK_CIJFER_GRENS:
        uit.append(("cijfer", fmt_kort(cijfer)))
    return uit


def _c_tekst(c):
    return fmt_verschil(c, 1, "°C")


def aandachtspunten(statussen, water_laatste, water_horizon, vandaag):
    """
    Maximaal MAX_AANDACHTSPUNTEN meldingen, belangrijkste eerst. Elke melding
    is een dict met ernst, tekst, soort ("vak"/"import") en sleutel
    (vaknummer of None).

    - statussen: beoordeel_teelt-resultaten van de lopende teelten van één
      tuin, met onder "stook" de uitkomst van TeeltPrognose.beoordeel (of None)
    - water_laatste: {vaknummer: datum laatste gift}; water_horizon: laatste
      dag met watergift in deze tuin

    Volgorde: correctie c (grootste |c| eerst, vanaf MELDING_C_DREMPEL; op de grens
    alleen als de oogst dan meer dan MELDING_GRENS_MARGE_DAGEN van plan ligt),
    oogstrijp zonder oogst, Florgib-achterstand, watergift, datafouten, stek.
    Vakken met dezelfde uitkomst (zelfde afdeling en plantdag) worden één regel.
    """
    punten = []
    correctie, rijp, florgib = {}, {}, {}
    for s in statussen:
        vak, st = s["teelt"]["vaknummer"], s.get("stook")
        # Op de grens en toch maar een paar dagen van plan: binnen de onzekerheid van het model.
        klein = (st and st["begrensd"] and st["prognose_bij_c"] and s["plan"]
                 and abs((st["prognose_bij_c"] - s["plan"]).days) <= MELDING_GRENS_MARGE_DAGEN)
        if st and st["c"] is not None and abs(st["c"]) >= MELDING_C_DREMPEL and not klein:
            sleutel = (s["teelt"]["afdeling"], round(st["c"], 1), st["begrensd"], s["plan"], st["prognose_bij_c"])
            correctie.setdefault(sleutel, []).append(vak)
        if st and st["oogstrijp"] and not _getal(s["teelt"].get("emmers")):
            rijp.setdefault(s["plan"], []).append(vak)
        verwacht = st and st["florgib_verwacht"]
        if s["florgib"] is None and verwacht and (vandaag - verwacht).days > FLORGIB_ACHTERSTAND_DAGEN:
            florgib.setdefault(verwacht, []).append(vak)
        if s.get("florgib_fout"):
            punten.append({"ernst": ERNST["data"], "gewicht": 0, "soort": "vak", "sleutel": vak,
                           "tekst": f"Vak {vak}: Florgib-datum {s['florgib_fout']:%d-%m} ligt vóór het planten "
                                    f"({s['start']:%d-%m}); controleer de registratie"})

    for (_, c, begrensd, plan, prognose), vakken in correctie.items():
        if begrensd and c > 0:
            tekst = f"haalt plan {plan:%d-%m} niet, ook niet bij {_c_tekst(c)} (prog. {prognose:%d-%m})"
        elif begrensd:
            tekst = f"te vroeg, ook bij {_c_tekst(c)} (prog. {prognose:%d-%m}, plan {plan:%d-%m})"
        else:
            tekst = f"{_c_tekst(c)} t.o.v. de lichtlijn voor plan {plan:%d-%m}"
        punten.append({"ernst": ERNST["correctie"], "gewicht": -abs(c), "soort": "vak", "sleutel": min(vakken),
                       "tekst": f"{vakken_tekst(vakken)}: {tekst}"})
    for plan, vakken in rijp.items():
        punten.append({"ernst": ERNST["oogst"], "gewicht": 0, "soort": "vak", "sleutel": min(vakken),
                       "tekst": f"{vakken_tekst(vakken)}: volgens het model oogstrijp"
                                + (f" (plan {plan:%d-%m})" if plan else "") + ", nog geen oogst geregistreerd"})
    for verwacht, vakken in florgib.items():
        punten.append({"ernst": ERNST["florgib"], "gewicht": -(vandaag - verwacht).days, "soort": "vak",
                       "sleutel": min(vakken),
                       "tekst": f"{vakken_tekst(vakken)}: Florgib verwacht {verwacht:%d-%m}, nog niet geregistreerd"})

    punten += watergift_meldingen(statussen, water_laatste, water_horizon, vandaag)

    # Stek: gebundeld per plantweek en kenmerk ("Stek wk 39: vak 3 en 4 wortel 'Matig'").
    stek = {}
    for s in statussen:
        if s["leeftijd"] > STEK_RECENT_DAGEN:
            continue
        for veld, waarde in stek_afwijkingen(s["teelt"]):
            stek.setdefault((s["plantweek"], veld, waarde), []).append(s["teelt"]["vaknummer"])
    for (week, veld, waarde), vakken in sorted(stek.items()):
        punten.append({"ernst": ERNST["stek"], "gewicht": -len(vakken), "soort": "vak", "sleutel": min(vakken),
                       "tekst": f"Stek wk {week}: {vakken_tekst(vakken).lower()} {veld} '{waarde}'"})

    punten.sort(key=lambda p: (p["ernst"], p["gewicht"]))
    return punten[:MAX_AANDACHTSPUNTEN]

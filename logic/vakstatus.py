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

from utils.format import fmt_getal, fmt_kort, fmt_verschil

# --- DREMPELS (hier aanpassen) ---
LENGTE_ORANJE_PCT = 5       # afwijking buiten ±5 % → oranje
LENGTE_ROOD_PCT = 10        # meer dan 10 % achter → rood (meer dan 10 % voor blijft oranje)
OOGST_ROOD_DAGEN = 5        # prognose-oogst meer dan 5 dagen na plan → rood
MIN_REFERENTIES = 3         # minder referentieteelten → grijs
REF_WEEKVENSTER = 2         # plantweek ±2 (eigen tuin, daarna beide tuinen)
REF_WEEKVENSTER_BREED = 4   # laatste stap van de ladder: ±4 in de eigen tuin ("≈")
MAX_PROGNOSE_DAGEN = 21     # prognose wijkt nooit meer dan 3 weken af van plan

KLIMAAT_TEMP_MARGE = 1.0    # °C boven (of onder) de ideale etmaaltemperatuur
KLIMAAT_VENSTER_DAGEN = 7   # kijk naar de laatste 7 dagen met klimaatdata
KLIMAAT_MIN_DAGEN = 4       # melding bij minstens 4 van die dagen buiten de marge
WATER_DROOG_DAGEN = 6       # melding bij zoveel dagen zonder geregistreerde gift
STEK_RECENT_DAGEN = 21      # stekmeldingen alleen voor teelten die korter staan
STEK_GOED = {"Goed"}        # wortel/plantmaat/uniformiteit anders → melding
STEK_CIJFER_GRENS = 6       # stekcijfer ≤ 6 → melding
MAX_AANDACHTSPUNTEN = 8

# Volgorde = ernst in de lijst aandachtspunten (laag getal eerst).
ERNST = {"rood": 1, "klimaat": 2, "water": 3, "oogst": 4, "stek": 5, "oranje": 6}

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
        "afwijking_pct": None, "refs": [], "niveau": None,
    }
    lengte = _getal(teelt.get("lengte_half"))
    half = als_datum(teelt.get("datum_half"))
    if lengte and half:
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

def klimaat_afwijking(dagen, ideaal):
    """
    `dagen`: lijst (datum, temp_24h, lichtsom) van één afdeling. Kijkt naar de
    laatste KLIMAAT_VENSTER_DAGEN dagen met data en telt hoe vaak de
    etmaaltemperatuur meer dan KLIMAAT_TEMP_MARGE boven of onder ideaal(lichtsom)
    lag. Geeft (boven, onder, aantal dagen).
    """
    bruikbaar = sorted((d for d in dagen if _getal(d[1]) is not None and _getal(d[2]) is not None),
                       key=lambda d: als_datum(d[0]))[-KLIMAAT_VENSTER_DAGEN:]
    boven = sum(1 for _, temp, licht in bruikbaar if temp - ideaal(licht) > KLIMAAT_TEMP_MARGE)
    onder = sum(1 for _, temp, licht in bruikbaar if ideaal(licht) - temp > KLIMAAT_TEMP_MARGE)
    return boven, onder, len(bruikbaar)


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


def _vakken_tekst(vakken):
    vakken = sorted(vakken)
    if len(vakken) == 1:
        return f"vak {vakken[0]}"
    return "vak " + ", ".join(str(v) for v in vakken[:-1]) + f" en {vakken[-1]}"


def aandachtspunten(statussen, klimaat_per_afdeling, water_laatste, water_horizon, vandaag, ideaal,
                    ideaal_tekst=""):
    """
    Maximaal MAX_AANDACHTSPUNTEN meldingen, ernstigste eerst. Elke melding is
    een dict met ernst, tekst, soort ("vak"/"afdeling") en sleutel (vaknummer
    of afdeling).

    - statussen: beoordeel_teelt-resultaten van de lopende teelten van één tuin
    - klimaat_per_afdeling: {afdeling: [(datum, temp_24h, lichtsom), ...]}
    - water_laatste: {vaknummer: datum laatste gift}; water_horizon: laatste
      dag met watergift in deze tuin
    """
    punten = []
    for s in statussen:
        t, vak = s["teelt"], s["teelt"]["vaknummer"]
        wk_leeftijd = f"wk {s['plantweek']}, {s['leeftijd']} d"
        ernstig_achter = s["afwijking_pct"] is not None and s["afwijking_pct"] <= -LENGTE_ROOD_PCT
        if s["kleur"] in ("rood", "oranje") and s["afwijking_pct"] is not None:
            if s["kleur"] == "oranje" or ernstig_achter:
                punten.append({
                    "ernst": ERNST["rood" if ernstig_achter else "oranje"], "gewicht": -abs(s["afwijking_pct"]),
                    "tekst": f"Vak {vak}: lengte {fmt_verschil(s['afwijking_pct'], 0, '%')} t.o.v. verwacht "
                             f"({wk_leeftijd})",
                    "soort": "vak", "sleutel": vak,
                })
        # De prognose volgt uit de lengte: staat de lengte al als rood in de
        # lijst, dan geen tweede rode regel voor hetzelfde vak.
        if not ernstig_achter and s["prognose_dagen"] is not None and s["prognose_dagen"] > OOGST_ROOD_DAGEN:
            punten.append({
                "ernst": ERNST["rood"], "gewicht": -s["prognose_dagen"],
                "tekst": f"Vak {vak}: prognose-oogst {s['prognose_dagen']} dagen na plan "
                         f"(wk {s['prognose'].isocalendar()[1]})",
                "soort": "vak", "sleutel": vak,
            })
        verwacht = s["prognose"] or s["plan"]
        if verwacht and not _getal(t.get("emmers")):
            maandag = vandaag - timedelta(days=vandaag.weekday())
            if maandag <= verwacht <= maandag + timedelta(days=6):
                punten.append({"ernst": ERNST["oogst"], "gewicht": 0, "soort": "vak", "sleutel": vak,
                               "tekst": f"Vak {vak}: oogst verwacht deze week, nog geen oogst geregistreerd"})
            elif verwacht < maandag:
                punten.append({"ernst": ERNST["oogst"], "gewicht": -(vandaag - verwacht).days,
                               "soort": "vak", "sleutel": vak,
                               "tekst": f"Vak {vak}: oogst was verwacht op {verwacht:%d-%m}, "
                                        "nog geen oogst geregistreerd"})
        droog = dagen_zonder_water(s["start"], water_laatste.get(vak), water_horizon)
        if droog is not None and droog >= WATER_DROOG_DAGEN:
            punten.append({"ernst": ERNST["water"], "gewicht": -droog, "soort": "vak", "sleutel": vak,
                           "tekst": f"Vak {vak}: {droog} dagen geen watergift geregistreerd"})

    for afdeling, dagen in sorted(klimaat_per_afdeling.items()):
        boven, onder, aantal = klimaat_afwijking(dagen, ideaal)
        for telling, richting in ((boven, "boven"), (onder, "onder")):
            if telling >= KLIMAAT_MIN_DAGEN:
                punten.append({
                    "ernst": ERNST["klimaat"], "gewicht": -telling, "soort": "afdeling", "sleutel": afdeling,
                    "tekst": f"Afd. {afdeling}: {telling} van de laatste {aantal} dagen > "
                             f"{fmt_getal(KLIMAAT_TEMP_MARGE, 0)} °C {richting} ideaal"
                             + (f" ({ideaal_tekst})" if ideaal_tekst else ""),
                })

    # Stek: gebundeld per plantweek en kenmerk ("Stek wk 39: vak 3 en 4 wortel 'Matig'").
    stek = {}
    for s in statussen:
        if s["leeftijd"] > STEK_RECENT_DAGEN:
            continue
        for veld, waarde in stek_afwijkingen(s["teelt"]):
            stek.setdefault((s["plantweek"], veld, waarde), []).append(s["teelt"]["vaknummer"])
    for (week, veld, waarde), vakken in sorted(stek.items()):
        punten.append({"ernst": ERNST["stek"], "gewicht": -len(vakken), "soort": "vak", "sleutel": min(vakken),
                       "tekst": f"Stek wk {week}: {_vakken_tekst(vakken)} {veld} '{waarde}'"})

    punten.sort(key=lambda p: (p["ernst"], p["gewicht"]))
    return punten[:MAX_AANDACHTSPUNTEN]

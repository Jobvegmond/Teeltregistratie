"""
Teeltvergelijking: alle plantingen uit één plantweek. Per teelt de
kengetallen van planten tot oogst, en per tuin (en samen) een samenvatting,
gewogen naar de m² van het vak. Alleen rekenwerk; tests in
tests/test_teeltvergelijking.py.

- Lopende teelten: oogstdatum = de prognose uit het Nu-model (gemarkeerd).
  Teeltduur en fase 2 rekenen daarmee; klimaat, input en resultaat tellen in
  de samenvatting alleen voor afgeronde teelten (een halve teelt naast een
  hele vergelijken zegt niets).
- Florgib: de datum in de app, anders die uit teelt_historie (klimaatregistratie).
- Warmte per teelt alleen als (vrijwel) elke dag van de teelt gemeten is.
- Stelen: uit de emmers, anders geplant × (1 − vastgelegde uitval); anders onbekend.
"""
from datetime import date, datetime, timedelta

from logic.lichtlijn import t_ideaal

ALLEEN_AFGEROND = {"lichtsom", "temp", "afwijking", "warmte", "water", "stelen_m2", "uitval", "lengte",
                   "gewicht", "lengte_fg", "lengtefactor"}
MET_PROGNOSE = {"fase2", "teeltduur"}
NUMERIEK = ["fase1", "fase2", "teeltduur", "lichtsom", "temp", "afwijking", "warmte", "water", "stelen_m2",
            "uitval", "lengte", "gewicht", "lengte_fg", "lengtefactor", "stek"]
STEK_MATIG = {"matig", "slecht"}
MIN_ENERGIEDEKKING = 0.9


def _d(waarde):
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, datetime):
        return waarde.date()
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def _getal(waarde):
    try:
        waarde = float(waarde)
    except (TypeError, ValueError):
        return None
    return None if waarde != waarde else waarde


def plantweek(datum):
    """(isojaar, week) van een datum."""
    jaar, week, _ = _d(datum).isocalendar()
    return jaar, week


def vorig_jaar(sleutel):
    """Dezelfde plantweek een jaar eerder; week 53 wordt week 52 als die niet bestaat."""
    jaar, week = sleutel
    return jaar - 1, min(week, date(jaar - 1, 12, 28).isocalendar()[1])


def teelt(k, m2, prognose=None, florgib_historie=None):
    """
    De kengetallen van één teelt als dict. k: een regel van get_teeltkengetallen
    aangevuld met tuin_id, datum_half en de stekvelden; m2: oppervlakte van het vak.
    """
    start, oogst = _d(k["datum_teelt_start"]), _d(k.get("datum_oogst"))
    half = _d(k.get("datum_half")) or _d(florgib_historie)
    half = half if half and half > start and (not oogst or half < oogst) else None
    eind = oogst or _d(prognose)
    lichtsom = _getal(k.get("lichtsom"))
    klimaatdagen = k.get("klimaatdagen") or 0
    licht_dag = lichtsom / klimaatdagen if lichtsom is not None and klimaatdagen else None
    temp = _getal(k.get("gem_temperatuur"))
    planten, uitval = _getal(k.get("aantal_planten")), _getal(k.get("uitval_pct"))
    stelen = _getal(k.get("stelen")) or (planten * (1 - uitval / 100) if planten and uitval is not None else None)
    lengte, lengte_fg = _getal(k.get("lengte_eind")), _getal(k.get("lengte_half"))
    warmte = _getal(k.get("warmte_mj_per_m2"))
    if warmte is not None and (k.get("energiedagen") or 0) < MIN_ENERGIEDEKKING * (k.get("looptijd_dagen") or 1):
        warmte = None
    stekvelden = [str(k.get(v) or "").strip().lower() for v in ("wortel", "plantmaat", "uniformiteit")]
    return {
        "id": k["id"], "tuin_id": int(k["tuin_id"]), "vak": int(k["vaknummer"]),
        "afdeling": int(k["afdeling"]) if _getal(k.get("afdeling")) is not None else None,
        "code": k.get("code"), "m2": m2, "afgerond": oogst is not None,
        "start": start, "florgib": half, "oogst": eind, "prognose": oogst is None and eind is not None,
        "fase1": (half - start).days if half else None,
        "fase2": (eind - half).days if eind and half else None,
        "teeltduur": (eind - start).days if eind else None,
        "lichtsom": licht_dag, "temp": temp,
        "afwijking": temp - t_ideaal(licht_dag) if temp is not None and licht_dag is not None else None,
        "warmte": warmte, "water": _getal(k.get("liters")),
        "stelen_m2": stelen / m2 if stelen and m2 else None, "uitval": uitval,
        "lengte": lengte, "gewicht": _getal(k.get("oogstgewicht")), "lengte_fg": lengte_fg,
        "lengtefactor": lengte / lengte_fg if lengte and lengte_fg else None,
        "stek": _getal(k.get("beoordeling")),
        "stek_matig": any(v in STEK_MATIG for v in stekvelden) if any(stekvelden) else None,
    }


def _bereik(datums):
    datums = sorted(d for d in datums if d)
    if not datums:
        return None
    return f"{datums[0]:%d-%m-%y}" if datums[0] == datums[-1] else f"{datums[0]:%d-%m} – {datums[-1]:%d-%m-%y}"


def samenvatting(teelten):
    """
    ({sleutel: (teller, noemer, n)}, {sleutel: tekst}, {sleutel: met prognose})
    over een groep teelten: numerieke kengetallen gewogen naar m² van het vak.
    """
    delen, prognose = {}, {}
    for sleutel in NUMERIEK:
        rijen = [t for t in teelten if t[sleutel] is not None and t["m2"]
                 and (t["afgerond"] or sleutel not in ALLEEN_AFGEROND)]
        if rijen:
            delen[sleutel] = (sum(t[sleutel] * t["m2"] for t in rijen), sum(t["m2"] for t in rijen), len(rijen))
            prognose[sleutel] = sleutel in MET_PROGNOSE and any(t["prognose"] for t in rijen)
    afgerond = sum(1 for t in teelten if t["afgerond"])
    if teelten:
        delen["aantal"] = (float(len(teelten)), 1.0, afgerond)
    stek = [t for t in teelten if t["stek_matig"] is not None]
    if stek:
        delen["stek_matig"] = (float(sum(1 for t in stek if t["stek_matig"])), 1.0, len(stek))
    tekst = {
        "plantdatum": _bereik(t["start"] for t in teelten),
        "florgib": _bereik(t["florgib"] for t in teelten),
        "oogst": _bereik(t["oogst"] for t in teelten),
    }
    prognose["oogst"] = any(t["prognose"] for t in teelten)
    return delen, {k: v for k, v in tekst.items() if v}, prognose


SOMMEN = {"aantal", "stek_matig"}


def tabelwaarden(teelten, tuinen):
    """
    Voor de vergelijkingstabel: (waarden, n, bron, markering) per kolom
    (de tuinen en "Totaal"). tuinen: [(naam, tuin_id)]. Datumbereiken zijn
    tekstwaarden; markering = kengetallen waarin een prognose zit (⏳).
    """
    groepen = {naam: [t for t in teelten if t["tuin_id"] == tuin_id] for naam, tuin_id in tuinen}
    if len(tuinen) > 1:
        groepen["Totaal"] = [t for t in teelten if t["tuin_id"] in {i for _, i in tuinen}]
    waarden, n, markering = {}, {}, {}
    for kolom, groep in groepen.items():
        delen, tekst, prognose = samenvatting(groep)
        waarden[kolom] = {s: (d[0] if s in SOMMEN else d[0] / d[1]) for s, d in delen.items()}
        waarden[kolom].update(tekst)
        n[kolom] = {s: d[2] for s, d in delen.items()}
        markering[kolom] = {s for s, p in prognose.items() if p}
    bron = {}
    for sleutel in set(waarden.get("Totaal", {})):
        bron[sleutel] = frozenset(naam for naam, _ in tuinen if waarden[naam].get(sleutel) is not None)
    return waarden, n, bron, markering


def afwijking_van_gemiddelde(teelten, sleutel):
    """{teelt_id: relatieve afwijking t.o.v. het m²-gewogen gemiddelde van de groep} voor één kengetal."""
    delen, _, _ = samenvatting(teelten)
    if sleutel not in delen or not delen[sleutel][1]:
        return {}
    gemiddeld = delen[sleutel][0] / delen[sleutel][1]
    if not gemiddeld:
        return {}
    return {t["id"]: (t[sleutel] - gemiddeld) / abs(gemiddeld)
            for t in teelten if t[sleutel] is not None and (t["afgerond"] or sleutel not in ALLEEN_AFGEROND)}


def plantweken(teelten):
    """{(isojaar, week): (aantal, afgerond)} over alle teelten."""
    uit = {}
    for t in teelten:
        sleutel = plantweek(t["start"])
        aantal, afgerond = uit.get(sleutel, (0, 0))
        uit[sleutel] = (aantal + 1, afgerond + (1 if t["afgerond"] else 0))
    return uit


def standaard_plantweek(weken):
    """De meest recente plantweek met minstens één afgeronde teelt (of de nieuwste)."""
    met_afgerond = [w for w, (_, afgerond) in weken.items() if afgerond]
    return max(met_afgerond or weken or [None])


def vorige_weken(sleutel, aantal):
    """De `aantal` plantweken t/m `sleutel`, oudste eerst."""
    maandag = date.fromisocalendar(sleutel[0], sleutel[1], 1)
    return [plantweek(maandag - timedelta(weeks=i)) for i in range(aantal - 1, -1, -1)]

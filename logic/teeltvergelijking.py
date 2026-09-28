"""
Teeltvergelijking: een teelt = alle vakken uit één plantweek. Per vak de
kengetallen van planten tot oogst, en per tuin (en samen) een samenvatting,
gewogen naar de m² van het vak. Alleen rekenwerk; tests in
tests/test_teeltvergelijking.py.

- Klimaat, water en warmte per vak komen uit de dagdata (Dagdata) over een
  venster: van planten tot de oogst, of tot gisteren als het vak nog loopt.
  Loopt de teelt nog, dan kan het venster van vorig jaar worden afgekapt op
  dezelfde teeltdag (teeltdag), zodat je hetzelfde stuk teelt vergelijkt.
- Lopende vakken tellen mee voor klimaat en input (gemarkeerd ⏳); resultaten
  die pas bij de oogst bekend zijn (stelen/m², uitval, lengte, gewicht,
  lengtefactor) alleen van afgeronde vakken.
- Oogstdatum van een lopend vak = de prognose uit het Nu-model (⏳).
- Florgib: de datum in de app, anders die uit teelt_historie (klimaatregistratie).
- Warmte per vak alleen als (vrijwel) elke dag van het venster gemeten is.
- Stelen: uit de emmers, anders geplant × (1 − vastgelegde uitval); anders onbekend.
"""
from datetime import date, datetime, timedelta

from logic.lichtlijn import t_ideaal

KLIMAAT_INPUT = {"lichtsom", "temp", "afwijking", "warmte", "water"}
ALLEEN_AFGEROND = {"stelen_m2", "uitval", "lengte", "gewicht", "lengte_fg", "lengtefactor"}
MET_PROGNOSE = {"fase2", "teeltduur"}
NUMERIEK = ["fase1", "fase2", "teeltduur", "lichtsom", "temp", "afwijking", "warmte", "water", "stelen_m2",
            "uitval", "lengte", "gewicht", "lengte_fg", "lengtefactor", "stek"]
SOMMEN = {"aantal", "stek_matig"}
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


class Dagdata:
    """
    Klimaat, water en warmte per dag, geïndexeerd voor snelle vensters per vak.
    - klimaat: DataFrame tuin_id, afdeling, datum, temp_24h, lichtsom
    - water: DataFrame tuin_id, vaknummer, datum, liter_per_m2
    - warmte: {tuin_id: {"jjjj-mm-dd": MJ per bezette m²}} (database.warmte_per_bezette_m2)
    """

    def __init__(self, klimaat, water, warmte):
        self.klimaat = {}
        for r in klimaat.itertuples():
            T, L = _getal(r.temp_24h), _getal(r.lichtsom)
            if T is not None or L is not None:
                self.klimaat.setdefault((int(r.tuin_id), int(r.afdeling)), {})[_d(r.datum)] = (T, L)
        self.water = {}
        for r in water.itertuples():
            liter = _getal(r.liter_per_m2)
            if liter is not None:
                self.water.setdefault((int(r.tuin_id), int(r.vaknummer)), {})[_d(r.datum)] = liter
        self.warmte = {int(t): {_d(d): mj for d, mj in dagen.items() if mj is not None}
                       for t, dagen in warmte.items()}


def teelt(k, m2, prognose=None, florgib_historie=None):
    """
    De vaste gegevens van één vak als dict (zonder klimaat/input; zie
    met_dagdata). k: een regel van get_teeltvergelijking_data; m2: oppervlakte.
    """
    start, oogst = _d(k["datum_teelt_start"]), _d(k.get("datum_oogst"))
    half = _d(k.get("datum_half")) or _d(florgib_historie)
    half = half if half and half > start and (not oogst or half < oogst) else None
    eind = oogst or _d(prognose)
    planten, uitval = _getal(k.get("aantal_planten")), _getal(k.get("uitval_pct"))
    stelen = _getal(k.get("stelen")) or (planten * (1 - uitval / 100) if planten and uitval is not None else None)
    lengte, lengte_fg = _getal(k.get("lengte_eind")), _getal(k.get("lengte_half"))
    stekvelden = [str(k.get(v) or "").strip().lower() for v in ("wortel", "plantmaat", "uniformiteit")]
    t = {
        "id": k["id"], "tuin_id": int(k["tuin_id"]), "vak": int(k["vaknummer"]),
        "afdeling": int(k["afdeling"]) if _getal(k.get("afdeling")) is not None else None,
        "code": k.get("code"), "m2": m2, "afgerond": oogst is not None, "oogst_echt": oogst,
        "start": start, "florgib": half, "oogst": eind, "prognose": oogst is None and eind is not None,
        "fase1": (half - start).days if half else None,
        "fase2": (eind - half).days if eind and half else None,
        "teeltduur": (eind - start).days if eind else None,
        "stelen_m2": stelen / m2 if stelen and m2 else None, "uitval": uitval,
        "lengte": lengte, "gewicht": _getal(k.get("oogstgewicht")), "lengte_fg": lengte_fg,
        "lengtefactor": lengte / lengte_fg if lengte and lengte_fg else None,
        "stek": _getal(k.get("beoordeling")),
        "stek_matig": any(v in STEK_MATIG for v in stekvelden) if any(stekvelden) else None,
        "gedeeltelijk": False,
    }
    t.update({s: None for s in KLIMAAT_INPUT})
    return t


def met_dagdata(t, dagdata, gisteren, teeltdag=None):
    """
    Het vak met klimaat en input over het venster [planten, eind]: eind = de
    oogst, of gisteren als het vak nog loopt, en hooguit planten + teeltdag.
    "gedeeltelijk" = het venster stopt vóór de oogst (lopend of afgekapt).
    """
    eind = min(t["oogst_echt"] or gisteren, gisteren)
    if teeltdag is not None:
        eind = min(eind, t["start"] + timedelta(days=teeltdag))
    uit = dict(t, gedeeltelijk=t["oogst_echt"] is None or eind < t["oogst_echt"], venster_eind=eind)
    if eind < t["start"]:
        return uit
    dagen = [t["start"] + timedelta(days=i) for i in range((eind - t["start"]).days + 1)]
    klimaat = dagdata.klimaat.get((t["tuin_id"], t["afdeling"]), {})
    T = [klimaat[d][0] for d in dagen if d in klimaat and klimaat[d][0] is not None]
    L = [klimaat[d][1] for d in dagen if d in klimaat and klimaat[d][1] is not None]
    beide = [klimaat[d] for d in dagen if d in klimaat and None not in klimaat[d]]
    uit["temp"] = sum(T) / len(T) if T else None
    uit["lichtsom"] = sum(L) / len(L) if L else None
    uit["afwijking"] = sum(tt - t_ideaal(ll) for tt, ll in beide) / len(beide) if beide else None
    water = dagdata.water.get((t["tuin_id"], t["vak"]), {})
    liters = [water[d] for d in dagen if d in water]
    uit["water"] = sum(liters) if liters else None
    warmte = dagdata.warmte.get(t["tuin_id"], {})
    mj = [warmte[d] for d in dagen if d in warmte]
    uit["warmte"] = sum(mj) if mj and len(mj) >= MIN_ENERGIEDEKKING * len(dagen) else None
    return uit


def teeltdag(groep, gisteren):
    """Loopt de teelt nog (minstens één vak lopend), dan de teeltdag: gisteren − eerste plantdatum."""
    if not groep or all(t["afgerond"] for t in groep):
        return None
    return (gisteren - min(t["start"] for t in groep)).days


def _meetellen(t, sleutel):
    return t[sleutel] is not None and t["m2"] and (t["afgerond"] or sleutel not in ALLEEN_AFGEROND)


def samenvatting(vakken):
    """
    ({sleutel: (teller, noemer, n, verwacht)}, {sleutel: tekst}, {sleutels met ⏳})
    over de vakken van een teelt: numerieke kengetallen gewogen naar m² van het vak.
    """
    delen, markering = {}, set()
    afgerond = [t for t in vakken if t["afgerond"]]
    for sleutel in NUMERIEK:
        rijen = [t for t in vakken if _meetellen(t, sleutel)]
        verwacht = len(afgerond) if sleutel in ALLEEN_AFGEROND else len(vakken)
        if rijen:
            delen[sleutel] = (sum(t[sleutel] * t["m2"] for t in rijen), sum(t["m2"] for t in rijen), len(rijen),
                              verwacht if sleutel not in ("fase1", "fase2", "teeltduur") else None)
            if sleutel in MET_PROGNOSE and any(t["prognose"] for t in rijen):
                markering.add(sleutel)
            if sleutel in KLIMAAT_INPUT and any(t["gedeeltelijk"] for t in rijen):
                markering.add(sleutel)
    if vakken:
        delen["aantal"] = (float(len(vakken)), 1.0, len(afgerond), None)
    stek = [t for t in vakken if t["stek_matig"] is not None]
    if stek:
        delen["stek_matig"] = (float(sum(1 for t in stek if t["stek_matig"])), 1.0, len(stek), None)
    tekst = {
        "plantdatum": kort_bereik(t["start"] for t in vakken),
        "florgib": kort_bereik(t["florgib"] for t in vakken),
        "oogst": kort_bereik(t["oogst"] for t in vakken),
    }
    if any(t["prognose"] for t in vakken):
        markering.add("oogst")
    return delen, {k: v for k, v in tekst.items() if v}, markering


MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def kort_bereik(datums):
    """Korte datumbereiken: "10 aug", "10–13 aug", "28 aug – 2 sep" (zonder jaar)."""
    datums = sorted(d for d in datums if d)
    if not datums:
        return None
    a, b = datums[0], datums[-1]
    if a == b:
        return f"{a.day} {MAANDEN[a.month - 1]}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b.day} {MAANDEN[a.month - 1]}"
    return f"{a.day} {MAANDEN[a.month - 1]} – {b.day} {MAANDEN[b.month - 1]}"


def _ontbreekt(sleutel, vakken):
    if not vakken:
        return "Geen vakken in deze teelt"
    if sleutel in ALLEEN_AFGEROND and not any(t["afgerond"] for t in vakken):
        return "Nog geen afgeronde vakken"
    if sleutel == "warmte":
        return "Warmte niet (vrijwel) elke dag van de teelt geregistreerd"
    if sleutel in KLIMAAT_INPUT:
        return "Geen data over de dagen van de teelt"
    return "Niet geregistreerd"


def tabelwaarden(vakken, tuinen):
    """
    Voor de vergelijkingstabel een dict met per kolom (de tuinen en "Totaal"):
    waarden, n, verwacht, markering en ontbreekt, plus bron: {sleutel: tuinen
    die in het totaal meetellen}. Datumbereiken zijn tekstwaarden.
    tuinen: [(naam, tuin_id)].
    """
    groepen = {naam: [t for t in vakken if t["tuin_id"] == tuin_id] for naam, tuin_id in tuinen}
    if len(tuinen) > 1:
        groepen["Totaal"] = [t for t in vakken if t["tuin_id"] in {i for _, i in tuinen}]
    uit = {"waarden": {}, "n": {}, "verwacht": {}, "markering": {}, "ontbreekt": {}}
    alle = set(NUMERIEK) | SOMMEN | {"plantdatum", "florgib", "oogst"}
    for kolom, groep in groepen.items():
        delen, tekst, markering = samenvatting(groep)
        uit["waarden"][kolom] = {s: (d[0] if s in SOMMEN else d[0] / d[1]) for s, d in delen.items()}
        uit["waarden"][kolom].update(tekst)
        uit["n"][kolom] = {s: d[2] for s, d in delen.items()}
        uit["verwacht"][kolom] = {s: d[3] for s, d in delen.items() if d[3] is not None}
        uit["markering"][kolom] = markering
        uit["ontbreekt"][kolom] = {s: _ontbreekt(s, groep) for s in alle if s not in uit["waarden"][kolom]}
    uit["bron"] = {s: frozenset(naam for naam, _ in tuinen if uit["waarden"][naam].get(s) is not None)
                   for s in uit["waarden"].get("Totaal", {})}
    return uit


def afwijking_van_gemiddelde(vakken, sleutel):
    """{vak-id: relatieve afwijking t.o.v. het m²-gewogen gemiddelde van de teelt} voor één kengetal."""
    delen, _, _ = samenvatting(vakken)
    if sleutel not in delen or not delen[sleutel][1]:
        return {}
    gemiddeld = delen[sleutel][0] / delen[sleutel][1]
    if not gemiddeld:
        return {}
    return {t["id"]: (t[sleutel] - gemiddeld) / abs(gemiddeld) for t in vakken if _meetellen(t, sleutel)}


def plantweken(vakken):
    """{(isojaar, week): (aantal vakken, afgerond)}."""
    uit = {}
    for t in vakken:
        sleutel = plantweek(t["start"])
        aantal, afgerond = uit.get(sleutel, (0, 0))
        uit[sleutel] = (aantal + 1, afgerond + (1 if t["afgerond"] else 0))
    return uit


def standaard_plantweek(weken):
    """De meest recente plantweek met minstens één afgerond vak (of de nieuwste)."""
    met_afgerond = [w for w, (_, afgerond) in weken.items() if afgerond]
    return max(met_afgerond or weken or [None])


def vorige_weken(sleutel, aantal):
    """De `aantal` plantweken t/m `sleutel`, oudste eerst."""
    maandag = date.fromisocalendar(sleutel[0], sleutel[1], 1)
    return [plantweek(maandag - timedelta(weeks=i)) for i in range(aantal - 1, -1, -1)]

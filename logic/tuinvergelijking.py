"""
Tuinvergelijking: wat er in een periode in de kas gebeurde, per tuin en voor
beide tuinen samen, per m². Alleen rekenwerk op DataFrames (zie
database.get_vergelijking_data); tests in tests/test_tuinvergelijking.py.

Elk kengetal is per tuin een teller en een noemer (plus n: dagen of teelten).
De waarde is teller / noemer; het totaal is de som van de tellers gedeeld door
de som van de noemers van de tuinen die een waarde hebben. Zo is het totaal
vanzelf gewogen naar m² (nooit het gemiddelde van twee tuinen), en zie je aan
de bijdragende tuinen of het totaal op één tuin rust.

Oppervlakten: vak-m² uit teeltvakken; een afdeling = de som van haar vakken;
de tuin = de som van alle vakken (energie en water per m² kas: de hele kas
wordt verwarmd).
"""
from datetime import date, datetime, timedelta

from logic.lichtlijn import t_ideaal

# Waarde = teller / noemer × schaal.
SCHAAL = {"bezetting": 100}
# Bij deze kengetallen is n een aantal teelten of vakken; bij de rest dagen.
N_TELLEN_OP = {"geplant", "stelen_m2", "uitval"}
# Een som (geen verhouding): het totaal telt de tuinen op.
SOMMEN = {"geplant"}
# Som over de dagen van de periode: in het totaal telt een tuin alleen mee als hij
# (bijna) even veel dagen data heeft als de tuin met de meeste, anders zou een
# tuin met 13 dagen water naast een tuin met 188 dagen het totaal omlaag trekken.
DAGSOMMEN = {"warmte", "gas", "water"}
MIN_DEKKING = 0.9


def _d(waarde):
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def _getal(waarde):
    try:
        waarde = float(waarde)
    except (TypeError, ValueError):
        return None
    return None if waarde != waarde else waarde


class Gegevens:
    """De data van get_vergelijking_data, één keer voorbereid (datums, m² per vak/afdeling/tuin)."""

    def __init__(self, data):
        self.vak_m2, self.afd_m2, self.tuin_m2, self.vak_afdeling = {}, {}, {}, {}
        for r in data["vakken"].itertuples():
            m2 = _getal(r.m2) or 0.0
            self.vak_m2[(int(r.tuin_id), int(r.vaknummer))] = m2
            if _getal(r.afdeling) is not None:
                self.vak_afdeling[(int(r.tuin_id), int(r.vaknummer))] = int(r.afdeling)
            self.tuin_m2[int(r.tuin_id)] = self.tuin_m2.get(int(r.tuin_id), 0.0) + m2
            if _getal(r.afdeling) is not None:
                sleutel = (int(r.tuin_id), int(r.afdeling))
                self.afd_m2[sleutel] = self.afd_m2.get(sleutel, 0.0) + m2
        self.teelten = [
            {**t, "tuin_id": int(t["tuin_id"]), "vaknummer": int(t["vaknummer"]),
             "start": _d(t["datum_teelt_start"]), "oogst": _d(t["datum_oogst"])}
            for t in data["teelten"].to_dict("records") if _d(t["datum_teelt_start"])
        ]
        self.eerste_teelt = {}
        for t in self.teelten:
            self.eerste_teelt[t["tuin_id"]] = min(t["start"], self.eerste_teelt.get(t["tuin_id"], t["start"]))
        self.emmers = [{**e, "tuin_id": int(e["tuin_id"]), "datum": _d(e["datum"])}
                       for e in data["emmers"].to_dict("records")]
        self.eerste_emmer = {}
        for e in self.emmers:
            self.eerste_emmer[e["tuin_id"]] = min(e["datum"], self.eerste_emmer.get(e["tuin_id"], e["datum"]))
        self.klimaat = data["klimaat"]
        self.energie = data["energie"]
        self.gas = data["gas"]
        self.water = data["water"]


def uitval_teelt(t):
    """Uitval in %: uit de emmers (100 stelen per emmer), anders het vastgelegde percentage."""
    planten, emmers = _getal(t.get("aantal_planten")), _getal(t.get("emmers"))
    if planten and emmers:
        return (planten - emmers * 100) / planten * 100
    return _getal(t.get("uitval_pct"))


def _bezet_per_dag(g, tuin_id, van, tot):
    """{dag: bezette m²}: vakken met een teelt die die dag stond (een vak telt één keer per dag)."""
    vakken = {}
    for t in g.teelten:
        if t["tuin_id"] != tuin_id or t["start"] > tot or (t["oogst"] and t["oogst"] < van):
            continue
        dag, eind = max(t["start"], van), min(t["oogst"] or tot, tot)
        while dag <= eind:
            vakken.setdefault(dag, set()).add(t["vaknummer"])
            dag += timedelta(days=1)
    return {dag: sum(g.vak_m2.get((tuin_id, v), 0.0) for v in vakken.get(dag, ()))
            for dag in (van + timedelta(days=i) for i in range((tot - van).days + 1))}


def _in_periode(df, van, tot):
    return df[(df["datum"] >= str(van)) & (df["datum"] <= str(tot))]


def onderdelen(g, tuin_id, van, tot):
    """
    {sleutel: (teller, noemer, n)} van één tuin over [van, tot]; een kengetal
    zonder data ontbreekt (wordt "–", nooit 0).
    """
    uit = {}
    totaal_m2 = g.tuin_m2.get(tuin_id, 0.0)
    bestond = g.eerste_teelt.get(tuin_id) and g.eerste_teelt[tuin_id] <= tot
    # Bezetting pas vanaf de eerste teelt in de app: daarvoor is "leeg" onbekend.
    van_bezet = max(van, g.eerste_teelt[tuin_id]) if bestond else van
    dagen = (tot - van_bezet).days + 1

    if bestond and totaal_m2:
        bezet = _bezet_per_dag(g, tuin_id, van_bezet, tot)
        uit["bezetting"] = (sum(bezet.values()), totaal_m2 * dagen, dagen)
        geplant = {t["vaknummer"] for t in g.teelten if t["tuin_id"] == tuin_id and van <= t["start"] <= tot}
        uit["geplant"] = (sum(g.vak_m2.get((tuin_id, v), 0.0) for v in geplant), 1.0, len(geplant))
        # Stelen uit de emmers: alleen als de emmerregistratie al vóór de periode liep.
        gem_bezet = sum(bezet.values()) / dagen
        eerste = g.eerste_emmer.get(tuin_id)
        if eerste and eerste <= van and gem_bezet:
            emmers = [e for e in g.emmers if e["tuin_id"] == tuin_id and van <= e["datum"] <= tot]
            stelen = sum(_getal(e["aantal_emmers"]) or 0 for e in emmers) * 100
            uit["stelen_m2"] = (stelen, gem_bezet, len({e["teelt_id"] for e in emmers}))

    afgerond = [t for t in g.teelten if t["tuin_id"] == tuin_id and t["oogst"] and van <= t["oogst"] <= tot]
    met_uitval = [(uitval_teelt(t), g.vak_m2.get((tuin_id, t["vaknummer"]), 0.0)) for t in afgerond]
    met_uitval = [(u, m2) for u, m2 in met_uitval if u is not None and m2]
    if met_uitval:
        uit["uitval"] = (sum(u * m2 for u, m2 in met_uitval), sum(m2 for _, m2 in met_uitval), len(met_uitval))

    # Klimaat: elke afdeling-dag weegt met de m² van de afdeling.
    klimaat = _in_periode(g.klimaat[g.klimaat["tuin_id"] == tuin_id], van, tot)
    if not klimaat.empty:
        m2 = klimaat["afdeling"].map(lambda a: g.afd_m2.get((tuin_id, int(a)), 0.0))
        afwijking = klimaat["temp_24h"] - t_ideaal(klimaat["lichtsom"])
        for sleutel, kolom in (("temp", klimaat["temp_24h"]), ("temp_dag", klimaat["temp_dag"]),
                               ("temp_nacht", klimaat["temp_nacht"]), ("rv", klimaat["rv_24h"]),
                               ("lichtsom", klimaat["lichtsom"]), ("afwijking", afwijking)):
            bekend = kolom.notna() & (m2 > 0)
            if bekend.any():
                uit[sleutel] = (float((kolom[bekend] * m2[bekend]).sum()), float(m2[bekend].sum()),
                                int(klimaat.loc[bekend, "datum"].nunique()))

    # Energie en water per m² kas: som over de periode gedeeld door de hele tuin.
    for sleutel, df, kolom in (("warmte", g.energie, "warmte_mj"), ("gas", g.gas, "gas_m3")):
        rijen = _in_periode(df[df["tuin_id"] == tuin_id], van, tot).dropna(subset=[kolom])
        if not rijen.empty and totaal_m2:
            uit[sleutel] = (float(rijen[kolom].sum()), totaal_m2, int(rijen["datum"].nunique()))
    water = _in_periode(g.water[g.water["tuin_id"] == tuin_id], van, tot).dropna(subset=["liter_per_m2"])
    if not water.empty and totaal_m2:
        liters = water["liter_per_m2"] * water["vaknummer"].map(lambda v: g.vak_m2.get((tuin_id, int(v)), 0.0))
        uit["water"] = (float(liters.sum()), totaal_m2, int(water["datum"].nunique()))
    return uit


def waarde(delen, sleutel):
    """teller / noemer × schaal, of None."""
    if not delen or not delen[1]:
        return None
    return delen[0] / delen[1] * SCHAAL.get(sleutel, 1)


def bijdragers(per_tuin, sleutel):
    """De tuinen die in het totaal van dit kengetal meetellen (zie DAGSOMMEN)."""
    met = {naam: d[sleutel] for naam, d in per_tuin.items() if sleutel in d}
    if sleutel in DAGSOMMEN and met:
        meeste = max(n for _, _, n in met.values())
        met = {naam: d for naam, d in met.items() if d[2] >= MIN_DEKKING * meeste}
    return frozenset(met)


def samenvoegen(per_tuin):
    """
    Het totaal van meerdere tuinen: {sleutel: (Σ teller, Σ noemer, Σ n)} over de
    tuinen die bijdragen (bijdragers). per_tuin: {naam: onderdelen(...)}.
    """
    totaal = {}
    for naam, delen in per_tuin.items():
        for sleutel, (teller, noemer, n) in delen.items():
            if naam not in bijdragers(per_tuin, sleutel):
                continue
            t, m, k = totaal.get(sleutel, (0.0, 0.0, 0))
            # n is een aantal teelten/vakken (optellen) of een aantal dagen (niet optellen).
            totaal[sleutel] = (t + teller, 1.0 if sleutel in SOMMEN else m + noemer,
                               k + n if sleutel in N_TELLEN_OP else max(k, n))
    return totaal


def tabelwaarden(g, tuinen, van, tot):
    """
    ({kolom: {sleutel: waarde}}, {kolom: {sleutel: n}}, {sleutel: bijdragende tuinen})
    voor de tuinen en "Totaal". tuinen: [(naam, tuin_id)].
    """
    per_tuin = {naam: onderdelen(g, tuin_id, van, tot) for naam, tuin_id in tuinen}
    alleen_tuinen = dict(per_tuin)
    if len(tuinen) > 1:
        per_tuin["Totaal"] = samenvoegen(alleen_tuinen)
    waarden = {k: {s: waarde(d, s) for s, d in delen.items()} for k, delen in per_tuin.items()}
    n = {k: {s: d[2] for s, d in delen.items()} for k, delen in per_tuin.items()}
    bron = {s: bijdragers(alleen_tuinen, s) for s in per_tuin.get("Totaal", {})}
    return waarden, n, bron

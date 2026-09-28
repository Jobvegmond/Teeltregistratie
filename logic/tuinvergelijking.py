"""
Tuinvergelijking: wat er in een periode in de kas gebeurde, per tuin en voor
beide tuinen samen, per m². Alleen rekenwerk op DataFrames (zie
database.get_vergelijking_data); tests in tests/test_tuinvergelijking.py.

Elk kengetal is per tuin een teller en een noemer, plus n (aantal dagen of
vakken met data) en verwacht (hoeveel het er hadden moeten zijn; minder = ⚠).
De waarde is teller / noemer; het totaal is de som van de tellers gedeeld door
de som van de noemers van de tuinen die meetellen. Zo is het totaal vanzelf
gewogen naar m² (nooit het gemiddelde van twee tuinen), en zie je aan de
bijdragende tuinen of het totaal op één tuin rust. Ontbreekt een kengetal,
dan zegt ontbreekt_tekst() waarom (bijv. "warmte geregistreerd t/m 20-09").

Oppervlakten: vak-m² uit teeltvakken; een afdeling = de som van haar vakken;
de tuin = de som van alle vakken (energie en water per m² kas: de hele kas
wordt verwarmd).
"""
from datetime import date, datetime, timedelta

from config import GAS_CALORISCHE_WAARDE_MJ_PER_M3
from logic.lichtlijn import t_ideaal

# Waarde = teller / noemer × schaal.
SCHAAL = {"bezetting": 100}
# Bij deze kengetallen is n een aantal vakken; bij de rest dagen.
N_TELLEN_OP = {"geplant", "geoogst", "uitval"}
# Een som (geen verhouding): het totaal telt de tuinen op.
SOMMEN = {"geplant", "geoogst"}
# Som over de dagen van de periode: in het totaal telt een tuin alleen mee als hij
# (bijna) even veel dagen data heeft als de tuin met de meeste, anders zou een
# tuin met 13 dagen water naast een tuin met 188 dagen het totaal omlaag trekken.
DAGSOMMEN = {"warmte", "gas", "energie", "water"}
MIN_DEKKING = 0.9
KLIMAAT = ("temp", "temp_dag", "temp_nacht", "rv", "lichtsom", "afwijking")
# Welke registratie achter een kengetal zit (voor de uitleg bij "–").
BRON = {**{s: "klimaat" for s in KLIMAAT}, "warmte": "warmte", "gas": "gas", "energie": "warmte", "water": "water"}


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
        # Per tuin de eerste en laatste dag met data per registratie.
        self.registratie = {}
        for naam, df, kolom in (("klimaat", self.klimaat, "temp_24h"), ("warmte", self.energie, "warmte_mj"),
                                ("gas", self.gas, "gas_m3"), ("water", self.water, "liter_per_m2")):
            bekend = df.dropna(subset=[kolom])
            for tuin_id, groep in bekend.groupby("tuin_id"):
                self.registratie[(int(tuin_id), naam)] = (_d(groep["datum"].min()), _d(groep["datum"].max()))


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
    {sleutel: (teller, noemer, n, verwacht)} van één tuin over [van, tot]; een
    kengetal zonder data ontbreekt (wordt "–", nooit 0). verwacht is None als er
    geen verwachting is (bijv. hoeveel vakken er geoogst hadden moeten worden).
    """
    uit = {}
    totaal_m2 = g.tuin_m2.get(tuin_id, 0.0)
    bestond = g.eerste_teelt.get(tuin_id) and g.eerste_teelt[tuin_id] <= tot
    # Bezetting pas vanaf de eerste teelt in de app: daarvoor is "leeg" onbekend.
    van_bezet = max(van, g.eerste_teelt[tuin_id]) if bestond else van
    dagen = (tot - van).days + 1

    if bestond and totaal_m2:
        dagen_bezet = (tot - van_bezet).days + 1
        bezet = _bezet_per_dag(g, tuin_id, van_bezet, tot)
        uit["bezetting"] = (sum(bezet.values()), totaal_m2 * dagen_bezet, dagen_bezet, None)
        geplant = [t for t in g.teelten if t["tuin_id"] == tuin_id and van <= t["start"] <= tot]
        planten = [_getal(t.get("aantal_planten")) for t in geplant]
        uit["geplant"] = (sum(p for p in planten if p), 1.0, sum(1 for p in planten if p), len(geplant))
    # Geoogst uit de emmers: alleen als de emmerregistratie al vóór de periode liep.
    eerste = g.eerste_emmer.get(tuin_id)
    if eerste and eerste <= van:
        emmers = [e for e in g.emmers if e["tuin_id"] == tuin_id and van <= e["datum"] <= tot]
        stelen = sum(_getal(e["aantal_emmers"]) or 0 for e in emmers) * 100
        uit["geoogst"] = (stelen, 1.0, len({e["teelt_id"] for e in emmers}), None)

    afgerond = [t for t in g.teelten if t["tuin_id"] == tuin_id and t["oogst"] and van <= t["oogst"] <= tot]
    met_uitval = [(uitval_teelt(t), g.vak_m2.get((tuin_id, t["vaknummer"]), 0.0)) for t in afgerond]
    met_uitval = [(u, m2) for u, m2 in met_uitval if u is not None and m2]
    if met_uitval:
        uit["uitval"] = (sum(u * m2 for u, m2 in met_uitval), sum(m2 for _, m2 in met_uitval), len(met_uitval),
                         len(afgerond))

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
                                int(klimaat.loc[bekend, "datum"].nunique()), dagen)

    # Energie en water per m² kas: som over de periode gedeeld door de hele tuin.
    per_dag = {}
    for sleutel, df, kolom in (("warmte", g.energie, "warmte_mj"), ("gas", g.gas, "gas_m3")):
        rijen = _in_periode(df[df["tuin_id"] == tuin_id], van, tot).dropna(subset=[kolom])
        if not rijen.empty and totaal_m2:
            uit[sleutel] = (float(rijen[kolom].sum()), totaal_m2, int(rijen["datum"].nunique()), dagen)
            per_dag[sleutel] = dict(zip(rijen["datum"], rijen[kolom].astype(float)))
    # Energie totaal = warmte + gas omgerekend naar MJ, over de dagen met beide.
    if "warmte" in per_dag and "gas" in per_dag:
        samen = set(per_dag["warmte"]) & set(per_dag["gas"])
        mj = sum(per_dag["warmte"][d] + per_dag["gas"][d] * GAS_CALORISCHE_WAARDE_MJ_PER_M3 for d in samen)
        uit["energie"] = (mj, totaal_m2, len(samen), dagen)
    water = _in_periode(g.water[g.water["tuin_id"] == tuin_id], van, tot).dropna(subset=["liter_per_m2"])
    if not water.empty and totaal_m2:
        liters = water["liter_per_m2"] * water["vaknummer"].map(lambda v: g.vak_m2.get((tuin_id, int(v)), 0.0))
        uit["water"] = (float(liters.sum()), totaal_m2, int(water["datum"].nunique()), dagen)
    return uit


def ontbreekt_tekst(g, tuin_id, sleutel, van, tot):
    """Waarom een kengetal van deze tuin in [van, tot] geen waarde heeft."""
    eerste_teelt = g.eerste_teelt.get(tuin_id)
    if sleutel in ("bezetting", "geplant"):
        return f"In de app sinds {eerste_teelt:%d-%m-%y}" if eerste_teelt else "Nog geen vakken in de app"
    if sleutel == "geoogst":
        eerste = g.eerste_emmer.get(tuin_id)
        return f"Emmers geregistreerd sinds {eerste:%d-%m-%y}" if eerste else "Nog geen emmers geregistreerd"
    if sleutel == "uitval":
        return "Geen afgeronde vakken met bekende uitval in deze periode"
    bron = BRON.get(sleutel, sleutel)
    periode = g.registratie.get((tuin_id, bron))
    if not periode:
        return f"Geen {bron} geregistreerd"
    eerste, laatste = periode
    if laatste < van:
        return f"{bron.capitalize()} geregistreerd t/m {laatste:%d-%m-%y}"
    if eerste > tot:
        return f"{bron.capitalize()} geregistreerd vanaf {eerste:%d-%m-%y}"
    return f"Geen {bron} in deze periode (geregistreerd {eerste:%d-%m-%y} t/m {laatste:%d-%m-%y})"


def waarde(delen, sleutel):
    """teller / noemer × schaal, of None."""
    if not delen or not delen[1]:
        return None
    return delen[0] / delen[1] * SCHAAL.get(sleutel, 1)


def bijdragers(per_tuin, sleutel):
    """De tuinen die in het totaal van dit kengetal meetellen (zie DAGSOMMEN)."""
    met = {naam: d[sleutel] for naam, d in per_tuin.items() if sleutel in d}
    if sleutel in DAGSOMMEN and met:
        meeste = max(d[2] for d in met.values())
        met = {naam: d for naam, d in met.items() if d[2] >= MIN_DEKKING * meeste}
    return frozenset(met)


def samenvoegen(per_tuin):
    """
    Het totaal van meerdere tuinen: {sleutel: (Σ teller, Σ noemer, n, verwacht)}
    over de tuinen die bijdragen (bijdragers). per_tuin: {naam: onderdelen(...)}.
    """
    totaal = {}
    for naam, delen in per_tuin.items():
        for sleutel, (teller, noemer, n, verwacht) in delen.items():
            if naam not in bijdragers(per_tuin, sleutel):
                continue
            t, m, k, v = totaal.get(sleutel, (0.0, 0.0, 0, None))
            # n is een aantal vakken (optellen) of een aantal dagen (niet optellen).
            optellen = sleutel in N_TELLEN_OP
            if verwacht is not None:
                v = (v or 0) + verwacht if optellen else max(v or 0, verwacht)
            totaal[sleutel] = (t + teller, 1.0 if sleutel in SOMMEN else m + noemer,
                               k + n if optellen else max(k, n), v)
    return totaal


def tabelwaarden(g, tuinen, van, tot):
    """
    Voor de vergelijkingstabel een dict met per kolom (de tuinen en "Totaal"):
    waarden, n, verwacht en ontbreekt (uitleg bij "–"), plus bron: {sleutel:
    tuinen die in het totaal meetellen}. tuinen: [(naam, tuin_id)].
    """
    per_tuin = {naam: onderdelen(g, tuin_id, van, tot) for naam, tuin_id in tuinen}
    alleen_tuinen = dict(per_tuin)
    if len(tuinen) > 1:
        per_tuin["Totaal"] = samenvoegen(alleen_tuinen)
    uit = {
        "waarden": {k: {s: waarde(d, s) for s, d in delen.items()} for k, delen in per_tuin.items()},
        "n": {k: {s: d[2] for s, d in delen.items()} for k, delen in per_tuin.items()},
        "verwacht": {k: {s: d[3] for s, d in delen.items() if d[3] is not None} for k, delen in per_tuin.items()},
        "bron": {s: bijdragers(alleen_tuinen, s) for s in per_tuin.get("Totaal", {})},
        "ontbreekt": {},
    }
    alle_sleutels = set(BRON) | {"bezetting", "geplant", "geoogst", "uitval"}
    for naam, tuin_id in tuinen:
        uit["ontbreekt"][naam] = {s: ontbreekt_tekst(g, tuin_id, s, van, tot)
                                  for s in alle_sleutels if s not in per_tuin[naam]}
    if len(tuinen) > 1:
        uit["ontbreekt"]["Totaal"] = {s: "Geen van de tuinen heeft data" for s in alle_sleutels
                                      if s not in per_tuin["Totaal"]}
    return uit

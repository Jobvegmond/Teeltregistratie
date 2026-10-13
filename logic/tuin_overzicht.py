"""
Pagina Tuin bij Tuin 1 / Tuin 3: wat er op een dag of in een week in één tuin gebeurde, per afdeling.

- tabelwaarden(): de kengetallen per afdeling en voor de hele tuin, in de vorm van
  tuinvergelijking.tabelwaarden (kolommen "Afd. n" en HELE_TUIN). Een afdeling rekent met dezelfde
  regels als een tuin (tuinvergelijking.onderdelen op alleen de vakken en het klimaat van die afdeling);
  warmte en gas zijn er alleen voor de hele kas. Uit het klimaat per uur (tabel klimaat_uur, alleen
  waar de Priva-bestanden zijn) komen de laagste/hoogste temperatuur, vochtdeficit, CO2, de berekende
  stooktemperatuur en de uren met een hoge RV. Verder de DIF (dag − nacht) en EC/pH van de gift.
- gebeurtenissen(): geplant, Florgib, oogst, afgerond en opmerkingen in de periode, per vak.

Alleen rekenwerk; tests in tests/test_tuin_overzicht.py.
"""
import copy

from logic import tuinvergelijking as tuinvgl
from utils.format import fmt_getal, fmt_kort

HELE_TUIN = "Hele tuin"
# Alleen voor de hele kas gemeten (geen meter per afdeling).
ALLEEN_TUIN = ("warmte", "gas", "energie")
# Uit klimaat_uur: gemiddelden (teller = som, noemer = aantal uren), uitersten en uren met RV ≥ RV_HOOG.
# "verwarming" = de door Priva berekende verwarmingstemperatuur: de stooklijn (luchttemperatuur), niet de buis.
UUR_GEMIDDELD = {"vd": "vd", "co2": "co2", "stook": "verwarming"}
UUR_SLEUTELS = ("temp_min", "temp_max", "rv_hoog", "stook_max", *UUR_GEMIDDELD)
UUR_UITERSTEN = {"temp_min": min, "temp_max": max, "stook_max": max}
RV_HOOG = 90


def kolom(afdeling):
    return f"Afd. {afdeling}"


def afdelingen(g, tuin_id):
    """De afdelingen van een tuin met vakken (m² > 0), oplopend."""
    return sorted(a for (t, a), m2 in g.afd_m2.items() if t == tuin_id and m2)


def afdeling_gegevens(g, tuin_id, afdeling):
    """
    Een kopie van de Gegevens met alleen de vakken, het klimaat en de watergift van één afdeling, zodat
    tuinvergelijking.onderdelen() die afdeling rekent als een tuin (per m² afdeling). Warmte en gas vallen
    weg. De eerste teelt en emmer van de tuin blijven: de registratie liep voor de hele tuin.
    """
    vakken = {v for (t, v), a in g.vak_afdeling.items() if t == tuin_id and a == afdeling}
    a = copy.copy(g)
    a.tuin_m2 = {tuin_id: g.afd_m2.get((tuin_id, afdeling), 0.0)}
    a.teelten = [t for t in g.teelten if t["tuin_id"] == tuin_id and t["vaknummer"] in vakken]
    a.emmers = [e for e in g.emmers if e["tuin_id"] == tuin_id and int(e["vaknummer"]) in vakken]
    a.klimaat = g.klimaat[(g.klimaat["tuin_id"] == tuin_id) & (g.klimaat["afdeling"] == afdeling)]
    a.energie, a.gas = g.energie.iloc[0:0], g.gas.iloc[0:0]
    a.water = g.water[(g.water["tuin_id"] == tuin_id) & g.water["vaknummer"].astype(int).isin(vakken)]
    return a


def uur_onderdelen(uur, afd_m2, van, tot):
    """
    {kolom: {sleutel: (teller, noemer, n, verwacht)}} uit het klimaat per uur (DataFrame met afdeling,
    tijdstip "YYYY-MM-DD HH:MM", temp, rv, vd, co2, verwarming) over de dagen van..tot. n = uren met
    data, verwacht = 24 per dag. De hele tuin: gemiddelden en uren hoge RV gewogen naar m² afdeling,
    uitersten over alle afdelingen. afd_m2: {afdeling: m²}.
    """
    uit = {}
    if uur is None or uur.empty:
        return uit
    uur = uur[(uur["tijdstip"] >= str(van)) & (uur["tijdstip"] <= f"{tot} 23:59")]
    verwacht = 24 * ((tot - van).days + 1)
    for afdeling, groep in uur.groupby("afdeling"):
        if int(afdeling) not in afd_m2:
            continue
        d = {}
        temp = groep["temp"].dropna()
        if len(temp):
            d["temp_min"] = (float(temp.min()), 1.0, len(temp), verwacht)
            d["temp_max"] = (float(temp.max()), 1.0, len(temp), verwacht)
        rv = groep["rv"].dropna()
        if len(rv):
            # Uren per etmaal met een hoge RV, geschaald naar 24 gemeten uren.
            d["rv_hoog"] = (float((rv >= RV_HOOG).sum()) * 24, float(len(rv)), len(rv), verwacht)
        stook = groep["verwarming"].dropna()
        if len(stook):
            d["stook_max"] = (float(stook.max()), 1.0, len(stook), verwacht)
        for sleutel, veld in UUR_GEMIDDELD.items():
            reeks = groep[veld].dropna()
            if len(reeks):
                d[sleutel] = (float(reeks.sum()), float(len(reeks)), len(reeks), verwacht)
        if d:
            uit[kolom(int(afdeling))] = d
    totaal = {}
    for sleutel in UUR_SLEUTELS:
        delen = [(afd_m2[int(k.split()[-1])], d[sleutel]) for k, d in uit.items() if sleutel in d]
        if not delen:
            continue
        n = max(d[2] for _, d in delen)
        if sleutel in UUR_UITERSTEN:
            totaal[sleutel] = (UUR_UITERSTEN[sleutel](d[0] for _, d in delen), 1.0, n, verwacht)
        else:
            totaal[sleutel] = (sum(m2 * d[0] / d[1] for m2, d in delen), sum(m2 for m2, _ in delen), n, verwacht)
    if totaal:
        uit[HELE_TUIN] = totaal
    return uit


def _gift(water, van, tot):
    """De watergift met water (l/m² > 0) in [van, tot]; leeg als EC/pH er (nog) niet bij zitten."""
    if "ec" not in water.columns:
        return water.iloc[0:0]
    w = water[(water["datum"] >= str(van)) & (water["datum"] <= str(tot))]
    return w[w["liter_per_m2"].fillna(0) > 0]


def water_kwaliteit(water, tuin_id, vak_m2, van, tot):
    """{"ec"/"ph": (teller, noemer, n dagen, None)}: EC en pH van de gift, gewogen naar liters × m² vak."""
    gift = _gift(water[water["tuin_id"] == tuin_id], van, tot)
    uit = {}
    for sleutel in ("ec", "ph"):
        rijen = gift.dropna(subset=[sleutel]) if sleutel in gift.columns else gift.iloc[0:0]
        if rijen.empty:
            continue
        gewicht = rijen["liter_per_m2"] * rijen["vaknummer"].map(lambda v: vak_m2.get((tuin_id, int(v)), 0.0))
        if gewicht.sum():
            uit[sleutel] = (float((rijen[sleutel] * gewicht).sum()), float(gewicht.sum()),
                            int(rijen["datum"].nunique()), None)
    return uit


def tabelwaarden(g, uur, tuin_id, van, tot):
    """
    Zoals tuinvergelijking.tabelwaarden, met kolommen "Afd. n" (oplopend) en HELE_TUIN:
    {"kolommen", "waarden", "n", "verwacht", "ontbreekt"}.
    """
    afds = afdelingen(g, tuin_id)
    per = {}
    for a in afds:
        ag = afdeling_gegevens(g, tuin_id, a)
        per[kolom(a)] = {**tuinvgl.onderdelen(ag, tuin_id, van, tot),
                         **water_kwaliteit(ag.water, tuin_id, g.vak_m2, van, tot)}
    per[HELE_TUIN] = {**tuinvgl.onderdelen(g, tuin_id, van, tot),
                      **water_kwaliteit(g.water, tuin_id, g.vak_m2, van, tot)}
    # DIF = dagtemperatuur − nachttemperatuur (beide gewogen gemiddelden over dezelfde dagen).
    for delen in per.values():
        dag, nacht = delen.get("temp_dag"), delen.get("temp_nacht")
        if dag and nacht:
            delen["dif"] = (tuinvgl.waarde(dag, "temp_dag") - tuinvgl.waarde(nacht, "temp_nacht"), 1.0,
                            min(dag[2], nacht[2]), dag[3])
    for k, delen in uur_onderdelen(uur, {a: g.afd_m2[(tuin_id, a)] for a in afds}, van, tot).items():
        per.setdefault(k, {}).update(delen)
    alle = (set(tuinvgl.BRON) | {"bezetting", "geplant", "geoogst", "uitval", "dif", "ec", "ph"}
            | set(UUR_SLEUTELS))
    ontbreekt = {}
    for k, delen in per.items():
        ontbreekt[k] = {}
        for s in alle - set(delen):
            if s in ALLEEN_TUIN and k != HELE_TUIN:
                ontbreekt[k][s] = "Alleen voor de hele kas gemeten"
            elif s in UUR_SLEUTELS:
                ontbreekt[k][s] = "Geen klimaat per uur in deze periode (uit de Priva-bestanden op de NAS)"
            elif s == "dif":
                ontbreekt[k][s] = "Geen dag- en nachttemperatuur in deze periode"
            elif s in ("ec", "ph"):
                ontbreekt[k][s] = f"Geen {'EC' if s == 'ec' else 'pH'} bij een watergift in deze periode"
            else:
                ontbreekt[k][s] = tuinvgl.ontbreekt_tekst(g, tuin_id, s, van, tot)
    return {
        "kolommen": [kolom(a) for a in afds] + [HELE_TUIN],
        "waarden": {k: {s: tuinvgl.waarde(d, s) for s, d in delen.items()} for k, delen in per.items()},
        "n": {k: {s: d[2] for s, d in delen.items()} for k, delen in per.items()},
        "verwacht": {k: {s: d[3] for s, d in delen.items() if d[3] is not None} for k, delen in per.items()},
        "ontbreekt": ontbreekt,
    }


def gebeurtenissen(g, opmerkingen, tuin_id, van, tot):
    """
    Wat er in [van, tot] in de tuin gebeurde, per vak, op datum: [{datum, afdeling, vak, code, soort,
    tekst, teelt_id}]. Oogst per vak samengevat (emmers over de dagen); opmerkingen: dicts van
    get_alle_opmerkingen (al gefilterd of niet).
    """
    uit = []
    for t in g.teelten:
        if t["tuin_id"] != tuin_id:
            continue
        basis = {"afdeling": g.vak_afdeling.get((tuin_id, t["vaknummer"])), "vak": t["vaknummer"],
                 "code": t.get("code") or "", "teelt_id": t.get("id")}
        if van <= t["start"] <= tot:
            planten = tuinvgl._getal(t.get("aantal_planten"))
            uit.append({**basis, "datum": t["start"], "soort": "Geplant",
                        "tekst": f"{fmt_getal(planten)} planten" if planten else ""})
        florgib = t.get("florgib")
        if florgib and van <= florgib <= tot:
            uit.append({**basis, "datum": florgib, "soort": "Florgib", "tekst": ""})
        if t["oogst"] and van <= t["oogst"] <= tot:
            emmers = tuinvgl._getal(t.get("emmers"))
            uit.append({**basis, "datum": t["oogst"], "soort": "Afgerond",
                        "tekst": f"{fmt_kort(emmers, 1)} emmers in totaal" if emmers else ""})
    per_vak = {}
    for e in g.emmers:
        if e["tuin_id"] == tuin_id and van <= e["datum"] <= tot:
            r = per_vak.setdefault(e["teelt_id"], {"e": e, "emmers": 0.0, "dagen": set()})
            r["emmers"] += tuinvgl._getal(e["aantal_emmers"]) or 0
            r["dagen"].add(e["datum"])
    for teelt_id, r in per_vak.items():
        vak = int(r["e"]["vaknummer"])
        dagen = sorted(r["dagen"])
        uit.append({"datum": dagen[-1], "afdeling": g.vak_afdeling.get((tuin_id, vak)), "vak": vak,
                    "code": r["e"].get("code") or "", "teelt_id": teelt_id, "soort": "Oogst", "emmers": r["emmers"],
                    "tekst": f"{fmt_kort(r['emmers'], 1)} emmers"
                             + (f" ({len(dagen)} dagen)" if len(dagen) > 1 else "")})
    for o in opmerkingen:
        d = tuinvgl._d(o["datum"])
        if o["tuin_id"] == tuin_id and van <= d <= tot:
            uit.append({"datum": d, "afdeling": o.get("afdeling"), "vak": o["vaknummer"], "code": o.get("code") or "",
                        "teelt_id": o.get("teelt_id"), "soort": "Opmerking",
                        "tekst": f"{o['categorie']}: {o['tekst']}" if o.get("categorie") else o["tekst"]})
    volgorde = {"Geplant": 0, "Florgib": 1, "Oogst": 2, "Afgerond": 3, "Opmerking": 4}
    return sorted(uit, key=lambda r: (r["datum"], volgorde[r["soort"]], r["vak"]))


def samenvatting(rijen):
    """Eén regel met de aantallen: "2 vakken geplant · 1 Florgib · 14 emmers uit 3 vakken · 2 opmerkingen"."""
    def tel(soort):
        return [r for r in rijen if r["soort"] == soort]

    def vakken(n):
        return f"{n} {'vak' if n == 1 else 'vakken'}"

    delen = []
    if tel("Geplant"):
        delen.append(f"{vakken(len(tel('Geplant')))} geplant")
    if tel("Florgib"):
        delen.append(f"{vakken(len(tel('Florgib')))} Florgib")
    if tel("Oogst"):
        emmers = sum(r["emmers"] for r in tel("Oogst"))
        delen.append(f"{fmt_kort(emmers, 1)} emmers uit {vakken(len(tel('Oogst')))}")
    if tel("Afgerond"):
        delen.append(f"{vakken(len(tel('Afgerond')))} afgerond")
    if tel("Opmerking"):
        n = len(tel("Opmerking"))
        delen.append(f"{n} opmerking{'' if n == 1 else 'en'}")
    return " · ".join(delen)

"""
Pagina Tuin bij Tuin 1 / Tuin 3: wat er op een dag of in een week in één tuin gebeurde, per afdeling.

- tabelwaarden(): de kengetallen per afdeling en voor de hele tuin, in de vorm van
  tuinvergelijking.tabelwaarden (kolommen "Afd. n" en HELE_TUIN). Een afdeling rekent met dezelfde
  regels als een tuin (tuinvergelijking.onderdelen op alleen de vakken en het klimaat van die afdeling);
  warmte en gas zijn er alleen voor de hele kas. Uit het klimaat per uur (tabel klimaat_uur, alleen
  waar de Priva-bestanden zijn) komen de laagste/hoogste temperatuur, vochtdeficit, CO2, buistemperatuur
  en de uren met een hoge RV.
- opvallend(): korte zinnen over wat afwijkt (lichtlijn, verschil tussen afdelingen, hoge RV, verschil
  met de vergelijkingsperiode, onvolledige data).
- gebeurtenissen(): geplant, Florgib, oogst, afgerond en opmerkingen in de periode, per vak.

Alleen rekenwerk; tests in tests/test_tuin_overzicht.py.
"""
import copy
from logic import tuinvergelijking as tuinvgl
from utils.format import fmt_getal, fmt_kort, fmt_verschil

HELE_TUIN = "Hele tuin"
# Alleen voor de hele kas gemeten (geen meter per afdeling).
ALLEEN_TUIN = ("warmte", "gas", "energie")
# Uit klimaat_uur: gemiddelden (teller = som, noemer = aantal uren), uitersten, en uren met RV ≥ RV_HOOG.
UUR_GEMIDDELD = {"vd": "vd", "co2": "co2", "buis": "verwarming"}
UUR_SLEUTELS = ("temp_min", "temp_max", "rv_hoog", *UUR_GEMIDDELD)
RV_HOOG = 90

# Drempels voor opvallend().
DREMPEL_LICHTLIJN = 1.0        # °C boven/onder de lichtlijn per afdeling
DREMPEL_AFDELINGEN = 1.0       # °C verschil in etmaaltemperatuur tussen afdelingen
DREMPEL_TEMP_VERSCHIL = 1.5    # °C verschil met de vergelijkingsperiode (hele tuin)
DREMPEL_RV_VERSCHIL = 5        # %-punt RV verschil met de vergelijkingsperiode
DREMPEL_RELATIEF = 0.25        # 25 % meer/minder lichtsom, water of energie dan de vergelijking
DREMPEL_RV_UREN = 4            # uren per dag met RV ≥ RV_HOOG
TEMP_HOOG, TEMP_LAAG = 30.0, 10.0


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
        if sleutel in ("temp_min", "temp_max"):
            kies = min if sleutel == "temp_min" else max
            totaal[sleutel] = (kies(d[0] for _, d in delen), 1.0, n, verwacht)
        else:
            totaal[sleutel] = (sum(m2 * d[0] / d[1] for m2, d in delen), sum(m2 for m2, _ in delen), n, verwacht)
    if totaal:
        uit[HELE_TUIN] = totaal
    return uit


def tabelwaarden(g, uur, tuin_id, van, tot):
    """
    Zoals tuinvergelijking.tabelwaarden, met kolommen "Afd. n" (oplopend) en HELE_TUIN:
    {"kolommen", "waarden", "n", "verwacht", "ontbreekt"}.
    """
    afds = afdelingen(g, tuin_id)
    per = {kolom(a): tuinvgl.onderdelen(afdeling_gegevens(g, tuin_id, a), tuin_id, van, tot) for a in afds}
    per[HELE_TUIN] = tuinvgl.onderdelen(g, tuin_id, van, tot)
    for k, delen in uur_onderdelen(uur, {a: g.afd_m2[(tuin_id, a)] for a in afds}, van, tot).items():
        per.setdefault(k, {}).update(delen)
    alle = set(tuinvgl.BRON) | {"bezetting", "geplant", "geoogst", "uitval"} | set(UUR_SLEUTELS)
    ontbreekt = {}
    for k, delen in per.items():
        ontbreekt[k] = {}
        for s in alle - set(delen):
            if s in ALLEEN_TUIN and k != HELE_TUIN:
                ontbreekt[k][s] = "Alleen voor de hele kas gemeten"
            elif s in UUR_SLEUTELS:
                ontbreekt[k][s] = "Geen klimaat per uur in deze periode (uit de Priva-bestanden op de NAS)"
            else:
                ontbreekt[k][s] = tuinvgl.ontbreekt_tekst(g, tuin_id, s, van, tot)
    return {
        "kolommen": [kolom(a) for a in afds] + [HELE_TUIN],
        "waarden": {k: {s: tuinvgl.waarde(d, s) for s, d in delen.items()} for k, delen in per.items()},
        "n": {k: {s: d[2] for s, d in delen.items()} for k, delen in per.items()},
        "verwacht": {k: {s: d[3] for s, d in delen.items() if d[3] is not None} for k, delen in per.items()},
        "ontbreekt": ontbreekt,
    }


def _afd_lijst(paren, decimalen=1, eenheid="°C", teken=True):
    """[("Afd. 2", 1.4), …] → "afd. 2 (+1,4 °C), afd. 3 (+1,1 °C)"."""
    opmaak = fmt_verschil if teken else fmt_getal
    return ", ".join(f"{k.lower()} ({opmaak(w, decimalen, eenheid)})" for k, w in paren)


def opvallend(nu, toen, n, verwacht, label_toen, dagen):
    """
    Korte zinnen (markdown) over wat er opvalt, belangrijkste eerst. nu/toen/n/verwacht: {kolom: {sleutel:
    waarde}} uit tabelwaarden (toen = de vergelijkingsperiode, mag leeg zijn); dagen: lengte van de periode.
    """
    zinnen = []
    tuin, tuin_toen = nu.get(HELE_TUIN, {}), toen.get(HELE_TUIN, {})
    afds = {k: w for k, w in nu.items() if k != HELE_TUIN}

    def per_afd(sleutel):
        return {k: w[sleutel] for k, w in afds.items() if w.get(sleutel) is not None}

    afwijking = per_afd("afwijking")
    boven = sorted(((k, w) for k, w in afwijking.items() if w >= DREMPEL_LICHTLIJN), key=lambda p: -p[1])
    onder = sorted(((k, w) for k, w in afwijking.items() if w <= -DREMPEL_LICHTLIJN), key=lambda p: p[1])
    if boven:
        zinnen.append(f"**Warmer dan de lichtlijn**: {_afd_lijst(boven)}.")
    if onder:
        zinnen.append(f"**Kouder dan de lichtlijn**: {_afd_lijst(onder)}.")

    temp = per_afd("temp")
    if len(temp) > 1:
        warmst, koudst = max(temp, key=temp.get), min(temp, key=temp.get)
        if temp[warmst] - temp[koudst] >= DREMPEL_AFDELINGEN:
            zinnen.append(f"**Verschil tussen afdelingen**: {koudst.lower()} was "
                          f"{fmt_getal(temp[warmst] - temp[koudst], 1, '°C')} kouder dan {warmst.lower()} "
                          f"({fmt_getal(temp[koudst], 1, '°C')} tegen {fmt_getal(temp[warmst], 1, '°C')}).")

    rv_hoog = sorted(((k, w) for k, w in per_afd("rv_hoog").items() if w >= DREMPEL_RV_UREN), key=lambda p: -p[1])
    if rv_hoog:
        per_dag = "" if dagen == 1 else " per dag"
        zinnen.append(f"**Hoge RV**: " + ", ".join(f"{k.lower()} {fmt_kort(w, 1)} uur{per_dag}" for k, w in rv_hoog)
                      + f" boven {RV_HOOG} %.")

    hoog = sorted(((k, w) for k, w in per_afd("temp_max").items() if w >= TEMP_HOOG), key=lambda p: -p[1])
    laag = sorted(((k, w) for k, w in per_afd("temp_min").items() if w <= TEMP_LAAG), key=lambda p: p[1])
    if hoog:
        zinnen.append(f"**Warm uur**: hoogste uur {_afd_lijst(hoog, teken=False)}.")
    if laag:
        zinnen.append(f"**Koud uur**: laagste uur {_afd_lijst(laag, teken=False)}.")

    if label_toen:
        for sleutel, naam, drempel, eenheid in (("temp", "Etmaaltemperatuur", DREMPEL_TEMP_VERSCHIL, "°C"),
                                                ("rv", "RV", DREMPEL_RV_VERSCHIL, "%")):
            a, b = tuin.get(sleutel), tuin_toen.get(sleutel)
            if a is not None and b is not None and abs(a - b) >= drempel:
                richting = "hoger" if a > b else "lager"
                zinnen.append(f"**{naam} {fmt_getal(abs(a - b), 1 if eenheid == '°C' else 0, eenheid)} {richting}** "
                              f"dan {label_toen} ({fmt_getal(a, 1 if eenheid == '°C' else 0, eenheid)} tegen "
                              f"{fmt_getal(b, 1 if eenheid == '°C' else 0, eenheid)}).")
        for sleutel, naam in (("lichtsom", "Lichtsom"), ("water", "Watergift"), ("energie", "Energie")):
            a, b = tuin.get(sleutel), tuin_toen.get(sleutel)
            if a == 0 and b:
                zinnen.append(f"**Geen {naam.lower()}**, {label_toen} wel.")
            elif a is not None and b and abs(a - b) / b >= DREMPEL_RELATIEF:
                zinnen.append(f"**{naam} {fmt_getal(abs(a - b) / b * 100, 0, '%')} "
                              f"{'hoger' if a > b else 'lager'}** dan {label_toen}.")

    k_n, k_v = n.get(HELE_TUIN, {}).get("temp"), verwacht.get(HELE_TUIN, {}).get("temp")
    if k_n is not None and k_v and k_n < k_v:
        zinnen.append(f"Klimaat niet compleet: {k_n} van {k_v} dagen met data.")
    elif tuin.get("temp") is None and tuin.get("temp_max") is None:
        zinnen.append("Geen klimaatdata in deze periode.")
    return zinnen


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

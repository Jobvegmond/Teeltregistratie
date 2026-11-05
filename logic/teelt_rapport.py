"""
Het rapport "Teelt afgerond" dat gemaild wordt zodra van een teelt (alle vakken uit één plantweek, beide tuinen)
het laatste vak geoogst is: per tuin en in totaal de kengetallen (gewogen naar m², zoals op de pagina Teelt) met
dezelfde plantweek van vorig jaar ernaast, en daaronder elk vak.

De vakken komen uit logic.teeltvergelijking (teelt + met_dagdata), dus dezelfde cijfers als in de app.
Alleen rekenwerk en opmaak; versturen doet teelt_rapport.py. Tests in tests/test_teelt_rapport.py.
"""
from logic import mailopmaak as mo
from logic import teeltvergelijking as teeltvgl
from logic.weken import weeknummer
from utils.format import LEEG, fmt_getal, fmt_verschil

DAGEN = ("ma", "di", "wo", "do", "vr", "za", "zo")


def week_dag(datum, plantweek=False):
    """Een datum als weeknummer en dag ("wk 34 ma"): een plantdatum in de ISO-plantweek (zoals de teeltcode),
    een andere datum in de week van zondag t/m zaterdag (zoals overal in de app)."""
    if not datum:
        return LEEG
    week = datum.isocalendar()[1] if plantweek else weeknummer(datum)
    return f"wk {week} {DAGEN[datum.weekday()]}"

# (sleutel, kop, decimalen, eenheid) per vak en in de samenvatting.
KENGETALLEN = [
    ("geplant", "Planten", 0, ""), ("geoogst", "Stelen", 0, ""), ("uitval", "Uitval", 1, "%"),
    ("teeltduur", "Teeltduur", 0, "d"), ("fase1", "Fase 1 (planten → Florgib)", 0, "d"),
    ("fase2", "Fase 2 (Florgib → oogst)", 0, "d"), ("lengte_fg", "Lengte bij Florgib", 1, "cm"),
    ("lengte", "Oogstlengte", 1, "cm"), ("gewicht", "Oogstgewicht", 0, "g"),
    ("lichtsom", "Lichtsom binnen per dag", 0, "J/cm²"), ("temp", "Etmaaltemperatuur", 1, "°C"),
    ("afwijking", "Afwijking berekende etmaaltemp.", 1, "°C"), ("water", "Water", 0, "l/m²"),
    ("warmte", "Energie (warmte + gas)", 0, "MJ/m²"), ("stek", "Stekcijfer", 1, ""),
]
TEKEN = {"afwijking"}
# In de tabel per vak niet (wel in de samenvatting): de aantallen, de twee fasen, klimaat, input en stek. Per vak
# blijven de datums, uitval, teeltduur, de lengtes en het gewicht.
NIET_PER_VAK = {"geplant", "geoogst", "fase1", "fase2", "lichtsom", "temp", "afwijking", "water", "warmte", "stek"}
# Korte koppen voor de tabel per vak.
KORT = {"geplant": "Planten", "geoogst": "Stelen", "uitval": "Uitval %", "teeltduur": "Duur d", "fase1": "Fase 1 d",
        "fase2": "Fase 2 d", "lengte_fg": "Lengte FG cm", "lengte": "Lengte cm", "gewicht": "Gewicht g",
        "lichtsom": "Licht J/cm²", "temp": "Etmaal °C", "afwijking": "Afw. °C", "water": "Water l/m²",
        "warmte": "Energie MJ/m²", "stek": "Stek"}


def afgeronde_plantweken(vakken):
    """{plantweek: (laatste oogstdatum, vakken)} van de plantweken waarvan elk vak geoogst is."""
    per_week = {}
    for t in vakken:
        per_week.setdefault(teeltvgl.plantweek(t["start"]), []).append(t)
    return {w: (max(t["oogst_echt"] for t in groep), groep)
            for w, groep in per_week.items() if groep and all(t["oogst_echt"] for t in groep)}


def onderwerp(plantweek):
    jaar, week = plantweek
    return f"Teelt afgerond; plantweek {week} ({jaar})"


def _waarde(sleutel, waarde, met_eenheid=True):
    if waarde is None or waarde != waarde:
        return LEEG
    decimalen, eenheid = next((d, e) for s, _, d, e in KENGETALLEN if s == sleutel)
    eenheid = eenheid if met_eenheid else ""
    return fmt_verschil(waarde, decimalen, eenheid) if sleutel in TEKEN else fmt_getal(waarde, decimalen, eenheid)


def samenvatting(vakken, vorig_jaar, tuinen):
    """
    [(kengetal, {kolom: tekst})] met kolommen per tuin (alleen tuinen met vakken), Totaal en Vorig jaar (het totaal
    van dezelfde plantweek een jaar eerder). tuinen: [(naam, tuin_id)].
    """
    met_vakken = [(n, i) for n, i in tuinen if any(t["tuin_id"] == i for t in vakken)]
    nu = teeltvgl.tabelwaarden(vakken, met_vakken)["waarden"]
    toen = teeltvgl.tabelwaarden(vorig_jaar, tuinen)["waarden"] if vorig_jaar else {}
    kolommen = [n for n, _ in met_vakken] + (["Totaal"] if len(met_vakken) > 1 else [])
    rijen = []
    for sleutel, kop, _, _ in KENGETALLEN:
        rij = {k: _waarde(sleutel, nu.get(k, {}).get(sleutel)) for k in kolommen}
        rij["Vorig jaar"] = _waarde(sleutel, toen.get("Totaal" if len(tuinen) > 1 else tuinen[0][0], {}).get(sleutel))
        rijen.append((kop, rij))
    return kolommen + ["Vorig jaar"], rijen


def per_vak(vakken, tuinnaam, afdeling_volgorde=None):
    """[{kolom: tekst}] per vak, op tuin → afdeling → vak."""
    volgorde = afdeling_volgorde or (lambda tuin_id, afd: afd or 0)
    uit = []
    for t in sorted(vakken, key=lambda t: (tuinnaam.get(t["tuin_id"], ""), volgorde(t["tuin_id"], t["afdeling"]),
                                           t["vak"])):
        rij = {"Tuin": tuinnaam.get(t["tuin_id"], "?"), "Vak": str(t["vak"]),
               "Geplant": week_dag(t["start"], plantweek=True), "Florgib": week_dag(t.get("florgib")),
               "Oogst": week_dag(t.get("oogst_echt"))}
        for sleutel, *_ in KENGETALLEN:
            if sleutel not in NIET_PER_VAK:
                rij[KORT[sleutel]] = _waarde(sleutel, t.get(sleutel), met_eenheid=False)
        uit.append(rij)
    return uit


# De tegels bovenaan: de belangrijkste kengetallen van de hele teelt, met de plantweek van vorig jaar eronder.
TEGELS = ("Stelen", "Uitval", "Teeltduur", "Oogstlengte", "Oogstgewicht", "Energie (warmte + gas)")


def tegels(samen, kolommen):
    """De tegels uit de samenvatting: het Totaal (of de ene tuin), met "vorig jaar …" eronder."""
    kolom = "Totaal" if "Totaal" in kolommen else kolommen[0]
    rijen = dict(samen)
    uit = []
    for naam in TEGELS:
        rij = rijen.get(naam)
        if not rij or rij.get(kolom, LEEG) == LEEG:
            continue
        vorig = rij.get("Vorig jaar", LEEG)
        uit.append({"label": naam.split(" (")[0], "waarde": rij[kolom],
                    "sub": f"vorig jaar {vorig}" if vorig != LEEG else None})
    return uit


def bericht(plantweek, vakken, vorig_jaar, tuinen, laatste_oogst, app_url=None, afdeling_volgorde=None):
    """(onderwerp, platte tekst, html) van het rapport."""
    tuinnaam = dict((i, n) for n, i in tuinen)
    jaar, week = plantweek
    kolommen, samen = samenvatting(vakken, vorig_jaar, tuinen)
    vak_rijen = per_vak(vakken, tuinnaam, afdeling_volgorde)
    vak_koppen = ["Tuin", "Vak", "Geplant", "Florgib", "Oogst"] + [KORT[s] for s, *_ in KENGETALLEN
                                                                 if s not in NIET_PER_VAK]
    per_tuin = ", ".join(f"{n}: {sum(1 for t in vakken if t['tuin_id'] == i)}" for n, i in tuinen
                         if any(t["tuin_id"] == i for t in vakken))
    inleiding = (f"Plantweek {week} ({jaar}) is afgerond: het laatste vak is geoogst in {week_dag(laatste_oogst)} "
                 f"({laatste_oogst:%d-%m-%Y}). "
                 f"{len(vakken)} vakken ({per_tuin}).")
    voet = ("Gemiddelden gewogen naar de m² van het vak; uitval, lengte en gewicht van de afgeronde vakken. Vorig jaar "
            f"= plantweek {week} van {jaar - 1}" + ("." if vorig_jaar else " (geen vakken).")
            + " Energie = warmte en gas per bezette m² over de teelt.")

    tekst = [inleiding, "", "Samenvatting:"]
    tekst += [f"  {kop}: " + " | ".join(f"{k} {rij[k]}" for k in kolommen) for kop, rij in samen]
    tekst += ["", "Per vak:", "  " + " ; ".join(vak_koppen)]
    tekst += ["  " + " ; ".join(rij[k] for k in vak_koppen) for rij in vak_rijen]
    tekst += ["", voet] + ([f"Teeltregistratie: {app_url}"] if app_url else [])

    html_tekst = mo.omhulsel(
        mo.alinea(inleiding)
        + mo.tegels(tegels(samen, kolommen), breedte=6)
        + mo.sectiekop("Samenvatting")
        + mo.tabel(["Kengetal"] + kolommen, [{"Kengetal": kop, **rij} for kop, rij in samen])
        + mo.sectiekop("Per vak")
        + mo.tabel(vak_koppen, vak_rijen, eerste_links=5)
        + mo.voetnoot(mo.e(voet))
        + (f'<p><a href="{mo.e(app_url)}" style="color:{mo.GROEN}">Open de teeltregistratie</a></p>' if app_url else ""),
        breedte=900, kop=mo.kop(f"Teelt afgerond: plantweek {week} ({jaar})", "Rapport per afgeronde plantweek"),
        titel=onderwerp(plantweek))
    return onderwerp(plantweek), "\n".join(tekst), html_tekst

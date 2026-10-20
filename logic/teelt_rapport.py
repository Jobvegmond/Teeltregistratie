"""
Het rapport "Teelt afgerond" dat gemaild wordt zodra van een teelt (alle vakken uit één plantweek, beide tuinen)
het laatste vak geoogst is: per tuin en in totaal de kengetallen (gewogen naar m², zoals op de pagina Teelt) met
dezelfde plantweek van vorig jaar ernaast, en daaronder elk vak.

De vakken komen uit logic.teeltvergelijking (teelt + met_dagdata), dus dezelfde cijfers als in de app.
Alleen rekenwerk en opmaak; versturen doet teelt_rapport.py. Tests in tests/test_teelt_rapport.py.
"""
import html

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
# In de tabel per vak niet (wel in de samenvatting): de aantallen en de twee fasen.
NIET_PER_VAK = {"geplant", "geoogst", "fase1", "fase2"}
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


def _tabel_html(koppen, rijen, eerste_links=1):
    stijl_kop = "padding:4px 8px;border-bottom:2px solid #2E6A4C;text-align:{};white-space:nowrap;font-size:12px"
    stijl_cel = "padding:3px 8px;border-bottom:1px solid #e3e3e0;text-align:{};white-space:nowrap;font-size:12px"
    kop = "".join(f'<th style="{stijl_kop.format("left" if i < eerste_links else "right")}">{html.escape(k)}</th>'
                  for i, k in enumerate(koppen))
    body = "".join("<tr>" + "".join(
        f'<td style="{stijl_cel.format("left" if i < eerste_links else "right")}">{html.escape(str(rij.get(k, "")))}</td>'
        for i, k in enumerate(koppen)) + "</tr>" for rij in rijen)
    return f'<table style="border-collapse:collapse;font-family:Arial,sans-serif">{kop and f"<tr>{kop}</tr>"}{body}</table>'


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

    samen_html = _tabel_html(["Kengetal"] + kolommen, [{"Kengetal": kop, **rij} for kop, rij in samen])
    html_tekst = (
        '<div style="font-family:Arial,sans-serif;font-size:13px;color:#1f1f1f">'
        f'<h2 style="color:#2E6A4C;margin:0 0 6px">Teelt afgerond: plantweek {week} ({jaar})</h2>'
        f"<p>{html.escape(inleiding)}</p><h3 style=\"margin:14px 0 4px\">Samenvatting</h3>{samen_html}"
        f'<h3 style="margin:14px 0 4px">Per vak</h3>{_tabel_html(vak_koppen, vak_rijen, eerste_links=5)}'
        f'<p style="color:#6f6f6a;font-size:11px">{html.escape(voet)}</p>'
        + (f'<p><a href="{html.escape(app_url)}">Open de teeltregistratie</a></p>' if app_url else "")
        + "</div>")
    return onderwerp(plantweek), "\n".join(tekst), html_tekst

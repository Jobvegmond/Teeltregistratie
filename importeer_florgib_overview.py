"""
Vult de Florgib-datum (teelten.datum_half) van vakken in de app met de "Fg"
uit het blad Overview van de klimaatregistratie (tuin 1 en tuin 3), en de
lengte bij de Florgib (teelten.lengte_half) met de knoplengte uit het blad
Plantingen (tuin 3, één waarde per plantweek van het lopende jaar). Uit
hetzelfde blad komen voor afgeronde vakken de oogstlengte en het oogstgewicht
(gemiddelde van rijpheid 2-3 en 3-4), als die in de app nog ontbreken.

Bron: Teelt\\Klimaatregistratie tuin 1 kopie.xlsx en tuin 3 kopie.xlsx, gelezen
met analyse.bronnen.lees_florgib_overview (dezelfde lezer als de teelthistorie).

- Alleen vakken zónder Florgib in de app; een registratie in de app wordt
  nooit overschreven. Er wordt niets verwijderd.
- Per vak de eerste Fg na het planten en vóór de oogst (lopend vak: vóór de
  volgende planting in dat vak, anders vóór vandaag).
- Knoplengte: alleen voor vakken mét Florgib en zónder lengte in de app. De
  rij Knoplengte heeft geen jaartal; het jaar is het laatste jaar uit de
  jaarblokken boven in Plantingen (de lopende teelt).
- Oogstlengte en -gewicht: alleen voor afgeronde vakken, alleen lege velden.
  Gewicht = het gemiddelde van "Gewicht 2-3" en "Gewicht 3-4" (rijpheid 2-4);
  staat er maar één, dan dat gewicht met de rijpheid van die rij. De
  rijpheid wordt alleen ingevuld als die leeg is. Een gewicht dat eerder door
  deze import is ingevuld (wijzigingenlog) wordt bijgewerkt.
- Elke ingevulde datum komt in het wijzigingenlog (gebruiker
  "florgib-import").

Gebruik:
    python importeer_florgib_overview.py               # proefrun: toont alleen
    python importeer_florgib_overview.py --uitvoeren   # schrijft naar DATABASE_URL (NAS)
    python importeer_florgib_overview.py --uitvoeren --productie   # ook toegestaan naar Supabase
"""
import argparse
import os
import sys
import warnings
from collections import Counter
from datetime import date, datetime

warnings.filterwarnings("ignore")
HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

import database
from analyse import bronnen


def _d(waarde):
    if not waarde:
        return None
    return waarde if isinstance(waarde, date) else datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def koppel(teelten, overview, vandaag):
    """
    teelten: [{id, tuin, vak, start, oogst, florgib}] (alle vakken, ook met Florgib),
    overview: {tuin: {vak: [Fg-datums]}}. Geeft [(teelt, Fg-datum, aantal Fg in het venster)]
    voor de gestarte vakken zonder Florgib waarvoor Overview een Fg heeft.
    """
    starts = {}
    for t in teelten:
        starts.setdefault((t["tuin"], t["vak"]), []).append(_d(t["start"]))
    uit = []
    for t in teelten:
        start, oogst = _d(t["start"]), _d(t["oogst"])
        if t["florgib"] or start > vandaag:
            continue
        volgende = min((s for s in starts[(t["tuin"], t["vak"])] if s > start), default=None)
        eind = oogst or volgende or vandaag
        fg = sorted(x for x in overview.get(t["tuin"], {}).get(t["vak"], []) if start < x < eind)
        if fg:
            uit.append((t, fg[0], len(fg)))
    return uit


def lees_plantingen(wb, label):
    """
    Blad Plantingen (tuin 3): (jaar, {plantweek: waarde}) uit de rij met `label` in kolom A
    (bijv. "Knoplengte", "Oogstlengte", "Gewicht 3-4"). Rij 1 heeft de weeknummers; het jaar
    is het hoogste jaartal in kolom D (de jaarblokken met temperatuur en licht erboven).
    """
    if "Plantingen" not in wb.sheetnames:
        return None, {}
    rijen = list(wb["Plantingen"].iter_rows(values_only=True))
    weken = rijen[0]
    jaren = [int(r[3]) for r in rijen if len(r) > 3 and isinstance(r[3], (int, float)) and 2000 < r[3] < 2100]
    rij = next((r for r in rijen if r and isinstance(r[0], str) and r[0].strip().lower() == label.lower()), None)
    if rij is None or not jaren:
        return None, {}
    waarden = {int(weken[k]): float(w) for k, w in enumerate(rij)
               if 4 <= k < len(weken) and isinstance(weken[k], (int, float)) and isinstance(w, (int, float))}
    return max(jaren), waarden


def lees_knoplengte(wb):
    return lees_plantingen(wb, "Knoplengte")


def koppel_lengte(teelten, jaar, lengtes, krijgt_florgib=()):
    """
    [(teelt, lengte)] voor de vakken van tuin 3 uit plantweek (jaar, week) met een knoplengte,
    met een Florgib (in de app, of uit deze import: `krijgt_florgib` = ids) en zonder lengte.
    """
    uit = []
    for t in teelten:
        if t["tuin"] != 3 or t.get("lengte_half") is not None:
            continue
        if not (t["florgib"] or t["id"] in krijgt_florgib):
            continue
        j, w, _ = _d(t["start"]).isocalendar()
        if j == jaar and w in lengtes:
            uit.append((t, lengtes[w]))
    return uit


def gewicht_per_week(g23, g34):
    """{plantweek: (gewicht, rijpheid)}: het gemiddelde van rijpheid 2-3 en 3-4, of het enige dat er is."""
    uit = {}
    for w in set(g23) | set(g34):
        if w in g23 and w in g34:
            uit[w] = ((g23[w] + g34[w]) / 2, "2-4")
        else:
            uit[w] = (g23[w], "2-3") if w in g23 else (g34[w], "3-4")
    return uit


def koppel_oogst(teelten, jaar, lengtes, gewichten, eigen=()):
    """
    [(teelt, {kolom: waarde})] voor de afgeronde vakken van tuin 3 uit plantweek (jaar, week):
    lengte_eind uit `lengtes` en oogstgewicht + rijpheid uit `gewichten` ({week: (gewicht,
    rijpheid)}), alleen waar die in de app leeg zijn. `eigen` = ids waarvan het gewicht eerder
    door deze import is ingevuld: dat gewicht (en de rijpheid) mag worden bijgewerkt.
    """
    uit = []
    for t in teelten:
        if t["tuin"] != 3 or not t["oogst"]:
            continue
        j, w, _ = _d(t["start"]).isocalendar()
        if j != jaar:
            continue
        velden = {}
        if t.get("lengte_eind") is None and w in lengtes:
            velden["lengte_eind"] = lengtes[w]
        if w in gewichten and (t.get("oogstgewicht") is None or t["id"] in eigen):
            gewicht, rijpheid = gewichten[w]
            if t.get("oogstgewicht") != gewicht:
                velden["oogstgewicht"] = gewicht
            if (not t.get("rijpheid") or t["id"] in eigen) and t.get("rijpheid") != rijpheid:
                velden["rijpheid"] = rijpheid
        if velden:
            uit.append((t, velden))
    return uit


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uitvoeren", action="store_true", help="echt schrijven (anders proefrun)")
    parser.add_argument("--productie", action="store_true", help="schrijven naar Supabase toestaan")
    args = parser.parse_args()
    if args.uitvoeren and "supabase" in (database.DATABASE_URL or "") and not args.productie:
        sys.exit("GESTOPT: DATABASE_URL wijst naar Supabase. Gebruik --productie als dat de bedoeling is.")

    overview = {tuin: bronnen.lees_florgib_overview(bronnen._open(pad)) for tuin, pad in bronnen.EXCEL.items()}
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, tu.nummer, v.vaknummer, t.code, t.datum_teelt_start, t.datum_oogst, t.datum_half,
                   t.lengte_half, t.lengte_eind, t.oogstgewicht, t.rijpheid
            FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id JOIN tuinen tu ON tu.id = v.tuin_id
        """)
        teelten = [dict(zip(("id", "tuin", "vak", "code", "start", "oogst", "florgib", "lengte_half",
                             "lengte_eind", "oogstgewicht", "rijpheid"), r)) for r in cur.fetchall()]

    gevonden = koppel(teelten, overview, date.today())
    per_tuin = Counter(t["tuin"] for t, _, _ in gevonden)
    print(f"Doel: {'Supabase (productie)' if 'supabase' in (database.DATABASE_URL or '') else 'NAS / lokaal'}")
    print(f"{len(gevonden)} vakken krijgen een Florgib uit Overview: "
          + ", ".join(f"tuin {tuin} {n}" for tuin, n in sorted(per_tuin.items())))
    for t, fg, n in sorted(gevonden, key=lambda g: (g[0]["tuin"], _d(g[0]["start"]), g[0]["vak"])):
        print(f"  tuin {t['tuin']} vak {t['vak']:>2} {t['code'] or '-':>7} geplant {_d(t['start']):%d-%m-%y} "
              f"→ Florgib {fg:%d-%m-%y}" + (f"  ({n} Fg in het venster, de eerste genomen)" if n > 1 else ""))
    wb3 = bronnen._open(bronnen.EXCEL[3])
    jaar, knop = lees_knoplengte(wb3)
    lengtes = koppel_lengte(teelten, jaar, knop, {t["id"] for t, _, _ in gevonden})
    print(f"\nKnoplengte tuin 3 ({jaar}, plantweek {min(knop, default='-')} t/m {max(knop, default='-')}): "
          f"{len(lengtes)} vakken krijgen een lengte bij de Florgib")
    for t, lengte in sorted(lengtes, key=lambda g: (_d(g[0]["start"]), g[0]["vak"])):
        print(f"  vak {t['vak']:>2} {t['code'] or '-':>7} geplant {_d(t['start']):%d-%m-%y} → {lengte:g} cm")
    # Gewichten die eerder door deze import zijn ingevuld, mogen worden bijgewerkt.
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT entiteit_id FROM wijzigingenlog WHERE gebruiker = 'florgib-import' "
                    "AND omschrijving LIKE '%%oogstgewicht%%'")
        eigen = {int(r[0]) for r in cur.fetchall() if r[0]}
    gewichten = gewicht_per_week(lees_plantingen(wb3, "Gewicht 2-3")[1], lees_plantingen(wb3, "Gewicht 3-4")[1])
    oogst = koppel_oogst(teelten, jaar, lees_plantingen(wb3, "Oogstlengte")[1], gewichten, eigen)
    print(f"\nOogstlengte en -gewicht tuin 3 ({jaar}): {len(oogst)} vakken")
    for t, velden in sorted(oogst, key=lambda g: (_d(g[0]["start"]), g[0]["vak"])):
        print(f"  vak {t['vak']:>2} {t['code'] or '-':>7} geplant {_d(t['start']):%d-%m-%y} → "
              + ", ".join(f"{k} {w:g}" if isinstance(w, float) else f"{k} {w}" for k, w in velden.items()))
    if not args.uitvoeren:
        print("\nProefrun: er is niets geschreven. Draai met --uitvoeren om weg te schrijven.")
        return

    with database.get_connection() as conn:
        cur = conn.cursor()
        geschreven = 0
        for t, fg, _ in gevonden:
            # Alleen als er nog steeds geen Florgib staat (niets overschrijven).
            cur.execute("UPDATE teelten SET datum_half = %s WHERE id = %s AND datum_half IS NULL",
                        (str(fg), t["id"]))
            geschreven += cur.rowcount
        lengte_geschreven = 0
        for t, lengte in lengtes:
            cur.execute("UPDATE teelten SET lengte_half = %s WHERE id = %s AND lengte_half IS NULL",
                        (lengte, t["id"]))
            lengte_geschreven += cur.rowcount
        oogst_geschreven = 0
        for t, velden in oogst:
            # Per kolom alleen als die nog leeg is, of (gewicht/rijpheid) eerder door deze import is gevuld.
            for kolom, waarde in velden.items():
                if t["id"] in eigen and kolom in ("oogstgewicht", "rijpheid"):
                    cur.execute(f"UPDATE teelten SET {kolom} = %s WHERE id = %s", (waarde, t["id"]))
                else:
                    cur.execute(f"UPDATE teelten SET {kolom} = %s WHERE id = %s AND {kolom} IS NULL",
                                (waarde, t["id"]))
                oogst_geschreven += cur.rowcount
        conn.commit()
    for t, fg, _ in gevonden:
        database.log_wijziging("florgib-import", "gewijzigd", "teelten", t["id"],
                               f"Vak {t['vak']} ({t['code'] or '-'}): Florgib {fg:%d-%m-%y} uit Overview "
                               "(klimaatregistratie)")
    for t, lengte in lengtes:
        database.log_wijziging("florgib-import", "gewijzigd", "teelten", t["id"],
                               f"Vak {t['vak']} ({t['code'] or '-'}): lengte bij Florgib {lengte:g} cm uit "
                               "knoplengte (klimaatregistratie)")
    for t, velden in oogst:
        database.log_wijziging("florgib-import", "gewijzigd", "teelten", t["id"],
                               f"Vak {t['vak']} ({t['code'] or '-'}): "
                               + ", ".join(f"{k} {w:g}" if isinstance(w, float) else f"{k} {w}" for k, w in velden.items())
                               + " uit Plantingen (klimaatregistratie)")
    print(f"\n{geschreven} vakken een Florgib-datum, {lengte_geschreven} vakken een lengte bij de Florgib, "
          f"{oogst_geschreven} oogstvelden ingevuld.")


if __name__ == "__main__":
    main()

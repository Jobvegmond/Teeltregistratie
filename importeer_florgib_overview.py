"""
Vult de Florgib-datum (teelten.datum_half) van vakken in de app met de "Fg"
uit het blad Overview van de klimaatregistratie (tuin 1 en tuin 3).

Bron: Teelt\\Klimaatregistratie tuin 1 kopie.xlsx en tuin 3 kopie.xlsx, gelezen
met analyse.bronnen.lees_florgib_overview (dezelfde lezer als de teelthistorie).

- Alleen vakken zónder Florgib in de app; een registratie in de app wordt
  nooit overschreven. Er wordt niets verwijderd.
- Per vak de eerste Fg na het planten en vóór de oogst (lopend vak: vóór de
  volgende planting in dat vak, anders vóór vandaag).
- De lengte bij de Florgib staat niet in Overview en blijft leeg.
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
            SELECT t.id, tu.nummer, v.vaknummer, t.code, t.datum_teelt_start, t.datum_oogst, t.datum_half
            FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id JOIN tuinen tu ON tu.id = v.tuin_id
        """)
        teelten = [dict(zip(("id", "tuin", "vak", "code", "start", "oogst", "florgib"), r)) for r in cur.fetchall()]

    gevonden = koppel(teelten, overview, date.today())
    per_tuin = Counter(t["tuin"] for t, _, _ in gevonden)
    print(f"Doel: {'Supabase (productie)' if 'supabase' in (database.DATABASE_URL or '') else 'NAS / lokaal'}")
    print(f"{len(gevonden)} vakken krijgen een Florgib uit Overview: "
          + ", ".join(f"tuin {tuin} {n}" for tuin, n in sorted(per_tuin.items())))
    for t, fg, n in sorted(gevonden, key=lambda g: (g[0]["tuin"], _d(g[0]["start"]), g[0]["vak"])):
        print(f"  tuin {t['tuin']} vak {t['vak']:>2} {t['code'] or '-':>7} geplant {_d(t['start']):%d-%m-%y} "
              f"→ Florgib {fg:%d-%m-%y}" + (f"  ({n} Fg in het venster, de eerste genomen)" if n > 1 else ""))
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
        conn.commit()
    for t, fg, _ in gevonden:
        database.log_wijziging("florgib-import", "gewijzigd", "teelten", t["id"],
                               f"Vak {t['vak']} ({t['code'] or '-'}): Florgib {fg:%d-%m-%y} uit Overview "
                               "(klimaatregistratie)")
    print(f"\n{geschreven} vakken bijgewerkt.")


if __name__ == "__main__":
    main()

"""
Vult teelt_historie en teelt_historie_week: de afgeronde teelten met hun
klimaat per week, als leerdata voor het teeltmodel (zie logic/teeltmodel.py en
analyse/bronnen.py voor de keuzes).

Bron: Teelt\\Klimaatregistratie tuin 1 kopie.xlsx en tuin 3 kopie.xlsx (tuin 3
alleen code S) plus de database zelf (teelten, klimaatdata_dag).

- Eén regel per teelt (tuin, plantjaar, plantweek, vak); opnieuw draaien werkt
  bij (upsert) en verdubbelt niets. Er wordt nooit iets verwijderd.
- Weekwaarden: Excel waar dat er is (Excel gaat voor), anders het
  weekgemiddelde uit klimaatdata_dag van de afdeling.
- Oogstdatums die precies de teeltduur-tabel zijn (bij een eerdere import
  geschat) worden niet overgenomen.

Gebruik:
    python importeer_teelt_historie.py               # proefrun: toont alleen
    python importeer_teelt_historie.py --uitvoeren   # schrijft naar DATABASE_URL (NAS)
    python importeer_teelt_historie.py --uitvoeren --productie   # ook toegestaan naar Supabase
"""
import argparse
import os
import sys
import warnings
from collections import Counter

warnings.filterwarnings("ignore")
HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

from psycopg2.extras import execute_values

import database
from analyse.bronnen import bouw_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uitvoeren", action="store_true", help="echt schrijven (anders proefrun)")
    parser.add_argument("--productie", action="store_true", help="schrijven naar Supabase toestaan")
    args = parser.parse_args()
    if args.uitvoeren and "supabase" in (database.DATABASE_URL or "") and not args.productie:
        sys.exit("GESTOPT: DATABASE_URL wijst naar Supabase. Gebruik --productie als dat de bedoeling is.")

    database.init_db()
    teelten, _klimaat, log = bouw_dataset()
    log.pop("Florgib in app én Overview (verschil in dagen)", None)
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT nummer, id FROM tuinen")
        tuin_id = dict(cur.fetchall())

    print(f"{len(teelten)} afgeronde teelten klaar voor de historie. Afgevallen: {log}")
    print("  per tuin en bron:", dict(Counter((t["tuin"], t["bron"]) for t in teelten)))
    print("  oogstdatum per nauwkeurigheid:", dict(Counter(t["precisie"] for t in teelten)))
    print("  met Florgib:", sum(1 for t in teelten if t["florgib"]),
          "| weekwaarden:", dict(Counter(b for t in teelten for (_, _, b) in t["weken"].values())))
    if not args.uitvoeren:
        print("Proefrun: niets geschreven. Gebruik --uitvoeren om te schrijven.")
        return

    with database.get_connection() as conn:
        cur = conn.cursor()
        for t in teelten:
            cur.execute("""
                INSERT INTO teelt_historie (tuin_id, vaknummer, afdeling, code, plantjaar, plantweek, startdatum,
                    start_precisie, oogstdatum, oogst_precisie, teeltduur_dagen, florgib_datum, florgib_bron,
                    lengte_eind, oogstgewicht, teelt_id, bron)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tuin_id, plantjaar, plantweek, vaknummer) DO UPDATE SET
                    afdeling = EXCLUDED.afdeling, code = EXCLUDED.code, startdatum = EXCLUDED.startdatum,
                    start_precisie = EXCLUDED.start_precisie, oogstdatum = EXCLUDED.oogstdatum,
                    oogst_precisie = EXCLUDED.oogst_precisie, teeltduur_dagen = EXCLUDED.teeltduur_dagen,
                    florgib_datum = EXCLUDED.florgib_datum, florgib_bron = EXCLUDED.florgib_bron,
                    lengte_eind = EXCLUDED.lengte_eind, oogstgewicht = EXCLUDED.oogstgewicht,
                    teelt_id = EXCLUDED.teelt_id, bron = EXCLUDED.bron, bijgewerkt_op = NOW()
                RETURNING id
            """, (tuin_id[t["tuin"]], t["vak"], t["afdeling"], t["code"], t["jaar"], t["plantweek"], str(t["start"]),
                  t["start_precisie"], str(t["oogst"]), t["precisie"], int(t["duur"]),
                  str(t["florgib"]) if t["florgib"] else None, t["florgib_bron"], t["lengte"], t["gewicht"],
                  t["teelt_id"], t["bron"]))
            historie_id = cur.fetchone()[0]
            execute_values(cur, """
                INSERT INTO teelt_historie_week (historie_id, isojaar, isoweek, etmaal_temp, lichtsom_binnen, bron)
                VALUES %s
                ON CONFLICT (historie_id, isojaar, isoweek) DO UPDATE SET
                    etmaal_temp = EXCLUDED.etmaal_temp, lichtsom_binnen = EXCLUDED.lichtsom_binnen, bron = EXCLUDED.bron
            """, [(historie_id, j, w, T, L, b) for (j, w), (T, L, b) in sorted(t["weken"].items())])
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM teelt_historie")
        n_teelt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM teelt_historie_week")
        n_week = cur.fetchone()[0]
    database.log_wijziging("teelthistorie-import", "gewijzigd", "teelt_historie", None,
                           f"{len(teelten)} teelten bijgewerkt (totaal {n_teelt} teelten, {n_week} weken)")
    print(f"Geschreven: teelt_historie {n_teelt} regels, teelt_historie_week {n_week} regels.")


if __name__ == "__main__":
    main()

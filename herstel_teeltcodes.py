"""
Zet teelt-codes recht: elke code wordt wat genereer_teelt_code ervan maakt
(jaar + plantweek + tuin + vak, sinds 2.7.0). Ook het prognoselogboek krijgt
de nieuwe code van zijn vak.

Eerder gebruikt om codes met het kalenderjaar (in plaats van het ISO-jaar van
de plantweek) recht te zetten; sinds 2.7.0 om de 6-cijferige codes om te zetten
naar 7 cijfers met de tuin erin (260904 in tuin 3 -> 2609304). De code is een
label: er hangt geen berekening aan, alles is gekoppeld via het id.

Gebruik:
    python herstel_teeltcodes.py              # proefdraai: toont alleen
    python herstel_teeltcodes.py --uitvoeren  # past de database in .env aan

Weigert naar Supabase te schrijven tenzij --productie erbij staat.
"""
import argparse
import os
import sys

import database

GEBRUIKER = "codeherstel"


def afwijkende_codes():
    """[(teelt_id, vaknummer, startdatum, oude code, juiste code)] voor alles wat niet klopt."""
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code, tu.nummer
            FROM teelten t
            JOIN teeltvakken v ON v.id = t.teeltvak_id
            JOIN tuinen tu ON tu.id = v.tuin_id
            WHERE v.vaknummer IS NOT NULL
            ORDER BY t.datum_teelt_start, v.vaknummer
        """)
        rijen = cursor.fetchall()
    afwijkend = []
    for teelt_id, vaknummer, start, code, tuin_nummer in rijen:
        juist = database.genereer_teelt_code(start, vaknummer, tuin_nummer)
        if code != juist:
            afwijkend.append((teelt_id, vaknummer, start, code, juist))
    return afwijkend


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uitvoeren", action="store_true", help="echt wegschrijven (anders proefdraai)")
    parser.add_argument("--productie", action="store_true", help="toestaan dat er naar Supabase geschreven wordt")
    args = parser.parse_args()

    if args.uitvoeren and "supabase" in os.environ.get("DATABASE_URL", "") and not args.productie:
        sys.exit("GESTOPT: .env wijst naar Supabase (productie). Voeg --productie toe als dat de bedoeling is.")

    afwijkend = afwijkende_codes()
    print(f"Teelten met een afwijkende code: {len(afwijkend)}")
    for _, vak, start, oud, juist in afwijkend[:15]:
        print(f"  vak {vak:>2}  {start}  {oud} -> {juist}")
    if len(afwijkend) > 15:
        print(f"  … en nog {len(afwijkend) - 15}")
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT COUNT(*) FROM prognose_log p JOIN teelten t ON t.id = p.teelt_id
                          WHERE p.code IS DISTINCT FROM t.code""")
        print(f"Regels in het prognoselogboek met een andere code dan hun vak (vóór het omzetten): "
              f"{cursor.fetchone()[0]}")

    if not afwijkend:
        return
    if not args.uitvoeren:
        print("\nProefdraai: er is niets geschreven. Gebruik --uitvoeren om aan te passen.")
        return

    with database.get_connection() as conn:
        cursor = conn.cursor()
        for teelt_id, _, _, _, juist in afwijkend:
            cursor.execute("UPDATE teelten SET code = %s WHERE id = %s", (juist, teelt_id))
        # Het prognoselogboek volgt de code van zijn vak (de koppeling zelf loopt via teelt_id).
        cursor.execute("""UPDATE prognose_log p SET code = t.code FROM teelten t
                          WHERE t.id = p.teelt_id AND p.code IS DISTINCT FROM t.code""")
        logregels = cursor.rowcount
        conn.commit()
    database.log_wijziging(
        GEBRUIKER, "gewijzigd", "teelt", None,
        f"{len(afwijkend)} teelt-codes omgezet naar jaar + week + tuin + vak ({logregels} regels in het "
        "prognoselogboek mee): " + ", ".join(f"{oud}->{juist}" for _, _, _, oud, juist in afwijkend[:10])
    )
    print(f"\n{len(afwijkend)} codes aangepast, {logregels} regels in het prognoselogboek.")


if __name__ == "__main__":
    main()

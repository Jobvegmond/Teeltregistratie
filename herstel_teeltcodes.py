"""
Zet teelt-codes recht die met het kalenderjaar zijn gemaakt in plaats van met
het ISO-jaar van de plantweek.

Een teelt van 29-12-2025 valt in week 1 van 2026 en hoort dus code '2601..' te
krijgen; er stond '2501..'. Alleen teelten rond de jaarwisseling zijn geraakt.
De code is een label: er hangt geen berekening aan, alleen herkenbaarheid.

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
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code
            FROM teelten t
            JOIN teeltvakken v ON v.id = t.teeltvak_id
            WHERE v.vaknummer IS NOT NULL
            ORDER BY t.datum_teelt_start, v.vaknummer
        """)
        rijen = cursor.fetchall()
    afwijkend = []
    for teelt_id, vaknummer, start, code in rijen:
        juist = database.genereer_teelt_code(start, vaknummer)
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
    for _, vak, start, oud, juist in afwijkend:
        print(f"  vak {vak:>2}  {start}  {oud} -> {juist}")

    if not afwijkend:
        return
    if not args.uitvoeren:
        print("\nProefdraai: er is niets geschreven. Gebruik --uitvoeren om aan te passen.")
        return

    with database.get_connection() as conn:
        cursor = conn.cursor()
        for teelt_id, _, _, _, juist in afwijkend:
            cursor.execute("UPDATE teelten SET code = %s WHERE id = %s", (juist, teelt_id))
        conn.commit()
    database.log_wijziging(
        GEBRUIKER, "gewijzigd", "teelt", None,
        f"{len(afwijkend)} teelt-codes rechtgezet naar het ISO-jaar van de plantweek: "
        + ", ".join(f"{oud}->{juist}" for _, _, _, oud, juist in afwijkend[:10])
    )
    print(f"\n{len(afwijkend)} codes aangepast.")


if __name__ == "__main__":
    main()

"""
Vangplaat- en insectentellingen van PATS (Trap-Eye en PATS-C) in de database: per section uit
config.PATS_SECTIONS de tellingen van de laatste dagen ophalen (integrations/pats.py, alleen lezen) en opslaan
in pats_telling (logic/pats.py). Opnieuw ophalen overschrijft dezelfde dag.

Gebruik:
    python pats_import.py                      # laatste 14 dagen, naar DATABASE_URL
    python pats_import.py --dagen 60           # verder terug (bijv. de eerste keer)
    python pats_import.py --droog              # alleen tonen, niets opslaan
    python pats_import.py --doel productie     # naar DATABASE_URL_PRODUCTIE

Draait elk uur via priva_bestanden.py. Zonder PATS_USER/PATS_PASSW (in .env.taak): een melding, geen fout.
Mislukt het ophalen: een foutcode (mail), de database blijft staan.
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dagen", type=int, default=14, help="hoeveel dagen terug (standaard 14)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    # priva_bestanden.py geeft zijn argumenten aan alle scripts door; --map hoort bij de Priva-scripts.
    parser.add_argument("--map", help=argparse.SUPPRESS)
    return parser.parse_args()


def main():
    args = lees_argumenten()
    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database                     # laadt ook .env
    from config import PATS_SECTIONS
    from integrations import pats as koppeling
    from logic import pats as lp

    login = koppeling.inloggegevens()
    if not login:
        print(f"[{stempel}] Geen PATS_USER/PATS_PASSW; niets gedaan.")
        return
    tot = date.today()
    van = tot - timedelta(days=args.dagen)
    tuinen = {t["nummer"]: t["id"] for t in database.get_tuinen()}
    try:
        api = koppeling.Pats(*login)
        sections = {s["id"]: s for s in api.sections()}
        alle = []
        for section_id, tuin in PATS_SECTIONS.items():
            s = sections.get(section_id)
            if s is None:
                print(f"[{stempel}] Section {section_id} (tuin {tuin}) niet gevonden bij PATS.", file=sys.stderr)
                continue
            klassen = {k["id"]: k.get("label") for k in s.get("detection_classes") or []}
            alle += lp.regels(api.counts(section_id, van, tot), klassen, tuinen[tuin], section_id)
    except Exception as fout:           # netwerk, verlopen toegang: melden, de database blijft staan
        print(f"[{stempel}] FOUT bij ophalen uit PATS: {fout}", file=sys.stderr)
        sys.exit(1)
    per_tuin = {}
    for r in alle:
        per_tuin[r["tuin_id"]] = per_tuin.get(r["tuin_id"], 0) + 1
    samenvatting = (f"{len(alle)} tellingen {van:%d-%m-%y} t/m {tot:%d-%m-%y} ("
                    + ", ".join(f"tuin {nr}: {per_tuin.get(tid, 0)}" for nr, tid in sorted(tuinen.items())) + ")")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting}")
        return
    database.init_db()                  # de tabel pats_telling (2.22.0)
    database.upsert_pats_tellingen(alle)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

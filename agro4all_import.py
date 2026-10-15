"""
Behandelingen (gewasbescherming, biologie, voeding) per vak uit een Agro4all-export in de database.

De export is een JSON-bestand met alle registraties en de vakken waarop ze zijn uitgevoerd (vorm: zie
logic/agro4all.py). Het wordt nu gemaakt via de Agro4all-koppeling van Claude en op de NAS gezet in
/volume2/Appdata/VEMteelt/agro4all/registraties.json. Elke run vervangt alle Agro4all-behandelingen in de
database door wat er in het bestand staat (een registratie kan in Agro4all gewijzigd of verwijderd zijn).
Registraties op de hele tuin vallen weg (zie logic/agro4all.py).

Gebruik:
    python agro4all_import.py                      # bestand uit AGRO4ALL_BESTAND, naar DATABASE_URL
    python agro4all_import.py --bestand pad.json   # een ander bestand
    python agro4all_import.py --droog              # alleen tonen, niets opslaan
    python agro4all_import.py --doel productie     # naar DATABASE_URL_PRODUCTIE

In de container: de map agro4all alleen-lezen erbij (-v /volume2/Appdata/VEMteelt/agro4all:/agro4all:ro);
draait elk uur via priva_bestanden.py. Zonder bestand: een melding, geen fout (er is dan niets nieuws).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

GEBRUIKER = "agro4all"


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bestand", default=os.environ.get("AGRO4ALL_BESTAND", "/agro4all/registraties.json"),
                        help="de Agro4all-export (JSON)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    # priva_bestanden.py geeft zijn argumenten aan alle scripts door; --map hoort bij de Priva-scripts.
    parser.add_argument("--map", help=argparse.SUPPRESS)
    return parser.parse_args()


def main():
    args = lees_argumenten()
    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    pad = Path(args.bestand)
    if not pad.exists():
        print(f"[{stempel}] Geen Agro4all-export in {pad}; niets gedaan.")
        return
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import agro4all as a4

    with open(pad, encoding="utf-8") as f:
        export = json.load(f)
    tuinen = {t["nummer"]: t for t in database.get_tuinen()}
    vakken_per_tuin = {nr: len(database.get_vakgegevens(t["id"])) for nr, t in tuinen.items()}
    middelen, regels = a4.behandelingen(export, vakken_per_tuin)
    for r in regels:
        r["tuin_id"] = tuinen[r.pop("tuin_nummer")]["id"]
    hele, zonder = a4.overgeslagen(export, vakken_per_tuin)
    registraties = {r["registratie"] for r in regels}
    dagen = sorted({r["datum"] for r in regels})
    samenvatting = (f"{len(registraties)} registraties per vak → {len(regels)} regels, {len(middelen)} middelen"
                    + (f" ({dagen[0]:%d-%m-%y} t/m {dagen[-1]:%d-%m-%y})" if dagen else "")
                    + f"; overgeslagen: {hele} op de hele tuin, {zonder} zonder vakken"
                    + f" · export van {export.get('opgehaald', '?')[:16]}")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting}")
        return
    database.init_db()      # de kolommen registratie, doel, mix en aantal_vakken (nieuw in 2.14.0)
    database.vervang_behandelingen(a4.BRON, middelen, regels)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

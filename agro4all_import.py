"""
Behandelingen (gewasbescherming, biologie, voeding) per vak uit een Agro4all-export in de database.

Staat er een toegangstoken in AGRO4ALL_PAT, dan haalt het script eerst alle registraties met hun vakken op
bij Agro4all (integrations/agro4all.py) en schrijft het de export opnieuw; anders leest het de export die de
geplande Claude-taak op de NAS zet (agro4all_samenvoegen.py; JSON, vorm: zie logic/agro4all.py). Elke run vervangt alle Agro4all-behandelingen in de
database door de export (een registratie kan in Agro4all gewijzigd of verwijderd zijn). Registraties op de
hele tuin vallen weg (zie logic/agro4all.py).

Gebruik:
    python agro4all_import.py                      # bestand uit AGRO4ALL_BESTAND, naar DATABASE_URL
    python agro4all_import.py --bestand pad.json   # een ander bestand
    python agro4all_import.py --droog              # alleen tonen, niets opslaan
    python agro4all_import.py --doel productie     # naar DATABASE_URL_PRODUCTIE

In de container: de map agro4all erbij (-v /volume2/Appdata/VEMteelt/agro4all:/agro4all:ro; schrijfbaar
als er met AGRO4ALL_PAT wordt opgehaald). Draait elk uur via priva_bestanden.py. Zonder token en zonder export:
een melding, geen fout. Mislukt het ophalen: een foutcode (mail), de database blijft staan.
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
    parser.add_argument("--niet-ophalen", action="store_true", help="alleen de export inlezen die er staat")
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
    export = None
    from integrations import agro4all as koppeling
    token = koppeling.toegang()
    if not args.niet_ophalen and token:
        from logic import agro4all as a4
        try:
            velden, registraties, secties, methodes = koppeling.ophalen(token)
        except Exception as fout:        # netwerk, verlopen toegang: melden, de database blijft staan
            print(f"[{stempel}] FOUT bij ophalen uit Agro4all: {fout}", file=sys.stderr)
            sys.exit(1)
        export = a4.export_uit_api(velden, registraties, secties, methodes,
                                   datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if not args.droog:              # de export bewaren (ter controle, en als het ophalen later mislukt)
            tijdelijk = pad.with_suffix(".tmp")
            tijdelijk.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")
            tijdelijk.replace(pad)
    elif not pad.exists():
        print(f"[{stempel}] Geen Agro4all-export in {pad} en geen AGRO4ALL_PAT; niets gedaan.")
        return
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import agro4all as a4

    if export is None:
        with open(pad, encoding="utf-8") as f:
            export = json.load(f)
    tuinen = {t["nummer"]: t for t in database.get_tuinen()}
    vakgegevens = {nr: database.get_vakgegevens(t["id"]) for nr, t in tuinen.items()}
    vakken_per_tuin = {nr: len(v) for nr, v in vakgegevens.items()}
    vak_m2 = {(nr, int(vak)): g["oppervlakte_m2"] for nr, v in vakgegevens.items() for vak, g in v.items()}
    middelen, regels = a4.behandelingen(export, vakken_per_tuin, vak_m2)
    for r in regels:
        r["tuin_id"] = tuinen[r.pop("tuin_nummer")]["id"]
    hele, zonder = a4.overgeslagen(export, vakken_per_tuin)
    registraties = {r["registratie"] for r in regels}
    dagen = sorted({r["datum"] for r in regels})
    samenvatting = (f"{len(registraties)} registraties per vak, {len(regels)} regels, {len(middelen)} middelen"
                    + (f" ({dagen[0]:%d-%m-%y} t/m {dagen[-1]:%d-%m-%y})" if dagen else "")
                    + f"; overgeslagen: {hele} op de hele tuin, {zonder} zonder vakken"
                    + f"; export van {export.get('opgehaald', '?')[:16]}")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting}")
        return
    database.init_db()      # de kolommen van behandeling (registratie, doel, mix, … 2.14.0; totalen 2.14.1)
    database.vervang_behandelingen(a4.BRON, middelen, regels)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

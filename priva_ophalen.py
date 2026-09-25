"""
Haalt de laatste afgeronde dagen klimaat- en watergiftdata uit Priva en zet ze
in de database, voor elke tuin die een Priva-site heeft. Bedoeld om periodiek
(bijv. drie keer per dag) te draaien, als vervanger van handmatig op de knop in
de app drukken.

Gebruik:
    python priva_ophalen.py                  # naar de database uit DATABASE_URL
    python priva_ophalen.py --doel productie # naar DATABASE_URL_PRODUCTIE
    python priva_ophalen.py --tuin 1         # alleen die ene tuin
    python priva_ophalen.py --dagen 5        # meer dagen terug (max 5)

Op de NAS draait de app tegen de database op de NAS zelf, terwijl de app die
iedereen gebruikt nog op Render staat. Met --doel productie schrijft deze taak
daarom naar Supabase; de verbinding daarvoor staat in DATABASE_URL_PRODUCTIE,
zodat er geen wachtwoord in de taakregel hoeft.

Synology Taakplanner — nieuwe taak, Door gebruiker gedefinieerd script (root):
    docker exec vemteelt-app python priva_ophalen.py --doel productie
Zet bij Instellingen "Details van uitvoering via e-mail verzenden" aan en vink
"Alleen als het script abnormaal wordt afgesloten" aan: dan krijg je alleen
bericht als het misgaat. Dit script sluit af met een foutcode zodra één tuin
niet gelukt is, dus dat werkt.

Let op: het Priva-abonnement staat 2 API-verzoeken per 5 minuten toe en levert
maximaal 5 dagen historie. Per tuin zijn dat 2 verzoeken, dus tussen twee
tuinen wacht dit script vijf minuten. Met twee tuinen duurt een ronde daardoor
ruim vijf minuten; plan hem niet vaker dan eens per kwartier. Mist het meer dan
5 dagen achter elkaar, dan is dat gat alleen nog met een CSV-upload te vullen.
"""

import argparse
import os
import sys
import time
from datetime import datetime

GEBRUIKER = "priva-automatisch"
# Het gratis abonnement staat 2 verzoeken per 5 minuten toe; per tuin zijn dat
# er precies 2, dus tussen twee tuinen die 5 minuten afwachten.
PAUZE_TUSSEN_TUINEN = 5 * 60 + 15


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--tuin", type=int, help="alleen deze tuin ophalen (1 of 3)")
    parser.add_argument("--dagen", type=int, default=4, help="aantal dagen terug (max 5)")
    return parser.parse_args()


def main():
    args = lees_argumenten()

    # De doeldatabase moet vaststaan vóór database.py geladen wordt: die leest
    # DATABASE_URL bij het importeren en houdt daar zijn verbindingen op aan.
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    from database import (
        init_db,
        get_tuinen,
        importeer_klimaat_uit_priva,
        importeer_watergift_uit_priva,
    )

    stempel = datetime.now().strftime("%d-%m-%y %H:%M")
    try:
        init_db()
        tuinen = [t for t in get_tuinen() if t["priva_site_id"]]
    except Exception as fout:
        print(f"[{stempel}] FOUT bij het opstarten: {fout}", file=sys.stderr)
        sys.exit(1)

    if args.tuin:
        tuinen = [t for t in tuinen if t["nummer"] == args.tuin]
    if not tuinen:
        print(f"[{stempel}] Geen tuin met een Priva-site gevonden.", file=sys.stderr)
        sys.exit(1)

    mislukt = False
    for i, tuin in enumerate(tuinen):
        if i:
            time.sleep(PAUZE_TUSSEN_TUINEN)
        stempel = datetime.now().strftime("%d-%m-%y %H:%M")
        try:
            klimaat, klimaat_over = importeer_klimaat_uit_priva(
                dagen_terug=args.dagen, gebruiker=GEBRUIKER, tuin_id=tuin["id"])
            water, water_over = importeer_watergift_uit_priva(
                dagen_terug=args.dagen, gebruiker=GEBRUIKER, tuin_id=tuin["id"])
        except Exception as fout:
            print(f"[{stempel}] {tuin['naam']}: FOUT bij ophalen uit Priva: {fout}", file=sys.stderr)
            mislukt = True
            continue
        print(
            f"[{stempel}] {tuin['naam']}: klimaat {klimaat} afdeling-dagen "
            f"({klimaat_over} overgeslagen), watergift {water} vak-dagen "
            f"({water_over} overgeslagen)."
        )

    if mislukt:
        sys.exit(1)


if __name__ == "__main__":
    main()

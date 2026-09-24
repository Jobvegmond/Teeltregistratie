"""
Haalt de laatste afgeronde dagen klimaat- en watergiftdata uit Priva en zet ze
in de database, voor elke tuin die een Priva-site heeft. Bedoeld om periodiek
(bijv. één keer per dag) te draaien, als vervanger van handmatig op de knop in
de app drukken.

Gebruik:
    python priva_ophalen.py              # alle tuinen met een Priva-site
    python priva_ophalen.py --tuin 1     # alleen die ene tuin

Vereist dezelfde omgeving als de app: een .env-bestand naast dit script met
DATABASE_URL en PRIVA_CLIENT_ID / PRIVA_CLIENT_SECRET (of die als
omgevingsvariabelen). Schrijft per tuin en per bron een regel naar het
wijzigingenlogboek.

Windows Taakplanner — nieuwe taak, actie "Programma starten":
    Programma/script:  <volledig pad naar python.exe>
    Argumenten:        priva_ophalen.py
    Beginnen in:       C:\\Users\\Job\\OneDrive\\Python

Let op: het gratis Priva-abonnement staat 2 API-verzoeken per 5 minuten toe en
levert maximaal 5 dagen historie. Per tuin zijn dat 2 verzoeken, dus wacht het
script tussen twee tuinen 5 minuten. Met twee tuinen duurt een ronde daardoor
ruim 5 minuten; draai hem niet vaker dan één keer per ~15 minuten. Mist het
meer dan 5 dagen achter elkaar, dan is dat gat alleen nog met een CSV-upload te
vullen.
"""

import argparse
import sys
import time
from datetime import datetime

from database import (
    init_db,
    get_tuinen,
    importeer_klimaat_uit_priva,
    importeer_watergift_uit_priva,
)

GEBRUIKER = "priva-automatisch"
# Het gratis abonnement staat 2 verzoeken per 5 minuten toe; per tuin zijn dat
# er precies 2, dus tussen twee tuinen die 5 minuten afwachten.
PAUZE_TUSSEN_TUINEN = 5 * 60 + 15


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tuin", type=int, help="alleen deze tuin ophalen (1 of 3)")
    args = parser.parse_args()

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
                gebruiker=GEBRUIKER, tuin_id=tuin["id"])
            water, water_over = importeer_watergift_uit_priva(
                gebruiker=GEBRUIKER, tuin_id=tuin["id"])
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

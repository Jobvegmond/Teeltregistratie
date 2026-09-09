"""
Haalt de laatste afgeronde dagen klimaat- en watergiftdata uit Priva en zet ze
in de database. Bedoeld om periodiek (bijv. één keer per dag) te draaien, als
vervanger van handmatig op de knop in de app drukken.

Gebruik:
    python priva_ophalen.py

Vereist dezelfde omgeving als de app: een .env-bestand naast dit script met
DATABASE_URL en PRIVA_CLIENT_ID / PRIVA_CLIENT_SECRET (of die als
omgevingsvariabelen). Draait de import voor beide bronnen en schrijft één
regel naar het wijzigingenlogboek per bron.

Windows Taakplanner — nieuwe taak, actie "Programma starten":
    Programma/script:  <volledig pad naar python.exe>
    Argumenten:        priva_ophalen.py
    Beginnen in:       C:\\Users\\Job\\OneDrive\\Python

Let op: het gratis Priva-abonnement staat 2 API-verzoeken per 5 minuten toe en
levert maximaal 5 dagen historie. Dit script doet 2 verzoeken, dus draai het
niet vaker dan één keer per ~10 minuten. Mist het meer dan 5 dagen achter
elkaar, dan is dat gat alleen nog met een CSV-upload te vullen.
"""

import sys
from datetime import datetime

from database import (
    init_db,
    importeer_klimaat_uit_priva,
    importeer_watergift_uit_priva,
)

GEBRUIKER = "priva-automatisch"


def main():
    stempel = datetime.now().strftime("%d-%m-%y %H:%M")
    try:
        init_db()
        klimaat_verwerkt, klimaat_over = importeer_klimaat_uit_priva(gebruiker=GEBRUIKER)
        water_verwerkt, water_over = importeer_watergift_uit_priva(gebruiker=GEBRUIKER)
    except Exception as e:
        print(f"[{stempel}] FOUT bij ophalen uit Priva: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[{stempel}] Klimaat: {klimaat_verwerkt} afdeling-dagen "
        f"({klimaat_over} overgeslagen). "
        f"Watergift: {water_verwerkt} vak-dagen ({water_over} overgeslagen)."
    )


if __name__ == "__main__":
    main()

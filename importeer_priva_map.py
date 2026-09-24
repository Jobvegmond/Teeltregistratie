"""
Importeert Priva-weekexports uit een map: "Rapport Algemeen Bedrijf" (klimaat
per afdeling per dag) en "Rapport Energie" (warmte en gas per dag).

Handig voor een inhaalslag: in de app upload je ze één voor één, hier gaat een
hele map in één keer. Een dag die al in de database staat wordt overschreven,
dus een half geïmporteerde week opnieuw aanbieden mag.

De data gaat naar de tuin die je met --tuin meegeeft (standaard tuin 3). Een
map hoort bij één tuin: de exports van tuin 1 komen uit een andere
klimaatcomputer en hebben dezelfde afdelingsnummers.

Gebruik:
    python importeer_priva_map.py "Klimaat 2026 tuin 1" --tuin 1
    python importeer_priva_map.py "Klimaat 2026 tuin 1" --tuin 1 --uitvoeren
    python importeer_priva_map.py "Klimaat 2026 tuin 3" "Energie 2026 tuin 3" --uitvoeren

Zonder mapnaam pakt hij de mappen van tuin 3.
Weigert naar Supabase te schrijven tenzij --productie erbij staat.
"""
import argparse
import os
import sys

import pandas as pd

import database

HIER = os.path.dirname(os.path.abspath(__file__))
STANDAARD_MAPPEN = ["Teelt", "Klimaat 2026 tuin 3", "Energie 2026 tuin 3"]
GEBRUIKER = "csv-import"


def soort_van_bestand(naam):
    """'klimaat', 'energie' of None op basis van de bestandsnaam van de Priva-export."""
    if not naam.lower().endswith(".csv"):
        return None
    if "algemeen_bedrijf" in naam.lower():
        return "klimaat"
    if "energie" in naam.lower():
        return "energie"
    return None


def periode_van_bestand(pad):
    """(eerste, laatste) datum in het bestand, om te tonen wat erin zit."""
    try:
        df = pd.read_csv(pad, sep=None, engine="python", decimal=",")
        datums = pd.to_datetime(df["startdate"], dayfirst=True, format="mixed").dt.date
        return min(datums), max(datums)
    except Exception:
        return None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mappen", nargs="*", default=STANDAARD_MAPPEN)
    parser.add_argument("--tuin", type=int, default=database.STANDAARD_TUIN,
                        help="tuinnummer waar deze exports bij horen (1 of 3)")
    parser.add_argument("--uitvoeren", action="store_true", help="echt importeren (anders proefdraai)")
    parser.add_argument("--productie", action="store_true", help="toestaan dat er naar Supabase geschreven wordt")
    args = parser.parse_args()

    if args.uitvoeren and "supabase" in os.environ.get("DATABASE_URL", "") and not args.productie:
        sys.exit("GESTOPT: .env wijst naar Supabase (productie). Voeg --productie toe als dat de bedoeling is.")

    tuin_id = database.get_tuin_id(args.tuin)
    if tuin_id is None:
        sys.exit(f"GESTOPT: tuin {args.tuin} bestaat niet in de database.")
    print(f"Doel: tuin {args.tuin}")

    bestanden = []
    for map_naam in (args.mappen or STANDAARD_MAPPEN):
        map_pad = map_naam if os.path.isabs(map_naam) else os.path.join(HIER, map_naam)
        if not os.path.isdir(map_pad):
            print(f"Map niet gevonden, overgeslagen: {map_naam}")
            continue
        for naam in sorted(os.listdir(map_pad)):
            soort = soort_van_bestand(naam)
            if soort:
                bestanden.append((soort, os.path.join(map_pad, naam), naam))

    klimaat = [b for b in bestanden if b[0] == "klimaat"]
    energie = [b for b in bestanden if b[0] == "energie"]
    print(f"Gevonden: {len(klimaat)} klimaatbestanden, {len(energie)} energiebestanden")
    for soort, lijst in (("klimaat", klimaat), ("energie", energie)):
        if lijst:
            periodes = [periode_van_bestand(pad) for _, pad, _ in lijst]
            geldig = [p for p in periodes if p[0]]
            if geldig:
                print(f"  {soort}: {min(p[0] for p in geldig):%d-%m-%y} t/m {max(p[1] for p in geldig):%d-%m-%y}")

    if not args.uitvoeren:
        print("\nProefdraai: er is niets geschreven. Gebruik --uitvoeren om te importeren.")
        return

    totaal_klimaat = totaal_energie = totaal_gas = 0
    for soort, pad, naam in bestanden:
        try:
            with open(pad, "rb") as bestand:
                if soort == "klimaat":
                    verwerkt, _overgeslagen = database.verwerk_klimaat_csv(
                        bestand, gebruiker=GEBRUIKER, tuin_id=tuin_id)
                    totaal_klimaat += verwerkt
                else:
                    warmte, _overgeslagen, gas = database.verwerk_energie_csv(
                        bestand, gebruiker=GEBRUIKER, tuin_id=tuin_id)
                    totaal_energie += warmte
                    totaal_gas += gas
        except Exception as fout:
            print(f"  FOUT in {naam}: {fout}")
    print(f"\nKlimaat: {totaal_klimaat} afdeling-dagen | warmte: {totaal_energie} dagen | gas: {totaal_gas} dagen")


if __name__ == "__main__":
    main()

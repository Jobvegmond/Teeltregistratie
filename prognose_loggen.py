"""
Legt één keer per dag de oogstprognose van alle lopende vakken vast in het
prognoselogboek (tabel prognose_log), voor Meer › Prognosekwaliteit.

Gebruik:
    python prognose_loggen.py                  # naar de database uit DATABASE_URL
    python prognose_loggen.py --doel productie # naar DATABASE_URL_PRODUCTIE

Veilig om vaker te draaien: een vak dat vandaag al gelogd is, blijft zoals het
was. Lukt deze taak een dag niet, dan logt de app zelf bij de eerste keer dat
iemand het Teeltoverzicht opent.

Synology Taakplanner — nieuwe taak, Door gebruiker gedefinieerd script (root),
dagelijks na de ochtendronde van priva_ophalen.py (dan is het klimaat van
gisteren binnen):
    docker exec vemteelt-app python prognose_loggen.py --doel productie
Zet "Details van uitvoering via e-mail verzenden" aan met "Alleen als het
script abnormaal wordt afgesloten".
"""

import argparse
import os
import sys
from datetime import date, datetime


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    args = parser.parse_args()

    # De doeldatabase moet vaststaan vóór database.py geladen wordt.
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import prognoselog
    from logic import teeltprognose as tp

    stempel = datetime.now().strftime("%d-%m-%y %H:%M")
    vandaag = date.today()
    try:
        database.init_db()
        data = database.get_vakstatus_data()
        historie, weken = database.get_teelthistorie_data()
        plandatum = lambda start: database.bereken_verwachte_oogstdatum(start)[1]
        model = prognoselog.bouw_model(data, historie, weken, plandatum)
        if model is None:
            print(f"{stempel} Geen teeltmodel (te weinig leerteelten); niets gelogd.")
            return
        stook, afwijking = prognoselog.stand_lopende_teelten(
            data["teelten"], tp.klimaat_per_afdeling(data["klimaat"]), model, vandaag, plandatum)
        regels = prognoselog.logregels(data["teelten"], stook, afwijking, vandaag, prognoselog.modelversie(model))
        nieuw = database.schrijf_prognose_log(regels)
    except Exception as fout:
        print(f"{stempel} FOUT: {fout}", file=sys.stderr)
        sys.exit(1)
    print(f"{stempel} {len(regels)} lopende vakken, {nieuw} nieuw gelogd ({len(regels) - nieuw} stonden er al).")


if __name__ == "__main__":
    main()

"""
Zet afgeronde Cameron-teelten uit de oude Excel-klimaatregistratie over naar
de database, zodat de app ook de teeltduur van vóór de app kent (juist de
wintermaanden, die de app zelf nog niet heeft meegemaakt).

Bron: Teelt\\Klimaatregistratie tuin 3 kopie.xlsx
  - blad "Stek":  plantdatum (jaar/week/dag), vak en aantal geplante stelen
  - blad "Teelt": per teelt één regel die doorloopt t/m de oogstweek

Wat wel en niet mee gaat:
  - alleen vanaf 2025 week 20 (start Cameron);
  - alleen teelten waarvan de oogstweek in Excel staat. Het blad Teelt is
    bijgehouden t/m 2026 week 18; teelten die toen nog liepen, missen hun
    oogst en blijven hier buiten (anders lijken ze in de app nog te lopen);
  - Excel kent de oogst alleen per week. De oogstdatum wordt daarom gezet op
    dezelfde weekdag als de plantdag, in de oogstweek (±3 dagen nauwkeurig);
  - lengte, gewicht en emmers staan niet in Excel en blijven leeg.

Gebruik:
    python importeer_excel_historie.py              # proefdraai: toont alleen
    python importeer_excel_historie.py --uitvoeren  # schrijft naar de database in .env

Weigert naar Supabase te schrijven tenzij --productie erbij staat. Teelten die
al bestaan (zelfde vak en startdatum) worden overgeslagen, dus nogmaals draaien
kan geen kwaad.
"""
import argparse
import os
import sys
import warnings
from collections import Counter
from datetime import date, timedelta

import openpyxl

import database

HIER = os.path.dirname(os.path.abspath(__file__))
EXCEL = os.path.join(HIER, "Teelt", "Klimaatregistratie tuin 3 kopie.xlsx")
VANAF = (2025, 20)  # start Cameron
GEBRUIKER = "excel-import"
DAGNUMMER = {"ma": 1, "di": 2, "wo": 3, "do": 4, "vr": 5, "za": 6, "zo": 7}


def lees_stek(wb):
    """(jaar, week, vak) -> (plantdatum, aantal stelen) uit blad Stek."""
    stek = {}
    rijen = wb["Stek"].iter_rows(values_only=True)
    next(rijen)
    for jaar, week, dag, vak, _ras, te_poten, *_ in rijen:
        if None in (jaar, week, dag, vak) or (int(jaar), int(week)) < VANAF:
            continue
        dagnr = DAGNUMMER.get(str(dag).strip().lower()[:2])
        if dagnr is None:
            continue
        plantdatum = date.fromisocalendar(int(jaar), int(week), dagnr)
        stek[(int(jaar), int(week), int(vak))] = (plantdatum, int(te_poten) if te_poten else None)
    return stek


def lees_teeltweken(wb):
    """(jaar, week, vak) -> (eerste, laatste gevulde jaar-week) uit blad Teelt."""
    rijen = wb["Teelt"].iter_rows(values_only=True)
    kop = next(rijen)
    next(rijen)
    weekkolommen = [
        (i, tuple(int(x) for x in k.split("-")))
        for i, k in enumerate(kop) if isinstance(k, str) and "-" in k
    ]
    teelten = {}
    for rij in rijen:
        week, jaar, vak, _ras, eenheid = rij[:5]
        # Elke teelt staat er twee keer in (°C en J/cm); één is genoeg.
        if eenheid != "°C" or None in (week, jaar, vak):
            continue
        gevuld = [jw for i, jw in weekkolommen if i < len(rij) and rij[i] is not None]
        if gevuld:
            teelten[(int(jaar), int(week), int(vak))] = (gevuld[0], gevuld[-1])
    return teelten


def bouw_teelten(stek, teeltweken):
    """Combineert beide bladen tot afgeronde teelten, plus redenen voor overslaan."""
    # Toen het blad niet meer werd bijgehouden, hielden alle lopende teelten in
    # dezelfde week op; die liepen toen nog. Neem daarom de laatste week waarin
    # meerdere teelten tegelijk eindigen, niet de laatste gevulde cel: in week 19
    # van 2026 staat één losse waarde.
    eindweken = Counter(laatst for _, laatst in teeltweken.values())
    laatste_bijgehouden = max(week for week, aantal in eindweken.items() if aantal >= 3)
    teelten, overgeslagen = [], Counter()
    for sleutel, (eerste, laatste) in sorted(teeltweken.items()):
        jaar, week, vak = sleutel
        if (jaar, week) < VANAF:
            continue
        if laatste >= laatste_bijgehouden:
            overgeslagen["liep nog toen Excel stopte"] += 1
            continue
        if sleutel not in stek:
            overgeslagen["plantdatum niet in blad Stek"] += 1
            continue
        if eerste != (jaar, week):
            overgeslagen["teeltregel begint niet in de plantweek"] += 1
            continue
        plantdatum, aantal = stek[sleutel]
        oogstdatum = date.fromisocalendar(laatste[0], laatste[1], plantdatum.isoweekday())
        teelten.append({"vak": vak, "start": plantdatum, "oogst": oogstdatum, "planten": aantal})
    return teelten, overgeslagen, laatste_bijgehouden


def bestaande_teelten():
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT v.vaknummer, t.datum_teelt_start
            FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id
        """)
        return {(vak, start[:10]) for vak, start in cur.fetchall()}


def schrijf(teelten):
    with database.get_connection() as conn:
        cur = conn.cursor()
        for t in teelten:
            cur.execute("""
                INSERT INTO teelten (teeltvak_id, datum_teelt_start, datum_oogst, aantal_planten, code)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                database.get_of_maak_teeltvak(t["vak"]), str(t["start"]), str(t["oogst"]),
                t["planten"], database.genereer_teelt_code(t["start"], t["vak"]),
            ))
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uitvoeren", action="store_true", help="echt wegschrijven (anders proefdraai)")
    parser.add_argument("--productie", action="store_true", help="toestaan dat er naar Supabase geschreven wordt")
    args = parser.parse_args()

    doel = os.environ.get("DATABASE_URL", "")
    if args.uitvoeren and "supabase" in doel and not args.productie:
        sys.exit("GESTOPT: .env wijst naar Supabase (productie). Voeg --productie toe als dat de bedoeling is.")

    warnings.filterwarnings("ignore", module="openpyxl")
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    teelten, overgeslagen, laatste_bijgehouden = bouw_teelten(lees_stek(wb), lees_teeltweken(wb))

    bestaand = bestaande_teelten()
    nieuw = [t for t in teelten if (t["vak"], str(t["start"])) not in bestaand]
    if len(nieuw) < len(teelten):
        overgeslagen["staat al in de database"] += len(teelten) - len(nieuw)

    print(f"Excel bijgehouden t/m week {laatste_bijgehouden[1]} van {laatste_bijgehouden[0]}")
    print(f"Af te ronden teelten gevonden: {len(teelten)}, nieuw: {len(nieuw)}")
    for reden, aantal in overgeslagen.items():
        print(f"  overgeslagen: {aantal:>3} x {reden}")
    if nieuw:
        duren = [(t["oogst"] - t["start"]).days for t in nieuw]
        print(f"Periode: gestart {min(t['start'] for t in nieuw):%d-%m-%y} t/m {max(t['start'] for t in nieuw):%d-%m-%y}, "
              f"teeltduur {min(duren)}-{max(duren)} dagen")
        for t in nieuw[:3] + nieuw[-3:]:
            print(f"  vak {t['vak']:>2}  start {t['start']:%d-%m-%y}  oogst ~{t['oogst']:%d-%m-%y}  "
                  f"{(t['oogst'] - t['start']).days} dgn  {t['planten']} planten")

    if not args.uitvoeren:
        print("\nProefdraai: er is niets geschreven. Gebruik --uitvoeren om te importeren.")
        return
    if not nieuw:
        print("\nNiets te doen.")
        return

    schrijf(nieuw)
    database.log_wijziging(
        GEBRUIKER, "aangemaakt", "teelt", None,
        f"{len(nieuw)} afgeronde teelten uit Excel geïmporteerd "
        f"(gestart {min(t['start'] for t in nieuw):%d-%m-%y} t/m {max(t['start'] for t in nieuw):%d-%m-%y}; "
        "oogstdatum op weekniveau)"
    )
    print(f"\n{len(nieuw)} teelten geïmporteerd.")


if __name__ == "__main__":
    main()

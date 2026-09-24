"""
Zet afgeronde Cameron-teelten uit de oude Excel-klimaatregistratie over naar
de database, zodat de app ook de teeltduur van vóór de app kent (juist de
wintermaanden, die de app zelf nog niet heeft meegemaakt).

Bron: Teelt\\Klimaatregistratie tuin 3 kopie.xlsx
  - blad "Stek":     plantdatum (jaar/week/dag), vak en aantal geplante stelen
  - blad "Teelt":    per teelt één regel die doorloopt t/m de oogstweek
  - blad "Overview": watergift per vak per dag (de rijen "W")

Wat wel en niet mee gaat:
  - alleen vanaf 2025 week 20 (start Cameron);
  - alleen teelten waarvan de oogstweek in Excel staat. Het blad Teelt is
    bijgehouden t/m 2026 week 18; teelten die toen nog liepen, missen hun
    oogst en blijven hier buiten (anders lijken ze in de app nog te lopen);
  - Excel kent de oogst alleen per week. De oogstdatum wordt daarom gezet op
    dezelfde weekdag als de plantdag, in de oogstweek (±3 dagen nauwkeurig);
  - lengte, gewicht en emmers staan niet in Excel en blijven leeg;
  - de stekbeoordeling (bakjes, wortel, plantmaat, uniformiteit, cijfer,
    opmerking) gaat mee naar stekbeoordelingen, voor elke teelt in de database
    met hetzelfde vak en dezelfde plantdatum. Een beoordeling die al in de app
    staat, wordt niet overschreven;
  - de watergift uit blad Overview gaat naar watergift_dag met bron 'excel'.
    Dat is de ingestelde gift; waar Priva gemeten heeft blijft die staan. Uit de
    overlap (sep 2026) blijkt Excel een paar procent lager en mist het de kleine
    giften, dus gebruik deze cijfers als benadering.

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
TUIN = 3
VANAF = (2025, 20)  # start Cameron
GEBRUIKER = "excel-import"
DAGNUMMER = {"ma": 1, "di": 2, "wo": 3, "do": 4, "vr": 5, "za": 6, "zo": 7}
RAS_NAAM = {"Cam": "Cameron"}  # afkortingen in Excel -> naam voor de leverancier


def lees_stek(wb):
    """(jaar, week, vak) -> gegevens van die planting uit blad Stek."""
    stek = {}
    rijen = wb["Stek"].iter_rows(values_only=True)
    next(rijen)
    for rij in rijen:
        (jaar, week, dag, vak, ras, te_poten, bakjes, _uitval, _celdagen,
         wortel, plantmaat, uniformiteit, cijfer, opmerking) = (list(rij) + [None] * 14)[:14]
        if None in (jaar, week, dag, vak) or (int(jaar), int(week)) < VANAF:
            continue
        dagnr = DAGNUMMER.get(str(dag).strip().lower()[:2])
        if dagnr is None:
            continue
        tekst = lambda v: str(v).strip() if v not in (None, "") else None
        stek[(int(jaar), int(week), int(vak))] = {
            "plantdatum": date.fromisocalendar(int(jaar), int(week), dagnr),
            "planten": int(te_poten) if te_poten else None,
            "beoordeling": {
                "ras": RAS_NAAM.get(tekst(ras), tekst(ras)),
                "bakjes": float(bakjes) if bakjes not in (None, "") else None,
                "wortel": tekst(wortel),
                "plantmaat": tekst(plantmaat),
                "uniformiteit": tekst(uniformiteit),
                "beoordeling": int(cijfer) if cijfer not in (None, "") else None,
                "opmerking": tekst(opmerking),
            },
        }
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


def lees_watergift(wb):
    """(vak, datum) -> liter per m2 uit de "W"-rijen van blad Overview."""
    rijen = wb["Overview"].iter_rows(values_only=True)
    jaren, weken, dagen = next(rijen), next(rijen), next(rijen)
    next(rijen)
    # De kop staat in drie rijen: jaar en week alleen boven de eerste dag van
    # het blok, daarna zeven dagkolommen (het blok begint op zondag).
    kolomdatum = {}
    jaar = week = None
    positie = 0
    blokstart = None
    for i in range(15, len(jaren)):
        if jaren[i] is not None:
            jaar, week, positie = jaren[i], weken[i], 0
            try:
                blokstart = date.fromisocalendar(int(jaar), int(week), 1) - timedelta(days=1)
            except ValueError:  # bijv. week 53 in een jaar dat er 52 heeft
                blokstart = None
        elif jaar is not None:
            positie += 1
        if blokstart and i < len(dagen) and dagen[i]:
            kolomdatum[i] = blokstart + timedelta(days=positie)

    eerste_dag = date.fromisocalendar(VANAF[0], VANAF[1], 1)
    watergift = {}
    vak = None
    for rij in rijen:
        if rij[0] is not None:
            vak = rij[0]
        if rij[1] != "W" or vak is None:
            continue
        for i, dag in kolomdatum.items():
            waarde = rij[i] if i < len(rij) else None
            if isinstance(waarde, (int, float)) and waarde and dag >= eerste_dag:
                watergift[(int(vak), dag)] = float(waarde)
    return watergift


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
        plantdatum, aantal = stek[sleutel]["plantdatum"], stek[sleutel]["planten"]
        oogstdatum = date.fromisocalendar(laatste[0], laatste[1], plantdatum.isoweekday())
        teelten.append({"vak": vak, "start": plantdatum, "oogst": oogstdatum, "planten": aantal})

    # Een enkele planting staat wel in blad Stek maar heeft geen regel in blad
    # Teelt; die zou anders helemaal wegvallen. De oogstdatum komt dan uit de
    # teeltduur-tabel. Alleen als die datum in het verleden ligt: een teelt die
    # volgens die schatting nog loopt, blijft open staan.
    geschat_uit_stek = [0]
    vandaag = date.today()
    uit_stek = {(t["vak"], t["start"].isocalendar()[:2]) for t in teelten}
    for (jaar, week, vak), gegevens in sorted(stek.items()):
        if (jaar, week) < VANAF or (vak, (jaar, week)) in uit_stek:
            continue
        if (jaar, week, vak) in teeltweken:
            continue  # stond in blad Teelt en is hierboven al beoordeeld
        plantdatum = gegevens["plantdatum"]
        _duur, verwacht = database.bereken_verwachte_oogstdatum(plantdatum)
        if not verwacht or verwacht >= vandaag:
            overgeslagen["geen regel in blad Teelt, oogst onbekend"] += 1
            continue
        teelten.append({"vak": vak, "start": plantdatum, "oogst": verwacht,
                        "planten": gegevens["planten"], "oogst_geschat": True})
        geschat_uit_stek[0] += 1

    return teelten, overgeslagen, laatste_bijgehouden, geschat_uit_stek[0]


def bestaande_teelten(tuin_id):
    """
    De teelten van deze tuin die al in de database staan, als (vak, plantweek).
    Excel en de app wijken soms een dag af in de plantdatum; een vak heeft nooit
    twee teelten in één week, dus op vak + week herken je ze toch als dezelfde.
    """
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT v.vaknummer, t.datum_teelt_start
            FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id
            WHERE v.tuin_id = %s
        """, (tuin_id,))
        return {(vak, date.fromisoformat(start[:10]).isocalendar()[:2])
                for vak, start in cur.fetchall()}


def stek_bij_teelten(stek, tuin_id):
    """
    Koppelt de stekbeoordelingen uit Excel aan teelten in de database (zelfde
    vak en plantdatum) die nog geen beoordeling hebben. Geeft (teelt_id, velden)
    terug, plus het aantal dat geen teelt vond en het aantal dat al bestond.
    """
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, s.id IS NOT NULL
            FROM teelten t
            JOIN teeltvakken v ON v.id = t.teeltvak_id
            LEFT JOIN stekbeoordelingen s ON s.teelt_id = t.id
            WHERE v.tuin_id = %s
        """, (tuin_id,))
        rijen = cur.fetchall()
    teelt_per_plant = {(vak, start[:10]): (tid, heeft) for tid, vak, start, heeft in rijen}
    # Excel en de app wijken soms een dag af in de plantdatum. Een vak heeft nooit
    # twee teelten in één week, dus dan mag vak + week ook.
    per_vakweek = {}
    for tid, vak, start, heeft in rijen:
        per_vakweek.setdefault((vak, date.fromisoformat(start[:10]).isocalendar()[:2]), []).append((tid, heeft))
    koppel, geen_teelt, al_ingevuld = [], 0, 0
    for (jaar, week, vak), gegevens in stek.items():
        gevonden = teelt_per_plant.get((vak, str(gegevens["plantdatum"])))
        if gevonden is None and len(per_vakweek.get((vak, (jaar, week)), [])) == 1:
            gevonden = per_vakweek[(vak, (jaar, week))][0]
        if gevonden is None:
            geen_teelt += 1
        elif gevonden[1]:
            al_ingevuld += 1
        else:
            koppel.append((gevonden[0], gegevens["beoordeling"]))
    return koppel, geen_teelt, al_ingevuld


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

    tuin_id = database.get_tuin_id(TUIN)
    if tuin_id is None:
        sys.exit(f"GESTOPT: tuin {TUIN} bestaat niet in de database.")
    # Alles in dit script gaat over tuin 3, ook de functies zonder expliciete tuin.
    database.zet_actieve_tuin(tuin_id)

    warnings.filterwarnings("ignore", module="openpyxl")
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    stek = lees_stek(wb)
    teelten, overgeslagen, laatste_bijgehouden, geschat = bouw_teelten(stek, lees_teeltweken(wb))

    bestaand = bestaande_teelten(tuin_id)
    nieuw = [t for t in teelten
             if (t["vak"], t["start"].isocalendar()[:2]) not in bestaand]
    if len(nieuw) < len(teelten):
        overgeslagen["staat al in de database"] += len(teelten) - len(nieuw)

    print(f"Excel bijgehouden t/m week {laatste_bijgehouden[1]} van {laatste_bijgehouden[0]}")
    print(f"Af te ronden teelten gevonden: {len(teelten)}, nieuw: {len(nieuw)}")
    if geschat:
        print(f"  {geschat} teelten staan alleen in blad Stek; hun oogstdatum is geschat "
              "uit de teeltduur-tabel")
    for reden, aantal in overgeslagen.items():
        print(f"  overgeslagen: {aantal:>3} x {reden}")
    if nieuw:
        duren = [(t["oogst"] - t["start"]).days for t in nieuw]
        print(f"Periode: gestart {min(t['start'] for t in nieuw):%d-%m-%y} t/m {max(t['start'] for t in nieuw):%d-%m-%y}, "
              f"teeltduur {min(duren)}-{max(duren)} dagen")
        for t in nieuw[:3] + nieuw[-3:]:
            print(f"  vak {t['vak']:>2}  start {t['start']:%d-%m-%y}  oogst ~{t['oogst']:%d-%m-%y}  "
                  f"{(t['oogst'] - t['start']).days} dgn  {t['planten']} planten")

    if args.uitvoeren and nieuw:
        schrijf(nieuw)
        database.log_wijziging(
            GEBRUIKER, "aangemaakt", "teelt", None,
            f"{len(nieuw)} afgeronde teelten uit Excel geïmporteerd "
            f"(gestart {min(t['start'] for t in nieuw):%d-%m-%y} t/m {max(t['start'] for t in nieuw):%d-%m-%y}; "
            "oogstdatum op weekniveau)"
        )
        print(f"\n{len(nieuw)} teelten geïmporteerd.")

    # Pas na de teelten: een beoordeling hangt aan een teelt die nu pas kan bestaan.
    # In de proefdraai tellen de nog niet geïmporteerde teelten dus als "zonder teelt".
    koppel, geen_teelt, al_ingevuld = stek_bij_teelten(stek, tuin_id)
    print(f"\nStekbeoordelingen: {len(koppel)} nieuw, {al_ingevuld} stonden er al, "
          f"{geen_teelt} zonder bijbehorende teelt in de database")

    watergift = lees_watergift(wb)
    if watergift:
        dagen_wg = sorted({dag for _, dag in watergift})
        print(f"Watergift (ingesteld): {len(watergift)} vak-dagen, "
              f"{dagen_wg[0]:%d-%m-%y} t/m {dagen_wg[-1]:%d-%m-%y}")

    if not args.uitvoeren:
        print("\nProefdraai: er is niets geschreven. Gebruik --uitvoeren om te importeren.")
        return
    for teelt_id, velden in koppel:
        database.sla_stekbeoordeling_op(teelt_id, velden, gebruiker=GEBRUIKER)
    if koppel:
        print(f"{len(koppel)} stekbeoordelingen geïmporteerd.")

    for (vak, dag), liter in sorted(watergift.items()):
        database.upsert_watergift_dag(vak, dag, liter, bron="excel")
    print(f"{len(watergift)} vak-dagen watergift weggeschreven (bron excel; "
          "gemeten Priva-waarden blijven staan).")


if __name__ == "__main__":
    main()

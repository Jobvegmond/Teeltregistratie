"""
Tuin 1, plantweek 27 t/m 37 van 2026: alle vakken van een plantweek stonden
op dezelfde maandag gestart (en de afgeronde op dezelfde dag geoogst), omdat
ze per week zijn ingevoerd. In werkelijkheid wordt er één vak per dag
geplant. Dit script zet ze recht (afspraak met Job, 29-09-2026):

- binnen een plantweek op volgorde van vaknummer: het eerste vak maandag,
  het tweede dinsdag, enz. (startdatum + 0, 1, 2, … dagen);
- de oogstdatum schuift evenveel mee, zodat de teeltduur gelijk blijft; valt
  hij dan op zaterdag of zondag, dan wordt het de maandag erna;
- emmers die op de oude oogstdatum geregistreerd staan, verhuizen naar de
  nieuwe oogstdatum (alleen bij afgeronde vakken);
- de Florgib-datum blijft staan.

Een plantweek waarvan de vakken niet allemaal op dezelfde maandag staan,
wordt overgeslagen. Er wordt niets verwijderd; elke wijziging komt in het
wijzigingenlog.

Gebruik:
    python herstel_plantdagen_tuin1.py                          # proefdraai: toont wat er verandert
    python herstel_plantdagen_tuin1.py --uitvoeren              # schrijft naar DATABASE_URL (NAS)
    python herstel_plantdagen_tuin1.py --uitvoeren --productie  # ook naar Supabase
Daarna: python importeer_teelt_historie.py --uitvoeren (zelfde database), zodat
de teelthistorie de nieuwe datums krijgt.
"""
import argparse
import os
import sys
import warnings
from collections import defaultdict
from datetime import date, datetime, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database  # noqa: E402

TUIN = 1
JAAR, WEKEN = 2026, range(27, 38)
GEBRUIKER = "herstel-plantdagen"


def _d(tekst):
    return datetime.strptime(str(tekst)[:10], "%Y-%m-%d").date() if tekst else None


def werkdag(dag):
    """Zaterdag of zondag wordt de maandag erna."""
    return dag + timedelta(days=(7 - dag.weekday()) % 7) if dag.weekday() >= 5 else dag


def plan(cursor):
    """Per vak (id, vak, week, oude/nieuwe start, oude/nieuwe oogst, emmers die meeverhuizen), plus meldingen."""
    cursor.execute("""
        SELECT t.id, v.vaknummer, t.code, t.datum_teelt_start, t.datum_oogst, t.datum_half
        FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id JOIN tuinen tu ON tu.id = v.tuin_id
        WHERE tu.nummer = %s ORDER BY v.vaknummer
    """, (TUIN,))
    per_week = defaultdict(list)
    for id_, vak, code, start, oogst, half in cursor.fetchall():
        jaar, week, _ = _d(start).isocalendar()
        if jaar == JAAR and week in WEKEN:
            per_week[week].append({"id": id_, "vak": vak, "code": code, "start": _d(start), "oogst": _d(oogst),
                                   "half": _d(half)})
    wijzigingen, meldingen = [], []
    for week in sorted(per_week):
        vakken = sorted(per_week[week], key=lambda t: t["vak"])
        starts = {t["start"] for t in vakken}
        if len(starts) != 1 or next(iter(starts)).weekday() != 0:
            meldingen.append(f"Week {week} overgeslagen: vakken staan niet allemaal op dezelfde maandag.")
            continue
        for i, t in enumerate(vakken):
            nieuwe_start = t["start"] + timedelta(days=i)
            nieuwe_oogst = werkdag(t["oogst"] + timedelta(days=i)) if t["oogst"] else None
            if nieuwe_oogst and nieuwe_oogst >= date.today():
                meldingen.append(f"Week {week} vak {t['vak']}: nieuwe oogst {nieuwe_oogst} ligt niet in het "
                                 "verleden; oogst ongewijzigd gelaten.")
                nieuwe_oogst = t["oogst"]
            if t["half"] and t["half"] <= nieuwe_start:
                meldingen.append(f"Week {week} vak {t['vak']}: Florgib {t['half']} ligt niet na de nieuwe start.")
            emmers = []
            if t["oogst"] and nieuwe_oogst != t["oogst"]:
                cursor.execute("SELECT id, datum, aantal_emmers FROM oogstregistraties WHERE teelt_id = %s", (t["id"],))
                for eid, datum, aantal in cursor.fetchall():
                    if _d(datum) == t["oogst"]:
                        emmers.append((eid, aantal))
                    else:
                        meldingen.append(f"Week {week} vak {t['vak']}: emmers op {datum} (niet de oogstdatum) "
                                         "blijven staan.")
            if nieuwe_start != t["start"] or nieuwe_oogst != t["oogst"]:
                wijzigingen.append({**t, "week": week, "nieuwe_start": nieuwe_start, "nieuwe_oogst": nieuwe_oogst,
                                    "emmers": emmers})
    return wijzigingen, meldingen


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uitvoeren", action="store_true", help="echt schrijven (anders proefdraai)")
    parser.add_argument("--productie", action="store_true", help="schrijven naar Supabase toestaan")
    args = parser.parse_args()
    if args.uitvoeren and "supabase" in (database.DATABASE_URL or "") and not args.productie:
        sys.exit("GESTOPT: DATABASE_URL wijst naar Supabase. Gebruik --productie als dat de bedoeling is.")

    with database.get_connection() as conn:
        cursor = conn.cursor()
        wijzigingen, meldingen = plan(cursor)
        print(f"{len(wijzigingen)} vakken van tuin {TUIN} krijgen een andere datum:")
        for w in wijzigingen:
            oogst = (f"oogst {w['oogst']:%a %d-%m} → {w['nieuwe_oogst']:%a %d-%m}"
                     if w["oogst"] and w["nieuwe_oogst"] != w["oogst"] else "oogst ongewijzigd")
            print(f"  wk {w['week']} vak {w['vak']:>2}: start {w['start']:%a %d-%m} → {w['nieuwe_start']:%a %d-%m}, "
                  f"{oogst}" + (f", {len(w['emmers'])} emmerregistratie(s) mee" if w["emmers"] else ""))
        for m in meldingen:
            print("  LET OP:", m)
        if not args.uitvoeren:
            print("Proefdraai: niets geschreven. Gebruik --uitvoeren om te schrijven.")
            return
        for w in wijzigingen:
            cursor.execute("UPDATE teelten SET datum_teelt_start = %s, datum_oogst = %s WHERE id = %s",
                           (str(w["nieuwe_start"]), str(w["nieuwe_oogst"]) if w["nieuwe_oogst"] else None, w["id"]))
            for eid, _aantal in w["emmers"]:
                cursor.execute("UPDATE oogstregistraties SET datum = %s WHERE id = %s", (str(w["nieuwe_oogst"]), eid))
        conn.commit()
    for w in wijzigingen:
        database.log_wijziging(
            GEBRUIKER, "gewijzigd", "teelt", w["id"],
            f"Plantdag rechtgezet (wk {w['week']}, vak {w['vak']}): start {w['start']} → {w['nieuwe_start']}"
            + (f", oogst {w['oogst']} → {w['nieuwe_oogst']}" if w["oogst"] and w["nieuwe_oogst"] != w["oogst"] else "")
            + (f", {len(w['emmers'])} emmerregistratie(s) mee" if w["emmers"] else ""))
    print(f"Geschreven: {len(wijzigingen)} vakken bijgewerkt.")


if __name__ == "__main__":
    main()

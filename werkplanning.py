"""
Werkplanning voor de komende dagen (tuin 3): CXDS-blokken per planting, Florgib met CXDS, planten met Rizolex
en inwateren, volgens de werkwijze van de kwekerij (logic/werkplanning.py). Alleen lezen.

Gebruikt door de geplande taak "Dagelijkse takenlijst" (Claude Code op de werklaptop, elke ochtend 07:00), die de
taken in de Takenlijst (claude.ai-artifact) zet.

Gebruik:
    python werkplanning.py                       # komende 7 dagen, als tekst
    python werkplanning.py --json                # als JSON (voor de Takenlijst)
    python werkplanning.py --van 2026-10-25      # vanaf een andere dag
    python werkplanning.py --doel productie      # de online database (DATABASE_URL_PRODUCTIE)
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--van", type=date.fromisoformat, default=date.today(), help="eerste dag (standaard vandaag)")
    parser.add_argument("--dagen", type=int, default=7, help="hoeveel dagen (standaard 7)")
    parser.add_argument("--tuin", type=int, default=3, help="tuinnummer (standaard 3)")
    parser.add_argument("--json", action="store_true", help="als JSON")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    return parser.parse_args()


def main():
    args = lees_argumenten()
    # Altijd UTF-8 (ook in een Windows-console of als de uitvoer naar een bestand gaat): "–" en "·" in de taken.
    sys.stdout.reconfigure(encoding="utf-8")
    if args.doel == "productie":
        import database as _db          # laadt .env; daarna het productie-adres als DATABASE_URL
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        _db.DATABASE_URL = doel_url

    import database
    from logic import prognoselog, teeltprognose as tp, vakstatus as vs
    from logic import werkplanning as wp

    tuin = next((t for t in database.get_tuinen() if t["nummer"] == args.tuin), None)
    if tuin is None:
        print(f"FOUT: geen tuin {args.tuin}", file=sys.stderr)
        sys.exit(1)
    van, tot = args.van, args.van + timedelta(days=args.dagen - 1)

    def plandatum(start):
        return database.bereken_verwachte_oogstdatum(start)[1]

    # Lopende teelten met de verwachte Florgib en de prognose-oogst van het teeltmodel (zoals Overzicht).
    data = database.get_vakstatus_data()
    historie, weken = database.get_teelthistorie_data()
    model = prognoselog.bouw_model(data, historie, weken, plandatum)
    stook, _afwijking = prognoselog.stand_lopende_teelten(
        data["teelten"], tp.klimaat_per_afdeling(data["klimaat"]), model, van, plandatum)
    teelten, concepten = [], []
    for t in data["teelten"].to_dict("records"):
        if t["tuin_id"] != tuin["id"]:
            continue
        start = vs.als_datum(t["datum_teelt_start"])
        if not start or vs.als_datum(t["datum_oogst"]):
            continue
        if start > van:                             # bevestigd, nog niet geplant
            concepten.append((int(t["vaknummer"]), start))
            continue
        u = stook.get(int(t["id"])) or {}
        teelten.append({"vak": int(t["vaknummer"]), "start": start, "florgib": vs.als_datum(t.get("datum_half")),
                        "florgib_verwacht": u.get("florgib_verwacht"), "prognose": u.get("prognose"),
                        "emmers": vs._getal(t.get("emmers")) or 0})
    # Per vak alleen de jongste lopende teelt.
    jongste = {}
    for t in teelten:
        if t["vak"] not in jongste or t["start"] > jongste[t["vak"]]["start"]:
            jongste[t["vak"]] = t
    teelten = list(jongste.values())
    # Concepten van deze week (ook van eerder deze week die nog niet gestart zijn) en verder in de periode; de
    # vakken die deze week al geplant zijn, tellen mee voor het inwateren.
    zondag = van - timedelta(days=(van.weekday() + 1) % 7)
    for _id, vak, start, _duur, _eind, _notitie in database.get_planning(tuin["id"]):
        start = vs.als_datum(start)
        if start and zondag <= start <= tot:
            concepten.append((int(vak), start))
    geplant = [(t["vak"], t["start"]) for t in teelten if zondag <= t["start"] <= van]
    behandelingen = database.get_behandelingen(tuin["id"], van - timedelta(days=90), van)
    for b in behandelingen:
        b["datum"] = vs.als_datum(b["datum"])
    cxds = wp.laatste_cxds(behandelingen)

    taken = wp.taken(teelten, cxds, concepten, van, args.dagen, geplant)
    if args.json:
        print(json.dumps([{"id": f"{t['soort']}-{'-'.join(map(str, t['vakken']))}-{t['datum']}",
                           "date": str(t["datum"]), "title": t["titel"], "note": t["toelichting"],
                           "soort": t["soort"], "vakken": t["vakken"]} for t in taken], ensure_ascii=False, indent=1))
        return
    print(f"Werkplanning {tuin['naam']}, {van:%d-%m-%y} t/m {tot:%d-%m-%y}")
    for t in taken:
        print(f"{wp.DAG[t['datum'].weekday()]} {t['datum']:%d-%m}  {t['titel']}  ({t['toelichting']})")


if __name__ == "__main__":
    main()

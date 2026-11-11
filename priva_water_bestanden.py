"""
Gietbeurten per vak en EC/pH per watersysteem uit de Priva-bestanden op de NAS, naast wat de Priva-API
(priva_ophalen.py) in de database zette. Rekenwerk in logic/priva_water_bestanden.py.

Fase 1 (nu): alleen vergelijken. De database wordt alleen gelezen; de API blijft de bron van watergift_beurt,
water_kwaliteit_dag en het aantal beurten in watergift_dag. Per dag een regel met wat overeenkomt en wat niet,
en met --details elke afwijking. Na een week of twee zonder afwijkingen kan het opslaan hiernaartoe en kan
priva_ophalen.py uit.

Per tuin (--tuin, standaard 3) staan de mappen en de regelaar in config.PRIVA_BESTANDEN; de regelaar in de
bestanden wordt gecontroleerd, net als bij de andere Priva-scripts.

In de uurtaak (priva_bestanden.py) draait dit met --alleen-om 6: alleen in het uur 6 UTC (07:00 of 08:00 NL,
na de ochtendronde van de API), over gisteren. Een verschil geeft geen foutcode; ontbrekende bestanden wel.

Gebruik:
    python priva_water_bestanden.py --tuin 3                       # gisteren
    python priva_water_bestanden.py --tuin 1 --van 2026-10-22 --tot 2026-11-09 --details
    python priva_water_bestanden.py --doel productie               # tegen DATABASE_URL_PRODUCTIE
    python priva_water_bestanden.py --json uit.json                # alle rijen voor eigen analyse

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal bijv.
\\\\192.168.0.197\\Priva).
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from config import WATERSYSTEMEN

# Een beurt uit de bestanden hoort bij een API-beurt van hetzelfde vak als de starts zo dicht bij elkaar liggen.
KOPPEL_VENSTER = timedelta(minutes=10)
# Wat nog als gelijk telt (de bestanden hebben EC/pH op één decimaal en peilen ± elke 75 s).
MARGES = {"start_s": 120, "eind_s": 150, "liter_per_m2": 0.06, "ec": 0.1, "ph": 0.1, "flow": 1.5}
KWALITEIT_MARGES = {"ec_gem": 0.1, "ph_gem": 0.1, "ec_min": 0.15, "ec_max": 0.15, "ph_min": 0.15, "ph_max": 0.15,
                    "ec_doel": 0.1, "ph_doel": 0.1, "ec_aanvoer": 0.1, "ec_gift": 0.1, "ph_gift": 0.1, "recept": 0}


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva")
    parser.add_argument("--tuin", type=int, default=3, help="tuinnummer (standaard 3)")
    parser.add_argument("--van", type=date.fromisoformat, help="eerste dag (standaard gelijk aan --tot)")
    parser.add_argument("--tot", type=date.fromisoformat, help="laatste dag (standaard gisteren)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--details", action="store_true", help="elke afwijking tonen")
    parser.add_argument("--json", help="alle rijen (bestanden en API) naar dit bestand")
    parser.add_argument("--alleen-om", type=int, metavar="UUR",
                        help="alleen draaien in dit uur (UTC), anders meteen klaar (voor de uurtaak)")
    parser.add_argument("--droog", action="store_true", help=argparse.SUPPRESS)   # van priva_bestanden.py
    return parser.parse_args()


def kies_database(doel):
    """Alleen lezen; bij productie het adres uit DATABASE_URL_PRODUCTIE (of .env.productie op de werklaptop)."""
    os.environ["PGOPTIONS"] = "-c default_transaction_read_only=on"
    import database
    if doel == "productie":
        url = os.environ.get("DATABASE_URL_PRODUCTIE")
        env_productie = Path(__file__).with_name(".env.productie")
        if not url and env_productie.exists():
            url = next((r.partition("=")[2].strip().strip('"').strip("'")
                        for r in env_productie.read_text(encoding="utf-8").splitlines()
                        if r.strip().startswith("DATABASE_URL=")), None)
        if not url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        database.DATABASE_URL = url
    return database


def lees_bestanden(live, van, tot, sleutels):
    """(reeksen, tijdzones, ontbrekende dagbestanden) over van−1 … tot+1."""
    from logic import priva_water_bestanden as pwb
    delen, tijdzones, ontbreekt = [], {}, []
    dag = van - timedelta(days=1)
    while dag <= tot + timedelta(days=1):
        pad = live / f"water-{dag}.jsonl"
        if pad.exists():
            with open(pad, encoding="utf-8", errors="replace") as f:
                delen.append(pwb.lees_jsonl(f, sleutels, tijdzones))
        elif van <= dag <= tot:
            ontbreekt.append(dag)
        dag += timedelta(days=1)
    return pwb.voeg_samen(*delen), tijdzones, ontbreekt


def api_rijen(database, tuin_id, van, tot):
    """Wat de API in de database zette: (beurten, kwaliteit, gift)."""
    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT vaknummer, start, eind, datum, liter_per_m2, ec, ph, flow FROM watergift_beurt
                       WHERE tuin_id = %s AND datum BETWEEN %s AND %s AND bron = 'priva'""",
                    (tuin_id, str(van), str(tot)))
        beurten = [{"vaknummer": v, "start": datetime.fromisoformat(s), "eind": datetime.fromisoformat(e),
                    "datum": date.fromisoformat(d), "liter_per_m2": l, "ec": ec, "ph": ph, "flow": f}
                   for v, s, e, d, l, ec, ph, f in cur.fetchall()]
        cur.execute("""SELECT watersysteem, datum, ec_gem, ec_min, ec_max, ph_gem, ph_min, ph_max, ec_doel, ph_doel,
                              ec_aanvoer, ec_gift, ph_gift, recept FROM water_kwaliteit_dag
                       WHERE tuin_id = %s AND datum BETWEEN %s AND %s AND bron = 'priva'""",
                    (tuin_id, str(van), str(tot)))
        velden = ("watersysteem", "datum", "ec_gem", "ec_min", "ec_max", "ph_gem", "ph_min", "ph_max", "ec_doel",
                  "ph_doel", "ec_aanvoer", "ec_gift", "ph_gift", "recept")
        kwaliteit = [dict(zip(velden, rij)) for rij in cur.fetchall()]
        for r in kwaliteit:
            r["datum"] = date.fromisoformat(r["datum"])
        cur.execute("""SELECT vaknummer, datum, liter_per_m2, beurten, bron FROM watergift_dag
                       WHERE tuin_id = %s AND datum BETWEEN %s AND %s""", (tuin_id, str(van), str(tot)))
        gift = {(v, date.fromisoformat(d)): {"liter_per_m2": l, "beurten": b, "bron": bron}
                for v, d, l, b, bron in cur.fetchall()}
    return beurten, kwaliteit, gift


def koppel_beurten(bestand, api):
    """(paren, alleen_bestand, alleen_api): per vak de beurten met de dichtstbijzijnde start binnen het venster."""
    paren, over_api = [], list(api)
    alleen_bestand = []
    for b in sorted(bestand, key=lambda x: x["start"]):
        kandidaten = [a for a in over_api if a["vaknummer"] == b["vaknummer"]
                      and abs(a["start"] - b["start"]) <= KOPPEL_VENSTER]
        if not kandidaten:
            alleen_bestand.append(b)
            continue
        a = min(kandidaten, key=lambda x: abs(x["start"] - b["start"]))
        over_api.remove(a)
        paren.append((b, a))
    return paren, alleen_bestand, over_api


def verschillen_beurt(b, a):
    """{grootheid: (bestand, api, verschil)} buiten de marge."""
    uit = {}
    for naam, x, y in (("start_s", b["start"], a["start"]), ("eind_s", b["eind"], a["eind"])):
        d = (x - y).total_seconds()
        if abs(d) > MARGES[naam]:
            uit[naam] = (x, y, d)
    for naam in ("liter_per_m2", "ec", "ph", "flow"):
        x, y = b.get(naam), a.get(naam)
        if x is None and y is None:
            continue
        if x is None or y is None or abs(x - y) > MARGES[naam]:
            uit[naam] = (x, y, None if x is None or y is None else round(x - y, 3))
    return uit


def verschillen_kwaliteit(b, a):
    uit = {}
    for naam, marge in KWALITEIT_MARGES.items():
        x, y = b.get(naam), a.get(naam)
        if x is None and y is None:
            continue
        if x is None or y is None or abs(x - y) > marge + 1e-9:
            uit[naam] = (x, y)
    return uit


def _tijd(t):
    return t.astimezone(timezone(timedelta(hours=1))).strftime("%d-%m %H:%M:%S") if t else "-"


def main():
    args = lees_argumenten()
    if args.alleen_om is not None and datetime.now(timezone.utc).hour != args.alleen_om:
        return
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    database = kies_database(args.doel)
    from logic import priva_bron
    from logic import priva_water_bestanden as pwb

    nu = datetime.now(timezone.utc)
    stempel = f"{nu:%d-%m-%y %H:%M} UTC"
    tot = args.tot or (nu + timedelta(hours=2)).date() - timedelta(days=1)
    van = args.van or tot
    live, _ = priva_bron.mappen(args.map, args.tuin)
    catalogus = live / "water-catalogus.csv"
    if not catalogus.exists():
        print(f"[{stempel}] FOUT: geen water-catalogus.csv van tuin {args.tuin} in {live}", file=sys.stderr)
        sys.exit(1)
    fout = priva_bron.controleer_regelaar(live, args.tuin)
    tuin = next((t for t in database.get_tuinen() if t["nummer"] == args.tuin), None)
    if fout or not tuin:
        print(f"[{stempel}] FOUT: {fout or f'geen tuin {args.tuin} in de database'}", file=sys.stderr)
        sys.exit(1)

    vakken = set(database.get_vaknummers(tuin["id"]))
    systeem = min(WATERSYSTEMEN.get(args.tuin, {1: None}))
    with open(catalogus, encoding="utf-8", errors="replace") as f:
        punten = pwb.systeem_punten(f)
    missend = [g for g in ("ec", "ph", "recept", "ec_aanvoer", "ec_doel") if (systeem, g) not in punten]
    if missend:
        print(f"[{stempel}] LET OP: niet in de catalogus voor watersysteem {systeem}: {', '.join(missend)}")
    reeksen, tijdzones, ontbreekt = lees_bestanden(live, van, tot, pwb.benodigde_sleutels(punten, vakken, systeem))
    gift, kwaliteit, beurten = pwb.water_dagwaarden(reeksen, punten, vakken, systeem, van, tot, tijdzones)
    api_beurten, api_kwaliteit, api_gift = api_rijen(database, tuin["id"], van, tot)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"bestanden": {"gift": gift, "kwaliteit": kwaliteit, "beurten": beurten},
                       "api": {"beurten": api_beurten, "kwaliteit": api_kwaliteit,
                               "gift": [{"vaknummer": v, "datum": d, **w} for (v, d), w in api_gift.items()]}},
                      f, default=str, ensure_ascii=False, indent=1)

    print(f"[{stempel}] {tuin['naam']}: bestanden naast de API, {van:%d-%m-%y} t/m {tot:%d-%m-%y}"
          + (f" (dagbestand ontbreekt: {', '.join(f'{d:%d-%m}' for d in ontbreekt)})" if ontbreekt else ""))
    totaal = {"dagen": 0, "dagen_gelijk": 0, "zonder_api": 0}
    afwijkend_beurt, afwijkend_kwal, afwijkend_aantal = [], [], []
    dag = van
    while dag <= tot:
        b_dag = [b for b in beurten if b["datum"] == dag]
        a_dag = [a for a in api_beurten if a["datum"] == dag]
        paren, alleen_b, alleen_a = koppel_beurten(b_dag, a_dag)
        beurt_af = [(b, a, v) for b, a in paren if (v := verschillen_beurt(b, a))]
        kb = next((k for k in kwaliteit if k["datum"] == dag), None)
        ka = next((k for k in api_kwaliteit if k["datum"] == dag and k["watersysteem"] == systeem), None)
        kwal_af = verschillen_kwaliteit(kb or {}, ka or {}) if (kb or ka) else {}
        aantal_af = []
        for g in (g for g in gift if g["datum"] == dag):
            a = api_gift.get((g["vaknummer"], dag))
            if a and a["bron"] == "priva" and a["beurten"] is not None and a["beurten"] != g["beurten"]:
                aantal_af.append((g["vaknummer"], g["beurten"], a["beurten"]))
        geen_api = not a_dag and not ka
        gelijk = not (beurt_af or alleen_b or alleen_a or kwal_af or aantal_af)
        totaal["dagen"] += not geen_api
        totaal["zonder_api"] += geen_api
        totaal["dagen_gelijk"] += gelijk and not geen_api
        starts = [abs((b["start"] - a["start"]).total_seconds()) for b, a in paren]
        regel = (f"  {dag:%a %d-%m}: beurten {len(b_dag)} bestanden / {len(a_dag)} API, {len(paren)} gekoppeld"
                 + (f" (start ±{median(starts):.0f} s)" if starts else "")
                 + (f", {len(beurt_af)} met verschil" if beurt_af else "")
                 + (f", alleen bestanden {len(alleen_b)}" if alleen_b else "")
                 + (f", alleen API {len(alleen_a)}" if alleen_a else "")
                 + ("; EC/pH-dag " + ("ontbreekt in de bestanden" if not kb else
                                      "ontbreekt bij de API" if not ka else
                                      "gelijk" if not kwal_af else f"verschil in {', '.join(kwal_af)}"))
                 + (f"; aantal beurten anders bij {len(aantal_af)} vakken" if aantal_af else "")
                 + ("  [geen API-gegevens]" if geen_api else "  OK" if gelijk else ""))
        print(regel)
        afwijkend_beurt += [(dag, "verschil", b, a, v) for b, a, v in beurt_af]
        afwijkend_beurt += [(dag, "alleen bestanden", b, None, None) for b in alleen_b]
        afwijkend_beurt += [(dag, "alleen API", None, a, None) for a in alleen_a]
        if kwal_af:
            afwijkend_kwal.append((dag, kwal_af))
        afwijkend_aantal += [(dag, *x) for x in aantal_af]
        dag += timedelta(days=1)

    if args.details:
        for dag, soort, b, a, v in afwijkend_beurt:
            x = b or a
            print(f"    {dag:%d-%m} vak {x['vaknummer']:2} {soort}: start {_tijd(b and b['start'])} / "
                  f"{_tijd(a and a['start'])}, l/m² {b and b['liter_per_m2']} / {a and a['liter_per_m2']}, "
                  f"EC {b and b['ec']} / {a and a['ec']}, pH {b and b['ph']} / {a and a['ph']}, "
                  f"flow {b and b['flow']} / {a and a['flow']}" + (f"  ← {', '.join(v)}" if v else ""))
        for dag, v in afwijkend_kwal:
            print(f"    {dag:%d-%m} EC/pH-dag: " + ", ".join(f"{k} {x} / {y}" for k, (x, y) in v.items()))
        for dag, vak, x, y in afwijkend_aantal:
            print(f"    {dag:%d-%m} vak {vak:2}: {x} beurten in de bestanden, {y} bij de API")
    print(f"[{stempel}] {tuin['naam']}: {totaal['dagen_gelijk']} van {totaal['dagen']} dagen gelijk aan de API"
          + (f", {totaal['zonder_api']} dagen zonder API-gegevens" if totaal["zonder_api"] else "")
          + f" (marges: start {MARGES['start_s']} s, l/m² {MARGES['liter_per_m2']}, EC/pH 0,1)")


if __name__ == "__main__":
    main()

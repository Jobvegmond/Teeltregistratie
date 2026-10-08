"""
Warmte en gas per dag uit de pulsmeters in de Priva-bestanden op de NAS (map Priva), voor de tuin
van die klimaatcomputer (standaard tuin 3, regelaar VP9508): pulsmeter 2 = warmte (GJ, opgeslagen
in MJ in energiedata_dag), pulsmeter 1 = gas (m³, gasdata_dag). Het rekenwerk staat in
logic/pulsmeters.py.

Standaard vult het alleen dagen aan die nog niet in de database staan: cijfers uit de
energie-export van Priva (handmatig ingelezen) blijven staan. Met --overschrijven gaan ook
bestaande dagen over. Een dag wordt alleen opgeslagen als hij voorbij en helemaal gedekt is.

Gebruik:
    python priva_pulsmeters.py                      # laatste 14 dagen, naar DATABASE_URL
    python priva_pulsmeters.py --vanaf 2026-09-28   # vanaf een datum
    python priva_pulsmeters.py --droog              # alleen tonen, niets opslaan
    python priva_pulsmeters.py --doel productie     # naar DATABASE_URL_PRODUCTIE

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal
bijv. \\\\192.168.0.197\\Priva). Daarin "bron historie" (pulsmeters_*.csv, per uur) en
"bron live" (historie-<datum>.jsonl, per minuut).

Synology Taakplanner (root), bijv. elk uur:
    docker exec vemteelt-app python priva_pulsmeters.py --doel productie
Sluit af met een foutcode als er iets misging, zodat de mail bij een fout werkt.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

GEBRUIKER = "priva-pulsmeters"
GJ_NAAR_MJ = 1000


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva (met 'bron live')")
    parser.add_argument("--vanaf", type=date.fromisoformat, help="eerste dag (standaard 14 dagen terug)")
    parser.add_argument("--tot", type=date.fromisoformat, help="laatste dag (standaard gisteren)")
    parser.add_argument("--pcu", default="VP9508", help="regelaar; bepaalt de tuin (tuinen.priva_device_id)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--overschrijven", action="store_true", help="ook dagen die al in de database staan")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    return parser.parse_args()


def lees_bestanden(map_, vanaf):
    """Alle tellerstanden vanaf de dag vóór `vanaf` uit de historie-CSV's en de live-JSONL's."""
    from logic import pulsmeters as pm
    bronnen = []
    for pad in sorted((map_ / "bron historie").glob("pulsmeters_*.csv")):
        with open(pad, encoding="utf-8") as f:
            bronnen.append(pm.lees_historie_csv(f))
    for pad in sorted((map_ / "bron live").glob("historie-*.jsonl")):
        gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
        if gevonden and date.fromisoformat(gevonden.group(1)) < vanaf - timedelta(days=1):
            continue
        with open(pad, encoding="utf-8") as f:
            bronnen.append(pm.lees_live_jsonl(f))
    return pm.samenvoegen(*bronnen)


def main():
    args = lees_argumenten()
    vandaag = date.today()
    vanaf = args.vanaf or vandaag - timedelta(days=14)
    tot = min(args.tot or vandaag - timedelta(days=1), vandaag - timedelta(days=1))

    # De doeldatabase moet vaststaan vóór database.py geladen wordt (zie priva_ophalen.py).
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import pulsmeters as pm

    stempel = datetime.now().strftime("%d-%m-%y %H:%M")
    map_ = Path(args.map)
    if not (map_ / "bron live").is_dir() and not (map_ / "bron historie").is_dir():
        print(f"[{stempel}] FOUT: geen Priva-bestanden in {map_}", file=sys.stderr)
        sys.exit(1)

    tuin = next((t for t in database.get_tuinen() if t.get("priva_device_id") == args.pcu), None)
    if tuin is None:
        print(f"[{stempel}] FOUT: geen tuin met regelaar {args.pcu}", file=sys.stderr)
        sys.exit(1)

    standen = lees_bestanden(map_, vanaf)
    per_meter = {n: pm.dagverbruik(standen.get(n, [])) for n in pm.METERS}

    with database.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT datum FROM energiedata_dag WHERE tuin_id = %s", (tuin["id"],))
        al_warmte = {r[0] for r in c.fetchall()}
        c.execute("SELECT datum FROM gasdata_dag WHERE tuin_id = %s", (tuin["id"],))
        al_gas = {r[0] for r in c.fetchall()}

    warmte_dagen, gas_dagen, overgeslagen = [], [], []
    dag = vanaf
    while dag <= tot:
        warmte_gj = per_meter[2][0].get(dag)
        gas_m3 = per_meter[1][0].get(dag)
        nieuw_w = warmte_gj is not None and (args.overschrijven or str(dag) not in al_warmte)
        nieuw_g = gas_m3 is not None and (args.overschrijven or str(dag) not in al_gas)
        status = []
        if warmte_gj is None or gas_m3 is None:
            status.append("onvolledig")
        if not nieuw_w and warmte_gj is not None:
            status.append("warmte stond er al")
        if not nieuw_g and gas_m3 is not None:
            status.append("gas stond er al")
        print(f"{dag}  warmte {'-' if warmte_gj is None else f'{warmte_gj:8.1f} GJ'}  "
              f"gas {'-' if gas_m3 is None else f'{gas_m3:8.0f} m3'}  {', '.join(status)}")
        if nieuw_w:
            warmte_dagen.append(dag)
            if not args.droog:
                database.upsert_energiedata_dag(dag, round(warmte_gj * GJ_NAAR_MJ, 1), tuin_id=tuin["id"])
        if nieuw_g:
            gas_dagen.append(dag)
            if not args.droog:
                database.upsert_gasdata_dag(dag, round(gas_m3, 1), tuin_id=tuin["id"])
        if warmte_gj is None or gas_m3 is None:
            overgeslagen.append(dag)
        dag += timedelta(days=1)

    samenvatting = (f"{tuin['naam']}: warmte {len(warmte_dagen)} dagen, gas {len(gas_dagen)} dagen opgeslagen "
                    f"({vanaf:%d-%m-%y} t/m {tot:%d-%m-%y}; {len(overgeslagen)} dagen onvolledig)")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting.replace(' opgeslagen', '')}")
        return
    if warmte_dagen or gas_dagen:
        database.log_wijziging(GEBRUIKER, "opgehaald", "energie_pulsmeters", None, samenvatting)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

"""
Warmte en gas per dag uit de pulsmeters in de Priva-bestanden op de NAS (map Priva). Welke pulsmeter
wat meet staat per tuin in config.PRIVA_BESTANDEN: tuin 3 pulsmeter 2 = warmte (GJ, opgeslagen in MJ in
energiedata_dag) en pulsmeter 1 = gas (m³, gasdata_dag); tuin 1 alleen pulsmeter 1 = gas (de warmte komt
daar van de warmtewisselaar: Priva's dagwaarde "warmte gisteren" (scherm M302.1, gemiddeld kW × 24 uur), anders
het gerealiseerde vermogen (scherm M340.0, kW) maal de tijd, uit overig-<datum>.jsonl;
logic/warmtewisselaar.py). Het rekenwerk staat in logic/pulsmeters.py.

Standaard vult het alleen dagen aan die nog niet in de database staan: cijfers uit de
energie-export van Priva (handmatig ingelezen) blijven staan. Uitzondering: de dagwaarde "warmte gisteren"
van tuin 1 gaat altijd voor (hetzelfde als de export, die alleen de dag van de wintertijd verschuift). Met
--overschrijven gaan ook bestaande dagen over. Een dag wordt alleen opgeslagen als hij voorbij en helemaal
gedekt is.

Gebruik:
    python priva_pulsmeters.py                      # tuin 3, laatste 14 dagen, naar DATABASE_URL
    python priva_pulsmeters.py --tuin 1             # tuin 1 (alleen gas)
    python priva_pulsmeters.py --vanaf 2026-09-28   # vanaf een datum
    python priva_pulsmeters.py --droog              # alleen tonen, niets opslaan
    python priva_pulsmeters.py --doel productie     # naar DATABASE_URL_PRODUCTIE

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal
bijv. \\\\192.168.0.197\\Priva), met de historie (pulsmeters_*.csv, per uur; alleen tuin 3) en de
live-bestanden (historie-<datum>.jsonl, per minuut).

Per tuin (--tuin, standaard 3) staan de mappen en de regelaar in config.PRIVA_BESTANDEN: tuin 3 (VP9508) in
`bron live` en `bron historie`, tuin 1 (Matricaria25) in `bron historie/Tuin 1/live` en `.../historie`. De
regelaar in de bestanden wordt gecontroleerd, zodat de gegevens nooit bij de verkeerde tuin komen.

Synology Taakplanner (root), elk uur; een losse container uit het app-image met de map Priva
(/volume2/Priva) alleen-lezen erbij, net als de taak Priva-data ophalen. .env.taak levert
DATABASE_URL = productie; de NAS-database krijgt het via de wekelijkse kopie:
    LOG=/volume2/Appdata/VEMteelt/logs/pulsmeters.log
    echo "--- $(date '+%d-%m-%y %H:%M') start" >> "$LOG"
    /usr/local/bin/docker run --rm -v /volume2/Priva:/priva:ro \\
        --env-file /volume2/Appdata/VEMteelt/.env.taak vemteelt-app:latest \\
        python priva_pulsmeters.py >> "$LOG" 2>&1
Sluit af met een foutcode als er iets misging, zodat de mail bij een fout werkt.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

GEBRUIKER = "priva-pulsmeters"
GJ_NAAR_MJ = 1000


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva (met 'bron live')")
    parser.add_argument("--vanaf", type=date.fromisoformat, help="eerste dag (standaard 14 dagen terug)")
    parser.add_argument("--tot", type=date.fromisoformat, help="laatste dag (standaard: de laatste dag met metingen)")
    parser.add_argument("--tuin", type=int, default=3,
                        help="tuinnummer (standaard 3); de mappen en de regelaar staan in config.PRIVA_BESTANDEN")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--overschrijven", action="store_true", help="ook dagen die al in de database staan")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    return parser.parse_args()


def lees_bestanden(live, historie, vanaf):
    """Alle tellerstanden vanaf de dag vóór `vanaf` uit de historie-CSV's en de live-JSONL's."""
    from logic import pulsmeters as pm
    bronnen = []
    for pad in sorted(historie.glob("pulsmeters_*.csv")):
        with open(pad, encoding="utf-8") as f:
            bronnen.append(pm.lees_historie_csv(f))
    for pad in sorted(live.glob("historie-*.jsonl")):
        gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
        if gevonden and date.fromisoformat(gevonden.group(1)) < vanaf - timedelta(days=1):
            continue
        with open(pad, encoding="utf-8") as f:
            bronnen.append(pm.lees_live_jsonl(f))
    return pm.samenvoegen(*bronnen)


def main():
    args = lees_argumenten()
    vanaf = args.vanaf or date.today() - timedelta(days=14)

    # De doeldatabase moet vaststaan vóór database.py geladen wordt (zie priva_ophalen.py).
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import priva_bron
    from logic import pulsmeters as pm

    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    live, historie = priva_bron.mappen(args.map, args.tuin)
    if not live.is_dir() and not historie.is_dir():
        print(f"[{stempel}] FOUT: geen Priva-bestanden van tuin {args.tuin} in {live} of {historie}",
              file=sys.stderr)
        sys.exit(1)

    tuin = next((t for t in database.get_tuinen() if t["nummer"] == args.tuin), None)
    fout = priva_bron.controleer_regelaar(live, args.tuin) if tuin else f"geen tuin {args.tuin} in de database"
    if fout:
        print(f"[{stempel}] FOUT: {fout}", file=sys.stderr)
        sys.exit(1)
    # Welke pulsmeter wat meet, per tuin (tuin 1 heeft alleen gas; de warmte komt daar van de warmtewisselaar).
    meter_van = {soort: n for n, soort in priva_bron.instellingen(args.tuin)["meters"].items()}
    vermogen = priva_bron.instellingen(args.tuin).get("warmte_vermogen")
    met_warmte = "warmte" in meter_van or bool(vermogen)

    standen = lees_bestanden(live, historie, vanaf)
    per_meter = {n: pm.dagverbruik(standen.get(n, [])) for n in meter_van.values()}
    # Tot en met de laatste dag met metingen (die zelf telt alleen als hij volledig is). Niet de klok van
    # de container: die loopt in UTC, en om 01:00 's nachts was het daar nog "gisteren".
    laatste = max((t for reeks in standen.values() for t, _ in reeks), default=datetime.combine(vanaf, datetime.min.time()))
    tot = args.tot or laatste.date()

    with database.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT datum, warmte_mj_totaal FROM energiedata_dag WHERE tuin_id = %s", (tuin["id"],))
        al_warmte = {r[0]: r[1] for r in c.fetchall()}
        c.execute("SELECT datum FROM gasdata_dag WHERE tuin_id = %s", (tuin["id"],))
        al_gas = {r[0] for r in c.fetchall()}

    # Tuin 1: de warmte per dag van de warmtewisselaar. Eerst Priva's eigen dagwaarde (scherm "warmte gisteren",
    # gemiddeld kW × 24 uur); die gaat ook voor wat er al staat (de Energie-export geeft hetzelfde, behalve op de
    # dag van de wintertijd, en de oude schatting uit het vermogen zat ernaast). Valt die weg, dan het vermogen
    # maal de tijd (alleen dagen die er nog niet staan; de dagbestanden zijn groot).
    warmte_ww, priva_dag = {}, set()
    if vermogen:
        from logic import warmtewisselaar as ww
        bestanden = []
        for pad in sorted(live.glob("overig-*.jsonl")):
            gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
            dag_bestand = date.fromisoformat(gevonden.group(1)) if gevonden else None
            if dag_bestand and vanaf <= dag_bestand <= tot + timedelta(days=1):
                bestanden.append((dag_bestand, pad))
        for _, pad in bestanden:
            with open(pad, encoding="utf-8") as f:
                for dag_ww, kw in ww.gisteren_kw(f).items():
                    if vanaf <= dag_ww <= tot:
                        warmte_ww[dag_ww] = kw * 24 * 3.6 / 1000        # gem. kW × 24 u = kWh → GJ
                        priva_dag.add(dag_ww)
        for dag_bestand, pad in bestanden:
            if dag_bestand > tot or dag_bestand in priva_dag or (
                    str(dag_bestand) in al_warmte and not args.overschrijven):
                continue
            with open(pad, encoding="utf-8") as f:
                dag_ww, kwh = ww.dag_kwh(f, vermogen)
            if dag_ww and kwh is not None:
                warmte_ww[dag_ww] = kwh * 3.6 / 1000          # kWh → GJ

    warmte_dagen, gas_dagen, overgeslagen = [], [], []
    dag = vanaf
    while dag <= tot:
        if "warmte" in meter_van:
            warmte_gj = per_meter[meter_van["warmte"]][0].get(dag)
        else:
            warmte_gj = warmte_ww.get(dag) if vermogen else None
        gas_m3 = per_meter[meter_van["gas"]][0].get(dag) if "gas" in meter_van else None
        nieuw_w = warmte_gj is not None and (args.overschrijven or str(dag) not in al_warmte or (
            dag in priva_dag and round(warmte_gj * GJ_NAAR_MJ, 1) != al_warmte[str(dag)]))
        nieuw_g = gas_m3 is not None and (args.overschrijven or str(dag) not in al_gas)
        # Onvolledig = een meter van deze tuin heeft die dag geen volledige reeks.
        onvolledig = (met_warmte and warmte_gj is None and not (vermogen and str(dag) in al_warmte)) or (
            "gas" in meter_van and gas_m3 is None)
        status = []
        if onvolledig:
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
        if onvolledig:
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

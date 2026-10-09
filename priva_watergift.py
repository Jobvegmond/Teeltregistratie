"""
Watergift per vak per dag (l/m², EC, pH) uit de Priva-bestanden op de NAS (map Priva), voor de tuin van
die klimaatcomputer (standaard tuin 3, regelaar VP9508). Rekenwerk en inlezen in logic/priva_watergift.py.

- Afgeronde dagen uit `bron historie/water/kraan-per-dag.csv` (bron 'priva-dag'): alleen waar nog niets
  staat of waar Excel staat. Wat de Priva-API zette blijft staan (EC/pH daar nauwkeuriger); met
  --overschrijven gaan ook die over.
- Vandaag tot nu toe uit `bron live/water-actueel.json` (bron 'priva-vandaag'): elke run bijgewerkt. De API
  slaat vandaag over; na middernacht vervangt het dagbestand of de API dit door de definitieve dag.

Het aantal gietbeurten staat niet in deze bestanden (blijft leeg); de API vult het nog aan zolang die loopt.

Gebruik:
    python priva_watergift.py                      # naar DATABASE_URL
    python priva_watergift.py --droog              # alleen tonen
    python priva_watergift.py --doel productie     # naar DATABASE_URL_PRODUCTIE

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal bijv.
\\\\192.168.0.197\\Priva).

Synology Taakplanner (root), bijv. elk uur, net als priva_pulsmeters.py:
    /usr/local/bin/docker run --rm -v /volume2/Priva:/priva:ro \\
        --env-file /volume2/Appdata/VEMteelt/.env.taak vemteelt-app:latest python priva_watergift.py
Sluit af met een foutcode als er iets misging.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GEBRUIKER = "priva-watergift"


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva")
    parser.add_argument("--dagen", type=int, default=14, help="hoeveel afgeronde dagen terug (standaard 14)")
    parser.add_argument("--pcu", default="VP9508", help="regelaar; bepaalt de tuin (tuinen.priva_device_id)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--overschrijven", action="store_true", help="ook dagen die de Priva-API al zette")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    return parser.parse_args()


def main():
    args = lees_argumenten()
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import priva_watergift as pwg

    # De klok van de container loopt in UTC; de dag en het uur van "vandaag" komen uit het bestand zelf.
    nu = datetime.now(timezone.utc)
    stempel = f"{nu:%d-%m-%y %H:%M} UTC"
    map_ = Path(args.map)
    dagbestand = map_ / "bron historie" / "water" / "kraan-per-dag.csv"
    actueel = map_ / "bron live" / "water-actueel.json"
    if not dagbestand.exists() and not actueel.exists():
        print(f"[{stempel}] FOUT: geen waterbestanden in {map_}", file=sys.stderr)
        sys.exit(1)
    tuin = next((t for t in database.get_tuinen() if t.get("priva_device_id") == args.pcu), None)
    if tuin is None:
        print(f"[{stempel}] FOUT: geen tuin met regelaar {args.pcu}", file=sys.stderr)
        sys.exit(1)

    dagen = []
    if dagbestand.exists():
        with open(dagbestand, encoding="utf-8") as f:
            dagen = pwg.lees_kraan_per_dag(f)
        if dagen:
            laatste = max(r["datum"] for r in dagen)
            dagen = [r for r in dagen if r["datum"] > laatste - timedelta(days=args.dagen)]
    vandaag, vandaag_rijen = (None, [])
    if actueel.exists():
        vandaag, vandaag_rijen = pwg.lees_vandaag(actueel.read_text(encoding="utf-8"), nu)
    # Staat een dag al als afgeronde dag in het dagbestand, dan telt de lopende stand niet.
    if vandaag and any(r["datum"] == vandaag for r in dagen):
        vandaag_rijen = []

    opgeslagen = {"dag": 0, "vandaag": 0}
    for soort, rijen, bron in (("dag", dagen, database.WATERGIFT_BRON_BESTAND_DAG),
                               ("vandaag", vandaag_rijen, database.WATERGIFT_BRON_BESTAND_VANDAAG)):
        per_dag = {}
        for r in rijen:
            per_dag.setdefault(r["datum"], []).append(r)
        for dag, rij_dag in sorted(per_dag.items()):
            met_gift = [r for r in rij_dag if r["liter_per_m2"]]
            nieuw = 0
            if not args.droog:
                for r in rij_dag:
                    nieuw += database.upsert_watergift_dag_bestand(
                        r["vak"], r["datum"], r["liter_per_m2"], r["ec"], r["ph"], bron,
                        tuin_id=tuin["id"], overschrijven=args.overschrijven)
            opgeslagen[soort] += nieuw
            print(f"{dag} ({'tot nu toe' if soort == 'vandaag' else 'afgerond'}): {len(rij_dag)} vakken, "
                  f"{len(met_gift)} met gift, samen {sum(r['liter_per_m2'] for r in rij_dag):.1f} l/m²"
                  + ("" if args.droog else f"; {nieuw} vakken opgeslagen"))

    samenvatting = (f"{tuin['naam']}: {opgeslagen['dag']} vak-dagen afgerond, {opgeslagen['vandaag']} vakken van "
                    f"vandaag ({vandaag:%d-%m-%y}) opgeslagen" if vandaag else
                    f"{tuin['naam']}: {opgeslagen['dag']} vak-dagen afgerond opgeslagen (geen actuele stand van vandaag)")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen.")
        return
    if opgeslagen["dag"]:
        database.log_wijziging(GEBRUIKER, "opgehaald", "watergift_bestanden", None, samenvatting)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

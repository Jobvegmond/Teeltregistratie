"""
Klimaat per uur per afdeling (temperatuur, RV, vochtdeficit, CO2, buistemperatuur) en de meteo per uur uit
de Priva-bestanden op de NAS (map Priva), voor de tuin van die klimaatcomputer (standaard tuin 3, regelaar
VP9508). Rekenwerk en inlezen in logic/klimaat_uur.py; de grafieken op de pagina Tuin gebruiken dit.

- `bron historie/priva_*_per-uur.csv`: de momentwaarde op elk heel uur (het jaar terug).
- `bron live/historie-<datum>.jsonl`: per minuut; een uur = het gemiddelde van zijn minuten. Gaat voor de CSV.

Een uur dat er al staat wordt overschreven (de bestanden zijn de bron). Alleen voorbije uren.

Gebruik:
    python priva_klimaat.py                      # laatste 3 dagen, naar DATABASE_URL
    python priva_klimaat.py --vanaf 2025-10-07   # het hele jaar uit de historie-CSV
    python priva_klimaat.py --droog              # alleen tonen, niets opslaan
    python priva_klimaat.py --doel productie     # naar DATABASE_URL_PRODUCTIE

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal bijv.
\\\\192.168.0.197\\Priva). Draait elk uur via priva_bestanden.py. Sluit af met een foutcode als er iets misging.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GEBRUIKER = "priva-klimaat"


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva")
    parser.add_argument("--vanaf", type=date.fromisoformat, help="eerste dag (standaard 3 dagen terug)")
    parser.add_argument("--pcu", default="VP9508", help="regelaar; bepaalt de tuin (tuinen.priva_device_id)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    return parser.parse_args()


def lees_bestanden(map_, vanaf):
    """(historie, live) vanaf de dag `vanaf` (lijsten van (tijd, afd, meteo), zie logic/klimaat_uur.py)."""
    from logic import klimaat_uur as ku
    begin = datetime.combine(vanaf, datetime.min.time())
    historie, live = [], []
    for pad in sorted((map_ / "bron historie").glob("priva_*_per-uur.csv")):
        with open(pad, encoding="utf-8") as f:
            historie += [r for r in ku.lees_historie_csv(f) if r[0] >= begin]
    for pad in sorted((map_ / "bron live").glob("historie-*.jsonl")):
        gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
        if gevonden and date.fromisoformat(gevonden.group(1)) < vanaf:
            continue
        with open(pad, encoding="utf-8") as f:
            live += [r for r in ku.lees_live_jsonl(f) if r[0] >= begin]
    return historie, live


def main():
    args = lees_argumenten()
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from logic import klimaat_uur as ku

    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    map_ = Path(args.map)
    if not (map_ / "bron live").is_dir() and not (map_ / "bron historie").is_dir():
        print(f"[{stempel}] FOUT: geen Priva-bestanden in {map_}", file=sys.stderr)
        sys.exit(1)
    tuin = next((t for t in database.get_tuinen() if t.get("priva_device_id") == args.pcu), None)
    if tuin is None:
        print(f"[{stempel}] FOUT: geen tuin met regelaar {args.pcu}", file=sys.stderr)
        sys.exit(1)

    # De klok van de container loopt in UTC; "3 dagen terug" is ruim genoeg om dat op te vangen.
    vanaf = args.vanaf or date.today() - timedelta(days=3)
    historie, live = lees_bestanden(map_, vanaf)
    afd, meteo = ku.per_uur(historie, live)
    if not afd and not meteo:
        print(f"[{stempel}] FOUT: geen klimaatmetingen vanaf {vanaf:%d-%m-%y} in {map_}", file=sys.stderr)
        sys.exit(1)
    uren = sorted({uur for uur, _ in afd} | set(meteo))
    eerste, laatste = uren[0], uren[-1]

    # Per dag het etmaalgemiddelde per afdeling, ter controle in het log (alleen bij weinig dagen).
    if (laatste - eerste).days <= 14:
        per_dag = {}
        for (uur, n), w in afd.items():
            if "temp" in w:
                per_dag.setdefault((uur.date(), n), []).append(w["temp"])
        for dag in sorted({d for d, _ in per_dag}):
            delen = [f"afd {n} {sum(v) / len(v):5.1f} °C ({len(v):2d} u)"
                     for (d, n), v in sorted(per_dag.items()) if d == dag]
            print(f"{dag}  " + "  ".join(delen))

    samenvatting = (f"{tuin['naam']}: klimaat {len(afd)} afdeling-uren, meteo {len(meteo)} uren "
                    f"({eerste:%d-%m-%y %H:%M} t/m {laatste:%d-%m-%y %H:%M})")
    if args.droog:
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting}")
        return
    database.init_db()      # maakt klimaat_uur en meteo_uur aan als ze er nog niet zijn (nieuw in 2.11.0)
    database.upsert_klimaat_uur(afd, meteo, tuin["id"])
    if args.vanaf:      # een grote aanvulling in het logboek; de uurlijkse run niet (te veel regels)
        database.log_wijziging(GEBRUIKER, "opgehaald", "klimaat_uur", None, samenvatting)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

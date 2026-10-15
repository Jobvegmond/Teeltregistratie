"""
Een deelexport uit Agro4all (registraties vanaf een datum) samenvoegen met de volledige export op de NAS.

De geplande Claude-taak "agro4all-export" haalt via de Agro4all-connector de registraties van de laatste
14 dagen op (met de vakken) en schrijft die als deelexport (zelfde vorm als de export, zie
logic/agro4all.py). Dit script zet ze in de volledige export: wat ouder is dan --van blijft staan, vanaf --van
komt alles uit de deelexport. agro4all_import.py (in de uurtaak op de NAS) leest de export daarna in.

Gebruik:
    py agro4all_samenvoegen.py --nieuw nieuw.json --van 2026-10-01
    py agro4all_samenvoegen.py --nieuw nieuw.json --van 2026-10-01 --export \\\\192.168.0.197\\Appdata\\VEMteelt\\agro4all\\registraties.json
    py agro4all_samenvoegen.py ... --droog      # alleen tonen
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from logic import agro4all as a4

NAS_EXPORT = r"\\192.168.0.197\Appdata\VEMteelt\agro4all\registraties.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--nieuw", required=True, help="de deelexport (JSON met 'registraties')")
    parser.add_argument("--van", required=True, type=date.fromisoformat,
                        help="eerste dag van de deelexport (Nederlandse tijd)")
    parser.add_argument("--export", default=NAS_EXPORT, help="de volledige export die bijgewerkt wordt")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets schrijven")
    args = parser.parse_args()

    with open(args.nieuw, encoding="utf-8") as f:
        nieuw = json.load(f)
    fouten = [r.get("id", "?") for r in nieuw.get("registraties", [])
              if not r.get("id") or r.get("tuin") not in (1, 3) or not isinstance(r.get("vakken"), list)
              or not r.get("producten")]
    if fouten:
        print(f"FOUT: onvolledige registraties in de deelexport: {fouten}", file=sys.stderr)
        sys.exit(1)
    pad = Path(args.export)
    if not pad.parent.exists():
        print(f"FOUT: map {pad.parent} niet bereikbaar (VPN/NAS?)", file=sys.stderr)
        sys.exit(1)
    oud = json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else None
    van = int(datetime.combine(args.van, datetime.min.time(), a4.NL).timestamp())
    uit = a4.samenvoegen(oud, nieuw, van, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    oude_ids = {r["id"] for r in (oud or {}).get("registraties", [])}
    nieuwe_ids = {r["id"] for r in uit["registraties"]}
    samenvatting = (f"{len(uit['registraties'])} registraties in de export ({len(nieuwe_ids - oude_ids)} nieuw, "
                    f"{len(oude_ids - nieuwe_ids)} weg), deelexport vanaf {args.van:%d-%m-%y}: "
                    f"{len(nieuw.get('registraties', []))}")
    if args.droog:
        print(f"DROOG: {samenvatting}")
        return
    tijdelijk = pad.with_suffix(".tmp")
    tijdelijk.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    tijdelijk.replace(pad)
    print(samenvatting)


if __name__ == "__main__":
    main()

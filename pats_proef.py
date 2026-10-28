"""
Proef met de PATS-API (alleen lezen): inloggen, de sections met hun insecten en drempels, de apparaten
(Trap-Eyes en PATS-C) en de tellingen van de afgelopen dagen tonen. Schrijft niets.

Gebruik:
    python pats_proef.py                    # testserver (beta.pats-c.com), laatste 7 dagen
    python pats_proef.py --server productie # pats-c.com (zodra v2 daar live is)
    python pats_proef.py --dagen 14
    python pats_proef.py --json uit.json    # ook de ruwe antwoorden bewaren
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta

import database  # noqa: F401  (laadt .env)
from integrations import pats


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", help="beta, productie of een adres (standaard config.PATS_SERVER)")
    parser.add_argument("--dagen", type=int, default=7, help="hoeveel dagen terug (standaard 7)")
    parser.add_argument("--json", help="bestand voor de ruwe antwoorden")
    return parser.parse_args()


def main():
    args = lees_argumenten()
    sys.stdout.reconfigure(encoding="utf-8")
    login = pats.inloggegevens()
    if not login:
        print("FOUT: PATS_USER en/of PATS_PASSW staan niet in .env.", file=sys.stderr)
        sys.exit(1)
    try:
        api = pats.Pats(*login, server=args.server)
    except pats.PatsFout as fout:
        print(f"FOUT: {fout}", file=sys.stderr)
        sys.exit(1)
    print(f"Ingelogd op {api.basis}\n")

    tot = date.today()
    van = tot - timedelta(days=args.dagen)
    ruw = {"sections": api.sections(), "spots": {}, "counts": {}}
    for s in ruw["sections"]:
        sid = s["id"]
        klassen = {str(k["id"]): k for k in s.get("detection_classes") or []}
        print(f"=== Section {sid}: {s.get('label') or s.get('name')} · gewas {s.get('crop')} · "
              f"{s.get('timezone')} ===")
        print("Insecten:")
        for k in klassen.values():
            soort = "plaag" if k.get("pest_insect") else "nuttig" if k.get("natural_enemy") or k.get("beneficial") else ""
            waar = "/".join(n for n, v in (("Trap-Eye", k.get("available_in_trapeye")), ("PATS-C", k.get("available_in_c")))
                            if v)
            drempels = [k.get(f"trapeye_level_{i}") for i in range(1, 5)]
            drempels_c = [k.get(f"c_level_{i}") for i in range(1, 5)]
            tekst = f"  {k['id']:>4} {k.get('label')}"
            tekst += f" ({soort})" if soort else ""
            tekst += f" · {waar}" if waar else ""
            if any(d is not None for d in drempels):
                tekst += f" · drempels Trap-Eye {drempels}"
            if any(d is not None for d in drempels_c):
                tekst += f" · drempels PATS-C {drempels_c}"
            print(tekst)

        try:
            spots = ruw["spots"][sid] = api.spots(sid)
        except pats.PatsFout as fout:
            print(f"  spots: {fout}")
            spots = {}
        for soort, naam in (("trapeye", "Trap-Eyes"), ("c", "PATS-C"), ("gateway", "Gateways")):
            rij = spots.get(soort) or []
            plekken = ", ".join(f"rij {p.get('row_id')} paal {p.get('post_id')}"
                                + (f" ({p['label']})" if p.get("label") else "") for p in rij)
            print(f"{naam}: {len(rij)}" + (f" — {plekken}" if plekken else ""))

        try:
            tel = ruw["counts"][sid] = api.counts(sid, van, tot)
        except pats.PatsFout as fout:
            print(f"  tellingen: {fout}\n")
            continue
        print(f"\nTellingen {van:%d-%m} t/m {tot:%d-%m} (som per apparaat):")
        for soort, sleutel, naam in (("trapeye", "new_counts", "Trap-Eye nieuw"), ("c", "counts", "PATS-C")):
            for apparaat in tel.get(soort) or []:
                som = defaultdict(int)
                for dag in apparaat.get(sleutel) or []:
                    for k, n in dag.items():
                        if k not in ("date", "datetime") and n:
                            som[k] += n
                delen = ", ".join(f"{klassen.get(k, {}).get('label', k)} {n}" for k, n in sorted(som.items()))
                print(f"  {naam} rij {apparaat.get('row_id')} paal {apparaat.get('post_id')}: {delen or 'niets'}")
            if soort == "trapeye":
                for apparaat in tel.get("trapeye") or []:
                    laatste = (apparaat.get("absolute_count") or [{}])[-1]
                    stand = ", ".join(f"{klassen.get(k, {}).get('label', k)} {n}" for k, n in laatste.items()
                                      if k != "date" and n)
                    print(f"  Trap-Eye stand rij {apparaat.get('row_id')} paal {apparaat.get('post_id')} op "
                          f"{laatste.get('date', '-')}: {stand or 'leeg'}")
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(ruw, f, ensure_ascii=False, indent=1)
        print(f"Ruwe antwoorden in {args.json}")


if __name__ == "__main__":
    main()

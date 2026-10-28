"""
Klimaat per uur per afdeling (temperatuur, RV, vochtdeficit, CO2, buistemperatuur) en de meteo per uur uit
de Priva-bestanden op de NAS (map Priva). Rekenwerk en inlezen in logic/klimaat_uur.py; de grafieken op de
pagina Tuin gebruiken dit.

- `<historie>/priva_*_per-uur.csv`: de momentwaarde op elk heel uur (het jaar terug; alleen tuin 3).
- `<live>/historie-<datum>.jsonl`: per minuut; een uur = het gemiddelde van zijn minuten. Gaat voor de CSV.

Daarna het klimaat per dag (klimaatdata_dag: etmaal, dag en nacht, RV en lichtsom; het teeltmodel rekent
hiermee) uit dezelfde minuten en de straling uit `<live>/alles-<datum>.jsonl`; rekenwerk in logic/klimaat_dag.py.
Alleen dagen die compleet zijn; de nacht van gisteren komt erbij na zonsopkomst. Bron 'bestanden': de
Priva-API (priva_ophalen.py) overschrijft die dagen niet meer en vult alleen aan wat hier ontbreekt.

Per tuin (--tuin, standaard 3) staan de mappen en de regelaar in config.PRIVA_BESTANDEN: tuin 3 (VP9508) in
`bron live` en `bron historie`, tuin 1 (Matricaria25) in `bron historie/Tuin 1/live` en `.../historie`. De
regelaar in de bestanden wordt gecontroleerd, zodat de gegevens nooit bij de verkeerde tuin komen.

Een uur dat er al staat wordt overschreven (de bestanden zijn de bron). Alleen voorbije uren.

Zonder --vanaf begint het bij de laatste dag die al in de database staat (hooguit 3 dagen terug): een gat na
een storing vult zich zo vanzelf, en een lege database (bijv. de eerste run tegen productie) krijgt alles
wat er in de bestanden staat.

Gebruik:
    python priva_klimaat.py                      # tuin 3, vanaf de laatst opgeslagen dag, naar DATABASE_URL
    python priva_klimaat.py --tuin 1             # tuin 1
    python priva_klimaat.py --vanaf 2025-10-07   # het hele jaar uit de historie-CSV
    python priva_klimaat.py --droog              # alleen tonen (per dag naast wat er nu staat), niets opslaan
    python priva_klimaat.py --doel productie     # naar DATABASE_URL_PRODUCTIE

De map met de bestanden: --map, of PRIVA_MAP in de omgeving (in de container /priva; lokaal bijv.
\\\\192.168.0.197\\Priva). Draait elk uur via priva_bestanden.py. Sluit af met een foutcode als er iets misging.
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

GEBRUIKER = "priva-klimaat"


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=os.environ.get("PRIVA_MAP", "/priva"), help="map Priva")
    parser.add_argument("--vanaf", type=date.fromisoformat, help="eerste dag (standaard: de laatst opgeslagen dag, hooguit 3 dagen terug)")
    parser.add_argument("--tuin", type=int, default=3,
                        help="tuinnummer (standaard 3); de mappen en de regelaar staan in config.PRIVA_BESTANDEN")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets opslaan")
    return parser.parse_args()


def lees_bestanden(live_map, historie_map, vanaf):
    """(historie, live) vanaf de dag `vanaf` (lijsten van (tijd, afd, meteo), zie logic/klimaat_uur.py)."""
    from logic import klimaat_uur as ku
    begin = datetime.combine(vanaf, datetime.min.time())
    historie, live = [], []
    for pad in sorted(historie_map.glob("priva_*_per-uur.csv")):
        with open(pad, encoding="utf-8") as f:
            historie += [r for r in ku.lees_historie_csv(f) if r[0] >= begin]
    for pad in sorted(live_map.glob("historie-*.jsonl")):
        gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
        if gevonden and date.fromisoformat(gevonden.group(1)) < vanaf:
            continue
        with open(pad, encoding="utf-8") as f:
            live += [r for r in ku.lees_live_jsonl(f) if r[0] >= begin]
    return historie, live


def lees_dagbestanden(live_map, vanaf, pcu):
    """
    (minuten, straling, straling_tijden) vanaf de dag `vanaf` uit historie-<datum>.jsonl en alles-<datum>.jsonl,
    zie logic/klimaat_dag.py. Zonder catalogus.csv (geen stralings-ids) is de straling None.
    """
    from logic import klimaat_dag as kd

    def dagbestanden(soort):
        for pad in sorted(live_map.glob(f"{soort}-*.jsonl")):
            gevonden = re.search(r"(\d{4}-\d{2}-\d{2})", pad.name)
            if gevonden and date.fromisoformat(gevonden.group(1)) >= vanaf:
                yield pad

    minuten = []
    for pad in dagbestanden("historie"):
        with open(pad, encoding="utf-8") as f:
            minuten += kd.lees_minuten(f)
    catalogus = live_map / "catalogus.csv"
    if not catalogus.exists():
        return minuten, None, []
    with open(catalogus, encoding="utf-8-sig") as f:
        ids = kd.stralings_ids(f, pcu)
    straling, tijden = {}, []
    for pad in dagbestanden("alles"):
        with open(pad, encoding="utf-8") as f:
            punten, t = kd.lees_straling(f, ids)
        for n, p in punten.items():
            straling.setdefault(n, []).extend(p)
        tijden += t
    return minuten, straling, tijden


def klimaat_per_dag(live_map, vanaf, tuin_nummer):
    """De rijen voor klimaatdata_dag van elke complete dag vanaf `vanaf` (logic.klimaat_dag.dagwaarden)."""
    from config import LIGGING
    from logic import klimaat_dag as kd
    from logic import priva_bron
    minuten, straling, tijden = lees_dagbestanden(live_map, vanaf, priva_bron.instellingen(tuin_nummer)["pcu"])
    if not minuten:
        return []
    rijen, dag = [], max(vanaf, min(t for t, _ in minuten).date())
    while dag < date.today():
        rijen += kd.dagwaarden(dag, LIGGING, minuten, straling, tijden)
        dag += timedelta(days=1)
    return rijen


def toon_per_dag(rijen, bestaand):
    """Per afdeling-dag de nieuwe waarden, met tussen haakjes wat er nu staat als dat anders is."""
    velden = (("gem_temperatuur", "etm"), ("gem_temperatuur_dag", "dag"), ("gem_temperatuur_nacht", "nacht"),
              ("gem_rv", "RV"), ("gem_rv_dag", "dag"), ("gem_rv_nacht", "nacht"), ("stralingssom_dag", "licht"))
    for r in rijen:
        oud = bestaand.get((r["afdeling"], r["datum"])) or {}
        delen = []
        for veld, naam in velden:
            tekst = f"{naam} {r[veld] if r[veld] is not None else '-'}"
            if oud.get(veld) is not None and oud[veld] != r[veld]:
                tekst += f" ({oud[veld]:g})"
            delen.append(tekst)
        print(f"{r['datum']} afd {r['afdeling']}  " + "  ".join(delen) + (f"  [nu: {oud['bron'] or 'oud'}]" if oud else ""))


def begin_aanvulling(database, tuin_id):
    """
    De eerste dag om in te lezen: de laatste dag in klimaat_uur, hooguit 3 dagen terug (de klok van de
    container loopt in UTC, dat vangt dit ruim op). Staat er nog niets, dan alles uit de bestanden.
    """
    try:
        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT MAX(tijdstip) FROM klimaat_uur WHERE tuin_id = %s", (tuin_id,))
            laatste = c.fetchone()[0]
    except Exception:           # tabel bestaat nog niet (alleen bij --droog)
        laatste = None
    if laatste is None:
        return date(2000, 1, 1)
    return min(date.today() - timedelta(days=3), date.fromisoformat(laatste[:10]))


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
    from logic import priva_bron

    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    live, historie_map = priva_bron.mappen(args.map, args.tuin)
    if not live.is_dir() and not historie_map.is_dir():
        print(f"[{stempel}] FOUT: geen Priva-bestanden van tuin {args.tuin} in {live} of {historie_map}",
              file=sys.stderr)
        sys.exit(1)
    tuin = next((t for t in database.get_tuinen() if t["nummer"] == args.tuin), None)
    fout = priva_bron.controleer_regelaar(live, args.tuin) if tuin else f"geen tuin {args.tuin} in de database"
    if fout:
        print(f"[{stempel}] FOUT: {fout}", file=sys.stderr)
        sys.exit(1)

    if not args.droog:
        database.init_db()      # maakt klimaat_uur en meteo_uur aan als ze er nog niet zijn (nieuw in 2.11.0)
    vanaf = args.vanaf or begin_aanvulling(database, tuin["id"])
    historie, minuten = lees_bestanden(live, historie_map, vanaf)
    afd, meteo = ku.per_uur(historie, minuten)
    if not afd and not meteo:
        print(f"[{stempel}] FOUT: geen klimaatmetingen vanaf {vanaf:%d-%m-%y} in {live}", file=sys.stderr)
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

    dagen = klimaat_per_dag(live, vanaf, args.tuin)
    samenvatting = (f"{tuin['naam']}: klimaat {len(afd)} afdeling-uren, meteo {len(meteo)} uren "
                    f"({eerste:%d-%m-%y %H:%M} t/m {laatste:%d-%m-%y %H:%M})")
    if dagen:
        datums = sorted({r["datum"] for r in dagen})
        zonder_nacht = sorted({r["datum"] for r in dagen if r["gem_temperatuur_nacht"] is None})
        samenvatting += (f", per dag {len(dagen)} afdeling-dagen ({datums[0]:%d-%m-%y} t/m {datums[-1]:%d-%m-%y}"
                         + (f"; nacht nog niet compleet: {', '.join(f'{d:%d-%m}' for d in zonder_nacht)}"
                            if zonder_nacht else "") + ")")
    if args.droog:
        if dagen:
            try:
                bestaand = database.get_klimaatdata_dagen(tuin["id"], dagen[0]["datum"], dagen[-1]["datum"])
            except Exception:   # kolom bron bestaat nog niet (init_db draait niet bij --droog)
                bestaand = {}
            toon_per_dag(dagen, bestaand)
        print(f"[{stempel}] DROOG, niets opgeslagen; zou opslaan: {samenvatting}")
        return
    database.upsert_klimaat_uur(afd, meteo, tuin["id"])
    database.upsert_klimaatdata_bestanden(dagen, tuin["id"])
    if (laatste - eerste).days > 7:      # een grote aanvulling in het logboek; de uurlijkse run niet
        database.log_wijziging(GEBRUIKER, "opgehaald", "klimaat_uur", None, samenvatting)
    print(f"[{stempel}] {samenvatting}")


if __name__ == "__main__":
    main()

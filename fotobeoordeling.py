"""
Foto's beoordelen op plagen zonder Anthropic-API (Registreren → Foto in de app).

Zo loopt het:
1. De teler stuurt in de app een foto in; die komt in de tabel foto_beoordeling met status "wacht".
2. De geplande taak "Foto's beoordelen" (Claude Code op de werklaptop, elk uur 07–19) haalt de wachtende foto's op:
       py fotobeoordeling.py ophalen --doel productie --uit %TEMP%\\fotos        (alleen lezen)
   bekijkt ze (opdracht.md staat in die map), schrijft per foto <id>.json en zet de uitslagen op de NAS:
       py fotobeoordeling.py klaarzetten --map %TEMP%\\fotos
   → \\\\192.168.0.197\\Appdata\\VEMteelt\\agro4all\\fotos\\uitslag-<id>.json
3. De uurtaak op de NAS (priva_bestanden.py) draait `fotobeoordeling.py` (= verwerk): elke uitslag van een foto die
   nog wacht gaat in de tabel (status "klaar") en, als er vakken bij de foto gekozen zijn, als opmerking
   (Ziekte/plagen) bij die vakken. Het beeld van foto's die langer dan FOTO_BEWAREN_DAGEN beoordeeld zijn gaat weg.

Gebruik:
    python fotobeoordeling.py ophalen [--doel productie] --uit MAP
    python fotobeoordeling.py klaarzetten --map MAP [--naar NASMAP]
    python fotobeoordeling.py [verwerk] [--droog] [--uitslagen MAP]
"""
import argparse
import json
import os
import sys
from pathlib import Path

NAS_MAP = r"\\192.168.0.197\Appdata\VEMteelt\agro4all\fotos"       # vanaf de werklaptop
CONTAINER_MAP = "/agro4all/fotos"                                   # in de container op de NAS
FOTO_BEWAREN_DAGEN = 60


def lees_argumenten(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("actie", nargs="?", default="verwerk", choices=("ophalen", "klaarzetten", "verwerk"))
    parser.add_argument("--uit", help="ophalen: de werkmap voor de foto's")
    parser.add_argument("--map", help="klaarzetten: de werkmap met de uitslagen")
    parser.add_argument("--naar", default=NAS_MAP, help="ophalen/klaarzetten: de map op de NAS")
    parser.add_argument("--uitslagen", default=os.environ.get("FOTO_MAP", CONTAINER_MAP),
                        help="verwerk: de map met klaargezette uitslagen")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="verwerk: alleen tonen, niets opslaan")
    args, _rest = parser.parse_known_args(argv)        # priva_bestanden.py geeft ook andere argumenten mee
    return args


def _tabel_ontbreekt(fout):
    return getattr(fout, "pgcode", None) == "42P01"          # undefined_table


def ophalen(args):
    """Wachtende foto's (zonder klaargezette uitslag) als <id>.jpg in de werkmap, met wachtrij.json en opdracht.md."""
    import psycopg2

    import database
    from logic import plaagherkenning as ph

    uit = Path(args.uit)
    uit.mkdir(parents=True, exist_ok=True)
    for oud in list(uit.glob("*.jpg")) + list(uit.glob("*.json")):
        oud.unlink()
    try:
        wachtend = database.get_fotos(status="wacht")
    except psycopg2.Error as fout:
        if _tabel_ontbreekt(fout):
            print("0 foto's te beoordelen (de tabel foto_beoordeling bestaat nog niet).")
            return []
        raise
    naar = Path(args.naar)
    al_klaar = {p.stem.removeprefix("uitslag-") for p in naar.glob("uitslag-*.json")} if naar.is_dir() else set()
    tuinen = {t["id"]: t["nummer"] for t in database.get_tuinen()}
    lijst = []
    for f in reversed(wachtend):                               # oudste eerst
        if str(f["id"]) in al_klaar or not f.get("foto"):
            continue
        (uit / f"{f['id']}.jpg").write_bytes(f["foto"])
        lijst.append({"id": f["id"], "foto": f"{f['id']}.jpg", "tuin": tuinen.get(f["tuin_id"]),
                      "vakken": f["vakken"] or "", "datum": f["datum"], "toelichting": f["toelichting"] or "",
                      "bestandsnaam": f["bestandsnaam"] or ""})
    (uit / "wachtrij.json").write_text(json.dumps(lijst, ensure_ascii=False, indent=2), encoding="utf-8")
    (uit / "opdracht.md").write_text(ph.opdracht(), encoding="utf-8")
    print(f"{len(lijst)} foto's te beoordelen in {uit}" + (f" ({len(al_klaar)} wachten al op de NAS)"
                                                          if al_klaar else ""))
    return lijst


def klaarzetten(args):
    """Controleer de uitslagen in de werkmap en zet de goede op de NAS. Geeft het aantal fouten."""
    from logic import plaagherkenning as ph

    werk = Path(args.map)
    lijst = json.loads((werk / "wachtrij.json").read_text(encoding="utf-8"))
    naar = Path(args.naar)
    if not naar.parent.is_dir():
        print(f"FOUT: {naar.parent} is niet bereikbaar (VPN uit?).", file=sys.stderr)
        return 1
    naar.mkdir(exist_ok=True)
    gezet, fouten = 0, 0
    for item in lijst:
        bestand = werk / f"{item['id']}.json"
        if not bestand.exists():
            print(f"FOUT: geen uitslag voor foto {item['id']} ({bestand.name} ontbreekt)", file=sys.stderr)
            fouten += 1
            continue
        try:
            uitslag = json.loads(bestand.read_text(encoding="utf-8"))
        except json.JSONDecodeError as fout:
            print(f"FOUT in {bestand.name}: geen geldige JSON ({fout})", file=sys.stderr)
            fouten += 1
            continue
        problemen = ph.controleer(uitslag)
        if problemen:
            print(f"FOUT in {bestand.name}:\n- " + "\n- ".join(problemen), file=sys.stderr)
            fouten += 1
            continue
        (naar / f"uitslag-{item['id']}.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=2),
                                                         encoding="utf-8", newline="\n")
        gezet += 1
        print(f"Klaargezet: foto {item['id']}: {ph.kort(uitslag)}")
    print(f"{gezet} uitslag(en) op de NAS, {fouten} fout(en).")
    return fouten


def verwerk(args, db=None):
    """De klaargezette uitslagen in de database zetten (NAS, elk uur). Geeft het aantal verwerkte foto's."""
    import psycopg2

    from logic import plaagherkenning as ph

    if db is None:
        import database as db
    map_ = Path(args.uitslagen)
    bestanden = sorted(map_.glob("uitslag-*.json")) if map_.is_dir() else []
    if not bestanden:
        print("Geen uitslagen van foto's klaargezet.")
        return 0
    if not args.droog:
        db.maak_foto_tabel()
    try:
        wachtend = {f["id"] for f in db.get_fotos(status="wacht", met_foto=False)}
    except psycopg2.Error as fout:
        if _tabel_ontbreekt(fout):              # alleen bij --droog op een database zonder de tabel
            print("De tabel foto_beoordeling bestaat nog niet.")
            return 0
        raise
    verwerkt = 0
    for bestand in bestanden:
        try:
            foto_id = int(bestand.stem.removeprefix("uitslag-"))
        except ValueError:
            continue
        if foto_id not in wachtend:
            continue                            # al verwerkt (de map op de NAS is alleen-lezen voor deze taak)
        uitslag = json.loads(bestand.read_text(encoding="utf-8"))
        problemen = ph.controleer(uitslag)
        if problemen:
            print(f"FOUT in {bestand.name}: {'; '.join(problemen)}", file=sys.stderr)
            continue
        if args.droog:
            print(f"[droog] foto {foto_id}: {ph.kort(uitslag)}")
            continue
        foto = db.zet_foto_uitslag(foto_id, uitslag)
        if foto is None:
            continue
        if foto["teelt_ids"]:
            db.voeg_opmerking_toe(foto["teelt_ids"], foto["datum"], "Ziekte/plagen", ph.opmerking_tekst(uitslag),
                                  gebruiker=foto["gebruiker"])
        verwerkt += 1
        print(f"Foto {foto_id} beoordeeld: {ph.kort(uitslag)}"
              + (f" (opmerking bij vak {foto['vakken']})" if foto["teelt_ids"] else ""))
    if not args.droog:
        opgeruimd = db.ruim_fotos_op(FOTO_BEWAREN_DAGEN)
        if opgeruimd:
            print(f"{opgeruimd} oude foto('s) opgeruimd (uitslag blijft).")
    print(f"{verwerkt} foto('s) verwerkt.")
    return verwerkt


def main():
    args = lees_argumenten()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.actie == "klaarzetten":
        sys.exit(1 if klaarzetten(args) else 0)
    from dagrapport import kies_database
    kies_database(args.doel, alleen_lezen=args.actie == "ophalen" or args.droog)
    if args.actie == "ophalen":
        if not args.uit:
            print("FOUT: geef --uit MAP", file=sys.stderr)
            sys.exit(2)
        ophalen(args)
        return
    verwerk(args)


if __name__ == "__main__":
    main()

"""
Watervoorspelling voor vandaag per vak (tuin 3, ook tuin 1): advies "water", "twijfel" of "niet nodig" met een
korte reden, uit de teeltleeftijd, de giften en de straling sinds de vorige gift en de stralingsverwachting van
Open-Meteo (logic/watervoorspelling.py). Een hulpmiddel voor de teler, geen sturing. Alleen lezen.

Gebruik:
    python watervoorspelling.py                       # advies voor vandaag, als tekst
    python watervoorspelling.py --json                # als JSON-items voor de Takenlijst ({id, date, title, area, note})
    python watervoorspelling.py --tuin 1              # tuin 1
    python watervoorspelling.py --van 2026-10-20      # advies voor een andere dag (met wat er die ochtend bekend was)
    python watervoorspelling.py --terugtoets          # het advies terugtoetsen op de laatste 4 maanden
    python watervoorspelling.py --doel productie      # de online database (DATABASE_URL_PRODUCTIE)
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--van", type=date.fromisoformat, default=date.today(), help="dag van het advies (standaard vandaag)")
    parser.add_argument("--tuin", type=int, default=3, help="tuinnummer (standaard 3)")
    parser.add_argument("--json", action="store_true", help="als JSON (items voor de Takenlijst)")
    parser.add_argument("--alles", action="store_true", help="ook de reden bij de vakken met niet nodig")
    parser.add_argument("--terugtoets", action="store_true", help="terugtoetsen op de historie")
    parser.add_argument("--maanden", type=int, default=4, help="toetsperiode van de terugtoets (standaard 4 maanden)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    return parser.parse_args()


def _datum(waarde):
    if waarde is None or waarde == "":
        return None
    return waarde if isinstance(waarde, date) else date.fromisoformat(str(waarde)[:10])


def lees_data(database, tuin):
    """Gegevens uit de database, met datums als date."""
    data = database.get_watervoorspelling_data(tuin["id"])
    teelten = [{"id": int(t["id"]), "vak": int(t["vaknummer"]), "start": _datum(t["datum_teelt_start"]),
                "eind": _datum(t["datum_oogst"])} for t in data["teelten"]]
    water = [{"vaknummer": int(r["vaknummer"]), "datum": _datum(r["datum"]), "liter_per_m2": r["liter_per_m2"],
              "bron": r["bron"]} for r in data["water"]]
    straling = {_datum(d): s for d, s in data["straling"].items()}
    eerste_emmer = {i: _datum(d) for i, d in data["eerste_emmer"].items()}
    opmerkingen = {}
    for o in data["opmerkingen"]:
        opmerkingen.setdefault(int(o["teelt_id"]), []).append((_datum(o["datum"]), o["tekst"]))
    return teelten, water, straling, eerste_emmer, opmerkingen


def main():
    args = lees_argumenten()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.doel == "productie":
        import database as _db          # laadt .env; daarna het productie-adres als DATABASE_URL
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        _db.DATABASE_URL = doel_url

    import database
    from integrations import openmeteo
    from logic import watervoorspelling as wv

    tuinen = database.get_tuinen()
    tuin = next((t for t in tuinen if t["nummer"] == args.tuin), None)
    if tuin is None:
        print(f"FOUT: geen tuin {args.tuin}", file=sys.stderr)
        sys.exit(1)
    vandaag = args.van
    if args.terugtoets:
        gisteren = vandaag - timedelta(days=1)
        # Het model leert op beide tuinen; de toets is voor de gekozen tuin.
        alle = {t["nummer"]: voorbereid(database, wv, t, vandaag) for t in tuinen}
        d = alle[tuin["nummer"]]
        andere = [x for n, x in alle.items() if n != tuin["nummer"]]
        terugtoets(wv, openmeteo, tuin, d, andere, gisteren, args.maanden, args.json)
        return

    uit = bereken_advies(database, tuin, vandaag)
    lijst, d, om, ijk, melding = uit["lijst"], uit["data"], uit["openmeteo"], uit["ijk"], uit["melding"]
    verwachting, verwacht_morgen = uit["verwachting"], uit["verwacht_morgen"]

    if args.json:
        items = wv.feed_items(lijst, vandaag, tuin["naam"])
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return

    print(f"Watervoorspelling {tuin['naam']}, {wv.DAG[vandaag.weekday()]} {vandaag:%d-%m-%y} (advies, geen sturing)")
    regel = f"Straling verwacht vandaag ± {wv.getal(verwachting[vandaag])} J/cm²"
    if vandaag in om:
        regel += f" (Open-Meteo {om[vandaag]:.1f}".replace(".", ",") + f" MJ/m²; ijking {ijk[0]:.0f} + {ijk[1]:.0f} × MJ/m²)"
    if verwacht_morgen is not None:
        regel += f", morgen ± {wv.getal(verwacht_morgen)}"
    print(regel)
    if melding:
        print(f"Let op: {melding}")
    for soort in wv.ADVIEZEN:
        groep = [a for a in lijst if a["advies"] == soort]
        if not groep:
            continue
        print(f"\n{soort.upper()}: vak {wv.planting_namen(groep)}")
        if soort != "niet nodig" or args.alles:
            for regel in wv.groepen(groep):
                print(f"  {regel}")
                if args.alles:                          # met de reden per vak eronder
                    naam = regel.split(" · ")[0][len("vak "):]
                    for a in groep:
                        if a["planting"] == naam:
                            print(f"      {a['reden']}")
    if d["zonder"]:
        print(f"\nGeen advies voor vak {wv.vakken_tekst(d['zonder'])} (waterteelt).")


def bereken_advies(database, tuin, vandaag):
    """
    Het advies van `vandaag` voor één tuin (dict uit database.get_tuinen()), geleerd op beide tuinen. Geeft een
    dict met lijst (wv.adviezen: per vak advies, kans en reden), data (voorbereid), openmeteo, ijk, verwachting,
    verwacht_morgen en melding (als Open-Meteo niet bereikbaar was). Ook gebruikt door de notificaties in de app.
    """
    from integrations import openmeteo
    from logic import watervoorspelling as wv

    gisteren = vandaag - timedelta(days=1)
    tuinen = database.get_tuinen()
    alle = {t["nummer"]: voorbereid(database, wv, t, vandaag) for t in tuinen}
    d = alle[tuin["nummer"]]
    # Stralingsverwachting: Open-Meteo, omgerekend met de laatste weken (ook voor een dag zonder meting).
    melding = None
    try:
        if vandaag == date.today():
            om = openmeteo.verwachting(dagen_terug=wv.IJK_DAGEN + 10, dagen_vooruit=2)
        else:
            om = openmeteo.historie(vandaag - timedelta(days=wv.IJK_DAGEN + 10), vandaag + timedelta(days=1))
    except Exception as fout:                                   # geen netwerk: verder met de metingen
        om, melding = {}, f"geen stralingsverwachting (Open-Meteo: {type(fout).__name__})"
    straling = d["straling"]
    ijk = wv.ijk_straling(straling, om, vandaag)
    verwachting = {dag: wv.omrekenen(mj, ijk) for dag, mj in om.items() if dag >= vandaag or dag not in straling}
    if vandaag not in verwachting:                              # terugvallen op het gemiddelde van de laatste week
        week = [straling[dag] for dag in straling if dag >= vandaag - timedelta(days=7)]
        verwachting[vandaag] = sum(week) / len(week) if week else 0.0
    verwacht_morgen = verwachting.get(vandaag + timedelta(days=1))

    # Leren op de gemeten straling van de dag zelf (toetste even goed als op de verwachting van die ochtend).
    model = wv.train([r for x in alle.values() for r in
                      wv.kenmerken(x["teelten"], x["gift"], x["straling"], x["begin"], gisteren)])
    rijen = wv.kenmerken(d["teelten"], d["gift"], straling, vandaag, vandaag, verwachting, d["eerste_emmer"])
    lijst = wv.adviezen(model, rijen, verwacht_morgen, d["opmerkingen"], d["vandaag_gegeven"])

    return {"lijst": lijst, "data": d, "openmeteo": om, "ijk": ijk, "verwachting": verwachting,
            "verwacht_morgen": verwacht_morgen, "melding": melding}


def voorbereid(database, wv, tuin, vandaag):
    """Gegevens van één tuin zoals ze die ochtend bekend waren: giften en straling t/m gisteren, en apart wat er
    vandaag al gegeven is."""
    teelten, water, straling, eerste_emmer, opmerkingen = lees_data(database, tuin)
    zonder = wv.GEEN_ADVIES.get(tuin["nummer"], set())
    return {"teelten": [t for t in teelten if t["vak"] not in zonder], "zonder": zonder,
            "gift": wv.giften([r for r in water if r["datum"] < vandaag]),
            # Wat er vandaag al gegeven is (Priva, deel van de dag); voor een eerdere dag niet: dat wist die
            # ochtend nog niemand.
            "vandaag_gegeven": {r["vaknummer"]: r["liter_per_m2"] for r in water
                                if r["datum"] == vandaag == date.today() and r["liter_per_m2"]},
            "straling": {d: s for d, s in straling.items() if d < vandaag},
            "eerste_emmer": eerste_emmer, "opmerkingen": opmerkingen,
            "begin": min((r["datum"] for r in water if r["datum"] < vandaag), default=vandaag)}


def terugtoets(wv, openmeteo, tuin, d, andere, tot, maanden, als_json):
    """Leren op het oude deel (beide tuinen), toetsen op de laatste maanden van deze tuin, met de verwachting
    die er die ochtend was."""
    begin = min([d["begin"]] + [x["begin"] for x in andere])
    try:
        om = openmeteo.historie(begin - timedelta(days=wv.IJK_DAGEN), tot)
        bron = "opgeslagen verwachtingen van Open-Meteo, elke dag geijkt op de 4 weken ervoor"
    except Exception as fout:
        om, bron = {}, f"gemeten straling van de dag zelf (Open-Meteo niet bereikbaar: {type(fout).__name__})"

    def rijen(x):
        verwachting = wv.verwachting_reeks(x["straling"], om) if om else None
        return [r for r in wv.kenmerken(x["teelten"], x["gift"], x["straling"], x["begin"], tot, verwachting,
                                        x["eerste_emmer"]) if r["S_vandaag"] is not None]

    splits = tot - timedelta(days=round(maanden * 30.44))
    uit = wv.terugtoets(rijen(d), splits, [r for x in andere for r in rijen(x)])
    if als_json:
        print(json.dumps(uit, ensure_ascii=False, indent=1, default=str))
        return

    def pct(x):
        return "–" if x is None else f"{x * 100:.0f} %"

    print(f"Terugtoets watervoorspelling {tuin['naam']}: geleerd op beide tuinen t/m "
          f"{splits - timedelta(days=1):%d-%m-%y} ({wv.getal(uit['oud_dagen'])} vak-dagen van deze tuin), "
          f"getoetst op {uit['van']:%d-%m-%y} t/m {uit['tot']:%d-%m-%y}")
    print(f"Straling vandaag: {bron}.")
    print(f"Per planting per dag, zoals het advies (water gekregen = minstens de helft van de vakken): "
          f"{wv.getal(uit['dagen'])} planting-dagen, {wv.getal(uit['giften'])} met water ({pct(uit['giftkans'])}).\n")
    print(f"{'advies':<11}{'dagen':>7}{'met gift':>10}{'raak':>7}")
    for a, v in uit["advies"].items():
        print(f"{a:<11}{v['aantal']:>7}{v['gift']:>10}{pct(v['gift'] / v['aantal'] if v['aantal'] else None):>7}")
    print(f"\nVan de echte giften kreeg {pct(uit['gevonden_water'])} het advies water, "
          f"{pct(uit['gevonden_water_twijfel'])} water of twijfel; bij 'niet nodig' kwam er in "
          f"{pct(uit['niet_nodig_mis'])} van de dagen toch water.")
    print(f"'Water' was in {pct(uit['water_raak'])} van de gevallen terecht; blind gokken (evenveel 'water', "
          f"willekeurig verdeeld) zit op {pct(uit['blind_raak'])}.")
    print(f"Juist (water bij een gift, geen water zonder gift): {pct(uit['juist'])}, tegen {pct(uit['blind_juist'])} "
          f"voor 'nooit water'.")
    v = uit["per_vak"]
    print(f"Per vak gerekend: 'water' {pct(v['water_raak'])} terecht (blind {pct(v['blind_raak'])}), "
          f"{pct(v['gevonden_water_twijfel'])} van de giften water of twijfel ({wv.getal(v['dagen'])} vak-dagen).\n")
    print(f"{'fase':<11}{'dagen':>7}{'giften':>8}{'water raak':>12}{'gevonden':>10}{'+twijfel':>10}")
    for naam, v in uit["fasen"].items():
        print(f"{naam:<11}{v['dagen']:>7}{v['giften']:>8}{pct(v['water_raak']):>12}{pct(v['gevonden_water']):>10}"
              f"{pct(v['gevonden_water_twijfel']):>10}")


if __name__ == "__main__":
    main()

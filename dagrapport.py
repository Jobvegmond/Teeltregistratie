"""
Dagrapport (elke ochtend, over gisteren) en weekrapport (maandag, over de afgelopen week zondag t/m zaterdag) van
de hele teelt: wat er gebeurde, de controles (logic/dagrapport.py) en de duiding van Claude.

Zo loopt het:
1. De geplande taak "Dagrapport teelt" (Claude Code op de werklaptop, 06:30) maakt de bundel:
       py dagrapport.py bundel --doel productie --uit %TEMP%\\bundel-dag.json        (alleen lezen)
   leest de bundel en de bedrijfswiki, schrijft de duiding (JSON) en zet beide samen op de NAS:
       py dagrapport.py klaarzetten --bundel ... --duiding ...
   → \\\\192.168.0.197\\Appdata\\VEMteelt\\agro4all\\rapporten\\rapport-<sleutel>.json
2. De uurtaak op de NAS (priva_bestanden.py) draait `dagrapport.py` (= verstuur): elk klaargezet rapport dat nog
   niet verstuurd is gaat de deur uit (integrations/mail.py) en komt in de tabel rapport, zodat er op de pagina
   Rapporten feedback op gegeven kan worden. Is er om RAPPORT_UITERLIJK uur (config) nog geen rapport van
   vandaag, dan maakt de NAS de bundel zelf en mailt die zonder duiding.

Sleutel: "2026-11-03-dag" (de dag waarover het gaat) of "2026-w45" (de week, zondag t/m zaterdag).
Ontvangers: DAGRAPPORT_AAN, anders RAPPORT_AAN (omgeving), anders config.RAPPORT_AAN.

Gebruik:
    python dagrapport.py bundel [--soort week] [--datum 2026-11-04] [--doel productie] [--uit bundel.json]
    python dagrapport.py klaarzetten --bundel bundel.json --duiding duiding.json [--naar MAP]
    python dagrapport.py voorbeeld --rapport rapport.json --uit rapport.html
    python dagrapport.py [verstuur] [--droog] [--test job@tanacetum.nl] [--rapporten MAP]
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NL = ZoneInfo("Europe/Amsterdam")
NAS_MAP = r"\\192.168.0.197\Appdata\VEMteelt\agro4all\rapporten"     # vanaf de werklaptop
CONTAINER_MAP = "/agro4all/rapporten"                               # in de container op de NAS
# Hoe oud de laatste data van een bron hoogstens mag zijn (dagen) voor het rapport van vandaag.
VERWACHT = {"klimaat": ("Klimaat per dag", 1), "water": ("Watergift", 1), "gas": ("Gas", 2),
            "pats": ("PATS-tellingen", 4)}
VERWACHT_WARMTE = {"warmte": ("Warmte", 2)}
VERWACHT_AGRO4ALL = {"behandeling": ("Behandelingen (Agro4all)", 7)}


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("actie", nargs="?", default="verstuur", choices=("bundel", "klaarzetten", "voorbeeld",
                                                                         "verstuur"))
    parser.add_argument("--soort", choices=("dag", "week"), default="dag")
    parser.add_argument("--datum", type=date.fromisoformat, help="de dag van het rapport (standaard vandaag)")
    parser.add_argument("--uit", help="bundel: JSON-bestand; voorbeeld: HTML-bestand")
    parser.add_argument("--bundel", help="klaarzetten: de bundel")
    parser.add_argument("--duiding", help="klaarzetten: de duiding van Claude")
    parser.add_argument("--naar", default=NAS_MAP, help="klaarzetten: de map op de NAS")
    parser.add_argument("--rapport", help="voorbeeld: een klaargezet rapport (bundel + duiding)")
    parser.add_argument("--rapporten", default=os.environ.get("RAPPORT_MAP", CONTAINER_MAP),
                        help="verstuur: de map met klaargezette rapporten")
    parser.add_argument("--test", metavar="ADRES", help="verstuur: proefmail naar dit adres, niets onthouden")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="verstuur: alleen tonen, niets versturen")
    parser.add_argument("--map", help=argparse.SUPPRESS)        # van priva_bestanden.py, niet voor dit script
    return parser.parse_args()


def kies_database(doel, alleen_lezen):
    """Vóór het importeren van database: het adres en zo nodig een sessie die alleen mag lezen."""
    if alleen_lezen:
        os.environ["PGOPTIONS"] = "-c default_transaction_read_only=on"
    if doel == "productie":
        import database as _db          # laadt .env
        url = os.environ.get("DATABASE_URL_PRODUCTIE")
        env_productie = Path(__file__).with_name(".env.productie")       # op de werklaptop (zoals datacontrole.py)
        if not url and env_productie.exists():
            url = next((r.partition("=")[2].strip().strip('"').strip("'")
                        for r in env_productie.read_text(encoding="utf-8").splitlines()
                        if r.strip().startswith("DATABASE_URL=")), None)
        if not url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        _db.DATABASE_URL = url


def periode(soort, vandaag):
    """(sleutel, van, tot, weeknummer of None)."""
    from logic.weken import week_begin, week_sleutel
    if soort == "dag":
        gisteren = vandaag - timedelta(days=1)
        return f"{gisteren}-dag", gisteren, gisteren, None
    zondag = week_begin(vandaag) - timedelta(days=7)
    jaar, week = week_sleutel(zondag)
    return f"{jaar}-w{week:02d}", zondag, zondag + timedelta(days=6), week


def _datum(waarde):
    from logic import vakstatus as vs
    return vs.als_datum(waarde)


def _veilig(functie, standaard):
    """Rapporten en feedback: de tabellen bestaan pas na de eerste run op de NAS."""
    try:
        return functie()
    except Exception as e:
        print(f"(overgeslagen: {e.__class__.__name__})", file=sys.stderr)
        return standaard


def maak_bundel(soort, vandaag):
    """De bundel als dict: periode, per tuin de feiten en kengetallen, de signalen, recente feedback en conclusies."""
    import database
    from config import (DIF_MIN, EC_BEREIK, FEEDBACK_DAGEN, HERHALING_DAGEN, LICHTLIJN_BASIS, LICHTLIJN_FACTOR,
                        PH_BEREIK, STOOK_MAX)
    from logic import dagrapport as dr
    from logic import pats, prognoselog, teeltprognose as tp, tuin_overzicht as tuin_ov, tuinvergelijking as tuinvgl
    from logic import vakstatus as vs, werkplanning as wp
    from logic.afdelingen import sorteer_afdelingen
    from utils.format import fmt_kort

    sleutel, van, tot, week = periode(soort, vandaag)
    lengte = (tot - van).days + 1
    v_van, v_tot = van - timedelta(days=lengte), tot - timedelta(days=lengte)

    def plandatum(start):
        return database.bereken_verwachte_oogstdatum(start)[1]

    g = tuinvgl.Gegevens(database.get_vergelijking_data())
    data = database.get_vakstatus_data()
    historie, weken = database.get_teelthistorie_data()
    model = prognoselog.bouw_model(data, historie, weken, plandatum)
    stook, afwijking = prognoselog.stand_lopende_teelten(
        data["teelten"], tp.klimaat_per_afdeling(data["klimaat"]), model, vandaag, plandatum)
    opmerkingen = database.get_alle_opmerkingen()
    alle_teelten = data["teelten"].to_dict("records")

    tuinen, signalen = [], []
    for tuin in sorted(database.get_tuinen(), key=lambda t: t["nummer"]):
        tid, nr = tuin["id"], tuin["nummer"]
        eigen = [t for t in alle_teelten if t["tuin_id"] == tid]

        # Teelten: per vak de jongste lopende, plus wat onlangs is afgerond.
        lopend, recent = {}, []
        for t in eigen:
            start, oogst = _datum(t["datum_teelt_start"]), _datum(t["datum_oogst"])
            if not start or start > vandaag:
                continue
            u = stook.get(int(t["id"])) or {}
            r = {"vak": int(t["vaknummer"]), "afdeling": vs._getal(t["afdeling"]), "teelt_id": int(t["id"]),
                 "code": t.get("code"), "start": start, "florgib": _datum(t.get("datum_half")),
                 "florgib_verwacht": u.get("florgib_verwacht"), "prognose": u.get("prognose"),
                 "plan": plandatum(start), "emmers": vs._getal(t.get("emmers")) or 0,
                 "laatste_emmers": _datum(t.get("laatste_emmers")), "oogst": oogst,
                 "lengte_eind": vs._getal(t.get("lengte_eind")), "gewicht": vs._getal(t.get("oogstgewicht")),
                 "stek": vs._getal(t.get("bakjes")) is not None or bool(t.get("beoordeling")),
                 "planten": vs._getal(t.get("aantal_planten")), "c": u.get("c")}
            if oogst:
                recent.append(r)
            elif r["vak"] not in lopend or start > lopend[r["vak"]]["start"]:
                lopend[r["vak"]] = r
        teelten = list(lopend.values()) + [r for r in recent if (vandaag - r["oogst"]).days <= dr.EINDMETING_DAGEN]

        planning = [(int(v), _datum(s)) for _id, v, s, *_ in database.get_planning(tid) if _datum(s)]
        bezetting = {}
        for t in eigen:
            start = _datum(t["datum_teelt_start"])
            if start:
                bezetting.setdefault(int(t["vaknummer"]), []).append((start, _datum(t["datum_oogst"])))
        for vak, start in planning:         # een concept wordt nog geplant: loopt door
            bezetting.setdefault(vak, []).append((start, None))

        behandelingen = [{"vak": int(b["vaknummer"]), "datum": _datum(b["datum"]), "middel": b["middel"],
                          "type": b["type"], "doel": b.get("doel")}
                         for b in database.get_behandelingen(tid, vandaag - timedelta(days=28), vandaag)]
        # Werkplanning (CXDS, Florgib, planten): alleen voor een tuin die in Agro4all registreert.
        taken = []
        if behandelingen:
            zondag = vandaag - timedelta(days=(vandaag.weekday() + 1) % 7)
            concepten = [(v, s) for v, s in planning if s <= vandaag + timedelta(days=3)]
            geplant = [(t["vak"], t["start"]) for t in lopend.values() if zondag <= t["start"] <= vandaag]
            taken = wp.taken(list(lopend.values()), wp.laatste_cxds(
                [{"vaknummer": b["vak"], "datum": b["datum"], "middel": b["middel"]} for b in behandelingen]),
                concepten, vandaag, 3, geplant)

        # Stookadvies per afdeling (zoals Overzicht): c gewogen naar het aantal planten.
        advies = {}
        for afd in {t["afdeling"] for t in lopend.values() if t["afdeling"] is not None}:
            rijen = [{"vak": t["vak"], "c": t["c"], "stelen": t["planten"] or 1.0} for t in lopend.values()
                     if t["afdeling"] == afd and t["c"] is not None]
            c, _ = tp.afdelingsadvies(rijen)
            advies[int(afd)] = {"c": c, "nu": afwijking.get((tid, int(afd)))}

        uur, _meteo = database.get_klimaat_uur(tid, van, tot)
        uur_toen, _ = database.get_klimaat_uur(tid, v_van, v_tot)
        nu = tuin_ov.tabelwaarden(g, uur, tid, van, tot)
        if soort == "dag":
            # De nacht van gisteren is 's ochtends nog niet rond: de DIF over gisteren en eergisteren.
            twee = tuin_ov.tabelwaarden(g, uur.iloc[0:0], tid, van - timedelta(days=1), tot)["waarden"]
            for k, w in nu["waarden"].items():
                w.pop("dif", None)
                if (twee.get(k) or {}).get("dif") is not None:
                    w["dif"] = twee[k]["dif"]
        toen = tuin_ov.tabelwaarden(g, uur_toen, tid, v_van, v_tot)
        volgorde = [tuin_ov.kolom(a) for a in sorteer_afdelingen(tuin_ov.afdelingen(g, tid), nr)]
        kolommen = volgorde + [tuin_ov.HELE_TUIN]

        water = g.water[(g.water["tuin_id"] == tid) & (g.water["datum"] >= str(van)) & (g.water["datum"] <= str(tot))]
        giften = [{"vak": int(w.vaknummer), "afdeling": g.vak_afdeling.get((tid, int(w.vaknummer))),
                   "datum": _datum(w.datum), "liter": float(w.liter_per_m2)}
                  for w in water.itertuples() if (w.liter_per_m2 or 0) > 0]

        tellingen = database.get_pats_tellingen(tid, min(v_van, vandaag - timedelta(days=17)), vandaag)
        dagtotalen = pats.dagtotalen(tellingen)
        pats_feit = []
        for insect in dict.fromkeys(r["insect"] for r in dagtotalen):
            pats_feit.append({"insect": insect,
                              "totaal": sum(r["totaal"] for r in dagtotalen if r["insect"] == insect
                                            and van <= r["datum"] <= tot),
                              "vorige": sum(r["totaal"] for r in dagtotalen if r["insect"] == insect
                                            and v_van <= r["datum"] <= v_tot)})

        verwacht = {**VERWACHT, **(VERWACHT_WARMTE if nr == 1 else {}), **(VERWACHT_AGRO4ALL if behandelingen else {})}
        if not pats.GETOOND or not database.pats_tuinen_met_tellingen() & {tid}:
            verwacht.pop("pats", None)

        signalen += dr.data_actueel(nr, database.get_laatste_data(tid), verwacht, vandaag)
        signalen += dr.registraties(nr, teelten, [(v, s) for v, s in planning if s < vandaag], vandaag)
        signalen += dr.bespuitingen(nr, list(lopend.values()), behandelingen, taken, bezetting, van, tot, vandaag)
        signalen += dr.klimaat(nr, {k: nu["waarden"].get(k, {}) for k in volgorde}, advies)
        signalen += dr.water(nr, {k: nu["waarden"].get(k, {}) for k in volgorde}, giften, bezetting)
        signalen += dr.plagen(nr, dagtotalen, vandaag)

        gebeurd = tuin_ov.gebeurtenissen(g, opmerkingen, tid, van, tot)
        per_middel = {}
        for b in behandelingen:
            if van <= b["datum"] <= tot:
                per_middel.setdefault((b["datum"], b["middel"] or "?"), []).append(b["vak"])
        tuinen.append({
            "nummer": nr, "naam": tuin["naam"], "samenvatting": tuin_ov.samenvatting(gebeurd),
            "gebeurd": [{"datum": r["datum"], "vak": r["vak"], "soort": r["soort"], "tekst": r["tekst"]}
                        for r in gebeurd],
            "behandelingen": [{"datum": d, "middel": m, "vakken": ", ".join(str(v) for v in sorted(set(vakken)))}
                              for (d, m), vakken in sorted(per_middel.items())],
            "pats": pats_feit, "kolommen": kolommen,
            "kengetallen": {k: nu["waarden"].get(k, {}) for k in kolommen},
            "kengetallen_vorige": {k: toen["waarden"].get(k, {}) for k in kolommen},
            "stookadvies": {f"Afd. {a}": v for a, v in sorted(advies.items())},
            "lopende_vakken": len(lopend),
            "werkplanning": [{"datum": t["datum"], "titel": t["titel"], "toelichting": t["toelichting"]}
                             for t in taken],
        })

    # Herhaling: hoe vaak elk signaal in de dagrapporten van de laatste HERHALING_DAGEN stond.
    rapporten = _veilig(lambda: database.get_rapporten(90), [])
    eerder = {}
    for r in rapporten:
        if r["soort"] == "dag" and r["van"] < str(van) and r["van"] >= str(van - timedelta(days=HERHALING_DAGEN)):
            for s in {s["sleutel"] for s in json.loads(r["bundel"]).get("signalen", [])}:
                eerder[s] = eerder.get(s, 0) + 1
    # Feedback van de laatste FEEDBACK_DAGEN, met de conclusie en haar signalen erbij.
    conclusies = {}
    for r in rapporten:
        for c in (json.loads(r["duiding"]) if r["duiding"] else {}).get("conclusies", []):
            conclusies[(r["sleutel"], c["id"])] = c
    feedback = []
    for f in _veilig(lambda: database.get_rapport_feedback(vandaag - timedelta(days=FEEDBACK_DAGEN)), []):
        c = conclusies.get((f["rapport"], f["conclusie"]), {})
        feedback.append({"rapport": f["rapport"], "conclusie": f["conclusie"], "titel": c.get("titel"),
                         "conclusie_tekst": c.get("tekst"), "sleutels": c.get("signalen", []),
                         "oordeel": f["oordeel"], "tekst": f["tekst"], "datum": str(f["tijdstip"])[:10]})
    signalen = dr.sorteer(dr.demp(dr.herhaling(signalen, eerder), feedback))
    vorige_conclusies = [{"rapport": r["sleutel"], **{k: c.get(k) for k in ("id", "titel", "soort", "tuin")}}
                         for r in rapporten[:7] if r["duiding"]
                         for c in json.loads(r["duiding"]).get("conclusies", [])]

    return {
        "versie": 1, "sleutel": sleutel, "soort": soort, "week": week, "van": van, "tot": tot,
        "vergelijk": {"van": v_van, "tot": v_tot}, "gemaakt": datetime.now(NL).isoformat(timespec="seconds"),
        "doelen": {"dif_min": DIF_MIN, "stook_max": STOOK_MAX, "ec": EC_BEREIK, "ph": PH_BEREIK,
                   "lichtlijn": f"etmaal = {fmt_kort(LICHTLIJN_BASIS, 1)} + {fmt_kort(LICHTLIJN_FACTOR, 4)} × lichtsom"},
        "tuinen": tuinen, "signalen": signalen, "feedback": feedback, "vorige_conclusies": vorige_conclusies,
    }


def als_json(waarde):
    return json.dumps(waarde, ensure_ascii=False, indent=1, default=str)


def controleer_duiding(duiding, bundel):
    """Lijst met fouten in de duiding (leeg = goed)."""
    fouten = []
    if not isinstance(duiding.get("samenvatting"), str) or not duiding["samenvatting"].strip():
        fouten.append("samenvatting ontbreekt")
    conclusies = duiding.get("conclusies")
    if not isinstance(conclusies, list):
        return fouten + ["conclusies moet een lijst zijn"]
    sleutels = {s["sleutel"] for s in bundel["signalen"]}
    ids = set()
    for i, c in enumerate(conclusies, 1):
        for veld in ("id", "titel", "tekst", "soort"):
            if not isinstance(c.get(veld), str) or not c[veld].strip():
                fouten.append(f"conclusie {i}: {veld} ontbreekt")
        if c.get("id") in ids:
            fouten.append(f"conclusie {i}: id {c.get('id')} komt dubbel voor")
        ids.add(c.get("id"))
        if c.get("soort") not in ("opvallend", "fout", "advies"):
            fouten.append(f"conclusie {i}: soort moet opvallend, fout of advies zijn")
        if c.get("tuin") not in (None, 1, 3):
            fouten.append(f"conclusie {i}: tuin moet 1, 3 of null zijn")
        onbekend = [s for s in c.get("signalen") or [] if s not in sleutels]
        if onbekend:
            fouten.append(f"conclusie {i}: onbekende signalen {onbekend}")
    return fouten


def verstuur_rapport(database, mail, bundel, duiding, aan, args, stempel):
    from config import APP_URL
    from logic import dagrapport as dr
    onderwerp, html_tekst = dr.bericht(bundel, duiding, APP_URL)
    if args.droog:
        print(f"[{stempel}] DROOG: zou mailen '{onderwerp}' ({'met' if duiding else 'zonder'} duiding, "
              f"{len(bundel['signalen'])} signalen) aan {', '.join(aan)}")
        return
    sleutel = bundel["sleutel"]
    mail.verstuur_en_log("dagrapport", sleutel + (" (proef)" if args.test else ""), onderwerp, html_tekst, aan,
                         log=database.log_mail)
    if not args.test:
        database.bewaar_rapport(sleutel, bundel["soort"], bundel["van"], bundel["tot"], als_json(bundel),
                                als_json(duiding) if duiding else None, ", ".join(aan))
    print(f"[{stempel}] {'Proefmail' if args.test else 'Gemaild'}: '{onderwerp}' "
          f"({'met' if duiding else 'zonder'} duiding) aan {', '.join(aan)}")


def verstuur(args):
    import database
    from config import RAPPORT_AAN, RAPPORT_UITERLIJK
    from integrations import mail

    nu = datetime.now(NL)
    stempel = f"{nu:%d-%m-%y %H:%M}"
    vandaag = args.datum or nu.date()
    if not args.droog:
        database.init_db()          # tabellen rapport en rapport_feedback (nieuw in 2.26.0)
    verstuurd = set() if args.test else {r["sleutel"] for r in _veilig(lambda: database.get_rapporten(200), [])}
    aan = mail.ontvangers(args.test or mail.instelling("DAGRAPPORT_AAN") or mail.instelling("RAPPORT_AAN", RAPPORT_AAN))
    if not mail.verzendweg() and not args.droog:
        print(f"[{stempel}] Het versturen is nog niet ingesteld (GRAPH_… of SMTP_… in .env.taak); niets gedaan.")
        return
    fout = False
    gedaan = set()
    map_ = Path(args.rapporten)
    for bestand in sorted(map_.glob("rapport-*.json")) if map_.is_dir() else []:
        try:
            rapport = json.loads(bestand.read_text(encoding="utf-8"))
            bundel, duiding = rapport["bundel"], rapport.get("duiding")
        except (ValueError, KeyError) as e:
            print(f"[{stempel}] FOUT: {bestand.name} is geen geldig rapport ({e})", file=sys.stderr)
            fout = True
            continue
        if bundel["sleutel"] in verstuurd or date.fromisoformat(bundel["tot"]) < vandaag - timedelta(days=8):
            continue
        try:
            verstuur_rapport(database, mail, bundel, duiding, aan, args, stempel)
            gedaan.add(bundel["sleutel"])
        except mail.MailFout as e:
            print(f"[{stempel}] FOUT bij mailen {bundel['sleutel']}: {e}", file=sys.stderr)
            fout = True
    # Terugval: na RAPPORT_UITERLIJK uur zonder duiding.
    if nu.hour >= RAPPORT_UITERLIJK or args.test:
        for soort in ("dag", "week") if vandaag.weekday() == 0 else ("dag",):
            sleutel = periode(soort, vandaag)[0]
            if sleutel in verstuurd or sleutel in gedaan:
                continue
            try:
                verstuur_rapport(database, mail, json.loads(als_json(maak_bundel(soort, vandaag))), None, aan, args,
                                 stempel)
            except mail.MailFout as e:
                print(f"[{stempel}] FOUT bij mailen {sleutel}: {e}", file=sys.stderr)
                fout = True
    if not gedaan and nu.hour < RAPPORT_UITERLIJK:
        print(f"[{stempel}] Geen nieuw dagrapport klaargezet.")
    if fout:
        sys.exit(1)


def main():
    args = lees_argumenten()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.actie == "klaarzetten":
        bundel = json.loads(Path(args.bundel).read_text(encoding="utf-8"))
        duiding = json.loads(Path(args.duiding).read_text(encoding="utf-8"))
        fouten = controleer_duiding(duiding, bundel)
        if fouten:
            print("FOUT in de duiding:\n- " + "\n- ".join(fouten), file=sys.stderr)
            sys.exit(1)
        naar = Path(args.naar)
        if not naar.parent.is_dir():
            print(f"FOUT: {naar.parent} is niet bereikbaar (VPN uit?).", file=sys.stderr)
            sys.exit(1)
        naar.mkdir(exist_ok=True)
        doel = naar / f"rapport-{bundel['sleutel']}.json"
        doel.write_text(als_json({"bundel": bundel, "duiding": duiding}), encoding="utf-8", newline="\n")
        print(f"Klaargezet: {doel} ({len(duiding['conclusies'])} conclusies, {len(bundel['signalen'])} signalen)")
        return
    if args.actie == "voorbeeld":
        from config import APP_URL
        from logic import dagrapport as dr
        rapport = json.loads(Path(args.rapport).read_text(encoding="utf-8"))
        _onderwerp, html_tekst = dr.bericht(rapport["bundel"], rapport.get("duiding"), APP_URL)
        Path(args.uit).write_text(html_tekst, encoding="utf-8")
        print(f"Voorbeeld in {args.uit}")
        return
    kies_database(args.doel, alleen_lezen=args.actie == "bundel" or args.droog)
    if args.actie == "bundel":
        tekst = als_json(maak_bundel(args.soort, args.datum or datetime.now(NL).date()))
        if args.uit:
            Path(args.uit).write_text(tekst, encoding="utf-8")
            print(f"Bundel in {args.uit}")
        else:
            print(tekst)
        return
    verstuur(args)


if __name__ == "__main__":
    main()

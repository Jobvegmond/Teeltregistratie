"""
Mail "Teelt afgerond; plantweek …" zodra van een teelt (alle vakken uit één plantweek, beide tuinen) het laatste
vak geoogst is, met per tuin en per vak de kengetallen (logic/teelt_rapport.py). Draait elk uur via
priva_bestanden.py; een verstuurd rapport staat in de tabel teelt_rapport en gaat niet nog een keer.

Alleen teelten die op of na RAPPORT_VANAF (config) zijn afgerond: oudere teelten worden niet alsnog gemaild.

Mail via SMTP, instellingen in de omgeving (.env.taak):
    SMTP_SERVER, SMTP_POORT (587, STARTTLS), SMTP_GEBRUIKER, SMTP_WACHTWOORD,
    RAPPORT_VAN (standaard SMTP_GEBRUIKER), RAPPORT_AAN (standaard config.RAPPORT_AAN; meer adressen met komma's)
Zonder SMTP-instellingen: een melding, niets verstuurd en niets als verstuurd gemarkeerd.

Gebruik:
    python teelt_rapport.py                              # nieuwe afgeronde teelten mailen
    python teelt_rapport.py --droog                      # alleen tonen welke teelten gemaild zouden worden
    python teelt_rapport.py --plantweek 2026-34 --voorbeeld rapport.html   # één rapport als HTML-bestand
    python teelt_rapport.py --plantweek 2026-34 --opnieuw                  # één rapport (opnieuw) mailen
"""
import argparse
import os
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path


def lees_argumenten():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plantweek", help="alleen deze plantweek, bijv. 2026-34")
    parser.add_argument("--voorbeeld", help="het rapport als HTML-bestand schrijven in plaats van mailen")
    parser.add_argument("--opnieuw", action="store_true", help="ook als het al verstuurd is (met --plantweek)")
    parser.add_argument("--doel", choices=("app", "productie"), default="app",
                        help="app = DATABASE_URL (standaard), productie = DATABASE_URL_PRODUCTIE")
    parser.add_argument("--droog", action="store_true", help="alleen tonen, niets versturen")
    parser.add_argument("--map", help=argparse.SUPPRESS)        # van priva_bestanden.py, niet voor dit script
    return parser.parse_args()


def vakken_en_tuinen(database):
    """Alle gestarte vakken met hun kengetallen (zoals de pagina Teelt), en [(naam, tuin_id)]."""
    from logic import teeltvergelijking as teeltvgl
    from logic import tuinvergelijking as tuinvgl
    tuinen = sorted(database.get_tuinen(), key=lambda t: t["nummer"])
    g = tuinvgl.Gegevens(database.get_vergelijking_data())
    dagdata = teeltvgl.Dagdata(g.klimaat, g.water, {t["id"]: database.warmte_per_bezette_m2(t["id"]) for t in tuinen})
    vandaag = date.today()
    gisteren = vandaag - timedelta(days=1)
    vakken = []
    for k in database.get_teeltvergelijking_data():
        t = teeltvgl.teelt(k, g.vak_m2.get((k["tuin_id"], int(k["vaknummer"]))),
                           florgib_historie=k.get("florgib_historie"))
        if t["start"] <= vandaag:
            vakken.append(teeltvgl.met_dagdata(t, dagdata, gisteren))
    return vakken, [(t["naam"], t["id"]) for t in tuinen], {t["id"]: t["nummer"] for t in tuinen}


def mailen(onderwerp, tekst, html_tekst, aan):
    bericht = EmailMessage()
    bericht["Subject"] = onderwerp
    bericht["From"] = os.environ.get("RAPPORT_VAN") or os.environ["SMTP_GEBRUIKER"]
    bericht["To"] = ", ".join(aan)
    bericht.set_content(tekst)
    bericht.add_alternative(html_tekst, subtype="html")
    with smtplib.SMTP(os.environ["SMTP_SERVER"], int(os.environ.get("SMTP_POORT", "587")), timeout=60) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_GEBRUIKER"], os.environ["SMTP_WACHTWOORD"])
        smtp.send_message(bericht)


def main():
    args = lees_argumenten()
    if args.doel == "productie":
        doel_url = os.environ.get("DATABASE_URL_PRODUCTIE")
        if not doel_url:
            print("FOUT: DATABASE_URL_PRODUCTIE is niet gezet.", file=sys.stderr)
            sys.exit(1)
        os.environ["DATABASE_URL"] = doel_url

    import database
    from config import APP_URL, RAPPORT_AAN, RAPPORT_VANAF
    from logic import teelt_rapport as tr
    from logic import teeltvergelijking as teeltvgl
    from logic.afdelingen import sorteer_afdelingen

    stempel = f"{datetime.now(timezone.utc):%d-%m-%y %H:%M} UTC"
    vakken, tuinen, tuinnummer = vakken_en_tuinen(database)
    afgerond = tr.afgeronde_plantweken(vakken)
    if args.plantweek:
        jaar, week = (int(x) for x in args.plantweek.split("-"))
        if (jaar, week) not in afgerond:
            print(f"[{stempel}] Plantweek {week} ({jaar}) is (nog) niet afgerond of bestaat niet.", file=sys.stderr)
            sys.exit(1)
        kandidaten = [(jaar, week)]
    else:
        kandidaten = sorted(w for w, (laatste, _) in afgerond.items() if laatste >= RAPPORT_VANAF)

    if not args.droog and not args.voorbeeld:
        database.init_db()          # tabel teelt_rapport (nieuw in 2.16.0)
    verstuurd = set() if args.droog or args.voorbeeld else database.get_teelt_rapporten()
    nieuw = [w for w in kandidaten if args.opnieuw or f"{w[0]}-{w[1]:02d}" not in verstuurd]
    if not nieuw:
        print(f"[{stempel}] Geen nieuwe afgeronde teelten.")
        return

    def volgorde(tuin_id, afdeling):
        nummer = tuinnummer.get(tuin_id)
        lijst = list(sorteer_afdelingen({afdeling}, nummer)) if afdeling is not None else []
        return lijst.index(afdeling) if afdeling in lijst else 99

    aan = [a.strip() for a in os.environ.get("RAPPORT_AAN", RAPPORT_AAN).split(",") if a.strip()]
    smtp_klaar = all(os.environ.get(k) for k in ("SMTP_SERVER", "SMTP_GEBRUIKER", "SMTP_WACHTWOORD"))
    fout = False
    for week in nieuw:
        laatste, groep = afgerond[week]
        vorig = teeltvgl.vorig_jaar(week)
        vorig_jaar = [t for t in vakken if teeltvgl.plantweek(t["start"]) == vorig]
        onderwerp, tekst, html_tekst = tr.bericht(week, groep, vorig_jaar, tuinen, laatste, APP_URL, volgorde)
        sleutel = f"{week[0]}-{week[1]:02d}"
        if args.voorbeeld:
            Path(args.voorbeeld).write_text(html_tekst, encoding="utf-8")
            print(f"[{stempel}] Voorbeeld van '{onderwerp}' in {args.voorbeeld}")
            return
        if args.droog:
            print(f"[{stempel}] DROOG: zou mailen '{onderwerp}' ({len(groep)} vakken, laatste oogst "
                  f"{laatste:%d-%m-%y}) aan {', '.join(aan)}")
            continue
        if not smtp_klaar:
            print(f"[{stempel}] '{onderwerp}' klaar om te mailen, maar SMTP is nog niet ingesteld "
                  "(SMTP_SERVER, SMTP_GEBRUIKER, SMTP_WACHTWOORD in .env.taak).")
            continue
        try:
            mailen(onderwerp, tekst, html_tekst, aan)
        except Exception as e:          # één mislukte mail stopt de rest niet; volgende run opnieuw
            print(f"[{stempel}] FOUT bij mailen '{onderwerp}': {e}", file=sys.stderr)
            fout = True
            continue
        database.markeer_teelt_rapport(sleutel, laatste, ", ".join(aan))
        print(f"[{stempel}] Gemaild: '{onderwerp}' ({len(groep)} vakken) aan {', '.join(aan)}")
    if fout:
        sys.exit(1)


if __name__ == "__main__":
    main()

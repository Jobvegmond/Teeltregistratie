"""
Rekenwerk voor de statusmonitor (statusmonitor.py): de logboeken van de NAS-taken lezen en per onderdeel een
kleur bepalen. Alleen lezen; er wordt nergens iets geschreven. Tests in tests/test_status.py.

Kleuren:
- groen: de laatste geplande keer is gelukt (of de data is vers genoeg);
- oranje: één keer gemist of wat aan de late kant;
- rood: een fout, of al langer niets;
- grijs: niet te meten (bijv. de NAS is niet bereikbaar);
- info: geen gezondheidssignaal, alleen het laatste moment (bijv. de laatste invoer van een gebruiker).

Tijden zijn naïeve datetimes in Nederlandse tijd, tenzij er UTC bij staat.

De logboeken op de NAS (`logs/` in de projectmap) hebben allemaal dezelfde vorm. De taakregel in DSM schrijft
een kop in Nederlandse tijd, het script daarna zijn eigen regels (vaak met UTC):

    --- 29-10-26 06:00 start                       (bouw.log: "--- 29-10-26 00:00 bouwen (aanvraag)")
    --- 29-10-26 05:00 UTC priva_pulsmeters.py --tuin 3
    [29-10-26 05:00 UTC] ...
    FOUT in: priva_klimaat.py --tuin 1
    --- klaar met code 0                           (niet in elk logboek)
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

GROEN, ORANJE, ROOD, GRIJS, INFO = "groen", "oranje", "rood", "grijs", "info"
ERNST = {ROOD: 0, ORANJE: 1, GRIJS: 2, GROEN: 3, INFO: 4}   # volgorde in de lijst: wat aandacht vraagt bovenaan

NL = ZoneInfo("Europe/Amsterdam")

# Hoe laat elke taak hoort te draaien (Nederlandse tijd): (uren, alleen op werkdagen).
SCHEMA = {
    "uurtaak": (tuple(range(1, 24)), False),     # DSM: elk uur 01–23 u
    "api": ((6, 12, 18), False),                # DSM: priva_ophalen.py
    "prognose": ((8,), False),                  # DSM: prognose_loggen.py
    "kopie": ((3,), False),                     # DSM: productie naar NAS kopiëren
    "backup": ((2,), False),                    # DSM: nas_backup_database.sh
    "bouwen": ((0,), False),                    # DSM: app-image bijwerken (vangnet; op aanvraag tussendoor)
    "agro4all": ((7, 12, 17), True),            # Claude-taak op de werklaptop, alleen als die aan staat
    "dagrapport": ((6,), False),                # Claude-taak "Dagrapport teelt" op de werklaptop (06:30, klaar ± 06:40)
    "dagrapport_mail": ((7,), False),           # de uurtaak mailt het klaargezette rapport (zonder duiding om 9 u)
}
# Zoveel ruimte krijgt een taak na het geplande moment voordat hij als gemist telt (looptijd, jitter van Claude).
SPELING = {"uurtaak": timedelta(minutes=10), "agro4all": timedelta(minutes=30),
           "dagrapport": timedelta(minutes=90), "dagrapport_mail": timedelta(minutes=120)}
STANDAARD_SPELING = timedelta(minutes=20)

_KOP = re.compile(r"^--- (\d\d-\d\d-\d\d \d\d:\d\d) (.*)$")
_CODE = re.compile(r"^--- klaar met code (\d+)")


def geplande_momenten(nu, taak, aantal=2):
    """De laatste `aantal` geplande momenten van een taak (uit SCHEMA) op of vóór `nu`, nieuwste eerst."""
    uren, werkdagen = SCHEMA[taak]
    momenten = []
    dag = nu.replace(minute=0, second=0, microsecond=0)
    for _ in range(24 * 14):
        if dag <= nu and dag.hour in uren and not (werkdagen and dag.weekday() >= 5):
            momenten.append(dag)
            if len(momenten) == aantal:
                break
        dag -= timedelta(hours=1)
    return momenten


def kleur_volgens_schema(laatst_ok, nu, taak):
    """
    Groen als de taak na het laatste geplande moment gelukt is, oranje als alleen de keer daarvoor gelukt is
    (één keer gemist), anders rood. Een taak krijgt SPELING na het geplande moment voordat hij als gemist telt.
    """
    if laatst_ok is None:
        return ROOD
    speling = SPELING.get(taak, STANDAARD_SPELING)
    laatste, vorige = geplande_momenten(nu - speling, taak)
    # Een taak die net vóór het hele uur start (zoals de Claude-taak met jitter) telt ook mee.
    if laatst_ok >= laatste - timedelta(minutes=15):
        return GROEN
    if laatst_ok >= vorige - timedelta(minutes=15):
        return ORANJE
    return ROOD


def kleur_volgens_leeftijd(moment, nu, groen_tot, oranje_tot):
    """Groen als `moment` hooguit `groen_tot` oud is, oranje tot `oranje_tot`, daarna rood; None = rood."""
    if moment is None:
        return ROOD
    leeftijd = nu - moment
    if leeftijd <= groen_tot:
        return GROEN
    if leeftijd <= oranje_tot:
        return ORANJE
    return ROOD


def _tijd(tekst):
    return datetime.strptime(tekst, "%d-%m-%y %H:%M")


def utc_naar_nl(moment):
    """Een tijd als naïeve Nederlandse tijd: een naïeve tijd geldt als UTC, een tijd met zone wordt omgerekend."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(NL).replace(tzinfo=None)


def statusbestand(tekst):
    """
    sync-status.json, het statusbestand dat de klimaat-pc van tuin 1 zelf op de NAS zet, als
    {moment, ok, melding, pc}, of None als het geen geldig bestand is:
      {"pc": "KLIMAAT", "syncTijdstip": "2026-10-29T07:08:13+01:00", "syncStatus": "ok", "pollerStatus": "ok",
       "stop": false}
    `moment` is Nederlandse tijd; een tijd zonder zone geldt als Nederlandse tijd.
    """
    import json
    try:
        gegevens = json.loads(tekst.lstrip("﻿"))    # PowerShell 5 schrijft UTF-8 met BOM
    except ValueError:
        return None
    if not isinstance(gegevens, dict):
        return None
    try:
        moment = datetime.fromisoformat(gegevens.get("syncTijdstip"))
        moment = utc_naar_nl(moment) if moment.tzinfo else moment
    except (TypeError, ValueError):
        moment = None
    statussen = {"sync": gegevens.get("syncStatus"), "poller": gegevens.get("pollerStatus")}
    ok = all(str(s).lower() == "ok" for s in statussen.values()) and not gegevens.get("stop")
    melding = ", ".join(f"{naam} {s}" for naam, s in statussen.items()) + (", gestopt" if gegevens.get("stop") else "")
    return {"moment": moment, "ok": ok, "melding": melding, "pc": gegevens.get("pc")}


def lees_runs(tekst):
    """
    De runs uit een logboek, oudste eerst. Een run begint bij een kopregel zonder "UTC" (de kop van de DSM-taak)
    en loopt tot de volgende. Per run een dict met:
    - start: de tijd uit de kop (Nederlandse tijd);
    - soort: de rest van de kop ("start", "bouwen (aanvraag)", ...);
    - stappen: [(naam, start in UTC, [regels])] voor de kopregels met "UTC" (priva_bestanden.py);
    - regels: alle regels van de run;
    - code: het getal uit "--- klaar met code N", of None als die (nog) ontbreekt;
    - fout_in: de scripts uit "FOUT in: ...";
    - fouten: regels met FOUT of Traceback.
    Een stuk vóór de eerste kop (een afgekapt begin) wordt overgeslagen.
    """
    runs = []
    for regel in tekst.splitlines():
        regel = regel.rstrip("\r")
        kop = _KOP.match(regel)
        if kop and not kop.group(2).startswith("UTC "):
            runs.append({"start": _tijd(kop.group(1)), "soort": kop.group(2).strip(), "stappen": [],
                         "regels": [], "code": None, "fout_in": [], "fouten": []})
            continue
        if not runs:
            continue
        run = runs[-1]
        run["regels"].append(regel)
        if kop:
            run["stappen"].append((kop.group(2)[4:].strip(), _tijd(kop.group(1)), []))
            continue
        code = _CODE.match(regel)
        if code:
            run["code"] = int(code.group(1))
            continue
        if regel.startswith("FOUT in:"):
            # De samenvatting van priva_bestanden.py hoort bij de run, niet bij het laatste script.
            run["fout_in"] = [s.strip() for s in regel[len("FOUT in:"):].split(",") if s.strip()]
            run["fouten"].append(regel.strip())
            continue
        if "FOUT" in regel or "Traceback" in regel:
            run["fouten"].append(regel.strip())
        if run["stappen"]:
            run["stappen"][-1][2].append(regel)
    return runs


def stap(run, script):
    """
    De status van één script in een run van de uurtaak: (kleur, tekst). Rood als het in "FOUT in" staat of een
    fout meldt, grijs als het niet in de run zit (nog niet aan de beurt, of afgekapt), anders groen.
    `script` is de naam met eventuele argumenten, bijv. "priva_klimaat.py --tuin 1".
    """
    if run is None:
        return GRIJS, "geen run gevonden"
    for naam, _, regels in run["stappen"]:
        if naam == script:
            if script in run["fout_in"] or any("FOUT" in r or "Traceback" in r for r in regels):
                melding = next((r.strip() for r in regels if "FOUT" in r or "Error" in r), "fout, zie het logboek")
                return ROOD, melding
            laatste = next((r.strip() for r in reversed(regels) if r.strip()), "")
            return GROEN, laatste
    if script in run["fout_in"]:
        return ROOD, "staat in FOUT in"
    return GRIJS, "niet in de laatste run"


def laatste_afgeronde(runs):
    """De laatste run met een "klaar met code"-regel, of None."""
    return next((r for r in reversed(runs) if r["code"] is not None), None)


def laatste_gelukte(runs):
    """De laatste run die met code 0 klaar is (of zonder code en zonder fouten), of None."""
    for run in reversed(runs):
        if run["code"] == 0 or (run["code"] is None and not run["fouten"] and run["regels"]):
            return run
    return None


def fouten_laatste_uren(runs, nu, uren=24):
    """
    Hoeveel runs van de laatste `uren` met een fout eindigden: {"totaal", "met_fout", "recent"}, met
    recent = [(start, scripts)] van de runs met een fout, oudste eerst. `scripts` komt uit "FOUT in:" (de uurtaak),
    anders staat de eerste foutregel erin. Een run telt mee als hij klaar is of regels heeft; een logboek zonder
    "klaar met code" (priva.log) telt een run met een foutregel als fout.
    """
    sinds = nu - timedelta(hours=uren)
    recente = [r for r in runs if r["start"] >= sinds and (r["code"] is not None or r["regels"])]
    fout = [r for r in recente if r["fouten"] or r["code"] not in (None, 0)]
    return {"totaal": len(recente), "met_fout": len(fout),
            "recent": [(r["start"], r["fout_in"] or r["fouten"][:1]) for r in fout]}


def hint(melding):
    """Een uitleg bij een bekende foutmelding, of None."""
    if "deadlock" in (melding or "").lower():
        return ("Deadlock in de database: de taak startte waarschijnlijk op hetzelfde moment als de uurtaak; "
                "beide passen bij het opstarten de database aan en blokkeren elkaar. De volgende run lukt meestal weer.")
    return None


def leeftijd_tekst(moment, nu):
    """Kort en leesbaar: "06:01" vandaag, "gisteren 18:00", anders "27-10 18:00"; "nooit" bij None."""
    if moment is None:
        return "nooit"
    if moment.date() == nu.date():
        return moment.strftime("%H:%M")
    if moment.date() == (nu - timedelta(days=1)).date():
        return "gisteren " + moment.strftime("%H:%M")
    return moment.strftime("%d-%m %H:%M")


def ergste(kleuren):
    """De kleur die de meeste aandacht vraagt (rood > oranje > grijs > groen > info)."""
    kleuren = list(kleuren)
    return min(kleuren, key=ERNST.get) if kleuren else GRIJS

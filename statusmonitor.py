"""
Statusmonitor: een pagina op de eigen laptop die laat zien of elk onderdeel van de teeltregistratie draait,
met het laatste moment waarop het werkte. Werkt ook als de app op Render plat ligt.

Alles wordt alleen gelezen:
- via de VPN de NAS (SMB): de logboeken in `Appdata\\VEMteelt\\logs`, de map agro4all, de share Priva (wanneer de
  poller van elke tuin voor het laatst schreef), de back-ups en de test-app en database op de NAS;
- Supabase (productie, uit .env.productie) in een read-only sessie: hoe vers de data is;
- de app op Render: of hij antwoordt.

De pagina draait alleen op deze laptop (127.0.0.1), van buitenaf is hij niet bereikbaar. Hij ververst elke minuut.

Het dagrapport loopt zo: de Claude-taak "Dagrapport teelt" op deze laptop (06:30) zet het rapport klaar in
`agro4all\\rapporten` op de NAS, en de uurtaak mailt het (zonder duiding om 9 uur). De monitor kijkt naar dat
bestand, naar de uurtaak en naar de tabellen rapport en mail_log in Supabase.
Rekenwerk (logboeken lezen, kleuren) in logic/status.py; de pagina zelf in status/pagina.html.

Gebruik (of dubbelklik op "Status teeltregistratie.cmd", ook als kopie op het bureaublad):
    py statusmonitor.py                 # start op http://127.0.0.1:8600 en opent de browser
    py statusmonitor.py --poort 8601
    py statusmonitor.py --geen-browser
    py statusmonitor.py --eenmalig      # één controle als tekst, zonder pagina
"""
import argparse
import json
import os
import re
import threading
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Wachttijd
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import APP_URL, PRIVA_BESTANDEN
from logic import priva_bron
from logic import status as st

HIER = Path(__file__).resolve().parent
PAGINA = HIER / "status" / "pagina.html"

NAS = r"\\192.168.0.197"
PROJECT = Path(NAS + r"\Appdata\VEMteelt")
LOGS = PROJECT / "logs"
AGRO4ALL = PROJECT / "agro4all"
PRIVA = Path(NAS + r"\Priva")
BACKUP = Path(NAS + r"\backup\postgres")
RAPPORTEN = AGRO4ALL / "rapporten"      # waar de Claude-taak "Dagrapport teelt" zijn rapport klaarzet
NAS_CONFIG = PROJECT / "config.py"      # de versie van de app op de NAS staat hierin
NAS_APP = "http://192.168.0.197:8501/_stcore/health"
RENDER = APP_URL.rstrip("/") + "/_stcore/health"

CACHE_SECONDEN = 30
WACHTTIJD = 45          # seconden per groep controles; daarna grijs

# De stappen van de uurtaak (priva_bestanden.py) per regel in de flowchart.
UUR_STAPPEN = {
    "uur.pulsmeters": [f"priva_pulsmeters.py --tuin {t}" for t in sorted(PRIVA_BESTANDEN, reverse=True)],
    "uur.watergift": [f"priva_watergift.py --tuin {t}" for t in sorted(PRIVA_BESTANDEN, reverse=True)],
    "uur.klimaat": [f"priva_klimaat.py --tuin {t}" for t in sorted(PRIVA_BESTANDEN, reverse=True)],
    "uur.agro4all": ["agro4all_import.py"],
    "uur.logboek": ["klimaatregistratie_import.py"],
    "uur.pats": ["pats_import.py"],
    "uur.rapport": ["teelt_rapport.py"],
    "uur.dagrapport": ["dagrapport.py"],
}
UUR_NAMEN = {"uur.pulsmeters": "warmte en gas", "uur.watergift": "watergift per vak",
             "uur.klimaat": "klimaat per uur en dag", "uur.agro4all": "behandelingen",
             "uur.logboek": "teeltlogboek", "uur.pats": "vangplaten", "uur.rapport": "mail Teelt afgerond",
             "uur.dagrapport": "dagrapport mailen"}

GROEPEN = ("Werklaptop", "Bronnen", "NAS", "Cloud", "Gebruikers")


def onderdeel(id_, naam, groep, kleur, nu, laatst=None, kort=None, details=()):
    """Eén onderdeel voor de pagina. `kort` staat in het kader; zonder `kort` het laatste moment."""
    return {"id": id_, "naam": naam, "groep": groep, "kleur": kleur,
            "laatst": laatst.isoformat(timespec="minutes") if laatst else None,
            "laatst_tekst": st.leeftijd_tekst(laatst, nu) if laatst else "",
            "kort": kort if kort is not None else st.leeftijd_tekst(laatst, nu),
            "details": [d for d in details if d]}


# --- Lezen ------------------------------------------------------------------------------------------------------

def gewijzigd(pad):
    """Het tijdstip van de laatste wijziging van een bestand, of None als het er niet is."""
    try:
        return datetime.fromtimestamp(os.stat(pad).st_mtime)
    except OSError:
        return None


def staart(pad, grootte=300_000):
    """Het laatste stuk van een (groot) logboek als tekst; '' als het er niet is."""
    try:
        with open(pad, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - grootte))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def hints(regels):
    """De uitleg bij bekende foutmeldingen in `regels`, zonder dubbele."""
    return list(dict.fromkeys(h for h in (st.hint(r) for r in regels) if h))


def fouten_regel(runs, nu, uren):
    """Eén regel over de runs met een fout in de laatste `uren`, of None als die er niet waren."""
    samen = st.fouten_laatste_uren(runs, nu, uren)
    if not samen["met_fout"]:
        return None
    wanneer = ", ".join(f"{start:%d-%m %H:%M}" for start, _ in samen["recent"][-4:])
    periode = f"{uren // 24} dagen" if uren >= 48 else f"{uren} uur"
    return f"Laatste {periode}: {samen['met_fout']} van {samen['totaal']} runs met een fout ({wanneer})"


def nas_versie():
    """(versie, moment van uitrol) van de app op de NAS uit zijn config.py, of None."""
    try:
        match = re.search(r'^APP_VERSIE\s*=\s*"([^"]+)"', NAS_CONFIG.read_text(encoding="utf-8"), re.M)
    except OSError:
        return None
    return (match.group(1), gewijzigd(NAS_CONFIG)) if match else None


def lees_statusbestand(pad):
    """Een statusbestand van een pc (logic.status.statusbestand), of None als het er niet is of niet klopt."""
    try:
        return st.statusbestand(Path(pad).read_text(encoding="utf-8"))
    except OSError:
        return None


def antwoordt(url, wachttijd):
    """(True, tekst) als de URL met 200 antwoordt, anders (False, de fout)."""
    try:
        with urllib.request.urlopen(url, timeout=wachttijd) as antwoord:
            return antwoord.status == 200, f"antwoordt ({antwoord.status})"
    except Exception as fout:           # time-out, DNS, 502 van Render, ...
        return False, f"antwoordt niet: {fout}"


def database_url(bestand):
    """DATABASE_URL uit een .env-bestand naast dit script, of None."""
    try:
        with open(HIER / bestand, encoding="utf-8") as f:
            for regel in f:
                match = re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\n]+)"?', regel)
                if match:
                    return match.group(1).strip()
    except OSError:
        pass
    return None


def vraag(url, vragen):
    """Voert de SELECT-vragen {naam: sql} uit in een read-only sessie; {naam: rijen}."""
    import psycopg2
    verbinding = psycopg2.connect(url, connect_timeout=10)
    try:
        verbinding.set_session(readonly=True, autocommit=True)
        cursor = verbinding.cursor()
        cursor.execute("SET statement_timeout = 15000")
        uitkomst = {}
        for naam, sql in vragen.items():
            cursor.execute(sql)
            uitkomst[naam] = cursor.fetchall()
        return uitkomst
    finally:
        verbinding.close()


# --- Controles ---------------------------------------------------------------------------------------------------

def controleer_nas(nu):
    """Alles wat via de VPN op de NAS te zien is."""
    if not os.path.isdir(LOGS):
        reden = "NAS niet bereikbaar: staat de VPN aan?"
        ids = [("laptop.agro4all", "Claude-taak Agro4all", "Werklaptop"),
               ("laptop.dagrapport", "Claude-taak Dagrapport teelt", "Werklaptop"),
               ("laptop.logboek", "Teeltlogboek → JSON", "Werklaptop"),
               ("bron.priva3", "Priva-pc tuin 3", "Bronnen"), ("bron.priva1", "Priva-pc tuin 1", "Bronnen"),
               ("bron.api", "Priva Horti API", "Bronnen"), ("nas.share", "Share Priva", "NAS"),
               ("nas.agro", "Map agro4all", "NAS"), ("nas.uurtaak", "Uurtaak", "NAS"),
               ("nas.api", "API-taak", "NAS"), ("nas.prognose", "Prognose loggen", "NAS"),
               ("nas.kopie", "Kopie productie naar NAS", "NAS"),
               ("nas.db", "vemteelt-db", "NAS"), ("nas.backup", "Back-up op HDD", "NAS"),
               ("nas.bouwen", "Image bouwen", "NAS"), ("cloud.mail", "Mail via Graph", "Cloud")]
        uit = [onderdeel(i, n, g, st.GRIJS, nu, kort="niet bereikbaar", details=[reden]) for i, n, g in ids]
        uit += [onderdeel(i, UUR_NAMEN[i], "NAS", st.GRIJS, nu, kort="") for i in UUR_STAPPEN]
        return uit, False

    uit = []

    # Uurtaak (priva_bestanden.py) en zijn stappen.
    runs = st.lees_runs(staart(LOGS / "priva-bestanden.log"))
    gelukt = next((r for r in reversed(runs) if r["code"] == 0), None)
    afgerond = st.laatste_afgeronde(runs)
    laatste = runs[-1] if runs else None
    kleur = st.kleur_volgens_schema(gelukt["start"] if gelukt else None, nu, "uurtaak")
    details = [f"Laatst gelukt: {st.leeftijd_tekst(gelukt['start'], nu) if gelukt else 'nooit'} (elk uur 01–23 u)"]
    kort = None
    if afgerond and afgerond["code"] != 0:
        kleur = st.ROOD
        kort = f"fout {afgerond['start']:%H:%M}"
        details.append(f"Run van {st.leeftijd_tekst(afgerond['start'], nu)} klaar met code {afgerond['code']}")
        details += afgerond["fouten"][-5:] + hints(afgerond["fouten"])
    samen = st.fouten_laatste_uren(runs, nu)
    if samen["met_fout"]:
        details.append(fouten_regel(runs, nu, 24))
        details += [f"{st.leeftijd_tekst(start, nu)}: {', '.join(scripts)[:160]}" for start, scripts in samen["recent"][-4:]]
    if laatste and laatste["code"] is None and nu - laatste["start"] < timedelta(minutes=15):
        kort = f"bezig sinds {laatste['start']:%H:%M}"
        details.append(f"Run van {laatste['start']:%H:%M} loopt nog")
    uit.append(onderdeel("nas.uurtaak", "Uurtaak", "NAS", kleur, nu, gelukt["start"] if gelukt else None,
                         kort, details))

    stappen = {}
    for id_, scripts in UUR_STAPPEN.items():
        uitslagen = [(s, *st.stap(afgerond, s)) for s in scripts]
        stappen[id_] = st.ergste(k for _, k, _ in uitslagen)
        uit.append(onderdeel(id_, UUR_NAMEN[id_], "NAS", stappen[id_], nu,
                             afgerond["start"] if afgerond else None,
                             details=[f"{s}: {t}" for s, _, t in uitslagen]))

    # Share Priva: bereikbaar en de Priva-stappen van de uurtaak gelukt.
    share = os.path.isdir(PRIVA)
    kleur = st.ergste([stappen["uur.pulsmeters"], stappen["uur.watergift"], stappen["uur.klimaat"],
                       st.GROEN if share else st.ROOD])
    uit.append(onderdeel("nas.share", "Share Priva", "NAS", kleur, nu, afgerond["start"] if afgerond else None,
                         details=["Share bereikbaar" if share else "Share Priva niet bereikbaar",
                                  "Warmte, gas, watergift en klimaat uit de laatste uurtaak"]))

    # De poller op elke Priva-pc: wanneer schreef hij laatste.json? De klimaat-pc van tuin 1 kopieert zijn
    # bestanden elke ± 20 minuten en meldt dat in sync-status.json (naast de map live); daar geldt die melding.
    for tuin in sorted(PRIVA_BESTANDEN, reverse=True):
        live, _ = priva_bron.mappen(PRIVA, tuin)
        moment = gewijzigd(live / "laatste.json")
        groen_tot = timedelta(minutes=20)
        details = [f"laatste.json van {PRIVA_BESTANDEN[tuin]['pcu']}: {st.leeftijd_tekst(moment, nu)}"]
        sync = lees_statusbestand(live.parent / "sync-status.json")
        if sync:
            moment, groen_tot = sync["moment"] or moment, timedelta(minutes=35)
            details.append(f"Kopie van de klimaat-pc: {sync['melding']}")
        kleur = st.kleur_volgens_leeftijd(moment, nu, groen_tot, timedelta(hours=1))
        if sync and not sync["ok"]:
            kleur = st.ROOD
        details.append(f"Groen tot {int(groen_tot.total_seconds() // 60)} minuten oud, oranje tot een uur")
        regelaar = priva_bron.controleer_regelaar(live, tuin) if moment else None
        if regelaar:
            kleur = st.ROOD
            details.append(regelaar)
        uit.append(onderdeel(f"bron.priva{tuin}", f"Priva-pc tuin {tuin}", "Bronnen", kleur, nu, moment,
                             details=details))

    # De Claude-taak "Dagrapport teelt" (laptop, 06:30): zijn rapport staat in agro4all\rapporten.
    try:
        nieuwste = max(RAPPORTEN.glob("rapport-*-dag.json"), default=None)    # de datum staat in de naam
    except OSError:
        nieuwste = None
    klaar = gewijzigd(nieuwste) if nieuwste else None
    uit.append(onderdeel("laptop.dagrapport", "Claude-taak Dagrapport teelt", "Werklaptop",
                         st.kleur_volgens_schema(klaar, nu, "dagrapport"), nu, klaar,
                         details=[f"Nieuwste rapport op de NAS: {nieuwste.name if nieuwste else 'geen'} "
                                  f"({st.leeftijd_tekst(klaar, nu)})",
                                  "Elke ochtend 06:30, alleen als de laptop aan staat. Komt er niets, dan mailt de "
                                  "NAS om 9 uur de cijfers zonder duiding"]))

    # Map agro4all en de Claude-taak die de export schrijft.
    export = gewijzigd(AGRO4ALL / "registraties.json")
    uit.append(onderdeel("laptop.agro4all", "Claude-taak Agro4all", "Werklaptop",
                         st.kleur_volgens_schema(export, nu, "agro4all"), nu, export,
                         details=[f"registraties.json bijgewerkt: {st.leeftijd_tekst(export, nu)}",
                                  "Werkdagen 7, 12 en 17 u, alleen als de laptop aan staat"]))
    logboeken = [gewijzigd(p) for p in AGRO4ALL.glob("klimaatregistratie-tuin*.json")]
    logboek = max((m for m in logboeken if m), default=None)
    uit.append(onderdeel("laptop.logboek", "Teeltlogboek → JSON", "Werklaptop", st.INFO, nu, logboek,
                         details=[f"Laatst omgezet: {st.leeftijd_tekst(logboek, nu)} (met de hand)"]))
    kleur = st.ergste([stappen["uur.agro4all"], stappen["uur.logboek"], st.GROEN if export else st.ROOD])
    uit.append(onderdeel("nas.agro", "Map agro4all", "NAS", kleur, nu, export,
                         details=["Ingelezen door de uurtaak: behandelingen, teeltlogboek en klaargezette rapporten",
                                  f"Map rapporten: {nieuwste.name if nieuwste else 'geen'} "
                                  f"({st.leeftijd_tekst(klaar, nu)})"]))

    # API-taak (priva_ophalen.py) en de Priva-API zelf.
    runs = st.lees_runs(staart(LOGS / "priva.log"))
    gelukt = st.laatste_gelukte(runs)
    laatste = runs[-1] if runs else None
    fout = bool(laatste and laatste["fouten"])
    kleur = st.ROOD if fout else st.kleur_volgens_schema(gelukt["start"] if gelukt else None, nu, "api")
    regels = [r.strip() for r in (laatste["regels"] if laatste else []) if r.strip()]
    uit.append(onderdeel("nas.api", "API-taak", "NAS", kleur, nu, gelukt["start"] if gelukt else None,
                         f"fout {laatste['start']:%H:%M}" if fout else None,
                         ["Om 6, 12 en 18 u", fouten_regel(runs, nu, 168)] + regels[-4:]
                         + hints(laatste["fouten"] if fout else [])))
    # Een taak die al bij het opstarten omvalt heeft de Priva-API niet eens aangeroepen.
    niet_bereikt = fout and all("bij het opstarten" in f for f in laatste["fouten"])
    uit.append(onderdeel("bron.api", "Priva Horti API", "Bronnen",
                         st.GRIJS if niet_bereikt else (st.ROOD if fout else (st.GROEN if laatste else st.GRIJS)),
                         nu, laatste["start"] if laatste else None, "niet bereikt" if niet_bereikt else None,
                         details=(["De API-taak viel om vóór hij de API aanriep"] if niet_bereikt
                                  else laatste["fouten"][-3:] if fout else ["Laatste ophaalronde zonder fouten"])))

    # Prognose loggen, kopie naar de NAS, image bouwen.
    for id_, naam, logboek_, taak, uitleg in (
            ("nas.prognose", "Prognose loggen", "prognose.log", "prognose", "Dagelijks om 8 u"),
            ("nas.kopie", "Kopie productie naar NAS", "sync.log", "kopie", "Dagelijks om 3 u"),
            ("nas.bouwen", "Image bouwen", "bouw.log", "bouwen", "00:00 en op aanvraag")):
        runs = st.lees_runs(staart(LOGS / logboek_))
        gelukt = st.laatste_gelukte(runs)
        laatste = runs[-1] if runs else None
        fout = laatste is not None and (laatste["fouten"] or (laatste["code"] not in (None, 0)))
        kleur = st.ROOD if fout else st.kleur_volgens_schema(gelukt["start"] if gelukt else None, nu, taak)
        regels = [r.strip() for r in (laatste["regels"] if laatste else []) if r.strip() and not r.startswith("#")]
        uit.append(onderdeel(id_, naam, "NAS", kleur, nu, gelukt["start"] if gelukt else None,
                             f"fout {laatste['start']:%H:%M}" if fout else None,
                             [uitleg, fouten_regel(runs, nu, 336)] + [r[:200] for r in regels[-3:]]
                             + hints(laatste["fouten"] if fout else [])))

    # Back-up: het nieuwste bestand in backup/postgres.
    try:
        bestanden = [(gewijzigd(p), p) for p in BACKUP.glob("vem_teelt_*.sql.gz")]
        moment, pad = max(((m, p) for m, p in bestanden if m), default=(None, None))
    except OSError:
        moment, pad = None, None
    grootte = pad.stat().st_size if pad else 0
    kleur = st.kleur_volgens_schema(moment, nu, "backup") if grootte >= 10_000 else st.ROOD
    uit.append(onderdeel("nas.backup", "Back-up op HDD", "NAS", kleur, nu, moment,
                         details=[f"{pad.name}: {grootte // 1024} kB" if pad else "Geen back-up gevonden",
                                  "Elke nacht om 2 u, 30 dagen bewaard"]))

    # Mail: alle rapporten gaan via Microsoft Graph (klimaat@tanacetum.nl) en worden door de uurtaak verstuurd.
    # Een "LET OP"-regel in de laatste run waarschuwt dat het Graph-geheim bijna verloopt.
    waarschuwingen = [r.strip() for r in (afgerond["regels"] if afgerond else []) if "LET OP" in r]
    kleur = st.ergste([stappen["uur.rapport"], stappen["uur.dagrapport"]] + ([st.ORANJE] if waarschuwingen else []))
    uit.append(onderdeel("cloud.mail", "Mail via Graph", "Cloud", kleur, nu,
                         afgerond["start"] if afgerond else None,
                         details=["Verstuurd door de uurtaak: Teelt afgerond naar info@, dagrapport naar job@ en "
                                  "weekrapport (maandag) naar info@",
                                  f"Teelt afgerond (laatste controle): {st.stap(afgerond, 'teelt_rapport.py')[1]}",
                                  f"Dagrapport (laatste controle): {st.stap(afgerond, 'dagrapport.py')[1]}"]
                         + waarschuwingen))
    return uit, True


def controleer_nas_database(nu, kopie):
    """De database op de NAS: bereikbaar, en de kopie van vannacht (uit sync.log) gelukt."""
    url = database_url(".env")
    if not url:
        return [onderdeel("nas.db", "vemteelt-db", "NAS", st.GRIJS, nu, kort="geen .env",
                          details=["Geen DATABASE_URL in .env"])]
    try:
        vraag(url, {"nu": "SELECT 1"})
        verbinding = (st.GROEN, "Database antwoordt")
    except Exception as fout:
        verbinding = (st.ROOD, f"Database antwoordt niet: {fout}".strip())
    kleur = st.ergste([verbinding[0], kopie["kleur"] if kopie else st.GRIJS])
    moment = datetime.fromisoformat(kopie["laatst"]) if kopie and kopie["laatst"] else None
    return [onderdeel("nas.db", "vemteelt-db", "NAS", kleur, nu, moment,
                      details=[verbinding[1], f"Kopie van productie: {kopie['kort'] if kopie else 'onbekend'}"])]


def controleer_supabase(nu):
    """Supabase (productie, read-only): bereikbaar, en hoe vers de data is."""
    url = database_url(".env.productie")
    if not url:
        return [onderdeel("cloud.supabase", "Supabase", "Cloud", st.GRIJS, nu, kort="geen .env.productie")], {}
    try:
        rijen = vraag(url, {
            "klimaat": "SELECT t.nummer, max(k.tijdstip) FROM klimaat_uur k JOIN tuinen t ON t.id = k.tuin_id "
                       "GROUP BY t.nummer",
            "pats": "SELECT t.nummer, max(p.datum) FROM pats_telling p JOIN tuinen t ON t.id = p.tuin_id "
                    "GROUP BY t.nummer",
            "agro4all": "SELECT max(datum) FROM behandeling WHERE bron = 'agro4all'",
            # Invoer van mensen, niet van de taken (die loggen als priva-...). Registreren raakt vooral oogst,
            # teelten, stek en opmerkingen; de rest (planning, weekdoelen, CSV-import) gebeurt meestal op kantoor.
            # Een teelt "aangemaakt" is een bevestigde planting (kantoor), "gewijzigd" komt uit Registreren.
            "invoer": "SELECT entiteit IN ('oogstregistratie', 'opmerking') OR entiteit LIKE 'stek%%' "
                      "OR (entiteit = 'teelt' AND actie = 'gewijzigd'), "
                      "max(tijdstip), count(*) FILTER (WHERE tijdstip > now() - interval '1 day') "
                      "FROM wijzigingenlog WHERE gebruiker IS NOT NULL AND gebruiker NOT LIKE 'priva-%%' "
                      "GROUP BY 1",
            # Elke mailpoging staat in mail_log; het nieuwste per soort, en de mislukte van de laatste 7 dagen.
            "mail": "SELECT DISTINCT ON (soort) soort, sleutel, status, tijdstip, weg, left(coalesce(melding, ''), 120) "
                    "FROM mail_log ORDER BY soort, tijdstip DESC",
            "mail_fouten": "SELECT soort, count(*) FROM mail_log WHERE status = 'fout' "
                           "AND tijdstip > now() - interval '7 days' GROUP BY soort",
            # De verstuurde dag- en weekrapporten, en of er een duiding van Claude bij zat.
            "rapport": "SELECT sleutel, soort, verstuurd_op, duiding IS NOT NULL FROM rapport "
                       "WHERE verstuurd_op IS NOT NULL ORDER BY verstuurd_op DESC LIMIT 8",
            "feedback": "SELECT count(*), max(tijdstip) FROM rapport_feedback",
            "water": "SELECT max(datum) FROM watergift_dag WHERE bron = 'priva-vandaag'",
        })
    except Exception as fout:
        return [onderdeel("cloud.supabase", "Supabase", "Cloud", st.ROOD, nu, kort="niet bereikbaar",
                          details=[str(fout).strip()])], {}
    klimaat = {nummer: datetime.strptime(t, "%Y-%m-%d %H:%M") + timedelta(hours=1)
               for nummer, t in rijen["klimaat"] if t}
    details = ["Bereikbaar (read-only)"]
    details += [f"Klimaat per uur tuin {n} t/m {st.leeftijd_tekst(m, nu)}" for n, m in sorted(klimaat.items())]
    if rijen["water"][0][0]:
        details.append(f"Watergift van vandaag t/m {rijen['water'][0][0]}")
    return [onderdeel("cloud.supabase", "Supabase", "Cloud", st.GROEN, nu, nu, kort="bereikbaar",
                      details=details)], {"rijen": rijen, "klimaat": klimaat}


def controleer_http(nu):
    """De app op Render en de test-app op de NAS: antwoorden ze?"""
    uit = []
    for id_, naam, groep, url, wachttijd in (("cloud.render", "Render", "Cloud", RENDER, 30),
                                              ("nas.app", "vemteelt-app", "NAS", NAS_APP, 8)):
        ok, tekst = antwoordt(url, wachttijd)
        uit.append(onderdeel(id_, naam, groep, st.GROEN if ok else st.ROOD, nu, nu if ok else None,
                             kort="draait" if ok else "plat", details=[url, tekst]))
    return uit


def _mail_uit_supabase(o, rijen, nu):
    """Zet in het kader Mail via Graph wat mail_log en rapport zeggen: laatste mail, fouten, dagrapport met duiding."""
    namen = {"dagrapport": "Dag- en weekrapport", "teelt_rapport": "Teelt afgerond"}
    laatste = []
    for soort, sleutel, status, tijdstip, weg, melding in rijen["mail"]:
        tijdstip = st.utc_naar_nl(tijdstip)
        laatste.append(tijdstip)
        o["details"].append(f"{namen.get(soort, soort)}: laatste mail {sleutel}, {status}, "
                            f"{st.leeftijd_tekst(tijdstip, nu)} via {weg}" + (f" ({melding})" if melding else ""))
        if status == "fout":
            o["kleur"] = st.ROOD
    if rijen["mail_fouten"]:
        o["details"].append("Mislukte pogingen in de laatste 7 dagen: "
                            + ", ".join(f"{namen.get(s, s)} {n}×" for s, n in rijen["mail_fouten"]))

    dag = next(((s, v, d) for s, soort, v, d in rijen["rapport"] if soort == "dag"), None)
    week = next(((s, v, d) for s, soort, v, d in rijen["rapport"] if soort == "week"), None)
    for naam, rapport in (("dagrapport", dag), ("weekrapport", week)):
        if rapport:
            sleutel, verstuurd, duiding = rapport
            o["details"].append(f"Laatste {naam} {sleutel}: verstuurd {st.leeftijd_tekst(st.utc_naar_nl(verstuurd), nu)}, "
                                f"{'met' if duiding else 'zonder'} duiding van Claude")
    if dag and o["kleur"] != st.GRIJS:
        o["kleur"] = st.ergste([o["kleur"], st.kleur_volgens_schema(st.utc_naar_nl(dag[1]), nu, "dagrapport_mail")])
    if laatste and o["kleur"] == st.GROEN:
        o["kort"] = f"laatste mail {st.leeftijd_tekst(max(laatste), nu)}"


def verfijn_met_data(onderdelen, data, nu):
    """Zet de versheid van de data uit Supabase bij de bronnen en de gebruikers."""
    per_id = {o["id"]: o for o in onderdelen}
    rijen = data.get("rijen")

    for tuin, moment in data.get("klimaat", {}).items():
        o = per_id.get(f"bron.priva{tuin}")
        if o and o["kleur"] != st.GRIJS:
            kleur = st.kleur_volgens_leeftijd(moment, nu, timedelta(hours=2), timedelta(hours=4))
            o["kleur"] = st.ergste([o["kleur"], kleur])
            o["details"].append(f"Klimaat per uur in productie t/m {st.leeftijd_tekst(moment, nu)}")

    if rijen:
        pats = {n: datetime.strptime(d, "%Y-%m-%d") for n, d in rijen["pats"] if d}
        stap = per_id.get("uur.pats", {}).get("kleur", st.GRIJS)
        vers = [st.kleur_volgens_leeftijd(d, nu, timedelta(days=2), timedelta(days=4)) for d in pats.values()]
        per_id["bron.pats"] = onderdeel("bron.pats", "PATS", "Bronnen", st.ergste([stap] + vers), nu,
                                        max(pats.values(), default=None),
                                        kort=", ".join(f"t{n} {d:%d-%m}" for n, d in sorted(pats.items())),
                                        details=[f"Tellingen tuin {n} t/m {d:%d-%m-%y}" for n, d in sorted(pats.items())]
                                        + [f"Ophalen in de uurtaak: {stap}"])

        agro = rijen["agro4all"][0][0]
        moment = datetime.strptime(agro, "%Y-%m-%d") if agro else None
        per_id["bron.agro4all"] = onderdeel(
            "bron.agro4all", "Agro4all", "Bronnen",
            st.kleur_volgens_leeftijd(moment, nu, timedelta(days=4), timedelta(days=8)), nu, moment,
            kort=f"t/m {moment:%d-%m}" if moment else "geen",
            details=[f"Laatste behandeling in productie: {agro or 'geen'}", "Tuin 1 registreert nog niet in Agro4all"])

        invoer = {registreren: (st.utc_naar_nl(moment), aantal) for registreren, moment, aantal in rijen["invoer"]}
        for id_, naam, registreren, wat in (
                ("gebruiker.telefoon", "Telefoon in de kas", True, "oogst, teelten, stek en opmerkingen"),
                ("gebruiker.kantoor", "Browser op kantoor", False, "planning, weekdoelen en import")):
            moment, aantal = invoer.get(registreren, (None, 0))
            per_id[id_] = onderdeel(id_, naam, "Gebruikers", st.INFO, nu, moment,
                                    kort=f"invoer {st.leeftijd_tekst(moment, nu)}" if moment else "geen invoer",
                                    details=[f"Laatste wijziging aan {wat}: {st.leeftijd_tekst(moment, nu)}",
                                             f"{aantal} in de laatste 24 uur",
                                             "Een indeling naar soort invoer, niet naar apparaat"])
        aantal, laatste = rijen["feedback"][0]
        per_id["gebruiker.kantoor"]["details"].append(
            f"Feedback op rapporten: {aantal}" + (f", laatste {st.leeftijd_tekst(st.utc_naar_nl(laatste), nu)}"
                                                   if laatste else ""))

        o = per_id.get("cloud.mail")
        if o:
            _mail_uit_supabase(o, rijen, nu)
    else:
        for id_, naam, groep in (("bron.pats", "PATS", "Bronnen"), ("bron.agro4all", "Agro4all", "Bronnen"),
                                 ("gebruiker.kantoor", "Browser op kantoor", "Gebruikers"),
                                 ("gebruiker.telefoon", "Telefoon in de kas", "Gebruikers")):
            per_id[id_] = onderdeel(id_, naam, groep, st.GRIJS, nu, kort="onbekend",
                                    details=["Supabase niet bereikbaar"])
    return list(per_id.values())


def controleer():
    """Alle controles, parallel. Een groep die niet op tijd klaar is wordt grijs."""
    nu = datetime.now().replace(second=0, microsecond=0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        taken = {"nas": pool.submit(controleer_nas, nu), "supabase": pool.submit(controleer_supabase, nu),
                 "http": pool.submit(controleer_http, nu)}
        uitkomst = {}
        for naam, taak in taken.items():
            try:
                uitkomst[naam] = taak.result(timeout=WACHTTIJD)
            except Wachttijd:
                uitkomst[naam] = None
            except Exception as fout:           # een controle mag de pagina nooit laten vallen
                uitkomst[naam] = fout
        pool.shutdown(wait=False, cancel_futures=True)

    onderdelen, nas_ok = [], False
    if isinstance(uitkomst["nas"], tuple):
        nas_deel, nas_ok = uitkomst["nas"]
        onderdelen += nas_deel
    else:
        onderdelen.append(onderdeel("nas.uurtaak", "Uurtaak", "NAS", st.GRIJS, nu, kort="geen antwoord",
                                    details=[f"De NAS antwoordde niet op tijd: {uitkomst['nas'] or 'time-out'}"]))
    data = {}
    if isinstance(uitkomst["supabase"], tuple):
        deel, data = uitkomst["supabase"]
        onderdelen += deel
    else:
        onderdelen.append(onderdeel("cloud.supabase", "Supabase", "Cloud", st.GRIJS, nu, kort="geen antwoord",
                                    details=[str(uitkomst["supabase"] or "time-out")]))
    if isinstance(uitkomst["http"], list):
        onderdelen += uitkomst["http"]

    if nas_ok:
        kopie = next((o for o in onderdelen if o["id"] == "nas.kopie"), None)
        try:
            onderdelen += controleer_nas_database(nu, kopie)
        except Exception as fout:
            onderdelen.append(onderdeel("nas.db", "vemteelt-db", "NAS", st.ROOD, nu, details=[str(fout)]))
        versie, app = nas_versie(), next((o for o in onderdelen if o["id"] == "nas.app"), None)
        if app and versie:
            app["details"].append(f"Versie {versie[0]}, uitgerold {st.leeftijd_tekst(versie[1], nu)}")
            if app["kleur"] == st.GROEN:
                app["kort"] = f"draait · {versie[0]}"
    onderdelen = verfijn_met_data(onderdelen, data, nu)
    onderdelen.append(onderdeel("laptop.takenlijst", "Claude-taak Takenlijst-app", "Werklaptop", st.GRIJS, nu,
                                kort="niet gemeten",
                                details=["Elke ochtend 07:10: werkplanning en wateradvies van tuin 3 en de "
                                         "Agro4all-plannen in de Takenlijst van app.jobvanegmond.com",
                                         "De Claude-app houdt de runs zelf bij; zie Geplande taken in de app"]))
    onderdelen.sort(key=lambda o: (GROEPEN.index(o["groep"]), st.ERNST[o["kleur"]], o["naam"]))
    return {"gecontroleerd": datetime.now().isoformat(timespec="seconds"), "nas_bereikbaar": nas_ok,
            "onderdelen": onderdelen}


# --- Pagina ------------------------------------------------------------------------------------------------------

class Cache:
    """Eén controle tegelijk; een uitkomst is CACHE_SECONDEN geldig."""

    def __init__(self):
        self.slot = threading.Lock()
        self.uitkomst = None
        self.moment = None

    def ophalen(self, vers=False):
        with self.slot:
            if vers or self.moment is None or datetime.now() - self.moment > timedelta(seconds=CACHE_SECONDEN):
                self.uitkomst = controleer()
                self.moment = datetime.now()
            return self.uitkomst


CACHE = Cache()


class Server(ThreadingHTTPServer):
    # Zonder dit mag op Windows een tweede monitor dezelfde poort pakken (SO_REUSEADDR) en ziet hij niet dat er al
    # één draait.
    allow_reuse_address = False


class Verzoek(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._stuur(200, "text/html; charset=utf-8", PAGINA.read_bytes())
        elif self.path.startswith("/status.json"):
            uitkomst = CACHE.ophalen(vers="nu=1" in self.path)
            self._stuur(200, "application/json; charset=utf-8",
                        json.dumps(uitkomst, ensure_ascii=False).encode("utf-8"))
        else:
            self._stuur(404, "text/plain; charset=utf-8", b"niet gevonden")

    def _stuur(self, code, soort, inhoud):
        self.send_response(code)
        self.send_header("Content-Type", soort)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(inhoud)

    def log_message(self, *args):       # geen regel per verzoek in de terminal
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--poort", type=int, default=8600)
    parser.add_argument("--geen-browser", action="store_true")
    parser.add_argument("--eenmalig", action="store_true", help="één controle als tekst, zonder pagina")
    args = parser.parse_args()

    if args.eenmalig:
        for o in controleer()["onderdelen"]:
            print(f"{o['kleur']:7} {o['groep']:11} {o['naam']:28} {o['kort']}")
        return

    adres = f"http://127.0.0.1:{args.poort}"
    try:
        server = Server(("127.0.0.1", args.poort), Verzoek)
    except OSError:
        # De poort is bezet: meestal draait de monitor al (bijv. twee keer op het bureaublad geklikt).
        print(f"De statusmonitor draait al op {adres}; die wordt geopend.", flush=True)
        if not args.geen_browser:
            webbrowser.open(adres)
        return
    print(f"Statusmonitor op {adres} (stoppen met Ctrl+C)", flush=True)
    if not args.geen_browser:
        webbrowser.open(adres)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

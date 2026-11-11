"""
Stralingsverwachting van de Priva-klimaatcomputer (rubriek M4.1 Overzicht meteo verwacht, via Meteovision) uit
de bestanden die de Priva-pc naar de NAS schrijft: `<live>/alles-<datum>.jsonl` (per regel een tijdstip en de
punten die veranderd zijn) met de ids in `<live>/catalogus.csv`. Voor de watervoorspelling (watervoorspelling.py):
de verwachte stralingssom (buiten, J/cm²) van vandaag en morgen zoals die 's ochtends bekend was. Alleen lezen.

Priva rekent een dag van zonsopkomst tot zonsopkomst: vóór zonsopkomst is "vandaag" nog de dag van gisteren en
"morgen" de dag die net begint. De geplande taak draait om ± 07:10, in de winter vóór zonsopkomst.

De rekenfuncties werken op regels en lijsten (tests/test_watervoorspelling.py); alleen verwachting() leest bestanden.
"""
import csv
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from config import LIGGING
from logic import priva_bron
from logic.klimaat_dag import zon_op_onder

VANDAAG = "/meteo[{pcu}:1]/toestand/verwachting[1]/verwachteStralingssomBuitenVandaag"
MORGEN = "/meteo[{pcu}:1]/toestand/verwachting[1]/verwachteStralingssomBuitenMorgen"
OCHTEND = time(7, 10)                # het moment waarop de verwachting van een eerdere dag telt (de geplande taak)


def ids(catalogus_regels, pcu):
    """(id van 'stralsom vandaag', id van 'stralsom morgen') uit catalogus.csv, of None als ze er niet in staan."""
    adressen = {VANDAAG.format(pcu=pcu): 0, MORGEN.format(pcu=pcu): 1}
    gevonden = [None, None]
    for rij in csv.DictReader(catalogus_regels, delimiter=";"):
        if rij.get("adres") in adressen:
            gevonden[adressen[rij["adres"]]] = rij["id"]
    return tuple(gevonden) if all(gevonden) else None


def lees_punten(regels, id_lijst):
    """{id: [(tijd, waarde)]} uit regels van alles-<datum>.jsonl; tijd zonder tijdzone (lokale tijd)."""
    uit = {i: [] for i in id_lijst}
    sleutels = [f'"{i}"' for i in id_lijst]
    for regel in regels:
        if not any(s in regel for s in sleutels):
            continue
        try:
            r = json.loads(regel)
            t = datetime.fromisoformat(r["t"]).replace(tzinfo=None)
        except (ValueError, KeyError, TypeError):
            continue
        for i in id_lijst:
            w = r.get("v", {}).get(i)
            if isinstance(w, (int, float)):
                uit[i].append((t, float(w)))
    for punten in uit.values():
        punten.sort()
    return uit


def stand(punten, moment):
    """De laatste waarde op of vóór `moment`, of None."""
    waarde = None
    for t, w in punten:
        if t > moment:
            break
        waarde = w
    return waarde


def verwachting_op(vandaag_punten, morgen_punten, moment, ligging=LIGGING):
    """
    (verwachting voor de dag van `moment`, verwachting voor de dag erna) zoals Priva die op `moment` gaf.
    Vóór zonsopkomst is "morgen" de dag van `moment` en is er nog niets voor de dag erna.
    """
    zon_op = zon_op_onder(moment.date(), ligging)[0].replace(tzinfo=None)
    if moment < zon_op:
        return stand(morgen_punten, moment), None
    return stand(vandaag_punten, moment), stand(morgen_punten, moment)


def per_dag(vandaag_punten, morgen_punten, van, tot, nu=None, ligging=LIGGING):
    """
    ({datum: verwachting zoals om OCHTEND die dag} van van t/m tot, verwachting voor de dag na `tot`). Voor `tot` =
    vandaag telt `nu` (als dat eerder is dan OCHTEND, of als het later is: wat er nu bekend is).
    """
    uit, erna = {}, None
    dag = van
    while dag <= tot:
        moment = datetime.combine(dag, OCHTEND)
        if dag == tot and nu is not None:
            moment = nu
        vandaag, morgen = verwachting_op(vandaag_punten, morgen_punten, moment, ligging)
        if vandaag:
            uit[dag] = vandaag
        if dag == tot:
            erna = morgen or None
        dag += timedelta(days=1)
    return uit, erna


def verwachting(map_, tuin_nummer, van, tot, nu=None):
    """
    ({datum: verwachte stralingssom buiten (J/cm²)} van van t/m tot, verwachting voor de dag na `tot`) uit de
    Priva-bestanden van een tuin in `map_` (PRIVA_MAP). Geeft ({}, None) als de bestanden er niet zijn.
    """
    try:
        live, _historie = priva_bron.mappen(map_, tuin_nummer)
        pcu = priva_bron.instellingen(tuin_nummer)["pcu"]
        catalogus = Path(live) / "catalogus.csv"
        if not catalogus.exists():
            return {}, None
        with open(catalogus, encoding="utf-8-sig") as f:
            id_paar = ids(f, pcu)
        if not id_paar:
            return {}, None
        regels = []
        dag = van - timedelta(days=1)                   # de laatste stand van de dag ervoor geldt nog
        while dag <= tot:
            bestand = Path(live) / f"alles-{dag.isoformat()}.jsonl"
            if bestand.exists():
                with open(bestand, encoding="utf-8") as f:
                    regels.extend(f)
            dag += timedelta(days=1)
    except (OSError, ValueError):
        return {}, None
    punten = lees_punten(regels, id_paar)
    return per_dag(punten[id_paar[0]], punten[id_paar[1]], van, tot, nu)


def standaard_map():
    """PRIVA_MAP, of de Priva-share op de NAS (Windows) / /priva (container)."""
    import os
    return os.environ.get("PRIVA_MAP") or (r"\\192.168.0.197\Priva" if os.name == "nt" else "/priva")


if __name__ == "__main__":                              # snel kijken: python -m integrations.priva_meteo
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    vandaag = date.today()
    for nummer in (3, 1):
        reeks, morgen = verwachting(standaard_map(), nummer, vandaag - timedelta(days=3), vandaag, datetime.now())
        print(f"tuin {nummer}:", {str(d): round(v) for d, v in reeks.items()}, "morgen", morgen)

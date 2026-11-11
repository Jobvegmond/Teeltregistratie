"""
De verdeling van de warmte over de afdelingen, per dag. Er is één warmtemeter per tuin (tuin 3 pulsmeter 2, tuin 1
de warmtewisselaar); Priva verdeelt die over de afdelingen naar het gerealiseerde vermogen van het verwarmingsnet
per afdeling: scherm M112.0 "VERW.REG - ger verm vwn" (M112.0N<afd>R12.1V1, kW). Gecontroleerd op tuin 1, 22–25
oktober 2026: de aandelen uit dit vermogen × de tijd vielen binnen ± 1 procentpunt samen met de verdeling in
Priva's Energie-export (Sum_24h_Gas_use per afdeling). De som van het vermogen zelf ligt 25–40 % onder de meter
(verliezen en wat niet over een afdelingsnet loopt), dus het is alleen een verdeelsleutel: warmte afdeling =
gemeten warmte van de kas × aandeel.

Bronnen:
- `alles-<datum>.jsonl` in de live-map (de poller op de Priva-pc): per minuut de gewijzigde punten, sleutel = het
  id uit `catalogus.csv` (`id;adres;naam;eenheid;soort;type;scad;vervallen`). Het vermogen maal de tijd = kWh.
- De Energie-export van Priva Office (database.lees_energie_csv): Sum_24h_Gas_use per afdeling, Priva's eigen
  verdeling van de dag (in m³ aardgasequivalent; alleen de verhouding telt).

Afdeling 5 is op tuin 3 de waterruimte en op tuin 1 de schuur: die krijgt zijn deel, maar heeft geen vakken. De
afdelingen met vakken samen krijgen dus iets minder dan de hele kas.

Alleen rekenwerk en inlezen van tekst; priva_pulsmeters.py leest de bestanden en slaat op. Tests in
tests/test_warmte_afdeling.py.
"""
import csv
import json
import re
from datetime import datetime, time, timedelta

VERMOGEN = re.compile(r"M112\.0N(\d+)R12\.1V1$")
# Hoe ver het begin en het einde van het dagbestand van middernacht mogen liggen.
MARGE = timedelta(minutes=20)


def punten(catalogus_regels):
    """{id: afdeling} van het vermogen per afdeling uit de regels van catalogus.csv (vervallen punten niet)."""
    uit = {}
    for rij in csv.reader(catalogus_regels, delimiter=";"):
        if len(rij) < 7 or (len(rij) > 7 and rij[7].strip() == "1"):
            continue
        gevonden = VERMOGEN.match(rij[6].strip())
        if gevonden:
            uit[rij[0].strip().lstrip("﻿")] = int(gevonden.group(1))
    return uit


def _getal(waarde):
    if waarde is None or waarde == "" or isinstance(waarde, bool):
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def dag_kwh(regels, punten_):
    """
    (dag, {afdeling: kWh}) over de dag van een alles-<datum>.jsonl; punten_ = {id: afdeling} (zie punten()).
    (dag, None) als de dag niet volledig gedekt is (begin of einde te ver van middernacht, een storing, of geen
    vermogen); (None, None) bij een leeg of onleesbaar bestand. De basisregel kort na middernacht geldt vanaf
    middernacht, de laatste stand tot middernacht.
    """
    eerste = vorige = laatste = None
    stand, kwh, storing = {}, {}, False
    for regel in regels:
        try:
            r = json.loads(regel)
            t = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            continue                       # een half geschreven laatste regel
        if r.get("soort") == "storing":
            storing = True
        nieuw = {id_: _getal(w) for id_, w in (r.get("v") or {}).items() if id_ in punten_}
        nieuw = {id_: kw for id_, kw in nieuw.items() if kw is not None}
        if eerste is None:
            # De basisregel (kort na middernacht) geldt vanaf middernacht.
            eerste, stand = t, dict(nieuw)
            vorige = datetime.combine(t.date(), time.min, tzinfo=t.tzinfo)
        uren = (t - vorige).total_seconds() / 3600
        for id_, kw in stand.items():
            kwh[id_] = kwh.get(id_, 0.0) + kw * uren
        vorige = laatste = t
        stand.update(nieuw)
    if eerste is None:
        return None, None
    dag = eerste.date()
    begin = datetime.combine(dag, time.min, tzinfo=eerste.tzinfo)
    eind = datetime.combine(dag + timedelta(days=1), time.min, tzinfo=laatste.tzinfo)
    if storing or not stand or eerste - begin > MARGE or eind - laatste > MARGE:
        return dag, None
    uren = (eind - vorige).total_seconds() / 3600
    uit = {}
    for id_, afdeling in punten_.items():
        if id_ in stand:
            uit[afdeling] = uit.get(afdeling, 0.0) + kwh.get(id_, 0.0) + stand[id_] * uren
    return dag, uit


def aandelen(sleutel):
    """{afdeling: aandeel 0–1} uit {afdeling: waarde}; None als er niets te verdelen is (alles 0)."""
    totaal = sum(max(w or 0.0, 0.0) for w in sleutel.values())
    if totaal <= 0:
        return None
    return {a: max(w or 0.0, 0.0) / totaal for a, w in sleutel.items()}

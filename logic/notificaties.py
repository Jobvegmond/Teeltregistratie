"""
Notificaties (knop met het belletje in de kop, alleen voor config.NOTIFICATIES_VOOR): losse meldingen over wat er
vandaag te doen is in de eigen tuin. Alleen rekenwerk; ophalen en tekenen in app.py, tests in
tests/test_notificaties.py.

Een notificatie is een dict met soort ("water", "spuiten", "registratie"), titel, regels (lijst korte teksten) en
eventueel actie: de keuze bij "Wat registreer je?" op Registreren waar je het invult.
"""
from datetime import timedelta

from logic import watervoorspelling as wv

DAG = ["ma", "di", "wo", "do", "vr", "za", "zo"]
VOLGORDE = ("water", "spuiten", "registratie")


def _dag(dag, vandaag):
    """"vandaag", "morgen" of "za 07-11"."""
    if dag == vandaag:
        return "vandaag"
    if dag == vandaag + timedelta(days=1):
        return "morgen"
    return f"{DAG[dag.weekday()]} {dag:%d-%m}"


def _geleden(dag, vandaag):
    dagen = (vandaag - dag).days
    return "vandaag" if dagen == 0 else f"{dagen} {'dag' if dagen == 1 else 'dagen'} geleden"


def water(lijst):
    """
    Uit de watervoorspelling (wv.adviezen): één melding voor de vakken met "water" en één voor "twijfel", met per
    planting een regel (wv.groepen). Vakken die vandaag al water kregen of geen water nodig hebben, geven niets.
    """
    uit = []
    for advies, titel in (("water", "Water geven"), ("twijfel", "Misschien water")):
        groep = [a for a in lijst if a["advies"] == advies]
        if groep:
            uit.append({"soort": "water", "titel": f"{titel}: vak {wv.vakken_tekst([a['vak'] for a in groep])}",
                        "regels": wv.groepen(groep)})
    return uit


def spuiten(taken, vandaag, dagen=2):
    """De taken uit de werkplanning (bespuitingen, inwateren) van vandaag en de dag(en) erna, elk een melding."""
    tot = vandaag + timedelta(days=dagen - 1)
    return [{"soort": "spuiten", "titel": t["titel"], "regels": [f"{_dag(t['datum'], vandaag)} · {t['toelichting']}"]}
            for t in sorted(taken, key=lambda t: (t["datum"], min(t["vakken"] or [0])))
            if vandaag <= t["datum"] <= tot]


def registraties(vakken, vandaag):
    """
    Registraties die er volgens de planning al hadden moeten zijn (vakken uit logic.registreren.lopende_vakken):
    - Florgib: verwacht op of vóór vandaag, nog niet ingevuld;
    - emmers: de prognose-oogst is er, nog geen emmers;
    - oogstlengte: in de oogst (emmers), nog geen lengte.
    Per soort één melding met een regel per vak, de oudste eerst.
    """
    uit = []
    florgib = sorted((v for v in vakken if v["lengte_half"] is None and v["florgib_verwacht"]
                      and v["florgib_verwacht"] <= vandaag), key=lambda v: (v["florgib_verwacht"], v["vak"]))
    if florgib:
        uit.append({"soort": "registratie", "actie": "Florgib",
                    "titel": f"Florgib invullen: vak {wv.vakken_tekst([v['vak'] for v in florgib])}",
                    "regels": [f"Vak {v['vak']} · verwacht {v['florgib_verwacht']:%d-%m} "
                               f"({_geleden(v['florgib_verwacht'], vandaag)})" for v in florgib]})
    emmers = sorted((v for v in vakken if not v["emmers"] and v["prognose"] and v["prognose"] <= vandaag),
                    key=lambda v: (v["prognose"], v["vak"]))
    if emmers:
        uit.append({"soort": "registratie", "actie": "Emmers",
                    "titel": f"Nog geen emmers: vak {wv.vakken_tekst([v['vak'] for v in emmers])}",
                    "regels": [f"Vak {v['vak']} · oogst verwacht {v['prognose']:%d-%m} "
                               f"({_geleden(v['prognose'], vandaag)})" for v in emmers]})
    lengte = sorted((v for v in vakken if v["emmers"] and v["lengte_eind"] is None),
                    key=lambda v: (v["geplant"], v["vak"]))
    if lengte:
        uit.append({"soort": "registratie", "actie": "Lengte en gewicht",
                    "titel": f"Oogstlengte invullen: vak {wv.vakken_tekst([v['vak'] for v in lengte])}",
                    "regels": [f"Vak {v['vak']} · in de oogst ({v['emmers']:g} emmers), nog geen lengte"
                               for v in lengte]})
    return uit


def alles(water_lijst=(), taken=(), vakken=(), vandaag=None):
    """Alle meldingen in vaste volgorde: water, spuiten, registraties."""
    return water(water_lijst) + spuiten(taken, vandaag) + registraties(vakken, vandaag)

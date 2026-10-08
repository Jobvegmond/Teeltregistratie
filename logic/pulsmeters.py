"""
Warmte en gas per dag uit de pulsmeters van de klimaatcomputer (Priva-bestanden op de NAS).

Tuin 3 (regelaar VP9508): pulsmeter 2 = warmte in GJ, pulsmeter 1 = gas (ketel) in m³ —
dezelfde tellers als in de energie-export (database.ENERGIE_BRONNEN), gecontroleerd op
okt 2025 – sep 2026: dagverbruik uit de tellerstand en de export kwamen overeen (warmte
99,9 %, gas 100 % over de periode).

Bronnen (map Priva op de NAS):
- bron historie/pulsmeters_*.csv: per uur, `tijdstip;pulsmeterN.pulsMeterStand;…`
- bron live/historie-<datum>.jsonl: per minuut, {"t": …, "v": {"pulsmeterN.pulsMeterStand": …}}

Verbruik = de toename van de tellerstand (`pulsMeterStand`); het veld `pulsMeterTotaal`
is onbetrouwbaar. Een daling is een reset (pulsmeter 1 op 20 april 2026) en telt niet.
Alleen rekenwerk en inlezen van tekst; het script priva_pulsmeters.py leest de bestanden en
slaat op. Tests in tests/test_pulsmeters.py.
"""
import csv
import json
from datetime import datetime, timedelta

METERS = {1: "gas", 2: "warmte"}
RESET_DREMPEL = -1.0
# Een toename over een langer interval dan dit dat over middernacht loopt, is niet over de dagen te
# verdelen: die dagen zijn onvolledig. Binnen één dag maakt een gat niet uit (stand begin → stand eind).
MAX_GAT = timedelta(hours=3)


def _tijd(tekst):
    """Lokale (wand)tijd zonder tijdzone; '2026-10-07T17:21:48+02:00' en '2026-10-07 00:00:00' allebei."""
    t = datetime.fromisoformat(tekst.strip())
    return t.replace(tzinfo=None)


def _getal(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def lees_historie_csv(regels):
    """{meter: [(tijd, stand)]} uit de regels van een pulsmeters_*.csv (kop met `tijdstip`, `;` en decimale punt)."""
    uit = {n: [] for n in METERS}
    for rij in csv.DictReader(regels, delimiter=";"):
        t = _tijd(rij["tijdstip"])
        for n in METERS:
            stand = _getal(rij.get(f"pulsmeter{n}.pulsMeterStand"))
            if stand is not None:
                uit[n].append((t, stand))
    return uit


def lees_live_jsonl(regels):
    """{meter: [(tijd, stand)]} uit een historie-<datum>.jsonl; regels die geen geldige JSON zijn vallen weg."""
    uit = {n: [] for n in METERS}
    for regel in regels:
        try:
            r = json.loads(regel)
            t = _tijd(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        for n in METERS:
            stand = _getal((r.get("v") or {}).get(f"pulsmeter{n}.pulsMeterStand"))
            if stand is not None:
                uit[n].append((t, stand))
    return uit


def samenvoegen(*bronnen):
    """Meerdere {meter: [(tijd, stand)]} samen, per meter op tijd en zonder dubbele tijdstippen."""
    uit = {}
    for bron in bronnen:
        for n, reeks in bron.items():
            uit.setdefault(n, {}).update({t: v for t, v in reeks})
    return {n: sorted(per_tijd.items()) for n, per_tijd in uit.items()}


def dagverbruik(reeks):
    """
    ({dag: verbruik}, {dagen onvolledig}) uit een tellerstandreeks [(tijd, stand)].
    Een toename telt op de dag waarin het interval valt (een interval dat precies om 00:00
    eindigt hoort bij de dag ervoor); loopt een kort interval over middernacht, dan wordt
    de toename naar tijd verdeeld. Een dag is volledig als de stand vanaf 00:00 tot en met
    00:00 de dag erna bekend is en er geen lang gat over zijn grenzen loopt.
    """
    reeks = sorted(reeks)
    if len(reeks) < 2:
        return {}, set()
    verbruik, onvolledig = {}, set()
    for (t0, v0), (t1, v1) in zip(reeks, reeks[1:]):
        toename = v1 - v0
        toename = 0.0 if toename < RESET_DREMPEL else max(toename, 0.0)
        eerste, laatste = t0.date(), (t1 - timedelta(microseconds=1)).date()
        if eerste == laatste:
            verbruik[eerste] = verbruik.get(eerste, 0.0) + toename
            continue
        if t1 - t0 > MAX_GAT:
            dag = eerste
            while dag <= laatste:
                onvolledig.add(dag)
                dag += timedelta(days=1)
            continue
        duur = (t1 - t0).total_seconds()
        dag = eerste
        while dag <= laatste:
            van = max(t0, datetime.combine(dag, datetime.min.time()))
            tot = min(t1, datetime.combine(dag + timedelta(days=1), datetime.min.time()))
            verbruik[dag] = verbruik.get(dag, 0.0) + toename * (tot - van).total_seconds() / duur
            dag += timedelta(days=1)
    # Begin en eind: alleen dagen waarvan de stand om 00:00 en om 00:00 de dag erna bekend is.
    begin, eind = reeks[0][0], reeks[-1][0]
    for dag in list(verbruik):
        if datetime.combine(dag, datetime.min.time()) < begin or \
                datetime.combine(dag + timedelta(days=1), datetime.min.time()) > eind:
            onvolledig.add(dag)
    return {d: v for d, v in verbruik.items() if d not in onvolledig}, onvolledig

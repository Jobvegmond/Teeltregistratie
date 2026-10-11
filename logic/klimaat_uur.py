"""
Klimaat per uur per afdeling (en de meteo per uur) uit de Priva-bestanden op de NAS (map Priva).

- bron historie/priva_*_per-uur.csv: per heel uur de **momentwaarde** (Priva interpoleert tussen
  samples), kolommen `afdN.klimaatOverzicht.gemetenKasTemperatuur` enz.
- bron live/historie-<datum>.jsonl: per minuut de kernpunten, {"t": …, "v": {naam: waarde}}. Een uur
  is het **gemiddelde** van de minuten in [uur, uur + 1); die gaan voor de momentwaarde uit de CSV.

Een uur wordt alleen gebruikt als het voorbij is (er is een meting ná het einde van het uur). Tijden
zijn de lokale tijd van Priva, zonder tijdzone; een uur heet naar zijn begin ("2026-10-09 14:00").
Alleen rekenwerk; tests in tests/test_klimaat_uur.py.
"""
import csv
import json
from datetime import datetime, timedelta

AFDELINGEN = (1, 2, 3, 4)
# Veld in de tabel klimaat_uur → naam in de Priva-bestanden (N = afdeling).
AFDELING_VELDEN = {
    "temp": "afd{n}.klimaatOverzicht.gemetenKasTemperatuur",
    "rv": "afd{n}.klimaatOverzicht.gemetenRelatieveLuchtvochtigheid",
    "vd": "afd{n}.klimaatOverzicht.gemetenVochtdeficit",
    "co2": "afd{n}.klimaatOverzicht.gemetenCO2Concentratie",
    "verwarming": "afd{n}.verwarmingToestand.berekendeVerwarmingsTemperatuur",
}
METEO_VELDEN = {
    "buiten_temp": "meteo.buitenTemperatuur",
    "buiten_rv": "meteo.gemetenRelatieveLuchtvochtigheid",
    "straling": "meteo.stralingsMeter.stralingsIntensiteit",
    "wind": "meteo.windSnelheid",
}
# Een constante 0 is bij deze velden geen meting (geen sensor, of een storing): weglaten.
NUL_IS_LEEG = {"co2", "rv", "vd"}


def _getal(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def _uur(t):
    return t.replace(minute=0, second=0, microsecond=0)


def _rij(waarden):
    """({(afdeling, veld): waarde}, {veld: waarde}) uit één regel met Priva-namen."""
    afd, meteo = {}, {}
    for n in AFDELINGEN:
        for veld, naam in AFDELING_VELDEN.items():
            w = _getal(waarden.get(naam.format(n=n)))
            if w is not None and not (veld in NUL_IS_LEEG and w == 0):
                afd[(n, veld)] = w
    for veld, naam in METEO_VELDEN.items():
        w = _getal(waarden.get(naam))
        if w is not None:
            meteo[veld] = w
    return afd, meteo


def lees_historie_csv(regels):
    """[(tijd, afd, meteo)] uit de regels van een priva_*_per-uur.csv (momentwaarde op het hele uur)."""
    uit = []
    for rij in csv.DictReader(regels, delimiter=";"):
        try:
            t = datetime.fromisoformat(rij["tijdstip"].strip())
        except (KeyError, ValueError):
            continue
        uit.append((t, *_rij(rij)))
    return uit


def lees_live_jsonl(regels):
    """[(tijd, afd, meteo)] uit een historie-<datum>.jsonl; kapotte regels vallen weg."""
    uit = []
    for regel in regels:
        try:
            r = json.loads(regel)
            t = datetime.fromisoformat(r["t"]).replace(tzinfo=None)
        except (ValueError, KeyError, TypeError):
            continue
        uit.append((t, *_rij(r.get("v") or {})))
    return uit


def per_uur(historie, live):
    """
    ({(uur, afdeling): {veld: waarde}}, {uur: {veld: waarde}}) voor de uren die voorbij zijn.
    Live (minuten, gemiddeld per uur) gaat voor de momentwaarde uit de historie-CSV.
    """
    afd_uit, meteo_uit = {}, {}
    for t, afd, meteo in historie:           # een momentwaarde op het hele uur is altijd compleet
        for (n, veld), w in afd.items():
            afd_uit.setdefault((t, n), {})[veld] = w
        for veld, w in meteo.items():
            meteo_uit.setdefault(t, {})[veld] = w
    laatste = max((t for t, _, _ in live), default=None)
    sommen_afd, sommen_meteo = {}, {}
    for t, afd, meteo in live:
        uur = _uur(t)
        for (n, veld), w in afd.items():
            s = sommen_afd.setdefault((uur, n), {}).setdefault(veld, [0.0, 0])
            s[0] += w
            s[1] += 1
        for veld, w in meteo.items():
            s = sommen_meteo.setdefault(uur, {}).setdefault(veld, [0.0, 0])
            s[0] += w
            s[1] += 1
    for (uur, n), velden in sommen_afd.items():
        if uur + timedelta(hours=1) <= laatste:
            afd_uit[(uur, n)] = {veld: round(s / k, 2) for veld, (s, k) in velden.items()}
    for uur, velden in sommen_meteo.items():
        if uur + timedelta(hours=1) <= laatste:
            meteo_uit[uur] = {veld: round(s / k, 2) for veld, (s, k) in velden.items()}
    return afd_uit, meteo_uit

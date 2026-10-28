"""
Warmte per dag van de warmtewisselaar (tuin 1). In de Priva-bestanden van tuin 1 staat geen energieteller (de
Energie-export gebruikt Sum_24h_HXEnergy, dat de poller niet leest). Twee bronnen in `overig-<datum>.jsonl`:

- `gisteren_kw`: Priva's eigen dagwaarde, scherm M302.1 "warmte gisteren", regel W.WISSELAAR
  (M302.1N1R6.1V1): het gemiddelde vermogen (kW) van de vorige dag; × 24 uur = kWh. Gelijk aan
  Ave_24h_HXCapacity in de Energie-export (en Sum_24h_HXEnergy ± 1 %). Dit gaat voor.
- `dag_kwh`: het gerealiseerde vermogen, scherm M340.0 "W.WISSELAAR - ger vermogen" (M340.0N1R11.1V1, kW),
  maal de tijd. Alleen als terugval: tot 28-10-2026 las de poller dit scherm maar elke ± 15 minuten, en de
  warmtewisselaar slaat steeds aan en af (0 – 2.000 kW), dus een dag zat er 10 % of meer naast.

Alleen rekenwerk en inlezen van tekst; priva_pulsmeters.py leest de bestanden en slaat op. Tests in
tests/test_warmtewisselaar.py.
"""
import json
from datetime import datetime, time, timedelta

GISTEREN = "M302.1N1R6.1V1"
# De poller leest het scherm "gisteren" eens per dag, kort na de daggrens van de regelaar. Die loopt niet mee
# met de wintertijd: sinds 25-10-2026 wisselt de dag om 23:00 (= 0:00 zomertijd). Een nieuwe waarde die tussen
# 22:00 en 3:00 binnenkomt hoort bij de dag van 3 uur eerder.
GISTEREN_UREN = (22, 23, 0, 1, 2)
GISTEREN_TERUG = timedelta(hours=3)


def gisteren_kw(regels, punt=GISTEREN):
    """
    {dag: gemiddeld kW} uit een overig-<datum>.jsonl: elke nieuwe waarde van het scherm "gisteren" (een regel
    "meting", niet de basisregel met de oude stand) rond de daggrens, bij de dag die toen afliep. Is de waarde
    gelijk aan die van de dag ervoor, dan komt er geen regel en ontbreekt die dag.
    """
    uit = {}
    for regel in regels:
        try:
            r = json.loads(regel)
            t = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        waarde = _getal((r.get("v") or {}).get(punt))
        if r.get("soort") == "meting" and waarde is not None and t.hour in GISTEREN_UREN:
            uit[(t - GISTEREN_TERUG).date()] = waarde
    return uit

# Hoe ver het begin en het einde van het dagbestand van middernacht mogen liggen.
MARGE = timedelta(minutes=20)


def _getal(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def dag_kwh(regels, punt):
    """
    (dag, kWh) over de dag van een overig-<datum>.jsonl, met het vermogen `punt` in kW. (dag, None) als de dag
    niet volledig gedekt is (begin of einde te ver van middernacht, een storing, of het punt ontbreekt);
    (None, None) bij een leeg of onleesbaar bestand. De tijden hebben een tijdzone (+01:00/+02:00), dus een
    dag met de overgang naar wintertijd telt 25 uur.
    """
    eerste = vorige = laatste = None
    stand, kwh, storing = None, 0.0, False
    for regel in regels:
        try:
            r = json.loads(regel)
            t = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            continue                       # een half geschreven laatste regel
        if r.get("soort") == "storing":
            storing = True
        waarde = _getal((r.get("v") or {}).get(punt))
        if eerste is None:
            # De basisregel (kort na middernacht) geldt vanaf middernacht.
            eerste, stand = t, waarde
            vorige = datetime.combine(t.date(), time.min, tzinfo=t.tzinfo)
        if stand is not None:
            kwh += stand * (t - vorige).total_seconds() / 3600
        vorige = t
        if waarde is not None:
            stand = waarde
        laatste = t
    if eerste is None:
        return None, None
    dag = eerste.date()
    begin = datetime.combine(dag, time.min, tzinfo=eerste.tzinfo)
    eind = datetime.combine(dag + timedelta(days=1), time.min, tzinfo=laatste.tzinfo)
    if storing or stand is None or eerste - begin > MARGE or eind - laatste > MARGE:
        return dag, None
    kwh += stand * (eind - vorige).total_seconds() / 3600     # de laatste stand tot middernacht
    return dag, kwh

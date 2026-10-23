"""
Warmte per dag uit het vermogen van de warmtewisselaar (tuin 1). In de Priva-bestanden van tuin 1 staat geen
energieteller (de Energie-export gebruikt Sum_24h_HXEnergy, dat de poller niet leest), wel het gerealiseerde
vermogen van de warmtewisselaar: scherm M340.0, "W.WISSELAAR - ger vermogen" (M340.0N1R11.1V1, kW), in
`overig-<datum>.jsonl`.

Energie = vermogen × tijd. Het bestand bevat een basisregel (alle punten) en daarna alleen wijzigingen: een
waarde geldt tot de volgende. Het scherm wordt elke 1–15 minuten gelezen (config van de poller); hoe vaker,
hoe nauwkeuriger, want de warmtewisselaar slaat vaak aan en af.

Een dag telt alleen als hij helemaal gedekt is: het bestand begint kort na middernacht en loopt tot kort voor
middernacht, zonder storing. Alleen rekenwerk en inlezen van tekst; priva_pulsmeters.py leest de bestanden en
slaat op. Tests in tests/test_warmtewisselaar.py.
"""
import json
from datetime import datetime, time, timedelta

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

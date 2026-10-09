"""
Watergift per vak per dag (l/m², EC, pH) uit de Priva-bestanden op de NAS (map Priva), tuin 3
(regelaar VP9508). Kraan 1–39 = vak 1–39, zoals in de Priva-API.

- Afgeronde dagen: `bron historie/water/kraan-per-dag.csv`, eens per dag kort na 00:05 geschreven
  uit het Priva-scherm "KRAAN GISTEREN" (M412.1): `datum;kraan;ec_mS_cm;ph;liter;ml_per_eenheid;
  l_per_m2;…`. EC en pH staan daar op één decimaal.
- Vandaag tot nu toe: `bron live/water-actueel.json`, elke minuut, scherm "KRAAN VANDAAG" (M412.0):
  sleutel `M412.0N<pagina>R1.<kraan>V<n>` met pagina 1 = kraan 1–20, 2 = kraan 21–39 en
  V1 EC, V2 pH, V3 liter, V5 l/m².

Alleen inlezen en rekenen; het script priva_watergift.py slaat op. Tests in tests/test_priva_watergift.py.
"""
import csv
import json
from datetime import date, datetime, timedelta

KRANEN = range(1, 40)
# Vlak na middernacht kan "vandaag" in Priva nog de stand van gisteren zijn (het scherm schuift om 00:05
# door); een stand van vóór dit tijdstip wordt niet als vandaag gebruikt.
VANDAAG_VANAF = (0, 15)
# Een actuele stand die ouder is dan dit, telt niet (de kopie naar de NAS staat dan stil).
MAX_OUDERDOM = timedelta(hours=2)


def _getal(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def lees_kraan_per_dag(regels):
    """[{vak, datum, liter_per_m2, ec, ph}] uit kraan-per-dag.csv; zonder gift zijn EC en pH leeg."""
    uit = []
    for rij in csv.DictReader(regels, delimiter=";"):
        try:
            dag, vak = date.fromisoformat(rij["datum"].strip()), int(rij["kraan"])
        except (KeyError, ValueError):
            continue
        liter = _getal(rij.get("l_per_m2"))
        if liter is None:
            continue
        uit.append({"vak": vak, "datum": dag, "liter_per_m2": round(liter, 2),
                    "ec": _getal(rij.get("ec_mS_cm")), "ph": _getal(rij.get("ph"))})
    return uit


def _sleutel(kraan, v):
    return f"M412.0N{1 if kraan <= 20 else 2}R1.{kraan}V{v}"


def lees_vandaag(tekst, nu):
    """
    (dag, [{vak, datum, liter_per_m2, ec, ph}]) uit water-actueel.json: de stand van vandaag tot nu toe
    per kraan. (None, []) als de stand te oud is, van vlak na middernacht, of onleesbaar.
    `nu` = de huidige tijd met tijdzone (bijv. UTC). De dag en het uur komen uit de tijdstempel van het
    bestand zelf (Nederlandse tijd met +01:00/+02:00), zodat de klok van de container niet uitmaakt.
    """
    try:
        data = json.loads(tekst)
        tijd = datetime.fromisoformat(data["tijdstip"])
        waarden = data["waarden"]
    except (ValueError, KeyError, TypeError):
        return None, []
    if tijd.tzinfo is None or nu - tijd > MAX_OUDERDOM or (tijd.hour, tijd.minute) < VANDAAG_VANAF:
        return None, []
    rijen = []
    for kraan in KRANEN:
        liter = _getal(waarden.get(_sleutel(kraan, 5)))
        if liter is None:
            continue
        rijen.append({"vak": kraan, "datum": tijd.date(), "liter_per_m2": round(liter, 2),
                      "ec": _getal(waarden.get(_sleutel(kraan, 1))) if liter else None,
                      "ph": _getal(waarden.get(_sleutel(kraan, 2))) if liter else None})
    return tijd.date(), rijen

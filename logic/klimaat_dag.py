"""
Klimaat per dag per afdeling (tabel klimaatdata_dag) uit de Priva-bestanden op de NAS: etmaal-, dag- en
nachttemperatuur, dezelfde RV's en de lichtsom. Vervangt de dagwaarden uit de Priva-API; de uitkomsten zijn
vergeleken met wat de API gaf (okt 2026, beide tuinen): temperatuur ± 0,01 °C gemiddeld, RV ± 0,1 %, lichtsom
± 1 J/cm².

- Etmaal: het gemiddelde van de minuten van 0:00 tot 24:00 (lokale tijd).
- Dag: van zonsopkomst tot zonsondergang (de zon zelf, zoals de API; de regelaar wisselt op het scherm
  M101.0 "actuele periode" een paar minuten later naar dag en ± 15 min vóór zonsondergang al naar nacht).
- Nacht: van zonsondergang tot zonsopkomst de volgende ochtend; hij hoort bij de dag waarop hij begint, zoals
  bij de API. De nacht van gisteren is dus pas na zonsopkomst vandaag compleet.
- Temperatuur en RV per minuut: `historie-<datum>.jsonl` (kernpunten); een RV van 0 is geen meting.
- Lichtsom: de berekende straling in de afdeling (W/m², "ber afd stral", M100.0N1R3.<afd>V5, hetzelfde punt
  als de API gebruikte) uit `alles-<datum>.jsonl`, opgeteld over de kalenderdag naar J/cm². Dat bestand
  bevat alleen wijzigingen: een waarde geldt tot de volgende. Het id per afdeling staat in catalogus.csv.

Een waarde komt er alleen als de minuten het hele venster dekken (geen gat van meer dan MAX_GAT); anders
blijft hij leeg en vult een volgende run hem aan. Alleen rekenwerk; priva_klimaat.py leest de bestanden en slaat
op. Tests in tests/test_klimaat_dag.py.
"""
import csv
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NL = ZoneInfo("Europe/Amsterdam")
AFDELINGEN = (1, 2, 3, 4)
TEMP = "afd{n}.klimaatOverzicht.gemetenKasTemperatuur"
RV = "afd{n}.klimaatOverzicht.gemetenRelatieveLuchtvochtigheid"
STRALING = "/afdeling[{pcu}:{n}]/klimaatOverzicht/berekendeBinnenStraling"
# Een venster telt als compleet als er nergens langer dan dit geen minuut is (ook niet aan het begin of eind).
# Een uur mag: bij de overgang naar wintertijd schrijft de poller het tweede uur van 2 tot 3 niet (25-10-2026).
MAX_GAT = timedelta(minutes=75)


def zon_op_onder(datum, ligging):
    """
    (zonsopkomst, zonsondergang) op `datum` als tijden met tijdzone, voor `ligging` = (breedte, lengte) in
    graden. De zon op 0,833° onder de horizon (rand van de zon, met lichtbreking), zoals de gangbare tabellen;
    nauwkeurig op ± 1 minuut (NOAA-benadering).
    """
    breedte, lengte = ligging
    g = 2 * math.pi / 365 * (datum.timetuple().tm_yday - 1)
    tijdvereffening = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                                - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    declinatie = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
                  + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    uurhoek = math.degrees(math.acos(
        math.sin(math.radians(-0.833)) / (math.cos(math.radians(breedte)) * math.cos(declinatie))
        - math.tan(math.radians(breedte)) * math.tan(declinatie)))
    middernacht = datetime(datum.year, datum.month, datum.day, tzinfo=timezone.utc)
    op, onder = (middernacht + timedelta(minutes=720 - 4 * (lengte + teken * uurhoek) - tijdvereffening)
                 for teken in (1, -1))
    return op.astimezone(NL), onder.astimezone(NL)


def _getal(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def _tijd(tekst):
    t = datetime.fromisoformat(tekst)
    return t if t.tzinfo else t.replace(tzinfo=NL)


def lees_minuten(regels):
    """[(tijd, {afdeling: (temp, rv)})] uit een historie-<datum>.jsonl; kapotte regels vallen weg."""
    uit = []
    for regel in regels:
        try:
            r = json.loads(regel)
            t = _tijd(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        v = r.get("v") or {}
        waarden = {}
        for n in AFDELINGEN:
            temp, rv = _getal(v.get(TEMP.format(n=n))), _getal(v.get(RV.format(n=n)))
            waarden[n] = (temp, rv if rv else None)
        uit.append((t, waarden))
    return uit


def stralings_ids(catalogus_regels, pcu):
    """{id: afdeling} van de berekende afdelingsstraling uit catalogus.csv (de ids verschillen per regelaar)."""
    adressen = {STRALING.format(pcu=pcu, n=n): n for n in AFDELINGEN}
    return {rij["id"]: adressen[rij["adres"]] for rij in csv.DictReader(catalogus_regels, delimiter=";")
            if rij.get("adres") in adressen}


def lees_straling(regels, ids):
    """
    ({afdeling: [(tijd, W/m²)]}, [tijd van elke regel]) uit een alles-<datum>.jsonl. Een regel "storing"
    telt niet als dekking: de waarden zijn dan de laatst bekende, niet de actuele.
    """
    punten, tijden = {n: [] for n in ids.values()}, []
    for regel in regels:
        try:
            r = json.loads(regel)
            t = _tijd(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        if r.get("soort") == "storing":
            continue
        tijden.append(t)
        for i, n in ids.items():
            if i in (r.get("v") or {}):
                punten[n].append((t, _getal(r["v"][i])))
    return punten, tijden


def gedekt(tijden, begin, eind):
    """
    True als de (gesorteerde) tijden het venster [begin, eind) dekken zonder gat van meer dan MAX_GAT. Er moet
    ook een tijd ná het eind zijn: zo telt een venster dat nog loopt (de laatste minuten van vandaag) niet mee.
    """
    vorige = begin
    for t in tijden:
        if t < begin:
            continue
        if t - vorige > MAX_GAT:
            return False
        if t >= eind:
            return True
        vorige = t
    return False


def _gemiddelde(minuten, n, i, begin, eind):
    waarden = [w[n][i] for t, w in minuten if begin <= t < eind and w[n][i] is not None]
    return sum(waarden) / len(waarden) if waarden else None


def _som(punten, begin, eind):
    """De straling (W/m²) opgeteld over [begin, eind) in J/cm²; elke waarde geldt tot de volgende."""
    som, waarde, vanaf = 0.0, None, begin
    for t, w in punten:
        if t <= begin:
            waarde = w
            continue
        if t >= eind:
            break
        som += (waarde or 0) * (t - vanaf).total_seconds()
        waarde, vanaf = w, t
    som += (waarde or 0) * (eind - vanaf).total_seconds()
    return som / 1e4


def _rond(waarde, decimalen):
    return None if waarde is None else round(waarde, decimalen)


def dagwaarden(datum, ligging, minuten, straling=None, straling_tijden=()):
    """
    De rijen voor klimaatdata_dag van één dag: [{afdeling, datum, gem_temperatuur, gem_rv, gem_temperatuur_dag,
    gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht, stralingssom_dag}], of [] als het etmaal nog niet compleet
    is. `minuten` (lees_minuten) en `straling` (lees_straling) mogen meer dagen bevatten; voor de nacht zijn de
    minuten tot de volgende ochtend nodig. Dag, nacht of lichtsom die (nog) niet compleet is, blijft None.
    """
    minuten = sorted(minuten, key=lambda m: m[0])
    tijden = [t for t, _ in minuten]
    nul = datetime.combine(datum, time(), tzinfo=NL)
    morgen = datetime.combine(datum + timedelta(days=1), time(), tzinfo=NL)
    if not gedekt(tijden, nul, morgen):
        return []
    op, onder = zon_op_onder(datum, ligging)
    op_morgen = zon_op_onder(datum + timedelta(days=1), ligging)[0]
    vensters = {"": (nul, morgen), "_dag": (op, onder), "_nacht": (onder, op_morgen)}
    compleet = {naam: gedekt(tijden, b, e) for naam, (b, e) in vensters.items()}
    licht = straling is not None and gedekt(sorted(straling_tijden), nul, morgen)
    rijen = []
    for n in AFDELINGEN:
        rij = {"afdeling": n, "datum": datum}
        for naam, (b, e) in vensters.items():
            rij[f"gem_temperatuur{naam}"] = _rond(_gemiddelde(minuten, n, 0, b, e), 2) if compleet[naam] else None
            rij[f"gem_rv{naam}"] = _rond(_gemiddelde(minuten, n, 1, b, e), 1) if compleet[naam] else None
        punten = sorted((straling or {}).get(n) or [], key=lambda p: p[0])
        rij["stralingssom_dag"] = _rond(_som(punten, nul, morgen), 0) if licht and punten else None
        if rij["gem_temperatuur"] is not None:
            rijen.append(rij)
    return rijen

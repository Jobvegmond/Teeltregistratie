"""
Watergift en waterkwaliteit uit de Priva Horti API, in één verzoek per tuin.

- Gift per vak: de oplopende meterstand KRAAN.VERBRUIKM2 (l/m²) per kraan
  (kraan = vak). Daggift = de toename over de dag; een gietbeurt = een reeks
  toenames zonder pauze langer dan BEURT_PAUZE.
- EC en pH per watersysteem: gemeten (EC_BOX.GEM_EC, PH_BOX.GEM_PH) en
  ingesteld (DOS_EC_CTL.REGEL_EC, DOS_PH_CTL.REGEL_PH), plus het actieve
  recept. De EC/pH per kraan (KRAAN.GEMID_EC/PH) is in Priva een kopie van het
  watersysteem, dus die halen we niet apart op. Daggemiddelde = tijdgewogen
  over de metingen (Priva logt bij verandering), elke meting telt tot de
  volgende maar hooguit MAX_GEWICHT, zodat een stilstand 's nachts het
  gemiddelde niet bepaalt.

De rekenfuncties werken op lijsten (tijdstip UTC, waarde) en zijn los te
testen (tests/test_priva_water.py); alleen haal_water_dagwaarden praat met Priva.
"""
from datetime import datetime, timedelta

from config import WATERSYSTEMEN as _WATERSYSTEMEN
from priva_client import LOKALE_OFFSET, STAART_WATER_METERSTAND, WATER_RESET_DREMPEL

# De watersystemen die we ophalen (zie config.WATERSYSTEMEN; ongebruikte systemen staan daar niet in).
WATERSYSTEMEN = tuple(sorted({systeem for per_tuin in _WATERSYSTEMEN.values() for systeem in per_tuin}))
STAART_EC = "0000000056a9"         # EC_BOX.GEM_EC        gemeten EC (mS/cm)
STAART_PH = "000000005752"         # PH_BOX.GEM_PH        gemeten pH
STAART_EC_DOEL = "000000005667"    # DOS_EC_CTL.REGEL_EC  berekende (ingestelde) EC
STAART_PH_DOEL = "000000005669"    # DOS_PH_CTL.REGEL_PH  berekende (ingestelde) pH
STAART_RECEPT = "00000000579a"     # WATDIS.RECEPT_NR     actief recept
GEEN_RECEPT = 32767                # Priva: geen recept actief
BEURT_PAUZE = timedelta(minutes=10)
MAX_GEWICHT = timedelta(minutes=10)

GROOTHEDEN = {STAART_EC: "ec", STAART_PH: "ph", STAART_EC_DOEL: "ec_doel", STAART_PH_DOEL: "ph_doel",
              STAART_RECEPT: "recept"}


def watersysteem_variabele(systeem, staart):
    return f"000002dc-{systeem:04x}-0000-0000-{staart}"


def kraan_variabele(vak):
    return f"000001c2-{vak:04x}-0000-0000-{STAART_WATER_METERSTAND}"


def lokale_dag(t):
    return (t + LOKALE_OFFSET).date()


def reeks_uit(entry):
    """[(tijdstip UTC, waarde)] uit één datapoint-entry van de API, op tijd gesorteerd; lege waarden vallen weg."""
    uit = []
    for meting in entry.get("measurements", []):
        ruwe = meting.get("value")
        if ruwe is None or ruwe == "":
            continue
        try:
            uit.append((datetime.fromisoformat(meting["timestampUtc"].replace("Z", "+00:00")), float(ruwe)))
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(uit)


def gift_per_dag(reeks):
    """
    {dag: (liter per m², aantal beurten)} uit een meterstandreeks. Een grote
    negatieve sprong is een reset en telt niet. Een dag met meterstanden maar
    zonder toename geeft (0.0, 0): gemeten, niets gegeven. Een beurt telt op de
    dag waarop hij begint.
    """
    uit, vorige_toename = {}, None
    for (t0, v0), (t1, v1) in zip(reeks, reeks[1:]):
        toename = v1 - v0
        if toename < WATER_RESET_DREMPEL:
            continue
        dag = lokale_dag(t0)
        liter, beurten = uit.get(dag, (0.0, 0))
        if toename > 0:
            if vorige_toename is None or t0 - vorige_toename > BEURT_PAUZE:
                beurten += 1
            vorige_toename = t1
            liter += toename
        uit[dag] = (liter, beurten)
    return {dag: (round(liter, 1), beurten) for dag, (liter, beurten) in uit.items()}


def tijdgewogen_per_dag(reeks, max_gewicht=MAX_GEWICHT):
    """{dag: {"gem", "min", "max", "n"}}: elke meting telt tot de volgende, hooguit max_gewicht."""
    per_dag = {}
    for i, (t, v) in enumerate(reeks):
        volgende = reeks[i + 1][0] if i + 1 < len(reeks) else t + max_gewicht
        gewicht = min(volgende - t, max_gewicht).total_seconds() or 1.0
        per_dag.setdefault(lokale_dag(t), []).append((v, gewicht))
    uit = {}
    for dag, paren in per_dag.items():
        totaal = sum(g for _, g in paren)
        waarden = [v for v, _ in paren]
        uit[dag] = {"gem": sum(v * g for v, g in paren) / totaal, "min": min(waarden), "max": max(waarden),
                    "n": len(paren)}
    return uit


def recept_per_dag(reeks):
    """{dag: recept} = het recept dat die dag het langst actief was (zonder 'geen recept')."""
    duur = {}
    for i, (t, v) in enumerate(reeks):
        if int(v) == GEEN_RECEPT:
            continue
        volgende = reeks[i + 1][0] if i + 1 < len(reeks) else t + MAX_GEWICHT
        dag = lokale_dag(t)
        duur.setdefault(dag, {})
        duur[dag][int(v)] = duur[dag].get(int(v), 0.0) + (volgende - t).total_seconds()
    return {dag: max(r, key=r.get) for dag, r in duur.items()}


def kwaliteit_rijen(reeksen, systeem, vanaf, tot):
    """
    Dagregels voor water_kwaliteit_dag uit {grootheid: reeks} van één
    watersysteem, alleen dagen vanaf..tot (inclusief) met een EC- of pH-meting.
    """
    ec, ph = tijdgewogen_per_dag(reeksen.get("ec", [])), tijdgewogen_per_dag(reeksen.get("ph", []))
    # De ingestelde waarde staat op 0 zolang er niet gedoseerd wordt; die tellen niet mee.
    ec_doel = tijdgewogen_per_dag([(t, w) for t, w in reeksen.get("ec_doel", []) if w > 0])
    ph_doel = tijdgewogen_per_dag([(t, w) for t, w in reeksen.get("ph_doel", []) if w > 0])
    recept = recept_per_dag(reeksen.get("recept", []))
    rijen = []
    for dag in sorted(set(ec) | set(ph)):
        if not vanaf <= dag <= tot:
            continue
        e, p = ec.get(dag), ph.get(dag)
        rijen.append({
            "watersysteem": systeem, "datum": dag,
            "ec_gem": round(e["gem"], 2) if e else None, "ec_min": e["min"] if e else None,
            "ec_max": e["max"] if e else None,
            "ph_gem": round(p["gem"], 2) if p else None, "ph_min": p["min"] if p else None,
            "ph_max": p["max"] if p else None,
            "ec_doel": round(ec_doel[dag]["gem"], 2) if dag in ec_doel else None,
            "ph_doel": round(ph_doel[dag]["gem"], 2) if dag in ph_doel else None,
            "recept": recept.get(dag), "metingen": (e["n"] if e else 0) + (p["n"] if p else 0),
        })
    return rijen


def haal_water_dagwaarden(client, dagen_terug):
    """
    Eén API-verzoek: gift per vak én EC/pH per watersysteem voor de laatste
    afgeronde dagen. Geeft (gift, kwaliteit):
      gift: [{"vaknummer", "datum", "liter_per_m2", "beurten"}], op (datum, vak)
      kwaliteit: dagregels van kwaliteit_rijen, op (systeem, datum)
    De oudste dag van het venster valt weg (daarvoor ontbreekt de stand van
    vóór middernacht); vandaag telt nooit mee.
    """
    begin, eind = client._venster(dagen_terug)
    oudste = lokale_dag(begin) + timedelta(days=1)
    laatste = eind.date()        # het venster eindigt vóór middernacht UTC: de lokale dag daarna is nog niet af
    datapoints = [{"deviceGroupId": "none", "deviceId": client.device_id, "variableId": kraan_variabele(vak)}
                  for vak in client.vakken]
    datapoints += [{"deviceGroupId": "none", "deviceId": client.device_id,
                    "variableId": watersysteem_variabele(systeem, staart)}
                   for systeem in WATERSYSTEMEN for staart in GROOTHEDEN]
    payload = client._data_call(begin, eind, datapoints, "watergift")

    gift, reeksen = [], {}
    for entry in payload.get("data", []):
        dp = entry.get("datapoint", {})
        vid = dp.get("variableId") or dp.get("id") or ""
        delen = vid.split("-")
        if len(delen) != 5:
            continue
        reeks = reeks_uit(entry)
        if delen[0] == "000001c2" and delen[4] == STAART_WATER_METERSTAND:
            vak = int(delen[1], 16)
            for dag, (liter, beurten) in gift_per_dag(reeks).items():
                if oudste <= dag <= laatste:
                    gift.append({"vaknummer": vak, "datum": dag, "liter_per_m2": liter, "beurten": beurten})
        elif delen[0] == "000002dc" and delen[4] in GROOTHEDEN:
            reeksen.setdefault(int(delen[1], 16), {})[GROOTHEDEN[delen[4]]] = reeks
    kwaliteit = [r for systeem in sorted(reeksen) for r in kwaliteit_rijen(reeksen[systeem], systeem, oudste, laatste)]
    gift.sort(key=lambda r: (r["datum"], r["vaknummer"]))
    return gift, kwaliteit

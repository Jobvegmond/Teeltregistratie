"""
Watergift en waterkwaliteit uit de Priva Horti API, in één verzoek per tuin.

- Gift per vak: de oplopende meterstand KRAAN.VERBRUIKM2 (l/m²) per kraan
  (kraan = vak). Daggift = de toename over de dag; een gietbeurt = een reeks
  toenames zonder pauze langer dan BEURT_PAUZE.
- EC en pH per gift: het tijdgewogen gemiddelde van de EC/pH van het
  watersysteem tussen start en eind van de beurt. Zo rekent Priva ook (A_EC en
  A_pH in het kraanoverzicht; gecontroleerd op kraan 7–9 van tuin 3, 29-09-26).
  De API geeft die per-beurtwaarde zelf niet: KRAAN.GEMID_EC is daar de
  live-meting. Daarnaast de gemiddelde flow van de kraan tijdens de beurt.
- EC en pH per watersysteem: gemeten (EC_BOX.GEM_EC, PH_BOX.GEM_PH) en
  ingesteld (DOS_EC_CTL.REGEL_EC, DOS_PH_CTL.REGEL_PH), het actieve recept en
  de gemeten EC van het uitgangswater (voorregeling, EC_M_SENSOR.GEM_EC); het
  verschil met de gift-EC is wat er aan meststoffen bij komt. De EC/pH per kraan (KRAAN.GEMID_EC/PH) is in Priva een kopie van het
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
STAART_EC_AANVOER = "0000000056ae"  # EC_M_SENSOR.GEM_EC  gemeten EC van het uitgangswater (voorregeling)
GEEN_RECEPT = 32767                # Priva: geen recept actief
BEURT_PAUZE = timedelta(minutes=10)
MAX_GEWICHT = timedelta(minutes=10)

GROOTHEDEN = {STAART_EC: "ec", STAART_PH: "ph", STAART_EC_DOEL: "ec_doel", STAART_PH_DOEL: "ph_doel",
              STAART_RECEPT: "recept", STAART_EC_AANVOER: "ec_aanvoer"}


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


# Tijdens een gietbeurt logt Priva de meterstand elke ~5 s; daarbuiten alleen bij een wijziging en eens
# per 12 uur. Ligt de vorige stand langer dan dit terug, dan begon het water pas bij de nieuwe stand te lopen.
LOG_STAP = timedelta(seconds=30)


def _begin_toename(t0, t1):
    """Het moment waarop een toename van de meterstand begon: t0, of vlak voor t1 als t0 lang geleden is."""
    return t0 if t1 - t0 <= LOG_STAP else t1 - timedelta(seconds=5)


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
        begin = _begin_toename(t0, t1) if toename > 0 else t0
        dag = lokale_dag(begin)
        liter, beurten = uit.get(dag, (0.0, 0))
        if toename > 0:
            if vorige_toename is None or begin - vorige_toename > BEURT_PAUZE:
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
    aanvoer = tijdgewogen_per_dag([(t, w) for t, w in reeksen.get("ec_aanvoer", []) if w > 0])
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
            "ec_aanvoer": round(aanvoer[dag]["gem"], 3) if dag in aanvoer else None,
            "recept": recept.get(dag), "metingen": (e["n"] if e else 0) + (p["n"] if p else 0),
        })
    return rijen


STAART_KRAAN_FLOW = "000000003428"   # KRAAN.FLOW  flow tijdens de gift (m³/uur)


def kraan_flow_variabele(vak):
    return f"000001c2-{vak:04x}-0000-0000-{STAART_KRAAN_FLOW}"


def beurten_uit(reeks):
    """
    De gietbeurten uit een meterstandreeks: [(start, eind, l/m²)], tijden in UTC.
    Een beurt = opeenvolgende toenames zonder pauze langer dan BEURT_PAUZE.
    """
    uit = []
    for (t0, v0), (t1, v1) in zip(reeks, reeks[1:]):
        toename = v1 - v0
        if toename <= 0 or toename < WATER_RESET_DREMPEL:
            continue
        begin = _begin_toename(t0, t1)
        if uit and begin - uit[-1][1] <= BEURT_PAUZE:
            start, _, liter = uit[-1]
            uit[-1] = (start, t1, liter + toename)
        else:
            uit.append((begin, t1, toename))
    return uit


def gemiddelde_tussen(reeks, van, tot):
    """
    Tijdgewogen gemiddelde van een reeks tussen van en tot, zoals Priva de EC/pH
    van een gift toont: de laatste meting vóór `van` geldt vanaf `van`, elke
    meting telt tot de volgende. None zonder metingen.
    """
    voor = [w for t, w in reeks if t <= van]
    punten = ([(van, voor[-1])] if voor else []) + [(t, w) for t, w in reeks if van < t < tot]
    if not punten:
        return None
    duur = (tot - punten[0][0]).total_seconds()
    if duur <= 0:
        return punten[0][1]
    som = sum(((punten[i + 1][0] if i + 1 < len(punten) else tot) - t).total_seconds() * w
              for i, (t, w) in enumerate(punten))
    return som / duur


def gewogen(paren):
    """Gemiddelde van (waarde, gewicht)-paren zonder lege waarden, of None."""
    paren = [(w, g) for w, g in paren if w is not None and g]
    totaal = sum(g for _, g in paren)
    return sum(w * g for w, g in paren) / totaal if totaal else None


def beurt_rijen(vak, meterstand, ec, ph, flow):
    """Eén regel per gietbeurt van een vak: start, eind, dag, l/m², EC, pH en flow gemiddeld over de beurt."""
    rijen = []
    for start, eind, liter in beurten_uit(meterstand):
        f = gemiddelde_tussen([(t, w) for t, w in flow if w > 0], start, eind) if flow else None
        rijen.append({"vaknummer": vak, "start": start, "eind": eind, "datum": lokale_dag(start),
                      "liter_per_m2": round(liter, 2),
                      "ec": round(gemiddelde_tussen(ec, start, eind), 3) if ec else None,
                      "ph": round(gemiddelde_tussen(ph, start, eind), 2) if ph else None,
                      "flow": round(f, 2) if f is not None else None})
    return rijen


def haal_water_dagwaarden(client, dagen_terug):
    """
    Eén API-verzoek: gift per vak, EC/pH per watersysteem en de flow per kraan
    voor de laatste afgeronde dagen. Geeft (gift, kwaliteit, beurten):
      gift: [{"vaknummer", "datum", "liter_per_m2", "beurten", "ec", "ph"}], op (datum, vak);
            ec/ph = het gemiddelde van de giften van dat vak die dag, gewogen naar de liters
      kwaliteit: dagregels van kwaliteit_rijen, op (systeem, datum), met ec_gift/ph_gift =
            het gemiddelde van alle giften van die dag, gewogen naar de liters
      beurten: dicts van beurt_rijen (per gietbeurt)
    De oudste dag van het venster valt weg (daarvoor ontbreekt de stand van
    vóór middernacht); vandaag telt nooit mee.
    """
    begin, eind = client._venster(dagen_terug)
    oudste = lokale_dag(begin) + timedelta(days=1)
    laatste = eind.date()        # het venster eindigt vóór middernacht UTC: de lokale dag daarna is nog niet af
    datapoints = [{"deviceGroupId": "none", "deviceId": client.device_id, "variableId": v}
                  for vak in client.vakken for v in (kraan_variabele(vak), kraan_flow_variabele(vak))]
    datapoints += [{"deviceGroupId": "none", "deviceId": client.device_id,
                    "variableId": watersysteem_variabele(systeem, staart)}
                   for systeem in WATERSYSTEMEN for staart in GROOTHEDEN]
    payload = client._data_call(begin, eind, datapoints, "watergift")

    meterstanden, flows, reeksen = {}, {}, {}
    for entry in payload.get("data", []):
        dp = entry.get("datapoint", {})
        vid = dp.get("variableId") or dp.get("id") or ""
        delen = vid.split("-")
        if len(delen) != 5:
            continue
        reeks = reeks_uit(entry)
        if delen[0] == "000001c2" and delen[4] == STAART_WATER_METERSTAND:
            meterstanden[int(delen[1], 16)] = reeks
        elif delen[0] == "000001c2" and delen[4] == STAART_KRAAN_FLOW:
            flows[int(delen[1], 16)] = reeks
        elif delen[0] == "000002dc" and delen[4] in GROOTHEDEN:
            reeksen.setdefault(int(delen[1], 16), {})[GROOTHEDEN[delen[4]]] = reeks

    # EC/pH per gift komt uit het watersysteem dat de vakken water geeft (nu: systeem 1).
    systeem = reeksen.get(min(reeksen)) if reeksen else {}
    beurten = [b for vak in sorted(meterstanden)
               for b in beurt_rijen(vak, meterstanden[vak], systeem.get("ec", []), systeem.get("ph", []),
                                    flows.get(vak, []))
               if oudste <= b["datum"] <= laatste]
    gift = []
    for vak, reeks in meterstanden.items():
        for dag, (liter, aantal) in gift_per_dag(reeks).items():
            if oudste <= dag <= laatste:
                van_dag = [b for b in beurten if b["vaknummer"] == vak and b["datum"] == dag]
                gift.append({"vaknummer": vak, "datum": dag, "liter_per_m2": liter, "beurten": aantal,
                             "ec": _rond(gewogen((b["ec"], b["liter_per_m2"]) for b in van_dag), 3),
                             "ph": _rond(gewogen((b["ph"], b["liter_per_m2"]) for b in van_dag), 2)})
    kwaliteit = [r for s in sorted(reeksen) for r in kwaliteit_rijen(reeksen[s], s, oudste, laatste)]
    for r in kwaliteit:
        van_dag = [b for b in beurten if b["datum"] == r["datum"]]
        r["ec_gift"] = _rond(gewogen((b["ec"], b["liter_per_m2"]) for b in van_dag), 3)
        r["ph_gift"] = _rond(gewogen((b["ph"], b["liter_per_m2"]) for b in van_dag), 2)
    gift.sort(key=lambda r: (r["datum"], r["vaknummer"]))
    beurten.sort(key=lambda b: (b["start"], b["vaknummer"]))
    return gift, kwaliteit, beurten


def _rond(waarde, decimalen):
    return round(waarde, decimalen) if waarde is not None else None

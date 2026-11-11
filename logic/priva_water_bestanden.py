"""
Gietbeurten per vak en EC/pH per watersysteem uit de Priva-bestanden op de NAS (map Priva), als vervanger van
de Priva-API (integrations/priva_water.py). Zelfde uitkomst en zelfde rekenwerk: de reeksen komen alleen uit
`<live>/water-<datum>.jsonl` in plaats van uit de API.

Welke punten (SCAD-codes, zie API-DOCUMENTATIE.md op de share):
- Kraan k (= vak k):
  - `M414.0N<p>R1.<k>V5` "tot.verbruik" (l/m², cumulatief): dezelfde oplopende meterstand als
    KRAAN.VERBRUIKM2 in de API. Hieruit volgen de beurten met integrations.priva_water.beurten_uit
    (reset, terugsprong en de pauze van 10 minuten zoals bij de API).
  - `M414.0N<p>R1.<k>V3` begintijd van de laatste beurt (uur:min, klok van de regelaar) en `M411.0N1R1.<k>V1`
    de toestand (RUST/START/GIET): daarmee wordt de start nauwkeuriger dan de minuutpeiling van de meterstand.
  - `M412.0N<p>R1.<k>V3` liters vandaag en `V6` de gemiddelde flow van de kraan vandaag (m³/uur): de flow van
    een beurt is de toename van de liters gedeeld door de toename van de draaitijd (liters / flow). De flow
    van het watersysteem kan niet: staan er twee kranen tegelijk open, dan is dat hun som.
  - `M412.0N<p>R1.<k>V1`/`V2` de EC/pH van de giften van vandaag (Priva's eigen gemiddelde, naar de liters):
    daaruit volgt de EC/pH van één beurt. Die wordt gebruikt als de EC/pH van het watersysteem tijdens de
    beurt er meer dan KRAAN_EC_GRENS van afwijkt (een sprong net bij de start, die de minuutpeiling mist).
  - Pagina p: tuin 3 kraan 1–20 op pagina 1, 21–39 op pagina 2; tuin 1 alles op pagina 1. Eerst 1, dan 2.
- Watersysteem s, scherm M430.0 (WATERSYSTEMEN/ACTUEEL) en M420.0 (DOSERING/ACTUEEL): gem EC, gem pH, gem ECa
  (EC van het uitgangswater), recept, ber EC en ber pH (de ingestelde waarde). De V-nummers
  verschillen per regelaar (tuin 3: EC op V6, tuin 1 op V5); ze worden daarom op omschrijving uit
  water-catalogus.csv gezocht.

Priva Office toont EC en pH op één decimaal, en zo staan ze ook in de bestanden (de API gaf er drie). Een
daggemiddelde wordt daardoor iets grover, het minimum en maximum per 0,1.

De bestanden noteren een waarde alleen bij een wijziging (plus een volledige stand bovenaan elk dagbestand).
Een dag volgens de API-indeling (lokale_dag, UTC+2) loopt over twee dagbestanden; lees daarom de dag ervoor en
erna mee.

Alleen inlezen en rekenen; het script priva_water_bestanden.py vergelijkt en slaat op.
Tests in tests/test_priva_water_bestanden.py.
"""
import csv
import json
import re
from datetime import datetime, timedelta, timezone

from integrations import priva_water as pw

# Omschrijving in water-catalogus.csv → grootheid, per scherm. "WATSYS - gem EC" (tuin 3, één systeem) of
# "WATSYS 1 - gem EC" (tuin 1, twee systemen).
SYSTEEM_PUNTEN = {
    ("M430.0", "gem EC"): "ec",
    ("M430.0", "gem pH"): "ph",
    ("M430.0", "gem ECa"): "ec_aanvoer",
    ("M430.0", "recept"): "recept",
    ("M420.0", "ber EC"): "ec_doel",
    ("M420.0", "ber pH"): "ph_doel",
}
_SYSTEEM_OMSCHRIJVING = re.compile(r"^WATSYS(?: (?P<s>\d+))? - (?P<naam>.+)$")

# Hoe ver de begintijd uit M414 (op de minuut) vóór de eerste gemeten toename mag liggen om als start te tellen.
START_VENSTER = timedelta(minutes=5)


def getal(waarde):
    """Een getal uit de bestanden, of None (leeg, '????', tekst)."""
    if isinstance(waarde, bool) or waarde is None:
        return None
    if isinstance(waarde, (int, float)):
        return float(waarde)
    try:
        return float(str(waarde).replace(",", "."))
    except ValueError:
        return None


def systeem_punten(catalogus_regels):
    """{(systeem, grootheid): scad} uit water-catalogus.csv (scad;iaddr;scherm;schermnaam;index;omschrijving;…)."""
    uit = {}
    for rij in csv.DictReader(catalogus_regels, delimiter=";"):
        m = _SYSTEEM_OMSCHRIJVING.match((rij.get("omschrijving") or "").strip())
        if not m:
            continue
        grootheid = SYSTEEM_PUNTEN.get((rij.get("scherm"), m["naam"]))
        if grootheid:
            uit.setdefault((int(m["s"] or 1), grootheid), rij["scad"])
    return uit


def kraan_sleutels(vak):
    """De sleutels die bij een kraan horen, op pagina 1 en 2 (de goede blijkt uit de bestanden)."""
    uit = {f"M411.0N1R1.{vak}V1"}
    for pagina in (1, 2):
        uit |= {f"M414.0N{pagina}R1.{vak}V{v}" for v in (3, 5)}
        uit |= {f"M412.0N{pagina}R1.{vak}V{v}" for v in (1, 2, 3, 6)}
    return uit


def lees_jsonl(regels, sleutels, tijdzones=None):
    """
    {scad: [(tijdstip UTC, waarde)]} voor de gevraagde sleutels uit water-<datum>.jsonl, op tijd gesorteerd.
    Regels die geen geldige JSON zijn (een half geschreven laatste regel) en storingsregels tellen niet.
    `tijdzones` (een dict, optioneel) krijgt {tijdstip UTC: tijdzone van het bestand} bij elke wisseling, voor
    tijdzone_op(): de regelaar toont zijn tijden in die tijdzone.
    """
    uit, vorige = {}, None
    for regel in regels:
        try:
            r = json.loads(regel)
            if r.get("soort") == "storing":
                continue
            lokaal = datetime.fromisoformat(r["t"])
            t = lokaal.astimezone(timezone.utc)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if tijdzones is not None and lokaal.tzinfo != vorige:
            tijdzones[t] = vorige = lokaal.tzinfo
        for k, v in (r.get("v") or {}).items():
            if k in sleutels:
                uit.setdefault(k, []).append((t, v))
    for reeks in uit.values():
        reeks.sort(key=lambda p: p[0])
    return uit


def tijdzone_op(tijdzones, t):
    """De tijdzone van de bestanden op tijdstip t (UTC), uit lees_jsonl(..., tijdzones); standaard UTC+1."""
    eerder = [tz for moment, tz in sorted(tijdzones.items()) if moment <= t]
    return eerder[-1] if eerder else (min(tijdzones.items())[1] if tijdzones else timezone(timedelta(hours=1)))


def voeg_samen(*delen):
    """Reeksen van meerdere dagbestanden samenvoegen (op tijd, dubbele tijdstippen eruit)."""
    uit = {}
    for deel in delen:
        for k, reeks in deel.items():
            uit.setdefault(k, []).extend(reeks)
    for k, reeks in uit.items():
        gezien, schoon = set(), []
        for t, v in sorted(reeks, key=lambda p: p[0]):
            if t not in gezien:
                gezien.add(t)
                schoon.append((t, v))
        uit[k] = schoon
    return uit


def getallen(reeks):
    """
    Alleen de getallen uit een reeks. De volledige stand bovenaan elk dagbestand blijft erin: zonder die regel
    heeft een dag met een constante waarde geen enkele meting.
    """
    return [(t, w) for t, w in ((t, getal(v)) for t, v in reeks or []) if w is not None]


def _kies(reeksen, vak, v, scherm="M414.0"):
    for pagina in (1, 2):
        reeks = reeksen.get(f"{scherm}N{pagina}R1.{vak}V{v}")
        if reeks:
            return reeks
    return []


# Na het einde van een beurt komt de stand van "kraan vandaag" nog één peiling later binnen.
NA_EINDE = timedelta(minutes=3)


def _stand(reeks, tot):
    """De laatste waarde met tijdstip ≤ tot, of None."""
    eerder = [w for t, w in reeks if t <= tot]
    return eerder[-1] if eerder else None


def beurt_flow(liters, flows, start, eind, volgende_start=None):
    """
    De flow van een beurt (m³/uur) uit "kraan vandaag": liters L en gemiddelde flow F (m³/uur) van de kraan
    sinds het begin van de dag. Draaitijd = L / F; flow van de beurt = toename L / toename draaitijd. Vóór de
    eerste beurt van de dag (of na de dagwissel) is de stand 0, dan is het gewoon F na de beurt.
    """
    grens = min(eind + NA_EINDE, volgende_start) if volgende_start else eind + NA_EINDE
    l1, f1 = _stand(liters, grens), _stand(flows, grens)
    if not l1 or not f1:
        return None
    l0, f0 = _stand(liters, start - timedelta(seconds=1)), _stand(flows, start - timedelta(seconds=1))
    if not l0 or not f0 or l0 > l1:                    # eerste beurt van de dag, of de teller is net op 0 gezet
        return f1
    duur = l1 / f1 - l0 / f0
    return (l1 - l0) / duur if duur > 0 else f1


def _begintijden(reeks):
    """[(tijdstip van de peiling UTC, 'uu:mm')] uit M414 V3, alleen bij een wijziging."""
    uit, vorige = [], None
    for t, v in reeks:
        if isinstance(v, str) and re.fullmatch(r"\d{1,2}:\d{2}", v.strip()) and v != vorige:
            uit.append((t, v.strip()))
        vorige = v
    return uit


def _giet_momenten(reeks):
    """Tijdstippen (UTC) waarop de kraan in GIET ging."""
    uit, vorige = [], None
    for t, v in reeks:
        if v == "GIET" and vorige != "GIET":
            uit.append(t)
        vorige = v
    return uit


def verfijn_start(begin, giet_momenten, begintijden, lokaal):
    """
    De start van een beurt: de begintijd die Priva zelf noteert (M414 V3, op de minuut, klok van de regelaar)
    als die tussen START_VENSTER vóór en het moment van de eerste gemeten toename valt; anders het moment dat
    de kraan op GIET ging, en anders de schatting uit de meterstand (`begin`).
    `lokaal` = de tijdzone van de bestanden (bijv. +01:00), waarin de regelaar zijn klok toont.
    """
    b_lok = begin.astimezone(lokaal)
    for t, hhmm in begintijden:
        if not begin - START_VENSTER <= t <= begin + START_VENSTER:
            continue
        uur, minuut = map(int, hhmm.split(":"))
        kandidaat = b_lok.replace(hour=uur, minute=minuut, second=0, microsecond=0)
        if kandidaat > b_lok + timedelta(minutes=1):
            kandidaat -= timedelta(days=1)
        if begin - START_VENSTER <= kandidaat.astimezone(timezone.utc) <= begin:
            return kandidaat.astimezone(timezone.utc)
    giet = [g for g in giet_momenten if begin - START_VENSTER <= g <= begin]
    return giet[-1] if giet else begin


# Wijkt de EC/pH van het watersysteem tijdens een beurt meer dan dit af van wat Priva voor de kraan noteert,
# dan geldt die van de kraan (vergeleken met de API, okt–nov 2026: zo vallen de uitschieters weg).
KRAAN_EC_GRENS = 0.15


def beurt_uit_dagcijfer(liters, waarden, start, eind, volgende_start=None):
    """
    De EC of pH van één beurt uit "kraan vandaag": het dagcijfer X is het gemiddelde van de giften naar de
    liters L, dus beurt = (X1·L1 − X0·L0) / (L1 − L0). Voor de eerste beurt van de dag gewoon X na de beurt.
    """
    grens = min(eind + NA_EINDE, volgende_start) if volgende_start else eind + NA_EINDE
    l1, x1 = _stand(liters, grens), _stand(waarden, grens)
    if not l1 or x1 is None:
        return None
    l0, x0 = _stand(liters, start - timedelta(seconds=1)), _stand(waarden, start - timedelta(seconds=1))
    if not l0 or x0 is None or l0 >= l1:
        return x1
    return (x1 * l1 - x0 * l0) / (l1 - l0)


def _kies_gemiddelde(systeem, kraan):
    """Die van het watersysteem, tenzij die van de kraan er meer dan KRAAN_EC_GRENS naast zit (of alleen één)."""
    if systeem is None or (kraan is not None and abs(systeem - kraan) > KRAAN_EC_GRENS):
        return kraan
    return systeem


def beurten_van_kraan(vak, reeksen, ec, ph, tijdzones):
    """
    De gietbeurten van één kraan: [{vaknummer, start, eind, datum, liter_per_m2, ec, ph, flow}], zoals
    integrations.priva_water.beurt_rijen. `ec`, `ph` = reeksen [(t, waarde)] van het watersysteem,
    `tijdzones` uit lees_jsonl.
    """
    meter = getallen(_kies(reeksen, vak, 5))
    begintijden = _begintijden(_kies(reeksen, vak, 3))
    giet = _giet_momenten(reeksen.get(f"M411.0N1R1.{vak}V1", []))
    liters, flows = getallen(_kies(reeksen, vak, 3, "M412.0")), getallen(_kies(reeksen, vak, 6, "M412.0"))
    kraan_ec, kraan_ph = getallen(_kies(reeksen, vak, 1, "M412.0")), getallen(_kies(reeksen, vak, 2, "M412.0"))
    ruw = pw.beurten_uit(meter)
    rijen = []
    for i, (begin, eind, liter) in enumerate(ruw):
        start = verfijn_start(begin, giet, begintijden, tijdzone_op(tijdzones, begin))
        volgende = ruw[i + 1][0] if i + 1 < len(ruw) else None
        f = beurt_flow(liters, flows, start, eind, volgende)
        e = _kies_gemiddelde(pw.gemiddelde_tussen(ec, start, eind) if ec else None,
                             beurt_uit_dagcijfer(liters, kraan_ec, start, eind, volgende))
        p = _kies_gemiddelde(pw.gemiddelde_tussen(ph, start, eind) if ph else None,
                             beurt_uit_dagcijfer(liters, kraan_ph, start, eind, volgende))
        rijen.append({"vaknummer": vak, "start": start, "eind": eind, "datum": pw.lokale_dag(start),
                      "liter_per_m2": round(liter, 2), "ec": _rond(e, 3), "ph": _rond(p, 2), "flow": _rond(f, 2)})
    return rijen


def gift_per_vak(vak, reeksen, beurten, vanaf, tot):
    """{dag: (l/m², aantal beurten, ec, ph)} uit de meterstand, met EC/pH van de beurten (naar de liters)."""
    uit = {}
    for dag, (liter, aantal) in pw.gift_per_dag(getallen(_kies(reeksen, vak, 5))).items():
        if vanaf <= dag <= tot:
            van_dag = [b for b in beurten if b["vaknummer"] == vak and b["datum"] == dag]
            uit[dag] = (liter, aantal, _rond(pw.gewogen((b["ec"], b["liter_per_m2"]) for b in van_dag), 3),
                        _rond(pw.gewogen((b["ph"], b["liter_per_m2"]) for b in van_dag), 2))
    return uit


def water_dagwaarden(reeksen, punten, vakken, systeem, vanaf, tot, tijdzones):
    """
    (gift, kwaliteit, beurten) in dezelfde vorm als integrations.priva_water.haal_water_dagwaarden, voor de
    dagen vanaf..tot (lokale_dag). `reeksen` = lees_jsonl over de dagbestanden (minstens een dag ervoor en erna),
    `punten` = systeem_punten uit de catalogus, `tijdzones` uit lees_jsonl.
    """
    def reeks(grootheid):
        scad = punten.get((systeem, grootheid))
        return getallen(reeksen.get(scad, [])) if scad else []

    sys_reeksen = {g: reeks(g) for g in ("ec", "ph", "ec_doel", "ph_doel", "ec_aanvoer")}
    # Geen recept actief toont Priva Office als '????': dat telt als "geen recept", zodat het vorige recept
    # daar ophoudt (net als 32767 bij de API).
    scad = punten.get((systeem, "recept"))
    sys_reeksen["recept"] = [(t, getal(v) if getal(v) is not None else pw.GEEN_RECEPT)
                             for t, v in reeksen.get(scad, [])] if scad else []
    beurten = [b for vak in sorted(vakken)
               for b in beurten_van_kraan(vak, reeksen, sys_reeksen["ec"], sys_reeksen["ph"], tijdzones)
               if vanaf <= b["datum"] <= tot]
    gift = [{"vaknummer": vak, "datum": dag, "liter_per_m2": liter, "beurten": aantal, "ec": ec, "ph": ph}
            for vak in sorted(vakken)
            for dag, (liter, aantal, ec, ph) in gift_per_vak(vak, reeksen, beurten, vanaf, tot).items()]
    kwaliteit = pw.kwaliteit_rijen(sys_reeksen, systeem, vanaf, tot)
    for r in kwaliteit:
        van_dag = [b for b in beurten if b["datum"] == r["datum"]]
        r["ec_gift"] = _rond(pw.gewogen((b["ec"], b["liter_per_m2"]) for b in van_dag), 3)
        r["ph_gift"] = _rond(pw.gewogen((b["ph"], b["liter_per_m2"]) for b in van_dag), 2)
    gift.sort(key=lambda r: (r["datum"], r["vaknummer"]))
    beurten.sort(key=lambda b: (b["start"], b["vaknummer"]))
    return gift, kwaliteit, beurten


def benodigde_sleutels(punten, vakken, systeem):
    """Alle SCAD-codes die water_dagwaarden nodig heeft (om de dagbestanden zuinig in te lezen)."""
    uit = {scad for (s, _), scad in punten.items() if s == systeem}
    for vak in vakken:
        uit |= kraan_sleutels(vak)
    return uit


def _rond(waarde, decimalen):
    return round(waarde, decimalen) if waarde is not None else None

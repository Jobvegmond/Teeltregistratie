"""
Het dagrapport (en op maandag het weekrapport): de controles op wat er in de teelt misging of opvalt, en de mail.

Een controle geeft signalen: {sleutel, soort, ernst, tuin, vak, afdeling, tekst}. De sleutel is elke dag dezelfde
voor hetzelfde probleem (zonder datum), zodat het rapport kan tellen hoe vaak het eerder kwam en feedback ("klopt
niet", "bewust zo") hetzelfde signaal een tijd kan dempen.

- soort: data, registratie, bespuiting, klimaat, water, plaag (SOORTEN, ook de volgorde in de mail);
- ernst: "fout" (de data of de registratie klopt niet), "let op" (iets doen of nakijken), "info".

De duiding (samenvatting en conclusies) schrijft Claude met de wiki erbij (geplande taak op de werklaptop); dit is
alleen het rekenwerk en de opmaak. dagrapport.py haalt de gegevens op en verstuurt. Tests in tests/test_dagrapport.py.
"""
from datetime import date, timedelta
from statistics import median

from config import (DIF_MIN, EC_BEREIK, FLORGIB_ACHTERSTAND_DAGEN, INWATER_DAGEN, PATS_STIJGING, PATS_STIJGING_MIN,
                    PH_BEREIK, PH_REGELING, RV_HOOG_UREN, STOOK_MAX, STOOKADVIES_MARGE)
from logic import mailopmaak as mo
from utils.format import LEEG, fmt_getal, fmt_kort, fmt_verschil

SOORTEN = ("data", "registratie", "bespuiting", "klimaat", "water", "plaag")
SOORT_NAAM = {"data": "Data", "registratie": "Registraties", "bespuiting": "Bespuitingen", "klimaat": "Klimaat",
              "water": "Water", "plaag": "Plagen"}
ERNST = ("fout", "let op", "info")
OORDELEN = ("klopt", "klopt niet", "bewust zo")
DEMPEN = {"klopt niet", "bewust zo"}          # feedback die hetzelfde signaal een tijd dempt
DAG = ("ma", "di", "wo", "do", "vr", "za", "zo")
RIZOLEX = "rizolex"
HERHAALD_MIDDEL = 3                           # zo vaak hetzelfde middel op een vak binnen 28 dagen: info
EINDMETING_DAGEN = 21                         # afgerond binnen zoveel dagen zonder lengte/gewicht: let op
NIET_AFGEROND_DAGEN = 7                       # laatste emmers zoveel dagen geleden, vak niet afgerond: let op
OOGSTRIJP_MARGE = 3                           # zoveel dagen na de prognose-oogst nog geen emmers: let op
STEK_DAGEN = (3, 21)                          # geplant tussen zoveel dagen geleden: stekbeoordeling verwacht
UITSCHIETER = (2.0, 3.0)                      # gift > 2× de mediaan van de afdeling én > mediaan + 3 l/m²


def _d(d):
    return f"{DAG[d.weekday()]} {d:%d-%m}" if d else "?"


def signaal(soort, ernst, tuin, tekst, sleutel, vak=None, afdeling=None):
    return {"sleutel": f"{soort}:{sleutel}:t{tuin}" + (f":v{vak}" if vak is not None else "")
            + (f":a{afdeling}" if afdeling is not None and vak is None else ""),
            "soort": soort, "ernst": ernst, "tuin": tuin, "vak": vak, "afdeling": afdeling, "tekst": tekst}


def bezet(bezetting, vak, dag, voor=INWATER_DAGEN):
    """Of een vak op `dag` een teelt heeft (of er binnen `voor` dagen een geplant wordt). bezetting: {vak: [(start,
    eind of None)]}; None = loopt nog (ook een concept: dat wordt nog geplant)."""
    return any(start - timedelta(days=voor) <= dag and (eind is None or dag <= eind)
               for start, eind in bezetting.get(vak, ()))


# --- Controles ---

def registraties(tuin, teelten, concepten, vandaag):
    """
    teelten: de lopende en de onlangs afgeronde teelten van de tuin als dicts met vak, afdeling, start, florgib,
    florgib_verwacht, prognose, plan, emmers, laatste_emmers, oogst, lengte_eind, gewicht, stek (beoordeeld);
    concepten: [(vak, startdatum)] uit de planning die nog geen teelt zijn.
    """
    uit = []
    for t in teelten:
        vak, oogst = t["vak"], t.get("oogst")
        if not oogst:
            fv = t.get("florgib_verwacht")
            if not t.get("florgib") and fv and (vandaag - fv).days > FLORGIB_ACHTERSTAND_DAGEN:
                uit.append(signaal("registratie", "let op", tuin, f"Florgib verwacht {_d(fv)}, nog niet geregistreerd "
                                   f"({(vandaag - fv).days} dagen)", "florgib", vak))
            prognose = t.get("prognose")
            if not t.get("emmers") and prognose and (vandaag - prognose).days > OOGSTRIJP_MARGE:
                uit.append(signaal("registratie", "let op", tuin, f"volgens het teeltmodel oogstrijp sinds "
                                   f"{_d(prognose)}, nog geen emmers geregistreerd", "oogst", vak))
            laatste = t.get("laatste_emmers")
            if laatste and (vandaag - laatste).days > NIET_AFGEROND_DAGEN:
                uit.append(signaal("registratie", "let op", tuin, f"laatste emmers {_d(laatste)}, vak nog niet "
                                   "afgerond", "afronden", vak))
            leeftijd = (vandaag - t["start"]).days
            if STEK_DAGEN[0] <= leeftijd <= STEK_DAGEN[1] and not t.get("stek"):
                uit.append(signaal("registratie", "info", tuin, f"geplant {_d(t['start'])}, nog geen "
                                   "stekbeoordeling", "stek", vak))
        elif (vandaag - oogst).days <= EINDMETING_DAGEN and (t.get("lengte_eind") is None or t.get("gewicht") is None):
            mist = " en ".join(n for n, k in (("lengte", "lengte_eind"), ("gewicht", "gewicht")) if t.get(k) is None)
            uit.append(signaal("registratie", "let op", tuin, f"afgerond {_d(oogst)} zonder {mist}", "eindmeting", vak))
    for vak, start in concepten:
        if (vandaag - start).days > 1:
            uit.append(signaal("registratie", "let op", tuin, f"concept stond op {_d(start)}, nog niet als teelt "
                               "gestart", "planten", vak))
    return uit


def bespuitingen(tuin, teelten, behandelingen, taken, bezetting, van, tot, vandaag):
    """
    behandelingen: [{vak, datum, middel, type}] van de laatste 28 dagen; taken: de werkplanning vanaf vandaag
    (logic.werkplanning.taken); bezetting: zie bezet(). [van, tot] = de periode van het rapport.
    """
    uit = []
    for taak in taken:      # planten dat achter loopt staat al bij de registraties
        if "loopt achter" in taak["toelichting"] and taak["soort"] == "cxds":
            uit.append(signaal("bespuiting", "let op", tuin, f"{taak['titel']} loopt achter ({taak['toelichting']})",
                               f"cxds-{taak['vakken'][0]}"))
    if not behandelingen:
        return uit
    per_vak = {}
    for b in behandelingen:
        per_vak.setdefault(b["vak"], []).append(b)
    for t in teelten:
        leeftijd = (vandaag - t["start"]).days
        if 2 <= leeftijd <= 14:
            rizolex = [b for b in per_vak.get(t["vak"], ()) if RIZOLEX in (b["middel"] or "").lower()
                       and -3 <= (b["datum"] - t["start"]).days <= 4]
            if not rizolex:
                uit.append(signaal("bespuiting", "let op", tuin, f"geplant {_d(t['start'])}, geen Rizolex "
                                   "geregistreerd", "rizolex", t["vak"]))
    leeg = {}
    for b in behandelingen:
        if van <= b["datum"] <= tot and not bezet(bezetting, b["vak"], b["datum"]):
            leeg.setdefault(b["vak"], set()).add(b["middel"] or "?")
    for vak, middelen in sorted(leeg.items()):
        uit.append(signaal("bespuiting", "fout", tuin, f"behandeling op een leeg vak ({', '.join(sorted(middelen))}): "
                           "verkeerd vak geregistreerd?", "leeg", vak))
    from logic.werkplanning import is_cxds
    herhaald = {}
    for vak, rijen in per_vak.items():
        tellen = {}
        for b in rijen:
            if b.get("type") == "gewasbescherming" and not is_cxds(b["middel"]) and (vandaag - b["datum"]).days <= 28:
                tellen.setdefault(b["middel"], set()).add(b["datum"])
        for middel, dagen in tellen.items():
            if len(dagen) >= HERHAALD_MIDDEL:
                herhaald.setdefault(middel, []).append(vak)
    for middel, vakken in sorted(herhaald.items()):
        uit.append(signaal("bespuiting", "info", tuin, f"{middel} {HERHAALD_MIDDEL}× of vaker in 4 weken op "
                           f"{_vakken(vakken)} (resistentie)", f"herhaald-{middel.lower()}"))
    return uit


def _vakken(vakken):
    vakken = sorted(vakken)
    return f"vak {vakken[0]}" if len(vakken) == 1 else "vak " + ", ".join(str(v) for v in vakken)


def klimaat(tuin, waarden, advies):
    """
    waarden: {"Afd. n": {sleutel: waarde}} (logic.tuin_overzicht.tabelwaarden, alleen de afdelingen);
    advies: {afdeling: {"c": stookadvies, "nu": huidige afwijking van de lichtlijn (14 dagen)}}.
    """
    dif = [(a, w["dif"]) for a, w in _afdelingen(waarden) if w.get("dif") is not None and w["dif"] < DIF_MIN]
    stook = [(a, w["stook_max"]) for a, w in _afdelingen(waarden)
             if w.get("stook_max") is not None and w["stook_max"] > STOOK_MAX]
    rv = [(a, w["rv_hoog"]) for a, w in _afdelingen(waarden)
          if w.get("rv_hoog") is not None and w["rv_hoog"] >= RV_HOOG_UREN[0]]
    afwijkend = [(a, x) for a, x in sorted(advies.items()) if x.get("c") is not None and x.get("nu") is not None
                 and abs(x["nu"] - x["c"]) >= STOOKADVIES_MARGE]
    uit = []
    if dif:
        uit.append(signaal("klimaat", "let op", tuin, f"DIF onder {fmt_kort(DIF_MIN, 1)} °C: " + _per_afd(
            dif, lambda x: fmt_getal(x, 1, "°C")), "dif"))
    if stook:
        uit.append(signaal("klimaat", "let op", tuin, f"stooklijn boven {fmt_kort(STOOK_MAX, 1)} °C: " + _per_afd(
            stook, lambda x: fmt_getal(x, 1, "°C")), "stook"))
    if rv:
        ernst = "let op" if max(x for _, x in rv) >= RV_HOOG_UREN[1] else "info"
        uit.append(signaal("klimaat", ernst, tuin, "uren per etmaal met RV ≥ 90 % (roest, schimmel): " + _per_afd(
            rv, lambda x: fmt_getal(x, 0, "u")), "rv"))
    if afwijkend:
        delen = [f"afd. {a} {fmt_verschil(x['nu'], 1)} (advies {fmt_verschil(x['c'], 1)})" for a, x in afwijkend]
        warmer = sum(x["c"] > x["nu"] for _, x in afwijkend)
        richting = ("warmer" if warmer == len(afwijkend) else "kouder" if not warmer else "anders") + " stoken"
        uit.append(signaal("klimaat", "let op", tuin, f"stooklijn t.o.v. de lichtlijn (14 dagen) wijkt af van het "
                           f"stookadvies, {richting}: " + "; ".join(delen), "stookadvies"))
    return uit


def _afdelingen(waarden):
    """[(afdeling, waarden)] van de kolommen "Afd. n", in de volgorde van de kolommen."""
    return [(int(k.split()[-1]), w) for k, w in waarden.items() if k.startswith("Afd. ")]


def _per_afd(lijst, opmaak):
    return ", ".join(f"afd. {a} {opmaak(x)}" for a, x in lijst)


def water(tuin, waarden, giften, bezetting):
    """
    waarden: zoals bij klimaat() (EC en pH van de gift per afdeling); giften: [{vak, afdeling, datum, liter}] in de
    periode, alleen giften > 0.
    """
    uit = []
    ec = [(a, w["ec"]) for a, w in _afdelingen(waarden)
          if w.get("ec") is not None and not EC_BEREIK[0] <= w["ec"] <= EC_BEREIK[1]]
    ph = [(a, w["ph"]) for a, w in _afdelingen(waarden)
          if w.get("ph") is not None and not PH_BEREIK[0] <= w["ph"] <= PH_BEREIK[1]]
    if ec:
        uit.append(signaal("water", "let op", tuin, f"EC van de gift buiten {fmt_kort(EC_BEREIK[0], 1)}–"
                           f"{fmt_kort(EC_BEREIK[1], 1)}: " + _per_afd(ec, lambda x: fmt_getal(x, 2)), "ec"))
    if ph and tuin in PH_REGELING:
        uit.append(signaal("water", "let op", tuin, f"pH van de gift buiten {fmt_kort(PH_BEREIK[0], 1)}–"
                           f"{fmt_kort(PH_BEREIK[1], 1)}: " + _per_afd(ph, lambda x: fmt_getal(x, 1)), "ph"))
    leeg = {}
    for g in giften:
        if not bezet(bezetting, g["vak"], g["datum"]):
            leeg.setdefault(g["vak"], []).append(g)
    for vak, rijen in sorted(leeg.items()):
        liter = sum(r["liter"] for r in rijen)
        uit.append(signaal("water", "let op", tuin, f"{fmt_getal(liter, 1)} l/m² gegeven op een leeg vak "
                           f"({', '.join(_d(r['datum']) for r in rijen)})", "leeg", vak))
    per_dag = {}
    for g in giften:
        per_dag.setdefault((g["datum"], g["afdeling"]), []).append(g)
    for (dag, afd), rijen in sorted(per_dag.items(), key=lambda x: (x[0][0], x[0][1] or 0)):
        if len(rijen) < 3:
            continue
        mid = median(r["liter"] for r in rijen)
        for r in rijen:
            inwateren = any(-INWATER_DAGEN <= (dag - start).days <= 10 for start, _ in bezetting.get(r["vak"], ()))
            if mid > 0 and r["liter"] > UITSCHIETER[0] * mid and r["liter"] > mid + UITSCHIETER[1] and not inwateren:
                uit.append(signaal("water", "info", tuin, f"{_d(dag)}: {fmt_getal(r['liter'], 1)} l/m², de rest van "
                                   f"afd. {afd} kreeg ± {fmt_getal(mid, 1)}", "uitschieter", r["vak"]))
    return uit


def plagen(tuin, dagtotalen, vandaag):
    """dagtotalen: logic.pats.dagtotalen over (minstens) de laatste 17 dagen."""
    uit = []
    per_insect = {}
    for r in dagtotalen:
        if r["datum"] < vandaag:
            per_insect.setdefault(r["insect"], []).append(r)
    for insect, rijen in per_insect.items():
        rijen.sort(key=lambda r: r["datum"])
        recent = rijen[-3:]
        eerder = [r for r in rijen[:-3] if (recent[0]["datum"] - r["datum"]).days <= 14]
        if len(recent) < 3 or not eerder:
            continue
        nu = sum(r["totaal"] for r in recent) / len(recent)
        toen = sum(r["totaal"] for r in eerder) / len(eerder)
        if nu >= PATS_STIJGING_MIN and nu >= PATS_STIJGING * max(toen, 0.5):
            uit.append(signaal("plaag", "let op", tuin, f"{insect} loopt op: {fmt_getal(nu, 1)} per teldag (laatste 3), "
                               f"was {fmt_getal(toen, 1)}", f"stijging-{insect.lower().replace(' ', '-')}"))
    return uit


def data_actueel(tuin, laatste, verwacht, vandaag):
    """laatste: {bron: laatste datum of None}; verwacht: {bron: (naam, hoogstens zoveel dagen oud)}."""
    uit = []
    for bron, (naam, dagen) in verwacht.items():
        d = laatste.get(bron)
        if d is None:
            uit.append(signaal("data", "fout", tuin, f"{naam}: niets in de database", bron))
        elif (vandaag - d).days > dagen:
            uit.append(signaal("data", "fout" if dagen <= 1 else "let op", tuin,
                               f"{naam} loopt achter: laatste {_d(d)} ({(vandaag - d).days} dagen)", bron))
    return uit


# --- Herhaling en feedback ---

def herhaling(signalen, eerder):
    """Zet bij elk signaal hoe vaak het in de vorige rapporten stond. eerder: {sleutel: aantal rapporten}."""
    for s in signalen:
        s["eerder"] = eerder.get(s["sleutel"], 0)
    return signalen


def demp(signalen, feedback):
    """
    Zet bij een signaal de laatste feedback die het dempt ("klopt niet", "bewust zo"). feedback: [{sleutels, oordeel,
    tekst, datum}] van de laatste FEEDBACK_DAGEN, nieuwste eerst; sleutels = de signalen van die conclusie.
    """
    for s in signalen:
        f = next((f for f in feedback if s["sleutel"] in (f.get("sleutels") or ()) and f["oordeel"] in DEMPEN), None)
        if f:
            s["feedback"] = {"oordeel": f["oordeel"], "tekst": f.get("tekst") or "", "datum": f["datum"]}
    return signalen


def sorteer(signalen):
    return sorted(signalen, key=lambda s: (ERNST.index(s["ernst"]), SOORTEN.index(s["soort"]), s["tuin"],
                                           s["vak"] or 0, s["afdeling"] or 0))


def _e(tekst):
    return mo.e(tekst)


# --- Reeksen per dag (voor de grafiekjes) ---

REEKS_DAGEN = {"dag": 14, "week": 28}
HELE_TUIN = "Hele tuin"


def dagenlijst(tot, aantal):
    """De `aantal` dagen die op `tot` eindigen, oplopend."""
    return [tot - timedelta(days=aantal - 1 - i) for i in range(aantal)]


def _gewogen_per_dag(waarden, dagen):
    """waarden: [(dag-tekst, m², waarde)] → [gewogen gemiddelde per dag of None], op de volgorde van `dagen`."""
    som, gewicht = {}, {}
    for dag, m2, w in waarden:
        som[dag] = som.get(dag, 0.0) + m2 * w
        gewicht[dag] = gewicht.get(dag, 0.0) + m2
    return [som[str(d)] / gewicht[str(d)] if gewicht.get(str(d)) else None for d in dagen]


def reeks_afwijking(klimaat, afd_m2, dagen):
    """
    De afwijking van de lichtlijn per dag (°C, positief = warmer gestookt), gewogen naar de m² van de afdeling.
    klimaat: DataFrame (van één tuin) met afdeling, datum, temp_24h en lichtsom; afd_m2: {afdeling: m²}.
    """
    from logic.lichtlijn import afwijking
    waarden = []
    for r in klimaat.itertuples():
        a = afwijking(r.temp_24h, r.lichtsom)
        m2 = afd_m2.get(int(r.afdeling), 0.0) if r.afdeling == r.afdeling and r.afdeling is not None else 0.0
        if a is not None and a == a and m2:
            waarden.append((str(r.datum)[:10], m2, a))
    return _gewogen_per_dag(waarden, dagen)


def reeks_temp(klimaat, afd_m2, dagen):
    """De etmaaltemperatuur per dag (°C), gewogen naar de m² van de afdeling; zelfde invoer als reeks_afwijking."""
    waarden = []
    for r in klimaat.itertuples():
        m2 = afd_m2.get(int(r.afdeling), 0.0) if r.afdeling == r.afdeling and r.afdeling is not None else 0.0
        if r.temp_24h is not None and r.temp_24h == r.temp_24h and m2:
            waarden.append((str(r.datum)[:10], m2, float(r.temp_24h)))
    return _gewogen_per_dag(waarden, dagen)


def reeks_verschil(eerste, tweede):
    """Per dag eerste − tweede; None als een van beide ontbreekt."""
    return [a - b if a is not None and b is not None else None for a, b in zip(eerste, tweede)]


def reeks_rv_uren(uur, afd_m2, dagen, grens=90, minimaal=12):
    """
    Uren per etmaal met RV ≥ `grens` %, gewogen naar de m² van de afdeling (zoals de kengetallen: geschaald naar 24
    gemeten uren); een dag met minder dan `minimaal` gemeten uren telt niet. uur: DataFrame met afdeling, tijdstip
    ("jjjj-mm-dd uu:mm") en rv.
    """
    if uur is None or uur.empty:
        return [None] * len(dagen)
    per = {}
    for r in uur.itertuples():
        if r.rv is None or r.rv != r.rv:
            continue
        d = per.setdefault((int(r.afdeling), str(r.tijdstip)[:10]), [0, 0])
        d[0] += r.rv >= grens
        d[1] += 1
    waarden = [(dag, afd_m2.get(afd, 0.0), hoog * 24 / n) for (afd, dag), (hoog, n) in per.items()
               if n >= minimaal and afd_m2.get(afd)]
    return _gewogen_per_dag(waarden, dagen)


def reeks_pats(dagtotalen, dagen):
    """{insect: [nieuw gevangen per dag of None als er die dag niet geteld is]} uit logic.pats.dagtotalen."""
    uit = {}
    for r in dagtotalen:
        uit.setdefault(r["insect"], {})[r["datum"]] = r["totaal"]
    return {insect: [per_dag.get(d) for d in dagen] for insect, per_dag in uit.items()}


# --- Mail ---

KENGETALLEN = [("temp", "Etmaal", 1, "°C"), ("temp_dag", "Dag", 1, "°C"), ("temp_nacht", "Nacht", 1, "°C"),
               ("dif", "DIF", 1, "°C"), ("afwijking", "Afw. lichtlijn", 1, "°C"), ("lichtsom", "Licht", 0, "J/cm²"),
               ("rv", "RV", 0, "%"), ("rv_hoog", "Uren RV ≥ 90", 0, ""), ("stook_max", "Stooklijn max", 1, "°C"),
               ("water", "Water", 1, "l/m²"), ("ec", "EC", 2, ""), ("ph", "pH", 1, ""), ("energie", "Energie", 1,
                                                                                         "MJ/m²")]
# De tegels per tuin in het dagrapport: (sleutel, kop, decimalen, eenheid).
TEGELS = [("temp", "Etmaal", 1, "°C"), ("afwijking", "Afw. lichtlijn", 1, "°C"), ("rv", "RV", 0, "%"),
          ("water", "Water", 1, "l/m²"), ("energie", "Energie", 1, "MJ/m²"), ("geoogst", "Geoogst", 0, "stelen")]
# Het weekrapport vergelijkt de tuinen en gaat niet over de lichtlijn of Agro4all (oogst).
VERGELIJK_NIET = {"afwijking"}
AFWIJKING_GRENS = 0.5            # |afwijking van de lichtlijn| die als te warm of te koud kleurt
ERNST_KLEUR = {"fout": mo.ROOD, "let op": mo.ORANJE, "info": mo.GRIJS}
# De conclusies van Claude als kaart: soort → (badge, kleur), de ernstigste eerst.
CONCLUSIE_SOORT = {"fout": ("Fout", mo.ROOD), "advies": ("Advies", mo.ORANJE), "opvallend": ("Opvallend", mo.BLAUW)}
MAX_KAARTEN = 5


def onderwerp(bundel):
    if bundel["soort"] == "week":
        return f"Weekrapport teelt week {bundel['week']} ({bundel['van']} t/m {bundel['tot']})"
    d = date.fromisoformat(bundel["van"])
    return f"Dagrapport teelt {_d(d)}-{d:%Y}"


def link(app_url, rapport, conclusie=None):
    if not app_url:
        return None
    return f"{app_url.rstrip('/')}/rapporten?rapport={rapport}" + (f"&conclusie={conclusie}" if conclusie else "")


def _maand_kort(d):
    return f"{d.day} {mo.MAAND[d.month - 1]}"


def _periode(bundel):
    van, tot = date.fromisoformat(bundel["van"]), date.fromisoformat(bundel["tot"])
    if bundel["soort"] == "week":
        return f"Week {bundel['week']} · {_maand_kort(van)} – {_maand_kort(tot)} {tot.year}"
    return f"{DAG[van.weekday()]} {_maand_kort(van)} {van.year}"


def _tegels_tuin(t, vergelijk):
    """De tegels van één tuin (dagrapport) uit de kengetallen van de hele tuin, met het verschil met de vorige dag."""
    nu = (t.get("kengetallen") or {}).get(HELE_TUIN) or {}
    toen = (t.get("kengetallen_vorige") or {}).get(HELE_TUIN) or {}
    rij = []
    for sleutel, naam, dec, eenheid in TEGELS:
        w = nu.get(sleutel)
        if w is None and sleutel != "geoogst":
            continue
        if sleutel == "afwijking":
            waarde = fmt_verschil(w, dec)
            toon = "let op" if w is not None and abs(w) >= AFWIJKING_GRENS else None
        else:
            waarde, toon = fmt_getal(w if w is not None else 0, dec), None
        verschil = mo.verschil_tekst(w if w is not None else 0, toen.get(sleutel), dec)
        rij.append({"label": naam, "waarde": waarde, "eenheid": eenheid, "toon": toon,
                    "sub": f"{mo.pijl(verschil)} {vergelijk}" if verschil else None})
    return rij


def _tegels_week(bundel):
    """De vier tegels van het weekrapport: etmaal per tuin, PATS-vangsten en het aantal aandachtspunten."""
    rij = []
    for t in bundel.get("tuinen", []):
        nu = (t.get("kengetallen") or {}).get(HELE_TUIN) or {}
        toen = (t.get("kengetallen_vorige") or {}).get(HELE_TUIN) or {}
        if nu.get("temp") is not None:
            verschil = mo.verschil_tekst(nu["temp"], toen.get("temp"), 1)
            rij.append({"label": f"Etmaal {t['naam'].lower()}", "waarde": fmt_getal(nu["temp"], 1), "eenheid": "°C",
                        "sub": f"{mo.pijl(verschil)} t.o.v. vorige week" if verschil else None})
    pats = [p for t in bundel.get("tuinen", []) for p in t.get("pats") or []]
    if pats:
        totaal, vorige = sum(p["totaal"] for p in pats), sum(p.get("vorige") or 0 for p in pats)
        verschil = mo.verschil_tekst(totaal, vorige, 0)
        rij.append({"label": "PATS-vangsten", "waarde": fmt_getal(totaal, 0),
                    "sub": f"{mo.pijl(verschil)} t.o.v. vorige week" if verschil else None})
    actief = [s for s in bundel["signalen"] if not s.get("feedback")]
    fouten, letop = sum(s["ernst"] == "fout" for s in actief), sum(s["ernst"] == "let op" for s in actief)
    rij.append({"label": "Aandachtspunten", "waarde": str(len(actief)),
                "toon": "fout" if fouten else "let op" if letop else None,
                "sub": f"{fouten} fout · {letop} let op"})
    return rij


def _grafieken(bundel):
    """
    De staafgrafiekjes uit de reeksen van de tuinen; leeg voor een bundel zonder reeksen. Het dagrapport toont de
    afwijking van de lichtlijn, het weekrapport het verschil in etmaaltemperatuur tussen de tuinen.
    """
    tuinen = [t for t in bundel.get("tuinen", []) if t.get("reeksen")]
    if not tuinen:
        return ""
    week = bundel["soort"] == "week"
    dagen = [date.fromisoformat(d) for d in tuinen[0]["reeksen"]["dagen"]]
    delen = [mo.sectiekop("Verloop")]

    def kleur_afwijking(v):
        return mo.ORANJE if v >= AFWIJKING_GRENS else mo.BLAUW if v <= -AFWIJKING_GRENS else mo.GROEN

    def kleur_rv(v):
        return mo.ROOD if v >= RV_HOOG_UREN[1] else mo.ORANJE if v >= RV_HOOG_UREN[0] else mo.GROEN

    if week and len(tuinen) == 2 and all(t["reeksen"].get("temp") for t in tuinen):
        eerste, tweede = tuinen
        delen.append(mo.staafgrafiek(
            f"Etmaaltemperatuur: {eerste['naam']} min {tweede['naam']}", dagen,
            [("Verschil", reeks_verschil(eerste["reeksen"]["temp"], tweede["reeksen"]["temp"]))],
            lambda v: mo.BLAUW if v < 0 else mo.ORANJE, "°C", 1, minimum=1.0, tweezijdig=True,
            uitleg=f"Boven de streep = {eerste['naam']} warmer dan {tweede['naam']}, eronder kouder."))
    elif not week:
        delen.append(mo.staafgrafiek(
            "Afwijking van de lichtlijn", dagen, [(t["naam"], t["reeksen"]["afwijking"]) for t in tuinen],
            kleur_afwijking, "°C", 1, minimum=1.0, tweezijdig=True,
            uitleg=f"Boven de streep = warmer gestookt dan de lichtlijn, eronder kouder; groen = binnen "
                   f"{fmt_kort(AFWIJKING_GRENS, 1)} °C."))
    delen.append(mo.staafgrafiek(
        "Uren per etmaal met RV ≥ 90 %", dagen, [(t["naam"], t["reeksen"]["rv_uren"]) for t in tuinen],
        kleur_rv, "uur", 0, minimum=24,
        uitleg=f"Kans op roest en schimmel; oranje vanaf {RV_HOOG_UREN[0]} uur, rood vanaf {RV_HOOG_UREN[1]} uur."))
    pats = [(f"{t['naam']} {insect.lower()}", waarden) for t in tuinen
            for insect, waarden in (t["reeksen"].get("pats") or {}).items() if any(waarden)]
    if pats:
        delen.append(mo.staafgrafiek(
            "Plaagdruk (PATS)", dagen, pats, lambda v: mo.BLAUW, "nieuw", 0, minimum=5,
            uitleg="Nieuw gevangen insecten per teldag; een korte grijze streep = die dag niet geteld."))
    return "".join(delen)


def _vergelijking(bundel):
    """Het weekrapport: de kengetallen van de hele tuin naast elkaar, met het verschil tussen de eerste en de tweede."""
    tuinen = bundel.get("tuinen", [])
    if len(tuinen) < 2:
        return ""
    eerste, tweede = tuinen[0], tuinen[1]
    rijen = []
    for s, naam, dec, eenheid in KENGETALLEN:
        if s in VERGELIJK_NIET:
            continue
        a = (eerste["kengetallen"].get(HELE_TUIN) or {}).get(s)
        b = (tweede["kengetallen"].get(HELE_TUIN) or {}).get(s)
        if a is None and b is None:
            continue
        rijen.append([f"{naam}{' ' + eenheid if eenheid else ''}", fmt_getal(a, dec), fmt_getal(b, dec),
                      fmt_verschil(a - b, dec) if a is not None and b is not None else LEEG])
    if not rijen:
        return ""
    return (mo.sectiekop(f"{eerste['naam']} naast {tweede['naam']}")
            + mo.tabel(["Kengetal", eerste["naam"], tweede["naam"], "Verschil"], rijen)
            + mo.voetnoot(f"Hele tuin, deze week; verschil = {eerste['naam']} min {tweede['naam']}."))


def _klimaat_per_dag(bundel):
    """Het weekrapport: per dag de etmaaltemperatuur en de uren RV ≥ 90 % van beide tuinen, kleurgecodeerd."""
    tuinen = [t for t in bundel.get("tuinen", []) if t.get("reeksen")]
    if len(tuinen) < 2 or not all(t["reeksen"].get("temp") for t in tuinen[:2]):
        return ""
    eerste, tweede = tuinen[:2]
    van, tot = date.fromisoformat(bundel["van"]), date.fromisoformat(bundel["tot"])
    dagen = [date.fromisoformat(d) for d in eerste["reeksen"]["dagen"]]
    verschil = reeks_verschil(eerste["reeksen"]["temp"], tweede["reeksen"]["temp"])

    def rv(w):
        if w is None:
            return LEEG
        kleur = mo.ROOD if w >= RV_HOOG_UREN[1] else mo.ORANJE if w >= RV_HOOG_UREN[0] else None
        return (fmt_getal(w, 0), kleur) if kleur else fmt_getal(w, 0)

    rijen = []
    for i, d in enumerate(dagen):
        if van <= d <= tot:
            rijen.append([f"{DAG[d.weekday()]} {d:%d-%m}", fmt_getal(eerste["reeksen"]["temp"][i], 1),
                          fmt_getal(tweede["reeksen"]["temp"][i], 1), fmt_verschil(verschil[i], 1),
                          rv(eerste["reeksen"]["rv_uren"][i]), rv(tweede["reeksen"]["rv_uren"][i])])
    if not rijen:
        return ""
    namen = (eerste["naam"], tweede["naam"])
    return (mo.sectiekop("Klimaat per dag")
            + mo.tabel(["Dag", f"Etmaal {namen[0]}", f"Etmaal {namen[1]}", "Verschil", f"RV-uren {namen[0]}",
                        f"RV-uren {namen[1]}"], rijen)
            + mo.voetnoot(f"Etmaaltemperatuur in °C; RV-uren = uren per etmaal met RV ≥ 90 % (oranje vanaf "
                          f"{RV_HOOG_UREN[0]}, rood vanaf {RV_HOOG_UREN[1]} uur)."))


def _afdelingstabellen(bundel):
    delen = []
    for t in bundel.get("tuinen", []):
        kolommen = t.get("kolommen") or []
        rijen = []
        for s, naam, dec, eenheid in KENGETALLEN:
            rij = [f"{naam}{' ' + eenheid if eenheid else ''}"]
            for k in kolommen:
                w = (t["kengetallen"].get(k) or {}).get(s)
                rij.append(fmt_verschil(w, dec) if s == "afwijking" else fmt_getal(w, dec))
            if any(r != "–" for r in rij[1:]):
                rijen.append(rij)
        if rijen:
            delen.append(f'<div style="font-weight:bold;font-size:14px;padding:10px 0 2px">{_e(t["naam"])}</div>'
                         + mo.tabel(["Kengetal"] + kolommen, rijen, klein=True))
    return mo.sectiekop("Per afdeling") + "".join(delen) if delen else ""


def _plaats(s):
    return f"T{s['tuin']}" + (f" vak {s['vak']}" if s["vak"] is not None else
                              f" afd. {s['afdeling']}" if s.get("afdeling") is not None else "")


def _kaarten(bundel, duiding, app_url):
    """
    De conclusies van Claude als kaart (de ernstigste eerst, hooguit MAX_KAARTEN).
    Geeft (html, [conclusies die als kaart staan], [conclusies die niet pasten]).
    """
    conclusies = duiding.get("conclusies") or []
    volgorde = list(CONCLUSIE_SOORT)
    gesorteerd = sorted(conclusies, key=lambda c: volgorde.index(c["soort"]) if c.get("soort") in volgorde else 9)
    getoond, rest = gesorteerd[:MAX_KAARTEN], gesorteerd[MAX_KAARTEN:]
    delen = []
    for c in getoond:
        naam, kleur = CONCLUSIE_SOORT.get(c.get("soort"), ("Info", mo.GRIJS))
        delen.append(mo.kaart(kleur, naam, c.get("titel", ""), c.get("tekst", ""),
                              plaats=f"Tuin {c['tuin']}" if c.get("tuin") else None, actie=c.get("actie"),
                              feedback_url=link(app_url, bundel["sleutel"], c["id"])))
    return "".join(delen), getoond, rest


def _controles(bundel, uitsluiten=(), extra=()):
    """
    De overige controles: de signalen die niet al in een kaart staan, per soort gegroepeerd en klein. `extra` zijn
    conclusies die niet als kaart pasten.
    """
    signalen = [s for s in bundel["signalen"] if s["sleutel"] not in uitsluiten]
    actief = [s for s in signalen if not s.get("feedback")]
    gedempt = [s for s in signalen if s.get("feedback")]
    groepen = []
    for soort in SOORTEN:
        items = [(ERNST_KLEUR[s["ernst"]], _plaats(s), s["tekst"] + (f" (ook {s['eerder']}× eerder)"
                                                                       if s.get("eerder") else ""))
                 for s in actief if s["soort"] == soort]
        if items:
            groepen.append((SOORT_NAAM[soort], items))
    if extra:
        groepen.append(("Meer conclusies", [(CONCLUSIE_SOORT.get(c.get("soort"), ("", mo.GRIJS))[1],
                                             f"Tuin {c['tuin']}" if c.get("tuin") else "",
                                             f"{c.get('titel', '')}: {c.get('tekst', '')}") for c in extra]))
    n = sum(len(i) for _, i in groepen)
    delen = [mo.sectiekop(f"Overige controles ({n})" if (uitsluiten or extra) else f"Controles ({n})")]
    delen.append(mo.regels(groepen) if groepen else mo.alinea("Niets gevonden."))
    if gedempt:
        delen.append(mo.voetnoot("Gedempt door feedback: " + "; ".join(
            f"{_e(_plaats(s))} {_e(s['tekst'])} ({_e(s['feedback']['oordeel'])})" for s in gedempt)))
    return "".join(delen)


def _samenvatting(duiding):
    if not duiding:
        return mo.voetnoot("Geen duiding van Claude ontvangen (stond de werklaptop uit?): alleen de cijfers en de "
                           "controles.")
    return mo.alinea(duiding.get("samenvatting", ""))


def bericht(bundel, duiding, app_url=None):
    """(onderwerp, html) van het rapport. duiding: {samenvatting, conclusies: [{id, soort, tuin, titel, tekst, actie}]} of None."""
    week = bundel["soort"] == "week"
    vergelijk = "t.o.v. vorige week" if week else "t.o.v. vorige dag"
    titel = "Weekrapport teelt" if week else "Dagrapport teelt"
    delen = []
    if week:
        delen.append(mo.tegels(_tegels_week(bundel)))
        delen.append(_vergelijking(bundel))        # de vergelijking tussen de tuinen staat bovenaan
    else:
        for t in bundel.get("tuinen", []):
            rij = _tegels_tuin(t, vergelijk)
            if rij:
                delen.append(mo.tegels(rij, label=t["naam"], breedte=3))
        delen.append(mo.voetnoot(f"Kleine regel onder een tegel = verschil {vergelijk}; cijfers voor de hele tuin."))
    delen.append(_samenvatting(duiding))
    uitsluiten, extra = set(), ()
    if duiding and (duiding.get("conclusies") or []):
        kaarten, getoond, rest = _kaarten(bundel, duiding, app_url)
        delen.append(mo.sectiekop("Aandachtspunten") + kaarten)
        uitsluiten = {s for c in getoond for s in c.get("signalen") or []}
        extra = rest
    if week:
        delen.append(_klimaat_per_dag(bundel))
    delen.append(_grafieken(bundel))
    if not week:
        delen.append(_afdelingstabellen(bundel))
    delen.append(_controles(bundel, uitsluiten, extra))
    url = link(app_url, bundel["sleutel"])
    gemaakt = bundel.get("gemaakt", "")[:16].replace("T", " ")
    delen.append(mo.voetnoot(
        f"Periode {bundel['van']} t/m {bundel['tot']}"
        + (f"; gemaakt op {gemaakt}" if gemaakt else "") + ". Cijfers en controles uit de teeltregistratie "
        + ("(Priva-bestanden, PATS)" if week else "(Priva-bestanden, Agro4all, PATS)")
        + "; de duiding is van Claude met de bedrijfswiki erbij."
        + (f' <a href="{_e(url)}" style="color:{mo.GROEN}">Open het rapport en geef feedback</a>.' if url else "")))
    return onderwerp(bundel), mo.omhulsel("".join(delen), kop=mo.kop(titel, _periode(bundel)),
                                          titel=onderwerp(bundel))


def tekst_bericht(bundel, duiding, app_url=None):
    """De tekstversie van de mail (voor mailprogramma's zonder HTML en als alternatief naast de HTML)."""
    week = bundel["soort"] == "week"
    uit = [("Weekrapport teelt" if week else "Dagrapport teelt") + " - " + _periode(bundel), ""]
    for t in bundel.get("tuinen", []):
        nu = (t.get("kengetallen") or {}).get(HELE_TUIN) or {}
        stukken = [f"{naam} {fmt_verschil(nu[s], dec) if s == 'afwijking' else fmt_getal(nu[s], dec)}"
                   f"{' ' + eenheid if eenheid else ''}"
                   for s, naam, dec, eenheid in (KENGETALLEN if week else TEGELS)
                   if nu.get(s) is not None and not (week and s in VERGELIJK_NIET)]
        uit.append(f"{t['naam']}: " + ", ".join(stukken))
    uit.append("")
    if duiding:
        uit += [duiding.get("samenvatting", ""), ""]
        for nr, c in enumerate(duiding.get("conclusies") or [], 1):
            uit.append(f"{nr}. {c.get('titel', '')}" + (f" (tuin {c['tuin']})" if c.get("tuin") else ""))
            uit.append(f"   {c.get('tekst', '')}")
            if c.get("actie"):
                uit.append(f"   Actie: {c['actie']}")
            url = link(app_url, bundel["sleutel"], c["id"])
            if url:
                uit.append(f"   Feedback: {url}")
        uit.append("")
    actief = [s for s in bundel["signalen"] if not s.get("feedback")]
    uit.append(f"Controles ({len(actief)}):")
    uit += [f"- {s['ernst']} · {SOORT_NAAM[s['soort']]} · {_plaats(s)}: {s['tekst']}" for s in actief] or ["- niets gevonden"]
    url = link(app_url, bundel["sleutel"])
    if url:
        uit += ["", f"Rapport en feedback: {url}"]
    return "\n".join(uit)

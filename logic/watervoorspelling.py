"""
Watervoorspelling per vak: voor vandaag per lopende teelt een advies "water", "twijfel" of "niet nodig", met een
korte reden. Een hulpmiddel voor de teler, geen sturing. Alleen rekenwerk; watervoorspelling.py haalt de gegevens
op (database en Open-Meteo). Tests in tests/test_watervoorspelling.py.

Werkwijze (verkenning tuin 3, november 2026):
- Het model leert op de historie van beide tuinen samen: dat toetste voor allebei beter dan alleen de eigen
  tuin (tuin 1 heeft pas historie sinds december 2025).
- Een gift is een dag met minstens MIN_GIFT l/m² op een vak (watergift_dag: Excel tot sept 2026, daarna Priva).
- De teeltleeftijd bepaalt het meest: dag 0–3 na planten (inregenen) 61 % kans op een gift, dag 4–7 35 %,
  week 2 24 %, week 3–4 17 %, daarna 1–2 %. Binnen een fase hangt het af van de straling sinds de vorige gift,
  het aantal dagen sinds die gift en de grootte ervan. Daarom per fase (FASEN) een eigen logistische regressie
  op die kenmerken (kenmerk_vector).
- Straling: de stralingssom per dag van de tuin (klimaatdata_dag, gemiddeld over de afdelingen) sinds de dag na
  de vorige gift t/m gisteren, plus de verwachting voor vandaag. De verwachting komt van Open-Meteo
  (kortegolfstraling in MJ/m²) en wordt omgerekend naar de Priva-schaal met een rechte lijn door de laatste
  IJK_DAGEN dagen (ijk_straling): de verhouding verschilt per seizoen (± 45 J/cm² per MJ/m² in de zomer van
  2025, ± 75–90 in de herfst), met een vaste voet van ± 200 J/cm².
- Advies: kans ≥ DREMPEL_WATER → water, ≥ DREMPEL_TWIJFEL → twijfel, anders niet nodig. Gekozen op het oude
  deel van de historie (tot juli 2026): "water" klopte daar in ± 75 % van de gevallen, water + twijfel vond
  ± 90 % van de giften.
- Een opmerking met categorie "Water" bij de teelt in de laatste OPMERKING_DAGEN dagen maakt van "niet nodig"
  een "twijfel" en staat in de reden.
- Wat niet in de data staat (droge plekken, voelen en kijken, ras en oogstfase) weegt de teler zelf; een eigen
  factor per vak maakte de terugtoets slechter, dus die zit er niet in.
"""
from datetime import timedelta

import numpy as np

MIN_GIFT = 1.0                      # l/m²: minder telt niet als gift (lekwater, meetruis)
# (eerste dag, laatste dag na planten, naam); de laatste fase loopt door tot het eind van de teelt.
FASEN = ((0, 3, "dag 0–3"), (4, 7, "dag 4–7"), (8, 14, "week 2"), (15, 28, "week 3–4"), (29, None, "na week 4"))
DREMPEL_WATER = 0.5
DREMPEL_TWIJFEL = 0.15
GEEN_ADVIES = {3: {1}}              # tuinnummer: vakken zonder advies (tuin 3 vak 1: waterteelt, proef)
IJK_DAGEN = 28                      # dagen voor het omrekenen van Open-Meteo naar de Priva-stralingssom
IJK_STANDAARD = (200.0, 60.0)       # J/cm² = a + b × MJ/m² als er te weinig dagen zijn om te ijken
OPMERKING_DAGEN = 7
MIN_RIJEN_FASE = 50                 # minder rijen of geen giften in een fase: alleen het gemiddelde van de fase
L2 = 1.0                            # regularisatie van de logistische regressie
ADVIEZEN = ("water", "twijfel", "niet nodig", "gegeven")
DAG = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def fase(leeftijd):
    """Index in FASEN voor een leeftijd in dagen na planten."""
    for i, (van, tot, _naam) in enumerate(FASEN):
        if leeftijd >= van and (tot is None or leeftijd <= tot):
            return i
    return 0


def giften(rijen, min_gift=MIN_GIFT):
    """{(vak, datum): liter per m²} uit dicts met vaknummer, datum (date) en liter_per_m2; alleen echte giften."""
    uit = {}
    for r in rijen:
        liter = r.get("liter_per_m2")
        if liter is not None and liter >= min_gift:
            uit[(int(r["vaknummer"]), r["datum"])] = float(liter)
    return uit


# --- Straling: Open-Meteo omrekenen naar de stralingssom van Priva ---

def ijk_straling(gemeten, openmeteo, tot, dagen=IJK_DAGEN):
    """
    (a, b) zodat stralingssom (J/cm²) ≈ a + b × Open-Meteo (MJ/m²), met de kleinste kwadraten over de laatste
    `dagen` dagen vóór `tot` waarop beide bekend zijn. Te weinig dagen: alle dagen vóór `tot`, anders IJK_STANDAARD.
    """
    paren = sorted((d, gemeten[d], openmeteo[d]) for d in gemeten
                   if d < tot and gemeten[d] is not None and openmeteo.get(d) is not None)
    recent = [p for p in paren if p[0] >= tot - timedelta(days=dagen)]
    for reeks in (recent, paren):
        if len(reeks) >= 10:
            x = np.array([p[2] for p in reeks], dtype=float)
            y = np.array([p[1] for p in reeks], dtype=float)
            if x.std() > 0:
                b, a = np.polyfit(x, y, 1)
                if b > 0:
                    return float(a), float(b)
    return IJK_STANDAARD


def omrekenen(mj, ijk):
    """Open-Meteo-straling (MJ/m²) naar de Priva-schaal (J/cm²)."""
    return None if mj is None else max(0.0, ijk[0] + ijk[1] * mj)


def verwachting_reeks(gemeten, openmeteo, dagen=IJK_DAGEN):
    """{datum: verwachte stralingssom} voor elke dag met Open-Meteo, elk met de ijking van de dagen ervóór
    (voor de terugtoets: zo had het advies die ochtend gerekend)."""
    return {d: omrekenen(mj, ijk_straling(gemeten, openmeteo, d, dagen)) for d, mj in openmeteo.items()
            if mj is not None}


# --- Kenmerken per vak-dag ---

def kenmerken(teelten, gift, straling, van, tot, verwachting=None, eerste_emmer=None):
    """
    Een dict per vak per dag van..tot waarop er een teelt loopt, met wat er die ochtend bekend is:
    vak, teelt, datum, leeftijd (dagen na planten), sinds (dagen sinds de vorige gift, None als er sinds het
    planten nog geen gift was), vorige_dag en vorige (l/m²) van die gift, S (straling sinds de dag na de vorige
    gift, of het planten, t/m gisteren), S_vandaag (verwachte straling vandaag), in_oogst (al emmers) en gift
    (l/m² die dag, 0 als er geen gift was).
    teelten: dicts met id, vak, start en eind (afgerond, of None); een teelt loopt tot de dag vóór de volgende
    start op hetzelfde vak. gift: {(vak, datum): l/m²} (giften()); straling: {datum: gemeten J/cm²};
    verwachting: {datum: verwachte J/cm²} voor S_vandaag (zonder: de gemeten straling van die dag) en voor dagen
    zonder meting; eerste_emmer: {teelt-id: eerste oogstdag}.
    """
    verwachting = verwachting or {}
    eerste_emmer = eerste_emmer or {}
    per_vak = {}
    for t in teelten:
        if t.get("start"):
            per_vak.setdefault(int(t["vak"]), []).append(t)
    uit = []
    for vak, lijst in per_vak.items():
        lijst.sort(key=lambda t: t["start"])
        for i, t in enumerate(lijst):
            eind = t.get("eind") or tot
            if i + 1 < len(lijst):
                eind = min(eind, lijst[i + 1]["start"] - timedelta(days=1))
            eind = min(eind, tot)
            emmer = eerste_emmer.get(t["id"])
            vorige_dag, vorige, som = None, None, 0.0
            dag = t["start"]
            while dag <= eind:
                gemeten = straling.get(dag)
                if dag >= van:
                    uit.append({
                        "vak": vak, "teelt": t["id"], "datum": dag, "leeftijd": (dag - t["start"]).days,
                        "sinds": (dag - vorige_dag).days if vorige_dag else None, "vorige_dag": vorige_dag,
                        "vorige": vorige, "S": som,
                        "S_vandaag": verwachting.get(dag) if verwachting.get(dag) is not None else gemeten,
                        "in_oogst": bool(emmer and emmer < dag), "gift": gift.get((vak, dag), 0.0)})
                if (vak, dag) in gift:
                    vorige_dag, vorige, som = dag, gift[(vak, dag)], 0.0
                else:
                    som += (gemeten if gemeten is not None else verwachting.get(dag)) or 0.0
                dag += timedelta(days=1)
    return sorted(uit, key=lambda k: (k["datum"], k["vak"]))


def straling_tot_nu(k):
    """Straling sinds de vorige gift t/m vandaag (verwacht)."""
    return k["S"] + (k["S_vandaag"] or 0.0)


def kenmerk_vector(k):
    """Invoer van de regressie: straling (en kwadraat), dagen sinds de gift (en kwadraat), grootte van de vorige
    gift, geen gift sinds planten, leeftijd in weken."""
    s = straling_tot_nu(k) / 1000
    sinds = k["sinds"] if k["sinds"] is not None else k["leeftijd"]
    return [s, s * s, sinds, sinds * sinds / 10, (k["vorige"] or 0.0) / 10, 1.0 if k["sinds"] is None else 0.0,
            k["leeftijd"] / 7]


# --- Model ---

def _logistisch(X, y, l2=L2, stappen=50):
    X = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X.shape[1])
    straf = l2 * np.eye(X.shape[1])
    straf[0, 0] = 0.0                                   # de constante niet bestraffen
    for _ in range(stappen):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        H = X.T @ (X * (p * (1 - p))[:, None]) + straf
        stap = np.linalg.solve(H, X.T @ (p - y) + straf @ w)
        w -= stap
        if np.abs(stap).max() < 1e-8:
            break
    return w.tolist()


def train(rijen):
    """
    Model uit vak-dagen met een bekende uitkomst (kenmerken()): per fase {"w": gewichten} of, met te weinig
    rijen of zonder giften/zonder droge dagen, {"kans": gemiddelde van de fase}.
    """
    model = {}
    totaal = [1.0 if r["gift"] >= MIN_GIFT else 0.0 for r in rijen]
    gemiddeld = sum(totaal) / len(totaal) if totaal else 0.0
    for i in range(len(FASEN)):
        groep = [r for r in rijen if fase(r["leeftijd"]) == i]
        y = np.array([1.0 if r["gift"] >= MIN_GIFT else 0.0 for r in groep])
        if len(groep) < MIN_RIJEN_FASE or y.sum() == 0 or y.sum() == len(y):
            model[i] = {"kans": float(y.mean()) if len(groep) else gemiddeld}
            continue
        model[i] = {"w": _logistisch(np.array([kenmerk_vector(r) for r in groep]), y)}
    return model


def kans(model, k):
    """Kans op een gift vandaag voor één vak-dag."""
    m = model[fase(k["leeftijd"])]
    if "kans" in m:
        return m["kans"]
    z = m["w"][0] + sum(w * x for w, x in zip(m["w"][1:], kenmerk_vector(k)))
    return float(1 / (1 + np.exp(-max(-30.0, min(30.0, z)))))


def advies(p, opmerking=False):
    """Advies bij een kans; een recente opmerking over water maakt van "niet nodig" een "twijfel"."""
    if p >= DREMPEL_WATER:
        return "water"
    if p >= DREMPEL_TWIJFEL or opmerking:
        return "twijfel"
    return "niet nodig"


def morgen(k, verwacht_morgen):
    """De vak-dag van morgen als er vandaag geen water komt."""
    m = dict(k)
    m.update(datum=k["datum"] + timedelta(days=1), leeftijd=k["leeftijd"] + 1, S=straling_tot_nu(k),
             sinds=k["sinds"] + 1 if k["sinds"] is not None else None, S_vandaag=verwacht_morgen)
    return m


# --- Tekst ---

def getal(x):
    """2800 → '2.800'."""
    return f"{x:,.0f}".replace(",", ".")


def liter(x):
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}".replace(".", ",")


def reden(k, p, opmerkingen=(), morgen_kans=None, vandaag_gegeven=None):
    """Korte reden, bijv. 'Vak 27 · 9 dagen na planten · 2.800 J/cm² straling sinds de gift van ma 02-11
    (15 l/m²) · kans 64 %'."""
    delen = [f"Vak {k['vak']}", f"{k['leeftijd']} {'dag' if k['leeftijd'] == 1 else 'dagen'} na planten"]
    if vandaag_gegeven:
        delen.append(f"vandaag al {liter(vandaag_gegeven)} l/m² gegeven")
        return " · ".join(delen)
    if k["vorige_dag"]:
        d = k["vorige_dag"]
        delen.append(f"{getal(straling_tot_nu(k))} J/cm² straling sinds de gift van {DAG[d.weekday()]} {d:%d-%m} "
                     f"({liter(k['vorige'])} l/m²)")
    else:
        delen.append(f"nog geen gift sinds het planten, {getal(straling_tot_nu(k))} J/cm² straling")
    if k.get("in_oogst"):
        delen.append("in de oogst")
    delen.append(f"kans {p * 100:.0f} %")
    if morgen_kans is not None and p < DREMPEL_WATER <= morgen_kans:
        delen.append("morgen waarschijnlijk wel")
    for datum, tekst in opmerkingen:
        delen.append(f"opmerking {datum:%d-%m}: {tekst}")
    return " · ".join(delen)


def vakken_tekst(vakken):
    """[25, 26, 27, 30] → '25–27, 30'."""
    reeksen = []
    for v in sorted(vakken):
        if reeksen and v == reeksen[-1][-1] + 1:
            reeksen[-1].append(v)
        else:
            reeksen.append([v])
    return ", ".join(f"{r[0]}–{r[-1]}" if len(r) > 2 else ", ".join(map(str, r)) for r in reeksen)


# --- Advies voor vandaag ---

def adviezen(model, vandaag_rijen, verwacht_morgen=None, opmerkingen=None, vandaag_gegeven=None):
    """
    [{vak, teelt, advies, kans, kans_morgen, reden, kenmerken}] voor de vak-dagen van vandaag, op vak.
    opmerkingen: {teelt-id: [(datum, tekst)]} met water-opmerkingen; vandaag_gegeven: {vak: l/m²} wat er
    vandaag al gegeven is (Priva): die vakken krijgen "gegeven".
    """
    opmerkingen = opmerkingen or {}
    vandaag_gegeven = vandaag_gegeven or {}
    uit = []
    for k in sorted(vandaag_rijen, key=lambda r: r["vak"]):
        p = kans(model, k)
        p_morgen = kans(model, morgen(k, verwacht_morgen)) if verwacht_morgen is not None else None
        recent = [(d, t) for d, t in opmerkingen.get(k["teelt"], ())
                  if timedelta(0) <= k["datum"] - d <= timedelta(days=OPMERKING_DAGEN)]
        gegeven = vandaag_gegeven.get(k["vak"])
        if gegeven and gegeven >= MIN_GIFT:
            a = "gegeven"
        else:
            gegeven = None
            a = advies(p, bool(recent))
        uit.append({"vak": k["vak"], "teelt": k["teelt"], "advies": a, "kans": p, "kans_morgen": p_morgen,
                    "reden": reden(k, p, recent, p_morgen, gegeven), "kenmerken": k})
    return uit


def _bereik(waarden, eenheid=""):
    lo, hi = min(waarden), max(waarden)
    return f"{lo}{eenheid}" if lo == hi else f"{lo}–{hi}{eenheid}"


def groepen(lijst):
    """
    Korte regels voor de Takenlijst: opeenvolgende vakken met hetzelfde advies en dezelfde vorige gift (meestal
    één planting) samen, bijv. 'vak 22–24 · 8–10 dagen na planten · 2.362 J/cm² sinds de gift van vr 30-10
    (10 l/m²) · kans 83–92 %'.
    """
    uit, groep, sleutel = [], [], None
    for a in sorted(lijst, key=lambda a: a["vak"]):
        k = a["kenmerken"]
        nieuw = (a["advies"], k["vorige_dag"], round(k["vorige"] or 0))
        if groep and (nieuw != sleutel or a["vak"] != groep[-1]["vak"] + 1):
            uit.append(groep)
            groep = []
        groep.append(a)
        sleutel = nieuw
    if groep:
        uit.append(groep)
    regels = []
    for g in uit:
        k = g[0]["kenmerken"]
        delen = [f"vak {vakken_tekst([a['vak'] for a in g])}",
                 _bereik([a["kenmerken"]["leeftijd"] for a in g]) + " dagen na planten"]
        if g[0]["advies"] == "gegeven":
            delen.append("vandaag al gegeven")
        elif k["vorige_dag"]:
            delen.append(f"{getal(straling_tot_nu(k))} J/cm² sinds de gift van {DAG[k['vorige_dag'].weekday()]} "
                         f"{k['vorige_dag']:%d-%m} ({liter(k['vorige'])} l/m²)")
        else:
            delen.append(f"nog geen gift sinds het planten ({getal(straling_tot_nu(k))} J/cm²)")
        if g[0]["advies"] != "gegeven":
            delen.append("kans " + _bereik([round(a["kans"] * 100) for a in g], " %"))
        if any(a["kans_morgen"] is not None and a["kans"] < DREMPEL_WATER <= a["kans_morgen"] for a in g):
            delen.append("morgen waarschijnlijk wel")
        regels.append(" · ".join(delen))
    return regels


def feed_items(lijst, datum, tuin_naam):
    """
    Items voor de Takenlijst ({id, date, title, area, note}): één item per dag met de vakken voor water en
    twijfel, of niets als er geen vak water of twijfel heeft. De id is per tuin en dag vast, zodat een afgevinkt
    item afgevinkt blijft.
    """
    water = [a for a in lijst if a["advies"] == "water"]
    twijfel = [a for a in lijst if a["advies"] == "twijfel"]
    if not water and not twijfel:
        return []
    titel = "Water: " + (f"vak {vakken_tekst([a['vak'] for a in water])}" if water else "geen vak zeker")
    if twijfel:
        titel += f" · twijfel: {vakken_tekst([a['vak'] for a in twijfel])}"
    note = (f"{tuin_naam} · advies, geen sturing. Water: " + "; ".join(groepen(water)) if water
            else f"{tuin_naam} · advies, geen sturing.")
    if twijfel:
        note += ". Twijfel: " + "; ".join(groepen(twijfel))
    opm = [o for a in water + twijfel for o in a["reden"].split(" · ") if o.startswith("opmerking ")]
    if opm:
        note += ". " + "; ".join(dict.fromkeys(opm))
    tuin = "".join(c for c in tuin_naam.lower() if c.isalnum())
    return [{"id": f"water-{tuin}-{datum}", "date": str(datum), "title": titel, "area": "werk", "note": note}]


# --- Terugtoets ---

def terugtoets(rijen, splits, extra=()):
    """
    Leren op de vak-dagen vóór `splits` (ook die van `extra`, bijv. de andere tuin), toetsen op de dagen van
    `rijen` vanaf `splits` (chronologisch). Geeft een dict met
    het aantal toetsdagen en giften, per advies het aantal en hoeveel daarvan een gift kregen, welk deel van de
    giften "water" / "water of twijfel" kreeg, en de vergelijking met blind gokken: dezelfde hoeveelheid
    "water" willekeurig verdeeld (raak = het giftpercentage) en "nooit water" (juist = de droge dagen).
    Per fase hetzelfde in "fasen".
    """
    oud = [r for r in rijen if r["datum"] < splits]
    nieuw = [r for r in rijen if r["datum"] >= splits]
    model = train(oud + [r for r in extra if r["datum"] < splits])

    def tel(groep):
        uitkomst = {a: [0, 0] for a in ADVIEZEN[:3]}
        for r in groep:
            a = advies(kans(model, r))
            uitkomst[a][0] += 1
            uitkomst[a][1] += r["gift"] >= MIN_GIFT
        n = len(groep)
        n_gift = sum(v[1] for v in uitkomst.values())
        w_n, w_raak = uitkomst["water"]
        t_raak = uitkomst["twijfel"][1]
        juist = w_raak + (uitkomst["twijfel"][0] - t_raak) + (uitkomst["niet nodig"][0] - uitkomst["niet nodig"][1])
        return {
            "dagen": n, "giften": n_gift, "giftkans": n_gift / n if n else 0.0,
            "advies": {a: {"aantal": v[0], "gift": v[1]} for a, v in uitkomst.items()},
            "water_raak": w_raak / w_n if w_n else None,
            "gevonden_water": w_raak / n_gift if n_gift else None,
            "gevonden_water_twijfel": (w_raak + t_raak) / n_gift if n_gift else None,
            "niet_nodig_mis": uitkomst["niet nodig"][1] / uitkomst["niet nodig"][0] if uitkomst["niet nodig"][0]
            else None,
            # "Juist" = water bij een gift en geen water (twijfel of niet nodig) zonder gift.
            "juist": juist / n if n else None,
            "blind_raak": n_gift / n if n else None,
            "blind_juist": 1 - n_gift / n if n else None,
        }

    uit = tel(nieuw)
    uit.update(oud_dagen=len(oud), van=min((r["datum"] for r in nieuw), default=None),
               tot=max((r["datum"] for r in nieuw), default=None),
               fasen={FASEN[i][2]: tel([r for r in nieuw if fase(r["leeftijd"]) == i]) for i in range(len(FASEN))})
    return uit

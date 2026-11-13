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
- Per planting: de teler geeft water per planting (de vakken van één plantweek in een aaneengesloten reeks,
  zoals de werkplanning), dus het advies is per planting, met de gemiddelde kans van de vakken (plantingen()).
- Advies: kans ≥ DREMPEL_WATER → water, ≥ DREMPEL_TWIJFEL → twijfel, anders niet nodig. Gekozen op het oude
  deel van de historie (tot juli 2026): "water" klopte daar in ± 75 % van de gevallen, water + twijfel vond
  ± 90 % van de giften.
- Een opmerking met categorie "Water" bij de teelt in de laatste OPMERKING_DAGEN dagen maakt van "niet nodig"
  een "twijfel" en staat in de reden.
- Florgib: vanaf de dag van de Florgib wordt er niet meer gegoten (historie: 1 gift op ± 3.200 vak-dagen na de
  Florgib, 1 op 384 Florgibdagen). Die vakken krijgen "na florgib" en geen advies. In het leren tellen die dagen
  wel mee: zonder toetste vooral tuin 1 slechter.
- Streefwater (bedrijfsomschrijving): ± 75 l/m² per teelt in de winter, ± 150 in de zomer, tot de Florgib.
  Daartussen naar de straling over de teelt (streef(); in de historie volgt het water de straling met r = 0,83),
  met de Florgib geregistreerd of geschat uit eerdere teelten rond dezelfde plantdatum (florgib_schattingen())
  en voor de dagen die nog komen de gemiddelde straling van andere jaren (klimatologie()). Het schema (VERLOOP)
  is hoe het water in de historie over de teelt verdeeld werd. Als extra kenmerk in de regressie voorspelde de
  achterstand niet beter wanneer er gegoten wordt; daarom twee regels per planting (streef_regel()): al op het
  streefwater → "water" wordt "twijfel"; STREEF_ACHTER l/m² of meer achter → "niet nodig" wordt "twijfel". In
  de toets (juli–november 2026) veranderde dat bijna niets (tuin 1: 4× water → twijfel, geen van die dagen gift).
- Verwachting vandaag: liefst die van Priva zelf (M4.1, integrations/priva_meteo.py), geijkt op de gemeten
  stralingssom (ijk_priva()): oktober–november 2026 ± 50–60 J/cm² ernaast tegen ± 105–115 voor Open-Meteo.
  Zonder Priva-bestanden of met minder dan PRIVA_MIN_DAGEN dagen: Open-Meteo.
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
PRIVA_IJK_DAGEN = 14                # dagen voor het ijken van de Priva-verwachting op de gemeten stralingssom
PRIVA_MIN_DAGEN = 5                 # minder dagen met verwachting én meting: Open-Meteo
OPMERKING_DAGEN = 7
MIN_RIJEN_FASE = 50                 # minder rijen of geen giften in een fase: alleen het gemiddelde van de fase
L2 = 1.0                            # regularisatie van de logistische regressie
# Streefwater per teelt (l/m², van planten tot de Florgib; bedrijfsomschrijving 2026): ± 75 in de winter en ± 150
# in de zomer. Daartussen naar de straling over de teelt (het water volgt de straling: r = 0,83 over 365
# teelten): een winterteelt krijgt tot de Florgib ± 13.000 J/cm², een zomerteelt ± 35.000.
STREEF_WINTER = (13000.0, 75.0)     # (J/cm² van planten tot Florgib, l/m²)
STREEF_ZOMER = (35000.0, 150.0)
# Hoe het water over de teelt verdeeld wordt (historie, mediaan): (deel van de tijd tot de Florgib, deel van het
# water). Het begin weegt zwaar: het inregenen.
VERLOOP = ((0.0, 0.0), (0.1, 0.19), (0.25, 0.38), (0.5, 0.64), (0.75, 0.87), (1.0, 1.0))
FLORGIB_STANDAARD = 35              # dagen na planten als er geen eerdere teelten zijn om op te schatten
FLORGIB_VENSTER = 21                # dagen rond dezelfde plantdatum (elk jaar) voor de schatting van de Florgib
KLIMAAT_VENSTER = 7                 # dagen rond dezelfde datum (elk jaar) voor de gemiddelde straling
SCHEMA_MARGE = 5.0                  # l/m²: kleiner verschil met het schema heet "op schema"
STREEF_ACHTER = 20.0                # l/m² achter op schema: "niet nodig" wordt "twijfel"
ADVIEZEN = ("water", "twijfel", "niet nodig", "gegeven", "na florgib")
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


# --- Straling: de verwachting van Priva ---

def ijk_priva(gemeten, priva, tot, dagen=PRIVA_IJK_DAGEN):
    """
    Factor f zodat stralingssom (binnen, J/cm²) ≈ f × de Priva-verwachting (buiten, J/cm²), met de kleinste
    kwadraten door 0 over de laatste `dagen` dagen vóór `tot` waarop beide bekend zijn; None bij te weinig dagen.
    De verwachting is buiten en ligt hoger dan de binnenstraling (glas, schermen): ruw zit hij er ± 100 J/cm²
    naast, geijkt ± 50 (oktober–november 2026, tegen ± 115 voor Open-Meteo).
    """
    paren = [(gemeten[d], priva[d]) for d in priva
             if tot - timedelta(days=dagen) <= d < tot and priva[d] and gemeten.get(d) is not None]
    if len(paren) < PRIVA_MIN_DAGEN:
        return None
    noemer = sum(p * p for _g, p in paren)
    return sum(g * p for g, p in paren) / noemer if noemer else None


# --- Streefwater en Florgib ---

def streef(lichtsom):
    """Streefwater (l/m²) tot de Florgib bij de straling over de teelt (J/cm²): tussen winter en zomer recht."""
    (l_w, w_w), (l_z, w_z) = STREEF_WINTER, STREEF_ZOMER
    deel = min(1.0, max(0.0, (lichtsom - l_w) / (l_z - l_w)))
    return w_w + deel * (w_z - w_w)


def verloop(deel):
    """Welk deel van het streefwater er bij `deel` van de tijd tot de Florgib gegeven is (VERLOOP)."""
    deel = min(1.0, max(0.0, deel))
    for (x0, y0), (x1, y1) in zip(VERLOOP, VERLOOP[1:]):
        if deel <= x1:
            return y0 + (y1 - y0) * (deel - x0) / (x1 - x0)
    return 1.0


def _dag_van_jaar(d):
    return min(d.timetuple().tm_yday, 365)


def klimatologie(straling, venster=KLIMAAT_VENSTER):
    """{dag van het jaar: gemiddelde stralingssom} over alle jaren, met `venster` dagen ervoor en erna."""
    per_dag = {}
    for d, s in straling.items():
        if s is not None:
            per_dag.setdefault(_dag_van_jaar(d), []).append(s)
    uit = {}
    for n in range(1, 366):
        waarden = [s for i in range(n - venster, n + venster + 1) for s in per_dag.get((i - 1) % 365 + 1, ())]
        if waarden:
            uit[n] = sum(waarden) / len(waarden)
    return uit


def florgib_schattingen(teelten, venster=FLORGIB_VENSTER):
    """
    {teelt-id: verwachte Florgib in dagen na planten}, zoals bekend bij het planten: de mediaan van de teelten
    die rond dezelfde plantdatum (elk jaar, ± `venster` dagen) geplant zijn en vóór dit planten hun Florgib
    hadden; zonder zulke teelten FLORGIB_STANDAARD.
    """
    klaar = [(t["start"], (t["florgib"] - t["start"]).days) for t in teelten
             if t.get("start") and t.get("florgib") and t["florgib"] > t["start"]]
    uit = {}
    for t in teelten:
        if not t.get("start"):
            continue
        n = _dag_van_jaar(t["start"])
        dagen = sorted(f for s, f in klaar if s + timedelta(days=f) < t["start"]
                       and min(abs(_dag_van_jaar(s) - n), 365 - abs(_dag_van_jaar(s) - n)) <= venster)
        uit[t["id"]] = dagen[len(dagen) // 2] if dagen else FLORGIB_STANDAARD
    return uit


def achterstand(k):
    """Hoeveel l/m² de teelt achter loopt op het schema naar het streefwater (negatief: voor), of None."""
    if not k.get("streef") or not k.get("florgib_dag"):
        return None
    return k["streef"] * verloop(k["leeftijd"] / k["florgib_dag"]) - k["gegeven"]


# --- Kenmerken per vak-dag ---

def kenmerken(teelten, gift, straling, van, tot, verwachting=None, eerste_emmer=None, klimaat=None,
              florgib_dagen=None):
    """
    Een dict per vak per dag van..tot waarop er een teelt loopt, met wat er die ochtend bekend is:
    vak, teelt, datum, leeftijd (dagen na planten), sinds (dagen sinds de vorige gift, None als er sinds het
    planten nog geen gift was), vorige_dag en vorige (l/m²) van die gift, S (straling sinds de dag na de vorige
    gift, of het planten, t/m gisteren), S_vandaag (verwachte straling vandaag), in_oogst (al emmers), gift
    (l/m² die dag, 0 als er geen gift was), gegeven (l/m² sinds het planten t/m gisteren), florgib (datum als die
    al geweest is), na_florgib (vanaf de dag van de Florgib: niet meer gieten), florgib_dag (de Florgib in dagen
    na planten: geregistreerd of geschat), lichtsom (straling van planten tot de Florgib: gemeten t/m gisteren,
    daarna het gemiddelde van andere jaren) en streef (l/m² tot de Florgib, streef()).
    teelten: dicts met id, vak, start, florgib (datum of None) en eind (afgerond, of None); een teelt loopt tot de
    dag vóór de volgende start op hetzelfde vak. gift: {(vak, datum): l/m²} (giften()); straling: {datum: gemeten
    J/cm²}; verwachting: {datum: verwachte J/cm²} voor S_vandaag (zonder: de gemeten straling van die dag) en voor
    dagen zonder meting; eerste_emmer: {teelt-id: eerste oogstdag}; klimaat: {dag van het jaar: J/cm²}
    (klimatologie(); zonder: geen streef); florgib_dagen: {teelt-id: geschatte Florgib in dagen}
    (florgib_schattingen(); zonder: FLORGIB_STANDAARD).
    """
    verwachting = verwachting or {}
    eerste_emmer = eerste_emmer or {}
    florgib_dagen = florgib_dagen or {}
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
            florgib = t.get("florgib")
            vorige_dag, vorige, som, gegeven, licht = None, None, 0.0, 0.0, 0.0
            dag = t["start"]
            while dag <= eind:
                gemeten = straling.get(dag)
                if dag >= van:
                    leeftijd = (dag - t["start"]).days
                    bekend = florgib if florgib and florgib <= dag else None
                    f_dag = ((bekend - t["start"]).days if bekend
                             else max(florgib_dagen.get(t["id"], FLORGIB_STANDAARD), leeftijd + 1))
                    lichtsom = streefwater = None
                    if klimaat:
                        lichtsom = licht + sum(klimaat.get(_dag_van_jaar(dag + timedelta(days=j)), 0.0)
                                               for j in range(max(0, f_dag - leeftijd)))
                        streefwater = streef(lichtsom)
                    uit.append({
                        "vak": vak, "teelt": t["id"], "datum": dag, "leeftijd": leeftijd,
                        "sinds": (dag - vorige_dag).days if vorige_dag else None, "vorige_dag": vorige_dag,
                        "vorige": vorige, "S": som,
                        "S_vandaag": verwachting.get(dag) if verwachting.get(dag) is not None else gemeten,
                        "in_oogst": bool(emmer and emmer < dag), "gift": gift.get((vak, dag), 0.0),
                        "gegeven": gegeven, "florgib": bekend, "na_florgib": bekend is not None,
                        "florgib_dag": f_dag, "lichtsom": lichtsom, "streef": streefwater})
                licht += (gemeten if gemeten is not None else verwachting.get(dag)) or 0.0
                if (vak, dag) in gift:
                    vorige_dag, vorige, som = dag, gift[(vak, dag)], 0.0
                    gegeven += gift[(vak, dag)]
                else:
                    som += (gemeten if gemeten is not None else verwachting.get(dag)) or 0.0
                dag += timedelta(days=1)
    return sorted(uit, key=lambda k: (k["datum"], k["vak"]))


def straling_tot_nu(k):
    """Straling sinds de vorige gift t/m vandaag (verwacht)."""
    return k["S"] + (k["S_vandaag"] or 0.0)


def kenmerk_vector(k):
    """Invoer van de regressie: straling (en kwadraat), dagen sinds de gift (en kwadraat), grootte van de vorige
    gift, geen gift sinds planten, leeftijd in weken. (De achterstand op het streefwater als extra kenmerk
    toetste niet beter; die werkt via de regels in adviezen().)"""
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
    rijen of zonder giften/zonder droge dagen, {"kans": gemiddelde van de fase}; met "liter": de mediaan van de
    giften in die fase (hoeveel er meestal gegeven wordt). De vak-dagen na de Florgib tellen mee: zonder die dagen
    toetste vooral tuin 1 slechter (ze leren het model dat er laat in de teelt weinig gegoten wordt).
    """
    model = {}
    totaal = [1.0 if r["gift"] >= MIN_GIFT else 0.0 for r in rijen]
    gemiddeld = sum(totaal) / len(totaal) if totaal else 0.0
    for i in range(len(FASEN)):
        groep = [r for r in rijen if fase(r["leeftijd"]) == i]
        y = np.array([1.0 if r["gift"] >= MIN_GIFT else 0.0 for r in groep])
        liters = [r["gift"] for r in groep if r["gift"] >= MIN_GIFT]
        maat = {"liter": float(np.median(liters))} if liters else {}
        if len(groep) < MIN_RIJEN_FASE or y.sum() == 0 or y.sum() == len(y):
            model[i] = {"kans": float(y.mean()) if len(groep) else gemiddeld, **maat}
            continue
        model[i] = {"w": _logistisch(np.array([kenmerk_vector(r) for r in groep]), y), **maat}
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


def streef_tekst(ks):
    """'62 van ± 110 l/m² gegeven (streef tot de Florgib ± do 19-11) · 8 l/m² achter op schema' voor de
    vak-dagen van één planting (gemiddeld)."""
    n = len(ks)
    gegeven, doel = sum(k["gegeven"] for k in ks) / n, sum(k["streef"] for k in ks) / n
    achter = sum(achterstand(k) for k in ks) / n
    florgib = ks[0]["datum"] + timedelta(days=round(sum(k["florgib_dag"] - k["leeftijd"] for k in ks) / n))
    tekst = f"{liter(round(gegeven))} van ± {liter(round(doel / 5) * 5)} l/m² gegeven (streef tot de Florgib ± {_dagtekst(florgib)})"
    if achter >= SCHEMA_MARGE:
        return tekst + f" · {liter(round(achter))} l/m² achter op schema"
    if achter <= -SCHEMA_MARGE:
        return tekst + f" · {liter(round(-achter))} l/m² voor op schema"
    return tekst + " · op schema"


def reden(k, p, opmerkingen=(), morgen_kans=None, vandaag_gegeven=None):
    """Korte reden, bijv. 'Vak 27 · 9 dagen na planten · 2.800 J/cm² straling sinds de gift van ma 02-11
    (15 l/m²) · 62 van ± 110 l/m² gegeven (…) · kans 64 %'."""
    delen = [f"Vak {k['vak']}", f"{k['leeftijd']} {'dag' if k['leeftijd'] == 1 else 'dagen'} na planten"]
    if k.get("na_florgib"):
        delen.append(f"Florgib op {_dagtekst(k['florgib'])}: daarna niet meer gieten")
        return " · ".join(delen)
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
    if k.get("streef"):
        delen.append(streef_tekst([k]))
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


# --- Plantingen ---

def plantingen(rijen):
    """
    {vak: naam van de planting} voor de vak-dagen van één dag: de vakken met dezelfde plantweek (ISO, uit de
    plantdatum = datum − leeftijd) in aaneengesloten reeksen, zoals de werkplanning (bijv. '17–21'). De teler
    geeft per planting water, dus het advies is per planting.
    """
    per_week = {}
    for k in rijen:
        start = k["datum"] - timedelta(days=k["leeftijd"])
        per_week.setdefault(start.isocalendar()[:2], []).append(k["vak"])
    uit = {}
    for vakken in per_week.values():
        reeks = []
        for v in sorted(vakken) + [None]:
            if reeks and (v is None or v != reeks[-1] + 1):
                naam = f"{reeks[0]}–{reeks[-1]}" if len(reeks) > 1 else str(reeks[0])
                uit.update({x: naam for x in reeks})
                reeks = []
            if v is not None:
                reeks.append(v)
    return uit


# --- Advies voor vandaag ---

def adviezen(model, vandaag_rijen, verwacht_morgen=None, opmerkingen=None, vandaag_gegeven=None):
    """
    [{vak, teelt, planting, advies, kans, kans_vak, kans_morgen, liter, reden, kenmerken}] voor de vak-dagen van
    vandaag, op vak. Het advies is per planting (plantingen()): de gemiddelde kans van de vakken ervan ("kans",
    ook "kans_morgen"); de eigen kans van het vak staat in "kans_vak" en in de reden. "liter": hoeveel er in die
    teeltfase meestal gegeven wordt. opmerkingen: {teelt-id: [(datum, tekst)]} met water-opmerkingen (één bij
    een vak maakt van "niet nodig" voor de hele planting een "twijfel"); vandaag_gegeven: {vak: l/m²} wat er
    vandaag al gegeven is (Priva): die vakken krijgen "gegeven". Vakken vanaf de dag van de Florgib krijgen
    "na florgib": daarna wordt er niet meer gegoten.
    Streefwater (per planting, gemiddeld over de vakken): is het streefwater tot de Florgib al gegeven, dan wordt
    "water" een "twijfel"; loopt de planting STREEF_ACHTER l/m² of meer achter op het schema, dan wordt "niet
    nodig" een "twijfel". De reden staat in "streef_regel".
    """
    opmerkingen = opmerkingen or {}
    vandaag_gegeven = vandaag_gegeven or {}
    namen = plantingen(vandaag_rijen)
    uit = []
    for k in sorted(vandaag_rijen, key=lambda r: r["vak"]):
        p = kans(model, k)
        p_morgen = kans(model, morgen(k, verwacht_morgen)) if verwacht_morgen is not None else None
        recent = [(d, t) for d, t in opmerkingen.get(k["teelt"], ())
                  if timedelta(0) <= k["datum"] - d <= timedelta(days=OPMERKING_DAGEN)]
        gegeven = vandaag_gegeven.get(k["vak"])
        gegeven = gegeven if gegeven and gegeven >= MIN_GIFT else None
        uit.append({"vak": k["vak"], "teelt": k["teelt"], "planting": namen[k["vak"]],
                    "advies": "na florgib" if k.get("na_florgib") else "gegeven" if gegeven else None, "kans": p, "kans_vak": p,
                    "kans_morgen": p_morgen, "kans_morgen_vak": p_morgen, "opmerking": bool(recent),
                    "liter": model[fase(k["leeftijd"])].get("liter"),
                    "reden": reden(k, p, recent, p_morgen, gegeven), "kenmerken": k})
    for naam in dict.fromkeys(a["planting"] for a in uit):
        groep = [a for a in uit if a["planting"] == naam and a["advies"] is None]
        if not groep:
            continue
        p = sum(a["kans_vak"] for a in groep) / len(groep)
        morgens = [a["kans_morgen_vak"] for a in groep if a["kans_morgen_vak"] is not None]
        p_morgen = sum(morgens) / len(morgens) if morgens else None
        a_pl = advies(p, any(a["opmerking"] for a in groep))
        a_pl, regel = streef_regel(a_pl, [a["kenmerken"] for a in groep])
        for a in groep:
            a.update(advies=a_pl, kans=p, kans_morgen=p_morgen, streef_regel=regel)
    return uit


def streef_regel(adv, ks):
    """(advies, reden of None) na de regels voor het streefwater, voor de vak-dagen van één planting."""
    if not ks or not all(k.get("streef") for k in ks):
        return adv, None
    n = len(ks)
    if adv == "water" and sum(k["gegeven"] for k in ks) / n >= sum(k["streef"] for k in ks) / n:
        return "twijfel", "streefwater al gegeven"
    if adv == "niet nodig" and sum(achterstand(k) for k in ks) / n >= STREEF_ACHTER:
        return "twijfel", "ver achter op het schema naar het streefwater"
    return adv, None


def _bereik(waarden, eenheid=""):
    lo, hi = min(waarden), max(waarden)
    return f"{lo}{eenheid}" if lo == hi else f"{lo}–{hi}{eenheid}"


def _dagtekst(d):
    return f"{DAG[d.weekday()]} {d:%d-%m}"


def groepen(lijst):
    """
    Een korte regel per planting (en advies), bijv. 'vak 22–24 · 8–10 dagen na planten · 2.362 J/cm² sinds de
    gift van vr 30-10 (10 l/m²) · kans 88 % (per vak 83–92 %) · meestal ± 15 l/m²'. Voor de Takenlijst, de
    notificaties en de tekst van watervoorspelling.py.
    """
    per = {}
    for a in sorted(lijst, key=lambda a: a["vak"]):
        per.setdefault((a.get("planting") or vakken_tekst([a["vak"]]), a["advies"]), []).append(a)
    regels = []
    for (naam, adv), g in sorted(per.items(), key=lambda x: min(a["vak"] for a in x[1])):
        ks = [a["kenmerken"] for a in g]
        delen = [f"vak {naam}", _bereik([k["leeftijd"] for k in ks]) + " dagen na planten"]
        if adv == "gegeven":
            delen.append("vandaag al gegeven")
            regels.append(" · ".join(delen))
            continue
        if adv == "na florgib":
            data = sorted({k["florgib"] for k in ks})
            delen.append(f"Florgib op {' en '.join(_dagtekst(d) for d in data)}: daarna niet meer gieten")
            regels.append(" · ".join(delen))
            continue
        straling = [straling_tot_nu(k) for k in ks]
        st = (getal(min(straling)) if max(straling) - min(straling) < 50
              else f"{getal(min(straling))}–{getal(max(straling))}")
        met_gift = [k for k in ks if k["vorige_dag"]]
        if met_gift:
            dagen = sorted({k["vorige_dag"] for k in met_gift})
            liters = sorted({round(k["vorige"], 1) for k in met_gift})
            l_tekst = liter(liters[0]) if len(liters) == 1 else f"{liter(liters[0])}–{liter(liters[-1])}"
            delen.append(f"{st} J/cm² sinds de gift van {' en '.join(_dagtekst(d) for d in dagen)} ({l_tekst} l/m²)")
            if len(met_gift) < len(ks):
                delen.append("deels nog geen gift sinds het planten")
        else:
            delen.append(f"nog geen gift sinds het planten ({st} J/cm²)")
        if all(k.get("streef") for k in ks):
            delen.append(streef_tekst(ks))
        kans_vak = [round(a.get("kans_vak", a["kans"]) * 100) for a in g]
        delen.append(f"kans {g[0]['kans'] * 100:.0f} %"
                     + (f" (per vak {_bereik(kans_vak, ' %')})" if len(set(kans_vak)) > 1 else ""))
        regel = next((a.get("streef_regel") for a in g if a.get("streef_regel")), None)
        if regel:
            delen.append(f"{regel}, daarom {adv}")
        if adv in ("water", "twijfel"):
            maat = sorted(a["liter"] for a in g if a.get("liter"))
            if maat:
                delen.append(f"meestal ± {liter(maat[len(maat) // 2])} l/m²")
        if adv != "water" and g[0].get("kans_morgen") is not None and g[0]["kans_morgen"] >= DREMPEL_WATER:
            delen.append("morgen waarschijnlijk wel")
        regels.append(" · ".join(delen))
    return regels


def planting_namen(lijst):
    """'22–24, 25–28': de plantingen in een lijst adviezen, op volgorde."""
    namen = {}
    for a in sorted(lijst, key=lambda a: a["vak"]):
        namen.setdefault(a.get("planting") or vakken_tekst([a["vak"]]), None)
    return ", ".join(namen)


def feed_items(lijst, datum, tuin_naam):
    """
    Items voor de Takenlijst ({id, date, title, area, note, soort, vakken}): één los item per planting met water
    of twijfel, eerst water, dan op vak; geen item voor "niet nodig" of "gegeven". Bijv. title "Water · vak
    22–24 · 87 %" (de kans van de planting: het gemiddelde van de vakken), note "8–10 dagen na planten · 2.362
    J/cm² sinds de gift van vr 30-10 (10 l/m²) · kans 87 % · …".
    De id is per tuin, dag en planting vast ("water-tuin3-2026-11-05-22-24"), zodat vinkjes en feedback bij het
    item blijven als het advies die dag opnieuw wordt gezet.
    """
    tuin = "".join(c for c in tuin_naam.lower() if c.isalnum())
    uit = []
    for soort, kop in (("water", "Water"), ("twijfel", "Twijfel")):
        per = {}
        for a in sorted((a for a in lijst if a["advies"] == soort), key=lambda a: a["vak"]):
            per.setdefault(a.get("planting") or str(a["vak"]), []).append(a)
        for naam, groep in per.items():
            regel = groepen(groep)[0]
            note = regel.split(" · ", 1)[1] if " · " in regel else regel          # zonder "vak …" vooraan
            opm = [o for a in groep for o in a["reden"].split(" · ") if o.startswith("opmerking ")]
            if opm:
                note += " · " + " · ".join(dict.fromkeys(opm))
            vakken = [a["vak"] for a in groep]
            uit.append({"id": f"water-{tuin}-{datum}-{min(vakken)}-{max(vakken)}", "date": str(datum),
                        "title": f"{kop} · vak {naam} · {groep[0]['kans'] * 100:.0f} %", "area": "werk", "note": f"{tuin_naam} · {note}",
                        "soort": soort, "vakken": vakken})
    return uit


# --- Terugtoets ---

def _tel(paren):
    """Telling voor de terugtoets uit (kans, gift ja/nee)-paren."""
    uitkomst = {a: [0, 0] for a in ADVIEZEN[:3]}
    for p, y in paren:
        a = advies(p)
        uitkomst[a][0] += 1
        uitkomst[a][1] += bool(y)
    n = len(paren)
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


def planting_dagen(rijen, kansen):
    """
    [(kans, water gekregen, leeftijd)] per planting per dag: de gemiddelde kans van de vakken, of de planting die
    dag water kreeg (minstens de helft van de vakken) en de leeftijd van het oudste vak. kansen: één per rij.
    """
    per_dag = {}
    for r, p in zip(rijen, kansen):
        per_dag.setdefault(r["datum"], []).append((r, p))
    uit = []
    for paren in per_dag.values():
        namen = plantingen([r for r, _p in paren])
        per = {}
        for r, p in paren:
            per.setdefault(namen[r["vak"]], []).append((r, p))
        for groep in per.values():
            n = len(groep)
            uit.append((sum(p for _r, p in groep) / n, sum(r["gift"] >= MIN_GIFT for r, _p in groep) * 2 >= n,
                        max(r["leeftijd"] for r, _p in groep)))
    return uit


def terugtoets(rijen, splits, extra=()):
    """
    Leren op de vak-dagen vóór `splits` (ook die van `extra`, bijv. de andere tuin), toetsen op de dagen van
    `rijen` vanaf `splits` (chronologisch). Per planting per dag (zoals het advies: de gemiddelde kans van de
    vakken; "water gekregen" = minstens de helft van de vakken) het aantal toetsdagen en giften, per advies het
    aantal en hoeveel daarvan water kregen, welk deel van de giften "water" / "water of twijfel" kreeg, en de
    vergelijking met blind gokken: dezelfde hoeveelheid "water" willekeurig verdeeld (raak = het giftpercentage)
    en "nooit water" (juist = de droge dagen). Per fase hetzelfde in "fasen", en per vak in "per_vak". De regels
    voor het streefwater (adviezen()) zitten er niet in. "na_florgib": vak-dagen vanaf de Florgib in de toetsperiode
    (niet getoetst) en hoeveel daarvan toch water kregen.
    """
    oud = [r for r in rijen if r["datum"] < splits]
    # Getoetst zonder de dagen vanaf de Florgib: die krijgen vast "na florgib" (in de historie 1 gift op ± 3.200).
    nieuw = [r for r in rijen if r["datum"] >= splits and not r.get("na_florgib")]
    model = train(oud + [r for r in extra if r["datum"] < splits])
    kansen = [kans(model, r) for r in nieuw]
    per_planting = planting_dagen(nieuw, kansen)
    uit = _tel([(p, y) for p, y, _l in per_planting])
    na = [r for r in rijen if r["datum"] >= splits and r.get("na_florgib")]
    uit.update(na_florgib={"dagen": len(na), "giften": sum(r["gift"] >= MIN_GIFT for r in na)},
               oud_dagen=len(oud), van=min((r["datum"] for r in nieuw), default=None),
               tot=max((r["datum"] for r in nieuw), default=None),
               fasen={FASEN[i][2]: _tel([(p, y) for p, y, l in per_planting if fase(l) == i])
                      for i in range(len(FASEN))},
               per_vak=_tel([(p, r["gift"] >= MIN_GIFT) for r, p in zip(nieuw, kansen)]))
    return uit

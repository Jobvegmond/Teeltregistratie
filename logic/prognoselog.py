"""
Prognoselogboek: elke dag per lopend vak vastleggen wat het teeltmodel
voorspelt, en na de oogst uitrekenen hoe goed dat was.

- Vastleggen: logregels() maakt uit de stand van vandaag (TeeltPrognose.beoordeel
  per lopend vak) de regels voor de tabel prognose_log. De database schrijft ze
  met ON CONFLICT DO NOTHING: één regel per vak per dag, de eerste blijft staan.
- Werkelijke oogst: de dag waarop de helft van de emmers binnen is (bij geen
  emmers: datum_oogst). De eerste emmerdag gaat mee als extra informatie.
- Fout = werkelijk − prognose in dagen: positief = later geoogst dan voorspeld.
  Dezelfde fout voor de plandatum (werkelijk − plan_oogst).
- Horizons: 28, 14 en 7 dagen vóór de werkelijke oogst (de logregel die daar
  het dichtst bij ligt, binnen ±2 dagen) en de eerste regel na Florgib.

Alleen rekenwerk; geen database, geen Streamlit. Tests in tests/test_prognoselog.py.
"""
from datetime import date, datetime, timedelta

import numpy as np

from logic import teeltprognose as tp

# Verhoog bij een inhoudelijke wijziging van het teeltmodel; de fit-grootte
# (aantal leerteelten) komt er automatisch achter.
MODELVERSIE = "teeltmodel-1"
HORIZONS = (28, 14, 7)
HORIZON_MARGE = 2
FLORGIB = "na Florgib"
BINNEN_DAGEN = 2
MIN_VAKKEN = 10


def _datum(waarde):
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, datetime):
        return waarde.date()
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def bouw_model(data, historie, historie_week, plandatum, min_leerteelten=20):
    """
    Het teeltmodel, gefit op teelt_historie plus de in de app afgeronde teelten
    die daar nog niet in staan. None als er te weinig leerteelten zijn.
    data: get_vakstatus_data(); historie/historie_week: get_teelthistorie_data().
    """
    klimaat = tp.klimaat_per_afdeling(data["klimaat"])
    leerset = tp.bouw_leerset(historie, historie_week, data["teelten"], klimaat, plandatum)
    if len(leerset) < min_leerteelten:
        return None
    return tp.TeeltPrognose().fit(leerset, tp.weeklicht(historie_week, data["klimaat"]))


def modelversie(model):
    return f"{MODELVERSIE}/n{model.n_leer}"


def stand_lopende_teelten(teelten, klimaat_afd, model, vandaag, plandatum):
    """
    (stook, afwijking) voor alle lopende teelten op `vandaag`:
    - stook: {teelt_id: TeeltPrognose.beoordeel-uitkomst}
    - afwijking: {(tuin_id, afdeling): gemiddelde afwijking van de lichtlijn, laatste 14 dagen}
    teelten: de teelten-DataFrame van get_vakstatus_data(); klimaat_afd: tp.klimaat_per_afdeling();
    plandatum(start) → de geplande oogstdatum.
    """
    afwijking = {k: tp.afwijking_afdeling(d, vandaag) for k, d in klimaat_afd.items()}
    stook = {}
    for t in teelten.itertuples() if model else []:
        start = _datum(t.datum_teelt_start)
        if _datum(t.datum_oogst) or start > vandaag or tp._getal(t.afdeling) is None:
            continue
        sleutel = (int(t.tuin_id), int(t.afdeling))
        reeks = tp.dagreeks(start, (vandaag - start).days, klimaat_afd.get(sleutel, {}))
        if reeks is None:
            continue
        half = _datum(t.datum_half)
        stook[int(t.id)] = model.beoordeel(
            int(t.tuin_id), start, vandaag, plandatum(start), *reeks,
            afwijking.get(sleutel), half if half and half > start else None)
    return stook, afwijking


def logregels(teelten, stook, afwijking, vandaag, modelversie):
    """Eén dict per lopend vak met een prognose, in de kolommen van prognose_log."""
    regels = []
    for t in teelten.itertuples():
        u = stook.get(int(t.id))
        if u is None:
            continue
        nu = afwijking.get((int(t.tuin_id), int(t.afdeling)))
        half = _datum(t.datum_half)
        regels.append({
            "datum": vandaag, "teelt_id": int(t.id), "tuin_id": int(t.tuin_id),
            "afdeling": int(t.afdeling), "vaknummer": int(t.vaknummer), "code": t.code,
            "leeftijd_d": (vandaag - u["start"]).days,
            "fase": "na_florgib" if half and u["start"] < half <= vandaag else "voor_florgib",
            "gedaan": float(u["gedaan"]),
            "plan_oogst": u["plan"], "prognose_oogst": u["prognose"],
            "correctie_c": None if u["c"] is None else float(u["c"]), "c_begrensd": bool(u["begrensd"]),
            # Zonder klimaat van de laatste 14 dagen rekent de prognose met de lichtlijn zelf.
            "stooklijn": float(nu) if nu is not None else 0.0,
            "stooklijn_bron": "gerealiseerd_14d" if nu is not None else "ingesteld",
            "modelversie": modelversie,
        })
    return regels


def werkelijke_oogst(emmers, datum_oogst=None):
    """
    (eerste emmerdag, dag waarop de helft van de emmers binnen is) uit
    emmers = {datum: aantal}. Zonder emmers: (None, datum_oogst).
    """
    dagen = sorted((_datum(d), a) for d, a in emmers.items() if a and a > 0)
    if not dagen:
        return None, _datum(datum_oogst)
    totaal, opgeteld = sum(a for _, a in dagen), 0.0
    for dag, aantal in dagen:
        opgeteld += aantal
        if opgeteld >= totaal / 2:
            return dagen[0][0], dag
    return dagen[0][0], dagen[-1][0]


def horizonregels(log, werkelijk):
    """
    {horizon: logregel} voor één vak: per horizon uit HORIZONS de regel die het
    dichtst bij `horizon` dagen vóór `werkelijk` ligt (binnen ±HORIZON_MARGE,
    bij gelijke afstand de vroegste), plus FLORGIB = de eerste regel na Florgib.
    log: de logregels van dat vak (dicts met datum en fase).
    """
    uit = {}
    for horizon in HORIZONS:
        doel = werkelijk - timedelta(days=horizon)
        kandidaten = [r for r in log if abs((_datum(r["datum"]) - doel).days) <= HORIZON_MARGE]
        if kandidaten:
            uit[horizon] = min(kandidaten, key=lambda r: (abs((_datum(r["datum"]) - doel).days), _datum(r["datum"])))
    na = sorted((r for r in log if r["fase"] == "na_florgib" and _datum(r["datum"]) < werkelijk),
                key=lambda r: _datum(r["datum"]))
    if na:
        uit[FLORGIB] = na[0]
    return uit


def fouten(log, oogsten):
    """
    Per geoogst vak met logregels en per horizon één rij:
    {teelt_id, tuin_id, code, vaknummer, horizon, datum, dagen_voor_oogst,
     werkelijk, eerste_emmer, fout_prognose, fout_plan}.
    log: alle logregels (dicts); oogsten: {teelt_id: (eerste_emmer, werkelijk)}
    voor de afgeronde vakken.
    """
    per_vak = {}
    for r in log:
        per_vak.setdefault(int(r["teelt_id"]), []).append(r)
    rijen = []
    for teelt_id, regels in per_vak.items():
        eerste, werkelijk = oogsten.get(teelt_id, (None, None))
        if werkelijk is None:
            continue
        for horizon, r in horizonregels(regels, werkelijk).items():
            prognose, plan = _datum(r["prognose_oogst"]), _datum(r["plan_oogst"])
            rijen.append({
                "teelt_id": teelt_id, "tuin_id": int(r["tuin_id"]), "code": r["code"],
                "vaknummer": int(r["vaknummer"]), "horizon": horizon, "datum": _datum(r["datum"]),
                "dagen_voor_oogst": (werkelijk - _datum(r["datum"])).days,
                "werkelijk": werkelijk, "eerste_emmer": eerste,
                "fout_prognose": (werkelijk - prognose).days if prognose else None,
                "fout_plan": (werkelijk - plan).days if plan else None,
            })
    return rijen


def kwaliteit(rijen, veld):
    """
    {(tuin_id, horizon): {n, gemiddeld, mae, binnen_pct}} over de rijen van
    fouten(), voor veld "fout_prognose" of "fout_plan".
    """
    groepen = {}
    for r in rijen:
        if r[veld] is not None:
            groepen.setdefault((r["tuin_id"], r["horizon"]), []).append(r[veld])
    return {k: {"n": len(v), "gemiddeld": float(np.mean(v)), "mae": float(np.mean(np.abs(v))),
                "binnen_pct": 100.0 * sum(abs(x) <= BINNEN_DAGEN for x in v) / len(v)}
            for k, v in groepen.items()}


def aantal_vakken(rijen):
    """Aantal geoogste vakken met minstens één horizonregel."""
    return len({r["teelt_id"] for r in rijen})


def grootste_missers(rijen, aantal=10):
    """
    De vakken met de grootste |fout| van de prognose over de horizons, groot naar
    klein: [{teelt_id, tuin_id, code, vaknummer, werkelijk, eerste_emmer,
    fouten: {horizon: fout}, max_fout}].
    """
    per_vak = {}
    for r in rijen:
        if r["fout_prognose"] is None:
            continue
        v = per_vak.setdefault(r["teelt_id"], {k: r[k] for k in ("teelt_id", "tuin_id", "code", "vaknummer",
                                                                  "werkelijk", "eerste_emmer")} | {"fouten": {}})
        v["fouten"][r["horizon"]] = r["fout_prognose"]
    for v in per_vak.values():
        v["max_fout"] = max(v["fouten"].values(), key=abs)
    return sorted(per_vak.values(), key=lambda v: (-abs(v["max_fout"]), v["code"] or ""))[:aantal]


def fout_per_dag(log, oogsten):
    """
    Voor de grafiek: [{tuin_id, dagen_voor_oogst, fout}] over álle logregels van
    geoogste vakken (niet alleen de horizons).
    """
    uit = []
    for r in log:
        eerste, werkelijk = oogsten.get(int(r["teelt_id"]), (None, None))
        prognose = _datum(r["prognose_oogst"])
        if werkelijk is None or prognose is None or _datum(r["datum"]) >= werkelijk:
            continue
        uit.append({"tuin_id": int(r["tuin_id"]), "dagen_voor_oogst": (werkelijk - _datum(r["datum"])).days,
                    "fout": (werkelijk - prognose).days})
    return uit

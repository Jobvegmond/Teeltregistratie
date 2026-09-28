"""
Stap 1: teeltduur-, Florgib- en kwaliteitsanalyse, alles leave-one-out.

    python analyse/teeltduur_analyse.py        # met DATABASE_URL (productie of NAS)

Schrijft analyse/rapport.html (tekst, tabellen, grafieken) en analyse/uitkomsten.json.
Leest alleen; schrijft niets naar de database.
"""
import json
import math
import os
import sys
import warnings
from collections import defaultdict
from datetime import timedelta

warnings.filterwarnings("ignore")
HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HIER))

import numpy as np
import pandas as pd

from analyse.bronnen import bouw_dataset
from logic.lichtlijn import t_ideaal
from logic.teeltmodel import (GraaddagenModel, LineairModel, MetTuinfactor, duur_uit_snelheid, florgib_fractie,
                              leave_one_out, ontwikkeling, voor_tuin, voorspel_duur)

T_BASISSEN = (0, 4, 6, 8, 10)
KAPPAS = (0.1, 0.25, 0.5, 1.0)
CHECKPOINTS = ("dag 14", "dag 28", "bij Florgib", "7 d voor oogst")
TOEKOMST_DAGEN = 150


def zomer(t):
    """Plantmaand april t/m september = zomer, anders winter."""
    return 4 <= t["start"].month <= 9


def fouten(voorspeld, werkelijk):
    f = np.asarray(voorspeld, float) - np.asarray(werkelijk, float)
    f = f[~np.isnan(f)]
    if not len(f):
        return {"n": 0}
    return {"n": int(len(f)), "mae": float(np.abs(f).mean()), "bias": float(f.mean()),
            "rmse": float(np.sqrt((f ** 2).mean())), "binnen3": float((np.abs(f) <= 3).mean() * 100)}


def tabel_duur(teelten):
    from database import bereken_verwachte_oogstdatum
    return np.array([(bereken_verwachte_oogstdatum(t["start"])[1] - t["start"]).days for t in teelten], float)


def loo_graaddagen(teelten, t_basis, kappa):
    """Snelle leave-one-out voor het graaddagenmodel (alleen de mediaan G verandert per teelt)."""
    model = GraaddagenModel(t_basis, kappa)
    sommen = np.array([model.som_bij_oogst(t) for t in teelten])
    voorspeld = []
    for i, t in enumerate(teelten):
        model.G = float(np.median(np.delete(sommen, i)))
        v = voorspel_duur(model, t["T_ext"], t["L_ext"])
        voorspeld.append(np.nan if v is None else v)
    return np.array(voorspeld)


def modelvergelijking(teelten):
    werkelijk = np.array([t["duur"] for t in teelten])
    uitkomst = {"tabel": tabel_duur(teelten), "regressie": leave_one_out(LineairModel, teelten)}
    for tb in T_BASISSEN:
        uitkomst[f"graaddagen {tb}"] = loo_graaddagen(teelten, tb, 0.0)
    beste_licht, beste_mae = None, math.inf
    for tb in T_BASISSEN:
        for k in KAPPAS:
            v = loo_graaddagen(teelten, tb, k)
            mae = fouten(v, werkelijk)["mae"]
            if mae < beste_mae:
                beste_licht, beste_mae, beste_v = (tb, k), mae, v
    naam_licht = f"graaddagen {beste_licht[0]} + licht {beste_licht[1]:g}"
    uitkomst[naam_licht] = beste_v
    # Dezelfde modellen met een correctie per tuin (factor ook leave-one-out bepaald).
    for naam in ("regressie", naam_licht):
        uitkomst[naam + " + tuincorrectie"] = leave_one_out(lambda n=naam: maak_model(n + " + tuincorrectie"), teelten)
    return werkelijk, uitkomst, beste_licht


def maak_model(naam):
    """Een ongefit model bij de naam uit de modelvergelijking."""
    if naam.endswith(" + tuincorrectie"):
        return MetTuinfactor(maak_model(naam[: -len(" + tuincorrectie")]))
    if naam == "regressie":
        return LineairModel()
    delen = naam.split()
    tb = float(delen[1])
    kappa = float(delen[-1]) if "licht" in naam else 0.0
    return GraaddagenModel(tb, kappa)


def florgib_analyse(teelten, modelnaam):
    """
    De Florgib als indicator van hoe ver de teelt is: welk deel van de
    ontwikkeling (volgens het model over de hele teelt) is bereikt op de dag
    van het spuiten, en hoe goed is de Florgib-datum daarmee te voorspellen.
    Leave-one-out: per teelt het model en de mediaan-fractie zonder die teelt.
    """
    met = [t for t in teelten if t["florgib"]]
    model = maak_model(modelnaam).fit(teelten)
    fracties = np.array([florgib_fractie(model, t["T"], t["L"], (t["florgib"] - t["start"]).days, t["duur"])
                         for t in met])
    dagdeel = np.array([(t["florgib"] - t["start"]).days / t["duur"] for t in met])
    fouten_dag = []
    for i, t in enumerate(met):
        m = maak_model(modelnaam).fit([x for x in teelten if x is not t])
        f_med = float(np.median(np.delete(fracties, i)))
        voorspeld = duur_uit_snelheid(voor_tuin(m, t["tuin"]).snelheid(t["T_ext"], t["L_ext"]), doel=f_med)
        if voorspeld is not None:
            fouten_dag.append(voorspeld - (t["florgib"] - t["start"]).days)
    fouten_dag = np.array(fouten_dag)
    return {
        "n": len(met), "per_tuin": {str(k): int(v) for k, v in pd.Series([t["tuin"] for t in met]).value_counts().items()},
        "fractie_mediaan": float(np.median(fracties)), "fractie_p10": float(np.percentile(fracties, 10)),
        "fractie_p90": float(np.percentile(fracties, 90)),
        "dagdeel_mediaan": float(np.median(dagdeel)), "dagdeel_p10": float(np.percentile(dagdeel, 10)),
        "dagdeel_p90": float(np.percentile(dagdeel, 90)),
        "dagen_mediaan": float(np.median([(t["florgib"] - t["start"]).days for t in met])),
        "voorspelling": {"mae": float(np.abs(fouten_dag).mean()), "bias": float(fouten_dag.mean()),
                         "binnen2": float((np.abs(fouten_dag) <= 2).mean() * 100)},
    }


def dagen_per_graad(model, teelten):
    lichten = np.percentile([t["L"].mean() for t in teelten], [10, 50, 90])
    uit = []
    for naam, L in zip(("laag", "middel", "hoog"), lichten):
        d0 = model.dagen_per_graad(L, 0.0)
        uit.append({"licht": naam, "lichtsom": float(L), "duur_op_lichtlijn": d0,
                    "plus_1": model.dagen_per_graad(L, 1.0) - d0, "min_1": model.dagen_per_graad(L, -1.0) - d0})
    return uit


def kwaliteit(teelten):
    """Oogstgewicht (en gewicht per 10 cm) tegen de afwijking van de lichtlijn, gecorrigeerd voor lichtniveau."""
    uit = {}
    for label, waarde in (("gewicht", lambda t: t["gewicht"]),
                          ("gewicht per 10 cm", lambda t: t["gewicht"] / t["lengte"] * 10 if t["lengte"] else None)):
        rijen = [(waarde(t), (t["T"] - t_ideaal(t["L"])).mean(), t["L"].mean(), t["plantweek"])
                 for t in teelten if t["gewicht"] and waarde(t)]
        n = len(rijen)
        weken = len({r[3] for r in rijen})
        res = {"n": n, "plantweken": weken}
        if n >= 8:
            y = np.array([r[0] for r in rijen])
            X = np.column_stack([np.ones(n), [r[1] for r in rijen], [r[2] for r in rijen]])
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            rest = y - X @ coef
            s2 = (rest @ rest) / max(n - 3, 1)
            se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
            res.update(gram_per_graad=float(coef[1]), se=float(se[1]), t=float(coef[1] / se[1]) if se[1] else None,
                       afwijking_bereik=(float(min(r[1] for r in rijen)), float(max(r[1] for r in rijen))),
                       punten=[{"afwijking": float(r[1]), "waarde": float(r[0]), "lichtsom": float(r[2])} for r in rijen])
        res["genoeg"] = n >= 30 and weken >= 10
        uit[label] = res
    return uit


def klimatologie(teelten, klimaat):
    """Gemiddelde lichtsom binnen per (jaar, ISO-week), om een meerjarig weekgemiddelde te maken."""
    per_jaar_week = defaultdict(list)
    for (tuin, afd), dagen in klimaat.items():
        for d, (_, L) in dagen.items():
            j, w, _ = d.isocalendar()
            per_jaar_week[(j, w)].append(L)
    return {k: float(np.mean(v)) for k, v in per_jaar_week.items()}


def verwacht_licht(klim, vanaf, dagen, eigen_jaar):
    """Meerjarig weekgemiddelde lichtsom per dag; het eigen jaar telt niet mee als er andere zijn."""
    uit = []
    for i in range(dagen):
        d = vanaf + timedelta(days=i)
        w = d.isocalendar()[1]
        andere = [v for (j, wk), v in klim.items() if wk == w and j != eigen_jaar]
        alle = andere or [v for (j, wk), v in klim.items() if wk == w]
        uit.append(np.mean(alle) if alle else np.nan)
    return np.array(pd.Series(uit).ffill().bfill())


def prognose_duur(model, t, k, klim, gedaan=None, doel=1.0):
    """
    Voorspelde dag (vanaf planten) waarop de teelt `doel` bereikt (1 = oogst),
    op dag k met alleen de data tot dan: werkelijke dagen tot k, daarna
    verwacht licht en temperatuur = lichtlijn + de gemiddelde afwijking van de
    laatste 14 dagen. Met `gedaan` wordt het opgebouwde deel op dag k
    vastgezet (Florgib-ijking) in plaats van uit de dagen berekend.
    """
    model = voor_tuin(model, t["tuin"])
    T_tot, L_tot = t["T_ext"][:k], t["L_ext"][:k]
    afw = float((T_tot[-14:] - t_ideaal(L_tot[-14:])).mean())
    L_verw = verwacht_licht(klim, t["start"] + timedelta(days=k), TOEKOMST_DAGEN, t["start"].year)
    T_verw = t_ideaal(L_verw) + afw
    if gedaan is None:
        gedaan = ontwikkeling(model, T_tot, L_tot)
    if gedaan >= doel:
        return float(duur_uit_snelheid(model.snelheid(T_tot, L_tot), doel=doel))
    rest = duur_uit_snelheid(model.snelheid(T_verw, L_verw), begin=gedaan, doel=doel)
    return None if rest is None else k + rest


def backtest(teelten, modelnaam, klim):
    """Alleen teelten met een oogstdatum op de dag; het model telkens zonder die teelt gefit."""
    tabel = tabel_duur(teelten)
    rijen = []
    for i, t in enumerate(teelten):
        if t["precisie"] != "dag":
            continue
        overige = teelten[:i] + teelten[i + 1:]
        model = maak_model(modelnaam).fit(overige)
        f_med = float(np.median([florgib_fractie(model, o["T"], o["L"], (o["florgib"] - o["start"]).days, o["duur"])
                                 for o in overige if o["florgib"]]))
        punten = {"dag 14": 14, "dag 28": 28, "7 d voor oogst": int(t["duur"]) - 7}
        if t["florgib"]:
            punten["bij Florgib"] = (t["florgib"] - t["start"]).days
        for label, k in punten.items():
            if k < 14 or k >= t["duur"]:
                continue
            v = prognose_duur(model, t, k, klim)
            rij = {"tuin": t["tuin"], "checkpoint": label, "werkelijk": t["duur"], "model": v, "plan": tabel[i]}
            if label == "bij Florgib":
                rij["ijking"] = prognose_duur(model, t, k, klim, gedaan=f_med)
            if label in ("dag 14", "dag 28") and t["florgib"] and k < (t["florgib"] - t["start"]).days:
                rij["florgib_voorspeld"] = prognose_duur(model, t, k, klim, doel=f_med)
                rij["florgib_werkelijk"] = (t["florgib"] - t["start"]).days
            rijen.append(rij)
    return pd.DataFrame(rijen)


def main():
    teelten, klimaat, log = bouw_dataset()
    dag = [t for t in teelten if t["precisie"] == "dag"]
    print(f"{len(teelten)} teelten ({len(dag)} met oogst op de dag). Afgevallen: {log}")

    werkelijk, voorspeld, beste_licht = modelvergelijking(teelten)
    is_dag = np.array([t["precisie"] == "dag" for t in teelten])
    is_zomer = np.array([zomer(t) for t in teelten])
    tuinen = np.array([t["tuin"] for t in teelten])
    vergelijking = {}
    for naam, v in voorspeld.items():
        vergelijking[naam] = {
            "alle": fouten(v, werkelijk), "op de dag": fouten(v[is_dag], werkelijk[is_dag]),
            "zomer": fouten(v[is_zomer], werkelijk[is_zomer]), "winter": fouten(v[~is_zomer], werkelijk[~is_zomer]),
            "tuin 1": fouten(v[tuinen == 1], werkelijk[tuinen == 1]), "tuin 3": fouten(v[tuinen == 3], werkelijk[tuinen == 3]),
            "tuin 3 op de dag": fouten(v[(tuinen == 3) & is_dag], werkelijk[(tuinen == 3) & is_dag]),
        }
    for naam, r in vergelijking.items():
        print(f"  {naam:<32} MAE {r['alle']['mae']:.2f} d (op de dag {r['op de dag']['mae']:.2f}) bias {r['alle']['bias']:+.2f} "
              f"| zomer {r['zomer']['mae']:.2f} winter {r['winter']['mae']:.2f} | bias tuin1 {r['tuin 1']['bias']:+.2f} "
              f"tuin3 {r['tuin 3']['bias']:+.2f}")
    kandidaten = [n for n in vergelijking if n != "tabel"]
    beste = min(kandidaten, key=lambda n: vergelijking[n]["alle"]["mae"])
    print("beste model:", beste)

    zonder = beste.replace(" + tuincorrectie", "")
    res = voorspeld[zonder] - werkelijk
    diag = pd.DataFrame({"tuin": tuinen, "jaar": [t["start"].year for t in teelten], "precisie": [t["precisie"] for t in teelten],
                         "fout": res}).groupby(["tuin", "jaar", "precisie"])["fout"].agg(["size", "mean"])
    print("gemiddelde fout (zonder tuincorrectie) per tuin, plantjaar en precisie:")
    print(diag.round(1).to_string())

    beste_model = maak_model(beste).fit(teelten)
    regressie = LineairModel().fit(teelten)
    neutraal = getattr(beste_model, "basis", beste_model)
    per_graad = {"beste": dagen_per_graad(neutraal, teelten), "regressie": dagen_per_graad(regressie, teelten)}
    tuinfactor = getattr(beste_model, "factor", {})
    print("tuinfactor:", tuinfactor)
    print("dagen per °C (beste):", [(r["licht"], round(r["lichtsom"]), round(r["duur_op_lichtlijn"], 1),
                                     round(r["plus_1"], 1), round(r["min_1"], 1)) for r in per_graad["beste"]])
    print("regressie a, b, c:", regressie.a, regressie.b, regressie.c)

    florgib = florgib_analyse(teelten, beste)
    print("Florgib:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in florgib.items()})

    kw = kwaliteit(teelten)
    for label, r in kw.items():
        print(f"  kwaliteit {label}: n {r['n']} plantweken {r['plantweken']} "
              + (f"{r['gram_per_graad']:+.1f} per °C (se {r['se']:.1f}, t {r['t']:.1f})" if "gram_per_graad" in r else ""))

    klim = klimatologie(teelten, klimaat)
    bt = backtest(teelten, beste, klim)
    bt["fout_model"] = bt["model"] - bt["werkelijk"]
    bt["fout_plan"] = bt["plan"] - bt["werkelijk"]
    bt["fout_ijking"] = bt["ijking"] - bt["werkelijk"]
    samenvatting = bt.groupby("checkpoint").agg(
        n=("werkelijk", "size"), mae_model=("fout_model", lambda f: f.abs().mean()),
        bias_model=("fout_model", "mean"), mae_plan=("fout_plan", lambda f: f.abs().mean()),
        mae_ijking=("fout_ijking", lambda f: f.abs().mean()))
    print(samenvatting.round(2).to_string())
    fg = bt.dropna(subset=["florgib_voorspeld"])
    florgib["backtest"] = {cp: {"n": int(len(g)), "mae": float((g["florgib_voorspeld"] - g["florgib_werkelijk"]).abs().mean())}
                           for cp, g in fg.groupby("checkpoint")}
    print("verwachte Florgib-datum in de backtest:", florgib["backtest"])

    resultaat = {
        "n": len(teelten), "n_dag": len(dag), "afgevallen": log, "beste": beste, "beste_licht": beste_licht,
        "vergelijking": vergelijking, "per_graad": per_graad,
        "regressie": {"a": regressie.a, "b": regressie.b, "c": regressie.c},
        "beste_parameters": {k: getattr(neutraal, k) for k in ("t_basis", "kappa", "G", "a", "b", "c")
                             if getattr(neutraal, k, None) is not None},
        "tuinfactor": tuinfactor, "diagnose": {f"{i[0]}|{i[1]}|{i[2]}": {"n": int(r["size"]), "fout": float(r["mean"])}
                                               for i, r in diag.iterrows()},
        "florgib": florgib, "kwaliteit": kw,
        "backtest": samenvatting.reset_index().to_dict("records"),
        "punten": [{"tuin": t["tuin"], "start": str(t["start"]), "werkelijk": t["duur"], "precisie": t["precisie"],
                    "zomer": zomer(t), "tabel": float(voorspeld["tabel"][i]), "beste": float(voorspeld[beste][i]),
                    "lichtsom": float(t["L"].mean()), "afwijking": float((t["T"] - t_ideaal(t["L"])).mean())}
                   for i, t in enumerate(teelten)],
    }
    with open(os.path.join(HIER, "uitkomsten.json"), "w", encoding="utf-8") as f:
        json.dump(resultaat, f, ensure_ascii=False, indent=1, default=float)
    return resultaat


if __name__ == "__main__":
    main()

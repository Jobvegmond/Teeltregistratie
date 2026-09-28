"""Maakt analyse/rapport.html uit de uitkomsten van teeltduur_analyse.py (tekst, tabellen, grafieken)."""
import html
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HIER))

import altair as alt
import pandas as pd

from logic.lichtlijn import formule_tekst
from utils.format import fmt_getal, fmt_verschil, zet_altair_nl

zet_altair_nl()
_grafieken = []


def grafiek(chart):
    """Voegt een Altair-grafiek toe; geeft de HTML-plek terug."""
    i = len(_grafieken)
    _grafieken.append(chart.to_json())
    return f'<div class="grafiek" id="g{i}"></div>'


def tabel(rijen, kolommen):
    """rijen: lijst dicts; kolommen: [(sleutel, kop)] — waarden zijn al opgemaakt."""
    kop = "".join(f"<th>{html.escape(k)}</th>" for _, k in kolommen)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(s, '')))}</td>" for s, _ in kolommen) + "</tr>"
                   for r in rijen)
    return f"<table><thead><tr>{kop}</tr></thead><tbody>{body}</tbody></table>"


def d(x, dec=1):
    return fmt_getal(x, dec)


def nl(tekst):
    """Getallen in modelnamen en parameters met een komma ("licht 0.1" → "licht 0,1")."""
    import re
    return re.sub(r"(?<=\d)\.(?=\d)", ",", str(tekst))


def maak(res):
    v = res["vergelijking"]
    beste = res["beste"]
    punten = pd.DataFrame(res["punten"])
    punten["fout_beste"] = punten["beste"] - punten["werkelijk"]
    punten["fout_tabel"] = punten["tabel"] - punten["werkelijk"]
    punten["maand"] = pd.to_datetime(punten["start"]).dt.month
    punten["Tuin"] = "Tuin " + punten["tuin"].astype(str)
    punten["Oogstdatum"] = punten["precisie"].map({"dag": "op de dag", "week": "op de week (±3 d)"})

    delen = []
    # --- Samenvatting ---
    t1 = res["tuinfactor"].get("1", res["tuinfactor"].get(1))
    bt = {r["checkpoint"]: r for r in res["backtest"]}
    kw = res["kwaliteit"]["gewicht"]
    delen.append(f"""
<h1>Teeltduur, stooklijn en kwaliteit — analyse</h1>
<p class="sub">{res['n']} afgeronde teelten: tuin 3 (code S, 2022–2026) en tuin 1 (2025–2026), waarvan {res['n_dag']}
met een oogstdatum op de dag. Alles leave-one-out: elke teelt is voorspeld met een model waarin hij zelf niet zat.
Lichtsom = binnen; lichtlijn = {html.escape(formule_tekst())}.</p>
<div class="kern">
<h2>In het kort</h2>
<ul>
<li><b>Beste model: {html.escape(nl(beste))}.</b> Gemiddeld {d(v[beste]['alle']['mae'])} dagen fout
({d(v[beste]['op de dag']['mae'])} bij teelten met een oogstdatum op de dag). De huidige teeltduur-tabel zit op
{d(v['tabel']['alle']['mae'])} dagen ({d(v['tabel']['op de dag']['mae'])} op de dag), en is vooral in de winter zwak
({d(v['tabel']['winter']['mae'])} tegen {d(v[beste]['winter']['mae'])} dagen).</li>
<li><b>Een graad boven de lichtlijn</b> scheelt bij weinig licht ruim {d(-res['per_graad']['beste'][0]['plus_1'], 0)} dagen,
bij gemiddeld licht {d(-res['per_graad']['beste'][1]['plus_1'])} en bij veel licht {d(-res['per_graad']['beste'][2]['plus_1'])} dagen.</li>
<li><b>Tuin 1 is trager</b> dan het model verwacht: factor {d(t1, 3)} (ongeveer {d((t1 - 1) * 56, 1)} dagen op een
teelt van 56 dagen). Een deel daarvan is een jaareffect (2026 was in beide tuinen trager); binnen 2026 is het
verschil tussen de tuinen ongeveer {d(abs(res['diagnose'].get('1|2026|dag', {}).get('fout', 0) - res['diagnose'].get('3|2026|week', {}).get('fout', 0)))} dagen.
Voorstel: tuincorrectie gebruiken (zit in het beste model), en na een jaar opnieuw bekijken.</li>
<li><b>Fase 1 (planten → Florgib)</b> is goed te voorspellen (±{d(res['fasen']['fase 1'][beste]['mae'])} d);
<b>fase 2</b> minder (±{d(res['fasen']['fase 2'][beste]['mae'])} d). Een apart fase 2-model maakt de prognose bij de
Florgib nu niet beter ({d(bt.get('bij Florgib', {}).get('mae_fase2'))} tegen {d(bt.get('bij Florgib', {}).get('mae_model'))} d).</li>
<li><b>Backtest:</b> op dag 14 al {d(bt['dag 14']['mae_model'])} dagen gemiddelde fout (plan: {d(bt['dag 14']['mae_plan'])}).
Dichter bij de oogst wordt het niet beter: de modelfout is groter dan de onzekerheid over het weer.</li>
<li><b>Kwaliteit:</b> te weinig data ({kw['n']} teelten uit {kw['plantweken']} plantweken, alleen tuin 3 in juli–augustus 2026).
Het gemeten verband wijst zelfs de andere kant op dan verwacht; daar kun je nog niets mee.</li>
</ul></div>""")

    # --- 1. Modellen ---
    rijen = []
    for naam, r in v.items():
        rijen.append({"model": nl(naam), "mae": d(r["alle"]["mae"]), "dag": d(r["op de dag"]["mae"]),
                      "bias": fmt_verschil(r["alle"]["bias"], 1), "zomer": d(r["zomer"]["mae"]), "winter": d(r["winter"]["mae"]),
                      "t1": fmt_verschil(r["tuin 1"]["bias"], 1), "t3": fmt_verschil(r["tuin 3"]["bias"], 1),
                      "binnen3": fmt_getal(r["alle"]["binnen3"], 0) + " %"})
    delen.append("<h2>1. Welk model voorspelt de teeltduur het best?</h2>")
    delen.append("""<p>Alle modellen rekenen met een ontwikkelingssnelheid per dag; de teelt is klaar als die
optelt tot 1. <b>Regressie</b>: snelheid = a + b × lichtsom + c × (T − T<sub>ideaal</sub>). <b>Graaddagen</b>:
(T − T<sub>basis</sub>) per dag, eventueel plus een deel licht. <b>Tuincorrectie</b>: per tuin een factor op de
snelheid. Fout = voorspelde min werkelijke teeltduur in dagen; bias &lt; 0 = te vroeg voorspeld.</p>""")
    delen.append(tabel(rijen, [("model", "Model"), ("mae", "Fout (d)"), ("dag", "Fout, oogst op de dag"),
                               ("bias", "Bias"), ("zomer", "Zomer"), ("winter", "Winter"), ("t1", "Bias tuin 1"),
                               ("t3", "Bias tuin 3"), ("binnen3", "Binnen 3 d")]))
    mae_df = pd.DataFrame([{"Model": nl(n), "Groep": g, "Fout (d)": r[k]["mae"]} for n, r in v.items()
                           for g, k in (("alle teelten", "alle"), ("oogst op de dag", "op de dag"))])
    delen.append(grafiek(alt.Chart(mae_df).mark_bar().encode(
        y=alt.Y("Model:N", sort=[nl(n) for n in v], title=None), x=alt.X("Fout (d):Q", title="Gemiddelde fout (dagen)"),
        color=alt.Color("Groep:N", title=None, legend=alt.Legend(orient="top")), yOffset="Groep:N",
        tooltip=["Model", "Groep", alt.Tooltip("Fout (d):Q", format=".2f")]).properties(height=300)))
    delen.append(grafiek(alt.Chart(punten).mark_circle(size=40, opacity=0.6).encode(
        x=alt.X("werkelijk:Q", title="Werkelijke teeltduur (d)", scale=alt.Scale(zero=False)),
        y=alt.Y("beste:Q", title=f"Voorspeld, {nl(beste)} (d)", scale=alt.Scale(zero=False)),
        color=alt.Color("Tuin:N", legend=alt.Legend(orient="top", title=None)),
        shape=alt.Shape("Oogstdatum:N", legend=alt.Legend(orient="top")),
        tooltip=["Tuin", "start", alt.Tooltip("werkelijk:Q", format=".0f"), alt.Tooltip("beste:Q", format=".1f")],
    ).properties(height=320, title="Voorspeld tegen werkelijk") + alt.Chart(pd.DataFrame({"x": [30, 115]})).mark_line(
        color="#999", strokeDash=[4, 3]).encode(x="x:Q", y="x:Q")))
    per_maand = punten.groupby("maand")[["fout_beste", "fout_tabel"]].mean().reset_index().melt(
        "maand", var_name="Wat", value_name="Gem. fout (d)")
    per_maand["Wat"] = per_maand["Wat"].map({"fout_beste": nl(beste), "fout_tabel": "teeltduur-tabel"})
    delen.append("<h3>Zomer en winter</h3><p>Gemiddelde fout per plantmaand: boven 0 = te laat voorspeld.</p>")
    delen.append(grafiek(alt.Chart(per_maand).mark_line(point=True).encode(
        x=alt.X("maand:O", title="Plantmaand"), y=alt.Y("Gem. fout (d):Q"),
        color=alt.Color("Wat:N", title=None, legend=alt.Legend(orient="top"))).properties(height=240)))

    # --- Tuinen ---
    diag = [{"groep": k.replace("|", " · "), "n": r["n"], "fout": fmt_verschil(r["fout"], 1)} for k, r in res["diagnose"].items()]
    delen.append("<h3>Tuin 1 tegen tuin 3</h3><p>Gemiddelde fout zonder tuincorrectie, per tuin, plantjaar en "
                 "nauwkeurigheid van de oogstdatum. Tuin 1 heeft alleen 2026; in 2026 was ook tuin 3 trager dan het "
                 f"model. Tuinfactor (1 = geen verschil): tuin 1 {d(t1, 3)}, tuin 3 {d(res['tuinfactor'].get('3', res['tuinfactor'].get(3)), 3)}.</p>")
    delen.append(tabel(diag, [("groep", "Tuin · plantjaar · oogstdatum"), ("n", "Teelten"), ("fout", "Gem. fout (d)")]))

    # --- Dagen per graad ---
    pg = res["per_graad"]["beste"]
    delen.append("<h2>Wat doet een graad boven of onder de lichtlijn?</h2>"
                 "<p>Teeltduur bij een vaste lichtsom als je de hele teelt op de lichtlijn stookt, en het verschil bij "
                 "1 °C erboven of eronder (zonder tuincorrectie).</p>")
    delen.append(tabel([{"licht": r["licht"], "lichtsom": d(r["lichtsom"], 0), "duur": d(r["duur_op_lichtlijn"]),
                         "plus": fmt_verschil(r["plus_1"], 1), "min": fmt_verschil(r["min_1"], 1)} for r in pg],
                       [("licht", "Licht"), ("lichtsom", "Lichtsom binnen (J/cm² per dag)"),
                        ("duur", "Teeltduur op de lichtlijn (d)"), ("plus", "+1 °C (d)"), ("min", "−1 °C (d)")]))
    pg_df = pd.DataFrame([{"Licht": f"{r['licht']} ({d(r['lichtsom'], 0)})", "Afwijking": a, "Dagen": r[k]}
                          for r in pg for a, k in (("+1 °C", "plus_1"), ("−1 °C", "min_1"))])
    delen.append(grafiek(alt.Chart(pg_df).mark_bar().encode(
        x=alt.X("Licht:N", sort=None, title=None), xOffset="Afwijking:N", y=alt.Y("Dagen:Q", title="Verschil in teeltduur (d)"),
        color=alt.Color("Afwijking:N", scale=alt.Scale(domain=["+1 °C", "−1 °C"], range=["#e4572e", "#2a78d6"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Licht", "Afwijking", alt.Tooltip("Dagen:Q", format=".1f")]).properties(height=240)))

    # --- 2. Fasen ---
    f = res["fasen"]
    delen.append("<h2>2. Fase 1 en fase 2</h2><p>Alleen teelten met een Florgib-datum (2026, voorjaar en zomer). "
                 "Fase 1 = planten → Florgib, fase 2 = Florgib → oogst.</p>")
    rijen = []
    for label, r in f.items():
        rij = {"fase": label, "n": r["n"], "duur": d(r["gem_duur"]), "sd": d(r["sd_duur"])}
        for naam in r:
            if isinstance(r[naam], dict):
                rij[naam] = d(r[naam]["mae"], 2)
        rijen.append(rij)
    modellen = [k for k in f["fase 1"] if isinstance(f["fase 1"][k], dict)]
    delen.append(tabel(rijen, [("fase", "Deel"), ("n", "Teelten"), ("duur", "Gem. duur (d)"), ("sd", "Spreiding (sd, d)")]
                       + [(m, f"Fout {nl(m)} (d)") for m in modellen]))

    # --- 3. Kwaliteit ---
    delen.append("<h2>3. Kwaliteit: gewicht tegen de stooklijn</h2>")
    for label, r in res["kwaliteit"].items():
        if "gram_per_graad" in r:
            delen.append(f"<p><b>{html.escape(label)}</b>: {fmt_verschil(r['gram_per_graad'], 1)} g per °C boven de lichtlijn "
                         f"(± {d(r['se'])} g; n = {r['n']} uit {r['plantweken']} plantweken, gecorrigeerd voor lichtniveau). "
                         + ("Te weinig data om op te sturen." if not r["genoeg"] else "") + "</p>")
    if res["kwaliteit"]["gewicht"].get("punten"):
        delen.append(grafiek(alt.Chart(pd.DataFrame(res["kwaliteit"]["gewicht"]["punten"])).mark_circle(size=60).encode(
            x=alt.X("afwijking:Q", title="Gem. afwijking van de lichtlijn (°C)"),
            y=alt.Y("waarde:Q", title="Oogstgewicht (g)", scale=alt.Scale(zero=False)),
            color=alt.Color("lichtsom:Q", title="Lichtsom"), tooltip=["afwijking", "waarde", "lichtsom"]).properties(height=240)))
    delen.append("<p>Om dit betrouwbaar te maken: bij elke oogst het gewicht registreren, over minstens een jaar "
                 "(zomer én winter), zodat er meer dan 10 plantweken met verschillende stooklijnen zijn.</p>")

    # --- 4. Backtest ---
    delen.append("<h2>4. Backtest: hoe goed was de prognose geweest?</h2><p>Voor elke teelt met een oogstdatum op de "
                 "dag: de oogstdatum voorspeld op dag 14, dag 28, bij de Florgib en 7 dagen voor de oogst, met alleen "
                 "de data tot dat moment. Verwacht licht = meerjarig gemiddelde per kalenderweek (zonder het eigen jaar); "
                 "verwachte temperatuur = lichtlijn + de gemiddelde afwijking van de laatste 14 dagen.</p>")
    rijen = [{"cp": r["checkpoint"], "n": r["n"], "model": d(r["mae_model"], 2), "bias": fmt_verschil(r["bias_model"], 1),
              "plan": d(r["mae_plan"], 2), "fase2": d(r.get("mae_fase2"), 2) if r.get("mae_fase2") == r.get("mae_fase2") else "–"}
             for r in res["backtest"]]
    volgorde = ["dag 14", "dag 28", "bij Florgib", "7 d voor oogst"]
    rijen.sort(key=lambda r: volgorde.index(r["cp"]))
    delen.append(tabel(rijen, [("cp", "Moment"), ("n", "Teelten"), ("model", f"Fout {nl(beste)} (d)"), ("bias", "Bias (d)"),
                               ("plan", "Fout plan/tabel (d)"), ("fase2", "Fout met fase 2-model (d)")]))
    bt_df = pd.DataFrame([{"Moment": r["checkpoint"], "Wat": w, "Fout (d)": r[k]} for r in res["backtest"]
                          for w, k in ((nl(beste), "mae_model"), ("plan (tabel)", "mae_plan")) if r.get(k) == r.get(k)])
    delen.append(grafiek(alt.Chart(bt_df).mark_bar().encode(
        x=alt.X("Moment:N", sort=volgorde, title=None), xOffset="Wat:N", y=alt.Y("Fout (d):Q", title="Gemiddelde fout (d)"),
        color=alt.Color("Wat:N", title=None, legend=alt.Legend(orient="top")),
        tooltip=["Moment", "Wat", alt.Tooltip("Fout (d):Q", format=".2f")]).properties(height=240)))

    # --- Verantwoording ---
    af = "; ".join(f"{k}: {n}" for k, n in res["afgevallen"].items())
    p = res["beste_parameters"]
    delen.append(f"""<h2>Verantwoording</h2><ul>
<li>Bronnen: Excel-kopieën in Teelt\\ (tuin 3 alleen code S; bij verschil gaat Excel voor) en de database
(teelten, oogstregistraties, klimaat per dag). Excel heeft weekwaarden: elke dag krijgt de weekwaarde.</li>
<li>Oogstdatum op de dag: tuin 1 (Aantekeningen/app) en teelten met emmers in de app. Tuin 3 vóór de app: op de week
(±3 d). Die tellen mee voor het model, de backtest alleen op teelten met een oogstdatum op de dag.</li>
<li>Afgevallen: {html.escape(af)}.</li>
<li>Modelparameters ({html.escape(nl(beste))}): {html.escape(nl(', '.join(f'{k} = {v:.6g}' for k, v in p.items())))};
tuinfactor {html.escape(', '.join(f'tuin {k}: {d(v, 3)}' for k, v in res['tuinfactor'].items()))}. Ze worden in de app uit de data
berekend, niet vastgezet.</li>
<li>De keuze tussen de graaddagenvarianten (T<sub>basis</sub>, licht) is op dezelfde data gemaakt; de fout van die
variant is daardoor iets te gunstig.</li></ul>""")
    return "\n".join(delen)


def schrijf():
    with open(os.path.join(HIER, "uitkomsten.json"), encoding="utf-8") as f:
        res = json.load(f)
    inhoud = maak(res)
    specs = json.dumps([json.loads(g) for g in _grafieken])
    pagina = f"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Teeltduur-analyse</title>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 980px; margin: 0 auto; padding: 1rem; color: #222; line-height: 1.45; }}
h1 {{ font-size: 1.5rem; margin-bottom: .2rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }} h3 {{ font-size: 1rem; }}
.sub {{ color: #666; font-size: .9rem; }}
.kern {{ background: #f4f7f2; border-left: 4px solid #1baf7a; padding: .2rem 1rem .6rem; margin: 1rem 0; }}
table {{ border-collapse: collapse; font-size: .85rem; margin: .6rem 0; width: 100%; }}
th, td {{ border-bottom: 1px solid #e3e3e3; padding: .3rem .5rem; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }} th {{ background: #fafafa; }}
.grafiek {{ width: 100%; margin: .6rem 0 1rem; }}
</style></head><body>
{inhoud}
<script>
const specs = {specs};
specs.forEach((s, i) => vegaEmbed('#g' + i, s, {{actions: false}}));
</script></body></html>"""
    with open(os.path.join(HIER, "rapport.html"), "w", encoding="utf-8") as f:
        f.write(pagina)
    print("rapport geschreven:", os.path.join(HIER, "rapport.html"))


if __name__ == "__main__":
    schrijf()

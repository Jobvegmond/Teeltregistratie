"""
De matrix vak × dag van de pagina Watergift, als eigen Streamlit-component
(st.components.v2): een HTML-tabel met weekkoppen, weekgrenzen, vaste kop en
eerste kolommen, tooltips per cel en klikken naar Python.

bouw_html() maakt de tabel uit een kant-en-klare structuur (zie app.py,
_wg_matrix_gegevens); toon() zet hem op het scherm en geeft terug waarop
geklikt is: "vak:<nr>" of "dag:<jjjj-mm-dd>", of None.
"""
from html import escape

import streamlit as st

from utils.format import fmt_getal

DAGEN_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]
TYPE_KLEUR = {"gewasbescherming": "#d64541", "biologie": "#2e9d5b", "voeding": "#8a6d3b"}
# Achtergrond per teeltronde in een vak (om en om), half doorzichtig zodat het in licht en donker werkt.
RONDE_KLEUR = ("rgba(76,175,80,0.20)", "rgba(142,68,173,0.17)", "rgba(214,69,120,0.15)")
OOGST = "rgba(237,161,0,0.85)"
OOGST_VERWACHT = "rgba(237,161,0,0.35)"

# Vaste breedtes van de linkerkolommen (px), zodat ze bij zijwaarts scrollen blijven staan.
LINKS = (("Vak", 44), ("Plantw.", 54), ("Leeftijd", 56), ("Totaal", 60))

CSS = """
.wg-scroll { overflow: auto; max-height: 75vh; border: 1px solid rgba(128,128,128,0.25); border-radius: 8px; }
table.wg { border-collapse: separate; border-spacing: 0; font-size: 12px; font-variant-numeric: tabular-nums;
           color: var(--st-text-color, #31333f); }
table.wg th, table.wg td { padding: 0 1px; height: 22px; width: 24px; min-width: 24px; max-width: 24px;
           text-align: center; box-sizing: border-box;
           border-bottom: 1px solid rgba(128,128,128,0.12); white-space: nowrap; }
table.wg td.c { font-size: 11px; letter-spacing: -0.2px; overflow: hidden; }
table.wg thead tr.dg th { font-size: 11px; }
table.wg thead th { position: sticky; z-index: 3; background: var(--st-background-color, #fff); font-weight: 600; }
table.wg thead tr.wk th { top: 0; height: 20px; font-size: 11px; opacity: 0.85; }
table.wg thead tr.dg th { top: 20px; height: 30px; line-height: 1.1; font-weight: 500; cursor: pointer; }
table.wg thead tr.dg th:hover { background: rgba(46,106,76,0.12); }
table.wg .l { position: sticky; z-index: 2; background: var(--st-background-color, #fff); text-align: right;
              padding-right: 6px; }
table.wg thead .l { z-index: 4; }
table.wg .l.laatste { border-right: 2px solid rgba(128,128,128,0.35); }
table.wg td.vak { font-weight: 600; cursor: pointer; }
table.wg td.vak:hover { text-decoration: underline; }
table.wg td.c { cursor: pointer; }
table.wg .weekgrens { border-left: 2px solid rgba(128,128,128,0.45); }
table.wg td.vandaag { background-image: linear-gradient(rgba(46,106,76,0.10), rgba(46,106,76,0.10)); }
table.wg thead th.vandaag { color: #fff; background: #2E6A4C; border-radius: 4px 4px 0 0; }
table.wg tr.afd td { font-weight: 700; text-align: left; padding: 8px 6px 2px; height: auto;
                     border-bottom: 1px solid rgba(128,128,128,0.35); }
table.wg tr.kw td.l { text-align: left; padding-left: 6px; font-weight: 600; }
table.wg tr.kw td { font-size: 11px; }
table.wg tr.kw td.buiten { color: #d64541; font-weight: 700; }
table.wg tr.beh td { height: 14px; font-size: 9px; border-bottom: 1px solid rgba(128,128,128,0.2); }
table.wg tr.beh span { display: inline-block; padding: 0 2px; border-radius: 3px; color: #fff; margin: 0 1px; }
table.wg td.florgib { position: relative; }
table.wg td.florgib::after { content: ""; position: absolute; top: 2px; right: 2px; width: 6px; height: 6px;
                              border-radius: 50%; background: #8e44ad; }
.wg-legenda { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 11px; margin: 6px 2px 0; opacity: 0.85; }
.wg-legenda span { display: inline-flex; align-items: center; gap: 4px; }
.wg-legenda i { display: inline-block; width: 16px; height: 12px; border-radius: 2px; }
"""

JS = """
export default function(component) {
    const { data, setTriggerValue, parentElement } = component;
    let houder = parentElement.querySelector('.wg-houder');
    if (!houder) {
        houder = document.createElement('div');
        houder.className = 'wg-houder';
        parentElement.appendChild(houder);
    }
    if (houder._html !== data) {
        const oud = houder.querySelector('.wg-scroll');
        const links = oud ? oud.scrollLeft : null;
        houder.innerHTML = data;
        houder._html = data;
        const scroll = houder.querySelector('.wg-scroll');
        // Eerste keer: vandaag in beeld, met de afgelopen weken links ervan.
        if (scroll && links === null) {
            const vandaag = scroll.querySelector('thead tr.dg th.vandaag');
            scroll.scrollLeft = vandaag ? Math.max(0, vandaag.offsetLeft - scroll.clientWidth * 0.6) : scroll.scrollWidth;
        } else if (scroll) {
            scroll.scrollLeft = links;
        }
    }
    houder.onclick = (e) => {
        const el = e.target.closest('[data-klik]');
        if (el) setTriggerValue('klik', el.getAttribute('data-klik'));
    };
}
"""

_COMPONENT = st.components.v2.component("vem_watergift_matrix", css=CSS, js=JS)


def _getal(waarde, decimalen=None):
    if waarde is None:
        return ""
    if decimalen is None:
        decimalen = 0 if waarde >= 10 else 1
    return fmt_getal(waarde, decimalen)


def _celstijl(cel, maximum):
    """
    Achtergrond: oogst oranje (verwacht: licht oranje), anders water blauw (licht →
    donker naar de gift), anders de kleur van de teeltronde (concept: gearceerd),
    en een leeg vak wit. Plantdag = groene streep links.
    """
    stijl = []
    marks = cel.get("markering")
    if marks and "oogst" in marks:
        stijl.append(f"background: {OOGST}")
    elif cel.get("liter"):
        sterkte = 0.15 + 0.75 * min(1.0, cel["liter"] / maximum) if maximum else 0.5
        stijl.append(f"background: rgba(42,120,214,{sterkte:.2f})")
        if sterkte > 0.55:
            stijl.append("color: #fff")
    elif marks and "oogst_verwacht" in marks:
        stijl.append(f"background: {OOGST_VERWACHT}")
    elif cel.get("ronde") is not None:
        kleur = RONDE_KLEUR[cel["ronde"] % len(RONDE_KLEUR)]
        if cel.get("concept"):
            stijl.append(f"background: repeating-linear-gradient(135deg, {kleur} 0 4px, transparent 4px 8px)")
        else:
            stijl.append(f"background: {kleur}")
    if marks and "plant" in marks:
        stijl.append("box-shadow: inset 3px 0 0 #2E6A4C")
    return "; ".join(stijl)


def bouw_html(m):
    """
    m = {
      "dagen": [date], "vandaag": date, "maximum": float, "toon_behandelingen": bool,
      "kwaliteit": [{"label": "EC", "cellen": [{"waarde", "buiten", "tip"}]}],
      "afdelingen": [{"naam", "vakken": [{"vak", "plantweek", "leeftijd", "totaal", "tip",
                                           "cellen": [{"liter", "bron", "markering", "tip"}],
                                           "behandelingen": [[(code, type)] per dag]}]}],
    }
    """
    dagen, vandaag = m["dagen"], m["vandaag"]
    breedte_links = [b for _, b in LINKS]
    links_px = [sum(breedte_links[:i]) for i in range(len(LINKS))]

    def links_cel(i, inhoud, tag="td", extra="", attrs=""):
        klas = "l" + (" laatste" if i == len(LINKS) - 1 else "") + (f" {extra}" if extra else "")
        return (f'<{tag} class="{klas}" style="left:{links_px[i]}px;min-width:{breedte_links[i]}px;'
                f'max-width:{breedte_links[i]}px"{attrs}>{inhoud}</{tag}>')

    def dagklasse(dag, basis=""):
        klas = [basis] if basis else []
        if dag.weekday() == 0:
            klas.append("weekgrens")
        if dag == vandaag:
            klas.append("vandaag")
        return " ".join(klas)

    # Kop: weeknummers boven de dagen, dan de dagen zelf (klik = dagpopup).
    weken = []
    for dag in dagen:
        week = dag.isocalendar()[1]
        if weken and weken[-1][0] == week:
            weken[-1][1] += 1
        else:
            weken.append([week, 1, dag])
    kop_wk = "".join(links_cel(i, "", "th") for i in range(len(LINKS)))
    kop_wk += "".join(f'<th colspan="{n}" class="{dagklasse(eerste)}">wk {w}</th>' for w, n, eerste in weken)
    kop_dg = "".join(links_cel(i, escape(naam), "th") for i, (naam, _) in enumerate(LINKS))
    kop_dg += "".join(
        f'<th class="{dagklasse(d)}" data-klik="dag:{d.isoformat()}" title="Klik voor deze dag">'
        f'{DAGEN_KORT[d.weekday()]}<br>{d.day}</th>' for d in dagen)

    rijen = []
    for kw in m["kwaliteit"]:
        cellen = "".join(
            f'<td class="{dagklasse(d, "buiten" if c["buiten"] else "")}" title="{escape(c["tip"])}">'
            f'{escape(c["waarde"])}</td>' for d, c in zip(dagen, kw["cellen"]))
        rijen.append(f'<tr class="kw"><td class="l laatste" colspan="{len(LINKS)}" style="left:0">'
                     f'{escape(kw["label"])}</td>{cellen}</tr>')
    for afd in m["afdelingen"]:
        rijen.append(f'<tr class="afd"><td class="l laatste" colspan="{len(LINKS)}" style="left:0">'
                     f'{escape(afd["naam"])}</td>' + "".join(f'<td class="{dagklasse(d)}"></td>' for d in dagen)
                     + "</tr>")
        for v in afd["vakken"]:
            klik = f' data-klik="vak:{v["vak"]}"'
            regel = (links_cel(0, v["vak"], extra="vak", attrs=f'{klik} title="{escape(v["tip"])}"')
                     + links_cel(1, escape(v["plantweek"])) + links_cel(2, escape(v["leeftijd"]))
                     + links_cel(3, escape(v["totaal"]), attrs=' title="Totale watergift van de lopende teelt (l/m²)"'))
            for d, c in zip(dagen, v["cellen"]):
                klas = ["c"]
                if c.get("markering") and "florgib" in c["markering"]:
                    klas.append("florgib")
                regel += (f'<td class="{dagklasse(d, " ".join(klas))}" style="{_celstijl(c, m["maximum"])}"'
                          f'{klik} title="{escape(c["tip"])}">{_getal(c.get("liter") or None)}</td>')
            rijen.append(f"<tr>{regel}</tr>")
            if m["toon_behandelingen"]:
                sub = "".join(links_cel(i, "") for i in range(len(LINKS)))
                for d, codes in zip(dagen, v["behandelingen"]):
                    inhoud = "".join(f'<span style="background:{TYPE_KLEUR.get(t, "#777")}">{escape(code)}</span>'
                                     for code, t in codes)
                    sub += f'<td class="{dagklasse(d)}">{inhoud}</td>'
                rijen.append(f'<tr class="beh">{sub}</tr>')

    legenda = (
        '<div class="wg-legenda">'
        '<span><i style="background:rgba(42,120,214,0.25)"></i><i style="background:rgba(42,120,214,0.9)">'
        '</i>gift l/m² (licht → veel)</span>'
        + '<span>' + "".join(f'<i style="background:{k}"></i>' for k in RONDE_KLEUR) + 'teelt (kleur per ronde)</span>'
        + f'<span><i style="background:repeating-linear-gradient(135deg,{RONDE_KLEUR[0]} 0 4px,transparent 4px 8px)">'
        '</i>concept-planning</span>'
        '<span><i style="border:1px solid rgba(128,128,128,.3)"></i>vak leeg</span>'
        '<span><i style="box-shadow:inset 3px 0 0 #2E6A4C;border:1px solid rgba(128,128,128,.3)"></i>plantdag</span>'
        '<span><i style="border-radius:50%;width:8px;height:8px;background:#8e44ad"></i>Florgib</span>'
        f'<span><i style="background:{OOGST}"></i>oogst</span>'
        f'<span><i style="background:{OOGST_VERWACHT}"></i>verwachte oogst</span>'
        '<span><i style="background:#2E6A4C"></i>vandaag</span>'
        '</div>')
    return (f'<div class="wg-scroll"><table class="wg"><thead><tr class="wk">{kop_wk}</tr>'
            f'<tr class="dg">{kop_dg}</tr></thead><tbody>{"".join(rijen)}</tbody></table></div>{legenda}')


def toon(m, sleutel):
    """Zet de matrix neer; geeft de klik van deze run terug ("vak:12" / "dag:2026-09-28") of None."""
    resultaat = _COMPONENT(data=bouw_html(m), key=sleutel, on_klik_change=lambda: None)
    return getattr(resultaat, "klik", None)

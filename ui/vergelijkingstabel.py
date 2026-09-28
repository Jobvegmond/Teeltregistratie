"""
De vergelijkingstabel: rijen = kengetallen (gegroepeerd), kolommen = de tuinen
en het totaal. Per cel:
- de waarde, met ⚠ als er minder data is dan verwacht en ⏳ als er een
  prognose of een lopende teelt in zit;
- eventueel een toelichting op een eigen kleine regel ("3 vakken");
- de vergelijkingswaarde met label ("2025: 16,8 °C"), met een groen/rood
  pijltje waar "beter" vastligt (logic/kengetallen.RICHTING).
Het verschil en de dekking ("5 van 7 dagen") staan in de tooltip van de cel.
Onder de tabel knopjes die per kengetal het verloop openen.

Gebruikt door de Tuinvergelijking en de Teeltvergelijking; de opmaak staat in
ui/styles.py.
"""
import html
from dataclasses import dataclass, field
from typing import Callable, Optional

import altair as alt
import pandas as pd
import streamlit as st

from logic import kengetallen as kg
from utils.format import LEEG, fmt_getal, fmt_verschil

TOTAAL = "Totaal"
NOOTTEKENS = "†‡§¶"


@dataclass(frozen=True)
class Kengetal:
    sleutel: str
    label: str
    groep: str
    eenheid: str = ""
    decimalen: int = 0
    uitleg: str = ""
    teken: bool = False                 # waarde altijd met + of − (bijv. afwijking lichtlijn)
    n_eenheid: Optional[str] = None     # "dagen", "vakken": waar n over gaat (tooltip, ⚠)
    formaat: Optional[Callable] = None  # eigen weergave: formaat(waarde, n) → tekst
    verschil: bool = True               # False: tekstwaarde (bijv. een datumbereik), geen pijltje/verloop


@dataclass
class Tabeldata:
    """
    Alles wat de tabel per cel nodig heeft, steeds als {kolom: {sleutel: …}}.
    - nu / toen: de waarden (toen = de vergelijking, of None)
    - n / n_toen: aantal datapunten; verwacht: hoeveel het er hadden moeten zijn (⚠ bij minder)
    - bron / bron_toen: {sleutel: tuinen die in het totaal meetellen}
    - markering: {kolom: {sleutels}} met een prognose of lopende teelt (⏳)
    - toelichting: kleine regel onder de waarde; ontbreekt: tooltip bij "–"
    - label_toen: label van de vergelijking ("2025", "wk 38", "wk 33 '25")
    """
    nu: dict
    toen: Optional[dict] = None
    n: dict = field(default_factory=dict)
    n_toen: dict = field(default_factory=dict)
    verwacht: dict = field(default_factory=dict)
    bron: Optional[dict] = None
    bron_toen: Optional[dict] = None
    markering: dict = field(default_factory=dict)
    toelichting: dict = field(default_factory=dict)
    ontbreekt: dict = field(default_factory=dict)
    label_toen: str = ""


def waarde_tekst(k, waarde, n=None):
    if k.formaat:
        return k.formaat(waarde, n)
    if waarde is None:
        return LEEG
    return fmt_verschil(waarde, k.decimalen, k.eenheid) if k.teken else fmt_getal(waarde, k.decimalen, k.eenheid)


def _vergelijk_html(k, waarde, vorig, n_vorig, label):
    """De kleine regel: label + vergelijkingswaarde, met een gekleurd pijltje waar beter vastligt."""
    if vorig is None or not label:
        return ""
    pijl, klasse = "", "neutraal"
    richting = kg.RICHTING.get(k.sleutel, 0)
    if k.verschil and waarde is not None and richting:
        afgerond = round(waarde - vorig, k.decimalen)
        klasse = kg.verschil_klasse(waarde - vorig, richting, k.decimalen)
        pijl = "▲ " if afgerond > 0 else "▼ " if afgerond < 0 else ""
    return (f'<div class="vt-vergelijk"><span class="vt-{klasse}">{pijl}</span>'
            f'<span class="vt-vergelijk-tekst">{html.escape(label)}: {waarde_tekst(k, vorig, n_vorig)}</span></div>')


def _tooltip(k, waarde, vorig, n, verwacht, ontbreekt, label):
    delen = []
    if waarde is None:
        delen.append(ontbreekt or "Geen data")
    if k.verschil and waarde is not None and vorig is not None:
        delen.append(f"Verschil met {label}: {fmt_verschil(waarde - vorig, k.decimalen, k.eenheid)}")
    if k.n_eenheid and n is not None and waarde is not None:
        delen.append(f"{fmt_getal(n)} van {fmt_getal(verwacht)} {k.n_eenheid} met data" if verwacht
                     else f"{fmt_getal(n)} {k.n_eenheid}")
    return " · ".join(delen)


def tabel_html(kengetallen, kolommen, d):
    """
    De tabel als HTML. kolommen: bijv. ["Tuin 1", "Tuin 3", "Totaal"]; d: Tabeldata.
    Een kengetal zonder waarde toont "–" (reden in de tooltip). Rust het totaal
    op één tuin, dan een voetnoot (†); het totaal wordt alleen vergeleken als
    toen dezelfde tuinen bijdroegen.
    """
    tuinen = [k for k in kolommen if k != TOTAAL]
    nu_tuinen = {t: d.nu.get(t, {}) for t in tuinen}
    toen_tuinen = {t: (d.toen or {}).get(t, {}) for t in tuinen}
    voetnoten = {}
    rijen, groep = [], None
    for k in kengetallen:
        if k.groep != groep:
            groep = k.groep
            rijen.append(f'<tr class="vt-groep"><td colspan="{len(kolommen) + 1}">{html.escape(groep)}</td></tr>')
        richting = kg.RICHTING.get(k.sleutel, 0)
        winnaar = kg.beste({t: nu_tuinen[t].get(k.sleutel) for t in tuinen}, richting, k.decimalen)
        cellen = []
        for kolom in kolommen:
            def haal(bron_dict):
                return bron_dict.get(kolom, {}).get(k.sleutel)

            waarde, n, verwacht = haal(d.nu), haal(d.n), haal(d.verwacht)
            noot = ""
            if kolom == TOTAAL:
                mee = (d.bron or {}).get(k.sleutel) if d.bron is not None else kg.bijdragers(nu_tuinen, k.sleutel)
                mee = mee or frozenset()
                if waarde is not None and k.verschil and len(mee) == 1 and len(tuinen) > 1:
                    teken = voetnoten.setdefault(next(iter(mee)), NOOTTEKENS[len(voetnoten) % len(NOOTTEKENS)])
                    noot = f'<sup class="vt-noot-teken">{teken}</sup>'
                if d.bron is not None:
                    vergelijkbaar = d.toen is not None and bool(mee) and mee == (d.bron_toen or {}).get(k.sleutel)
                else:
                    vergelijkbaar = d.toen is not None and kg.totaal_vergelijkbaar(
                        nu_tuinen, toen_tuinen, k.sleutel, {t: True for t in tuinen})
                vorig = haal(d.toen) if vergelijkbaar else None
            else:
                vorig = haal(d.toen or {})
            onvolledig = (waarde is not None and verwacht is not None and n is not None and n < verwacht)
            markering = " ⏳" if k.sleutel in d.markering.get(kolom, ()) and waarde is not None else ""
            toelichting = haal(d.toelichting)
            titel = _tooltip(k, waarde, vorig, n, verwacht, haal(d.ontbreekt), d.label_toen)
            klassen = " ".join(c for c in ("vt-totaal" if kolom == TOTAAL else "",
                                           "vt-beste" if kolom == winnaar else "") if c)
            cellen.append(
                f'<td class="{klassen}" title="{html.escape(titel)}">'
                f'<div class="vt-waarde">{waarde_tekst(k, waarde, n)}'
                f'{"<span class=vt-waarschuwing>⚠</span>" if onvolledig else ""}{markering}{noot}</div>'
                + (f'<div class="vt-toelichting">{html.escape(toelichting)}</div>' if toelichting else "")
                + _vergelijk_html(k, waarde, vorig, haal(d.n_toen), d.label_toen)
                + "</td>"
            )
        rijen.append(f'<tr class="vt-rij"><td class="vt-onderwerp" title="{html.escape(k.uitleg)}">'
                     f'{html.escape(k.label)}<span class="vt-i">ⓘ</span></td>{"".join(cellen)}</tr>')
    kop = "".join(f'<th class="{"vt-totaal" if k == TOTAAL else ""}">{html.escape(k)}</th>' for k in kolommen)
    kolgroep = '<colgroup><col class="vt-col-onderwerp">' + "<col>" * len(kolommen) + "</colgroup>"
    noten = " · ".join(f"{teken} alleen {html.escape(t)}" for t, teken in voetnoten.items())
    return (f'<div class="vt-wrap"><table class="vt">{kolgroep}<thead><tr><th></th>{kop}</tr></thead>'
            f'<tbody>{"".join(rijen)}</tbody></table>'
            + (f'<div class="vt-noot">{noten}</div>' if noten else "") + "</div>")


def toon(kengetallen, kolommen, d, sleutel="vt", verloop=None, verloop_titel="Verloop"):
    """
    Tekent de tabel en, als `verloop` gegeven is, eronder knopjes per kengetal.
    verloop(kengetal) → DataFrame met Periode, Tuin, Waarde, n (in volgorde);
    een klik opent een venster met per tuin een lijn en n per periode.
    """
    st.markdown(tabel_html(kengetallen, kolommen, d), unsafe_allow_html=True)
    if verloop is None:
        return
    # Een verloop alleen voor getallen (niet voor bijv. een datumbereik).
    per_sleutel = {k.sleutel: k for k in kengetallen if k.verschil}

    # Een keuze opent het venster en springt daarna terug, zodat hetzelfde
    # kengetal nog een keer te openen is.
    def _gekozen():
        st.session_state[f"{sleutel}_open"] = st.session_state.get(f"{sleutel}_keuze")
        st.session_state[f"{sleutel}_keuze"] = None

    st.pills(f"📈 {verloop_titel}", list(per_sleutel), format_func=lambda s: per_sleutel[s].label,
             key=f"{sleutel}_keuze", on_change=_gekozen)
    gekozen = st.session_state.pop(f"{sleutel}_open", None)
    if gekozen:
        verloop_venster(per_sleutel[gekozen], verloop(per_sleutel[gekozen]), verloop_titel)


def verloop_venster(k, df, titel):
    """Venster met het verloop van één kengetal: per tuin een lijn, daaronder n per periode."""

    @st.dialog(f"{k.label} · {titel.lower()}", width="large")
    def _venster():
        if k.uitleg:
            st.caption(k.uitleg)
        if df.empty or df["Waarde"].isna().all():
            st.info("Geen data in deze perioden.")
            return
        volgorde = list(dict.fromkeys(df["Periode"]))
        x_as = dict(sort=volgorde, title=None)
        lijn = alt.Chart(df.dropna(subset=["Waarde"])).mark_line(point=True).encode(
            x=alt.X("Periode:O", axis=alt.Axis(labels=False, ticks=False), **x_as),
            y=alt.Y("Waarde:Q", title=f"{k.label} ({k.eenheid})" if k.eenheid else k.label,
                    scale=alt.Scale(zero=False)),
            color=alt.Color("Tuin:N", title=None, legend=alt.Legend(orient="top")),
            tooltip=["Periode", "Tuin", alt.Tooltip("Waarde:Q", format=f",.{k.decimalen}f"), "n"],
        ).properties(height=220)
        staven = alt.Chart(df).mark_bar().encode(
            x=alt.X("Periode:O", axis=alt.Axis(labelAngle=-40), **x_as), xOffset="Tuin:N",
            y=alt.Y("n:Q", title=f"n ({k.n_eenheid})" if k.n_eenheid else "n"),
            color=alt.Color("Tuin:N", legend=None), tooltip=["Periode", "Tuin", "n"],
        ).properties(height=70)
        st.altair_chart(alt.vconcat(lijn, staven).resolve_scale(x="shared"), use_container_width=True)
        st.caption("Een lopende periode telt tot en met gisteren. Bij een lage n is een waarde minder betrouwbaar.")

    _venster()


def verloop_frame(rijen):
    """[{Periode, Tuin, Waarde, n}] → DataFrame in de gegeven volgorde."""
    return pd.DataFrame(rijen, columns=["Periode", "Tuin", "Waarde", "n"])

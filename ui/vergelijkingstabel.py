"""
De vergelijkingstabel: rijen = kengetallen (gegroepeerd), kolommen = de tuinen
en het totaal. In elke cel de waarde en daaronder klein het verschil met de
vergelijking, gekleurd naar betekenis (logic/kengetallen.RICHTING). Onder de
tabel knopjes die per kengetal het verloop over de laatste perioden openen.

Gebruikt door de Tuinvergelijking en de Teeltvergelijking; de opmaak staat in
ui/styles.py.
"""
import html
from dataclasses import dataclass
from typing import Callable, Optional

import altair as alt
import pandas as pd
import streamlit as st

from logic import kengetallen as kg
from utils.format import LEEG, fmt_getal, fmt_verschil

TOTAAL = "Totaal"


@dataclass(frozen=True)
class Kengetal:
    sleutel: str
    label: str
    groep: str
    eenheid: str = ""
    decimalen: int = 0
    uitleg: str = ""
    teken: bool = False                 # waarde altijd met + of − (bijv. afwijking lichtlijn)
    n_eenheid: Optional[str] = None     # "d", "teelten": toon n in de verschilregel
    formaat: Optional[Callable] = None  # eigen weergave: formaat(waarde, n) → tekst
    verschil: bool = True               # False: geen verschilregel (bijv. een datum)


def _waarde_tekst(k, waarde, n):
    if k.formaat:
        return k.formaat(waarde, n)
    if waarde is None:
        return LEEG
    return fmt_verschil(waarde, k.decimalen, k.eenheid) if k.teken else fmt_getal(waarde, k.decimalen, k.eenheid)


def _verschil_html(k, waarde, vorig, n):
    """De kleine regel onder de waarde: pijl + verschil, gekleurd naar betekenis, en eventueel n."""
    stukken = []
    if k.verschil:
        verschil = waarde - vorig if waarde is not None and vorig is not None else None
        klasse = kg.verschil_klasse(verschil, kg.RICHTING.get(k.sleutel, 0), k.decimalen)
        if verschil is None:
            stukken.append(f'<span class="vt-leeg">{LEEG}</span>')
        else:
            afgerond = round(verschil, k.decimalen)
            pijl = "↑ " if afgerond > 0 else "↓ " if afgerond < 0 else ""
            stukken.append(f'<span class="vt-{klasse}">{pijl}{fmt_verschil(verschil, k.decimalen, k.eenheid)}</span>')
    if k.n_eenheid and n:
        stukken.append(f'<span class="vt-n">n {fmt_getal(n)}{" " + k.n_eenheid if k.n_eenheid else ""}</span>')
    return f'<div class="vt-verschil">{"".join(stukken) or "&nbsp;"}</div>'


def tabel_html(kengetallen, kolommen, nu, toen=None, n=None, bron=None, bron_toen=None):
    """
    De tabel als HTML.
    - kolommen: bijv. ["Tuin 1", "Tuin 3", "Totaal"]; "Totaal" is het gewogen totaal.
    - nu / toen: {kolom: {sleutel: waarde}} (toen = de vergelijking, of None)
    - n: {kolom: {sleutel: aantal}} (optioneel)
    - bron / bron_toen: {sleutel: tuinen die in het totaal meetellen}; zonder
      bron: de tuinen met een waarde
    Een kengetal zonder waarde toont "–". Rust het totaal op één tuin, dan een
    voetnoot; een verschil bij het totaal alleen als toen dezelfde tuinen bijdroegen.
    """
    tuinen = [k for k in kolommen if k != TOTAAL]
    nu_tuinen = {t: nu.get(t, {}) for t in tuinen}
    toen_tuinen = {t: (toen or {}).get(t, {}) for t in tuinen}
    n = n or {}
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
            waarde = nu.get(kolom, {}).get(k.sleutel)
            aantal = n.get(kolom, {}).get(k.sleutel)
            noot = ""
            if kolom == TOTAAL:
                mee = bron.get(k.sleutel, frozenset()) if bron is not None else kg.bijdragers(nu_tuinen, k.sleutel)
                if waarde is not None and len(mee) == 1 and len(tuinen) > 1:
                    noot = f"<sup>{voetnoten.setdefault(next(iter(mee)), len(voetnoten) + 1)}</sup>"
                if bron is not None:
                    vergelijkbaar = toen is not None and bool(mee) and mee == (bron_toen or {}).get(k.sleutel)
                else:
                    vergelijkbaar = toen is not None and kg.totaal_vergelijkbaar(
                        nu_tuinen, toen_tuinen, k.sleutel, {t: True for t in tuinen})
                vorig = toen.get(kolom, {}).get(k.sleutel) if vergelijkbaar else None
            else:
                vorig = (toen or {}).get(kolom, {}).get(k.sleutel)
            klassen = " ".join(c for c in ("vt-totaal" if kolom == TOTAAL else "",
                                           "vt-beste" if kolom == winnaar else "") if c)
            cellen.append(
                f'<td class="{klassen}"><div class="vt-waarde">{_waarde_tekst(k, waarde, aantal)}{noot}</div>'
                f"{_verschil_html(k, waarde, vorig, aantal)}</td>"
            )
        rijen.append(f'<tr class="vt-rij"><td class="vt-onderwerp" title="{html.escape(k.uitleg)}">'
                     f'{html.escape(k.label)}<span class="vt-i">ⓘ</span></td>{"".join(cellen)}</tr>')
    kop = "".join(f'<th class="{"vt-totaal" if k == TOTAAL else ""}">{html.escape(k)}</th>' for k in kolommen)
    kolgroep = '<colgroup><col class="vt-col-onderwerp">' + "<col>" * len(kolommen) + "</colgroup>"
    noten = " · ".join(f"<sup>{nr}</sup> alleen {html.escape(t)}" for t, nr in voetnoten.items())
    return (f'<div class="vt-wrap"><table class="vt">{kolgroep}<thead><tr><th></th>{kop}</tr></thead>'
            f'<tbody>{"".join(rijen)}</tbody></table>'
            + (f'<div class="vt-noot">{noten}</div>' if noten else "") + "</div>")


def toon(kengetallen, kolommen, nu, toen=None, n=None, sleutel="vt", verloop=None, verloop_titel="Verloop",
         bron=None, bron_toen=None):
    """
    Tekent de tabel en, als `verloop` gegeven is, eronder knopjes per kengetal.
    verloop(kengetal) → DataFrame met Periode, Tuin, Waarde, n (in volgorde);
    een klik opent een venster met per tuin een lijn en n per periode.
    """
    st.markdown(tabel_html(kengetallen, kolommen, nu, toen, n, bron, bron_toen), unsafe_allow_html=True)
    if verloop is None:
        return
    per_sleutel = {k.sleutel: k for k in kengetallen}

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

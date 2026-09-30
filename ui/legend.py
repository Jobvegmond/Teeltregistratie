"""
Legenda's (UI-standaard, docs/ui-standaard.md): elke matrix of grafiek met
kleuren of symbolen krijgt direct eronder een zichtbare legenda.

    legenda([
        {"kleur": "#5b9bd5", "label": "gift (l/m²)"},
        {"kleur": "#f5a623", "label": "oogst", "vorm": "blok"},
        {"kleur": "#1f1f1f", "label": "Florgib", "vorm": "ring"},
    ])

Vormen: blok (standaard), rand (alleen omlijnd), stippelrand, lijn, stip,
ruit, ring. `tekst` zet een teken in het blokje (bijv. een getal of ✓).
"""
import html

import streamlit as st

CSS = """
<style>
.vem-legenda { display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; font-size: 0.74rem; margin: 0.25rem 0 0.7rem; }
.vem-legenda .item { display: inline-flex; align-items: center; gap: 0.3rem; }
.vem-legenda .item .titel { font-weight: 600; opacity: 0.75; margin-right: -0.2rem; }
.vem-legenda i {
    display: inline-flex; align-items: center; justify-content: center; flex: none;
    width: 0.95rem; height: 0.95rem; border-radius: 0.2rem; font-style: normal;
    font-size: 0.6rem; font-weight: 700; border: 1px solid rgba(128, 128, 128, 0.35);
}
.vem-legenda i.rand { background: transparent !important; border-width: 2px; }
.vem-legenda i.stippelrand { background: transparent !important; border-width: 2px; border-style: dotted; }
.vem-legenda i.lijn { height: 0; border-width: 1.5px 0 0; border-radius: 0; width: 1.1rem; }
.vem-legenda i.stip { border-radius: 50%; width: 0.6rem; height: 0.6rem; }
.vem-legenda i.ring { border-radius: 50%; background: transparent !important; border-width: 2px; }
.vem-legenda i.ruit { transform: rotate(45deg) scale(0.75); border-radius: 0.1rem; }
</style>
"""


def _item(i):
    vorm = i.get("vorm", "blok")
    kleur = i.get("kleur") or "transparent"
    stijl = f"background:{kleur};"
    if vorm in ("rand", "stippelrand", "ring", "lijn"):
        stijl = f"border-color:{kleur};"
    if i.get("tekstkleur"):
        stijl += f"color:{i['tekstkleur']};"
    if i.get("stijl"):
        stijl += i["stijl"]
    teken = html.escape(str(i.get("tekst", "")))
    return (f'<span class="item"><i class="{vorm}" style="{stijl}">{teken}</i>'
            f'{html.escape(i["label"])}</span>')


def legenda_html(items, titel=None):
    """De legenda als HTML (voor wie hem in een eigen component zet)."""
    kop = f'<span class="item"><span class="titel">{html.escape(titel)}</span></span>' if titel else ""
    return f'<div class="vem-legenda">{kop}{"".join(_item(i) for i in items)}</div>'


def legenda(items, titel=None):
    """Zichtbare legenda direct onder een matrix of grafiek."""
    st.markdown(CSS + legenda_html(items, titel), unsafe_allow_html=True)

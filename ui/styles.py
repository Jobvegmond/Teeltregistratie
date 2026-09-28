"""
De CSS van de gedeelde schermonderdelen, op één plek. laad() zet hem één
keer per pagina neer; de vergelijkingstabellen (ui/vergelijkingstabel.py)
gebruiken de klassen .vt-*.

Licht en donker: tekst erft de themakleur; lijnen en achtergronden zijn
half doorzichtig grijs/groen, zodat ze op beide thema's werken. Alleen de
vaste kopregel en eerste kolom hebben een dekkende achtergrond nodig (anders
schuift de tabel er zichtbaar onderdoor); die komt uit het actieve thema.
"""
import streamlit as st

# Achtergrond van het Streamlit-thema (licht/donker), voor de vaste kop en kolom.
ACHTERGROND = {"light": "#ffffff", "dark": "#0e1117"}

CSS = """
.vt-wrap { max-width: 900px; margin: 0.25rem 0 0.4rem; }
.vt-wrap.vt-breed { max-width: none; overflow-x: auto; }
table.vt {
    width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed;
    font-variant-numeric: tabular-nums;
}
table.vt col.vt-col-onderwerp { width: 220px; }
table.vt th, table.vt td {
    padding: 5px 16px; text-align: right; vertical-align: top;
    border-bottom: 1px solid rgba(128, 128, 128, 0.18);
}
table.vt thead th {
    position: sticky; top: 3.75rem; z-index: 2; background: var(--vt-bg);
    font-size: 13px; font-weight: 600; opacity: 1;
    border-bottom: 1px solid rgba(128, 128, 128, 0.45);
}
table.vt th:first-child, table.vt td:first-child {
    text-align: left; position: sticky; left: 0; z-index: 1; background: var(--vt-bg);
}
table.vt thead th:first-child { z-index: 3; }
table.vt tbody tr:nth-child(even of .vt-rij) td { background-image: linear-gradient(rgba(128, 128, 128, 0.035), rgba(128, 128, 128, 0.035)); }
table.vt td.vt-onderwerp { font-size: 14px; cursor: help; padding-top: 7px; }
table.vt td.vt-onderwerp .vt-i { font-size: 11px; opacity: 0.45; margin-left: 4px; }
table.vt .vt-waarde { font-size: 15.5px; font-weight: 600; line-height: 1.15; white-space: nowrap; }
table.vt .vt-verschil { font-size: 12px; line-height: 1.1; margin-top: 2px; white-space: nowrap; }
table.vt .vt-n { opacity: 0.55; margin-left: 6px; }
table.vt th.vt-totaal, table.vt td.vt-totaal {
    border-left: 1px solid rgba(128, 128, 128, 0.35);
    background-image: linear-gradient(rgba(128, 128, 128, 0.06), rgba(128, 128, 128, 0.06));
}
table.vt td.vt-beste { background-image: linear-gradient(rgba(46, 160, 67, 0.13), rgba(46, 160, 67, 0.13)); }
table.vt tr.vt-groep td {
    padding: 16px 16px 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.07em;
    text-transform: uppercase; opacity: 0.6; border-bottom: none; background: none;
}
.vt-beter { color: #2e9a44; }
.vt-slechter { color: #d64541; }
.vt-neutraal, .vt-leeg { opacity: 0.55; }
.vt-noot { font-size: 12px; opacity: 0.7; margin: 2px 0 6px; }
.vt-noot sup, table.vt sup { font-size: 10px; margin-left: 1px; }
"""


def laad():
    """Zet de CSS op de pagina, met de achtergrond van het actieve thema."""
    thema = getattr(getattr(st.context, "theme", None), "type", None) or "light"
    achtergrond = st.get_option("theme.backgroundColor") or ACHTERGROND.get(thema, ACHTERGROND["light"])
    st.markdown(f"<style>:root {{ --vt-bg: {achtergrond}; }}{CSS}</style>", unsafe_allow_html=True)

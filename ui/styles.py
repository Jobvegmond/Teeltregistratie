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
/* Keuze- en invoervelden op het hoofdscherm niet breder dan nodig: op een
   breed scherm oogt een smal veld strakker. De zijbalk en popups houden hun
   eigen breedte. */
[data-testid="stMain"] [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stMultiSelect"],
[data-testid="stMain"] [data-testid="stDateInput"],
[data-testid="stMain"] [data-testid="stTextInput"],
[data-testid="stMain"] [data-testid="stNumberInput"],
[data-testid="stMain"] [data-testid="stSelectSlider"] { max-width: 360px; }
[data-testid="stMain"] [data-testid="stTextArea"] { max-width: 720px; }
/* Paginaopbouw (ui/layout.py): titel met de knop Uitleg ernaast, sectiekoppen, filterbalk. */
.st-key-vem_paginakop { margin: 0.1rem 0 0.2rem; }
.vem-paginatitel { font-size: 1.35rem; font-weight: 700; line-height: 1.2; }
.vem-sectie { font-size: 1rem; font-weight: 600; margin: 0.6rem 0 0.1rem; }
.vem-sectie span { font-weight: 400; opacity: 0.65; }
[class*="st-key-filterbalk_"] { flex-wrap: wrap; row-gap: 0.5rem; margin-bottom: 0.4rem; }
[class*="st-key-filterbalk_"] [data-testid="stCheckbox"] { padding-bottom: 0.45rem; }
/* Zijbalk: 360 px breed (standaard 300), zodat Florgib · Oogst · Opmerking · Wijzigen op één regel passen en
   de invoervelden ruimte hebben. Alleen uitgeklapt (inklappen blijft werken); slepen aan de rand kan nog
   breder. Op een telefoon nooit breder dan het scherm. Minder opvulling in de knoppengroepen. */
[data-testid="stSidebar"][aria-expanded="true"] { min-width: min(360px, 100vw); }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button { padding-left: 10px; padding-right: 10px; }
/* Pills (afdelingen, overige filters) hebben in Streamlit een vaste pilvorm; dezelfde ronding als de
   andere knoppen (theme.buttonRadius). */
button[data-variant="pills"] { border-radius: 0.2rem; }
/* ◀ [label ▾] ▶ (ui/filters.bladeraar): het label als vette knop met vaste minimumbreedte. */
[class*="st-key-bladeraar_"] [data-testid="stPopover"] button { min-width: 9rem; font-weight: 600; }
.vt-wrap { max-width: 900px; margin: 0.25rem 0 0.4rem; }
.vt-wrap.vt-breed { max-width: none; overflow-x: auto; }
table.vt {
    width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed;
    font-variant-numeric: tabular-nums;
}
table.vt col.vt-col-onderwerp { width: 200px; }
table.vt th, table.vt td {
    padding: 5px 14px; text-align: right; vertical-align: top;
    border-bottom: 1px solid rgba(128, 128, 128, 0.18);
    overflow-wrap: anywhere;
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
table.vt td.vt-onderwerp { font-size: 14px; cursor: help; padding-top: 7px; overflow-wrap: normal; }
table.vt td.vt-onderwerp .vt-i { font-size: 11px; opacity: 0.45; margin-left: 4px; }
table.vt .vt-waarde { font-size: 15.5px; font-weight: 600; line-height: 1.2; }
table.vt .vt-toelichting { font-size: 12px; line-height: 1.15; opacity: 0.6; margin-top: 1px; }
table.vt .vt-vergelijk { font-size: 12px; line-height: 1.15; margin-top: 2px; }
table.vt .vt-vergelijk-tekst { opacity: 0.6; }
table.vt .vt-waarschuwing { font-size: 12px; margin-left: 4px; color: #c98a00; font-weight: 400; }
table.vt sup.vt-noot-teken { font-size: 10px; font-weight: 400; opacity: 0.55; margin-left: 3px; }
table.vt th.vt-totaal, table.vt td.vt-totaal {
    border-left: 1px solid rgba(128, 128, 128, 0.35);
    background-image: linear-gradient(rgba(128, 128, 128, 0.06), rgba(128, 128, 128, 0.06));
}
table.vt td.vt-beste { background-image: linear-gradient(rgba(46, 160, 67, 0.13), rgba(46, 160, 67, 0.13)); }
table.vt tr.vt-groep td {
    padding: 16px 14px 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.07em;
    text-transform: uppercase; opacity: 0.6; border-bottom: none; background: none;
}
.vt-beter { color: #2e9a44; }
.vt-slechter { color: #d64541; }
.vt-neutraal, .vt-leeg { opacity: 0.55; }
.vt-noot { font-size: 12px; opacity: 0.7; margin: 2px 0 6px; }
"""


def laad():
    """Zet de CSS op de pagina, met de achtergrond van het actieve thema."""
    thema = getattr(getattr(st.context, "theme", None), "type", None) or "light"
    achtergrond = st.get_option("theme.backgroundColor") or ACHTERGROND.get(thema, ACHTERGROND["light"])
    st.markdown(f"<style>:root {{ --vt-bg: {achtergrond}; }}{CSS}</style>", unsafe_allow_html=True)

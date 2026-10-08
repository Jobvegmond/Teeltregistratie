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
/* Paginaopbouw (ui/layout.py): de knop Uitleg klein rechts in de rij met de tuinkeuze, sectiekoppen,
   filterbalk. Geen paginatitel: de gevulde knop in de navigatiebalk laat de pagina zien. */
/* Streamlit verpakt elk blok in een stLayoutWrapper: de rij met de tuinkeuze over de hele breedte, de
   knop Uitleg daarin helemaal rechts. */
[data-testid="stLayoutWrapper"]:has(> .st-key-vem_tuinkeuze) { flex: 1 1 auto; width: 100%; }
[data-testid="stLayoutWrapper"]:has(> .st-key-vem_uitleg) { margin-left: auto; }
.st-key-vem_uitleg [data-testid="stPopover"] button { min-height: 0; padding: 0.1rem 0.55rem; }
.st-key-vem_uitleg [data-testid="stPopover"] button p,
.st-key-vem_uitleg [data-testid="stPopover"] button span { font-size: 0.8rem; }
.vem-sectie { font-size: 1rem; font-weight: 600; margin: 0.6rem 0 0.1rem; }
.vem-sectie span { font-weight: 400; opacity: 0.65; }
[class*="st-key-filterbalk_"] { flex-wrap: wrap; row-gap: 0.5rem; margin-bottom: 0.4rem; }
[class*="st-key-filterbalk_"] [data-testid="stCheckbox"] { padding-bottom: 0.45rem; }
/* Zijbalk: 330 px breed (standaard 300), net breed genoeg dat Florgib · Oogst · Opmerking · Wijzigen op één regel passen en
   de invoervelden ruimte hebben. Alleen uitgeklapt (inklappen blijft werken); slepen aan de rand kan nog
   breder. Op een telefoon nooit breder dan het scherm. Minder opvulling in de knoppengroepen. */
[data-testid="stSidebar"][aria-expanded="true"] { min-width: min(330px, 100vw); }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button { padding-left: 10px; padding-right: 10px; }
/* Pills (afdelingen, overige filters) hebben in Streamlit een vaste pilvorm; dezelfde ronding als de
   andere knoppen (theme.buttonRadius). */
button[data-variant="pills"] { border-radius: 0.2rem; }
/* ◀ [label ▾] ▶ (ui/filters.bladeraar): het label als vette knop met vaste minimumbreedte. */
[class*="st-key-bladeraar_"] [data-testid="stPopover"] button { min-width: 9rem; font-weight: 600; }
/* Vergelijkingstabel (ui/vergelijkingstabel.py), strak: alleen horizontale lijnen, geen zebra, waarden
   nooit afgebroken. Streamlit zet om elke cel van een markdown-tabel een rand; die gaat eraf. Past de tabel
   niet (smal scherm), dan schuift hij zijwaarts met de eerste kolom vast. */
.vt-wrap { max-width: 900px; margin: 0.25rem 0 0.4rem; }
.vt-wrap.vt-breed { max-width: none; overflow-x: auto; }
/* Smal scherm: de tabel schuift zijwaarts in zijn eigen kader; de vaste kopregel rekent dan vanaf dat kader,
   dus daar bovenaan (top 0) in plaats van onder de balk van Streamlit. */
@media (max-width: 900px) { .vt-wrap { overflow-x: auto; } .vt-wrap table.vt thead th { top: 0; } }
table.vt {
    width: 100%; border-collapse: separate; border-spacing: 0; table-layout: auto;
    font-variant-numeric: tabular-nums; border: none;
}
table.vt col.vt-col-onderwerp { width: 170px; }
table.vt th, table.vt td {
    padding: 4px 10px; text-align: right; vertical-align: top; white-space: nowrap;
    border: none; border-bottom: 1px solid rgba(128, 128, 128, 0.16);
}
table.vt thead th {
    position: sticky; top: 3.75rem; z-index: 2; background: var(--vt-bg);
    font-size: 12.5px; font-weight: 600; opacity: 1; padding-top: 6px; padding-bottom: 5px;
    border-bottom: 1.5px solid rgba(128, 128, 128, 0.5);
}
table.vt th:first-child, table.vt td:first-child {
    text-align: left; position: sticky; left: 0; z-index: 1; background: var(--vt-bg);
}
table.vt thead th:first-child { z-index: 3; }
table.vt td.vt-onderwerp { font-size: 14.5px; cursor: help; padding-top: 5px; white-space: normal; min-width: 130px; }
table.vt td.vt-onderwerp .vt-i { font-size: 10.5px; opacity: 0.45; margin-left: 4px; }
table.vt .vt-waarde { font-size: 13.5px; font-weight: 500; line-height: 1.35; }
table.vt .vt-toelichting { font-size: 11.5px; line-height: 1.15; opacity: 0.6; }
table.vt .vt-vergelijk { font-size: 11.5px; line-height: 1.15; margin-top: 1px; }
table.vt .vt-vergelijk-tekst { opacity: 0.6; }
table.vt .vt-waarschuwing { font-size: 11.5px; margin-left: 4px; color: #c98a00; font-weight: 400; }
table.vt sup.vt-noot-teken { font-size: 10px; font-weight: 400; opacity: 0.55; margin-left: 3px; }
table.vt th.vt-totaal, table.vt td.vt-totaal {
    border-left: 1px solid rgba(128, 128, 128, 0.3);
    background-image: linear-gradient(rgba(128, 128, 128, 0.05), rgba(128, 128, 128, 0.05));
}
table.vt td.vt-beste { background-image: linear-gradient(rgba(46, 160, 67, 0.13), rgba(46, 160, 67, 0.13)); }
table.vt tr.vt-groep td {
    padding: 12px 10px 3px; font-size: 10.5px; font-weight: 700; letter-spacing: 0.07em;
    text-transform: uppercase; opacity: 0.6; border-bottom: 1px solid rgba(128, 128, 128, 0.3); background: none;
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

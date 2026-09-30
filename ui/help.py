"""
Uitleg op één manier (UI-standaard, docs/ui-standaard.md):

- uitleg(): de knop "Uitleg" rechts naast de paginatitel. Opent een popover met
  altijd dezelfde kopjes, in deze volgorde: Wat zie je · Hoe lees je het ·
  Waar komen de getallen vandaan · Wat betekenen de kleuren. Een kopje zonder
  tekst valt weg.
- voetnoot(): hooguit één korte regel onder een tabel of grafiek. Langere
  tekst hoort in de Uitleg.
- ⓘ-tooltips alleen bij losse kengetallen en kolomkoppen: gebruik daarvoor de
  help=-parameter van Streamlit of de help-tekst van toon_kengetallen.
"""
import streamlit as st

KOPJES = (
    ("wat", "Wat zie je"),
    ("lezen", "Hoe lees je het"),
    ("bron", "Waar komen de getallen vandaan"),
    ("kleuren", "Wat betekenen de kleuren"),
)


def _tekst(waarde):
    """Een tekst of een lijst regels (wordt een opsomming)."""
    if isinstance(waarde, (list, tuple)):
        return "\n".join(f"- {regel}" for regel in waarde)
    return waarde


def uitleg_inhoud(wat=None, lezen=None, bron=None, kleuren=None):
    """De inhoud van de uitleg (ook los te gebruiken, bijv. in een popup)."""
    teksten = {"wat": wat, "lezen": lezen, "bron": bron, "kleuren": kleuren}
    for sleutel, kop in KOPJES:
        if teksten[sleutel]:
            st.markdown(f"**{kop}**")
            st.markdown(_tekst(teksten[sleutel]))


def uitleg(wat=None, lezen=None, bron=None, kleuren=None, plek=None):
    """De knop "Uitleg" met de popover; `plek` = de container waarin de knop staat (standaard de pagina)."""
    with (plek or st).popover("Uitleg", icon=":material/help:", width="content"):
        with st.container(width=560):
            uitleg_inhoud(wat, lezen, bron, kleuren)


def voetnoot(tekst):
    """Eén korte regel onder een tabel of grafiek."""
    st.caption(tekst)

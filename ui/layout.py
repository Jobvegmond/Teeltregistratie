"""
De vaste paginaopbouw (UI-standaard, docs/ui-standaard.md). Elke pagina, van
boven naar beneden:

  a. pagina_kop(): de knop "Uitleg" (rechts in de kop, naast de tuinkeuze); geen titel, want de gevulde knop
     in de navigatiebalk laat al zien op welke pagina je bent;
  b. filterbalk(): één regel met de keuzes uit ui/filters.py;
  c. samenvatting (tabel);
  d. hoofdweergave (matrix, tabel of grafiek), met legenda eronder (ui/legend.py);
  e. uitklap(): aanvullende lijsten in openklapmenu's;
  f. export(): de downloadknop(pen).
"""
import streamlit as st

from ui import help as uitleg_help


def kop_plek(plek):
    """De plek voor de knop Uitleg: rechts in de rij met de tuinkeuze. app.py zet hem elke run vóór de pagina."""
    st.session_state["_vem_kop_plek"] = plek


def pagina_kop(titel, **uitleg):
    """
    De knop "Uitleg" van de pagina, klein rechts in de kop (zie kop_plek; zonder plek gewoon op de pagina).
    `uitleg` = wat, lezen, bron, kleuren (zie ui/help.py). `titel` wordt niet getoond: de gevulde knop in de
    navigatiebalk laat de pagina al zien; hij staat er voor wie de code leest.
    """
    if any(uitleg.values()):
        uitleg_help.uitleg(plek=st.session_state.get("_vem_kop_plek"), **uitleg)


def filterbalk(sleutel):
    """Eén regel keuzes, links uitgelijnd en op de onderkant van de velden; loopt door op een smal scherm."""
    return st.container(horizontal=True, vertical_alignment="bottom", gap="medium", key=f"filterbalk_{sleutel}")


def sectie(titel, aantal=None):
    """Kopje boven een blok (samenvatting, hoofdweergave)."""
    st.markdown(f'<div class="vem-sectie">{titel}' + (f' <span>({aantal})</span>' if aantal is not None else "")
                + "</div>", unsafe_allow_html=True)


def uitklap(titel, aantal=None, open=False):
    """Openklapmenu voor aanvullende lijsten (onderdeel e)."""
    return st.expander(f"{titel} ({aantal})" if aantal is not None else titel, expanded=open)


def export(data, bestandsnaam, label="Excel", sleutel=None, mime=None):
    """Downloadknop onderaan de pagina (onderdeel f); `data` = bytes of tekst."""
    if mime is None and bestandsnaam.endswith(".xlsx"):
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    st.download_button(label, data, file_name=bestandsnaam, mime=mime, key=sleutel,
                       icon=":material/download:", width="content")

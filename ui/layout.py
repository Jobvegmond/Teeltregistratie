"""
De vaste paginaopbouw (UI-standaard, docs/ui-standaard.md). Elke pagina, van
boven naar beneden:

  a. pagina_kop(): de knop "Uitleg" (rechts in de kopbalk met de tabbladknoppen en de tuinkeuze); geen
     titel, want de gevulde knop in de navigatiebalk laat al zien op welke pagina je bent;
  b. filterbalk(): één regel met de keuzes uit ui/filters.py;
  c. samenvatting (tabel);
  d. hoofdweergave (matrix, tabel of grafiek), met legenda eronder (ui/legend.py);
  e. uitklap(): aanvullende lijsten in openklapmenu's;
  f. export(): de downloadknop(pen).

Elk tabblad heeft een nummer (1. Overzicht, 2. Teelt, …) en elke sectie en elk openklapmenu daarop een
volgnummer ("2.3"), zodat je bij feedback precies kunt zeggen welk scherm je bedoelt. app.py zet het nummer
van de pagina met begin_pagina(); sectie() en uitklap() tellen zelf door.
"""
import streamlit as st

from ui import help as uitleg_help


def kop_plek(plek):
    """De plek voor de knop Uitleg: rechts in de kopbalk. app.py zet hem elke run vóór de pagina."""
    st.session_state["_vem_kop_plek"] = plek


def begin_pagina(nummer):
    """Het nummer van het tabblad; de secties en openklapmenu's tellen vanaf hier (nummer.1, nummer.2, …)."""
    st.session_state["_vem_nummer"] = [nummer, 0]


def _volgnummer():
    """Het volgende schermnummer op deze pagina ("2.3"), of "" buiten een pagina."""
    teller = st.session_state.get("_vem_nummer")
    if not teller:
        return ""
    teller[1] += 1
    return f"{teller[0]}.{teller[1]}"


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
    """Kopje boven een blok (samenvatting, hoofdweergave), met het schermnummer ervoor."""
    nummer = _volgnummer()
    st.markdown('<div class="vem-sectie">' + (f'<b class="vem-nr">{nummer}</b>' if nummer else "") + titel
                + (f' <span>({aantal})</span>' if aantal is not None else "") + "</div>", unsafe_allow_html=True)


def uitklap(titel, aantal=None, open=False):
    """Openklapmenu voor aanvullende lijsten (onderdeel e), met het schermnummer ervoor."""
    nummer = _volgnummer()
    label = f"{titel} ({aantal})" if aantal is not None else titel
    return st.expander(f"{nummer}  {label}" if nummer else label, expanded=open)


def export(data, bestandsnaam, label="Excel", sleutel=None, mime=None):
    """Downloadknop onderaan de pagina (onderdeel f); `data` = bytes of tekst."""
    if mime is None and bestandsnaam.endswith(".xlsx"):
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    st.download_button(label, data, file_name=bestandsnaam, mime=mime, key=sleutel,
                       icon=":material/download:", width="content")

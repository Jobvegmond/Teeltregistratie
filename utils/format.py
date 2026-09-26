"""
Getallen in Nederlandse notatie, op één plek: komma als decimaalteken, punt
als duizendtalscheiding (1.111.400 en 20,4 °C). Een ontbrekende waarde
(None of NaN) wordt LEEG, nooit 0.

Voor tekst (tegels, captions, verschilregels) de fmt_-functies; voor
Altair-grafieken het thema "vem_nl" (as- en tooltip-opmaak met dezelfde
tekens); voor st.dataframe getalkolom().
"""
import math

# Streamlit en Altair pas in de functies die ze nodig hebben: database.py en
# de losse scripts (Priva-taak) gebruiken alleen de fmt_-functies.

LEEG = "–"

# d3-format-locale voor Vega/Altair: dezelfde notatie in grafieken.
D3_NUMBER_LOCALE = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["€ ", ""]}


def _ontbreekt(x):
    if x is None:
        return True
    try:
        return math.isnan(float(x))
    except (TypeError, ValueError):
        return True


def fmt_getal(x, decimalen=0, eenheid=""):
    """1234567.8 -> "1.234.568" (0 decimalen) of "1.234.567,8" (1); met eenheid erachter."""
    if _ontbreekt(x):
        return LEEG
    tekst = f"{float(x):,.{decimalen}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    if tekst.startswith("-"):
        tekst = "−" + tekst[1:]
    if tekst in ("−0", ) or (tekst.startswith("−0,") and set(tekst[3:]) == {"0"}):
        tekst = tekst[1:]  # geen "−0,0"
    return f"{tekst} {eenheid}" if eenheid else tekst


def fmt_kort(x, max_decimalen=2, eenheid=""):
    """Zonder overbodige nullen: 12.0 -> "12", 12.5 -> "12,5" (voor emmers, weken)."""
    if _ontbreekt(x):
        return LEEG
    tekst = fmt_getal(x, max_decimalen)
    if "," in tekst:
        tekst = tekst.rstrip("0").rstrip(",")
    return f"{tekst} {eenheid}" if eenheid else tekst


def fmt_pct(x, decimalen=1):
    """8.0 -> "8,0 %" (x is al een percentage, geen fractie)."""
    return fmt_getal(x, decimalen, "%")


def fmt_temp(x, decimalen=1):
    """19.94 -> "19,9 °C"."""
    return fmt_getal(x, decimalen, "°C")


def fmt_weken(x, decimalen=1):
    """7.24 -> "7,2 wk"."""
    return fmt_getal(x, decimalen, "wk")


def fmt_dagen(x, decimalen=0):
    """52.4 -> "52 dgn"."""
    return fmt_getal(x, decimalen, "dgn")


def fmt_verschil(x, decimalen=1, eenheid=""):
    """
    Verschil met teken: "+1,2 °C", "−0,4 %", en "0,0" zonder teken als het
    afgerond nul is. Een ontbrekend verschil is LEEG.
    """
    if _ontbreekt(x):
        return LEEG
    if round(float(x), decimalen) == 0:
        return fmt_getal(0, decimalen, eenheid)
    teken = "+" if x > 0 else "−"
    return teken + fmt_getal(abs(float(x)), decimalen, eenheid)


def getalkolom(label=None, decimalen=0, **kwargs):
    """
    st.column_config.NumberColumn in de notatie van de browser (in een
    Nederlandse browser: 1.234,5) met een vast aantal decimalen. Streamlit
    kent geen vaste locale voor tabellen; "localized" volgt de browsertaal.
    """
    import streamlit as st

    return st.column_config.NumberColumn(label, format="localized", step=10 ** -decimalen, **kwargs)


def _vem_nl_thema():
    return {"config": {"locale": {"number": D3_NUMBER_LOCALE}}}


def zet_altair_nl():
    """Zet het Altair-thema met de Nederlandse getalnotatie aan (één keer bij het opstarten)."""
    import altair as alt

    alt.theme.register("vem_nl", enable=True)(_vem_nl_thema)

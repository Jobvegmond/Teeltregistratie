import html
import io
import math
import os
import re
import secrets
import urllib.parse

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, date
from database import (
    init_db,
    get_lopende_teelten,
    update_halverwege,
    update_oogst,
    get_overzicht_dataframe,
    get_weeknummer,
    format_datum,
    get_alle_teelten_voor_selectie,
    get_teelt_by_id,
    update_teelt_volledig,
    delete_teelt,
    voeg_oogstregistratie_toe,
    get_oogstregistraties_voor_teelt,
    get_totaal_emmers_per_teelt,
    wijzig_oogstregistratie,
    verwijder_oogstregistratie,
    markeer_teelt_afgerond,
    get_gebruikers_credentials,
    verwerk_klimaat_csv,
    importeer_klimaat_uit_priva,
    get_klimaat_overzicht_dataframe,
    afdeling_van_vak,
    get_klimaatdata_dagen_voor_periode,
    get_klimaatdata_dekking,
    get_klimaat_voor_periode,
    importeer_watergift_uit_priva,
    get_watergift_dekking,
    get_watergift_voor_periode,
    get_watergift_dagen_voor_periode,
    verwerk_energie_csv,
    get_energiedata_dagen_voor_periode,
    get_energiedata_dekking,
    get_gasdata_dekking,
    get_gasdata_dagen_voor_periode,
    get_warmte_voor_periode,
    GAS_CALORISCHE_WAARDE_MJ_PER_M3,
    oppervlakte_van_tuin,
    ideale_etmaaltemperatuur,
    LICHT_TEMP_FACTOR,
    LICHT_TEMP_BASIS,
    get_teeltduur,
    teeltduur_voor_plantweek,
    get_alle_teelten_detail,
    get_isojaar_week,
    get_wijzigingenlog,
    get_planning,
    get_planning_per_week,
    voeg_planning_toe,
    wijzig_planning,
    verwijder_planning,
    bevestig_planning,
    plan_x_weken_vooruit,
    planner_eenheden,
    MAX_VAKKEN_PER_WEEK,
    get_planning_weekoverzicht,
    set_planning_weekdoel,
    set_planning_weekdoel_vak1,
    wis_planning_weekdoelen,
    bereken_verwachte_oogstdatum,
    get_strokenplanning,
    get_oogstregistraties_voor_periode,
    get_watergift_per_vak_voor_periode,
    get_watergift_per_dag_voor_periode,
    get_instelling,
    set_instelling,
    get_stekweken,
    get_teeltkengetallen,
    get_rassen,
    zet_ras,
    get_tuinen,
    get_tuin_id,
    get_vaknummers,
    get_standaard_tuin_van_gebruiker,
    zet_actieve_tuin,
    stelen_bij_60_van_vak,
    STANDAARD_RAS,
    get_stek_voor_week,
    sla_stekbeoordeling_op,
    stek_uitval_pct,
    verdeel_bakjes,
    STEK_KEUZES,
    STEK_STANDAARD_RAS,
)

# --- PAGINA-INSTELLINGEN ---
# Moet de eerste Streamlit-aanroep zijn. Bepaalt o.a. de titel van het
# browsertabblad.
st.set_page_config(page_title="VEM teeltregistratie", page_icon="🌱", layout="wide")

# Gedeelde opmaak voor de hele app: kengetallen-tegels en de compacte kop.
st.markdown("""
<style>
/* Kengetallen: compacte tegels in een raster dat de regel vult (ca. 7 per rij op
   een laptop, 2 op een telefoon), i.p.v. brede st.metric-kaders met veel lege ruimte. */
.vem-kg-titel {
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; opacity: 0.6; margin: 0.9rem 0 0.35rem;
}
.vem-kg {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr));
    gap: 0.4rem; margin-bottom: 0.4rem;
}
.vem-kg-tegel {
    border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 0.4rem;
    padding: 0.35rem 0.55rem; line-height: 1.25;
}
.vem-kg-label { font-size: 0.72rem; opacity: 0.7; }
.vem-kg-label abbr { text-decoration: none; cursor: help; opacity: 0.8; margin-left: 0.2rem; }
.vem-kg-waarde { font-size: 1rem; font-weight: 600; margin-top: 0.1rem; }
.vem-kg-delta { font-size: 0.68rem; opacity: 0.65; margin-top: 0.1rem; }

/* Compacte kop: titel links, week + datum rechts, altijd op één regel. */
.vem-kop {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 0.75rem; margin: 0 0 0.75rem 0; padding-bottom: 0.4rem;
    border-bottom: 1px solid rgba(128, 128, 128, 0.25);
}
.vem-titel { font-size: 1.15rem; font-weight: 600; }
.vem-week { font-size: 0.85rem; opacity: 0.7; white-space: nowrap; }

/* Minder lege ruimte boven de inhoud; nog wel onder de vaste Streamlit-balk (3.75rem). */
[data-testid="stMainBlockContainer"], .block-container { padding-top: 3.75rem !important; }
</style>
""", unsafe_allow_html=True)


# Vaste kleur per afdeling, zodat afd. 1 overal dezelfde kleur heeft.
AFDELING_KLEUR = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#eda100"}


# --- GRAFIEKEN: gedeelde instellingen (één plek, zodat alle grafieken gelijk ogen) ---

# Datumas als dd-mm: nooit Engelse maandnamen ("Oct", "Nov") op de as.
DATUM_FORMAAT_AS = "%d-%m"

# Dag/nacht/24h onderscheiden zich per afdeling alleen in dikte, helderheid en
# stippeling — nooit in kleur (rood is gereserveerd voor waarschuwingen).
# 24h = donker en dik, dag = licht, nacht = gestippeld.
DEEL_VOLGORDE = ["24h", "dag", "nacht"]
DEEL_DASH = [[1, 0], [1, 0], [2, 3]]
DEEL_OPACITY = [1.0, 0.45, 1.0]
DEEL_BREEDTE = [2.5, 1.5, 1.5]


def datum_as(titel=None, veld="datum"):
    """X-as voor datums, als dd-mm."""
    return alt.X(f"{veld}:T", title=titel, axis=alt.Axis(format=DATUM_FORMAAT_AS, labelOverlap=True))


def y_as(veld, titel, domein=None, **kwargs):
    """
    Y-as die niet automatisch vanaf 0 begint (dat verspilt ruimte bij
    temperatuur, RV en lengte). Met `domein` een vaste schaal, bijv. om
    meerdere lagen dezelfde as te laten delen.
    """
    schaal = alt.Scale(domain=domein, clamp=True) if domein else alt.Scale(zero=False)
    return alt.Y(f"{veld}:Q", title=titel, scale=schaal, **kwargs)


def gedeeld_domein(*reeksen, marge=1.0):
    """[laag, hoog] met wat marge om alle opgegeven waarden heen, of None zonder waarden."""
    waarden = [w for reeks in reeksen for w in reeks if pd.notna(w)]
    if not waarden:
        return None
    return [math.floor(min(waarden) - marge), math.ceil(max(waarden) + marge)]


def afdeling_kleur(labels):
    """Vaste kleur per afdeling ("Afd. 3" -> AFDELING_KLEUR[3])."""
    labels = sorted(labels)
    return alt.Color(
        "Afdeling:N",
        scale=alt.Scale(
            domain=labels,
            range=[AFDELING_KLEUR.get(int(lbl.split()[-1]), "#8a8a80") for lbl in labels],
        ),
        legend=alt.Legend(title=None, orient="top"),
    )


def deel_encoding(toon_dagnacht):
    """Encoding-kanalen voor 24h/dag/nacht; zonder dag/nacht één effen lijn."""
    if not toon_dagnacht:
        return {"strokeDash": alt.value([1, 0]), "strokeWidth": alt.value(2)}
    legenda = alt.Legend(title=None, orient="bottom")

    def _schaal(bereik):
        return alt.Scale(domain=DEEL_VOLGORDE, range=bereik)

    return {
        "strokeDash": alt.StrokeDash("Deel:N", scale=_schaal(DEEL_DASH), legend=legenda),
        "opacity": alt.Opacity("Deel:O", scale=_schaal(DEEL_OPACITY), legend=legenda),
        "strokeWidth": alt.StrokeWidth("Deel:O", scale=_schaal(DEEL_BREEDTE), legend=legenda),
    }


def toon_grafiek(chart, data, melding, waardekolom=None):
    """Toont de grafiek, of een korte melding i.p.v. een leeg vlak als er niets te tekenen valt."""
    leeg = data is None or data.empty
    if not leeg and waardekolom is not None:
        leeg = data[waardekolom].dropna().empty
    if leeg:
        st.info(melding)
        return
    st.altair_chart(chart, use_container_width=True)


def lijngrafiek_per_afdeling(lang, y_titel, toon_dagnacht=True, formaat=".1f",
                             melding="Geen klimaatdata in deze periode."):
    """
    Lijngrafiek per afdeling uit een lange tabel met kolommen datum, Afdeling
    ("Afd. 3"), Deel ("24h"/"dag"/"nacht") en waarde. Eén kleur per afdeling.
    """
    if lang is not None and not lang.empty:
        lang = lang.dropna(subset=["waarde"]).copy()
        if not toon_dagnacht:
            lang = lang[lang["Deel"] == "24h"]
        lang["datum"] = pd.to_datetime(lang["datum"])
    chart = None
    if lang is not None and not lang.empty:
        chart = alt.Chart(lang).mark_line().encode(
            x=datum_as(), y=y_as("waarde", y_titel),
            color=afdeling_kleur(lang["Afdeling"].unique()),
            tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Afdeling:N", "Deel:N",
                     alt.Tooltip("waarde:Q", title=y_titel, format=formaat)],
            **deel_encoding(toon_dagnacht),
        )
    toon_grafiek(chart, lang, melding, waardekolom="waarde")


# --- TABELLEN: gedeelde weergave ---

def toon_tabel(df, kolommen, verberg_leeg=False, pin_eerste=False):
    """
    Toont een DataFrame als nette tabel volgens `kolommen`: een lijst van
    (kolom, label, soort, formaat, breedte) met soort "tekst", "getal" of
    "datum". Alleen die kolommen worden getoond, in die volgorde.
    - "-" en lege tekst zijn echt leeg. Streamlit toont een ontbrekend getal
      of ontbrekende datum als "None"; een kolom met lege cellen wordt daarom
      tekst met lege cellen (getallen met cijferspaties tot gelijke breedte,
      zodat sorteren nog op getalvolgorde loopt). Kolommen zonder gaten blijven
      echte getal-/datumkolommen (rechts uitgelijnd, sorteren klopt);
    - een kolom met iets dat niet als getal/datum (dd-mm-jj) te lezen is blijft
      tekst; er verdwijnt niets;
    - breedte: "small"/"medium"/"large" of een aantal pixels; "small" wordt
      afgeleid van de lengte van de kolomkop, zodat er zoveel mogelijk
      kolommen op het scherm passen;
    - verberg_leeg: kolommen zonder één waarde worden weggelaten;
    - pin_eerste: eerste kolom blijft staan bij zijwaarts scrollen.
    """
    df = df.copy()
    df = df.mask(df.isin(["-", ""]))
    config, volgorde = {}, []
    for kolom, label, soort, formaat, breedte in kolommen:
        if kolom not in df.columns:
            continue
        if verberg_leeg and df[kolom].isna().all():
            continue
        f = formaat or "%d"
        if soort in ("getal", "datum"):
            gelezen = (
                pd.to_numeric(df[kolom], errors="coerce") if soort == "getal"
                else pd.to_datetime(df[kolom], format="%d-%m-%y", errors="coerce")
            )
            if gelezen.isna().sum() > df[kolom].isna().sum():
                soort = "tekst"  # niet alles leesbaar: laat de kolom ongemoeid
            else:
                if gelezen.isna().any():  # gaten: tekst met echt lege cellen
                    if soort == "getal":
                        tekst = gelezen.map(lambda v: "" if pd.isna(v) else f % v)
                        breed = tekst.str.len().max()
                        gelezen = tekst.map(lambda t: t.rjust(breed, " ") if t else t)
                    else:
                        gelezen = gelezen.map(lambda v: "" if pd.isna(v) else v.strftime("%d-%m-%y"))
                    soort = "tekst"
                df[kolom] = gelezen
        if soort == "tekst":
            df[kolom] = df[kolom].fillna("").astype(str)
        if breedte == "small":
            breedte = int(max(85 if soort == "datum" else 60, 26 + 6.5 * len(label)))
        elif breedte == "medium":
            breedte = 105
        elif breedte == "large":
            breedte = 320
        if soort == "getal":
            config[kolom] = st.column_config.NumberColumn(label, format=f, width=breedte)
        elif soort == "datum":
            config[kolom] = st.column_config.DateColumn(label, format="DD-MM-YY", width=breedte)
        else:
            config[kolom] = st.column_config.TextColumn(label, width=breedte)
        volgorde.append(kolom)
    if pin_eerste and volgorde:
        config[volgorde[0]]["pinned"] = True
    st.dataframe(df[volgorde], hide_index=True, column_config=config)


def toon_kengetallen(items, titel=None):
    """
    Toont kengetallen (lijst dicts met label, waarde en optioneel delta en
    help) als compacte tegels in een raster dat zelf bepaalt hoeveel er naast
    elkaar passen. Met `titel` komt er een klein kopje boven de groep.

    Eigen HTML i.p.v. st.metric: st.metric in st.columns gaf brede, hoge
    kaders met veel lege ruimte en liet zich niet compacter krijgen.
    """
    if not items:
        return
    tegels = []
    for item in items:
        uitleg = item.get("help")
        uitleg_html = f' <abbr title="{html.escape(uitleg)}">ⓘ</abbr>' if uitleg else ""
        delta = item.get("delta")
        delta_html = ""
        if delta:
            tekst = str(delta).strip()
            getal = re.match(r"[+\-−]?(\d+(?:[.,]\d+)?)", tekst)
            nul = getal is not None and float(getal.group(1).replace(",", ".")) == 0
            pijl = "" if nul else "↑ " if tekst.startswith("+") else "↓ " if tekst.startswith(("-", "−")) else ""
            delta_html = f'<div class="vem-kg-delta">{pijl}{html.escape(tekst)}</div>'
        tegels.append(
            '<div class="vem-kg-tegel">'
            f'<div class="vem-kg-label">{html.escape(str(item["label"]))}{uitleg_html}</div>'
            f'<div class="vem-kg-waarde">{html.escape(str(item["waarde"]))}</div>'
            f"{delta_html}</div>"
        )
    kop = f'<div class="vem-kg-titel">{html.escape(titel)}</div>' if titel else ""
    st.markdown(f'{kop}<div class="vem-kg">{"".join(tegels)}</div>', unsafe_allow_html=True)


def jaargemiddelden_oogst(jaar):
    """
    Gemiddelde taklengte, takgewicht, gewicht per 10 cm, lengtefactor
    (oogst/halverwege) en uitval over alle teelten die in `jaar` zijn
    afgerond (datum_oogst) — voor vergelijking met een losse plantweek-
    groep in Teelt-detail. Waarden zijn None als er geen data is.
    """
    alle = get_alle_teelten_detail()
    emmers_per_teelt = get_totaal_emmers_per_teelt()
    lengtes, gewichten, factoren, gewicht_10cm, uitval = [], [], [], [], []
    for t in alle:
        if not t["datum_oogst"] or not t["datum_oogst"].startswith(str(jaar)):
            continue
        if t["lengte_eind"]:
            lengtes.append(t["lengte_eind"])
        if t["oogstgewicht"]:
            gewichten.append(t["oogstgewicht"])
        if t["lengte_half"] and t["lengte_eind"]:
            factoren.append(t["lengte_eind"] / t["lengte_half"])
        if t["oogstgewicht"] and t["lengte_eind"]:
            gewicht_10cm.append(t["oogstgewicht"] / t["lengte_eind"] * 10)
        # Zonder emmers én zonder vastgelegd percentage is de uitval onbekend,
        # niet 100% (bijv. als de emmers nog niet zijn ingevoerd).
        uitval_t = uitval_van_teelt(t, emmers_per_teelt)
        if uitval_t is not None:
            uitval.append(uitval_t)

    def _gem(lijst):
        return sum(lijst) / len(lijst) if lijst else None

    return {
        "lengte": _gem(lengtes),
        "gewicht": _gem(gewichten),
        "factor": _gem(factoren),
        "gewicht_10cm": _gem(gewicht_10cm),
        "uitval": _gem(uitval),
    }


def klimaat_grafieken(dagen_records, toon_dagnacht=False, toon_trend=False, licht_max=2500):
    """
    Tekent twee grafieken uit dagrecords (dicts met datum, afdeling, temp_24h,
    temp_dag, temp_nacht, rv_24h, rv_dag, rv_nacht, lichtsom):
    1) temperatuur als lijn (linker-as, niet vanaf 0, gedeeld door alle
       temperatuurlagen) gecombineerd met de lichtsom per dag als staaf
       (rechter-as 0..licht_max, gemiddeld over de gekozen afdelingen);
    2) relatieve luchtvochtigheid als lijn.
    Met toon_trend loopt er een dik voortschrijdend 14-daags gemiddelde door de
    temperatuur- en lichtsomlijn. De assen zijn temporeel, dus altijd
    chronologisch. Per afdeling één kleur; dag/nacht/24h verschillen alleen in
    helderheid, dikte en stippeling.
    """
    if not dagen_records:
        st.info("Geen klimaatdata in deze periode.")
        return

    df = pd.DataFrame(dagen_records)
    df["datum"] = pd.to_datetime(df["datum"])
    df["Afdeling"] = "Afd. " + df["afdeling"].astype(str)
    kleur = afdeling_kleur(df["Afdeling"].unique())
    x_as = datum_as()

    def _lang(prefix):
        varianten = [(f"{prefix}_24h", "24h")]
        if toon_dagnacht:
            varianten += [(f"{prefix}_dag", "dag"), (f"{prefix}_nacht", "nacht")]
        etiket = dict(varianten)
        lang = df.melt(
            id_vars=["datum", "Afdeling"], value_vars=list(etiket),
            var_name="_v", value_name="waarde",
        ).dropna(subset=["waarde"])
        lang["Deel"] = lang["_v"].map(etiket)
        return lang

    temp_lang = _lang("temp")
    licht = df.groupby("datum", as_index=False)["lichtsom"].mean().dropna(subset=["lichtsom"])
    licht["ideaal"] = ideale_etmaaltemperatuur(licht["lichtsom"])

    # Alle temperatuurlagen moeten dezelfde schaal delen (de lagen hebben elk
    # een eigen y-as), dus één vast domein rond temperatuur én ideaal.
    temp_domein = gedeeld_domein(temp_lang["waarde"], licht["ideaal"])

    temp_lagen = []
    if not licht.empty:
        temp_lagen.append(alt.Chart(licht).mark_bar(color="#e7c98a", opacity=0.75).encode(
            x=x_as,
            y=alt.Y("lichtsom:Q", title="Lichtsom per dag",
                    scale=alt.Scale(domain=[0, licht_max], clamp=True)),
            tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                     alt.Tooltip("lichtsom:Q", title="lichtsom", format=".0f")],
        ))
    if not temp_lang.empty:
        temp_lagen.append(alt.Chart(temp_lang).mark_line().encode(
            x=x_as, y=y_as("waarde", "Temperatuur (°C)", temp_domein),
            color=kleur,
            tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                     "Afdeling:N", "Deel:N", alt.Tooltip("waarde:Q", title="°C", format=".1f")],
            **deel_encoding(toon_dagnacht),
        ))
    if not licht.empty:
        temp_lagen.append(
            alt.Chart(licht).mark_line(color="#c0392b", strokeWidth=3, strokeDash=[6, 3]).encode(
                x=x_as, y=y_as("ideaal", None, temp_domein, axis=None),
                tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                         alt.Tooltip("ideaal:Q", title="ideale temp °C", format=".1f")],
            )
        )
    if toon_trend and not temp_lang.empty:
        temp_trend_df = (
            df.groupby("datum", as_index=False)["temp_24h"].mean().dropna(subset=["temp_24h"])
            .sort_values("datum")
        )
        temp_trend_df["trend"] = (
            temp_trend_df["temp_24h"].rolling(14, center=True, min_periods=3).mean()
        )
        licht_trend = licht.sort_values("datum").copy()
        licht_trend["trend"] = licht_trend["lichtsom"].rolling(14, center=True, min_periods=3).mean()
        temp_lagen += [
            alt.Chart(licht_trend).mark_line(color="#c79a3e", strokeWidth=3).encode(
                x=x_as, y=alt.Y("trend:Q", scale=alt.Scale(domain=[0, licht_max], clamp=True), axis=None),
            ),
            alt.Chart(temp_trend_df).mark_line(color="#333", strokeWidth=3).encode(
                x=x_as, y=y_as("trend", None, temp_domein, axis=None),
                tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                         alt.Tooltip("trend:Q", title="trend °C", format=".1f")],
            ),
        ]

    st.caption(
        "Temperatuur (lijn, links) + lichtsom per dag (staaf, gemiddeld over de afdelingen, rechts). "
        f"Rode stippellijn = ideale temperatuur bij dat licht ({LICHT_TEMP_FACTOR} x lichtsom + "
        f"{LICHT_TEMP_BASIS} °C) — temperatuurlijn erboven is relatief te warm, eronder te koud."
        + (" Dikke effen lijn = 14-daags voortschrijdend gemiddelde." if toon_trend else "")
        + (" Per afdeling: donker = 24h, licht = dag, gestippeld = nacht." if toon_dagnacht else "")
    )
    toon_grafiek(
        alt.layer(*temp_lagen).resolve_scale(y="independent") if temp_lagen else None,
        temp_lang, "Geen temperatuurdata in deze periode.", waardekolom="waarde",
    )

    st.caption("Relatieve luchtvochtigheid (%)")
    lijngrafiek_per_afdeling(
        _lang("rv"), "RV (%)", toon_dagnacht=toon_dagnacht, formaat=".0f",
        melding="Geen luchtvochtigheidsdata in deze periode.",
    )


def licht_temperatuur_grafiek(dagen_records):
    """
    Zet de werkelijke en de ideale etmaaltemperatuur (op basis van de
    lichtsom van diezelfde dag) als twee lijnen op de tijdlijn — zo is in
    1 oogopslag te zien wanneer er structureel te warm of te koud gestookt
    wordt t.o.v. het gerealiseerde licht. Vervangt een eerdere puntenwolk
    (temperatuur tegen lichtsom), die met meer data onoverzichtelijk werd.
    """
    df = pd.DataFrame(dagen_records)
    if not df.empty:
        df = df.dropna(subset=["lichtsom", "temp_24h"])
    if df.empty:
        st.info("Geen gekoppelde lichtsom/temperatuur in deze periode.")
        return

    df["datum"] = pd.to_datetime(df["datum"])
    df["Afdeling"] = "Afd. " + df["afdeling"].astype(str)
    df["ideaal"] = ideale_etmaaltemperatuur(df["lichtsom"])
    kleur = afdeling_kleur(df["Afdeling"].unique())
    lang = df.melt(
        id_vars=["datum", "Afdeling"], value_vars=["temp_24h", "ideaal"],
        var_name="_v", value_name="waarde",
    ).dropna(subset=["waarde"])
    lang["Type"] = lang["_v"].map({"temp_24h": "Werkelijk", "ideaal": "Ideaal (obv licht)"})

    chart = alt.Chart(lang).mark_line().encode(
        x=datum_as(),
        y=y_as("waarde", "Etmaaltemperatuur (°C)"),
        color=kleur,
        strokeDash=alt.StrokeDash("Type:N", legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Afdeling:N", "Type:N",
                 alt.Tooltip("waarde:Q", title="°C", format=".1f")],
    )
    st.caption(
        f"Ideaal = {LICHT_TEMP_FACTOR} x lichtsom + {LICHT_TEMP_BASIS} °C van diezelfde dag. "
        "Werkelijk boven ideaal: relatief te warm gestookt voor het licht. Eronder: te koud."
    )
    toon_grafiek(chart, lang, "Geen gekoppelde lichtsom/temperatuur in deze periode.", waardekolom="waarde")


# --- INITIALISATIE ---
@st.cache_resource
def _database_klaarzetten():
    """Draai init_db() één keer per serverstart in plaats van bij elke rerun."""
    init_db()


_database_klaarzetten()


# --- INLOG ---
@st.cache_resource
def _tijdelijke_cookie_key():
    """Eén willekeurige sleutel per draaiende server (fallback als AUTH_COOKIE_KEY ontbreekt)."""
    return secrets.token_hex(32)


def _cookie_key():
    sleutel = os.environ.get("AUTH_COOKIE_KEY")
    if sleutel:
        return sleutel
    st.warning(
        "AUTH_COOKIE_KEY is niet gezet; er wordt een tijdelijke sleutel gebruikt. "
        "Zet AUTH_COOKIE_KEY in je .env zodat je ingelogd blijft na een herstart."
    )
    return _tijdelijke_cookie_key()


_DAGEN_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]
_vandaag_kop = date.today()
st.markdown(
    '<div class="vem-kop">'
    '<span class="vem-titel">🌱 Teeltregistratie</span>'
    f'<span class="vem-week">Week {_vandaag_kop.isocalendar()[1]} · '
    f'{_DAGEN_KORT[_vandaag_kop.weekday()]} {format_datum(_vandaag_kop)}</span>'
    '</div>',
    unsafe_allow_html=True,
)

_credentials = get_gebruikers_credentials()

if not _credentials["usernames"]:
    st.warning(
        "Er zijn nog geen gebruikers aangemaakt. Voeg er een toe met:\n\n"
        '`python beheer_gebruikers.py toevoegen <gebruikersnaam> "<Volledige naam>"`'
    )
    st.stop()

authenticator = stauth.Authenticate(
    _credentials,
    cookie_name="teeltregistratie",
    cookie_key=_cookie_key(),
    cookie_expiry_days=7,
)

authenticator.login(
    location="main",
    fields={
        "Form name": "Inloggen",
        "Username": "Gebruikersnaam",
        "Password": "Wachtwoord",
        "Login": "Inloggen",
    },
)

_auth_status = st.session_state.get("authentication_status")
if _auth_status is False:
    st.error("❌ Gebruikersnaam of wachtwoord is onjuist.")
    st.stop()
if _auth_status is None:
    st.info("Log in om de teeltregistratie te gebruiken.")
    st.stop()

# Vanaf hier is de gebruiker ingelogd.
st.sidebar.caption(f"👤 Ingelogd als {st.session_state.get('name')}")
authenticator.logout("Uitloggen", location="sidebar")

# --- TUIN KIEZEN ---
#
# Eén app voor beide tuinen, met de tuin als keuze bovenaan. Alles wat daarna
# uit de database komt gaat over die tuin: teelten, klimaat, water, energie en
# het registratieformulier. Zo kun je niet per ongeluk op de verkeerde tuin
# registreren, en kun je de tuinen wel naast elkaar leggen.
TUINEN = get_tuinen()
_standaard_tuin = get_standaard_tuin_van_gebruiker(st.session_state.get("username"))
if "tuin_nummer" not in st.session_state:
    st.session_state["tuin_nummer"] = _standaard_tuin

_tuin_labels = {t["nummer"]: t["naam"] for t in TUINEN}
_tuin_nummers = [t["nummer"] for t in TUINEN]
if len(_tuin_nummers) > 1:
    _kolom_tuin, _kolom_leeg = st.columns([2, 5])
    _keuze = _kolom_tuin.segmented_control(
        "Tuin", _tuin_nummers, format_func=lambda n: _tuin_labels.get(n, f"Tuin {n}"),
        default=st.session_state["tuin_nummer"], key="tuin_keuze", label_visibility="collapsed",
    )
    if _keuze:
        st.session_state["tuin_nummer"] = _keuze

TUIN_NUMMER = st.session_state["tuin_nummer"]
TUIN_ID = get_tuin_id(TUIN_NUMMER)
TUIN_NAAM = _tuin_labels.get(TUIN_NUMMER, f"Tuin {TUIN_NUMMER}")
# Vanaf hier werken alle databasefuncties zonder expliciete tuin op deze tuin.
zet_actieve_tuin(TUIN_ID)
st.sidebar.caption(f"🏡 {TUIN_NAAM}")


def huidige_gebruiker():
    """Identificeert de ingelogde gebruiker voor het wijzigingenlog."""
    return st.session_state.get("username") or st.session_state.get("name")


ANDER_RAS = "➕ Ander ras…"
RIJPHEID_OPTIES = [1, 2, 3, 4]


def rijpheid_bereik_naar_tekst(bereik):
    """Zet een (min, max) rijpheid-bereik om naar tekst, bijv. (1, 1) -> '1', (1, 3) -> '1-3'."""
    laag, hoog = bereik
    if laag == hoog:
        return str(laag)
    return f"{laag}-{hoog}"


def rijpheid_tekst_naar_bereik(tekst):
    """Zet opgeslagen rijpheid-tekst om naar een (min, max)-tuple voor de slider."""
    if not tekst:
        return (1, 4)
    try:
        if "-" in tekst:
            laag, hoog = tekst.split("-", 1)
            return (int(laag), int(hoog))
        waarde = int(tekst)
        return (waarde, waarde)
    except ValueError:
        return (1, 4)


def bereken_aantal_stelen(vaknummer, stelen_per_m2, tuin_id=None):
    """
    Vooringevuld aantal stelen voor een vak bij de gekozen plantdichtheid
    (40, 50 of 60 stelen per m²), herschaald vanaf de basiswaarde bij 60
    stelen/m² van dat vak. Die basiswaarde staat per vak in de database
    (halve vakken hebben er de helft van), zodat beide tuinen dezelfde
    berekening gebruiken.
    """
    basis_60 = stelen_bij_60_van_vak(int(vaknummer), tuin_id) or 0
    return round(basis_60 / 60 * stelen_per_m2)


def standaard_dichtheid_voor_plantweek(week):
    """
    Standaard plantdichtheid (stelen per m²) per plantweek: 60 in week 1-37,
    50 in week 38-41, 40 in week 42-47, 50 in week 48-53. Wordt gebruikt om
    het aantal planten automatisch vooraf in te vullen op basis van de
    startdatum; je kunt de dichtheid altijd handmatig overschrijven.
    """
    if 38 <= week <= 41:
        return 50
    if 42 <= week <= 47:
        return 40
    if 48 <= week <= 53:
        return 50
    return 60


def uitval_van_teelt(teelt, emmers_per_teelt):
    """
    Uitval van een teelt in procenten: uit de getelde emmers als die er zijn
    (100 stelen per emmer), anders het percentage dat bij de teelt zelf staat.
    Geeft None als geen van beide bekend is; dan is de uitval onbekend, niet 0.

    `emmers_per_teelt` is het totaal per teelt uit get_totaal_emmers_per_teelt();
    dat wordt één keer per scherm opgehaald in plaats van per teelt.
    """
    planten = teelt.get("aantal_planten")
    emmers = emmers_per_teelt.get(teelt["id"]) if planten else None
    if emmers:
        return (planten - emmers * 100) / planten * 100
    return teelt.get("uitval_pct")


def toon_oogstregistraties_beheer(teelt_id, teelt_info):
    """
    Toont de al geregistreerde oogstmomenten (emmers) voor een teelt: totaal,
    uitvalpercentage en per moment de mogelijkheid om het aan te passen (💾)
    of te verwijderen (🗑️). Wordt zowel gebruikt bij het registreren van
    oogst (voor lopende teelten) als bij het wijzigen van een teelt (ook
    voor afgeronde teelten, om het aantal emmers achteraf te corrigeren).
    """
    registraties = get_oogstregistraties_voor_teelt(teelt_id)
    if not registraties:
        st.caption("Nog geen oogst geregistreerd.")
        return

    totaal_emmers = sum(r[2] for r in registraties)
    samenvatting = f"{totaal_emmers:g} emmers"
    if teelt_info.get("aantal_planten"):
        uitval_pct = (
            (teelt_info["aantal_planten"] - totaal_emmers * 100) / teelt_info["aantal_planten"] * 100
        )
        samenvatting += f" · {uitval_pct:.1f}% uitval"
    st.caption(samenvatting)

    for reg_id, reg_datum, reg_emmers in registraties:
        col_datum, col_aantal, col_opslaan, col_verwijder = st.columns([2, 2, 1, 1])
        col_datum.write(format_datum(reg_datum))
        nieuw_aantal = col_aantal.number_input(
            "Aantal emmers",
            min_value=0, step=1, value=int(reg_emmers),
            key=f"edit_emmer_{reg_id}",
            label_visibility="collapsed",
        )
        if col_opslaan.button("💾", key=f"save_emmer_{reg_id}", help="Wijziging opslaan"):
            wijzig_oogstregistratie(reg_id, reg_datum, nieuw_aantal, gebruiker=huidige_gebruiker())
            st.rerun()
        if col_verwijder.button("🗑️", key=f"del_emmer_{reg_id}", help="Oogstmoment verwijderen"):
            verwijder_oogstregistratie(reg_id, gebruiker=huidige_gebruiker())
            st.rerun()

# Zijbalk voor invoer. Een nieuwe teelt begint niet hier maar in het tabblad
# Planning: daar staat het concept al klaar en zet je het met één knop om in
# een lopende teelt.
st.sidebar.header("Registratie")

FLORGIB, OOGST, WIJZIGEN = "Florgib lengte", "Oogst", "Wijzigen of verwijderen"
actie = st.sidebar.radio("Wat wil je doen?", [FLORGIB, OOGST, WIJZIGEN])

# Elke actie krijgt een eigen plek in de zijbalk; de plekken van de andere twee
# blijven leeg. Streamlit ruimt namelijk alleen op wat het opnieuw tekent: zonder
# die vaste plekken bleven de velden van de vorige keuze er grijs onder staan.
_paneel = {naam: st.sidebar.empty() for naam in (FLORGIB, OOGST, WIJZIGEN)}
with _paneel[actie].container():

    # --- ACTIE 2: HALVERWEGE VOOR MEERDERE VAKKEN ---
    if actie == FLORGIB:
    
        # Alleen teelten die nog lopen én nog geen Florgib-lengte hebben: zodra je
        # er een invult, verdwijnt hij uit de lijst, dus wat er staat moet nog.
        lopende = get_lopende_teelten(zonder_florgib=True)

        if lopende:
            keuzes = {label: teelt_id for teelt_id, label in lopende}
        
            # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
            datum_half = st.date_input(
                "Datum", key="half_datum", format="DD-MM-YYYY"
            )
            week_half = get_weeknummer(datum_half)
            st.caption(f"Week {week_half}")

            with st.form("half_form"):
                geselecteerde_labels = st.multiselect(
                    "Teelten", list(keuzes.keys())
                )

                lengte_half = st.number_input("Lengte (cm)", min_value=0.0, format="%.1f")
            
                submit_half = st.form_submit_button("Opslaan")
            
                if submit_half and geselecteerde_labels:
                    successen = []
                    fouten = []
                
                    for label in geselecteerde_labels:
                        geselecteerd_id = keuzes[label]
                        try:
                            update_halverwege(geselecteerd_id, datum_half, lengte_half, gebruiker=huidige_gebruiker())
                            successen.append(f"✅ {label}")
                        except Exception as e:
                            fouten.append(f"❌ {label}: {e}")
                
                    if successen:
                        st.success(
                            f"Opgeslagen voor {len(successen)} teelten."
                        )
                    if fouten:
                        st.warning("Mislukt:\n" + "\n".join(fouten))
                
                    if successen:
                        st.rerun()
                elif submit_half and not geselecteerde_labels:
                    st.warning("Kies minstens één teelt.")
        else:
            st.info("Alle lopende teelten hebben hun Florgib-lengte al.")

    # --- ACTIE 3: UITVAL (EMMERS) + OOGSTGEWICHT EN LENGTE ---
    elif actie == OOGST:

        tab_uitval, tab_eind = st.tabs(["🪣 Emmers", "📏 Lengte en gewicht"])

        # --- TABBLAD: UITVAL (EMMERS, 100 STELEN PER EMMER) ---
        with tab_uitval:
            lopende_uitval = get_lopende_teelten()

            if lopende_uitval:
                keuzes_uitval = {label: teelt_id for teelt_id, label in lopende_uitval}

                uitval_label = st.selectbox(
                    "Teelt", list(keuzes_uitval.keys()), key="uitval_selectie"
                )
                uitval_id = keuzes_uitval[uitval_label]
                huidige_uitval = get_teelt_by_id(uitval_id)

                st.caption(
                    f"Vak {huidige_uitval['vaknummer']} · {huidige_uitval['code'] or '-'}"
                    + (f" · {huidige_uitval['aantal_planten']} planten" if huidige_uitval["aantal_planten"] else "")
                )

                if "emmers_form_versie" not in st.session_state:
                    st.session_state["emmers_form_versie"] = 0

                with st.form("emmers_form"):
                    datum_emmers = st.date_input(
                        "Datum", key="emmers_datum", format="DD-MM-YYYY"
                    )
                    st.caption(f"Week {get_weeknummer(datum_emmers)}")
                    aantal_emmers = st.number_input("Emmers", min_value=0, step=1)
                    laatste_emmers = st.checkbox(
                        "Teelt afronden",
                        key=f"emmers_laatste_{st.session_state['emmers_form_versie']}",
                    )

                    submit_emmers = st.form_submit_button("Opslaan")

                    if submit_emmers:
                        if aantal_emmers > 0:
                            voeg_oogstregistratie_toe(uitval_id, datum_emmers, aantal_emmers, gebruiker=huidige_gebruiker())
                            if laatste_emmers:
                                markeer_teelt_afgerond(uitval_id, datum_emmers, gebruiker=huidige_gebruiker())
                                st.success(f"{aantal_emmers} emmers opgeslagen, teelt afgerond.")
                            else:
                                st.success(f"{aantal_emmers} emmers opgeslagen.")
                            # Nieuwe key voor het vinkje bij de volgende weergave, zodat het
                            # altijd weer uit staat na het opslaan (i.p.v. aan te blijven staan).
                            st.session_state["emmers_form_versie"] += 1
                            st.rerun()
                        else:
                            st.warning("Vul een aantal emmers in.")

                toon_oogstregistraties_beheer(uitval_id, huidige_uitval)
            else:
                st.info("Geen lopende teelten. Start ze in het tabblad Planning.")

        # --- TABBLAD: OOGSTGEWICHT EN LENGTE ---
        with tab_eind:
            # Alleen teelten die nog niet zijn afgerond bij de uitval.
            alle_teelten = get_lopende_teelten()

            if alle_teelten:
                keuzes_eind = {label: teelt_id for teelt_id, label in alle_teelten}

                with st.form("oogst_form"):
                    geselecteerde_labels = st.multiselect(
                        "Teelten", list(keuzes_eind.keys())
                    )

                    lengte_eind = st.number_input("Lengte (cm)", min_value=0.0, format="%.1f")
                    oogstgewicht = st.number_input("Gewicht (g)", min_value=0, step=1)
                    rijpheid_bereik = st.select_slider(
                        "Rijpheid", options=RIJPHEID_OPTIES, value=(1, 4),
                        help="1 = rauw, 4 = rijp. Zet beide punten gelijk voor één stadium.",
                    )

                    submit_oogst = st.form_submit_button("Opslaan")

                    if submit_oogst and geselecteerde_labels:
                        successen = []
                        fouten = []
                        rijpheid_tekst = rijpheid_bereik_naar_tekst(rijpheid_bereik)

                        for label in geselecteerde_labels:
                            try:
                                update_oogst(
                                    keuzes_eind[label], lengte_eind, oogstgewicht, rijpheid_tekst,
                                    gebruiker=huidige_gebruiker(),
                                )
                                successen.append(f"✅ {label}")
                            except Exception as e:
                                fouten.append(f"❌ {label}: {e}")

                        if successen:
                            st.success(f"Opgeslagen voor {len(successen)} teelten.")
                        if fouten:
                            st.warning("Mislukt:\n" + "\n".join(fouten))
                        if successen:
                            st.rerun()
                    elif submit_oogst and not geselecteerde_labels:
                        st.warning("Kies minstens één teelt.")
            else:
                st.info("Geen lopende teelten.")

    # --- ACTIE 4: WIJZIGEN / VERWIJDEREN ---
    elif actie == WIJZIGEN:

        alle_teelten = get_alle_teelten_voor_selectie()

        if alle_teelten:
            keuzes = {label: teelt_id for teelt_id, label in alle_teelten}
            geselecteerd_label = st.selectbox(
                "Teelt", list(keuzes.keys()), key="wijzig_selectie"
            )
            geselecteerd_id = keuzes[geselecteerd_label]
            huidige = get_teelt_by_id(geselecteerd_id)

            st.caption(f"Vak {huidige['vaknummer']} · {huidige['code'] or '-'}")

            # Het ras staat buiten het formulier, zodat "Ander ras" meteen een
            # invoerveld toont in plaats van er altijd een te laten staan.
            rassen = get_rassen()
            huidig_ras = huidige["ras"] or STANDAARD_RAS
            if huidig_ras not in rassen:
                rassen = rassen + [huidig_ras]
            gekozen_ras = st.selectbox(
                "Ras", rassen + [ANDER_RAS], index=rassen.index(huidig_ras),
                key=f"wijzig_ras_{geselecteerd_id}",
            )
            if gekozen_ras == ANDER_RAS:
                gekozen_ras = st.text_input(
                    "Naam van het ras", key=f"wijzig_ras_nieuw_{geselecteerd_id}"
                ).strip()

            # Helper om string-datums om te zetten naar date-objecten voor de widgets
            def naar_date(waarde):
                if waarde:
                    return datetime.strptime(waarde, "%Y-%m-%d").date()
                return None

            with st.form("wijzig_form"):
                nieuwe_start = st.date_input(
                    "Startdatum",
                    value=naar_date(huidige["datum_teelt_start"]) or datetime.today().date(),
                    format="DD-MM-YYYY"
                )
                st.caption(f"Week {get_weeknummer(nieuwe_start)}")

                nieuw_aantal_planten = st.number_input(
                    "Planten", min_value=0, step=1,
                    value=int(huidige["aantal_planten"]) if huidige["aantal_planten"] else 0
                )

                half_ingevuld = st.checkbox("Florgib bekend", value=huidige["datum_half"] is not None)
                nieuwe_datum_half = st.date_input(
                    "Datum Florgib",
                    value=naar_date(huidige["datum_half"]) or datetime.today().date(),
                    disabled=not half_ingevuld,
                    format="DD-MM-YYYY"
                )
                nieuwe_lengte_half = st.number_input(
                    "Florgib lengte (cm)",
                    min_value=0.0, format="%.1f",
                    value=float(huidige["lengte_half"]) if huidige["lengte_half"] else 0.0,
                    disabled=not half_ingevuld
                )

                oogst_ingevuld = st.checkbox("Oogst bekend", value=huidige["datum_oogst"] is not None)
                nieuwe_datum_oogst = st.date_input(
                    "Oogstdatum",
                    value=naar_date(huidige["datum_oogst"]) or datetime.today().date(),
                    disabled=not oogst_ingevuld,
                    format="DD-MM-YYYY"
                )
                nieuwe_lengte_eind = st.number_input(
                    "Oogstlengte (cm)",
                    min_value=0.0, format="%.1f",
                    value=float(huidige["lengte_eind"]) if huidige["lengte_eind"] else 0.0,
                    disabled=not oogst_ingevuld
                )
                nieuw_gewicht = st.number_input(
                    "Oogstgewicht (g)",
                    min_value=0, step=1,
                    value=int(round(huidige["oogstgewicht"])) if huidige["oogstgewicht"] else 0,
                    disabled=not oogst_ingevuld
                )
                nieuwe_rijpheid_bereik = st.select_slider(
                    "Rijpheid", options=RIJPHEID_OPTIES,
                    value=rijpheid_tekst_naar_bereik(huidige["rijpheid"]),
                    help="1 = rauw, 4 = rijp.",
                    disabled=not oogst_ingevuld
                )

                opslaan = st.form_submit_button("Opslaan")

                if opslaan:
                    try:
                        update_teelt_volledig(
                            geselecteerd_id,
                            nieuwe_start,
                            nieuwe_datum_half if half_ingevuld else None,
                            nieuwe_lengte_half if half_ingevuld else None,
                            nieuwe_datum_oogst if oogst_ingevuld else None,
                            nieuwe_lengte_eind if oogst_ingevuld else None,
                            nieuw_gewicht if oogst_ingevuld else None,
                            rijpheid_bereik_naar_tekst(nieuwe_rijpheid_bereik) if oogst_ingevuld else None,
                            nieuw_aantal_planten if nieuw_aantal_planten else None,
                            huidige["vaknummer"],
                            gebruiker=huidige_gebruiker(),
                        )
                        if gekozen_ras and gekozen_ras != huidig_ras:
                            zet_ras(geselecteerd_id, gekozen_ras, gebruiker=huidige_gebruiker())
                        st.success("Opgeslagen.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # Oogstregistraties (emmers) staan hier ook, zodat je ze ook voor
            # een afgeronde teelt nog kunt corrigeren.
            st.markdown("---")
            st.caption("Oogstmomenten")
            with st.container():
                toon_oogstregistraties_beheer(geselecteerd_id, huidige)

            # Verwijderen staat buiten het formulier, met expliciete bevestiging
            st.markdown("---")
            bevestig_verwijderen = st.checkbox(
                "Definitief verwijderen",
                key="bevestig_verwijderen"
            )
            if st.button("🗑️ Verwijderen", disabled=not bevestig_verwijderen):
                delete_teelt(geselecteerd_id, gebruiker=huidige_gebruiker())
                st.success("Verwijderd.")
                st.rerun()
        else:
            st.info("Nog geen registraties.")

# --- HOOFDSCHERM: TABBLADEN ---
tab_overzicht, tab_week, tab_detail, tab_planning, tab_stek, tab_klimaat, tab_stats, tab_meer = st.tabs([
    "📊 Teeltoverzicht", "📆 Weekoverzicht", "🔍 Teelt-detail", "🗓️ Planning", "🌱 Stek", "🌡️ Klimaatdata",
    "📈 Statistieken", "ℹ️ Meer",
])
# Weinig gebruikt: logboek en uitleg als subtabbladen onder "Meer".
with tab_meer:
    tab_log, tab_help = st.tabs(["🧾 Logboek", "ℹ️ Hoe dit werkt"])

kolommen, rijen = get_overzicht_dataframe()

# Kolommen van de teeltentabel: (kolom, label, soort, formaat, breedte).
OVERZICHT_KOLOMMEN = [
    ("Code", "Code", "tekst", None, "medium"),
    ("Teeltvak", "Vak", "tekst", None, "small"),
    ("Status", "Status", "tekst", None, "medium"),
    ("Startdatum", "Start", "datum", None, "small"),
    ("Startweek", "Wk start", "getal", "%d", "small"),
    ("Aantal Planten", "Planten", "getal", "%d", "small"),
    ("Aantal Emmers", "Emmers", "getal", "%d", "small"),
    ("Aantal Stelen", "Stelen", "getal", "%d", "small"),
    ("Uitval (%)", "Uitval (%)", "getal", "%.1f", "small"),
    ("Datum Halverwege", "Halverwege", "datum", None, "small"),
    ("Week Halverwege", "Wk half", "getal", "%d", "small"),
    ("Lengte Half (cm)", "Lengte half (cm)", "getal", "%.1f", "small"),
    ("Oogstdatum", "Oogst", "datum", None, "small"),
    ("Oogstweek", "Wk oogst", "getal", "%d", "small"),
    ("Teeltduur (dagen)", "Duur (dgn)", "getal", "%d", "small"),
    ("Oogstlengte (cm)", "Oogstlengte (cm)", "getal", "%.1f", "small"),
    ("Oogstgewicht (gram)", "Gewicht (g)", "getal", "%d", "small"),
    ("Rijpheid", "Rijpheid", "tekst", None, "small"),
]

# --- OVERZICHT ---
with tab_overzicht:
    st.subheader("📊 Teeltoverzicht")

    if rijen:
        # Maak een DataFrame van de rijen (zonder de ID-kolom voor display)
        df = pd.DataFrame(rijen, columns=kolommen)

        # Kengetallen bovenaan, zodat je die in 1 oogopslag ziet zonder
        # eerst langs de (steeds langere) tabel te hoeven scrollen.
        gem_duur = df[df['Teeltduur (dagen)'] != '-']['Teeltduur (dagen)'].astype(float).mean()
        toon_kengetallen([
            {"label": "Actief", "waarde": len(df[df['Status'] == 'Lopend'])},
            {"label": "Nog te starten", "waarde": len(df[df['Status'] == 'Nog te starten'])},
            {"label": "Afgerond", "waarde": len(df[df['Status'] == 'Afgerond'])},
            {"label": "Gem. duur", "waarde": f"{gem_duur:.0f} dgn" if not pd.isna(gem_duur) else "-"},
        ])

        st.markdown("---")

        # Afgeronde teelten staan standaard ingeklapt: de tabel groeit elke
        # afgeronde teelt door, en dagelijks is vooral het lopende/nog te
        # starten deel relevant.
        mask_afgerond = df['Status'] == 'Afgerond'
        verborgen = ['ID', '_startdatum_iso']
        df_ov_actief = df.loc[~mask_afgerond].drop(columns=verborgen)
        df_ov_afgerond = df.loc[mask_afgerond].sort_values('_startdatum_iso', ascending=False).drop(columns=verborgen)

        # Kolommen over de oogst bestaan pas bij afgeronde teelten en horen daar;
        # bij lopende teelten worden ze niet getoond. Overige kolommen die voor
        # de getoonde teelten nog helemaal leeg zijn (bijv. oogstlengte) ook niet.
        oogst_kolommen = {"Oogstweek", "Teeltduur (dagen)", "Oogstdatum"}
        actief_kolommen = [k for k in OVERZICHT_KOLOMMEN if k[0] not in oogst_kolommen]

        with st.expander(f"Lopend & nog te starten tonen ({len(df_ov_actief)})", expanded=True):
            toon_tabel(df_ov_actief, actief_kolommen, verberg_leeg=True, pin_eerste=True)

        with st.expander(f"Afgeronde teelten tonen ({len(df_ov_afgerond)})"):
            toon_tabel(df_ov_afgerond, OVERZICHT_KOLOMMEN, pin_eerste=True)
    else:
        st.info("Nog geen teelten geregistreerd. Gebruik de zijbalk om te beginnen.")

    # --- KENGETALLEN PER TEELT ---
    st.markdown("---")
    st.write("**Kengetallen per teelt**")

    kengetallen = get_teeltkengetallen()
    if not kengetallen:
        st.info("Nog geen teelten om door te rekenen.")
    else:
        jaren_teelt = sorted({r["plantjaar"] for r in kengetallen}, reverse=True)
        rassen_teelt = sorted({r["ras"] for r in kengetallen})
        kol_jaar, kol_ras = st.columns(2)
        keuze_jaar = kol_jaar.selectbox(
            "Plantjaar", ["Alle jaren"] + jaren_teelt,
            index=1 if jaren_teelt else 0, key="teeltoverzicht_jaar",
        )
        # Rassen niet door elkaar: een ander ras heeft een eigen teeltduur en
        # oogstgewicht, dus die hoort niet in hetzelfde gemiddelde.
        keuze_ras = kol_ras.selectbox(
            "Ras", rassen_teelt + ["Alle rassen"],
            index=rassen_teelt.index(STANDAARD_RAS) if STANDAARD_RAS in rassen_teelt else 0,
            key="teeltoverzicht_ras",
        ) if len(rassen_teelt) > 1 else rassen_teelt[0]
        gekozen = [r for r in kengetallen
                   if (keuze_jaar == "Alle jaren" or r["plantjaar"] == keuze_jaar)
                   and (keuze_ras == "Alle rassen" or r["ras"] == keuze_ras)]

        # Een periode die maar deels klimaat-, water- of energiedata heeft geeft
        # een te lage som; die laten we leeg in plaats van misleidend laag.
        def _volledig(rij, dagen_veld, drempel=0.9):
            return rij[dagen_veld] >= rij["looptijd_dagen"] * drempel

        df_keng = pd.DataFrame([{
            "Code": r["code"] or "-",
            "Vak": r["vaknummer"],
            "Afdeling": r["afdeling"],
            "Ras": r["ras"],
            "Plantweek": r["plantweek"],
            "Start": format_datum(r["datum_teelt_start"]),
            "Oogst": format_datum(r["datum_oogst"]) if r["datum_oogst"] else "",
            "Duur (dgn)": r["teeltduur"],
            "Planten": r["aantal_planten"],
            "Lichtsom": round(r["lichtsom"]) if r["lichtsom"] and _volledig(r, "klimaatdagen") else None,
            "Licht/dag": (round(r["lichtsom"] / r["klimaatdagen"])
                          if r["lichtsom"] and r["klimaatdagen"] else None),
            "Etmaal (°C)": round(r["gem_temperatuur"], 1) if r["gem_temperatuur"] else None,
            # Geen dekkingseis: in de oude Excel staan alleen de dagen met een gift,
            # een lege dag betekent daar nul en niet "onbekend".
            "Water (l/m²)": round(r["liters"], 1) if r["liters"] else None,
            "Warmte (MJ/m²)": (round(r["warmte_mj_per_m2"], 1)
                               if r["warmte_mj_per_m2"] and _volledig(r, "energiedagen") else None),
            "Lengte (cm)": r["lengte_eind"],
            "Gewicht (g)": r["oogstgewicht"],
        } for r in gekozen])

        toon_tabel(df_keng, [
            ("Code", "Code", "tekst", None, "medium"),
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Afdeling", "Afd", "getal", "%d", "small"),
            ("Ras", "Ras", "tekst", None, "small"),
            ("Plantweek", "Wk", "getal", "%d", "small"),
            ("Start", "Start", "datum", None, "small"),
            ("Oogst", "Oogst", "datum", None, "small"),
            ("Duur (dgn)", "Duur (dgn)", "getal", "%d", "small"),
            ("Planten", "Planten", "getal", "%d", "small"),
            ("Lichtsom", "Lichtsom", "getal", "%d", "small"),
            ("Licht/dag", "Licht/dag", "getal", "%d", "small"),
            ("Etmaal (°C)", "Etmaal (°C)", "getal", "%.1f", "small"),
            ("Water (l/m²)", "Water (l/m²)", "getal", "%.1f", "small"),
            ("Warmte (MJ/m²)", "Warmte (MJ/m²)", "getal", "%.1f", "small"),
            ("Lengte (cm)", "Lengte (cm)", "getal", "%.1f", "small"),
            ("Gewicht (g)", "Gewicht (g)", "getal", "%d", "small"),
        ], pin_eerste=True)
        st.caption(
            "Lichtsom en warmte zijn opgeteld over de hele teelt, de etmaaltemperatuur is "
            "een gemiddelde; klimaat komt van de eigen afdeling, warmte van de hele kas. "
            "Is een periode maar deels gemeten, dan blijft de cel leeg in plaats van te laag. "
            "Klimaatdata begint op 29-12-25, warmte op 29-06-26; watergift vóór 05-09-26 is de "
            "ingestelde gift uit de oude Excel: alleen dagen met een gift, dus mogelijk "
            "iets aan de lage kant."
        )

        # --- GRAFIEKEN PER PLANTWEEK ---
        # Staaf = gemiddelde van de teelten in die plantweek, punten = de losse
        # teelten, zodat je de spreiding binnen een week ziet.
        df_grafiek = pd.DataFrame([{
            "Plantweek": r["plantweek"],
            "Jaarweek": f"{r['plantjaar']}-{r['plantweek']:02d}",
            "Vak": r["vaknummer"],
            "Lichtsom": r["lichtsom"] if r["lichtsom"] and _volledig(r, "klimaatdagen") else None,
            "Etmaaltemperatuur": r["gem_temperatuur"],
            "Water": r["liters"],
            "Warmte": r["warmte_mj_per_m2"] if r["warmte_mj_per_m2"] and _volledig(r, "energiedagen") else None,
            "Gewicht": r["oogstgewicht"],
            "Lengte": r["lengte_eind"],
        } for r in gekozen])

        weekvolgorde = [w for w in sorted(df_grafiek["Jaarweek"].unique())]

        def teeltgrafiek(staaf_veld, staaf_titel, punt_veld, punt_titel, titel):
            """
            Staafdiagram (rechteras) met daaroverheen een puntenwolk (linkeras),
            beide per plantweek. Geeft None als er niets te tonen is.
            """
            data = df_grafiek.dropna(subset=[staaf_veld, punt_veld], how="all")
            if data.empty:
                return None
            x = alt.X("Jaarweek:N", sort=weekvolgorde, title="Plantweek",
                      axis=alt.Axis(labelAngle=0, labelOverlap=True))
            staven = alt.Chart(data).mark_bar(color=AFDELING_KLEUR[3], opacity=0.35).encode(
                x=x,
                y=alt.Y(f"mean({staaf_veld}):Q", title=staaf_titel,
                        axis=alt.Axis(orient="right"), scale=alt.Scale(zero=True)),
                tooltip=[alt.Tooltip("Jaarweek:N", title="Plantweek"),
                         alt.Tooltip(f"mean({staaf_veld}):Q", title=f"{staaf_titel} (gem.)", format=".1f")],
            )
            punten = alt.Chart(data).mark_circle(size=55, color=AFDELING_KLEUR[1]).encode(
                x=x,
                y=y_as(punt_veld, punt_titel, axis=alt.Axis(orient="left")),
                tooltip=[alt.Tooltip("Jaarweek:N", title="Plantweek"),
                         alt.Tooltip("Vak:Q", title="Vak"),
                         alt.Tooltip(f"{punt_veld}:Q", title=punt_titel, format=".1f"),
                         alt.Tooltip(f"{staaf_veld}:Q", title=staaf_titel, format=".1f")],
            )
            return alt.layer(staven, punten).resolve_scale(y="independent").properties(
                height=260, title=titel
            )

        for staaf, staaf_titel, punt, punt_titel, titel, toelichting in [
            ("Lichtsom", "Lichtsom per teelt (J/cm²)", "Etmaaltemperatuur", "Etmaaltemperatuur (°C)",
             "Licht en temperatuur", None),
            ("Water", "Watergift per teelt (l/m²)", "Etmaaltemperatuur", "Etmaaltemperatuur (°C)",
             "Water en temperatuur", None),
            ("Gewicht", "Oogstgewicht (g)", "Lengte", "Oogstlengte (cm)",
             "Oogstgewicht en lengte", "Alleen teelten waarvan gewicht en lengte zijn gemeten."),
            ("Warmte", "Warmte per teelt (MJ/m²)", "Etmaaltemperatuur", "Etmaaltemperatuur (°C)",
             "Warmte en temperatuur", "Warmte wordt voor de hele kas gemeten, dus gelijk voor alle vakken."),
        ]:
            grafiek = teeltgrafiek(staaf, staaf_titel, punt, punt_titel, titel)
            if grafiek is None:
                st.caption(f"{titel}: nog geen data voor deze selectie.")
            else:
                st.altair_chart(grafiek, use_container_width=True)
                if toelichting:
                    st.caption(toelichting)
        st.caption("Staven zijn het gemiddelde van de plantweek, de punten zijn de losse teelten.")

# --- WEEKOVERZICHT ---
with tab_week:
    st.subheader("📆 Weekoverzicht")

    def _week_maandag(datum):
        if isinstance(datum, str):
            datum = datetime.strptime(datum, "%Y-%m-%d").date()
        return datum - timedelta(days=datum.weekday())

    def _week_label(week_start):
        jaar, week, _ = week_start.isocalendar()
        week_eind = week_start + timedelta(days=6)
        return f"Week {week} - {jaar} ({format_datum(week_start)} t/m {format_datum(week_eind)})"

    alle_teelten_week = get_alle_teelten_detail()

    # Zo ver terug kunnen we gaan: de vroegste teeltstart die geregistreerd is.
    startdatums_week = [t["datum_teelt_start"] for t in alle_teelten_week if t["datum_teelt_start"]]
    vroegste_datum_week = min(startdatums_week) if startdatums_week else str(date.today())

    maandag_nu_week = _week_maandag(date.today())
    maandag_vroegst_week = _week_maandag(vroegste_datum_week)

    weken_terug = []
    w = maandag_nu_week
    while w >= maandag_vroegst_week:
        weken_terug.append(w)
        w -= timedelta(weeks=1)
    if not weken_terug:
        weken_terug = [maandag_nu_week]

    labels_week = [_week_label(w) for w in weken_terug]
    labels_week[0] += " - huidige week"
    # Standaard de laatste volledige week; de huidige week is gewoon kiesbaar.
    gekozen_label_week = st.selectbox(
        "Kies een week", labels_week, index=1 if len(labels_week) > 1 else 0,
        key="week_overzicht_selectie",
    )
    week_start = weken_terug[labels_week.index(gekozen_label_week)]
    week_eind = week_start + timedelta(days=6)
    week_start_s, week_eind_s = str(week_start), str(week_eind)

    # --- Data verzamelen (voor zowel de samenvatting bovenaan als de tabellen) ---
    geplant_week = sorted(
        (t for t in alle_teelten_week
         if t["datum_teelt_start"] and week_start_s <= t["datum_teelt_start"] <= week_eind_s),
        key=lambda t: (t["vaknummer"] or 0)
    )

    emmers_week = get_oogstregistraties_voor_periode(week_start_s, week_eind_s)
    totaal_emmers_week = sum(e["aantal_emmers"] for e in emmers_week) if emmers_week else 0
    totaal_stelen_week = totaal_emmers_week * 100

    afgerond_week = sorted(
        (t for t in alle_teelten_week
         if t["datum_oogst"] and week_start_s <= t["datum_oogst"] <= week_eind_s),
        key=lambda t: (t["vaknummer"] or 0)
    )
    uitval_rijen_week = []
    uitval_pct_week = []
    emmers_per_teelt = get_totaal_emmers_per_teelt()
    for t in afgerond_week:
        emmers_t = emmers_per_teelt.get(t["id"])
        totaal_stelen_t = emmers_t * 100 if emmers_t else 0
        uitval_pct_t = uitval_van_teelt(t, emmers_per_teelt)
        if uitval_pct_t is not None:
            uitval_pct_week.append(uitval_pct_t)
        uitval_rijen_week.append({
            "Vak": t["vaknummer"],
            "Code": t["code"] or "-",
            "Oogstdatum": format_datum(t["datum_oogst"]),
            "Planten": t["aantal_planten"] if t["aantal_planten"] is not None else "-",
            "Geoogste stelen": totaal_stelen_t if emmers_t else "-",
            "Uitval (%)": round(uitval_pct_t, 1) if uitval_pct_t is not None else "-",
            "Lengte (cm)": t["lengte_eind"] if t["lengte_eind"] is not None else "-",
            "Gewicht (g)": t["oogstgewicht"] if t["oogstgewicht"] is not None else "-",
            "Rijpheid": t["rijpheid"] or "-",
        })

    water_week = get_watergift_per_vak_voor_periode(week_start_s, week_eind_s)
    df_water_week = None
    gem_water_week = None
    if water_week:
        df_water_week = pd.DataFrame([{
            "Vak": v,
            "Totaal (l/m²)": round(totaal, 1) if totaal is not None else "-",
            "Dagen met data": dagen,
        } for v, totaal, dagen in water_week])
        gem_water_week = pd.to_numeric(df_water_week["Totaal (l/m²)"], errors="coerce").mean()

    # --- Samenvatting bovenaan ---
    toon_kengetallen([
        {"label": "Geplant", "waarde": len(geplant_week), "help": "Teelten gestart in deze week"},
        {"label": "Emmers", "waarde": f"{totaal_emmers_week:g}" if emmers_week else "-"},
        {"label": "Stelen",
         "waarde": f"{totaal_stelen_week:,.0f}".replace(",", ".") if emmers_week else "-"},
        {"label": "Gem. uitval",
         "waarde": f"{sum(uitval_pct_week) / len(uitval_pct_week):.1f} %" if uitval_pct_week else "-",
         "help": "Teelten die deze week zijn afgerond"},
        {"label": "Gem. water",
         "waarde": f"{gem_water_week:.1f} l/m²" if gem_water_week is not None and pd.notna(gem_water_week) else "-",
         "help": f"Gemiddeld over {len(df_water_week)} vakken" if df_water_week is not None else None},
    ])

    st.markdown("---")

    # --- Geplant ---
    st.write(f"**🌱 Geplant deze week** ({len(geplant_week)})")
    if geplant_week:
        toon_tabel(pd.DataFrame([{
            "Vak": t["vaknummer"],
            "Code": t["code"] or "-",
            "Startdatum": format_datum(t["datum_teelt_start"]),
            "Aantal planten": t["aantal_planten"] if t["aantal_planten"] is not None else "-",
        } for t in geplant_week]), [
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Code", "Code", "tekst", None, "medium"),
            ("Startdatum", "Start", "datum", None, "small"),
            ("Aantal planten", "Planten", "getal", "%d", "small"),
        ])
    else:
        st.caption("Geen teelten gestart deze week.")

    st.markdown("---")

    # --- Geoogst ---
    st.write("**🌾 Geoogst deze week**")
    if emmers_week:
        per_vak_oogst = (
            pd.DataFrame(emmers_week).groupby("vaknummer", as_index=False)["aantal_emmers"].sum()
            .sort_values("vaknummer")
        )
        per_vak_oogst["Stelen"] = per_vak_oogst["aantal_emmers"] * 100
        per_vak_oogst = per_vak_oogst.rename(columns={"vaknummer": "Vak", "aantal_emmers": "Emmers"})
        toon_tabel(per_vak_oogst, [
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Emmers", "Emmers", "getal", "%d", "small"),
            ("Stelen", "Stelen", "getal", "%d", "small"),
        ])

        with st.expander(f"Alle oogstmomenten deze week tonen ({len(emmers_week)})"):
            toon_tabel(pd.DataFrame([{
                "Datum": format_datum(e["datum"]),
                "Vak": e["vaknummer"],
                "Code": e["code"] or "-",
                "Emmers": e["aantal_emmers"],
            } for e in emmers_week]), [
                ("Datum", "Datum", "datum", None, "small"),
                ("Vak", "Vak", "getal", "%d", "small"),
                ("Code", "Code", "tekst", None, "medium"),
                ("Emmers", "Emmers", "getal", "%d", "small"),
            ])
    else:
        st.caption("Geen emmers geregistreerd deze week.")

    if afgerond_week:
        st.write("**🪣 Uitval van teelten afgerond deze week**")
        toon_tabel(pd.DataFrame(uitval_rijen_week), [
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Code", "Code", "tekst", None, "medium"),
            ("Oogstdatum", "Oogst", "datum", None, "small"),
            ("Planten", "Planten", "getal", "%d", "small"),
            ("Geoogste stelen", "Stelen", "getal", "%d", "small"),
            ("Uitval (%)", "Uitval (%)", "getal", "%.1f", "small"),
            ("Lengte (cm)", "Lengte (cm)", "getal", "%.1f", "small"),
            ("Gewicht (g)", "Gewicht (g)", "getal", "%d", "small"),
            ("Rijpheid", "Rijpheid", "tekst", None, "small"),
        ])

    st.markdown("---")

    # --- Watergift ---
    st.write("**💧 Watergift deze week**")
    if water_week:
        toon_tabel(df_water_week, [
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Totaal (l/m²)", "Totaal (l/m²)", "getal", "%.1f", "small"),
            ("Dagen met data", "Dagen", "getal", "%d", "small"),
        ])
    else:
        st.caption("Geen watergiftdata beschikbaar voor deze week.")

    st.write("**Watergift per vak per dag (l/m²)**")
    water_dag_week = get_watergift_per_dag_voor_periode(week_start_s, week_eind_s)
    if water_dag_week:
        df_water_dag = pd.DataFrame(water_dag_week, columns=["datum", "Vak", "Liter/m²"])
        df_water_dag["Datum"] = pd.to_datetime(df_water_dag["datum"]).dt.strftime("%d-%m-%y")
        kolomvolgorde_water = sorted(
            df_water_dag["Datum"].unique(), key=lambda d: datetime.strptime(d, "%d-%m-%y")
        )
        pivot_water = df_water_dag.pivot_table(index="Vak", columns="Datum", values="Liter/m²", aggfunc="sum")
        pivot_water = pivot_water.reindex(kolomvolgorde_water, axis=1).sort_index()
        st.dataframe(pivot_water.round(1), column_config={
            dag: st.column_config.NumberColumn(dag[:5], format="%.1f", width="small")
            for dag in pivot_water.columns
        })
    else:
        st.caption("Geen watergiftdata per dag beschikbaar voor deze week.")

    st.markdown("---")

    # --- Klimaat ---
    st.write("**🌡️ Klimaat deze week**")
    klimaat_rijen_week = []
    klimaat_dagen_week = []
    for afdeling_week in (1, 2, 3, 4):
        k_week = get_klimaat_voor_periode(afdeling_week, week_start_s, week_eind_s)
        if k_week:
            klimaat_rijen_week.append({
                "Afdeling": afdeling_week,
                "Gem. temperatuur (°C)": round(k_week["gem_temperatuur"], 1) if k_week["gem_temperatuur"] is not None else "-",
                "Gem. RV (%)": round(k_week["gem_rv"], 1) if k_week["gem_rv"] is not None else "-",
                "Gem. lichtsom/dag": round(k_week["gem_stralingssom_dag"], 0) if k_week["gem_stralingssom_dag"] is not None else "-",
            })
        for datum, temp, rv, straling, *_rest in get_klimaatdata_dagen_voor_periode(
            afdeling_week, week_start_s, week_eind_s
        ):
            klimaat_dagen_week.append({
                "datum": datum, "afdeling": afdeling_week, "temp_24h": temp, "lichtsom": straling,
            })
    if klimaat_rijen_week:
        toon_tabel(pd.DataFrame(klimaat_rijen_week), [
            ("Afdeling", "Afdeling", "getal", "%d", "small"),
            ("Gem. temperatuur (°C)", "Temp. (°C)", "getal", "%.1f", "small"),
            ("Gem. RV (%)", "RV (%)", "getal", "%.1f", "small"),
            ("Gem. lichtsom/dag", "Lichtsom/dag", "getal", "%d", "small"),
        ])
    else:
        st.caption("Geen klimaatdata beschikbaar voor deze week.")

    st.write("**Licht/temperatuur-verhouding per dag**")
    if klimaat_dagen_week:
        licht_temperatuur_grafiek(klimaat_dagen_week)
    else:
        st.caption("Geen klimaatdata beschikbaar voor deze week.")

# --- TEELT-DETAIL (GRAFISCH OVERZICHT PER TEELT) ---
with tab_detail:
    st.subheader("🔍 Teelt-detail")

    alle_teelten_detail = get_alle_teelten_detail()
    if alle_teelten_detail:
        # Groepeer per plantweek (iso-jaar + weeknummer van de startdatum), zodat
        # je alle vakken die in dezelfde week geplant zijn in één keer ziet,
        # in plaats van per los vak.
        groepen_detail = {}
        for t in alle_teelten_detail:
            sleutel = get_isojaar_week(t["datum_teelt_start"])
            groepen_detail.setdefault(sleutel, []).append(t)

        def _label_plantweek(sleutel):
            jaar, week = sleutel
            teelten_groep = groepen_detail[sleutel]
            vakken = sorted({t["vaknummer"] for t in teelten_groep if t["vaknummer"] is not None})
            vakken_tekst = ", ".join(str(v) for v in vakken) if vakken else "?"
            return f"Week {week} - {jaar} ({len(teelten_groep)} vak(ken): {vakken_tekst})"

        keuzes_weken = {_label_plantweek(sleutel): sleutel for sleutel in sorted(groepen_detail.keys())}

        # Open standaard op de plantweek met de meest recent geoogste teelt.
        laatste_oogst, standaard_sleutel = None, None
        for sleutel, groep in groepen_detail.items():
            for t in groep:
                if t["datum_oogst"] and (laatste_oogst is None or t["datum_oogst"] > laatste_oogst):
                    laatste_oogst, standaard_sleutel = t["datum_oogst"], sleutel
        labels = list(keuzes_weken.keys())
        standaard_index = 0
        if standaard_sleutel is not None:
            standaard_label = next(lbl for lbl, s in keuzes_weken.items() if s == standaard_sleutel)
            standaard_index = labels.index(standaard_label)

        week_label = st.selectbox(
            "Kies een plantweek", labels, index=standaard_index, key="detail_week_selectie"
        )
        sleutel_groep = keuzes_weken[week_label]
        teelten_groep = groepen_detail[sleutel_groep]
        _, week_groep = sleutel_groep
        verwachte_duur_weken = teeltduur_voor_plantweek(week_groep)

        vandaag_detail = str(datetime.today().date())
        aantal_afgerond = sum(1 for t in teelten_groep if t["datum_oogst"])
        aantal_nog_te_starten = sum(
            1 for t in teelten_groep if not t["datum_oogst"] and t["datum_teelt_start"] > vandaag_detail
        )
        aantal_lopend = len(teelten_groep) - aantal_afgerond - aantal_nog_te_starten

        if aantal_lopend == len(teelten_groep):
            status_tekst = "🌱 Alle lopend"
        elif aantal_afgerond == len(teelten_groep):
            status_tekst = "✅ Alle afgerond"
        elif aantal_nog_te_starten == len(teelten_groep):
            status_tekst = "🕓 Nog te starten"
        else:
            status_delen = []
            if aantal_lopend:
                status_delen.append(f"{aantal_lopend} lopend")
            if aantal_afgerond:
                status_delen.append(f"{aantal_afgerond} afgerond")
            if aantal_nog_te_starten:
                status_delen.append(f"{aantal_nog_te_starten} nog te starten")
            status_tekst = " · ".join(status_delen)

        start_datums = sorted(t["datum_teelt_start"] for t in teelten_groep)
        vakken_groep = sorted({t["vaknummer"] for t in teelten_groep if t["vaknummer"] is not None})
        st.caption(f"Vakken in deze plantweek: {', '.join(str(v) for v in vakken_groep) if vakken_groep else '-'}")

        # Teeltduur en klimaat worden per teelt (dus per planting, op basis
        # van de eigen afdeling en periode) berekend en pas daarna gemiddeld
        # over de groep — niet als één vast afdeling/vak-gemiddelde.
        dagen_lijst, temp_lijst, rv_lijst, straling_lijst, water_lijst, warmte_lijst = [], [], [], [], [], []
        delta_temp_lijst = []
        for t in teelten_groep:
            if not t["datum_oogst"] and t["datum_teelt_start"] > vandaag_detail:
                continue  # nog niet gestart: geen teeltduur/klimaat "tot nu toe" om te middelen

            eind_t = t["datum_oogst"] or vandaag_detail
            dagen_t = get_teeltduur(t["datum_teelt_start"], eind_t)
            if dagen_t is not None:
                dagen_lijst.append(dagen_t)

            afdeling_t = afdeling_van_vak(t["vaknummer"])
            if afdeling_t:
                klimaat_t = get_klimaat_voor_periode(afdeling_t, t["datum_teelt_start"], eind_t)
                if klimaat_t:
                    if klimaat_t["gem_temperatuur"] is not None:
                        temp_lijst.append(klimaat_t["gem_temperatuur"])
                    if klimaat_t["gem_rv"] is not None:
                        rv_lijst.append(klimaat_t["gem_rv"])
                    if klimaat_t["gem_stralingssom_dag"] is not None:
                        straling_lijst.append(klimaat_t["gem_stralingssom_dag"])
                    if klimaat_t["gem_temperatuur"] is not None and klimaat_t["gem_stralingssom_dag"] is not None:
                        ideaal_t = ideale_etmaaltemperatuur(klimaat_t["gem_stralingssom_dag"])
                        delta_temp_lijst.append(klimaat_t["gem_temperatuur"] - ideaal_t)

            if t["vaknummer"]:
                water_t = get_watergift_voor_periode(t["vaknummer"], t["datum_teelt_start"], eind_t)
                if water_t:
                    water_lijst.append(water_t["totaal_liter_per_m2"])

                warmte_t = get_warmte_voor_periode(t["vaknummer"], t["datum_teelt_start"], eind_t)
                if warmte_t:
                    warmte_lijst.append(warmte_t["totaal_mj"])

        if dagen_lijst:
            gem_dagen = sum(dagen_lijst) / len(dagen_lijst)
            gem_weken = round(gem_dagen / 7 * 2) / 2
            teeltduur_tekst = f"{gem_weken:g} wk ({gem_dagen:.0f} dgn)"
        else:
            teeltduur_tekst = "-"

        teeltduur_delta = None
        if dagen_lijst and verwachte_duur_weken is not None:
            teeltduur_delta = f"{gem_weken - verwachte_duur_weken:+.1f} wk t.o.v. gepland ({verwachte_duur_weken:g} wk)"

        def _datum_bereik(datums, voorvoegsel=""):
            # Niet-afbrekende streepjes (U+2011): op een smal scherm mag het
            # bereik wél op de spatie breken, maar niet midden in een datum.
            nb = lambda d: format_datum(d).replace("-", "‑")
            if datums[0] == datums[-1]:
                return f"{voorvoegsel}{nb(datums[-1])}"
            return f"{voorvoegsel}{nb(datums[0])} – {nb(datums[-1])}"

        oogst_datums_echt = sorted(t["datum_oogst"] for t in teelten_groep if t["datum_oogst"])
        if oogst_datums_echt:
            oogst_tekst = _datum_bereik(oogst_datums_echt)
        else:
            verwachte_oogsten = []
            for t in teelten_groep:
                _, verwacht_t = bereken_verwachte_oogstdatum(t["datum_teelt_start"])
                if verwacht_t:
                    verwachte_oogsten.append(verwacht_t)
            oogst_tekst = _datum_bereik(sorted(verwachte_oogsten), "~") if verwachte_oogsten else "-"

        toon_kengetallen(titel="Teelt", items=[
            {"label": "Eerste start", "waarde": format_datum(start_datums[0])},
            {"label": "Oogst", "waarde": oogst_tekst,
             "help": "Werkelijke oogstdatum(s); met ~ de verwachte datum uit de teeltduur-tabel."},
            {"label": "Gem. duur", "waarde": teeltduur_tekst,
             "delta": teeltduur_delta,
             "help": "Gemiddelde teeltduur van de teelten in deze plantweek."},
            {"label": "Status", "waarde": status_tekst},
        ])

        toon_kengetallen(titel="Klimaat", items=[
            {"label": "Gem. temp.",
             "waarde": f"{sum(temp_lijst) / len(temp_lijst):.1f} °C" if temp_lijst else "-",
             "delta": f"{sum(delta_temp_lijst) / len(delta_temp_lijst):+.1f} °C t.o.v. ideaal" if delta_temp_lijst else None,
             "help": "Gemiddelde etmaaltemperatuur. Ideaal is afhankelijk van de lichtsom: "
                     f"{LICHT_TEMP_FACTOR} x lichtsom + {LICHT_TEMP_BASIS} °C."},
            {"label": "Gem. RV", "waarde": f"{sum(rv_lijst) / len(rv_lijst):.0f} %" if rv_lijst else "-"},
            {"label": "Lichtsom/dag",
             "waarde": f"{sum(straling_lijst) / len(straling_lijst):.0f}" if straling_lijst else "-",
             "help": "Gemiddelde lichtsom per dag."},
            {"label": "Water",
             "waarde": f"{sum(water_lijst) / len(water_lijst):.0f} l/m²" if water_lijst else "-",
             "help": "Gemiddelde totale watergift per vak."},
            {"label": "Warmte",
             "waarde": f"{sum(warmte_lijst) / len(warmte_lijst) / 1000:.2f} GJ" if warmte_lijst else "-",
             "help": "Gemiddeld warmteverbruik per teelt."},
        ])

        afgeronde_groep = [t for t in teelten_groep if t["datum_oogst"]]
        halve_lengtes = [t["lengte_half"] for t in teelten_groep if t["lengte_half"]]
        lengtes = [t["lengte_eind"] for t in afgeronde_groep if t["lengte_eind"]]
        gewichten = [t["oogstgewicht"] for t in afgeronde_groep if t["oogstgewicht"]]

        uitval_lijst = []
        factor_lijst = []
        gewicht_per_10cm_lijst = []
        emmers_per_teelt = get_totaal_emmers_per_teelt()
        for t in afgeronde_groep:
            uitval_t = uitval_van_teelt(t, emmers_per_teelt)
            if uitval_t is not None:
                uitval_lijst.append(uitval_t)
            if t["lengte_half"] and t["lengte_eind"]:
                factor_lijst.append(t["lengte_eind"] / t["lengte_half"])
            if t["oogstgewicht"] and t["lengte_eind"]:
                gewicht_per_10cm_lijst.append(t["oogstgewicht"] / t["lengte_eind"] * 10)

        jaar_gem = jaargemiddelden_oogst(date.today().year)

        def _delta_jaar(waarde, jaar_waarde, eenheid="", decimalen=1):
            if waarde is None or jaar_waarde is None:
                return None
            return f"{waarde - jaar_waarde:+.{decimalen}f}{eenheid} t.o.v. dit jaar"

        gem_halve_lengte = sum(halve_lengtes) / len(halve_lengtes) if halve_lengtes else None
        gem_lengte = sum(lengtes) / len(lengtes) if lengtes else None
        gem_gewicht = sum(gewichten) / len(gewichten) if gewichten else None
        gem_uitval = sum(uitval_lijst) / len(uitval_lijst) if uitval_lijst else None
        gem_factor = sum(factor_lijst) / len(factor_lijst) if factor_lijst else None
        gem_gewicht_10cm = (
            sum(gewicht_per_10cm_lijst) / len(gewicht_per_10cm_lijst) if gewicht_per_10cm_lijst else None
        )
        toon_kengetallen(titel="Oogst", items=[
            {"label": "Florgib",
             "waarde": f"{gem_halve_lengte:.1f} cm" if gem_halve_lengte is not None else "-",
             "help": "Gemiddelde lengte bij de Florgib-meting halverwege de teelt."},
            {"label": "Gem. taklengte",
             "waarde": f"{gem_lengte:.1f} cm" if gem_lengte is not None else "-",
             "delta": _delta_jaar(gem_lengte, jaar_gem["lengte"], " cm")},
            {"label": "Gem. takgewicht",
             "waarde": f"{gem_gewicht:.0f} g" if gem_gewicht is not None else "-",
             "delta": _delta_jaar(gem_gewicht, jaar_gem["gewicht"], " g", 0)},
            {"label": "Gem. uitval",
             "waarde": f"{gem_uitval:.1f} %" if gem_uitval is not None else "-",
             "delta": _delta_jaar(gem_uitval, jaar_gem["uitval"], " %-punt")},
            {"label": "Gem. factor",
             "waarde": f"{gem_factor:.2f}" if gem_factor is not None else "-",
             "delta": _delta_jaar(gem_factor, jaar_gem["factor"], "", 2),
             "help": "Eindlengte gedeeld door de lengte bij de Florgib-meting halverwege."},
            {"label": "Gewicht/10 cm",
             "waarde": f"{gem_gewicht_10cm:.1f} g" if gem_gewicht_10cm is not None else "-",
             "delta": _delta_jaar(gem_gewicht_10cm, jaar_gem["gewicht_10cm"], " g"),
             "help": "Gemiddeld takgewicht per 10 cm taklengte."},
        ])

        st.markdown("---")

        st.write("**Klimaat tijdens deze plantweek**")
        afdelingen_groep = sorted({
            afdeling_van_vak(t["vaknummer"]) for t in teelten_groep
            if afdeling_van_vak(t["vaknummer"])
        })
        if afdelingen_groep:
            eind_groep = max(t["datum_oogst"] or vandaag_detail for t in teelten_groep)
            records_temp, records_rv, records_straling = [], [], []
            for afdeling in afdelingen_groep:
                dagen = get_klimaatdata_dagen_voor_periode(afdeling, start_datums[0], eind_groep)
                for datum, temp, rv, straling, temp_dag, temp_nacht, rv_dag, rv_nacht in dagen:
                    afd = f"Afd. {afdeling}"
                    for deel, t_waarde, rv_waarde in (
                        ("24h", temp, rv), ("dag", temp_dag, rv_dag), ("nacht", temp_nacht, rv_nacht)
                    ):
                        records_temp.append({"datum": datum, "Afdeling": afd, "Deel": deel, "waarde": t_waarde})
                        records_rv.append({"datum": datum, "Afdeling": afd, "Deel": deel, "waarde": rv_waarde})
                    records_straling.append({"datum": datum, "Afdeling": afd, "Deel": "24h", "waarde": straling})

            geen_klimaat = "Nog geen klimaatdata gekoppeld aan deze plantweek."
            st.caption("Temperatuur (°C): donker = 24 uur, licht = dag, gestippeld = nacht")
            lijngrafiek_per_afdeling(pd.DataFrame(records_temp), "Temperatuur (°C)", melding=geen_klimaat)
            st.caption("RV (%): donker = 24 uur, licht = dag, gestippeld = nacht")
            lijngrafiek_per_afdeling(pd.DataFrame(records_rv), "RV (%)", formaat=".0f", melding=geen_klimaat)
            st.caption("Lichtsom (per dag)")
            lijngrafiek_per_afdeling(
                pd.DataFrame(records_straling), "Lichtsom", toon_dagnacht=False, formaat=".0f",
                melding=geen_klimaat,
            )
        else:
            st.info("Onbekend vaknummer; kan geen afdeling/klimaatdata bepalen.")

        st.write("**Watergift tijdens deze plantweek**")
        eind_water = max(t["datum_oogst"] or vandaag_detail for t in teelten_groep)
        records_water = []
        for vak in vakken_groep:
            for datum, liter in get_watergift_dagen_voor_periode(vak, start_datums[0], eind_water):
                records_water.append({"datum": datum, "Vak": f"Vak {vak}", "liter": liter})
        df_water = pd.DataFrame(records_water).dropna(subset=["liter"]) if records_water else None
        if df_water is not None and not df_water.empty:
            df_water["datum"] = pd.to_datetime(df_water["datum"])
            df_water = df_water.sort_values("datum")
            df_water["dag"] = df_water["datum"].dt.strftime(DATUM_FORMAAT_AS)
            st.caption("Watergift per vak (l/m² per dag) — vakken naast elkaar, niet opgeteld")
            # x als ordinaal (i.p.v. temporeel) zetten, want xOffset heeft een
            # discrete band-schaal per dag nodig om de vakken naast elkaar te
            # kunnen zetten — op een continue tijdas vallen de staven anders
            # gewoon over elkaar heen. Het label is daarom een kant-en-klare
            # dd-mm-tekst: een tijdformaat op een ordinale as leest Vega als
            # getalformaat ("invalid format") en de grafiek blijft dan leeg.
            water_chart = alt.Chart(df_water).mark_bar().encode(
                x=alt.X("dag:O", title=None, sort=list(df_water["dag"].unique()),
                        axis=alt.Axis(labelAngle=-45)),
                xOffset="Vak:N",
                y=alt.Y("liter:Q", title="Liter/m²"),
                color=alt.Color("Vak:N", legend=alt.Legend(title=None, orient="top")),
                tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Vak:N",
                         alt.Tooltip("liter:Q", title="l/m²", format=".1f")],
            )
            st.altair_chart(water_chart, use_container_width=True)
        else:
            st.info("Nog geen watergift gekoppeld aan deze plantweek.")
    else:
        st.info("Nog geen teelten geregistreerd.")

# --- PLANNING (TOEKOMSTIGE TEELTEN) ---
with tab_planning:
    st.subheader("🗓️ Planning")
    with st.expander("Hoe lees ik dit?"):
        st.caption(
            "Concept-planning voor toekomstige teelten: plant vooruit vanaf waar de huidige teelt van "
            "elk vak en de bestaande concept-planning gebleven zijn. Vak 19+20 worden als één eenheid "
            "gepland. Het aantal vakken per week komt volledig uit jouw eigen jaarplanning hieronder — "
            "een week zonder ingevuld aantal blijft leeg, en er worden nooit meer dan 5 vakken per week "
            "gepoot. Vak 1 loopt op een eigen ritme, los van de andere vakken, en wordt alleen gepland "
            "in de weken die je daarvoor apart aanvinkt. Binnen een week worden de vakken over maandag "
            "t/m donderdag verdeeld (laagste vaknummer op maandag); kan een week niet op maandag "
            "beginnen doordat de grond nog bezet is, dan start die week op di/wo/do i.p.v. een week "
            "over te slaan. Een vak wordt nooit eerder gepland dan de (verwachte) oogst van de lopende "
            "teelt in dat vak."
        )
        st.caption(
            "Strokenplanning: grijs = afgerond, groen = lopende teelt, blauw = concept-planning. "
            "Getal op de as = ISO-weeknummer; rode stippellijn = vandaag. Een rode stippelrand om "
            "een deel van een balk = die dagen overlappen met de vorige ronde in dat vak. Oogstdatum "
            "van lopende teelten en concepten is de verwachte datum uit de teeltduur-tabel. Beweeg "
            "over een balk voor weeknummer + dag van start en oogst en de teeltduur in weken."
        )

    # --- Strokenplanning (Gantt): vakken verticaal, weken horizontaal ---
    stroken = get_strokenplanning(weken_terug=8)
    if stroken:
        df_stroken = pd.DataFrame(stroken)
        df_stroken["start"] = pd.to_datetime(df_stroken["start"])
        df_stroken["eind"] = pd.to_datetime(df_stroken["eind"])
        _dagen_nl = ["ma", "di", "wo", "do", "vr", "za", "zo"]

        def _week_dag(ts):
            return f"wk {ts.isocalendar().week} {_dagen_nl[ts.weekday()]}"

        df_stroken["start_tekst"] = df_stroken["start"].apply(_week_dag)
        df_stroken["eind_tekst"] = df_stroken["eind"].apply(_week_dag)
        df_stroken["duur_tekst"] = df_stroken["teeltduur_weken"].apply(
            lambda x: f"{x:.1f} wk" if pd.notna(x) else "–"
        )

        # Overlap: per vak, het stuk van een balk dat vóór de oogst van een
        # eerder gestarte balk in datzelfde vak valt (nu toegestaan door de
        # planner, zie planningsmodule). Alleen dát dagbereik krijgt een rode
        # stippelrand, niet de hele balk — via een losse laag die alleen over
        # het overlappende deel getekend wordt.
        overlap_segmenten = []
        for _vak, groep in df_stroken.groupby("vaknummer"):
            eerdere_einden = []
            for _idx, rij in groep.sort_values("start").iterrows():
                overlappend = [eind_e for eind_e in eerdere_einden if rij["start"] < eind_e]
                if overlappend:
                    overlap_segmenten.append({
                        "vaknummer": rij["vaknummer"],
                        "start": rij["start"],
                        "eind": min(rij["eind"], max(overlappend)),
                    })
                eerdere_einden.append(rij["eind"])
        df_overlap = pd.DataFrame(overlap_segmenten)

        kleur = alt.Color(
            "status:N",
            scale=alt.Scale(
                domain=["afgerond", "lopend", "concept"],
                range=["#b8b8b3", "#1baf7a", "#2a78d6"],
            ),
            legend=alt.Legend(title=None, orient="top"),
        )
        vak_y = alt.Y(
            "vaknummer:O", title="Vak", sort="ascending",
            # De vakken van deze tuin, zodat tuin 1 geen lege rijen 28-39 krijgt.
            scale=alt.Scale(domain=get_vaknummers() or list(range(1, 40))),
        )
        balken = (
            alt.Chart(df_stroken)
            .mark_bar(height=13, cornerRadius=3, stroke="white", strokeWidth=1)
            .encode(
                y=vak_y,
                x=alt.X(
                    "start:T", title="Week",
                    axis=alt.Axis(format="%V", tickCount={"interval": "week", "step": 2}, grid=True),
                ),
                x2="eind:T",
                color=kleur,
                tooltip=[
                    alt.Tooltip("vaknummer:O", title="Vak"),
                    alt.Tooltip("label:N", title="Teelt"),
                    alt.Tooltip("status:N", title="Status"),
                    alt.Tooltip("start_tekst:N", title="Start"),
                    alt.Tooltip("eind_tekst:N", title="Oogst"),
                    alt.Tooltip("duur_tekst:N", title="Teeltduur"),
                ],
            )
        )
        lagen = [balken]
        if not df_overlap.empty:
            overlap_balken = (
                alt.Chart(df_overlap)
                .mark_bar(height=13, cornerRadius=3, filled=False, stroke="#e34948",
                          strokeWidth=2, strokeDash=[4, 2])
                .encode(y=vak_y, x="start:T", x2="eind:T")
            )
            lagen.append(overlap_balken)
        vandaag_lijn = (
            alt.Chart(pd.DataFrame({"d": [pd.Timestamp(date.today())]}))
            .mark_rule(color="#e34948", strokeDash=[4, 3])
            .encode(x="d:T")
        )
        lagen.append(vandaag_lijn)
        st.altair_chart(
            alt.layer(*lagen).properties(height=640).configure_view(strokeOpacity=0),
            use_container_width=True,
        )
        st.markdown("---")

    # Horizon voor de jaarplanning-tabel en het (her)plannen: een vol jaar vooruit.
    aantal_weken_vooruit = 52

    def _toon_planresultaat(resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen):
        gepland = [r for r in resultaten if r[1] == "gepland"]
        buiten_horizon = [r for r in resultaten if r[1] == "buiten_horizon"]
        geen_geschiedenis = [r for r in resultaten if r[1] == "geen_geschiedenis"]

        totaal_concepten = len(get_planning())
        if gepland:
            st.success(
                f"✅ {len(gepland)} vakken ingepland — {totaal_concepten} concept-plantingen in totaal "
                "(meerdere teeltrondes per vak tot de horizon)."
            )
        else:
            st.info("Geen nieuwe vakken gepland binnen deze horizon.")
        if buiten_horizon:
            st.info(
                f"ℹ️ {len(buiten_horizon)} vakken komen pas ná de horizon vrij — vergroot 'Aantal weken "
                "vooruit' om ook die in te plannen: "
                + ", ".join(str(v) for v, _, _ in buiten_horizon)
            )
        if geen_geschiedenis:
            st.warning(
                f"⚠️ {len(geen_geschiedenis)} vakken hebben nog geen teeltgeschiedenis, dus geen "
                "voorstel: " + ", ".join(str(v) for v, _, _ in geen_geschiedenis)
            )
        for week_start, gevraagd, geplant in weekdoel_waarschuwingen:
            st.warning(
                f"⚠️ Week {week_start.isocalendar()[1]} - {week_start.year}: je vroeg {gevraagd} vak(ken), "
                f"maar er konden er maar {geplant} gepland worden (te weinig vakken vrij die week)."
            )
        for week_gevraagd, week_gepland in vak1_waarschuwingen:
            if week_gepland is None:
                st.warning(
                    f"⚠️ Vak 1 aangevinkt voor week {week_gevraagd.isocalendar()[1]} - {week_gevraagd.year}, "
                    "maar dat past niet binnen de horizon (vorige ronde is dan nog niet geoogst). "
                    "Vergroot 'Aantal weken vooruit' of vink een latere week aan."
                )
            else:
                st.warning(
                    f"⚠️ Vak 1 aangevinkt voor week {week_gevraagd.isocalendar()[1]} - {week_gevraagd.year}, "
                    f"maar kon pas in week {week_gepland.isocalendar()[1]} - {week_gepland.year} gepland "
                    "worden (vorige ronde nog niet klaar, of die week al vol)."
                )

    # Tuin 3 plant vak 2 t/m 39 als cyclus met 19+20 samen en vak 1 op een eigen
    # ritme; tuin 1 plant gewoon vak 1 t/m 27 op volgorde. De kolomnamen en de
    # uitleg volgen die vorm, de planner zelf werkt voor allebei hetzelfde.
    _eenheden_tuin, _los_vak = planner_eenheden(TUIN_ID)
    _cyclusvakken = [v for _rep, _vakken in _eenheden_tuin for v in _vakken] or [1]
    CYCLUS = f"{min(_cyclusvakken)}-{max(_cyclusvakken)}"
    KOLOM_VAKKEN = f"Vakken ({CYCLUS})"

    if True:
        st.markdown("---")
        st.write("**Jaarplanning: vakken per week**")
        if _los_vak:
            st.caption(
                f"Vul per week in hoeveel vakken je wilt poten uit de cyclus {CYCLUS} "
                f"(19+20 = 1, max {MAX_VAKKEN_PER_WEEK}) en of vak {_los_vak} die week mee moet. "
                "Een lege cel betekent: die week niets plannen. De planner vult zelf niets aan."
            )
        else:
            st.caption(
                f"Vul per week in hoeveel vakken je wilt poten (max {MAX_VAKKEN_PER_WEEK}). "
                f"De planner gaat op volgorde verder vanaf het vak waar {TUIN_NAAM} gebleven is. "
                "Een lege cel betekent: die week niets plannen."
            )
        weekoverzicht = get_planning_weekoverzicht(int(aantal_weken_vooruit))
        df_weekdoel = pd.DataFrame([
            {
                "Week": f"Week {r['week']} - {r['jaar']}",
                "Nu gepland": r["concepten"],
                KOLOM_VAKKEN: r["weekdoel"],
                "Vak 1": r["vak1_planten"],
            }
            for r in weekoverzicht
        ])
        if not _los_vak:
            df_weekdoel = df_weekdoel.drop(columns=["Vak 1"])
        bewerkt_weekdoel = st.data_editor(
            df_weekdoel,
            hide_index=True, key="weekdoel_editor",
            column_config={
                "Week": st.column_config.TextColumn(disabled=True),
                "Nu gepland": st.column_config.NumberColumn(
                    disabled=True, help="Aantal vakken dat nu voor die week gepland staat"
                ),
                KOLOM_VAKKEN: st.column_config.NumberColumn(
                    min_value=0, max_value=MAX_VAKKEN_PER_WEEK, step=1,
                    help="Leeg = die week niets plannen"
                ),
                "Vak 1": st.column_config.CheckboxColumn(help="Vak 1 in deze week poten"),
            },
        )
        col_herplan, col_wis = st.columns([2, 1])
        if col_herplan.button("🔄 Plan opnieuw met deze aantallen", key="plan_herplan"):
            for r, (_, rij) in zip(weekoverzicht, bewerkt_weekdoel.iterrows()):
                waarde = rij[KOLOM_VAKKEN]
                nieuw = None if pd.isna(waarde) else int(waarde)
                if nieuw != r["weekdoel"]:
                    set_planning_weekdoel(r["week_start"], nieuw, gebruiker=huidige_gebruiker())
                nieuw_vak1 = bool(rij["Vak 1"]) if _los_vak else False
                if _los_vak and nieuw_vak1 != r["vak1_planten"]:
                    set_planning_weekdoel_vak1(r["week_start"], nieuw_vak1, gebruiker=huidige_gebruiker())
            resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen = plan_x_weken_vooruit(
                int(aantal_weken_vooruit), gebruiker=huidige_gebruiker(), verwijder_bestaande=True
            )
            _toon_planresultaat(resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen)
            st.rerun()
        if col_wis.button("↩︎ Wis mijn jaarplanning", key="plan_wis_weekdoelen"):
            wis_planning_weekdoelen(gebruiker=huidige_gebruiker())
            st.rerun()

    st.markdown("---")
    st.write("**Overzicht per plantweek**")
    planning_per_week = get_planning_per_week()
    if planning_per_week:
        df_planning_week = pd.DataFrame(
            [
                (f"Week {week} - {jaar}", arbeidsaantal, ", ".join(str(v) for v in vakken))
                for jaar, week, vakken, arbeidsaantal in planning_per_week
            ],
            columns=["Plantweek", "Aantal vakken (arbeid)", "Vakken (oplopend)"]
        )
        toon_tabel(df_planning_week, [
            ("Plantweek", "Plantweek", "tekst", None, "medium"),
            ("Aantal vakken (arbeid)", "Aantal (arbeid)", "getal", "%d", "small"),
            ("Vakken (oplopend)", "Vakken", "tekst", None, "large"),
        ])
    else:
        st.info("Nog geen concept-planningen om per week te tonen.")

    st.markdown("---")
    st.write("**Eén vak handmatig plannen**")
    col_plan_vak, col_plan_datum = st.columns(2)
    plan_vaknummer = col_plan_vak.selectbox(
        "Vaknummer", get_vaknummers() or [1], key=f"plan_vaknummer_{TUIN_NUMMER}"
    )
    plan_startdatum = col_plan_datum.date_input(
        "Verwachte startdatum", value=datetime.today().date(),
        key=f"plan_startdatum_{int(plan_vaknummer)}", format="DD-MM-YYYY",
    )
    plan_duur, plan_eind = bereken_verwachte_oogstdatum(plan_startdatum)
    if plan_duur is not None:
        st.caption(
            f"Plantweek {get_weeknummer(plan_startdatum)} → verwachte teeltduur {plan_duur:g} weken, "
            f"verwachte oogst {format_datum(plan_eind)}"
        )
    else:
        st.caption("Geen teeltduur bekend voor deze plantweek (bijv. week 53).")
    if st.button("➕ Toevoegen aan planning", key="plan_toevoegen"):
        voeg_planning_toe(int(plan_vaknummer), plan_startdatum, gebruiker=huidige_gebruiker())
        st.success(f"✅ Concept-planning toegevoegd voor vak {int(plan_vaknummer)}.")
        st.rerun()

    st.markdown("---")
    st.write("**Concept-planningen**")
    planning_rijen = get_planning()  # al gesorteerd op startdatum (dus per week), dan vaknummer

    if planning_rijen:
        huidige_weeksleutel = None
        for planning_id, vaknummer, start, duur, eind, notitie in planning_rijen:
            start_d = datetime.strptime(start, "%Y-%m-%d").date()
            weeksleutel = get_isojaar_week(start)
            if weeksleutel != huidige_weeksleutel:
                jaar_kop, week_kop = weeksleutel
                st.markdown(f"**Week {week_kop} - {jaar_kop}**")
                huidige_weeksleutel = weeksleutel

            col1, col2, col2b, col3, col4, col5, col6, col7 = st.columns(
                [0.8, 1.6, 0.6, 1, 1.6, 1.5, 0.8, 0.8]
            )
            col1.write(f"Vak {vaknummer}")
            nieuwe_datum_plan = col2.date_input(
                "Startdatum", value=start_d,
                key=f"plan_datum_{planning_id}", format="DD-MM-YYYY", label_visibility="collapsed",
            )
            if col2b.button("💾", key=f"plan_datum_opslaan_{planning_id}", help="Startdatum aanpassen"):
                wijzig_planning(planning_id, nieuwe_datum_plan, gebruiker=huidige_gebruiker())
                st.rerun()
            col3.write(f"{duur:g} wk" if duur is not None else "-")
            col4.write(format_datum(eind) if eind else "-")
            dichtheid_plan = standaard_dichtheid_voor_plantweek(get_weeknummer(start))
            aantal_planten_plan = col5.number_input(
                "Aantal planten",
                min_value=0, step=1, value=bereken_aantal_stelen(vaknummer, dichtheid_plan),
                key=f"plan_aantal_{planning_id}",
                label_visibility="collapsed",
                help=f"Aantal planten bij bevestigen (standaard {dichtheid_plan} stelen/m² o.b.v. plantweek; pas aan indien nodig).",
            )
            if col6.button("✅", key=f"plan_bevestig_{planning_id}", help="Omzetten naar een echte teeltregistratie"):
                resultaat = bevestig_planning(
                    planning_id,
                    aantal_planten_plan if aantal_planten_plan else None,
                    gebruiker=huidige_gebruiker(),
                )
                if resultaat:
                    teelt_id, code = resultaat
                    st.success(f"✅ Vak {vaknummer} gestart - code **{code}** (teelt-ID {teelt_id}).")
                st.rerun()
            if col7.button("🗑️", key=f"plan_verwijder_{planning_id}", help="Concept-planning verwijderen"):
                verwijder_planning(planning_id, gebruiker=huidige_gebruiker())
                st.rerun()
    else:
        st.info("Nog geen concept-planningen.")


# --- STEK ---
# Kolommen van het weekrapport, zoals de stekleverancier ze uit het oude
# Excel-blad "Weekrapport" gewend is.
STEK_RAPPORT_KOLOMMEN = [
    "Datum", "Vak", "Plant", "Te poten", "Bakjes gepoot", "Uitval (%)",
    "Wortel", "Plantmaat", "Uniformiteit", "Beoordeling", "Opmerkingen",
]
_DAGEN_STEK = ["ma", "di", "wo", "do", "vr", "za", "zo"]
NIET_WIJZIGEN = "— niet wijzigen —"


def _leeg_naar_none(waarde):
    """Lege cel uit st.data_editor (None, NaN of lege tekst) -> None."""
    if waarde is None or (not isinstance(waarde, str) and pd.isna(waarde)):
        return None
    if isinstance(waarde, str) and not waarde.strip():
        return None
    return waarde.strip() if isinstance(waarde, str) else waarde


def _getal_nl(waarde, decimalen=1):
    """Getal met komma, zoals in een Nederlandse mail."""
    return f"{waarde:.{decimalen}f}".replace(".", ",")


def _stek_mailtekst(rapport, week, jaar, afzender):
    """
    Platte tekst voor de mail: één regel per vak. Geen uitgelijnde tabel,
    want die valt in een mailprogramma met gewoon lettertype uit elkaar.
    """
    regels = []
    for _, r in rapport.iterrows():
        delen = [f"Vak {r['Vak']} ({r['Datum']})"]
        if pd.notna(r["Te poten"]):
            delen.append(f"{int(r['Te poten'])} gepoot")
        if pd.notna(r["Bakjes gepoot"]):
            delen.append(f"{_getal_nl(r['Bakjes gepoot']).removesuffix(',0')} bakjes")
        if pd.notna(r["Uitval (%)"]):
            delen.append(f"uitval {_getal_nl(r['Uitval (%)'])}%")
        for kolom in ("Wortel", "Plantmaat", "Uniformiteit"):
            if r[kolom]:
                delen.append(f"{kolom.lower()} {r[kolom].lower()}")
        if pd.notna(r["Beoordeling"]):
            delen.append(f"cijfer {int(r['Beoordeling'])}")
        regel = " · ".join(delen)
        if r["Opmerkingen"]:
            regel += f"\n    {r['Opmerkingen']}"
        regels.append(regel)
    return (
        f"Beste,\n\nHierbij de stekresultaten van week {week} ({jaar}):\n\n"
        + "\n".join(regels)
        + "\n\nUitval = het deel van de geleverde stekken (bakjes x 600) dat niet gepoot is."
        + f"\n\nMet vriendelijke groet,\n{afzender}\nVan Egmond Matricaria"
    )


with tab_stek:
    st.subheader("🌱 Stek")
    stekweken = get_stekweken()
    if not stekweken:
        st.info("Er zijn nog geen teelten gestart.")
    else:
        vandaag_stek = date.today()
        deze_maandag = vandaag_stek - timedelta(days=vandaag_stek.weekday())
        # Standaard de huidige week; is daar nog niets gepoot, dan de laatste week waarin wel.
        standaard_stekweek = next((m for m in stekweken if m <= deze_maandag), stekweken[-1])

        def _stekweek_label(maandag):
            jaar_s, week_s = get_isojaar_week(maandag)
            return (f"Week {week_s} - {jaar_s} "
                    f"({format_datum(maandag)} t/m {format_datum(maandag + timedelta(days=6))})")

        stek_maandag = st.selectbox(
            "Pootweek", stekweken, index=stekweken.index(standaard_stekweek),
            format_func=_stekweek_label, key="stek_week",
        )
        stek_jaar, stek_week = get_isojaar_week(stek_maandag)
        rijen_stek = get_stek_voor_week(stek_maandag)

        st.caption(
            "Vul per vak het geleverde stek in. Te poten komt uit de teeltregistratie; "
            "de uitval rekent de app zelf uit (bakjes × 600 stekken)."
        )
        # Het stek van een week komt uit dezelfde partij, dus de beoordeling is
        # meestal voor alle vakken gelijk: hier één keer invullen, daarna in de
        # tabel per vak aanpassen als een vak afwijkt.
        def _gedeeld(veld):
            """De waarde als alle ingevulde vakken het erover eens zijn, anders None."""
            waarden = {r[veld] for r in rijen_stek if r[veld] not in (None, "")}
            return waarden.pop() if len(waarden) == 1 else None

        with st.container(border=True):
            st.write("**Hele week invullen**")
            kol1, kol2, kol3 = st.columns(3)
            totaal_bakjes = kol1.number_input(
                "Totaal geleverde bakjes", min_value=0.0, step=0.25, format="%.2f",
                value=float(sum(r["bakjes"] or 0 for r in rijen_stek)),
                help="Wordt verdeeld naar rato van het aantal te poten planten, zodat een "
                     "half vak de helft krijgt. Afronding op kwart bakjes; de som klopt precies.",
                key=f"stek_totaal_{stek_maandag}",
            )

            def _keuze(kolom, veld, label, opties):
                huidig = _gedeeld(veld)
                keuzes = [NIET_WIJZIGEN] + list(opties)
                return kolom.selectbox(
                    label, keuzes,
                    index=keuzes.index(huidig) if huidig in keuzes else 0,
                    key=f"stek_week_{veld}_{stek_maandag}",
                )

            week_wortel = _keuze(kol2, "wortel", "Wortel", STEK_KEUZES["wortel"])
            week_plantmaat = _keuze(kol3, "plantmaat", "Plantmaat", STEK_KEUZES["plantmaat"])
            kol4, kol5, kol6 = st.columns([1, 1, 2])
            week_uniformiteit = _keuze(kol4, "uniformiteit", "Uniformiteit", STEK_KEUZES["uniformiteit"])
            week_cijfer = _keuze(kol5, "beoordeling", "Beoordeling", range(1, 11))
            week_opmerking = kol6.text_input(
                "Opmerking", value=_gedeeld("opmerking") or "",
                key=f"stek_week_opmerking_{stek_maandag}",
            )
            st.caption(
                f"Vult alle {len(rijen_stek)} vakken van deze week in één keer. "
                f"'{NIET_WIJZIGEN}' laat staan wat er per vak staat; wijkt een vak af, "
                "pas het dan in de tabel hieronder aan."
            )
            if st.button("📋 Invullen voor alle vakken", key=f"stek_week_vullen_{stek_maandag}",
                         disabled=not rijen_stek):
                verdeling = (verdeel_bakjes(totaal_bakjes, [r["aantal_planten"] for r in rijen_stek])
                             if totaal_bakjes else [r["bakjes"] for r in rijen_stek])
                for rij_stek, bakjes_vak in zip(rijen_stek, verdeling):
                    velden = {veld: rij_stek[veld] for veld in
                              ("wortel", "plantmaat", "uniformiteit", "beoordeling", "opmerking")}
                    for veld, gekozen in (("wortel", week_wortel), ("plantmaat", week_plantmaat),
                                          ("uniformiteit", week_uniformiteit), ("beoordeling", week_cijfer)):
                        if gekozen != NIET_WIJZIGEN:
                            velden[veld] = gekozen
                    if week_opmerking.strip() or _gedeeld("opmerking"):
                        velden["opmerking"] = week_opmerking.strip() or None
                    sla_stekbeoordeling_op(
                        rij_stek["teelt_id"],
                        {**velden, "ras": rij_stek["ras"] or STEK_STANDAARD_RAS, "bakjes": bakjes_vak},
                        gebruiker=huidige_gebruiker(),
                    )
                st.session_state["stek_melding"] = f"Ingevuld voor {len(rijen_stek)} vakken."
                st.rerun()

        df_stek = pd.DataFrame(
            [{
                "Datum": f"{_DAGEN_STEK[date.fromisoformat(r['datum'][:10]).weekday()]} {format_datum(r['datum'])}",
                "Vak": r["vaknummer"],
                "Te poten": r["aantal_planten"],
                "Plant": r["ras"] or STEK_STANDAARD_RAS,
                "Bakjes": r["bakjes"],
                "Wortel": r["wortel"],
                "Plantmaat": r["plantmaat"],
                "Uniformiteit": r["uniformiteit"],
                "Beoordeling": r["beoordeling"],
                "Opmerking": r["opmerking"] or "",
            } for r in rijen_stek],
            index=[r["teelt_id"] for r in rijen_stek],
        )
        bewerkt_stek = st.data_editor(
            df_stek,
            hide_index=True,
            key=f"stek_editor_{stek_maandag}",
            disabled=["Datum", "Vak", "Te poten"],
            column_config={
                "Vak": st.column_config.NumberColumn(format="%d", width="small"),
                "Te poten": st.column_config.NumberColumn(format="%d", width="small"),
                "Plant": st.column_config.TextColumn(width="small"),
                "Bakjes": st.column_config.NumberColumn(
                    min_value=0.0, step=0.5, format="%.1f", width="small",
                    help="Aantal gepote bakjes (600 stekken per bakje)",
                ),
                "Wortel": st.column_config.SelectboxColumn(options=STEK_KEUZES["wortel"], width="small"),
                "Plantmaat": st.column_config.SelectboxColumn(options=STEK_KEUZES["plantmaat"], width="small"),
                "Uniformiteit": st.column_config.SelectboxColumn(
                    options=STEK_KEUZES["uniformiteit"], width="small"
                ),
                "Beoordeling": st.column_config.NumberColumn(
                    min_value=1, max_value=10, step=1, format="%d", width="small",
                    help="Totaalcijfer 1-10",
                ),
                "Opmerking": st.column_config.TextColumn(width="large"),
            },
        )

        niet_opgeslagen = not bewerkt_stek.fillna("").astype(str).equals(df_stek.fillna("").astype(str))
        col_opslaan, col_status = st.columns([1, 3])
        if col_opslaan.button("💾 Opslaan", key="stek_opslaan", type="primary", disabled=not niet_opgeslagen):
            opgeslagen = 0
            for teelt_id, rij in bewerkt_stek.iterrows():
                velden = {
                    "ras": _leeg_naar_none(rij["Plant"]),
                    "bakjes": None if pd.isna(rij["Bakjes"]) else float(rij["Bakjes"]),
                    "wortel": _leeg_naar_none(rij["Wortel"]),
                    "plantmaat": _leeg_naar_none(rij["Plantmaat"]),
                    "uniformiteit": _leeg_naar_none(rij["Uniformiteit"]),
                    "beoordeling": None if pd.isna(rij["Beoordeling"]) else int(rij["Beoordeling"]),
                    "opmerking": _leeg_naar_none(rij["Opmerking"]),
                }
                # Alleen het (vooringevulde) ras en verder niets: geen lege beoordeling aanmaken.
                if all(waarde is None for veld, waarde in velden.items() if veld != "ras"):
                    continue
                if sla_stekbeoordeling_op(int(teelt_id), velden, gebruiker=huidige_gebruiker()):
                    opgeslagen += 1
            st.session_state["stek_melding"] = f"{opgeslagen} vak(ken) opgeslagen."
            st.rerun()
        if "stek_melding" in st.session_state:
            col_status.success(st.session_state.pop("stek_melding"))
        elif niet_opgeslagen:
            col_status.warning("Wijzigingen nog niet opgeslagen.")

        # Het rapport volgt het invulblad direct, ook vóór het opslaan.
        st.markdown("---")
        st.write(f"**📧 Weekrapport voor de stekleverancier — week {stek_week}**")
        rapport_stek = pd.DataFrame({
            "Datum": [format_datum(r["datum"]) for r in rijen_stek],
            "Vak": bewerkt_stek["Vak"].to_list(),
            "Plant": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Plant"]],
            "Te poten": bewerkt_stek["Te poten"].to_list(),
            "Bakjes gepoot": bewerkt_stek["Bakjes"].to_list(),
            "Uitval (%)": [
                round(u, 1) if (u := stek_uitval_pct(p, None if pd.isna(b) else b)) is not None else None
                for p, b in zip(bewerkt_stek["Te poten"], bewerkt_stek["Bakjes"])
            ],
            "Wortel": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Wortel"]],
            "Plantmaat": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Plantmaat"]],
            "Uniformiteit": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Uniformiteit"]],
            "Beoordeling": bewerkt_stek["Beoordeling"].to_list(),
            "Opmerkingen": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Opmerking"]],
        }, columns=STEK_RAPPORT_KOLOMMEN)
        toon_tabel(rapport_stek, [
            ("Datum", "Datum", "datum", None, "small"),
            ("Vak", "Vak", "getal", "%d", "small"),
            ("Plant", "Plant", "tekst", None, "small"),
            ("Te poten", "Te poten", "getal", "%d", "small"),
            ("Bakjes gepoot", "Bakjes gepoot", "getal", "%.1f", "small"),
            ("Uitval (%)", "Uitval (%)", "getal", "%.1f", "small"),
            ("Wortel", "Wortel", "tekst", None, "small"),
            ("Plantmaat", "Plantmaat", "tekst", None, "small"),
            ("Uniformiteit", "Uniformiteit", "tekst", None, "small"),
            ("Beoordeling", "Beoordeling", "getal", "%d", "small"),
            ("Opmerkingen", "Opmerkingen", "tekst", None, "large"),
        ])

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as schrijver:
            rapport_stek.to_excel(schrijver, index=False, sheet_name=f"Week {stek_week}")
        leverancier_email = get_instelling("stek_leverancier_email", "")
        onderwerp_stek = f"Stekresultaten week {stek_week} - {stek_jaar} - Van Egmond Matricaria"
        mailtekst_stek = _stek_mailtekst(
            rapport_stek, stek_week, stek_jaar, st.session_state.get("name") or "",
        )

        col_excel, col_mail = st.columns(2)
        col_excel.download_button(
            "⬇️ Download als Excel", excel_buffer.getvalue(),
            file_name=f"Stekresultaten week {stek_week:02d}-{stek_jaar}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="stek_download",
        )
        col_mail.link_button(
            "✉️ Mail opstellen",
            f"mailto:{leverancier_email}?subject={urllib.parse.quote(onderwerp_stek)}"
            f"&body={urllib.parse.quote(mailtekst_stek)}",
        )
        if niet_opgeslagen:
            st.caption("Let op: het rapport toont ook wat nog niet is opgeslagen.")
        with st.expander("Voorbeeld van de mailtekst"):
            st.text(mailtekst_stek)
        with st.expander("⚙️ E-mailadres stekleverancier"):
            nieuw_email = st.text_input(
                "Wordt als ontvanger ingevuld bij 'Mail opstellen'", value=leverancier_email,
                key="stek_email_invoer",
            )
            if st.button("Opslaan", key="stek_email_opslaan") and nieuw_email.strip() != leverancier_email:
                set_instelling("stek_leverancier_email", nieuw_email.strip() or None, gebruiker=huidige_gebruiker())
                st.rerun()


# --- KLIMAATDATA (KLIMAATCOMPUTER-CSV) ---
with tab_klimaat:
    st.subheader("🌡️ Klimaatdata")

    with st.expander("📤 Data importeren"):
        col_imp_klimaat, col_imp_energie, col_imp_priva = st.columns(3)

        with col_imp_klimaat:
            klimaat_csv = st.file_uploader(
                "Klimaatcomputer-export (.csv)",
                type=["csv"],
                key="klimaat_csv_upload",
                help="Dagexport met kolommen label, pcu, type_1, idx_1, type_2, idx_2, startdate, enddate, value.",
            )
            if klimaat_csv is not None:
                try:
                    aantal_verwerkt, aantal_overgeslagen = verwerk_klimaat_csv(
                        klimaat_csv, gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID)
                    melding = f"✅ {aantal_verwerkt} afdeling-dagen verwerkt."
                    if aantal_overgeslagen:
                        melding += f" {aantal_overgeslagen} overgeslagen (nog niet afgerond)."
                    st.success(melding)
                except Exception as e:
                    st.error(f"❌ Kon de CSV niet verwerken: {e}")

        with col_imp_energie:
            energie_csv = st.file_uploader(
                "Energiecomputer-export (.csv)",
                type=["csv"],
                key="energie_csv_upload",
                help="Rapport Energie-export uit Priva; hieruit worden de Pulsteller (warmteverbruik hele kas) "
                     "en, in weken met bijstook, het gasverbruik gehaald.",
            )
            if energie_csv is not None:
                try:
                    aantal_verwerkt_e, aantal_overgeslagen_e, aantal_gas_e = verwerk_energie_csv(
                        energie_csv, gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID
                    )
                    melding_e = f"✅ {aantal_verwerkt_e} dagen warmteverbruik verwerkt."
                    if aantal_gas_e:
                        melding_e += f" {aantal_gas_e} dagen gasverbruik verwerkt."
                    if aantal_overgeslagen_e:
                        melding_e += f" {aantal_overgeslagen_e} overgeslagen (nog niet afgerond)."
                    st.success(melding_e)
                except Exception as e:
                    st.error(f"❌ Kon de CSV niet verwerken: {e}")

        with col_imp_priva:
            if os.environ.get("PRIVA_CLIENT_ID"):
                st.caption(
                    f"Of haal de laatste afgeronde dagen rechtstreeks uit Priva voor {TUIN_NAAM}: "
                    "klimaat en watergift. Historische CSV-data blijft staan."
                )
                if st.button("📡 Haal laatste dagen op uit Priva"):
                    try:
                        aantal_k, _ = importeer_klimaat_uit_priva(
                            gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID)
                        aantal_w, _ = importeer_watergift_uit_priva(
                            gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID)
                        st.success(f"✅ {aantal_k} afdeling-dagen klimaat, {aantal_w} vak-dagen watergift opgehaald.")
                    except Exception as e:
                        st.error(f"❌ Kon niet uit Priva ophalen: {e}")

                water_dekking = get_watergift_dekking()
                if water_dekking:
                    laatste_water = max(r[2] for r in water_dekking)
                    st.caption(f"Watergift: {len(water_dekking)} vakken, tot {format_datum(laatste_water)}.")
            else:
                st.caption("Priva-koppeling niet geconfigureerd (PRIVA_CLIENT_ID ontbreekt).")

    dekking = get_klimaatdata_dekking()
    kolommen_klimaat, rijen_klimaat = get_klimaat_overzicht_dataframe()

    if not dekking and not rijen_klimaat:
        st.info(
            "Nog geen gekoppelde klimaatdata. Upload hierboven een CSV-export uit de klimaatcomputer "
            "of haal 'm uit Priva; de gemiddelde temperatuur, RV en dagstralingssom worden automatisch "
            "gekoppeld aan elke teelt op basis van vaknummer (→ afdeling) en teeltperiode."
        )

    # --- Grafieken: klimaatverloop per afdeling over een vrije periode ---
    if dekking:
        st.write("**Grafieken**")
        alle_afdelingen = [r[0] for r in dekking]
        data_eerste = datetime.strptime(min(r[1] for r in dekking), "%Y-%m-%d").date()
        data_laatste = datetime.strptime(max(r[2] for r in dekking), "%Y-%m-%d").date()

        col_afd, col_van, col_tot = st.columns([2, 1, 1])
        gekozen_afdelingen = col_afd.multiselect(
            "Afdeling(en)", alle_afdelingen, default=alle_afdelingen, key="klimaat_grafiek_afd"
        )
        standaard_van = max(data_eerste, data_laatste - timedelta(days=90))
        datum_van = col_van.date_input(
            "Van", value=standaard_van, min_value=data_eerste, max_value=data_laatste,
            key="klimaat_grafiek_van", format="DD-MM-YYYY",
        )
        datum_tot = col_tot.date_input(
            "Tot en met", value=data_laatste, min_value=data_eerste, max_value=data_laatste,
            key="klimaat_grafiek_tot", format="DD-MM-YYYY",
        )
        col_dn, col_tr = st.columns(2)
        toon_dagnacht = col_dn.checkbox(
            "Toon ook dag- en nachtgemiddelde", value=False, key="klimaat_grafiek_dagnacht"
        )
        toon_trend = col_tr.checkbox(
            "Toon trendlijn (voortschrijdend gemiddelde)", value=False, key="klimaat_grafiek_trend"
        )

        if gekozen_afdelingen and datum_van <= datum_tot:
            records = []
            for afdeling in sorted(gekozen_afdelingen):
                for datum, temp, rv, straling, temp_dag, temp_nacht, rv_dag, rv_nacht in \
                        get_klimaatdata_dagen_voor_periode(afdeling, datum_van, datum_tot):
                    records.append({
                        "datum": datum, "afdeling": afdeling,
                        "temp_24h": temp, "temp_dag": temp_dag, "temp_nacht": temp_nacht,
                        "rv_24h": rv, "rv_dag": rv_dag, "rv_nacht": rv_nacht,
                        "lichtsom": straling,
                    })
            klimaat_grafieken(records, toon_dagnacht=toon_dagnacht, toon_trend=toon_trend)

            st.markdown("---")
            st.write("**Licht/temperatuur-verhouding**")
            licht_temperatuur_grafiek(records)
        elif datum_van > datum_tot:
            st.warning("'Van' ligt na 'Tot en met'.")

    # --- Warmteverbruik (Pulsteller, hele kas) ---
    energie_dekking = get_energiedata_dekking()
    if energie_dekking:
        st.markdown("---")
        st.write("**Warmteverbruik (hele kas)**")
        e_eerste, e_laatste, e_aantal, e_ontbrekend = energie_dekking
        e_eerste_d = datetime.strptime(e_eerste, "%Y-%m-%d").date()
        e_laatste_d = datetime.strptime(e_laatste, "%Y-%m-%d").date()
        e_standaard_van = max(e_eerste_d, e_laatste_d - timedelta(days=90))
        col_e_van, col_e_tot = st.columns(2)
        e_datum_van = col_e_van.date_input(
            "Van", value=e_standaard_van, min_value=e_eerste_d, max_value=e_laatste_d,
            key="energie_grafiek_van", format="DD-MM-YYYY",
        )
        e_datum_tot = col_e_tot.date_input(
            "Tot en met", value=e_laatste_d, min_value=e_eerste_d, max_value=e_laatste_d,
            key="energie_grafiek_tot", format="DD-MM-YYYY",
        )
        if e_datum_van <= e_datum_tot:
            energie_dagen = get_energiedata_dagen_voor_periode(e_datum_van, e_datum_tot)
            gas_dagen = get_gasdata_dagen_voor_periode(e_datum_van, e_datum_tot)
            if energie_dagen or gas_dagen:
                df_energie = pd.DataFrame(energie_dagen, columns=["datum", "warmte_mj_totaal", "MJ per m²"])
                df_gas = pd.DataFrame(gas_dagen, columns=["datum", "gas_m3_totaal", "gas_mj_totaal", "gas_mj_per_m2"])
                df_warmte_dag = pd.merge(
                    df_energie[["datum", "warmte_mj_totaal"]],
                    df_gas[["datum", "gas_mj_totaal"]],
                    on="datum", how="outer",
                ).fillna(0)
                df_warmte_dag["Hoofdwarmte (GJ)"] = df_warmte_dag["warmte_mj_totaal"] / 1000
                df_warmte_dag["Gasketel (GJ)"] = df_warmte_dag["gas_mj_totaal"] / 1000
                df_warmte_dag["datum"] = pd.to_datetime(df_warmte_dag["datum"])

                df_warmte_lang = df_warmte_dag.melt(
                    id_vars="datum", value_vars=["Hoofdwarmte (GJ)", "Gasketel (GJ)"],
                    var_name="Bron", value_name="GJ",
                )
                warmte_chart = alt.Chart(df_warmte_lang).mark_bar().encode(
                    x=datum_as(),
                    y=alt.Y("GJ:Q", title="Warmte (GJ)", stack=True),
                    color=alt.Color(
                        "Bron:N",
                        scale=alt.Scale(domain=["Hoofdwarmte (GJ)", "Gasketel (GJ)"], range=["#2a78d6", "#c0392b"]),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Bron:N",
                             alt.Tooltip("GJ:Q", format=".2f")],
                )
                st.altair_chart(warmte_chart, use_container_width=True)
        else:
            st.warning("'Van' ligt na 'Tot en met'.")
        st.caption(
            f"Warmteverbruik geregistreerd van {format_datum(e_eerste)} t/m {format_datum(e_laatste)} "
            f"({e_aantal} dagen, {e_ontbrekend} ontbrekend). Kasoppervlak {TUIN_NAAM}: "
            f"{oppervlakte_van_tuin(TUIN_ID) or 0:,.0f} m²."
            .replace(",", ".")
        )
        gas_dekking = get_gasdata_dekking()
        if gas_dekking:
            g_eerste, g_laatste, g_aantal = gas_dekking
            st.caption(
                f"Gasketel (bijstook, Pulsteller 1) geregistreerd van {format_datum(g_eerste)} t/m "
                f"{format_datum(g_laatste)} ({g_aantal} dagen), omgerekend met "
                f"{GAS_CALORISCHE_WAARDE_MJ_PER_M3} MJ/m³."
            )

    # --- Gemiddelden per teelt (onder de grafieken) ---
    if rijen_klimaat:
        st.markdown("---")
        with st.expander(f"📋 Gemiddelden per teelt ({len(rijen_klimaat)})"):
            df_klimaat = pd.DataFrame(rijen_klimaat, columns=kolommen_klimaat)
            toon_tabel(df_klimaat, [
                ("Code", "Code", "tekst", None, "medium"),
                ("Teeltvak", "Vak", "tekst", None, "small"),
                ("Afdeling", "Afd.", "getal", "%d", "small"),
                ("Startdatum", "Start", "datum", None, "small"),
                ("Oogstdatum", "Oogst", "tekst", None, "small"),
                ("Gem. temperatuur (°C)", "Temp. (°C)", "getal", "%.1f", "small"),
                ("Gem. RV (%)", "RV (%)", "getal", "%.1f", "small"),
                ("Gem. stralingssom (per dag)", "Lichtsom/dag", "getal", "%d", "small"),
                ("Ideale temp (°C)", "Ideaal (°C)", "getal", "%.1f", "small"),
                ("Verschil (°C)", "Verschil (°C)", "tekst", None, "small"),
                ("Totaal water (l/m²)", "Water (l/m²)", "getal", "%.1f", "small"),
                ("Totaal warmte (GJ)", "Warmte (GJ)", "getal", "%.2f", "small"),
            ], pin_eerste=True)

    # --- Geïmporteerd t/m: per afdeling tot welke dag er data is (onderaan) ---
    if dekking:
        with st.expander("🗂️ Geïmporteerd t/m (dekking per afdeling)"):
            laatste_alle = max(r[2] for r in dekking)
            dekking_rijen = []
            for afdeling, eerste, laatste, aantal, ontbrekend in dekking:
                achterstand = (
                    datetime.strptime(laatste_alle, "%Y-%m-%d").date()
                    - datetime.strptime(laatste, "%Y-%m-%d").date()
                ).days
                dekking_rijen.append({
                    "Afdeling": afdeling,
                    "Eerste dag": format_datum(eerste),
                    "Laatste dag": format_datum(laatste),
                    "Dagen": aantal,
                    "Ontbrekende dagen": ontbrekend,
                    "Loopt achter": f"{achterstand} dg" if achterstand else "-",
                })
            toon_tabel(pd.DataFrame(dekking_rijen), [
                ("Afdeling", "Afdeling", "getal", "%d", "small"),
                ("Eerste dag", "Eerste dag", "datum", None, "small"),
                ("Laatste dag", "Laatste dag", "datum", None, "small"),
                ("Dagen", "Dagen", "getal", "%d", "small"),
                ("Ontbrekende dagen", "Ontbrekend", "getal", "%d", "small"),
                ("Loopt achter", "Loopt achter", "tekst", None, "small"),
            ])
            dagen_oud = (datetime.today().date() - datetime.strptime(laatste_alle, "%Y-%m-%d").date()).days
            st.caption(
                f"Nieuwste geïmporteerde dag: {format_datum(laatste_alle)} ({dagen_oud} dag(en) geleden). "
                "**Ontbrekende dagen** = dagen tussen de eerste en laatste dag zonder data (bijv. overgeslagen "
                "omdat de dag nog niet compleet was bij het uploaden). **Loopt achter** = hoeveel dagen die "
                "afdeling achterloopt op de afdeling met de meest recente data (0 = alles gelijk geïmporteerd)."
            )

# --- STATISTIEKEN ---
with tab_stats:
    st.subheader("📈 Statistieken & Inzichten")
    if rijen:
        df_stats = pd.DataFrame(rijen, columns=kolommen)

        # Teeltduur analyse
        df_afgerond = df_stats[df_stats['Oogstdatum'] != '-'].copy()
        if len(df_afgerond) > 0:
            st.write("**Teeltduur analyse (afgeronde teelten):**")
            df_afgerond['Teeltduur (dagen)'] = pd.to_numeric(df_afgerond['Teeltduur (dagen)'], errors='coerce')
            gemiddeld = df_afgerond['Teeltduur (dagen)'].mean()
            minimum = df_afgerond['Teeltduur (dagen)'].min()
            maximum = df_afgerond['Teeltduur (dagen)'].max()

            toon_kengetallen([
                {"label": "Gemiddeld", "waarde": f"{gemiddeld:.0f} dgn"},
                {"label": "Kortst", "waarde": f"{minimum:.0f} dgn"},
                {"label": "Langst", "waarde": f"{maximum:.0f} dgn"},
            ])

        # --- Analyse: lengtegroei ---
        st.markdown("---")
        st.write("**Lengtegroei: halverwege → oogst**")
        st.caption(
            "Factor = oogstlengte / lengte halverwege. Gebaseerd op alle afgeronde teelten met beide metingen."
        )

        alle_teelten_stats = get_alle_teelten_detail()
        analyse_lengte_rijen = [
            {
                "Oogstdatum": t["datum_oogst"],
                "Vak": t["vaknummer"],
                "Code": t["code"] or "-",
                "Lengte halverwege (cm)": t["lengte_half"],
                "Lengte oogst (cm)": t["lengte_eind"],
                "Factor (oogst / halverwege)": t["lengte_eind"] / t["lengte_half"],
            }
            for t in alle_teelten_stats
            if t["datum_oogst"] and t["lengte_half"] and t["lengte_eind"]
        ]

        if len(analyse_lengte_rijen) < 2:
            st.info("Nog te weinig teelten met zowel een halverwege- als oogstlengte voor deze grafiek.")
        else:
            df_lengte = pd.DataFrame(analyse_lengte_rijen).sort_values("Oogstdatum")
            df_lengte["Oogstdatum"] = pd.to_datetime(df_lengte["Oogstdatum"])

            df_lengte_lang = df_lengte.melt(
                id_vars=["Oogstdatum", "Vak", "Code"],
                value_vars=["Lengte halverwege (cm)", "Lengte oogst (cm)"],
                var_name="Meting", value_name="Lengte (cm)",
            )
            lijn_lengte = alt.Chart(df_lengte_lang).mark_line(point=True).encode(
                x=datum_as("Oogstdatum", veld="Oogstdatum"),
                y=alt.Y("Lengte (cm):Q", title="Lengte (cm)", scale=alt.Scale(zero=False)),
                color=alt.Color("Meting:N", title=None),
                tooltip=["Oogstdatum:T", "Vak:N", "Code:N", "Meting:N", alt.Tooltip("Lengte (cm):Q", format=".1f")],
            )
            lijn_factor = alt.Chart(df_lengte).mark_line(point=True, color="#c0392b", strokeDash=[4, 4]).encode(
                x=datum_as("Oogstdatum", veld="Oogstdatum"),
                y=alt.Y("Factor (oogst / halverwege):Q", title="Factor (oogst / halverwege)",
                        scale=alt.Scale(zero=False)),
                tooltip=["Oogstdatum:T", "Vak:N", "Code:N", alt.Tooltip("Factor (oogst / halverwege):Q", format=".2f")],
            )
            st.altair_chart(
                alt.layer(lijn_lengte, lijn_factor).resolve_scale(y="independent"),
                use_container_width=True,
            )
            st.caption(
                f"Gebaseerd op {len(df_lengte)} afgeronde teelten met zowel een halverwege- als oogstmeting "
                "(rode stippellijn = factor, rechteras)."
            )

        # --- Analyse: groeifactoren vs. resultaat ---
        st.markdown("---")
        st.write("**Analyse: groeifactoren vs. resultaat (afgeronde teelten)**")
        st.caption(
            "Combineert lichtsom, temperatuur en watergift tijdens de teelt met het eindresultaat "
            "(gewicht, lengte, rijpheid, teeltduur) en zoekt naar de sterkste samenhang."
        )

        # Uit dezelfde bron als het teeltoverzicht: dat is een query voor alle
        # teelten samen, in plaats van per teelt klimaat en water opvragen.
        analyse_rijen = []
        for k in get_teeltkengetallen():
            if not k["datum_oogst"]:
                continue
            laag, hoog = rijpheid_tekst_naar_bereik(k["rijpheid"]) if k["rijpheid"] else (None, None)
            lichtsom_per_dag = (
                k["lichtsom"] / k["klimaatdagen"] if k["lichtsom"] and k["klimaatdagen"] else None
            )
            analyse_rijen.append({
                "Teeltduur (dagen)": k["teeltduur"],
                "Gewicht (g)": k["oogstgewicht"],
                "Lengte (cm)": k["lengte_eind"],
                "Rijpheid": (laag + hoog) / 2 if laag is not None else None,
                "Lichtsom (per dag)": lichtsom_per_dag,
                "Temperatuur (°C)": k["gem_temperatuur"],
                "Water (l/m²)": k["liters"],
            })

        df_analyse = pd.DataFrame(analyse_rijen).apply(pd.to_numeric, errors="coerce")

        if len(df_analyse) < 5:
            st.info("Nog te weinig afgeronde teelten voor een zinvolle analyse (minimaal 5 nodig).")
        else:
            kolommen_analyse = list(df_analyse.columns)
            corr = df_analyse.corr(min_periods=5)

            corr_lang = (
                corr.reset_index().melt(id_vars="index", var_name="Variabele 2", value_name="r")
                .rename(columns={"index": "Variabele 1"}).dropna(subset=["r"])
            )
            heatmap = alt.Chart(corr_lang).mark_rect().encode(
                x=alt.X("Variabele 1:N", title=None, sort=kolommen_analyse),
                y=alt.Y("Variabele 2:N", title=None, sort=kolommen_analyse),
                color=alt.Color("r:Q", title="Correlatie", scale=alt.Scale(scheme="redblue", domain=[-1, 1])),
                tooltip=["Variabele 1:N", "Variabele 2:N", alt.Tooltip("r:Q", format=".2f")],
            )
            tekst = alt.Chart(corr_lang).mark_text(fontSize=11).encode(
                x=alt.X("Variabele 1:N", sort=kolommen_analyse),
                y=alt.Y("Variabele 2:N", sort=kolommen_analyse),
                text=alt.Text("r:Q", format=".2f"),
                color=alt.condition("abs(datum.r) > 0.5", alt.value("white"), alt.value("black")),
            )
            st.altair_chart((heatmap + tekst).properties(height=340), use_container_width=True)
            st.caption(f"Gebaseerd op {len(df_analyse)} afgeronde teelten.")

            paren = []
            for i, kol_a in enumerate(kolommen_analyse):
                for kol_b in kolommen_analyse[i + 1:]:
                    r = corr.loc[kol_a, kol_b]
                    n = df_analyse[[kol_a, kol_b]].dropna().shape[0]
                    if pd.notna(r) and n >= 5:
                        paren.append((abs(r), r, kol_a, kol_b, n))
            paren.sort(key=lambda p: p[0], reverse=True)

            if paren:
                st.write("**Sterkste samenhangen:**")
                for abs_r, r, kol_a, kol_b, n in paren[:3]:
                    sterkte = "sterk" if abs_r > 0.7 else "matig" if abs_r > 0.4 else "zwak"
                    richting = "ook hoger" if r > 0 else "juist lager"
                    st.write(
                        f"- **{kol_a}** vs **{kol_b}**: naarmate {kol_a.lower()} hoger is, is "
                        f"{kol_b.lower()} {richting} (r = {r:+.2f}, {sterkte} verband, n={n})"
                    )
                    df_paar = df_analyse.dropna(subset=[kol_a, kol_b])
                    scatter = alt.Chart(df_paar).mark_circle(size=60, opacity=0.6).encode(
                        x=alt.X(f"{kol_a}:Q", scale=alt.Scale(zero=False)),
                        y=alt.Y(f"{kol_b}:Q", scale=alt.Scale(zero=False)),
                        tooltip=[kol_a, kol_b],
                    )
                    trend = scatter.transform_regression(kol_a, kol_b).mark_line(color="#c0392b")
                    st.altair_chart((scatter + trend).properties(height=220), use_container_width=True)

                st.caption(
                    f"Let op: gebaseerd op {len(df_analyse)} teelten — met zo'n kleine steekproef kan een "
                    "verband ook toeval zijn. Gebruik dit als richting om op te letten, niet als bewijs, "
                    "en correlatie is geen oorzakelijk verband."
                )
            else:
                st.caption("Geen paren met genoeg overlappende data gevonden.")
    else:
        st.info("Geen data beschikbaar voor statistieken.")

# --- LOGBOEK ---
with tab_log:
    st.subheader("🧾 Logboek")
    st.caption("Wie wat wanneer heeft aangemaakt, gewijzigd of verwijderd — nieuwste bovenaan.")

    limiet_log = st.number_input(
        "Aantal regels tonen", min_value=25, max_value=2000, value=300, step=25, key="log_limiet"
    )
    log_rijen = get_wijzigingenlog(limiet=int(limiet_log))

    if log_rijen:
        df_log = pd.DataFrame(
            log_rijen,
            columns=["Tijdstip", "Gebruiker", "Actie", "Type", "ID", "Omschrijving"]
        )
        df_log["Tijdstip"] = df_log["Tijdstip"].apply(lambda t: t.strftime("%d-%m-%y %H:%M:%S"))
        df_log["Gebruiker"] = df_log["Gebruiker"].fillna("onbekend")

        gebruikers_log = ["Alle gebruikers"] + sorted(df_log["Gebruiker"].unique())
        types_log = ["Alle types"] + sorted(df_log["Type"].unique())
        col_filter1, col_filter2 = st.columns(2)
        gekozen_gebruiker = col_filter1.selectbox("Filter op gebruiker", gebruikers_log, key="log_filter_gebruiker")
        gekozen_type = col_filter2.selectbox("Filter op type", types_log, key="log_filter_type")

        if gekozen_gebruiker != "Alle gebruikers":
            df_log = df_log[df_log["Gebruiker"] == gekozen_gebruiker]
        if gekozen_type != "Alle types":
            df_log = df_log[df_log["Type"] == gekozen_type]

        toon_tabel(df_log, [
            ("Tijdstip", "Tijdstip", "tekst", None, "medium"),
            ("Gebruiker", "Gebruiker", "tekst", None, "small"),
            ("Actie", "Actie", "tekst", None, "small"),
            ("Type", "Type", "tekst", None, "medium"),
            ("ID", "ID", "tekst", None, "small"),
            ("Omschrijving", "Omschrijving", "tekst", None, "large"),
        ])
    else:
        st.info("Nog geen logregels.")

# --- EXTRA INFO ---
with tab_help:
    st.write("""
    **Een teelt starten**
    - Dat gaat via het tabblad 🗓️ Planning: klik bij het concept van dat vak op ✅. De teelt
      krijgt dan een code (jaar + plantweek + vaknummer) en staat daarna als lopend in de app.
    - Het aantal planten staat al klaar per vak, op basis van de vaste basiswaarde bij 60 stelen
      per m² en de plantdichtheid die bij die plantweek hoort. Je kunt het altijd aanpassen.

    **Florgib lengte**
    - Kies één of meer teelten, vul de datum en de lengte in; die geldt dan voor alle gekozen
      teelten.

    **Oogst**
    - Tabblad 🪣 Emmers: per oogstmoment het aantal emmers (100 stelen per emmer). Vink
      "Teelt afronden" aan bij de laatste emmers.
    - Tabblad 📏 Lengte en gewicht: voor teelten die nog niet zijn afgerond.
    - Rijpheid loopt van 1 (rauw) tot 4 (rijp); zet de slider op één punt voor een enkel stadium
      of laat een bereik staan.
    - Emmers van een **afgeronde** teelt corrigeer je bij Wijzigen of verwijderen; daar staat
      dezelfde emmers-editor.

    **Ras**
    - Elke teelt begint als Cameron. Is een vak met een ander ras geplant, kies de teelt dan bij
      Wijzigen of verwijderen en zet het ras om. Nieuwe rassen typ je zelf in bij "Ander ras".

    **Teelt-detail**
    - Kies een plantweek in het tabblad 🔍 Teelt-detail voor kengetallen (teeltduur, klimaat,
      water, warmte, oogstresultaat — steeds met een vergelijking t.o.v. het jaargemiddelde waar
      relevant) en het klimaat (temperatuur, RV, stralingssom, watergift) tijdens de teeltperiode.

    **Planning**
    - Tabblad 🗓️ Planning plant vooruit vanaf waar de huidige teelt van elk vak en de bestaande
      concept-planning gebleven zijn, op basis van de jaarplanning die je zelf invult onder
      "Jaarplanning: vakken per week" (aantal poot-eenheden per week voor de vak 2-39-cyclus, en
      een aparte aanvinkkolom voor vak 1). Een week zonder ingevuld aantal blijft leeg — de app
      vult niets automatisch aan. Klik op "Plan opnieuw met deze aantallen" om te (her)plannen.
    - Vak 19 en 20 worden altijd samen (als één eenheid) gepland; vak 1 loopt op een eigen ritme,
      los van de vak 2-39-cyclus, en telt niet mee in dat wekelijkse aantal.
    - Een concept-planning is nog geen echte teelt: pas nadat je 'm bevestigt (✅) wordt er een
      teeltregistratie met een eigen code aangemaakt. Met 🗑️ verwijder je een concept weer.
    - Elke tuin heeft zijn eigen planning: je ziet en bevestigt alleen de concepten van de tuin
      die bovenaan gekozen is. Automatisch plannen kent voorlopig alleen het ritme van tuin 3;
      op tuin 1 plan je per vak met "Eén vak handmatig plannen".

    **Weeknummers**
    - Elke datum toont het ISO-weeknummer (1-53)
    - Handig voor overzicht en teeltplanning

    **Teeltduur**
    - Dit wordt automatisch berekend als start- en oogstdatum beide ingevuld zijn
    - Toont het aantal dagen van planten tot oogsten

    **Meerdere teelten per vak**
    - Je kunt hetzelfde teeltvak meerdere keren gebruiken (bijv. lente, zomer, herfst)
    - Elke teelt is een apart record met eigen gegevens
    """)

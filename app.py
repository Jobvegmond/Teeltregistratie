import html
import io
import json
import math
import os
import re
import secrets
import urllib.parse

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import streamlit_authenticator as stauth
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, date
from utils.format import (
    LEEG, fmt_getal, fmt_kort, fmt_pct, fmt_weken, fmt_dagen, fmt_verschil,
    getalkolom, zet_altair_nl,
)
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
    wijzig_oogstregistratie,
    verwijder_oogstregistratie,
    markeer_teelt_afgerond,
    get_gebruikers_credentials,
    verwerk_klimaat_csv,
    importeer_klimaat_uit_priva,
    get_klimaat_overzicht_dataframe,
    get_klimaatdata_dagen_voor_periode,
    get_klimaatdata_dekking,
    laatste_priva_ophaling,
    importeer_watergift_uit_priva,
    get_watergift_dekking,
    get_watergift_dagen_voor_periode,
    verwerk_energie_csv,
    get_energiedata_dagen_voor_periode,
    get_energiedata_dekking,
    get_gasdata_dekking,
    get_gasdata_dagen_voor_periode,
    GAS_CALORISCHE_WAARDE_MJ_PER_M3,
    oppervlakte_van_tuin,
    get_vakgegevens,
    ideale_etmaaltemperatuur,
    LICHT_TEMP_FACTOR,
    LICHT_TEMP_BASIS,
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
    get_vakstatus_data,
    get_teelthistorie_data,
    get_vergelijking_data,
    get_teeltvergelijking_data,
    vakstatus_dataversie,
)
from logic import vakstatus as vs
from logic import kengetallen as kg
from logic import perioden
from logic import tuinvergelijking as tuinvgl
from logic import teeltvergelijking as teeltvgl
from logic import teeltprognose as tp
from logic.afdelingen import sorteer_afdelingen
from logic.lichtlijn import formule_tekst, t_ideaal
from ui import styles, vergelijkingstabel
from ui.vergelijkingstabel import Kengetal, verloop_frame
from config import (
    AFDELING_VOLGORDE, AFWIJKING_VENSTER_DAGEN, C_GRENZEN, FLORGIB_ACHTERSTAND_DAGEN, MELDING_C_DREMPEL,
    OP_KOERS_MARGE,
)

# --- PAGINA-INSTELLINGEN ---
# Moet de eerste Streamlit-aanroep zijn. Bepaalt o.a. de titel van het
# browsertabblad.
st.set_page_config(page_title="VEM teeltregistratie", page_icon="🌱", layout="wide")

# Alle Altair-grafieken in Nederlandse getalnotatie (komma, punt voor duizendtallen).
zet_altair_nl()

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


/* Vakkenmatrix ("Nu"): per afdeling een rij (nu_rij_*) met links het label en
   rechts de vakken in een eigen raster (nu_blokken_*). Blokken hebben een
   minimale breedte waarin elke regel past; past een afdeling niet op één
   regel, dan loopt het raster door naar de volgende. Elk vak is een
   st.button; de kleur zit in de knop-key (nu_vak_<kleur>_*). Vaste
   tekstkleur, zodat het ook in donkere modus leesbaar blijft. */
[class*="st-key-nu_rij_"] {
    display: grid !important; grid-template-columns: 3rem minmax(0, 1fr);
    gap: 0.25rem !important; align-items: start; margin-bottom: 0.25rem;
}
[class*="st-key-nu_blokken_"] {
    display: grid !important; grid-template-columns: repeat(auto-fill, minmax(5rem, 1fr));
    gap: 0.25rem !important;
}
[class*="st-key-nu_rij_"] > div, [class*="st-key-nu_blokken_"] > div { width: auto !important; min-width: 0; }
.nu-afd { font-size: 0.72rem; font-weight: 600; opacity: 0.65; padding-top: 0.3rem; }
[class*="st-key-nu_vak_"] button {
    width: 100%; height: 100%; min-height: 3.2rem; padding: 0.15rem 0.3rem;
    justify-content: flex-start; align-items: flex-start; text-align: left;
    border-radius: 0.35rem; line-height: 1.2; color: #1f1f1f;
    border: 1px solid rgba(0, 0, 0, 0.12);
}
[class*="st-key-nu_vak_"] button > div,
[class*="st-key-nu_vak_"] button [data-testid="stMarkdownContainer"] {
    width: 100%; justify-content: flex-start; text-align: left;
}
[class*="st-key-nu_vak_"] button p {
    white-space: pre; font-size: 0.66rem; margin: 0; text-align: left; color: #1f1f1f;
    overflow: hidden;
}
[class*="st-key-nu_vak_"] button strong { font-size: 0.85rem; }
[class*="st-key-nu_vak_"] button:hover { filter: brightness(0.95); border-color: rgba(0, 0, 0, 0.35); }
[class*="st-key-nu_vak_b3_"] button, .nu-legenda .b3 { background: #8fb8e3; }
[class*="st-key-nu_vak_b2_"] button, .nu-legenda .b2 { background: #b5d0ee; }
[class*="st-key-nu_vak_b1_"] button, .nu-legenda .b1 { background: #dae7f6; }
[class*="st-key-nu_vak_n_"] button, .nu-legenda .n { background: #f4f4f1; }
[class*="st-key-nu_vak_o1_"] button, .nu-legenda .o1 { background: #fde4c6; }
[class*="st-key-nu_vak_o2_"] button, .nu-legenda .o2 { background: #f9c793; }
[class*="st-key-nu_vak_r1_"] button, .nu-legenda .r1 { background: #f2a28f; }
[class*="st-key-nu_vak_r2_"] button, .nu-legenda .r2 { background: #e57a68; }
[class*="st-key-nu_vak_rijp_"] button, .nu-legenda .rijp { background: #cfe8c6; }
[class*="st-key-nu_vak_grijs_"] button, .nu-legenda .grijs { background: #e2e2e0; }
[class*="st-key-nu_vak_leeg_"] button, .nu-legenda .leeg {
    background: repeating-linear-gradient(135deg, #ffffff 0 6px, #eeeeec 6px 12px);
}
/* Florgib over tijd: gestippelde rand. */
[class*="st-key-nu_vak_"][class*="_fa_"] button, .nu-legenda .fa { border: 2px dotted #1f1f1f; }
.nu-legenda .fa { background: #ffffff; }
.nu-legenda .nu-schaal { gap: 0; }
.nu-legenda .nu-schaal i { border-radius: 0; width: 1.1rem; }
.nu-legenda .nu-schaal em { font-style: normal; margin: 0 0.3rem; opacity: 0.7; }
.nu-legenda { display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; font-size: 0.72rem; margin: 0.2rem 0 0.6rem; }
.nu-legenda span { display: inline-flex; align-items: center; gap: 0.3rem; }
.nu-legenda i {
    display: inline-block; width: 0.9rem; height: 0.9rem; border-radius: 0.2rem;
    border: 1px solid rgba(0, 0, 0, 0.15);
}
/* Aandachtspunten: tertiaire knoppen als compacte, klikbare regels. */
[class*="st-key-nu_punten_"] button, [class*="st-key-nu_advies_"] button {
    justify-content: flex-start; text-align: left; min-height: 0; padding: 0.05rem 0;
}
[class*="st-key-nu_punten_"] button p, [class*="st-key-nu_advies_"] button p { font-size: 0.85rem; text-align: left; }
[class*="st-key-nu_punten_"], [class*="st-key-nu_punten_"] [data-testid="stVerticalBlock"],
[class*="st-key-nu_advies_"], [class*="st-key-nu_advies_"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
/* Minder witruimte tussen de afdelingsrijen dan tussen gewone elementen. */
[class*="st-key-nu_rij_"] { margin-top: -0.6rem; }
/* Telefoon: afdelingslabel boven de vakken in plaats van ernaast. */
@media (max-width: 700px) {
    [class*="st-key-nu_rij_"] { grid-template-columns: minmax(0, 1fr); margin-top: 0.5rem; }
}

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


def afdeling_kleur(labels, tuin_nummer=None):
    """
    Vaste kleur per afdeling ("Afd. 3" -> AFDELING_KLEUR[3]); de legenda staat
    in de teeltvolgorde van de tuin (config.AFDELING_VOLGORDE), standaard de
    bovenin gekozen tuin.
    """
    nummers = sorteer_afdelingen([int(lbl.split()[-1]) for lbl in labels],
                                 tuin_nummer or globals().get("TUIN_NUMMER"))
    labels = [f"Afd. {n}" for n in nummers]
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

def kopieerknop(inhoud_html, label, hoogte=44):
    """
    Knop die opgemaakte HTML op het klembord zet, zodat je het mét tabel in een
    mail kunt plakken. Een gewone downloadknop of tekstveld levert platte tekst
    op; dit houdt de opmaak heel.

    De moderne clipboard-API werkt niet in elke browser binnen een ingesloten
    kader, dus als die faalt valt hij terug op het ouderwetse selecteren en
    kopiëren — dat werkt overal en behoudt de opmaak net zo goed.
    """
    inhoud = json.dumps(inhoud_html)
    components.html(
        f"""
        <div id="bron" style="position:absolute;left:-9999px;top:0;"></div>
        <button id="knop" style="font:inherit;padding:0.35rem 0.75rem;border-radius:0.5rem;
                border:1px solid rgba(49,51,63,0.2);background:#fff;cursor:pointer;">{label}</button>
        <script>
        const inhoud = {inhoud};
        const bron = document.getElementById("bron");
        const knop = document.getElementById("knop");
        bron.innerHTML = inhoud;
        function gelukt() {{
            const oud = knop.textContent;
            knop.textContent = "✅ Gekopieerd";
            setTimeout(() => knop.textContent = oud, 2000);
        }}
        function ouderwets() {{
            const bereik = document.createRange();
            bereik.selectNodeContents(bron);
            const selectie = window.getSelection();
            selectie.removeAllRanges();
            selectie.addRange(bereik);
            document.execCommand("copy");
            selectie.removeAllRanges();
            gelukt();
        }}
        knop.onclick = () => {{
            if (navigator.clipboard && window.ClipboardItem) {{
                navigator.clipboard.write([new ClipboardItem({{
                    "text/html": new Blob([inhoud], {{type: "text/html"}}),
                    "text/plain": new Blob([bron.innerText], {{type: "text/plain"}}),
                }})]).then(gelukt).catch(ouderwets);
            }} else {{
                ouderwets();
            }}
        }};
        </script>
        """,
        height=hoogte,
    )


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
        # Aantal decimalen uit het printf-formaat ("%d" = 0, "%.1f" = 1);
        # getoond wordt in Nederlandse notatie (utils.format).
        decimalen_match = re.match(r"%\.(\d+)f", formaat or "")
        decimalen = int(decimalen_match.group(1)) if decimalen_match else 0
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
                        tekst = gelezen.map(lambda v: "" if pd.isna(v) else fmt_getal(v, decimalen))
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
            config[kolom] = getalkolom(label, decimalen, width=breedte)
        elif soort == "datum":
            config[kolom] = st.column_config.DateColumn(label, format="DD-MM-YY", width=breedte)
        else:
            config[kolom] = st.column_config.TextColumn(label, width=breedte)
        volgorde.append(kolom)
    if pin_eerste and volgorde:
        config[volgorde[0]]["pinned"] = True
    st.dataframe(df[volgorde], hide_index=True, column_config=config)


def toon_strokenplanning(stroken, vaknummers, hoogte=640, legenda=True):
    """
    Tekent de strokenplanning (Gantt) van `stroken` (uit get_strokenplanning):
    per vak een balk van start tot (verwachte) oogst, grijs voor afgerond,
    groen voor lopend, blauw voor concept. Rode stippellijn = vandaag; een
    rode stippelrand om (een deel van) een balk = die dagen overlappen met de
    vorige ronde in dat vak. Gedeeld door de Planning-tab en het gecombineerde
    overzicht, met een eigen hoogte en al dan niet een legenda.
    """
    if not stroken:
        st.caption("Geen teelten of concepten in deze periode.")
        return
    df_stroken = pd.DataFrame(stroken)
    df_stroken["start"] = pd.to_datetime(df_stroken["start"])
    df_stroken["eind"] = pd.to_datetime(df_stroken["eind"])
    _dagen_nl = ["ma", "di", "wo", "do", "vr", "za", "zo"]

    def _week_dag(ts):
        return f"wk {ts.isocalendar().week} {_dagen_nl[ts.weekday()]}"

    df_stroken["start_tekst"] = df_stroken["start"].apply(_week_dag)
    df_stroken["eind_tekst"] = df_stroken["eind"].apply(_week_dag)
    df_stroken["duur_tekst"] = df_stroken["teeltduur_weken"].apply(fmt_weken)

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
        legend=alt.Legend(title=None, orient="top") if legenda else None,
    )
    vak_y = alt.Y(
        "vaknummer:O", title="Vak", sort="ascending",
        scale=alt.Scale(domain=vaknummers or list(range(1, 40))),
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
        alt.layer(*lagen).properties(height=hoogte).configure_view(strokeOpacity=0),
        use_container_width=True,
    )


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
        if item.get("waarde") in (None, "-", ""):
            item = {**item, "waarde": LEEG}
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


# --- STATISTIEKEN: seizoensgecorrigeerde verbanden ---

# Minimaal aantal teelten met beide waarden voordat een verband iets zegt.
ANALYSE_MIN_N = 20
# Minimaal aantal buren (eigen tuin, plantweek ±2) voor een eigen normaal;
# anders telt de andere tuin mee.
SEIZOEN_MIN_BUREN = 5

# Groeifactoren eerst, dan het resultaat: in een verband is de eerste de
# "oorzaak"-kant van de zin. Per kolom: (eenheid, eenheid bij 1, stap in de
# zin, werkwoord, (woord bij hoger, woord bij lager), decimalen).
ANALYSE_VARIABELEN = {
    # Licht eerst: dat stuurt de kastemperatuur, niet andersom.
    "Lichtsom (per dag)": ("J/cm² per dag", "J/cm² per dag", 100, "kregen", ("meer licht", "minder licht"), 0),
    "Temperatuur (°C)": ("°C", "°C", 1, "waren", ("warmer", "kouder"), 1),
    "Water (l/m²)": ("l/m²", "l/m²", 10, "kregen", ("meer water", "minder water"), 0),
    "Teeltduur (dagen)": ("dagen", "dag", 1, "duurden", ("langer", "korter"), 1),
    "Lengte (cm)": ("cm", "cm", 1, "waren", ("langer", "korter"), 1),
    "Gewicht (g)": ("g", "g", 10, "waren", ("zwaarder", "lichter"), 0),
    "Rijpheid": ("punt", "punt", 1, "waren", ("rijper", "minder rijp"), 1),
}


def seizoensafwijking(df, kolommen, venster=2, min_buren=SEIZOEN_MIN_BUREN):
    """
    Zet per teelt elke waarde om in de afwijking van het seizoensnormaal: de
    waarde min het gemiddelde van de andere teelten met een plantweek binnen
    ±`venster` weken (over alle jaren, over de jaargrens heen). Normaal uit de
    eigen tuin (kolom tuin_id) als daar minstens `min_buren` teelten met een
    waarde zijn, anders uit beide tuinen samen; met minder dan 3 buren blijft
    de afwijking leeg. De teelt zelf telt niet mee in zijn eigen normaal.
    """
    uit = df.copy()
    weken = df["plantweek"].to_numpy(dtype=float)
    tuinen = df["tuin_id"].to_numpy()
    afstand = np.abs(weken[:, None] - weken[None, :])
    in_venster = np.minimum(afstand, 52 - afstand) <= venster
    np.fill_diagonal(in_venster, False)
    zelfde_tuin = tuinen[:, None] == tuinen[None, :]
    for kolom in kolommen:
        waarden = df[kolom].to_numpy(dtype=float)
        heeft = ~np.isnan(waarden)
        buren = in_venster & heeft[None, :]
        eigen = buren & zelfde_tuin
        kies = np.where((eigen.sum(axis=1) >= min_buren)[:, None], eigen, buren)
        aantal = kies.sum(axis=1)
        som = np.where(kies, np.nan_to_num(waarden)[None, :], 0.0).sum(axis=1)
        normaal = np.divide(som, aantal, out=np.full(len(df), np.nan), where=aantal >= 3)
        uit[kolom] = np.where(heeft, waarden - normaal, np.nan)
    return uit


def verband_zin(kol_a, kol_b, helling, r, n, seizoen):
    """
    Het verband in gewone woorden, bijv. "Teelten die 1 °C warmer waren dan
    normaal voor hun plantweek, duurden gemiddeld 2,6 dagen korter dan normaal
    (r = −0,62, n = 150)." `helling` is de verandering in kol_b per eenheid
    kol_a (regressielijn).
    """
    eenheid_a, eenheid_a1, stap, werkwoord_a, (hoger_a, _), _ = ANALYSE_VARIABELEN[kol_a]
    eenheid_b, eenheid_b1, _, werkwoord_b, (hoger_b, lager_b), decimalen_b = ANALYSE_VARIABELEN[kol_b]
    effect = helling * stap
    hoeveel = fmt_getal(abs(effect), decimalen_b)
    oorzaak = f"{fmt_kort(stap)} {eenheid_a1 if stap == 1 else eenheid_a} {hoger_a}"
    gevolg = f"{hoeveel} {eenheid_b1 if hoeveel == '1' else eenheid_b} {hoger_b if effect > 0 else lager_b}"
    maat = f"(r = {fmt_verschil(r, 2)}, n = {n})"
    if seizoen:
        return (f"Teelten die {oorzaak} {werkwoord_a} dan normaal voor hun plantweek, "
                f"{werkwoord_b} gemiddeld {gevolg} dan normaal {maat}.")
    return (f"Teelten die {oorzaak} {werkwoord_a} dan andere teelten, "
            f"{werkwoord_b} gemiddeld {gevolg} {maat}.")


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
                     alt.Tooltip("lichtsom:Q", title="lichtsom", format=",.0f")],
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
        f"Rode stippellijn = ideale temperatuur bij dat licht ({fmt_kort(LICHT_TEMP_FACTOR, 4)} x lichtsom + "
        f"{fmt_kort(LICHT_TEMP_BASIS, 1)} °C) — temperatuurlijn erboven is relatief te warm, eronder te koud."
        + (" Dikke effen lijn = 14-daags voortschrijdend gemiddelde." if toon_trend else "")
        + (" Per afdeling: donker = 24h, licht = dag, gestippeld = nacht." if toon_dagnacht else "")
    )
    toon_grafiek(
        alt.layer(*temp_lagen).resolve_scale(y="independent") if temp_lagen else None,
        temp_lang, "Geen temperatuurdata in deze periode.", waardekolom="waarde",
    )

    st.caption("Relatieve luchtvochtigheid (%)")
    lijngrafiek_per_afdeling(
        _lang("rv"), "RV (%)", toon_dagnacht=toon_dagnacht, formaat=",.0f",
        melding="Geen luchtvochtigheidsdata in deze periode.",
    )


def watergift_grafiek(records, melding="Nog geen watergift gekoppeld."):
    """
    Watergift per dag als staven, per vak naast elkaar (niet opgeteld).
    `records`: dicts met datum, Vak ("Vak 12") en liter (l/m²). Gebruikt in
    de teeltweergave (teelt_detail: Nu en Teeltvergelijking).
    """
    # Priva schrijft ook dagen zonder gift weg (0,0); die zijn geen gift en
    # rekten de as op tot vandaag, alsof er nog water gegeven werd.
    df_water = pd.DataFrame(records).dropna(subset=["liter"]) if records else None
    if df_water is not None:
        df_water = df_water[df_water["liter"] > 0]
    if df_water is None or df_water.empty:
        st.info(melding)
        return
    df_water["datum"] = pd.to_datetime(df_water["datum"])
    df_water = df_water.sort_values("datum")
    df_water["dag"] = df_water["datum"].dt.strftime(DATUM_FORMAAT_AS)
    st.caption("Watergift per vak (l/m² per dag, alleen dagen met een gift) — vakken naast elkaar, "
               f"niet opgeteld. Laatste gift {df_water['datum'].max():%d-%m-%y}.")
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
        strokeDash=alt.StrokeDash(
            "Type:N", legend=alt.Legend(title=None, orient="bottom"),
            scale=alt.Scale(domain=["Werkelijk", "Ideaal (obv licht)"], range=[[1, 0], [6, 3]]),
        ),
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Afdeling:N", "Type:N",
                 alt.Tooltip("waarde:Q", title="°C", format=".1f")],
    )
    st.caption(
        f"Ideaal = {fmt_kort(LICHT_TEMP_FACTOR, 4)} x lichtsom + {fmt_kort(LICHT_TEMP_BASIS, 1)} °C van diezelfde dag. "
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
_tuinnummer_van = {t["id"]: t["nummer"] for t in TUINEN}
_tuinnaam_van = {t["id"]: t["naam"] for t in TUINEN}
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
    samenvatting = f"{fmt_kort(totaal_emmers)} emmers"
    if teelt_info.get("aantal_planten"):
        uitval_pct = (
            (teelt_info["aantal_planten"] - totaal_emmers * 100) / teelt_info["aantal_planten"] * 100
        )
        samenvatting += f" · {fmt_pct(uitval_pct)} uitval"
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
                florgib_gram = st.number_input("Florgib (g) per vak", min_value=0.0, step=0.5, format="%.1f")
            
                submit_half = st.form_submit_button("Opslaan")
            
                if submit_half and geselecteerde_labels:
                    successen = []
                    fouten = []
                
                    for label in geselecteerde_labels:
                        geselecteerd_id = keuzes[label]
                        try:
                            update_halverwege(geselecteerd_id, datum_half, lengte_half,
                                              gebruiker=huidige_gebruiker(),
                                              florgib_gram=florgib_gram or None)
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
                nieuw_florgib_gram = st.number_input(
                    "Florgib (g) per vak",
                    min_value=0.0, step=0.5, format="%.1f",
                    value=float(huidige["florgib_gram"]) if huidige["florgib_gram"] else 0.0,
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
                            florgib_gram=(nieuw_florgib_gram or None) if half_ingevuld else None,
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
styles.laad()
tab_nu, tab_tuinvgl, tab_teeltvgl, tab_overzicht, tab_planning, tab_stek, tab_klimaat, tab_stats, tab_meer = st.tabs([
    "🧭 Nu", "⚖️ Tuinvergelijking", "🌿 Teeltvergelijking", "📊 Teeltoverzicht", "🗓️ Planning", "🌱 Stek",
    "🌡️ Klimaatdata", "📈 Statistieken", "ℹ️ Meer",
])
# Weinig gebruikt: logboek en uitleg als subtabbladen onder "Meer".
with tab_meer:
    tab_log, tab_help = st.tabs(["🧾 Logboek", "ℹ️ Hoe dit werkt"])

# --- NU: hoe staat elk vak ervoor ---
#
# Eén raster per tuin met per vak een klikbaar blok (kleur = status), met de
# aandachtspunten erboven. Het rekenwerk staat in logic/vakstatus.py; hier
# alleen ophalen (één keer, gecachet) en tekenen.

# Kleur van een vakblok = de prognose t.o.v. plan in dagen bij de huidige
# stooklijn (logic/teeltprognose.dagen_klasse), schaal −7 … +7: blauw = te
# vroeg, neutraal = op schema, oranje → rood = te laat. De kleuren staan in de
# CSS (.st-key-nu_vak_<klasse>_*) en in de legenda.
NU_KLASSEN = ("b3", "b2", "b1", "n", "o1", "o2", "r1", "r2")
NU_STATUS_KORT = {"b3": "ruim te vroeg", "b2": "te vroeg", "b1": "iets te vroeg", "n": "op schema",
                  "o1": "iets te laat", "o2": "te laat", "r1": "ruim te laat", "r2": "ruim te laat", "rijp": "oogstrijp",
                  "grijs": "geen prognose", "leeg": "leeg"}
NU_PUNT_ICOON = {1: "🌡️", 2: "🧪", 3: "✂️", 4: "💧", 5: "⚠️", 6: "🌱"}
_NU_PER_RUN = {}   # één keer rekenen per scriptrun (Nu, Teeltvergelijking en Planning gebruiken het)


@st.cache_data(ttl=600, show_spinner="Vakken ophalen…")
def _nu_data(versie, dag):
    """Alle data voor "Nu". `versie` (wijzigingenlog) en `dag` zijn alleen cachesleutels."""
    return get_vakstatus_data()


@st.cache_data(ttl=3600, show_spinner="Teeltmodel bijwerken…")
def _nu_model(versie, dag):
    """
    Het teeltmodel, gefit op teelt_historie plus de in de app afgeronde
    teelten die daar nog niet in staan. Leert zo mee met elke nieuwe oogst.
    None als er (nog) geen historie is.
    """
    data = _nu_data(versie, dag)
    historie, weken = get_teelthistorie_data()
    klimaat = tp.klimaat_per_afdeling(data["klimaat"])
    leerset = tp.bouw_leerset(historie, weken, data["teelten"], klimaat,
                              lambda start: bereken_verwachte_oogstdatum(start)[1])
    if len(leerset) < 20:
        return None
    return tp.TeeltPrognose().fit(leerset, tp.weeklicht(weken, data["klimaat"]))


def _nu_alles(vandaag):
    """
    (data, model, stook, afwijking) voor deze run:
    - stook: {teelt_id: TeeltPrognose.beoordeel-uitkomst} voor alle lopende teelten
    - afwijking: {(tuin_id, afdeling): gemiddelde afwijking van de lichtlijn, laatste 14 dagen}
    """
    if "alles" not in _NU_PER_RUN:
        versie = vakstatus_dataversie()
        data, model = _nu_data(versie, str(vandaag)), _nu_model(versie, str(vandaag))
        klimaat = tp.klimaat_per_afdeling(data["klimaat"])
        afwijking = {k: tp.afwijking_afdeling(d, vandaag) for k, d in klimaat.items()}
        stook = {}
        for t in data["teelten"].itertuples() if model else []:
            start = vs.als_datum(t.datum_teelt_start)
            if vs.als_datum(t.datum_oogst) or start > vandaag or vs._getal(t.afdeling) is None:
                continue
            sleutel = (int(t.tuin_id), int(t.afdeling))
            reeks = tp.dagreeks(start, (vandaag - start).days, klimaat.get(sleutel, {}))
            if reeks is None:
                continue
            half = vs.als_datum(t.datum_half)
            stook[int(t.id)] = model.beoordeel(
                int(t.tuin_id), start, vandaag, bereken_verwachte_oogstdatum(start)[1], *reeks,
                afwijking.get(sleutel), half if half and half > start else None)
        _NU_PER_RUN["alles"] = (data, model, stook, afwijking)
    return _NU_PER_RUN["alles"]


def _nu_uitval(t):
    """Uitval van een teelt in %: uit de emmers, anders het vastgelegde percentage."""
    planten, emmers = vs._getal(t.get("aantal_planten")), vs._getal(t.get("emmers"))
    if planten and emmers:
        return (planten - emmers * 100) / planten * 100
    return vs._getal(t.get("uitval_pct"))


def _nu_tuin(data, model, stook, afwijking, tuin, vandaag):
    """Status en prognose van alle vakken van één tuin, het stookadvies per afdeling en de aandachtspunten."""
    alle = data["teelten"].to_dict("records")
    eigen = [t for t in alle if t["tuin_id"] == tuin["id"]]
    vakken = data["vakken"][data["vakken"]["tuin_id"] == tuin["id"]]

    lopend = {}
    for t in eigen:
        start = vs.als_datum(t["datum_teelt_start"])
        if not vs.als_datum(t["datum_oogst"]) and start <= vandaag:
            if t["vaknummer"] not in lopend or start > vs.als_datum(lopend[t["vaknummer"]]["datum_teelt_start"]):
                lopend[t["vaknummer"]] = t
    statussen = {vak: vs.beoordeel_teelt(t, alle, vandaag, bereken_verwachte_oogstdatum) for vak, t in lopend.items()}

    # De prognose en de status volgen het teeltmodel; de lengtevergelijking
    # (meting, verwacht, afwijking_pct) blijft alleen in het venster.
    for s in statussen.values():
        u = s["stook"] = stook.get(int(s["teelt"]["id"]))
        s["prognose"] = u["prognose"] if u else None
        s["prognose_dagen"] = (u["prognose"] - s["plan"]).days if u and u["prognose"] and s["plan"] else None
        s["klasse"] = "grijs" if not u else ("rijp" if u["oogstrijp"] else tp.dagen_klasse(s["prognose_dagen"]))
        s["florgib_achter"] = bool(u and s["florgib"] is None and u["florgib_verwacht"]
                                   and (vandaag - u["florgib_verwacht"]).days > FLORGIB_ACHTERSTAND_DAGEN)

    # Stookadvies per afdeling: c gewogen naar het aantal stelen. Zonder
    # vastgelegd plantaantal telt een vak als de mediaan van de afdeling.
    advies = {}
    for afdeling in sorteer_afdelingen({s["teelt"]["afdeling"] for s in statussen.values()}, tuin["nummer"]):
        groep = [s for s in statussen.values() if s["teelt"]["afdeling"] == afdeling and s["stook"]
                 and s["stook"]["c"] is not None]
        bekend = [vs._getal(s["teelt"]["aantal_planten"]) for s in groep if vs._getal(s["teelt"]["aantal_planten"])]
        standaard = float(np.median(bekend)) if bekend else 1.0
        rijen = [{"vak": s["teelt"]["vaknummer"], "c": s["stook"]["c"], "s": s,
                  "stelen": vs._getal(s["teelt"]["aantal_planten"]) or standaard} for s in groep]
        c, doorslag = tp.afdelingsadvies(rijen)
        advies[int(afdeling)] = {"c": c, "doorslag": doorslag, "vakken": rijen,
                                 "nu": afwijking.get((tuin["id"], int(afdeling)))}

    # Volgende planting per vak: een teelt met een startdatum in de toekomst of een concept.
    gepland = {}
    for t in eigen:
        start = vs.als_datum(t["datum_teelt_start"])
        if start > vandaag:
            gepland[t["vaknummer"]] = min(start, gepland.get(t["vaknummer"], start))
    for c in data["concepten"][data["concepten"]["tuin_id"] == tuin["id"]].itertuples():
        start = vs.als_datum(c.verwachte_startdatum)
        gepland[c.vaknummer] = min(start, gepland.get(c.vaknummer, start))
    laatste_oogst = {}
    for t in eigen:
        oogst = vs.als_datum(t["datum_oogst"])
        if oogst:
            laatste_oogst[t["vaknummer"]] = max(oogst, laatste_oogst.get(t["vaknummer"], oogst))

    water = data["water"][data["water"]["tuin_id"] == tuin["id"]]
    water_horizon = vs.als_datum(water["datum"].max()) if not water.empty else None
    met_gift = water[water["liter_per_m2"] > 0]
    water_laatste = {int(v): vs.als_datum(d) for v, d in met_gift.groupby("vaknummer")["datum"].max().items()}

    punten = vs.aandachtspunten(list(statussen.values()), water_laatste, water_horizon, vandaag)
    return {"tuin": tuin, "vakken": vakken, "statussen": statussen, "gepland": gepland, "advies": advies,
            "laatste_oogst": laatste_oogst, "punten": punten, "alle": alle, "model": model}


def _nu_c_tekst(u, kort=False):
    """"+0,8 °C", "≥ +3 °C" (begrensd), "op koers", "oogstrijp" of "geen prognose"."""
    if not u:
        return "geen prognose"
    if u["oogstrijp"]:
        return "oogstrijp"
    if u["c"] is None:
        return "geen plan"
    if tp.op_koers(u["c"]):
        return "op koers"
    if u["begrensd"]:
        return f"{'≥' if u['c'] > 0 else '≤'} {fmt_verschil(u['c'], 0, '°C')}"
    return fmt_verschil(u["c"], 1, "°C")


def _nu_florgib_tekst(s):
    """"Fg 13-09" (geregistreerd) of "Fg verw. 28-10" (volgens het model)."""
    u = s["stook"]
    if s["florgib"]:
        return f"Fg {s['florgib']:%d-%m}"
    if u and u["florgib_verwacht"]:
        return f"Fg verw. {u['florgib_verwacht']:%d-%m}"
    return "vóór Fg"


def _nu_bloklabel(vak, s, gepland):
    """
    Knoptekst van een vak, 4 korte regels die in het smalle blok passen:
    vak + plantweek + leeftijd · Florgib · correctie + gewichtseffect · plan
    met de prognose als verschil in dagen. Volledige datums staan in de tooltip.
    """
    if s is None:
        regels = [f"**{vak}** leeg"]
        if gepland:
            regels.append(f"plant {gepland:%d-%m}")
        return "\n".join(regels)
    u = s["stook"]
    correctie = _nu_c_tekst(u)
    if u and u["c"] is not None and not tp.op_koers(u["c"]) and u["gewicht"] is not None:
        correctie += f" · {fmt_verschil(u['gewicht'], 0, 'g')}"
    plan = f"plan {s['plan']:%d-%m}" if s["plan"] else "plan ?"
    if s["prognose_dagen"]:
        plan += f" {fmt_verschil(s['prognose_dagen'], 0)} d"
    return "\n".join([f"**{vak}** wk {s['plantweek']} · {s['leeftijd']} d", _nu_florgib_tekst(s), correctie, plan])


def _nu_bloktip(vak, s, gepland, laatste_oogst, info):
    """Tooltip bij een vak: de getallen achter de kleur."""
    if s is None:
        tekst = f"Vak {vak}: leeg"
        if laatste_oogst:
            tekst += f" sinds {format_datum(laatste_oogst)}"
        return tekst + (f". Volgende planting {format_datum(gepland)}." if gepland else ".")
    t, u = s["teelt"], s["stook"]
    delen = [f"Vak {vak} · {t['code'] or '-'} · geplant {format_datum(s['start'])}"]
    if not u:
        delen.append("geen prognose: te weinig klimaatdata van de afdeling sinds planten")
        return " · ".join(delen)
    delen.append(f"{fmt_getal(u['gedaan'] * 100)} % van de teelt opgebouwd")
    if u["afwijking_nu"] is not None:
        delen.append(f"afdeling de laatste {AFWIJKING_VENSTER_DAGEN} dagen {fmt_verschil(u['afwijking_nu'], 1, '°C')} "
                     "t.o.v. de lichtlijn")
    if s["prognose"]:
        delen.append(f"zo aanhouden: oogst {format_datum(s['prognose'])}")
    if u["c"] is not None:
        delen.append(f"voor plan {format_datum(s['plan'])}: {_nu_c_tekst(u)} t.o.v. de lichtlijn")
    if s["florgib_achter"]:
        delen.append(f"Florgib verwacht {format_datum(u['florgib_verwacht'])}, nog niet geregistreerd")
    return " · ".join(delen)


def _nu_tijdlijn(s):
    """Planten → Florgib → plan en prognose (of de oogst) op één datumas, met vandaag als stippellijn."""
    u, oogst = s.get("stook"), vs.als_datum(s["teelt"].get("datum_oogst"))
    punten = [("Geplant", s["start"], "gedaan")]
    if s["florgib"]:
        punten.append(("Florgib", s["florgib"], "gedaan"))
    elif u and u["florgib_verwacht"]:
        punten.append(("Florgib (verw.)", u["florgib_verwacht"], "verwacht"))
    if s["plan"]:
        punten.append(("Plan", s["plan"], "plan"))
    if oogst:
        punten.append(("Geoogst", oogst, "gedaan"))
    elif s["prognose"]:
        punten.append(("Prognose", s["prognose"], "verwacht"))
    df = pd.DataFrame([{"Moment": m, "datum": pd.Timestamp(d), "Soort": soort,
                        "label": f"{m} {d:%d-%m}", "rij": i % 2} for i, (m, d, soort) in enumerate(punten)])
    as_x = alt.X("datum:T", title=None, axis=alt.Axis(format="%d-%m", grid=False))
    basis = alt.Chart(df)
    lijn = basis.mark_rule(color="#999").encode(x=alt.X("min(datum):T"), x2="max(datum):T")
    stippen = basis.mark_point(size=110, filled=True).encode(
        x=as_x,
        color=alt.Color("Soort:N", legend=None,
                        scale=alt.Scale(domain=["gedaan", "plan", "verwacht"], range=["#2e7d32", "#555", "#e67e22"])),
        shape=alt.Shape("Soort:N", legend=None,
                        scale=alt.Scale(domain=["gedaan", "plan", "verwacht"], range=["circle", "diamond", "circle"])),
        tooltip=[alt.Tooltip("Moment:N"), alt.Tooltip("datum:T", format="%d-%m-%y")],
    )
    tekst = basis.mark_text(dy=-14, fontSize=11).encode(x=as_x, text="label:N")
    lagen = [lijn, stippen, tekst]
    if not oogst:
        lagen.append(alt.Chart(pd.DataFrame({"datum": [pd.Timestamp(date.today())]})).mark_rule(
            color="#888", strokeDash=[4, 3]).encode(x="datum:T"))
    st.altair_chart(alt.layer(*lagen).properties(height=70), use_container_width=True)


def _nu_klimaat_doel(s, klimaat):
    """
    Etmaaltemperatuur sinds planten tegen de lichtlijn, en vanaf vandaag tot de
    plandatum de doellijn (lichtlijn + c) bij de verwachte lichtsom. Met de
    Florgib (geregistreerd of verwacht) als verticale lijn. Bij een afgeronde
    teelt alleen werkelijk tegen de lichtlijn.
    """
    u, afgerond = s.get("stook"), bool(s["teelt"].get("datum_oogst"))
    rijen = []
    for r in klimaat.dropna(subset=["temp_24h", "lichtsom"]).itertuples():
        rijen += [{"datum": r.datum, "Reeks": "Werkelijk", "waarde": r.temp_24h},
                  {"datum": r.datum, "Reeks": "Lichtlijn", "waarde": t_ideaal(r.lichtsom)}]
    if u and u["c"] is not None and s["plan"]:
        vandaag = date.today()
        for i in range(max((s["plan"] - vandaag).days, 0) + 1):
            dag, licht = vandaag + timedelta(days=i), u["L_verw"][min(i, len(u["L_verw"]) - 1)]
            rijen += [{"datum": str(dag), "Reeks": "Lichtlijn", "waarde": t_ideaal(licht)},
                      {"datum": str(dag), "Reeks": "Doel (lichtlijn + c)", "waarde": t_ideaal(licht) + u["c"]}]
    if not rijen:
        st.caption("Geen klimaatdata sinds planten.")
        return
    df = pd.DataFrame(rijen)
    stijl = {"Werkelijk": ("#c0392b", [1, 0]), "Lichtlijn": ("#777", [6, 3]), "Doel (lichtlijn + c)": ("#e67e22", [2, 2])}
    reeksen = [r for r in stijl if r in set(df["Reeks"])]
    lijnen = alt.Chart(df).mark_line().encode(
        x=datum_as(),
        y=y_as("waarde", "Etmaaltemperatuur (°C)", domein=gedeeld_domein(df["waarde"])),
        color=alt.Color("Reeks:N", title=None, legend=alt.Legend(orient="bottom"),
                        scale=alt.Scale(domain=reeksen, range=[stijl[r][0] for r in reeksen])),
        strokeDash=alt.StrokeDash("Reeks:N", legend=None,
                                  scale=alt.Scale(domain=reeksen, range=[stijl[r][1] for r in reeksen])),
        tooltip=[alt.Tooltip("datum:T", title="Datum", format="%d-%m-%y"), alt.Tooltip("Reeks:N"),
                 alt.Tooltip("waarde:Q", title="°C", format=".1f")],
    )
    lagen = [lijnen]
    if not afgerond:
        lagen.append(alt.Chart(pd.DataFrame({"datum": [str(date.today())]})).mark_rule(
            color="#888", strokeDash=[4, 3]).encode(x="datum:T"))
    florgib = s["florgib"] or (u and u["florgib_verwacht"])
    if florgib:
        fg = pd.DataFrame({"datum": [str(florgib)], "tekst": ["Florgib" + ("" if s["florgib"] else " (verw.)")]})
        lagen += [alt.Chart(fg).mark_rule(color="#2e7d32").encode(x="datum:T"),
                  alt.Chart(fg).mark_text(align="left", dx=3, dy=-4, color="#2e7d32", fontSize=11).encode(
                      x="datum:T", y=alt.value(8), text="tekst:N")]
    st.altair_chart(alt.layer(*lagen).properties(height=240), use_container_width=True)
    st.caption(f"Lichtlijn = {formule_tekst()}."
               + (f" Doel = lichtlijn + de benodigde correctie ({_nu_c_tekst(u)}) bij de gemiddelde lichtsom van "
                  "die kalenderweek, tot de plandatum." if u and u["c"] is not None else ""))


def teelt_detail(s, klimaat, water, model=None):
    """
    De hele teelt van één vak: tijdlijn, voortgang (lopend), klimaat tegen de
    lichtlijn, lichtsom, watergift per dag, groei en stek. Voor lopende teelten
    (s["stook"] uit het Nu-model) en afgeronde (s["teelt"]["datum_oogst"]).
    - s: een vakstatus-dict (logic.vakstatus.beoordeel_teelt) met "stook" (of None)
    - klimaat: DataFrame met datum, temp_24h, lichtsom van de afdeling sinds planten
    - water: [{datum, liter}] van het vak sinds planten
    """
    t, u = s["teelt"], s.get("stook")
    vak = t["vaknummer"]
    _nu_tijdlijn(s)
    if u:
        nodig = 1.0
        st.progress(min(u["gedaan"] / nodig, 1.0),
                    text=f"Opgebouwd {fmt_getal(u['gedaan'] * 100)} % van wat een teelt nodig heeft"
                         + (f" · Florgib bij ± {fmt_getal(model.florgib_fractie * 100)} %"
                            if model and model.florgib_fractie else ""))

    st.write(f"**Klimaat afdeling {fmt_kort(t['afdeling'])} tijdens de teelt**")
    _nu_klimaat_doel(s, klimaat)
    lijngrafiek_per_afdeling(
        pd.DataFrame({"datum": klimaat["datum"], "Afdeling": f"Afd. {fmt_kort(t['afdeling'])}",
                      "Deel": "24h", "waarde": klimaat["lichtsom"]}),
        "Lichtsom per dag (J/cm²)", toon_dagnacht=False, formaat=",.0f",
        melding="Geen lichtsom sinds planten.",
    )

    st.write("**Watergift**")
    if s["florgib"]:
        st.caption(f"Na de Florgib ({format_datum(s['florgib'])}) wordt er geen water meer gegeven.")
    watergift_grafiek([{"datum": r["datum"], "Vak": f"Vak {vak}", "liter": r["liter"]} for r in water],
                      "Geen watergift in deze teelt.")

    st.write("**Groei**")
    if s["refs"]:
        einde = max(s["leeftijd"], (s["plan"] - s["start"]).days if s["plan"] else 0,
                    max(vs.referentiepunten(r)[-1][0] for r in s["refs"]))
        curve = pd.DataFrame(vs.groeicurve(s["refs"], einde), columns=["dag", "P25", "Verwacht", "P75"])
        band = alt.Chart(curve).mark_area(opacity=0.25, color="#4c78a8").encode(
            x=alt.X("dag:Q", title="Leeftijd (dagen)"), y=alt.Y("P25:Q", title="Lengte (cm)"), y2="P75:Q",
        )
        lijn = alt.Chart(curve).mark_line(color="#4c78a8").encode(
            x="dag:Q", y="Verwacht:Q",
            tooltip=[alt.Tooltip("dag:Q", title="dag"), alt.Tooltip("Verwacht:Q", format=".1f"),
                     alt.Tooltip("P25:Q", format=".1f"), alt.Tooltip("P75:Q", format=".1f")],
        )
        lagen = [band, lijn, alt.Chart(pd.DataFrame({"dag": [s["leeftijd"]]})).mark_rule(
            color="#888", strokeDash=[4, 3]).encode(x="dag:Q")]
        florgib_dag = ((s["florgib"] - s["start"]).days if s["florgib"]
                       else (u["florgib_verwacht"] - s["start"]).days if u and u["florgib_verwacht"] else None)
        if florgib_dag is not None:
            fg = pd.DataFrame({"dag": [florgib_dag], "tekst": ["Florgib" + ("" if s["florgib"] else " (verw.)")]})
            lagen += [alt.Chart(fg).mark_rule(color="#2e7d32").encode(x="dag:Q"),
                      alt.Chart(fg).mark_text(align="left", dx=3, color="#2e7d32", fontSize=11).encode(
                          x="dag:Q", y=alt.value(8), text="tekst:N")]
        if s["meting"] is not None:
            lagen.append(alt.Chart(pd.DataFrame(
                {"dag": [0, s["meet_leeftijd"]], "Gemeten": [0, s["meting"]]}
            )).mark_line(point=alt.OverlayMarkDef(size=70, filled=True, color="#c0392b"),
                         color="#c0392b").encode(
                x="dag:Q", y="Gemeten:Q", tooltip=[alt.Tooltip("Gemeten:Q", format=".1f")]))
        st.altair_chart(alt.layer(*lagen).properties(height=220), use_container_width=True)
        meting = ""
        if s["meting"] is not None and s["verwacht"] is not None:
            meting = (f" Gemeten {fmt_getal(s['meting'], 1)} cm op dag {s['meet_leeftijd']}, verwacht "
                      f"{fmt_getal(s['verwacht'], 1)} cm ({fmt_verschil(s['afwijking_pct'], 0, '%')}).")
        st.caption(
            f"Lijn = mediaan, band = P25–P75 van {len(s['refs'])} referentieteelten "
            f"({vs.REFERENTIE_NIVEAUS[s['niveau']]}); rood = gemeten, groen = Florgib, "
            f"stippellijn = {'oogst' if t.get('datum_oogst') else 'vandaag'}.{meting}"
        )
    else:
        st.caption("Te weinig afgeronde teelten met een halverwege- én oogstmeting rond deze plantweek "
                   f"(minder dan {vs.MIN_REFERENTIES}).")

    st.write("**Stek**")
    if vs._getal(t.get("bakjes")) is None and not t.get("wortel"):
        st.caption("Geen stekbeoordeling.")
    else:
        toon_kengetallen([
            {"label": "Bakjes", "waarde": fmt_kort(t.get("bakjes"))},
            {"label": "Wortel", "waarde": t.get("wortel") or LEEG},
            {"label": "Plantmaat", "waarde": t.get("plantmaat") or LEEG},
            {"label": "Uniformiteit", "waarde": t.get("uniformiteit") or LEEG},
            {"label": "Cijfer", "waarde": fmt_kort(t.get("beoordeling"))},
        ])
        if isinstance(t.get("opmerking"), str) and t["opmerking"].strip():
            st.caption(t["opmerking"])



def _nu_vak_venster(info, vak, vandaag, data):
    """Venster met de hele teelt van één vak."""
    tuin, s = info["tuin"], info["statussen"].get(vak)

    @st.dialog(f"Vak {vak} · {tuin['naam']}", width="large")
    def _venster():
        if s is None:
            st.write(_nu_bloktip(vak, None, info["gepland"].get(vak), info["laatste_oogst"].get(vak), info))
            return
        t, u, model = s["teelt"], s["stook"], info["model"]
        florgib = (format_datum(s["florgib"]) if s["florgib"]
                   else f"verw. {format_datum(u['florgib_verwacht'])}" if u and u["florgib_verwacht"] else LEEG)
        toon_kengetallen([
            {"label": "Code", "waarde": t["code"] or LEEG},
            {"label": "Ras", "waarde": t["ras"] or LEEG},
            {"label": "Afdeling", "waarde": fmt_kort(t["afdeling"])},
            {"label": "Geplant", "waarde": f"{format_datum(s['start'])} (wk {s['plantweek']})"},
            {"label": "Leeftijd", "waarde": fmt_dagen(s["leeftijd"])},
            {"label": "Florgib", "waarde": florgib,
             "help": "Geregistreerde Florgib, of de verwachte: de dag waarop het model het deel van de teelt "
                     "bereikt waarop meestal gespoten wordt"
                     + (f" ({fmt_getal(model.florgib_fractie * 100)} %)." if model and model.florgib_fractie else ".")},
            {"label": "Correctie", "waarde": _nu_c_tekst(u),
             "delta": (f"{fmt_verschil(u['gewicht'], 0, 'g')} gewicht" if u and u["gewicht"] is not None
                       and u["c"] is not None and not tp.op_koers(u["c"]) else None),
             "help": "Constante afwijking van de lichtlijn vanaf vandaag waarmee de teelt precies op de plandatum "
                     f"oogstrijp is (grenzen {fmt_verschil(C_GRENZEN[0], 0)} tot {fmt_verschil(C_GRENZEN[1], 0)} °C). "
                     "Gewichtseffect = correctie × het verband tussen stooklijn en oogstgewicht in de historie "
                     "(indicatief)."},
            {"label": "Status", "waarde": NU_STATUS_KORT[s["klasse"]]},
            {"label": "Plan-oogst", "waarde": format_datum(s["plan"]) if s["plan"] else LEEG,
             "help": "Startdatum + teeltduur uit de teeltduur-tabel."},
            {"label": "Prognose", "waarde": format_datum(s["prognose"]) if s["prognose"] else LEEG,
             "delta": f"{fmt_verschil(s['prognose_dagen'], 0)} d t.o.v. plan" if s["prognose_dagen"] else None,
             "help": f"Oogst als de afdeling blijft stoken zoals de laatste {AFWIJKING_VENSTER_DAGEN} dagen "
                     "(gemiddelde afwijking van de lichtlijn), bij de gemiddelde lichtsom per kalenderweek."},
        ])

        klimaat = data["klimaat"]
        klimaat = klimaat[(klimaat["tuin_id"] == tuin["id"]) & (klimaat["afdeling"] == t["afdeling"])
                          & (klimaat["datum"] >= str(s["start"]))].sort_values("datum")
        water = data["water"]
        water = water[(water["tuin_id"] == tuin["id"]) & (water["vaknummer"] == vak)
                      & (water["datum"] >= str(s["start"]))]
        teelt_detail(s, klimaat, [{"datum": r.datum, "liter": r.liter_per_m2} for r in water.itertuples()], model)

        st.write("**Vergelijking**")
        st.dataframe(_nu_vergelijking(s, info, data), hide_index=True, use_container_width=True)

    _venster()


def _nu_vergelijking(s, info, data):
    """Tabel dit vak / zelfde plantweek vorig jaar / plantweek ±2 in alle jaren en beide tuinen."""
    t, tuin, u = s["teelt"], info["tuin"], s["stook"]
    water = data["water"]

    def water_tot(teelt, dagen):
        start = vs.als_datum(teelt["datum_teelt_start"])
        w = water[(water["tuin_id"] == teelt["tuin_id"]) & (water["vaknummer"] == teelt["vaknummer"])
                  & (water["datum"] >= str(start)) & (water["datum"] <= str(start + timedelta(days=dagen)))]
        return float(w["liter_per_m2"].sum()) if not w.empty else None

    def kengetallen(teelt):
        start, oogst = vs.als_datum(teelt["datum_teelt_start"]), vs.als_datum(teelt["datum_oogst"])
        half = vs.als_datum(teelt.get("datum_half"))
        lengte, gewicht = vs._getal(teelt.get("lengte_eind")), vs._getal(teelt.get("oogstgewicht"))
        return {
            "florgib": (half - start).days if half and half > start else None,
            "half": vs._getal(teelt.get("lengte_half")), "eind": lengte,
            "duur": (oogst - start).days if oogst else None, "uitval": _nu_uitval(teelt),
            "gewicht": gewicht, "g10": gewicht / lengte * 10 if gewicht and lengte else None,
            "water": water_tot(teelt, s["leeftijd"]),
        }

    def gemiddelde(rijen, sleutel):
        waarden = [r[sleutel] for r in rijen if r[sleutel] is not None]
        return sum(waarden) / len(waarden) if waarden else None

    jaar = s["start"].isocalendar()[0]
    afgerond = [k for k in info["alle"] if vs.als_datum(k["datum_oogst"]) and k["id"] != t["id"]]
    vorig = [kengetallen(k) for k in afgerond
             if k["tuin_id"] == tuin["id"]
             and vs.als_datum(k["datum_teelt_start"]).isocalendar()[:2] == (jaar - 1, s["plantweek"])]
    refs = [kengetallen(k) for k in afgerond
            if vs.weekafstand(vs.plantweek(k["datum_teelt_start"]), s["plantweek"]) <= vs.REF_WEEKVENSTER]
    dit = kengetallen(t)
    if dit["florgib"] is None and u and u["florgib_verwacht"]:
        dit["florgib"] = (u["florgib_verwacht"] - s["start"]).days
    oogst_verwacht = s["prognose"] or s["plan"]
    dit["duur"] = (oogst_verwacht - s["start"]).days if oogst_verwacht else None

    regels = [("Florgib op dag", "florgib", 0), ("Lengte halverwege (cm)", "half", 1),
              ("Oogstlengte (cm)", "eind", 1), ("Teeltduur (dagen)", "duur", 0), ("Uitval (%)", "uitval", 1),
              ("Oogstgewicht (g)", "gewicht", 0), ("Gewicht per 10 cm (g)", "g10", 1),
              (f"Water t/m dag {s['leeftijd']} (l/m²)", "water", 0)]
    verwacht = {"duur": s["prognose"] is not None, "florgib": s["florgib"] is None}
    return pd.DataFrame({
        "": [naam for naam, _, _ in regels],
        "Dit vak": [fmt_getal(dit[k], d) + (" (verw.)" if verwacht.get(k) and dit[k] is not None else "")
                    for _, k, d in regels],
        f"Wk {s['plantweek']} vorig jaar ({len(vorig)})": [fmt_getal(gemiddelde(vorig, k), d) for _, k, d in regels],
        f"Wk {s['plantweek']} ±{vs.REF_WEEKVENSTER}, alle jaren, beide tuinen ({len(refs)})":
            [fmt_getal(gemiddelde(refs, k), d) for _, k, d in regels],
    })


def _nu_advies_tekst(afdeling, a):
    if a is None or a["c"] is None:
        return f"Afd. {afdeling}: geen advies (geen lopende teelt met prognose)"
    tekst = f"Afd. {afdeling}: lichtlijn {fmt_verschil(a['c'], 1, '°C')}"
    if a["nu"] is not None:
        tekst += f" (laatste {AFWIJKING_VENSTER_DAGEN} d {fmt_verschil(a['nu'], 1, '°C')})"
    return tekst + f" · vak {a['doorslag']} bepalend"


def _nu_afdeling_venster(info, afdeling, data, vandaag):
    """Stookadvies van één afdeling: c per vak, een schuif voor de afdelingscorrectie en wat die per vak doet."""
    tuin, a, model = info["tuin"], info["advies"].get(afdeling), info["model"]

    @st.dialog(f"Stookadvies afdeling {afdeling} · {tuin['naam']}", width="large")
    def _venster():
        if a is None or a["c"] is None:
            st.info("Geen lopende teelten met een prognose in deze afdeling.")
        else:
            keuze = st.slider(
                "Afdelingscorrectie t.o.v. de lichtlijn (°C)", float(C_GRENZEN[0]), float(C_GRENZEN[1]),
                value=float(round(a["c"], 1)), step=0.1, format="%+.1f", key=f"nu_schuif_{tuin['nummer']}_{afdeling}",
                help="Voorstel = het gemiddelde van de benodigde correctie per vak, gewogen naar het aantal stelen. "
                     "Schuif om te zien wat een andere stooklijn per vak doet.",
            )
            punten = pd.DataFrame([{
                "Vak": f"Vak {v['vak']}", "c": v["c"], "Stelen": v["stelen"],
                "Dagen tot plan": (v["s"]["plan"] - vandaag).days,
                "Plan": f"{v['s']['plan']:%d-%m}", "Correctie": _nu_c_tekst(v["s"]["stook"]),
            } for v in sorted(a["vakken"], key=lambda v: (v["s"]["plan"], v["vak"]))])
            volgorde = list(punten["Vak"])
            stippen = alt.Chart(punten).mark_circle(opacity=0.9).encode(
                x=alt.X("c:Q", title="Benodigde correctie t.o.v. de lichtlijn (°C)",
                        scale=alt.Scale(domain=list(C_GRENZEN))),
                y=alt.Y("Vak:N", sort=volgorde, title=None),
                size=alt.Size("Stelen:Q", legend=None, scale=alt.Scale(range=[60, 260])),
                color=alt.Color("Dagen tot plan:Q", scale=alt.Scale(scheme="viridis"),
                                legend=alt.Legend(orient="bottom", title="Dagen tot plan")),
                tooltip=["Vak", "Plan", "Correctie", alt.Tooltip("Dagen tot plan:Q"),
                         alt.Tooltip("Stelen:Q", format=",.0f")],
            )
            lijnen = pd.DataFrame([
                {"x": 0.0, "Lijn": "Lichtlijn"},
                {"x": a["c"], "Lijn": "Voorstel"},
                {"x": keuze, "Lijn": "Keuze"},
            ] + ([{"x": a["nu"], "Lijn": f"Laatste {AFWIJKING_VENSTER_DAGEN} d"}] if a["nu"] is not None else []))
            namen = ["Lichtlijn", "Voorstel", "Keuze", f"Laatste {AFWIJKING_VENSTER_DAGEN} d"]
            regels = alt.Chart(lijnen).mark_rule().encode(
                x="x:Q",
                color=alt.Color("Lijn:N", title=None, legend=alt.Legend(orient="bottom"),
                                scale=alt.Scale(domain=namen, range=["#999", "#e67e22", "#1f1f1f", "#4c78a8"])),
                strokeDash=alt.StrokeDash("Lijn:N", legend=None,
                                          scale=alt.Scale(domain=namen, range=[[2, 2], [1, 0], [6, 3], [1, 0]])),
            )
            st.altair_chart(alt.layer(regels, stippen).resolve_scale(color="independent")
                            .properties(height=alt.Step(22)), use_container_width=True)
            st.caption(
                f"Voorstel {fmt_verschil(a['c'], 1, '°C')} t.o.v. de lichtlijn = gemiddelde van de vakken, gewogen "
                f"naar stelen. Bepalend is vak {a['doorslag']} (meeste stelen × grootste correctie). Een vak op de "
                f"rand ({fmt_verschil(C_GRENZEN[0], 0)} of {fmt_verschil(C_GRENZEN[1], 0)} °C) haalt de plandatum "
                "ook daar niet."
            )
            tabel = []
            for v in sorted(a["vakken"], key=lambda v: (v["s"]["plan"], v["vak"])):
                s = v["s"]
                oogst = s["stook"]["dag_bij"](keuze)
                tabel.append({
                    "Vak": v["vak"], "Geplant": format_datum(s["start"]), "Plan": format_datum(s["plan"]),
                    "Oogst bij keuze": format_datum(oogst) if oogst else LEEG,
                    "Verschil met plan": (f"{fmt_verschil((oogst - s['plan']).days, 0)} d" if oogst else LEEG),
                    "Gewichtseffect": fmt_verschil(model.gewichtseffect(keuze), 0, "g") if model else LEEG,
                    "Eigen correctie": _nu_c_tekst(s["stook"]),
                })
            st.dataframe(pd.DataFrame(tabel), hide_index=True, use_container_width=True)
            if model and model.gram_per_graad is not None:
                st.caption(f"Gewichtseffect = keuze × {fmt_verschil(model.gram_per_graad, 0)} g per °C boven de "
                           "lichtlijn (verband in de historie, gecorrigeerd voor licht; indicatief).")

        with st.expander("Klimaat laatste 30 dagen"):
            klimaat = data["klimaat"]
            klimaat = klimaat[(klimaat["tuin_id"] == tuin["id"]) & (klimaat["afdeling"] == afdeling)].sort_values("datum")
            licht_temperatuur_grafiek(klimaat.tail(30).to_dict("records"))

    _venster()


def _nu_toon_tuin(info, vandaag, data):
    """Aandachtspunten, stookadvies per afdeling en de matrix van één tuin."""
    tuin_nr = info["tuin"]["nummer"]
    st.markdown(f'<div class="vem-kg-titel">🏡 {html.escape(info["tuin"]["naam"])}</div>', unsafe_allow_html=True)

    # Twee kolommen: 8 meldingen nemen dan 4 regels in, zodat de matrix op
    # een laptopscherm nog zonder scrollen in beeld is.
    with st.container(key=f"nu_punten_{tuin_nr}"):
        if not info["punten"]:
            st.caption("Geen aandachtspunten.")
        kolommen = st.columns(2, gap="small")
        for i, p in enumerate(info["punten"]):
            if kolommen[i % 2].button(f"{NU_PUNT_ICOON[p['ernst']]} {p['tekst']}", key=f"nu_punt_{tuin_nr}_{i}",
                                      type="tertiary", disabled=p["soort"] == "import"):
                _nu_vak_venster(info, p["sleutel"], vandaag, data)

    # Stookadvies per afdeling in teeltvolgorde, elk klikbaar.
    with st.container(key=f"nu_advies_{tuin_nr}"):
        kolommen = st.columns(2, gap="small")
        for i, afdeling in enumerate(info["advies"]):
            if kolommen[i % 2].button(f"🔥 {_nu_advies_tekst(afdeling, info['advies'][afdeling])}",
                                      key=f"nu_adv_{tuin_nr}_{afdeling}", type="tertiary"):
                _nu_afdeling_venster(info, afdeling, data, vandaag)

    # Per afdeling (in teeltvolgorde) een rij: het label links en de vakken in
    # een eigen raster dat bij een smal scherm naar een volgende regel loopt.
    vakken = info["vakken"]
    for afdeling in sorteer_afdelingen(vakken["afdeling"].dropna(), tuin_nr):
        groep = vakken[vakken["afdeling"] == afdeling]
        with st.container(key=f"nu_rij_{tuin_nr}_{afdeling}"):
            st.markdown(f'<div class="nu-afd">Afd. {afdeling}</div>', unsafe_allow_html=True)
            with st.container(key=f"nu_blokken_{tuin_nr}_{afdeling}"):
                for vak in sorted(int(v) for v in groep["vaknummer"]):
                    s = info["statussen"].get(vak)
                    klasse = s["klasse"] if s else "leeg"
                    rand = "fa" if s and s["florgib_achter"] else "ok"
                    label = _nu_bloklabel(vak, s, info["gepland"].get(vak))
                    tip = _nu_bloktip(vak, s, info["gepland"].get(vak), info["laatste_oogst"].get(vak), info)
                    if st.button(label, key=f"nu_vak_{klasse}_{rand}_{tuin_nr}_{vak}", help=tip, width="stretch"):
                        _nu_vak_venster(info, vak, vandaag, data)


with tab_nu:
    _nu_vandaag = date.today()
    _nu_uitleg = (
        "Per vak: plantweek en leeftijd, de Florgib (geregistreerd of verwacht), de correctie op de lichtlijn "
        "die nodig is om op de plandatum te oogsten (met het effect op het gewicht), en plan en prognose.\n\n"
        "Het teeltmodel telt per dag een deel van de teelt af, afhankelijk van de lichtsom binnen en de "
        f"afwijking van de lichtlijn ({formule_tekst()}), met een correctie per tuin. Het leert van alle "
        "afgeronde teelten (historie uit de klimaatregistratie plus wat in de app is afgerond). Na de Florgib "
        "wordt de voortgang gelijkgezet op het deel waarop meestal gespoten wordt.\n\n"
        f"Prognose = oogst als de afdeling blijft stoken zoals de laatste {AFWIJKING_VENSTER_DAGEN} dagen. "
        "Correctie = de vaste afwijking van de lichtlijn vanaf vandaag waarmee de oogst precies op de plandatum "
        f"valt (tussen {fmt_verschil(C_GRENZEN[0], 0)} en {fmt_verschil(C_GRENZEN[1], 0)} °C). "
        f"Binnen ±{fmt_kort(OP_KOERS_MARGE)} °C: op koers. Meldingen vanaf ±{fmt_kort(MELDING_C_DREMPEL)} °C.\n\n"
        "Stookadvies per afdeling = de correctie per vak, gewogen naar het aantal stelen.\n\n"
        "Kleur = prognose t.o.v. plan in dagen: ±1 d op schema, daarna stappen van 2 dagen tot 6 d te vroeg "
        "(donkerblauw) of 7 d te laat (donkerrood)."
    )
    _nu_kop, _nu_keuze_kolom = st.columns([3, 2])
    _nu_kop.subheader("🧭 Nu", help=_nu_uitleg)
    _nu_opties = [t["nummer"] for t in TUINEN] + (["beide"] if len(TUINEN) > 1 else [])
    _nu_keuze = _nu_keuze_kolom.segmented_control(
        "Tuin", _nu_opties, default=TUIN_NUMMER, key="nu_tuin", label_visibility="collapsed",
        format_func=lambda o: "Beide" if o == "beide" else _tuin_labels.get(o, f"Tuin {o}"),
    ) or TUIN_NUMMER

    _nu_gegevens, _nu_teeltmodel, _nu_stook, _nu_afwijking = _nu_alles(_nu_vandaag)
    if _nu_teeltmodel is None:
        st.warning("Nog geen teelthistorie in de database: draai importeer_teelt_historie.py. "
                   "Tot die tijd geen prognose en geen correctie.")
    _nu_tuinen = [t for t in sorted(TUINEN, key=lambda t: t["nummer"])
                  if _nu_keuze == "beide" or t["nummer"] == _nu_keuze]
    for _nu_tuin_rij in _nu_tuinen:
        _nu_toon_tuin(_nu_tuin(_nu_gegevens, _nu_teeltmodel, _nu_stook, _nu_afwijking, _nu_tuin_rij, _nu_vandaag),
                      _nu_vandaag, _nu_gegevens)
    st.markdown(
        '<div class="nu-legenda"><span class="nu-schaal">'
        "<em>−7 d</em>"
        + "".join(f'<i class="{k}"></i>' for k in NU_KLASSEN)
        + "<em>+7 d</em></span>"
        "<span>prognose t.o.v. plan bij de huidige stooklijn (blauw: te vroeg, rood: te laat)</span>"
        '<span><i class="rijp"></i>oogstrijp</span><span><i class="grijs"></i>geen prognose</span>'
        '<span><i class="leeg"></i>leeg</span>'
        f'<span><i class="fa"></i>Florgib &gt; {FLORGIB_ACHTERSTAND_DAGEN} d over tijd</span>'
        "<span>Fg = Florgib · plan +2 d = prognose 2 dagen na plan</span>"
        "<span>klik op een vak, melding of afdeling voor details</span></div>",
        unsafe_allow_html=True,
    )

# --- TUINVERGELIJKING: wat er in een periode in de kas gebeurde, per m² ---
#
# Tuin 1 naast tuin 3 en het totaal (gewogen naar m²). Het rekenwerk staat in
# logic/tuinvergelijking.py, de tabel in ui/vergelijkingstabel.py.


def _tv_geplant(waarde, n):
    if waarde is None:
        return LEEG
    return f"{fmt_getal(waarde, 0, 'm²')} ({n} {'vak' if n == 1 else 'vakken'})"


TV_KENGETALLEN = [
    Kengetal("bezetting", "Bezetting", "Bezetting & productie", "%", 0,
             "Aandeel van het teeltoppervlak met een teelt, gemiddeld over de dagen van de periode."),
    Kengetal("geplant", "Geplant", "Bezetting & productie", "m²", 0,
             "Oppervlakte van de vakken die in de periode geplant zijn.", formaat=_tv_geplant),
    Kengetal("stelen_m2", "Stelen per bezette m²", "Bezetting & productie", "", 1,
             "Emmers × 100 geregistreerd in de periode, gedeeld door de gemiddelde bezette m². Alleen als de "
             "emmerregistratie al vóór de periode liep (tuin 1 sinds 04-06-26, tuin 3 sinds 14-08-26).",
             n_eenheid="teelten"),
    Kengetal("uitval", "Uitval", "Bezetting & productie", "%", 1,
             "Uitval van de teelten afgerond in de periode, gewogen naar vak-m². Uit de emmers, anders het "
             "vastgelegde percentage.", n_eenheid="teelten"),
    Kengetal("temp", "Etmaaltemperatuur", "Klimaat", "°C", 1,
             "Gemiddeld over de afdelingen, gewogen naar hun m².", n_eenheid="d"),
    Kengetal("temp_dag", "Dagtemperatuur", "Klimaat", "°C", 1, "Gemiddeld over de afdelingen, gewogen naar m².",
             n_eenheid="d"),
    Kengetal("temp_nacht", "Nachttemperatuur", "Klimaat", "°C", 1, "Gemiddeld over de afdelingen, gewogen naar m².",
             n_eenheid="d"),
    Kengetal("rv", "RV", "Klimaat", "%", 0, "Etmaalgemiddelde, gewogen naar m² per afdeling.", n_eenheid="d"),
    Kengetal("lichtsom", "Lichtsom binnen per dag", "Klimaat", "J/cm²", 0,
             "Gemiddelde dagsom binnen, gewogen naar m² per afdeling.", n_eenheid="d"),
    Kengetal("afwijking", "Afwijking lichtlijn", "Klimaat", "°C", 1,
             f"Etmaaltemperatuur min de lichtlijn ({formule_tekst()}), per afdeling per dag, gewogen naar m². "
             "Positief = warmer gestookt dan de lichtlijn.", teken=True, n_eenheid="d"),
    Kengetal("warmte", "Warmte", "Energie & water", "MJ/m²", 1,
             "Warmte in de periode gedeeld door de m² kas (de hele kas wordt verwarmd). Tuin 3: Pulsteller; "
             "tuin 1: warmtewisselaar (sinds 09-01-26).", n_eenheid="d"),
    Kengetal("gas", "Gas", "Energie & water", "m³/m²", 2, "Gasverbruik (Pulsteller 1) gedeeld door de m² kas.",
             n_eenheid="d"),
    Kengetal("water", "Water", "Energie & water", "l/m²", 1,
             "Watergift van alle vakken samen in de periode, gedeeld door de m² kas.", n_eenheid="d"),
]


@st.cache_resource(ttl=600, show_spinner="Gegevens ophalen…")
def _tv_gegevens(versie):
    """Alle data van de Tuinvergelijking, voorbereid. `versie` (wijzigingenlog) is alleen de cachesleutel."""
    return tuinvgl.Gegevens(get_vergelijking_data())


def _tv_volgorde(tuin_id, afdeling, vak):
    """Sorteersleutel tuin → afdeling (teeltvolgorde) → vak."""
    nummer = _tuinnummer_van.get(tuin_id, tuin_id)
    volgorde = list(sorteer_afdelingen({afdeling} | set(AFDELING_VOLGORDE.get(nummer, ())), nummer))
    return nummer, volgorde.index(afdeling) if afdeling in volgorde else 99, vak


def _tv_uitklappers(g, van, tot, periode_naam):
    """Geplant, geoogst en watergift in de periode, per vak (tuin → afdeling → vak)."""
    afdeling = g.vak_afdeling

    geplant = sorted((t for t in g.teelten if van <= t["start"] <= tot),
                     key=lambda t: _tv_volgorde(t["tuin_id"], afdeling.get((t["tuin_id"], t["vaknummer"])),
                                                t["vaknummer"]))
    with st.expander(f"🌱 Geplant in deze periode ({len(geplant)})"):
        if geplant:
            toon_tabel(pd.DataFrame([{
                "Tuin": _tuinnaam_van.get(t["tuin_id"], "?"),
                "Afd.": afdeling.get((t["tuin_id"], t["vaknummer"])),
                "Vak": t["vaknummer"], "Code": t.get("code") or "-",
                "Plantdatum": format_datum(t["start"]),
                "Planten": t.get("aantal_planten") if vs._getal(t.get("aantal_planten")) else "-",
                "m²": g.vak_m2.get((t["tuin_id"], t["vaknummer"])),
            } for t in geplant]), [
                ("Tuin", "Tuin", "tekst", None, "small"), ("Afd.", "Afd.", "getal", "%d", "small"),
                ("Vak", "Vak", "getal", "%d", "small"), ("Code", "Code", "tekst", None, "medium"),
                ("Plantdatum", "Plantdatum", "datum", None, "small"), ("Planten", "Planten", "getal", "%d", "small"),
                ("m²", "m²", "getal", "%.0f", "small"),
            ])
        else:
            st.caption("Niets geplant in deze periode.")

    emmers = [e for e in g.emmers if van <= e["datum"] <= tot]
    afgerond = sorted((t for t in g.teelten if t["oogst"] and van <= t["oogst"] <= tot),
                      key=lambda t: _tv_volgorde(t["tuin_id"], afdeling.get((t["tuin_id"], t["vaknummer"])),
                                                 t["vaknummer"]))
    with st.expander(f"🌾 Geoogst in deze periode ({len({e['teelt_id'] for e in emmers})} vakken, "
                     f"{len(afgerond)} afgerond)"):
        if emmers:
            per_vak = {}
            for e in emmers:
                rij = per_vak.setdefault(e["teelt_id"], {"e": e, "emmers": 0.0, "dagen": set()})
                rij["emmers"] += vs._getal(e["aantal_emmers"]) or 0
                rij["dagen"].add(e["datum"])
            rijen = sorted(per_vak.values(), key=lambda r: _tv_volgorde(
                r["e"]["tuin_id"], afdeling.get((r["e"]["tuin_id"], int(r["e"]["vaknummer"]))),
                int(r["e"]["vaknummer"])))
            st.write("**Emmers per vak**")
            toon_tabel(pd.DataFrame([{
                "Tuin": _tuinnaam_van.get(r["e"]["tuin_id"], "?"),
                "Afd.": afdeling.get((r["e"]["tuin_id"], int(r["e"]["vaknummer"]))),
                "Vak": r["e"]["vaknummer"], "Code": r["e"]["code"] or "-",
                "Emmers": r["emmers"], "Stelen": r["emmers"] * 100,
                "Oogstdagen": ", ".join(f"{d:%d-%m}" for d in sorted(r["dagen"])),
            } for r in rijen]), [
                ("Tuin", "Tuin", "tekst", None, "small"), ("Afd.", "Afd.", "getal", "%d", "small"),
                ("Vak", "Vak", "getal", "%d", "small"), ("Code", "Code", "tekst", None, "medium"),
                ("Emmers", "Emmers", "getal", "%d", "small"), ("Stelen", "Stelen", "getal", "%d", "small"),
                ("Oogstdagen", "Oogstdagen", "tekst", None, "medium"),
            ])
        else:
            st.caption("Geen emmers geregistreerd in deze periode.")
        if afgerond:
            st.write("**Afgerond in deze periode**")
            toon_tabel(pd.DataFrame([{
                "Tuin": _tuinnaam_van.get(t["tuin_id"], "?"), "Afd.": afdeling.get((t["tuin_id"], t["vaknummer"])),
                "Vak": t["vaknummer"], "Code": t.get("code") or "-", "Oogstdatum": format_datum(t["oogst"]),
                "Planten": t.get("aantal_planten") if vs._getal(t.get("aantal_planten")) else "-",
                "Stelen": vs._getal(t.get("emmers")) * 100 if vs._getal(t.get("emmers")) else "-",
                "Uitval (%)": tuinvgl.uitval_teelt(t) if tuinvgl.uitval_teelt(t) is not None else "-",
                "Lengte (cm)": t.get("lengte_eind") if vs._getal(t.get("lengte_eind")) else "-",
                "Gewicht (g)": t.get("oogstgewicht") if vs._getal(t.get("oogstgewicht")) else "-",
                "Rijpheid": t.get("rijpheid") or "-",
            } for t in afgerond]), [
                ("Tuin", "Tuin", "tekst", None, "small"), ("Afd.", "Afd.", "getal", "%d", "small"),
                ("Vak", "Vak", "getal", "%d", "small"), ("Code", "Code", "tekst", None, "medium"),
                ("Oogstdatum", "Oogst", "datum", None, "small"), ("Planten", "Planten", "getal", "%d", "small"),
                ("Stelen", "Stelen", "getal", "%d", "small"), ("Uitval (%)", "Uitval (%)", "getal", "%.1f", "small"),
                ("Lengte (cm)", "Lengte (cm)", "getal", "%.1f", "small"),
                ("Gewicht (g)", "Gewicht (g)", "getal", "%d", "small"), ("Rijpheid", "Rijpheid", "tekst", None, "small"),
            ], verberg_leeg=True)

    water = g.water[(g.water["datum"] >= str(van)) & (g.water["datum"] <= str(tot))].dropna(subset=["liter_per_m2"])
    with st.expander("💧 Watergift per vak"):
        if water.empty:
            st.caption("Geen watergift in deze periode.")
        else:
            water = water.assign(
                Tuin=water["tuin_id"].map(lambda t: _tuinnaam_van.get(int(t), "?")),
                Afd=[afdeling.get((int(t), int(v))) for t, v in zip(water["tuin_id"], water["vaknummer"])],
                sorteer=[_tv_volgorde(int(t), afdeling.get((int(t), int(v))), int(v))
                         for t, v in zip(water["tuin_id"], water["vaknummer"])],
            )
            if periode_naam == "Week":
                water["Dag"] = pd.to_datetime(water["datum"]).dt.strftime("%d-%m")
                tabel = water.pivot_table(index=["sorteer", "Tuin", "Afd", "vaknummer"], columns="Dag",
                                          values="liter_per_m2", aggfunc="sum")
                tabel["Totaal"] = tabel.sum(axis=1)
            else:
                tabel = water.groupby(["sorteer", "Tuin", "Afd", "vaknummer"]).agg(
                    Totaal=("liter_per_m2", "sum"), Dagen=("datum", "nunique"))
            tabel = tabel.sort_index().reset_index().drop(columns="sorteer").rename(
                columns={"Afd": "Afd.", "vaknummer": "Vak"})
            st.dataframe(tabel, hide_index=True, use_container_width=True, column_config={
                **{k: getalkolom(k, 1) for k in tabel.columns if k not in ("Tuin", "Afd.", "Vak", "Dagen")},
                "Afd.": getalkolom("Afd.", 0), "Vak": getalkolom("Vak", 0),
            })
            st.caption("Liter per m² vak; bij een week per dag, anders het totaal en het aantal dagen met data.")


with tab_tuinvgl:
    st.subheader("⚖️ Tuinvergelijking", help=(
        "Wat er in een periode in de kas gebeurde: tuin 1 naast tuin 3 en het totaal, alles per m². Het totaal "
        "is gewogen naar m² (niet het gemiddelde van twee tuinen). Een kengetal zonder data toont –."))
    _tv_laatste_priva = laatste_priva_ophaling()
    if _tv_laatste_priva:
        st.caption(f"Klimaat, watergift en energie bijgewerkt tot {format_datum(_tv_laatste_priva.date())} "
                   f"{_tv_laatste_priva:%H:%M}.")
    _tv_vandaag = date.today()
    _tv_g = _tv_gegevens(vakstatus_dataversie())
    _tv_tuinen = [(t["naam"], t["id"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])]

    _tv_k1, _tv_k2, _tv_k3 = st.columns([1.3, 1.2, 1.6])
    _tv_periode = _tv_k1.segmented_control("Periode", list(perioden.PERIODEN), default="Week", key="tv_periode") \
        or "Week"
    _tv_sleutel_key = f"tv_sleutel_{_tv_periode}"
    if _tv_sleutel_key not in st.session_state:
        st.session_state[_tv_sleutel_key] = perioden.laatste_volledige(_tv_periode, _tv_vandaag)
    _tv_huidig = perioden.periode_sleutel(_tv_vandaag, _tv_periode)[0]

    def _tv_blader(stappen, sleutel_key=_tv_sleutel_key, periode=_tv_periode):
        st.session_state[sleutel_key] = perioden.verschuif(st.session_state[sleutel_key], periode, stappen)

    with _tv_k2:
        st.markdown('<div style="font-size:14px;margin-bottom:0.3rem">Welke</div>', unsafe_allow_html=True)
        _tv_b1, _tv_lbl, _tv_b2 = st.columns([1, 3, 1], vertical_alignment="center")
        _tv_b1.button("◀", key="tv_terug", on_click=_tv_blader, args=(-1,), help="Vorige periode")
        _tv_sleutel = st.session_state[_tv_sleutel_key]
        _tv_lbl.markdown(f"**{perioden.periode_label(_tv_sleutel, _tv_periode)}**")
        _tv_b2.button("▶", key="tv_verder", on_click=_tv_blader, args=(1,), help="Volgende periode",
                      disabled=_tv_sleutel >= _tv_huidig)
    _tv_vergelijk = _tv_k3.radio("Vergelijk met", ["vorige periode", "zelfde periode vorig jaar"], index=1,
                                 horizontal=True, key="tv_vergelijk")
    _tv_soort = "vorige" if _tv_vergelijk == "vorige periode" else "vorig_jaar"

    _tv_van, _tv_tot, _tv_loopt = perioden.venster(_tv_sleutel, _tv_periode, _tv_vandaag)
    _tv_v_van, _tv_v_tot, _tv_v_label = perioden.vergelijk_venster(_tv_sleutel, _tv_periode, _tv_soort, _tv_vandaag)
    _tv_nu, _tv_n, _tv_bron = tuinvgl.tabelwaarden(_tv_g, _tv_tuinen, _tv_van, _tv_tot)
    _tv_toen, _, _tv_bron_toen = tuinvgl.tabelwaarden(_tv_g, _tv_tuinen, _tv_v_van, _tv_v_tot)
    st.caption(
        f"{format_datum(_tv_van)} t/m {format_datum(_tv_tot)}" + (" (loopt nog, t/m gisteren)" if _tv_loopt else "")
        + f". Kleine regel = verschil met {_tv_v_label}"
        + (f" ({format_datum(_tv_v_van)} t/m {format_datum(_tv_v_tot)})" if _tv_loopt else "")
        + "; – als er toen geen data was. Groen = beter, rood = slechter, grijs = neutraal; lichtgroen vak = "
          "beste tuin. n = aantal dagen of teelten met data."
    )

    def _tv_verloop(k, sleutel=_tv_sleutel, periode=_tv_periode):
        rijen = []
        for stap in range(-11, 1):
            s = perioden.verschuif(sleutel, periode, stap)
            van, tot, _ = perioden.venster(s, periode, _tv_vandaag)
            if tot < van:
                continue
            w, n, _ = tuinvgl.tabelwaarden(_tv_g, _tv_tuinen, van, tot)
            for naam, _ in _tv_tuinen:
                rijen.append({"Periode": perioden.periode_label(s, periode), "Tuin": naam,
                              "Waarde": w[naam].get(k.sleutel), "n": n[naam].get(k.sleutel, 0)})
        return verloop_frame(rijen)

    vergelijkingstabel.toon(TV_KENGETALLEN, [n for n, _ in _tv_tuinen] + ["Totaal"], _tv_nu, _tv_toen, _tv_n,
                            sleutel="tv_verloop", verloop=_tv_verloop,
                            verloop_titel=f"Verloop over 12 {'weken' if _tv_periode == 'Week' else 'perioden'}",
                            bron=_tv_bron, bron_toen=_tv_bron_toen)

    # Trend geoogste stelen (uit de emmers), de laatste 12 perioden t/m de gekozen.
    st.write("**Geoogste stelen per periode**")
    _tv_eenheid = st.radio("Eenheid", ["Totaal", "Per bezette m²"], horizontal=True, key="tv_stelen_eenheid",
                           label_visibility="collapsed")
    _tv_trend = []
    for _tv_stap in range(-11, 1):
        _tv_s = perioden.verschuif(_tv_sleutel, _tv_periode, _tv_stap)
        _tv_pv, _tv_pt, _ = perioden.venster(_tv_s, _tv_periode, _tv_vandaag)
        if _tv_pt < _tv_pv:
            continue
        for _tv_naam, _tv_id in _tv_tuinen:
            _tv_delen = tuinvgl.onderdelen(_tv_g, _tv_id, _tv_pv, _tv_pt).get("stelen_m2")
            if _tv_delen:
                _tv_trend.append({
                    "Periode": perioden.periode_label(_tv_s, _tv_periode), "Tuin": _tv_naam,
                    "Waarde": _tv_delen[0] if _tv_eenheid == "Totaal" else tuinvgl.waarde(_tv_delen, "stelen_m2"),
                    "n": _tv_delen[2]})
    if not _tv_trend:
        st.caption("Nog geen emmers geregistreerd in deze perioden.")
    else:
        _tv_df = pd.DataFrame(_tv_trend)
        _tv_enc = dict(
            x=alt.X("Periode:O", sort=list(dict.fromkeys(_tv_df["Periode"])), title=None,
                    axis=alt.Axis(labelAngle=-40 if _tv_periode == "Week" else 0)),
            y=alt.Y("Waarde:Q", title="Geoogste stelen" if _tv_eenheid == "Totaal" else "Stelen per bezette m²"),
            color=alt.Color("Tuin:N", title=None, legend=alt.Legend(orient="top")),
            tooltip=["Periode", "Tuin", alt.Tooltip("Waarde:Q", format=",.0f" if _tv_eenheid == "Totaal" else ",.1f"),
                     alt.Tooltip("n:Q", title="teelten")],
        )
        if _tv_eenheid != "Totaal":
            _tv_enc["xOffset"] = alt.XOffset("Tuin:N")
        st.altair_chart(alt.Chart(_tv_df).mark_bar().encode(**_tv_enc).properties(height=240),
                        use_container_width=True)
        st.caption("Uit de emmers (× 100 stelen): tuin 1 sinds 04-06-26, tuin 3 sinds 14-08-26. Totaal gestapeld; "
                   "per bezette m² naast elkaar.")

    _tv_uitklappers(_tv_g, _tv_van, _tv_tot, _tv_periode)

# --- TEELTVERGELIJKING: alle plantingen uit één plantweek ---
#
# Bovenaan een samenvatting per tuin (gewogen naar m² van het vak), daaronder
# de teelten naast elkaar. Rekenwerk in logic/teeltvergelijking.py.


def _tl_tekst(waarde, n):
    return waarde or LEEG


TL_KENGETALLEN = [
    Kengetal("aantal", "Aantal teelten", "Teelt", "", 0, "Teelten met een plantdatum in deze week.",
             formaat=lambda w, n: LEEG if w is None else f"{int(w)} ({n} afgerond, {int(w) - n} lopend)"),
    Kengetal("plantdatum", "Plantdatum", "Teelt", uitleg="Eerste en laatste plantdatum.", formaat=_tl_tekst,
             verschil=False),
    Kengetal("florgib", "Florgib", "Teelt", uitleg="Eerste en laatste Florgib-datum (app, anders klimaatregistratie).",
             formaat=_tl_tekst, verschil=False),
    Kengetal("fase1", "Fase 1 (planten → Florgib)", "Teelt", "d", 0, "Dagen van planten tot de Florgib.",
             n_eenheid="teelten"),
    Kengetal("oogst", "Oogst", "Teelt", uitleg="Eerste en laatste oogstdatum; ⏳ = met de prognose van het Nu-model "
             "voor lopende teelten.", formaat=_tl_tekst, verschil=False),
    Kengetal("fase2", "Fase 2 (Florgib → oogst)", "Teelt", "d", 0, "Dagen van de Florgib tot de oogst (⏳ = met prognose).",
             n_eenheid="teelten"),
    Kengetal("teeltduur", "Teeltduur", "Teelt", "d", 0, "Dagen van planten tot oogst (⏳ = met prognose).",
             n_eenheid="teelten"),
    Kengetal("lichtsom", "Lichtsom binnen per dag", "Klimaat tijdens de teelt", "J/cm²", 0,
             "Gemiddelde dagsom binnen over de hele teelt, eigen afdeling. Alleen afgeronde teelten.",
             n_eenheid="teelten"),
    Kengetal("temp", "Etmaaltemperatuur", "Klimaat tijdens de teelt", "°C", 1,
             "Gemiddeld over de teelt, eigen afdeling. Alleen afgeronde teelten.", n_eenheid="teelten"),
    Kengetal("afwijking", "Afwijking lichtlijn", "Klimaat tijdens de teelt", "°C", 1,
             f"Etmaaltemperatuur min de lichtlijn ({formule_tekst()}) bij de gemiddelde lichtsom van de teelt.",
             teken=True, n_eenheid="teelten"),
    Kengetal("warmte", "Warmte", "Input (per m²)", "MJ/m²", 0,
             "Warmte (en gas) per bezette m² over de teelt; alleen als (vrijwel) elke dag gemeten is.",
             n_eenheid="teelten"),
    Kengetal("water", "Water", "Input (per m²)", "l/m²", 0, "Totale watergift van het vak over de teelt.",
             n_eenheid="teelten"),
    Kengetal("stelen_m2", "Stelen per m²", "Resultaat", "", 1,
             "Geoogste stelen (emmers × 100, anders geplant × (1 − uitval)) per m² vak.", n_eenheid="teelten"),
    Kengetal("uitval", "Uitval", "Resultaat", "%", 1, "Uit de emmers, anders het vastgelegde percentage.",
             n_eenheid="teelten"),
    Kengetal("lengte", "Oogstlengte", "Resultaat", "cm", 1, "Lengte bij de oogst.", n_eenheid="teelten"),
    Kengetal("gewicht", "Oogstgewicht", "Resultaat", "g", 0, "Vastgelegd oogstgewicht (tuin 1 weegt niet).",
             n_eenheid="teelten"),
    Kengetal("lengte_fg", "Lengte bij Florgib", "Resultaat", "cm", 1, "Lengtemeting bij de Florgib.",
             n_eenheid="teelten"),
    Kengetal("lengtefactor", "Lengtefactor", "Resultaat", "", 2, "Oogstlengte gedeeld door de lengte bij de Florgib.",
             n_eenheid="teelten"),
    Kengetal("stek", "Stekcijfer", "Stek", "", 1, "Gemiddeld cijfer van de stekbeoordeling.", n_eenheid="teelten"),
    Kengetal("stek_matig", "Stek matig of slechter", "Stek", "", 0,
             "Vakken met wortel, plantmaat of uniformiteit 'Matig' of 'Slecht'.",
             formaat=lambda w, n: LEEG if w is None else f"{int(w)} van {n} vakken"),
]

# Kolommen van de teelttabel: (sleutel, kop, decimalen)
TL_KOLOMMEN = [("fase1", "Fase 1 (d)", 0), ("fase2", "Fase 2 (d)", 0), ("teeltduur", "Duur (d)", 0),
               ("lichtsom", "Licht/dag", 0), ("temp", "Etmaal °C", 1), ("afwijking", "Afw. lichtlijn", 1),
               ("warmte", "Warmte MJ/m²", 0), ("water", "Water l/m²", 0), ("stelen_m2", "Stelen/m²", 1),
               ("uitval", "Uitval %", 1), ("lengte", "Lengte cm", 1), ("gewicht", "Gewicht g", 0),
               ("stek", "Stekcijfer", 0)]


@st.cache_data(ttl=600, show_spinner="Teelten ophalen…")
def _tl_ruw(versie):
    """Kengetallen van alle teelten (zie database.get_teeltvergelijking_data); `versie` is de cachesleutel."""
    return get_teeltvergelijking_data()


def _tl_teelten(versie, vandaag):
    """Alle teelten als dicts van logic.teeltvergelijking, met de prognose van het Nu-model voor lopende teelten."""
    g = _tv_gegevens(versie)
    stook = _nu_alles(vandaag)[2]
    return [teeltvgl.teelt(k, g.vak_m2.get((k["tuin_id"], int(k["vaknummer"]))),
                           prognose=(stook.get(k["id"]) or {}).get("prognose"),
                           florgib_historie=k.get("florgib_historie"))
            for k in _tl_ruw(versie) if vs.als_datum(k["datum_teelt_start"]) <= vandaag]


def _tl_detail_venster(teelt_id, teelten, vandaag):
    """Popup met de hele teelt: dezelfde weergave als het vakvenster in Nu, ook voor afgeronde teelten."""
    data, model, stook, _ = _nu_alles(vandaag)
    alle = data["teelten"].to_dict("records")
    t = next((r for r in alle if r["id"] == teelt_id), None)
    rij = next((r for r in teelten if r["id"] == teelt_id), None)
    if t is None or rij is None:
        return
    tuin = _tuinnaam_van.get(t["tuin_id"], "?")

    @st.dialog(f"Vak {t['vaknummer']} · {tuin} · {t['code'] or '-'}", width="large")
    def _venster():
        start, oogst = vs.als_datum(t["datum_teelt_start"]), vs.als_datum(t["datum_oogst"])
        s = vs.beoordeel_teelt(t, alle, oogst or vandaag, bereken_verwachte_oogstdatum)
        s["stook"] = stook.get(teelt_id) if not oogst else None
        if s["stook"]:
            s["prognose"] = s["stook"]["prognose"]
        if not s["florgib"] and rij["florgib"]:
            s["florgib"] = rij["florgib"]
        toon_kengetallen([
            {"label": "Tuin", "waarde": tuin},
            {"label": "Afdeling", "waarde": fmt_kort(t["afdeling"])},
            {"label": "Ras", "waarde": t["ras"] or LEEG},
            {"label": "Geplant", "waarde": f"{format_datum(start)} (wk {s['plantweek']})"},
            {"label": "Florgib", "waarde": format_datum(rij["florgib"]) if rij["florgib"] else LEEG},
            {"label": "Oogst" if oogst else "Prognose ⏳",
             "waarde": format_datum(rij["oogst"]) if rij["oogst"] else LEEG},
            {"label": "Teeltduur", "waarde": fmt_dagen(rij["teeltduur"]) if rij["teeltduur"] else LEEG},
            {"label": "Uitval", "waarde": fmt_pct(rij["uitval"])},
            {"label": "Oogstlengte", "waarde": fmt_getal(rij["lengte"], 1, "cm")},
            {"label": "Oogstgewicht", "waarde": fmt_getal(rij["gewicht"], 0, "g")},
        ])
        eind = oogst or vandaag
        klimaat = pd.DataFrame(
            get_klimaatdata_dagen_voor_periode(t["afdeling"], str(start), str(eind), t["tuin_id"]),
            columns=["datum", "temp_24h", "rv_24h", "lichtsom", "temp_dag", "temp_nacht", "rv_dag", "rv_nacht"])
        water = [{"datum": d, "liter": liter}
                 for d, liter in get_watergift_dagen_voor_periode(t["vaknummer"], str(start), str(eind), t["tuin_id"])]
        teelt_detail(s, klimaat, water, model)

    _venster()


def _tl_teelttabel(groep, vandaag):
    """De teelten van de plantweek naast elkaar; een klik op een regel opent de teelt."""
    groep = sorted(groep, key=lambda t: _tv_volgorde(t["tuin_id"], t["afdeling"], t["vak"]))
    rijen = []
    for t in groep:
        rij = {"Tuin": _tuinnaam_van.get(t["tuin_id"], "?"), "Afd.": t["afdeling"], "Vak": t["vak"],
               "Code": t["code"] or "-", "Status": "✅ afgerond" if t["afgerond"] else "⏳ lopend",
               "Geplant": format_datum(t["start"]), "Florgib": format_datum(t["florgib"]) if t["florgib"] else LEEG,
               "Oogst": (("⏳ " if t["prognose"] else "") + format_datum(t["oogst"])) if t["oogst"] else LEEG}
        for sleutel, kop, _ in TL_KOLOMMEN:
            rij[kop] = t[sleutel]
        rijen.append(rij)
    df = pd.DataFrame(rijen)

    # Kleur: afwijking van het (m²-gewogen) gemiddelde van de plantweek, alleen
    # waar "beter" vastligt en vanaf 5 %, zodat uitschieters opvallen.
    kleuren = pd.DataFrame("", index=df.index, columns=df.columns)
    for sleutel, kop, _ in TL_KOLOMMEN:
        richting = kg.RICHTING.get(sleutel, 0)
        if not richting:
            continue
        afwijking = teeltvgl.afwijking_van_gemiddelde(groep, sleutel)
        for i, t in enumerate(groep):
            a = afwijking.get(t["id"])
            if a is not None and abs(a) >= 0.05:
                beter = a * richting > 0
                kleuren.loc[i, kop] = f"background-color: {'rgba(46,160,67,0.18)' if beter else 'rgba(214,69,65,0.18)'}"
    def _opmaak(sleutel, decimalen):
        def formatteer(x):
            if x is None or x != x:
                return LEEG
            return fmt_verschil(x, decimalen) if sleutel == "afwijking" else fmt_getal(x, decimalen)
        return formatteer

    opmaak = {kop: _opmaak(sleutel, d) for sleutel, kop, d in TL_KOLOMMEN}
    styler = df.style.apply(lambda _: kleuren, axis=None).format(opmaak)
    keuze = st.dataframe(
        styler, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
        key="tl_teelten", column_config={
            "Tuin": st.column_config.TextColumn(pinned=True), "Afd.": st.column_config.NumberColumn(pinned=True),
            "Vak": st.column_config.NumberColumn(pinned=True), "Code": st.column_config.TextColumn(pinned=True),
        })
    st.caption("Groen/rood = minstens 5 % beter/slechter dan het gemiddelde van deze plantweek (alleen waar beter "
               "vastligt). ⏳ = lopende teelt; oogst en duur zijn dan de prognose. Klik op een regel voor de teelt.")
    gekozen = keuze.selection.rows if keuze else []
    vorige = st.session_state.get("tl_gekozen")
    if gekozen and gekozen != vorige:
        st.session_state["tl_gekozen"] = gekozen
        _tl_detail_venster(groep[gekozen[0]]["id"], groep, vandaag)
    elif not gekozen:
        st.session_state["tl_gekozen"] = None


with tab_teeltvgl:
    st.subheader("🌿 Teeltvergelijking", help=(
        "Alle plantingen uit één plantweek: bovenaan per tuin samengevat (gewogen naar de m² van het vak), "
        "daaronder de teelten naast elkaar. De kleine regel vergelijkt met dezelfde plantweek vorig jaar."))
    _tl_vandaag = date.today()
    _tl_versie = vakstatus_dataversie()
    _tl_alle = _tl_teelten(_tl_versie, _tl_vandaag)
    _tl_weken = teeltvgl.plantweken(_tl_alle)
    _tl_lijst = sorted(_tl_weken, reverse=True)
    if not _tl_lijst:
        st.info("Nog geen teelten.")
    else:
        if st.session_state.get("tl_week") not in _tl_lijst:
            st.session_state["tl_week"] = teeltvgl.standaard_plantweek(_tl_weken)

        def _tl_blader(stappen):
            i = _tl_lijst.index(st.session_state["tl_week"]) - stappen   # lijst loopt van nieuw naar oud
            st.session_state["tl_week"] = _tl_lijst[max(0, min(i, len(_tl_lijst) - 1))]

        _tl_k1, _tl_k2, _tl_k3 = st.columns([0.35, 3, 0.35], vertical_alignment="bottom")
        _tl_k1.button("◀", key="tl_terug", on_click=_tl_blader, args=(-1,), help="Vorige plantweek",
                      disabled=st.session_state["tl_week"] == _tl_lijst[-1])
        _tl_k2.selectbox(
            "Plantweek", _tl_lijst, key="tl_week",
            format_func=lambda w: f"Wk {w[1]} - {w[0]} · {_tl_weken[w][0]} teelten, {_tl_weken[w][1]} afgerond")
        _tl_k3.button("▶", key="tl_verder", on_click=_tl_blader, args=(1,), help="Volgende plantweek",
                      disabled=st.session_state["tl_week"] == _tl_lijst[0])
        _tl_week = st.session_state["tl_week"]
        _tl_vorig = teeltvgl.vorig_jaar(_tl_week)
        _tl_tuinen = [(t["naam"], t["id"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])]
        _tl_groep = [t for t in _tl_alle if teeltvgl.plantweek(t["start"]) == _tl_week]
        _tl_toen_groep = [t for t in _tl_alle if teeltvgl.plantweek(t["start"]) == _tl_vorig]
        _tl_nu, _tl_n, _tl_bron, _tl_mark = teeltvgl.tabelwaarden(_tl_groep, _tl_tuinen)
        _tl_toen, _, _tl_bron_toen, _ = teeltvgl.tabelwaarden(_tl_toen_groep, _tl_tuinen)
        st.caption(f"Kleine regel = verschil met plantweek {_tl_vorig[1]} van {_tl_vorig[0]} "
                   f"({len(_tl_toen_groep)} teelten); – als een tuin toen niet plantte. Groen = beter, rood = "
                   "slechter, grijs = neutraal; lichtgroen vak = beste tuin. ⏳ = met prognose voor lopende teelten.")

        def _tl_verloop(k, week=_tl_week):
            rijen = []
            for w in teeltvgl.vorige_weken(week, 12):
                groep = [t for t in _tl_alle if teeltvgl.plantweek(t["start"]) == w]
                waarden, aantallen, _, _ = teeltvgl.tabelwaarden(groep, _tl_tuinen)
                for naam, _ in _tl_tuinen:
                    waarde = waarden.get(naam, {}).get(k.sleutel)
                    rijen.append({"Periode": f"Wk {w[1]} - {w[0]}", "Tuin": naam,
                                  "Waarde": waarde if isinstance(waarde, (int, float)) else None,
                                  "n": aantallen.get(naam, {}).get(k.sleutel, 0)})
            return verloop_frame(rijen)

        vergelijkingstabel.toon(
            TL_KENGETALLEN, [n for n, _ in _tl_tuinen] + ["Totaal"], _tl_nu, _tl_toen, _tl_n,
            sleutel="tl_verloop", verloop=_tl_verloop, verloop_titel="Verloop over 12 plantweken",
            bron=_tl_bron, bron_toen=_tl_bron_toen, markering=_tl_mark)

        st.write("**Teelten van deze plantweek**")
        _tl_teelttabel(_tl_groep, _tl_vandaag)

# --- VOORUITBLIK: wat er de komende weken te planten en te oogsten staat (beide tuinen) ---
#
# Tuin 1 heeft grotere vakken dan tuin 3 (883 vs 550 m², 53064 vs 32688
# stelen bij 60/m²). "3 vakken" betekent dus niet in beide tuinen evenveel
# areaal of planten — daarom is dit om te zetten naar m² of aantal stelen.

def toon_vooruitblik(vandaag, n_weken=6):
    """Tabel met per week en per tuin wat er geplant (concepten) en geoogst (lopend + concepten) wordt."""
    st.write(f"**Vooruitblik komende {n_weken} weken (beide tuinen)**")
    eenheid = st.radio("Eenheid", ["Aantal vakken", "m²", "Aantal stelen"], horizontal=True,
                       key="vooruitblik_eenheid")
    tuinen = sorted(TUINEN, key=lambda t: t["nummer"])
    vakgegevens = {t["id"]: get_vakgegevens(t["id"]) for t in tuinen}
    maandag_nu = vandaag - timedelta(days=vandaag.weekday())
    weken = [maandag_nu + timedelta(weeks=i) for i in range(n_weken)]
    data, _, stook, _ = _nu_alles(vandaag)
    lopend = [t for t in data["teelten"].to_dict("records") if not vs.als_datum(t["datum_oogst"])]

    def waarde(tuin_id, vak, startdatum, aantal_planten=None):
        """
        Hoeveel één planting/oogst meetelt, in de gekozen eenheid. Een concept
        heeft nog geen vastgelegd plantaantal; dat wordt dan geschat met de
        standaarddichtheid voor die plantweek, net als het invulscherm doet.
        """
        if eenheid == "Aantal vakken":
            return 1
        gegevens = vakgegevens[tuin_id].get(vak, {})
        if eenheid == "m²":
            return gegevens.get("oppervlakte_m2") or 0
        if vs._getal(aantal_planten):
            return vs._getal(aantal_planten)
        dichtheid = standaard_dichtheid_voor_plantweek(get_weeknummer(startdatum))
        return round((gegevens.get("stelen_bij_60") or 0) / 60 * dichtheid)

    def week_van(dag):
        """Maandag van de week; een oogst die al vóór deze week verwacht werd telt bij deze week."""
        return max(weken[0], dag - timedelta(days=dag.weekday()))

    rijen = [{"Week": f"Week {w.isocalendar()[1]} - {w.isocalendar()[0]}" + (" (deze week)" if i == 0 else "")}
             for i, w in enumerate(weken)]
    for tuin in tuinen:
        plant, oogst = {w: 0 for w in weken}, {w: 0 for w in weken}
        for t in (t for t in lopend if t["tuin_id"] == tuin["id"]):
            start = vs.als_datum(t["datum_teelt_start"])
            # Prognose van het teeltmodel (zoals in "Nu"), anders de plandatum.
            verwacht = (stook.get(t["id"]) or {}).get("prognose") or bereken_verwachte_oogstdatum(start)[1]
            if verwacht and week_van(verwacht) in oogst:
                oogst[week_van(verwacht)] += waarde(tuin["id"], t["vaknummer"], start, t["aantal_planten"])
        for _pid, vak, start, _duur, eind, _notitie in get_planning(tuin["id"]):
            start = vs.als_datum(start)
            if week_van(start) in plant:
                plant[week_van(start)] += waarde(tuin["id"], vak, start)
            if eind and week_van(vs.als_datum(eind)) in oogst:
                oogst[week_van(vs.als_datum(eind))] += waarde(tuin["id"], vak, start)
        for rij, w in zip(rijen, weken):
            rij[f"{tuin['naam']} plant"] = round(plant[w])
            rij[f"{tuin['naam']} oogst"] = round(oogst[w])
    kolommen = [("Week", "Week", "tekst", None, "medium")]
    for tuin in tuinen:
        kolommen += [(f"{tuin['naam']} plant", f"{tuin['naam']} plant", "getal", "%d", "small"),
                     (f"{tuin['naam']} oogst", f"{tuin['naam']} oogst", "getal", "%d", "small")]
    toon_tabel(pd.DataFrame(rijen), kolommen)
    st.caption(
        f"In {eenheid.lower()}. Plant = concept-plantingen die week; oogst = lopende teelten en concepten "
        "waarvan de (verwachte) oogst in die week valt. Voor lopende teelten is dat de prognose van het "
        "teeltmodel bij de huidige stooklijn (zoals in 🧭 Nu), voor concepten de plandatum. Een oogst die al "
        "werd verwacht vóór deze week telt mee bij 'deze week', zodat die niet uit beeld verdwijnt. Stelen bij "
        "een concept zijn een schatting op de standaarddichtheid voor die plantweek."
    )


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
    ("Florgib (g)", "Florgib (g)", "getal", "%.1f", "small"),
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
            {"label": "Gem. duur", "waarde": fmt_dagen(gem_duur)},
        ])

        st.markdown("---")

        # Afgeronde teelten staan standaard ingeklapt: de tabel groeit elke
        # afgeronde teelt door, en dagelijks is vooral het lopende/nog te
        # starten deel relevant.
        mask_afgerond = df['Status'] == 'Afgerond'
        verborgen = ['ID', '_startdatum_iso']
        df_ov_actief = df.loc[~mask_afgerond].drop(columns=verborgen)
        # Laatst afgeronde teelt bovenaan: op oogstdatum (staat als dd-mm-yy
        # in de tabel, dus eerst terug naar een datum), bij gelijke oogstdag
        # de laatst geplante eerst.
        df_ov_afgerond = df.loc[mask_afgerond].assign(
            _oogst=lambda d: pd.to_datetime(d["Oogstdatum"], format="%d-%m-%y", errors="coerce")
        ).sort_values(['_oogst', '_startdatum_iso'], ascending=False).drop(columns=verborgen + ['_oogst'])

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
            "een gemiddelde; klimaat komt van de eigen afdeling. Warmte is het verbruik van de "
            "kas, verdeeld over alleen de vakken die die week een teelt hadden. "
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
        toon_strokenplanning(stroken, get_vaknummers())
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
            f"Plantweek {get_weeknummer(plan_startdatum)} → verwachte teeltduur {fmt_kort(plan_duur, 1)} weken, "
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
            col3.write(fmt_kort(duur, 1, "wk"))
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


with tab_planning:
    st.markdown("---")
    toon_vooruitblik(date.today())

# --- STEK ---
# Kolommen van het weekrapport, zoals de stekleverancier ze uit het oude
# Excel-blad "Weekrapport" gewend is.
# De kolommen van het weekrapport, in de volgorde die de stekleverancier gewend
# is uit het oude Excel-blad. "Cel dagen" houden we aan als lege kolom: die
# wordt niet in de app bijgehouden, maar hoort wel in hun overzicht.
STEK_RAPPORT_KOLOMMEN = [
    "Week", "Dag", "Vak", "Ras", "Te poten", "Bakjes Gepoot", "Uitval",
    "Cel dagen", "Wortel", "Plantmaat", "Uniformiteit", "Totaal beoordeling",
    "Opmerkingen",
]
# Rechts uitlijnen wat een getal is, de rest links.
STEK_RECHTS = {"Vak", "Te poten", "Bakjes Gepoot", "Uitval", "Cel dagen", "Totaal beoordeling"}
_DAGEN_STEK = ["ma", "di", "wo", "do", "vr", "za", "zo"]
NIET_WIJZIGEN = "— niet wijzigen —"


def _leeg_naar_none(waarde):
    """Lege cel uit st.data_editor (None, NaN of lege tekst) -> None."""
    if waarde is None or (not isinstance(waarde, str) and pd.isna(waarde)):
        return None
    if isinstance(waarde, str) and not waarde.strip():
        return None
    return waarde.strip() if isinstance(waarde, str) else waarde


def _stek_afkorting(ras):
    """De afkorting die de leverancier gebruikt: Cameron -> Cam."""
    ras = (ras or "").strip()
    return ras[:3] if ras else ""


def _stek_getal(waarde, decimalen=0):
    """Nederlands getal: punt als duizendtal, komma als decimaal."""
    if waarde is None or (not isinstance(waarde, str) and pd.isna(waarde)):
        return ""
    tekst = f"{float(waarde):,.{decimalen}f}"
    return tekst.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _stek_mailhtml(rapport, totaal_geplant):
    """
    De mail als HTML: een groet, de tabel met randen en eronder het totaal.
    Precies wat er in Outlook geplakt moet worden; de handtekening zit al in
    de mail zelf.
    """
    cel = "border:1px solid #000;padding:2px 6px;"
    koppen = "".join(
        f'<th style="{cel}text-align:{"right" if k in STEK_RECHTS else "left"};">{html.escape(k)}</th>'
        for k in STEK_RAPPORT_KOLOMMEN
    )
    regels = []
    for _, r in rapport.iterrows():
        cellen = "".join(
            f'<td style="{cel}text-align:{"right" if k in STEK_RECHTS else "left"};">'
            f'{html.escape(str(r[k]))}</td>'
            for k in STEK_RAPPORT_KOLOMMEN
        )
        regels.append(f"<tr>{cellen}</tr>")
    return (
        '<div style="font-family:Aptos,Calibri,sans-serif;font-size:11pt;">'
        "<p>Goedemorgen,</p>"
        '<table style="border-collapse:collapse;">'
        f"<tr>{koppen}</tr>{''.join(regels)}</table>"
        f"<p>Totaal geplant: {_stek_getal(totaal_geplant)}</p></div>"
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
                    min_value=0.0, step=0.5, format="localized", width="small",
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
        # Alles als tekst, al in de Nederlandse schrijfwijze: deze tabel gaat
        # één op één de mail in, dus wat hier staat is wat de leverancier ziet.
        _uitval_stek = [
            stek_uitval_pct(p, None if pd.isna(b) else b)
            for p, b in zip(bewerkt_stek["Te poten"], bewerkt_stek["Bakjes"])
        ]
        rapport_stek = pd.DataFrame({
            "Week": [str(get_weeknummer(r["datum"])) for r in rijen_stek],
            "Dag": [
                _DAGEN_STEK[date.fromisoformat(str(r["datum"])[:10]).weekday()].capitalize()
                for r in rijen_stek
            ],
            "Vak": [str(int(v)) for v in bewerkt_stek["Vak"]],
            "Ras": [_stek_afkorting(_leeg_naar_none(v)) for v in bewerkt_stek["Plant"]],
            "Te poten": [_stek_getal(v) for v in bewerkt_stek["Te poten"]],
            "Bakjes Gepoot": [_stek_getal(v, 1).removesuffix(",0") for v in bewerkt_stek["Bakjes"]],
            "Uitval": [_stek_getal(u, 1) for u in _uitval_stek],
            "Cel dagen": ["" for _ in rijen_stek],
            "Wortel": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Wortel"]],
            "Plantmaat": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Plantmaat"]],
            "Uniformiteit": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Uniformiteit"]],
            "Totaal beoordeling": [_stek_getal(v) for v in bewerkt_stek["Beoordeling"]],
            "Opmerkingen": [(_leeg_naar_none(v) or "") for v in bewerkt_stek["Opmerking"]],
        }, columns=STEK_RAPPORT_KOLOMMEN)
        toon_tabel(rapport_stek, [
            (k, k, "tekst", None, "large" if k == "Opmerkingen" else "small")
            for k in STEK_RAPPORT_KOLOMMEN
        ])

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as schrijver:
            rapport_stek.to_excel(schrijver, index=False, sheet_name=f"Week {stek_week}")
        leverancier_email = get_instelling("stek_leverancier_email", "")
        leverancier_cc = get_instelling("stek_leverancier_cc", "")
        # Onderwerp zoals de leverancier het gewend is: rasnaam + weeknummer.
        _rassen_week = [r for r in dict.fromkeys(bewerkt_stek["Plant"]) if _leeg_naar_none(r)]
        ras_onderwerp = _rassen_week[0] if _rassen_week else STEK_STANDAARD_RAS
        onderwerp_stek = f"{ras_onderwerp} week {stek_week}"
        totaal_geplant = sum(v for v in bewerkt_stek["Te poten"] if pd.notna(v))
        mailhtml_stek = _stek_mailhtml(rapport_stek, totaal_geplant)

        col_kopie, col_mail, col_excel = st.columns([2, 2, 2])
        with col_kopie:
            kopieerknop(mailhtml_stek, "📋 Kopieer de tabel")
        col_mail.link_button(
            "✉️ Mail opstellen",
            f"mailto:{urllib.parse.quote(leverancier_email)}"
            f"?cc={urllib.parse.quote(leverancier_cc)}"
            f"&subject={urllib.parse.quote(onderwerp_stek)}",
        )
        col_excel.download_button(
            "⬇️ Excel", excel_buffer.getvalue(),
            file_name=f"Stekresultaten week {stek_week:02d}-{stek_jaar}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="stek_download",
        )
        st.caption(
            f"Kopieer de tabel, open de mail — onderwerp *{onderwerp_stek}*, ontvangers staan klaar — "
            "en plak hem boven je handtekening. Totaal geplant: "
            f"{_stek_getal(totaal_geplant)}."
        )
        if niet_opgeslagen:
            st.caption("Let op: het rapport toont ook wat nog niet is opgeslagen.")
        with st.expander("⚙️ Ontvangers van de mail"):
            nieuw_email = st.text_input(
                "Aan (meerdere adressen scheiden met een komma)", value=leverancier_email,
                key="stek_email_invoer",
            )
            nieuw_cc = st.text_input("CC", value=leverancier_cc, key="stek_cc_invoer")
            if st.button("Opslaan", key="stek_email_opslaan"):
                if nieuw_email.strip() != leverancier_email:
                    set_instelling("stek_leverancier_email", nieuw_email.strip() or None,
                                   gebruiker=huidige_gebruiker())
                if nieuw_cc.strip() != leverancier_cc:
                    set_instelling("stek_leverancier_cc", nieuw_cc.strip() or None,
                                   gebruiker=huidige_gebruiker())
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
                help="Rapport Energie-export uit Priva, voor de tuin die bovenin gekozen is. Warmte: tuin 3 "
                     "Pulsteller 2 (GJ), tuin 1 de warmtewisselaar (kWh, omgerekend). Gas: Pulsteller 1 (m³).",
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

                # De automatische taak kan stilvallen zonder dat iemand het ziet;
                # Priva bewaart maar vijf dagen, dus dat moet snel opvallen.
                laatste_priva = laatste_priva_ophaling()
                if laatste_priva is None:
                    st.warning("De automatische Priva-taak heeft nog nooit gedraaid.")
                else:
                    uren_geleden = (
                        datetime.now(laatste_priva.tzinfo) - laatste_priva
                    ).total_seconds() / 3600
                    wanneer = f"{format_datum(laatste_priva.date())} om {laatste_priva:%H:%M}"
                    if uren_geleden > 36:
                        st.warning(
                            f"⚠️ Laatste automatische ophaling: {wanneer}, "
                            f"{fmt_getal(uren_geleden / 24)} dagen geleden. Priva bewaart 5 dagen, "
                            "dus controleer de taak voordat er een gat ontstaat."
                        )
                    else:
                        st.caption(f"Laatste automatische ophaling: {wanneer}.")
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
        alle_afdelingen = sorteer_afdelingen([r[0] for r in dekking], TUIN_NUMMER)
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
            for afdeling in sorteer_afdelingen(gekozen_afdelingen, TUIN_NUMMER):
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
                )
                df_warmte_dag["Hoofdwarmte (GJ)"] = df_warmte_dag["warmte_mj_totaal"] / 1000
                df_warmte_dag["Gasketel (GJ)"] = df_warmte_dag["gas_mj_totaal"] / 1000
                df_warmte_dag["datum"] = pd.to_datetime(df_warmte_dag["datum"])

                # Een dag zonder meting van een bron blijft leeg (geen staafdeel),
                # niet 0: 0 zou betekenen dat er die dag niet gestookt is.
                df_warmte_lang = df_warmte_dag.melt(
                    id_vars="datum", value_vars=["Hoofdwarmte (GJ)", "Gasketel (GJ)"],
                    var_name="Bron", value_name="GJ",
                ).dropna(subset=["GJ"])
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
            f"{fmt_getal(oppervlakte_van_tuin(TUIN_ID), 0, 'm²')}."
        )
        gas_dekking = get_gasdata_dekking()
        if gas_dekking:
            g_eerste, g_laatste, g_aantal = gas_dekking
            st.caption(
                f"Gasketel (bijstook, Pulsteller 1) geregistreerd van {format_datum(g_eerste)} t/m "
                f"{format_datum(g_laatste)} ({g_aantal} dagen), omgerekend met "
                f"{fmt_kort(GAS_CALORISCHE_WAARDE_MJ_PER_M3, 2)} MJ/m³."
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
            _volgorde_dekking = {a: i for i, a in enumerate(sorteer_afdelingen([r[0] for r in dekking], TUIN_NUMMER))}
            for afdeling, eerste, laatste, aantal, ontbrekend in sorted(dekking, key=lambda r: _volgorde_dekking[r[0]]):
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
                {"label": "Gemiddeld", "waarde": fmt_dagen(gemiddeld)},
                {"label": "Kortst", "waarde": fmt_dagen(minimum)},
                {"label": "Langst", "waarde": fmt_dagen(maximum)},
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

        # Beide tuinen ophalen: het seizoensnormaal van een tuin met weinig
        # teelten rond een plantweek valt terug op beide tuinen samen. De
        # analyse zelf gaat over de gekozen tuin.
        analyse_rijen = []
        for _tuin in TUINEN:
            for k in get_teeltkengetallen(_tuin["id"]):
                if not k["datum_oogst"]:
                    continue
                laag, hoog = rijpheid_tekst_naar_bereik(k["rijpheid"]) if k["rijpheid"] else (None, None)
                analyse_rijen.append({
                    "tuin_id": _tuin["id"],
                    "plantweek": k["plantweek"],
                    "Temperatuur (°C)": k["gem_temperatuur"],
                    "Lichtsom (per dag)": (
                        k["lichtsom"] / k["klimaatdagen"] if k["lichtsom"] and k["klimaatdagen"] else None
                    ),
                    "Water (l/m²)": k["liters"],
                    "Teeltduur (dagen)": k["teeltduur"],
                    "Lengte (cm)": k["lengte_eind"],
                    "Gewicht (g)": k["oogstgewicht"],
                    "Rijpheid": (laag + hoog) / 2 if laag is not None else None,
                })
        kolommen_analyse = list(ANALYSE_VARIABELEN)
        df_alle = pd.DataFrame(analyse_rijen)
        if not df_alle.empty:
            df_alle[kolommen_analyse] = df_alle[kolommen_analyse].apply(pd.to_numeric, errors="coerce")
        df_tuin = df_alle[df_alle["tuin_id"] == TUIN_ID] if not df_alle.empty else df_alle

        if len(df_tuin) < ANALYSE_MIN_N:
            st.info(f"Nog te weinig afgeronde teelten voor een zinvolle analyse (minimaal {ANALYSE_MIN_N} nodig).")
        else:
            seizoen_eruit = st.toggle(
                "Seizoenseffect eruit halen", value=True, key="stats_seizoen",
                help="Vergelijkt elke teelt met teelten uit dezelfde tijd van het jaar (plantweek ±2), "
                     "zodat winter tegen zomer niet de verbanden bepaalt.",
            )
            if seizoen_eruit:
                df_analyse = seizoensafwijking(df_alle, kolommen_analyse)
                df_analyse = df_analyse[df_analyse["tuin_id"] == TUIN_ID][kolommen_analyse]
                st.caption(
                    "Per teelt is elke waarde vergeleken met het normaal voor die tijd van het jaar: het "
                    "gemiddelde van de andere teelten met een plantweek binnen 2 weken (alle jaren, eigen "
                    f"tuin; zijn dat er minder dan {SEIZOEN_MIN_BUREN}, dan beide tuinen samen). De verbanden "
                    "hieronder gaan over die afwijkingen: wat er binnen een seizoen gebeurt."
                )
            else:
                df_analyse = df_tuin[kolommen_analyse]
                st.caption(
                    "Ruwe waarden: de verbanden zijn grotendeels het seizoen (winterteelten zijn kouder, "
                    "donkerder en duren langer)."
                )

            corr = df_analyse.corr(min_periods=5)
            aanwezig = df_analyse.notna().astype(int)
            n_paren = aanwezig.T @ aanwezig

            corr_lang = (
                corr.reset_index().melt(id_vars="index", var_name="Variabele 2", value_name="r")
                .rename(columns={"index": "Variabele 1"})
            )
            corr_lang["n"] = [int(n_paren.loc[a, b]) for a, b in zip(corr_lang["Variabele 1"], corr_lang["Variabele 2"])]
            corr_lang = corr_lang.dropna(subset=["r"])
            genoeg = f"datum.n >= {ANALYSE_MIN_N}"
            heatmap = alt.Chart(corr_lang).mark_rect().encode(
                x=alt.X("Variabele 1:N", title=None, sort=kolommen_analyse),
                y=alt.Y("Variabele 2:N", title=None, sort=kolommen_analyse),
                color=alt.condition(
                    genoeg,
                    alt.Color("r:Q", title="Correlatie", scale=alt.Scale(scheme="redblue", domain=[-1, 1])),
                    alt.value("#e3e3e3"),
                ),
                tooltip=["Variabele 1:N", "Variabele 2:N", alt.Tooltip("r:Q", format=".2f"), "n:Q"],
            )
            # Tekstkleur: wit op een donker vakje, grijs als n te klein is.
            corr_lang["tekstkleur"] = [
                "#9a9a9a" if n < ANALYSE_MIN_N else "white" if abs(r) > 0.5 else "black"
                for r, n in zip(corr_lang["r"], corr_lang["n"])
            ]
            tekst = alt.Chart(corr_lang).mark_text(fontSize=11).encode(
                x=alt.X("Variabele 1:N", sort=kolommen_analyse),
                y=alt.Y("Variabele 2:N", sort=kolommen_analyse),
                text=alt.Text("r:Q", format=".2f"),
                color=alt.Color("tekstkleur:N", scale=None),
            )
            # Eigen kleurschaal per laag: de tekstkleur is een vaste kleur per
            # vakje en hoort niet in de correlatieschaal van de vakjes.
            st.altair_chart(
                (heatmap + tekst).resolve_scale(color="independent").properties(height=340),
                use_container_width=True,
            )
            st.caption(
                f"Gebaseerd op {len(df_analyse)} afgeronde teelten van {TUIN_NAAM}. Grijze vakjes: minder dan "
                f"{ANALYSE_MIN_N} teelten met beide waarden, te weinig om iets over te zeggen. "
                "Beweeg over een vakje voor r en n."
            )

            paren = []
            for i, kol_a in enumerate(kolommen_analyse):
                for kol_b in kolommen_analyse[i + 1:]:
                    r = corr.loc[kol_a, kol_b]
                    n = int(n_paren.loc[kol_a, kol_b])
                    if pd.notna(r) and n >= ANALYSE_MIN_N:
                        paren.append((abs(r), r, kol_a, kol_b, n))
            paren.sort(key=lambda p: p[0], reverse=True)
            te_klein = sum(
                1 for i, a in enumerate(kolommen_analyse) for b in kolommen_analyse[i + 1:]
                if pd.notna(corr.loc[a, b]) and int(n_paren.loc[a, b]) < ANALYSE_MIN_N
            )

            if paren:
                st.write("**Sterkste samenhangen:**")
                for abs_r, r, kol_a, kol_b, n in paren[:3]:
                    df_paar = df_analyse[[kol_a, kol_b]].dropna()
                    helling = r * df_paar[kol_b].std() / df_paar[kol_a].std() if df_paar[kol_a].std() else 0
                    sterkte = "sterk" if abs_r > 0.7 else "matig" if abs_r > 0.4 else "zwak"
                    st.write(f"- {verband_zin(kol_a, kol_b, helling, r, n, seizoen_eruit)} {sterkte.capitalize()} verband.")
                    as_titel = (lambda kol: f"{kol} t.o.v. normaal") if seizoen_eruit else (lambda kol: kol)
                    scatter = alt.Chart(df_paar).mark_circle(size=60, opacity=0.6).encode(
                        x=alt.X(f"{kol_a}:Q", title=as_titel(kol_a), scale=alt.Scale(zero=False)),
                        y=alt.Y(f"{kol_b}:Q", title=as_titel(kol_b), scale=alt.Scale(zero=False)),
                        tooltip=[alt.Tooltip(f"{kol_a}:Q", format=".1f"), alt.Tooltip(f"{kol_b}:Q", format=".1f")],
                    )
                    trend = scatter.transform_regression(kol_a, kol_b).mark_line(color="#c0392b")
                    st.altair_chart((scatter + trend).properties(height=220), use_container_width=True)

                st.caption(
                    (f"{te_klein} paren met minder dan {ANALYSE_MIN_N} teelten zijn weggelaten. " if te_klein else "")
                    + "Een verband kan ook toeval zijn: gebruik dit als richting om op te letten, niet als "
                    "bewijs, en correlatie is geen oorzakelijk verband."
                )
            else:
                st.caption(f"Geen paren met minstens {ANALYSE_MIN_N} teelten met beide waarden.")
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

    **Tuinvergelijking**
    - Tabblad ⚖️ Tuinvergelijking: wat er in een week (of maand, kwartaal, jaar) in de kas gebeurde,
      tuin 1 naast tuin 3 en het totaal, alles per m². De kleine regel onder een getal is het
      verschil met de vorige periode of dezelfde periode vorig jaar.

    **Teeltvergelijking**
    - Tabblad 🌿 Teeltvergelijking: alle plantingen uit één plantweek, bovenaan per tuin
      samengevat en daaronder de teelten naast elkaar. Klik op een teelt voor klimaat, water,
      groei en stek.

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

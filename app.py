import html
import io
import time
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
    get_klimaatdata_dagen_voor_periode,
    get_klimaatdata_dekking,
    laatste_priva_ophaling,
    importeer_watergift_uit_priva,
    get_watergift_dekking,
    get_watergift_dagen_voor_periode,
    verwerk_energie_csv,
    GAS_CALORISCHE_WAARDE_MJ_PER_M3,
    get_vakgegevens,
    ideale_etmaaltemperatuur,
    LICHT_TEMP_FACTOR,
    LICHT_TEMP_BASIS,
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
    get_rassen,
    zet_ras,
    get_tuinen,
    get_tuin_id,
    get_vaknummers,
    get_standaard_tuin_van_gebruiker,
    zet_actieve_tuin,
    STANDAARD_RAS,
    get_stek_voor_week,
    sla_stekbeoordeling_op,
    stek_uitval_pct,
    verdeel_bakjes,
    STEK_KEUZES,
    STEK_STANDAARD_RAS,
    get_vakstatus_data,
    get_teelthistorie_data,
    schrijf_prognose_log,
    get_prognose_log,
    get_oogst_emmers,
    voeg_opmerking_toe,
    get_opmerkingen,
    get_alle_opmerkingen,
    wijzig_opmerking,
    verwijder_opmerking,
    get_vergelijking_data,
    get_teeltvergelijking_data,
    warmte_per_bezette_m2,
    vakstatus_dataversie,
)
from logic import vakstatus as vs
from logic import kengetallen as kg
from logic import perioden
from logic import planning_editor
from logic import prognoselog
from logic import opmerkingen as opm_logic
from logic import selectie
from logic import tuinvergelijking as tuinvgl
from logic import teeltvergelijking as teeltvgl
from logic import teeltprognose as tp
from logic.afdelingen import sorteer_afdelingen
from logic.lichtlijn import formule_tekst, t_ideaal
from ui import styles, vergelijkingstabel
from ui.vergelijkingstabel import Kengetal, verloop_frame
from config import (
    AFDELING_VOLGORDE, AFWIJKING_VENSTER_DAGEN, C_GRENZEN, FLORGIB_ACHTERSTAND_DAGEN,
    OP_KOERS_MARGE, OPMERKING_CATEGORIEEN, APP_VERSIE,
)

# --- PAGINA-INSTELLINGEN ---
# Moet de eerste Streamlit-aanroep zijn. Bepaalt o.a. de titel van het
# browsertabblad.
st.set_page_config(page_title="VEM teeltregistratie", page_icon="🌱", layout="wide")
_VEM_T0 = time.perf_counter()  # laadtijd meten (zie het einde van dit bestand)

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
/* Afdelingsnaam links van een rij: een knop die het stookadvies opent. */
[class*="st-key-nu_afdknop_"] button {
    min-height: 0; padding: 0.3rem 0 0; justify-content: flex-start; text-decoration: underline dotted;
}
[class*="st-key-nu_afdknop_"] button p { font-size: 0.72rem; font-weight: 600; opacity: 0.75; }
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
/* Minder witruimte tussen de afdelingsrijen dan tussen gewone elementen. */
[class*="st-key-nu_rij_"] { margin-top: -0.6rem; }
/* Telefoon: afdelingslabel boven de vakken in plaats van ernaast. */
@media (max-width: 700px) {
    [class*="st-key-nu_rij_"] { grid-template-columns: minmax(0, 1fr); margin-top: 0.5rem; }
}

/* Kop: naam van de app en het bedrijf links, week, datum en versie rechts. */
.vem-kop {
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    margin: 0 0 0.6rem 0; padding: 0.9rem 1.3rem; border-radius: 12px;
    background: linear-gradient(100deg, #2E6A4C 0%, #3d8761 100%); color: #fff;
}
.vem-merk { display: flex; flex-direction: column; line-height: 1.2; }
.vem-titel { font-size: 1.45rem; font-weight: 700; letter-spacing: 0.01em; }
.vem-bedrijf { font-size: 0.9rem; opacity: 0.85; }
.vem-meta { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.35; white-space: nowrap; }
.vem-week { font-size: 0.9rem; font-weight: 600; }
.vem-versie { font-size: 0.75rem; opacity: 0.75; }
@media (max-width: 700px) { .vem-titel { font-size: 1.15rem; } .vem-kop { padding: 0.7rem 0.9rem; } }

/* Navigatiebalk onder de kop: knoppen per pagina, de huidige gevuld groen. */
.st-key-vem_nav {
    gap: 0.3rem; flex-wrap: wrap; margin-bottom: 0.4rem; padding-bottom: 0.45rem;
    border-bottom: 2px solid rgba(46, 106, 76, 0.25);
}
.st-key-vem_nav [data-testid="stPageLink"] a {
    padding: 0.3rem 0.95rem; border-radius: 999px; border: 1px solid rgba(46, 106, 76, 0.35);
    background: transparent;
}
.st-key-vem_nav [data-testid="stPageLink"] a:hover { background: rgba(46, 106, 76, 0.10); }
.st-key-vem_nav_actief [data-testid="stPageLink"] a { background: #2E6A4C; border-color: #2E6A4C; }
.st-key-vem_nav_actief [data-testid="stPageLink"] a,
.st-key-vem_nav_actief [data-testid="stPageLink"] a * { color: #fff !important; }

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


def toon_tabel(df, kolommen, verberg_leeg=False, pin_eerste=False, vast=(), sleutel=None):
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
    - pin_eerste: eerste kolom blijft staan bij zijwaarts scrollen; vast: deze
      kolommen blijven staan;
    - sleutel: de tabel is klikbaar (één regel kiezen); geeft dan de keuze
      van st.dataframe terug.
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
    for kolom in vast:
        if kolom in config:
            config[kolom]["pinned"] = True
    if sleutel:
        return st.dataframe(df[volgorde], hide_index=True, column_config=config, on_select="rerun",
                            selection_mode="single-row", key=sleutel)
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
        st.caption("Geen vakken of concepten in deze periode.")
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
                alt.Tooltip("label:N", title="Vak"),
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


# De pagina's (zie NAVIGATIE onderaan): (naam van de functie, titel, adres, standaard).
PAGINA_DEFINITIES = [
    ("pagina_planning", "Planning", "planning", False),
    ("pagina_stek", "Stek", "stek", False),
    ("pagina_teeltoverzicht", "Teeltoverzicht", "teeltoverzicht", True),
    ("pagina_teeltvergelijking", "Teeltvergelijking", "teeltvergelijking", False),
    ("pagina_tuinvergelijking", "Tuin vergelijking", "tuinvergelijking", False),
    ("pagina_opmerkingen", "Opmerkingen", "opmerkingen", False),
    ("pagina_meer", "Meer", "meer", False),
]


def _paginas():
    """st.Page-objecten; de paginafuncties zelf worden pas bij het draaien opgezocht (ze staan onderaan)."""
    def pagina(naam):
        def draai():
            globals()[naam]()
        draai.__name__ = naam
        return draai
    return [st.Page(pagina(naam), title=titel, url_path=adres, default=standaard)
            for naam, titel, adres, standaard in PAGINA_DEFINITIES]


# Al vóór het inloggen (verborgen) aan st.navigation geven: het cookie-onderdeel
# van de inlogmodule start in de eerste run een herhaalde run, en die weet de
# gevraagde pagina (link of bladwijzer, bijv. /planning) alleen als de
# navigatie dan al bekend is. Anders kom je op de standaardpagina uit.
st.navigation(_paginas(), position="hidden")

_DAGEN_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]
_vandaag_kop = date.today()
st.markdown(
    '<div class="vem-kop">'
    '<div class="vem-merk"><span class="vem-titel">Teeltregistratie</span>'
    '<span class="vem-bedrijf">Van Egmond Matricaria</span></div>'
    '<div class="vem-meta">'
    f'<span class="vem-week">Week {_vandaag_kop.isocalendar()[1]} · '
    f'{_DAGEN_KORT[_vandaag_kop.weekday()]} {format_datum(_vandaag_kop)}</span>'
    f'<span class="vem-versie">versie {APP_VERSIE}</span>'
    '</div></div>',
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

# Vanaf hier is de gebruiker ingelogd. De navigatie staat vóór alles wat een
# st.rerun() kan geven (tuinkeuze, zijbalk): een herhaalde run onthoudt dan de
# gekozen pagina. Uitgevoerd wordt de pagina pas onderaan (_pagina.run()).
# Het menu van Streamlit zelf blijft verborgen; de knoppen staan in een eigen
# balk onder de kop, met de huidige pagina gevuld.
_pagina_lijst = _paginas()
_pagina = st.navigation(_pagina_lijst, position="hidden")
with st.container(horizontal=True, key="vem_nav"):
    for _p in _pagina_lijst:
        with st.container(width="content", key="vem_nav_actief" if _p.title == _pagina.title
                          else f"vem_nav_{_p.url_path or 'start'}"):
            st.page_link(_p, label=_p.title)
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
# "Beide" toont in Teeltoverzicht de twee tuinen onder elkaar. Wat per tuin
# werkt (registratie in de zijbalk, Planning, Stek, import) volgt dan de
# werk-tuin, die je in de zijbalk kiest.
if "tuin_weergave" not in st.session_state:
    st.session_state["tuin_weergave"] = st.session_state["tuin_nummer"]
if len(_tuin_nummers) > 1:
    _keuze = st.segmented_control(
        "Tuin", _tuin_nummers + ["beide"], label_visibility="collapsed", key="tuin_keuze",
        format_func=lambda n: "Beide" if n == "beide" else _tuin_labels.get(n, f"Tuin {n}"),
        default=st.session_state["tuin_weergave"], width="content",
    )
    if _keuze:
        st.session_state["tuin_weergave"] = _keuze
        if _keuze != "beide":
            st.session_state["tuin_nummer"] = _keuze
TUIN_WEERGAVE = st.session_state["tuin_weergave"]
if TUIN_WEERGAVE == "beide":
    _werk = st.sidebar.segmented_control(
        "Werk-tuin (registratie, Planning, Stek, import)", _tuin_nummers, key="werk_tuin",
        format_func=lambda n: _tuin_labels.get(n, f"Tuin {n}"), default=st.session_state["tuin_nummer"],
    )
    if _werk:
        st.session_state["tuin_nummer"] = _werk

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

FLORGIB, OOGST, OPMERKING, WIJZIGEN = "Florgib lengte", "Oogst", "Opmerking", "Wijzigen of verwijderen"
WIJZIG_ONDERDELEN = ["Startdatum en planten", "Florgib", "Oogst", "Opmerkingen"]
actie = st.sidebar.radio("Wat wil je doen?", [FLORGIB, OOGST, OPMERKING, WIJZIGEN])

# Elke actie krijgt een eigen plek in de zijbalk; de plekken van de andere twee
# blijven leeg. Streamlit ruimt namelijk alleen op wat het opnieuw tekent: zonder
# die vaste plekken bleven de velden van de vorige keuze er grijs onder staan.
_paneel = {naam: st.sidebar.empty() for naam in (FLORGIB, OOGST, OPMERKING, WIJZIGEN)}
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
                    "Vakken", list(keuzes.keys())
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
                            f"Opgeslagen voor {len(successen)} vakken."
                        )
                    if fouten:
                        st.warning("Mislukt:\n" + "\n".join(fouten))
                
                    if successen:
                        st.rerun()
                elif submit_half and not geselecteerde_labels:
                    st.warning("Kies minstens één vak.")
        else:
            st.info("Alle lopende vakken hebben hun Florgib-lengte al.")

    # --- ACTIE 3: UITVAL (EMMERS) + OOGSTGEWICHT EN LENGTE ---
    elif actie == OOGST:

        tab_uitval, tab_eind = st.tabs(["🪣 Emmers", "📏 Lengte en gewicht"])

        # --- TABBLAD: UITVAL (EMMERS, 100 STELEN PER EMMER) ---
        with tab_uitval:
            lopende_uitval = get_lopende_teelten()

            if lopende_uitval:
                keuzes_uitval = {label: teelt_id for teelt_id, label in lopende_uitval}

                uitval_label = st.selectbox(
                    "Vak", list(keuzes_uitval.keys()), key="uitval_selectie"
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
                        "Vak afronden",
                        key=f"emmers_laatste_{st.session_state['emmers_form_versie']}",
                    )

                    submit_emmers = st.form_submit_button("Opslaan")

                    if submit_emmers:
                        if aantal_emmers > 0:
                            voeg_oogstregistratie_toe(uitval_id, datum_emmers, aantal_emmers, gebruiker=huidige_gebruiker())
                            if laatste_emmers:
                                markeer_teelt_afgerond(uitval_id, datum_emmers, gebruiker=huidige_gebruiker())
                                st.success(f"{aantal_emmers} emmers opgeslagen, vak afgerond.")
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
                st.info("Geen lopende vakken. Start ze in het tabblad Planning.")

        # --- TABBLAD: OOGSTGEWICHT EN LENGTE ---
        with tab_eind:
            # Alleen teelten die nog niet zijn afgerond bij de uitval.
            alle_teelten = get_lopende_teelten()

            if alle_teelten:
                keuzes_eind = {label: teelt_id for teelt_id, label in alle_teelten}

                with st.form("oogst_form"):
                    geselecteerde_labels = st.multiselect(
                        "Vakken", list(keuzes_eind.keys())
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
                            st.success(f"Opgeslagen voor {len(successen)} vakken.")
                        if fouten:
                            st.warning("Mislukt:\n" + "\n".join(fouten))
                        if successen:
                            st.rerun()
                    elif submit_oogst and not geselecteerde_labels:
                        st.warning("Kies minstens één vak.")
            else:
                st.info("Geen lopende vakken.")

    # --- ACTIE 4: WIJZIGEN / VERWIJDEREN ---
    elif actie == OPMERKING:
        # Een opmerking bij één of meer lopende vakken, bijv. een afwijking in de
        # groei. Terug te zien (en te wijzigen) in de vakpopup.
        lopende_opm = get_lopende_teelten()
        if not lopende_opm:
            st.info("Geen lopende vakken.")
        else:
            keuzes_opm = {label: teelt_id for teelt_id, label in lopende_opm}
            if st.session_state.get("opmerking_melding"):
                st.success(st.session_state.pop("opmerking_melding"))
            # Nieuwe sleutel na elke opslag: dan is het formulier weer leeg, maar
            # bij een waarschuwing blijft de getypte tekst staan.
            with st.form(f"opmerking_form_{st.session_state.get('opmerking_versie', 0)}"):
                labels_opm = st.multiselect("Vakken", list(keuzes_opm))
                datum_opm = st.date_input("Datum", format="DD-MM-YYYY")
                categorie_opm = st.selectbox("Categorie", OPMERKING_CATEGORIEEN)
                tekst_opm = st.text_area("Opmerking", placeholder="Bijv. vak 12 blijft achter in lengte, bladpunten geel")
                if st.form_submit_button("Opslaan"):
                    if not labels_opm:
                        st.warning("Kies minstens één vak.")
                    elif not tekst_opm.strip():
                        st.warning("Schrijf een opmerking.")
                    else:
                        voeg_opmerking_toe([keuzes_opm[l] for l in labels_opm], datum_opm, categorie_opm,
                                           tekst_opm.strip(), gebruiker=huidige_gebruiker())
                        st.session_state["opmerking_melding"] = (
                            f"Opmerking opgeslagen bij {len(labels_opm)} {'vak' if len(labels_opm) == 1 else 'vakken'}.")
                        st.session_state["opmerking_versie"] = st.session_state.get("opmerking_versie", 0) + 1
                        st.rerun()

    elif actie == WIJZIGEN:

        alle_teelten = get_alle_teelten_voor_selectie()

        if alle_teelten:
            # Kiezen met drie losse velden (week → vak → jaar) in plaats van één
            # lange lijst; elk veld toont alleen wat bij de eerdere keuze bestaat.
            # Weken in de tijd (recentste onderaan); standaard de week van de
            # laatst gestarte teelt, en bij een week het meest recente jaar.
            k_week, k_vak, k_jaar = st.columns([1, 1, 1.3])
            weken_alle = selectie.weken(alle_teelten)
            recent = selectie.laatste(alle_teelten)
            week_keuze = k_week.selectbox("Week", weken_alle, index=weken_alle.index(recent["week"]),
                                          key="wijzig_week")
            vakken_week = selectie.vakken(alle_teelten, week=week_keuze)
            vak_keuze = k_vak.selectbox("Vak", vakken_week, key=f"wijzig_vak_{week_keuze}")
            jaren_vak = selectie.jaren(alle_teelten, week_keuze, vak=vak_keuze)
            jaar_keuze = k_jaar.selectbox("Jaar", jaren_vak, index=len(jaren_vak) - 1,
                                          key=f"wijzig_jaar_{week_keuze}_{vak_keuze}")
            passend = selectie.gekozen(alle_teelten, vak=vak_keuze, week=week_keuze, jaar=jaar_keuze)
            if len(passend) > 1:   # zelden: twee teelten in één vak in dezelfde week
                passend = [st.selectbox("Code", passend, format_func=lambda t: t["code"] or f"ID{t['id']}",
                                        key=f"wijzig_dubbel_{week_keuze}_{vak_keuze}_{jaar_keuze}")]
            geselecteerd_id = passend[0]["id"]
            huidige = get_teelt_by_id(geselecteerd_id)
            st.caption(f"Vak {huidige['vaknummer']} · {huidige['code'] or '-'} · "
                       f"{'afgerond' if huidige['datum_oogst'] else 'lopend'}")

            def naar_date(waarde):
                """String-datum uit de database naar een date voor de invoervelden."""
                if waarde:
                    return datetime.strptime(waarde, "%Y-%m-%d").date()
                return None

            def bewaar(**nieuw):
                """Eén onderdeel wijzigen; de overige velden van de teelt blijven zoals ze waren."""
                w = {"start": huidige["datum_teelt_start"], "datum_half": huidige["datum_half"],
                     "lengte_half": huidige["lengte_half"], "florgib_gram": huidige["florgib_gram"],
                     "datum_oogst": huidige["datum_oogst"], "lengte_eind": huidige["lengte_eind"],
                     "gewicht": huidige["oogstgewicht"], "rijpheid": huidige["rijpheid"],
                     "planten": huidige["aantal_planten"]}
                w.update(nieuw)
                update_teelt_volledig(
                    geselecteerd_id, w["start"], w["datum_half"], w["lengte_half"], w["datum_oogst"],
                    w["lengte_eind"], w["gewicht"], w["rijpheid"], w["planten"], huidige["vaknummer"],
                    gebruiker=huidige_gebruiker(), florgib_gram=w["florgib_gram"])

            onderdeel = st.selectbox("Wat wil je wijzigen?", WIJZIG_ONDERDELEN, key="wijzig_onderdeel")

            if onderdeel == "Startdatum en planten":
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
                with st.form(f"wijzig_start_{geselecteerd_id}"):
                    nieuwe_start = st.date_input(
                        "Startdatum", value=naar_date(huidige["datum_teelt_start"]) or date.today(),
                        format="DD-MM-YYYY")
                    nieuw_aantal_planten = st.number_input(
                        "Planten", min_value=0, step=1,
                        value=int(huidige["aantal_planten"]) if huidige["aantal_planten"] else 0)
                    if st.form_submit_button("Opslaan"):
                        bewaar(start=nieuwe_start, planten=nieuw_aantal_planten or None)
                        if gekozen_ras and gekozen_ras != huidig_ras:
                            zet_ras(geselecteerd_id, gekozen_ras, gebruiker=huidige_gebruiker())
                        st.success("Opgeslagen.")
                        st.rerun()

            elif onderdeel == "Florgib":
                with st.form(f"wijzig_florgib_{geselecteerd_id}"):
                    half_ingevuld = st.checkbox("Florgib bekend", value=huidige["datum_half"] is not None)
                    nieuwe_datum_half = st.date_input(
                        "Datum Florgib", value=naar_date(huidige["datum_half"]) or date.today(),
                        format="DD-MM-YYYY")
                    nieuwe_lengte_half = st.number_input(
                        "Florgib lengte (cm)", min_value=0.0, format="%.1f",
                        value=float(huidige["lengte_half"]) if huidige["lengte_half"] else 0.0)
                    nieuw_florgib_gram = st.number_input(
                        "Florgib (g) per vak", min_value=0.0, step=0.5, format="%.1f",
                        value=float(huidige["florgib_gram"]) if huidige["florgib_gram"] else 0.0)
                    st.caption("Vink 'Florgib bekend' uit om de Florgib te wissen.")
                    if st.form_submit_button("Opslaan"):
                        bewaar(datum_half=nieuwe_datum_half if half_ingevuld else None,
                               lengte_half=nieuwe_lengte_half if half_ingevuld else None,
                               florgib_gram=(nieuw_florgib_gram or None) if half_ingevuld else None)
                        st.success("Opgeslagen.")
                        st.rerun()

            elif onderdeel == "Oogst":
                with st.form(f"wijzig_oogst_{geselecteerd_id}"):
                    oogst_ingevuld = st.checkbox("Oogst bekend (vak afgerond)",
                                                 value=huidige["datum_oogst"] is not None)
                    nieuwe_datum_oogst = st.date_input(
                        "Oogstdatum", value=naar_date(huidige["datum_oogst"]) or date.today(),
                        format="DD-MM-YYYY")
                    nieuwe_lengte_eind = st.number_input(
                        "Oogstlengte (cm)", min_value=0.0, format="%.1f",
                        value=float(huidige["lengte_eind"]) if huidige["lengte_eind"] else 0.0)
                    nieuw_gewicht = st.number_input(
                        "Oogstgewicht (g)", min_value=0, step=1,
                        value=int(round(huidige["oogstgewicht"])) if huidige["oogstgewicht"] else 0)
                    nieuwe_rijpheid_bereik = st.select_slider(
                        "Rijpheid", options=RIJPHEID_OPTIES,
                        value=rijpheid_tekst_naar_bereik(huidige["rijpheid"]), help="1 = rauw, 4 = rijp.")
                    st.caption("Vink 'Oogst bekend' uit om het vak weer als lopend te zetten.")
                    if st.form_submit_button("Opslaan"):
                        bewaar(datum_oogst=nieuwe_datum_oogst if oogst_ingevuld else None,
                               lengte_eind=nieuwe_lengte_eind if oogst_ingevuld else None,
                               gewicht=nieuw_gewicht if oogst_ingevuld else None,
                               rijpheid=rijpheid_bereik_naar_tekst(nieuwe_rijpheid_bereik) if oogst_ingevuld
                               else None)
                        st.success("Opgeslagen.")
                        st.rerun()
                # Oogstregistraties (emmers) staan hier ook, zodat je ze ook voor
                # een afgeronde teelt nog kunt corrigeren.
                st.caption("Oogstmomenten")
                toon_oogstregistraties_beheer(geselecteerd_id, huidige)

            elif onderdeel == "Opmerkingen":
                opmerkingen_vak = {o["id"]: o for o in get_opmerkingen(geselecteerd_id)}
                if not opmerkingen_vak:
                    st.caption("Nog geen opmerkingen bij dit vak. Maak er een via Opmerking hierboven.")
                else:
                    opm_id = st.selectbox(
                        "Opmerking", list(opmerkingen_vak), key=f"wijzig_opm_{geselecteerd_id}",
                        format_func=lambda i: f"{format_datum(opmerkingen_vak[i]['datum'])} · "
                                              f"{opmerkingen_vak[i]['categorie'] or 'Overig'} · "
                                              f"{opmerkingen_vak[i]['tekst'][:30]}")
                    o = opmerkingen_vak[opm_id]
                    with st.form(f"wijzig_opm_form_{opm_id}"):
                        opm_datum = st.date_input("Datum", vs.als_datum(o["datum"]), format="DD-MM-YYYY")
                        opm_categorie = st.selectbox(
                            "Categorie", OPMERKING_CATEGORIEEN,
                            index=OPMERKING_CATEGORIEEN.index(o["categorie"])
                            if o["categorie"] in OPMERKING_CATEGORIEEN else len(OPMERKING_CATEGORIEEN) - 1)
                        opm_tekst = st.text_area("Opmerking", o["tekst"])
                        opm_weg = st.checkbox("Deze opmerking verwijderen")
                        if st.form_submit_button("Opslaan"):
                            if opm_weg:
                                verwijder_opmerking(opm_id, gebruiker=huidige_gebruiker())
                                st.success("Opmerking verwijderd.")
                                st.rerun()
                            elif not opm_tekst.strip():
                                st.warning("Een opmerking kan niet leeg zijn; vink verwijderen aan om hem weg te halen.")
                            elif (str(opm_datum), opm_categorie, opm_tekst.strip()) != (
                                    str(vs.als_datum(o["datum"])), o["categorie"], o["tekst"]):
                                wijzig_opmerking(opm_id, opm_datum, opm_categorie, opm_tekst.strip(),
                                                 gebruiker=huidige_gebruiker())
                                st.success("Opmerking opgeslagen.")
                                st.rerun()

            # Het hele vak verwijderen staat los van de onderdelen, met expliciete bevestiging.
            st.markdown("---")
            bevestig_verwijderen = st.checkbox(
                "Dit vak (deze teelt) definitief verwijderen",
                key=f"bevestig_verwijderen_{geselecteerd_id}"
            )
            if st.button("🗑️ Verwijderen", disabled=not bevestig_verwijderen):
                delete_teelt(geselecteerd_id, gebruiker=huidige_gebruiker())
                st.success("Verwijderd.")
                st.rerun()
        else:
            st.info("Nog geen registraties.")

# --- HOOFDSCHERM: PAGINA'S ---
#
# Elke pagina is een functie; st.navigation (na het inloggen) kiest er één en
# _pagina.run() onderaan voert alleen die uit. Alles hierboven (login, tuinkeuze, registratie in de
# zijbalk, gedeelde functies en caches) geldt voor alle pagina's.
styles.laad()

# --- NU: hoe staat elk vak ervoor ---
#
# Eén raster per tuin met per vak een klikbaar blok (kleur = status); de
# afdelingsnaam links opent het stookadvies van die afdeling. Het rekenwerk
# staat in logic/vakstatus.py en logic/teeltprognose.py; hier alleen ophalen
# (één keer, gecachet) en tekenen.

# Kleur van een vakblok = de prognose t.o.v. plan in dagen bij de huidige
# stooklijn (logic/teeltprognose.dagen_klasse), schaal −7 … +7: blauw = te
# vroeg, neutraal = op schema, oranje → rood = te laat. De kleuren staan in de
# CSS (.st-key-nu_vak_<klasse>_*) en in de legenda.
NU_KLASSEN = ("b3", "b2", "b1", "n", "o1", "o2", "r1", "r2")
NU_STATUS_KORT = {"b3": "ruim te vroeg", "b2": "te vroeg", "b1": "iets te vroeg", "n": "op schema",
                  "o1": "iets te laat", "o2": "te laat", "r1": "ruim te laat", "r2": "ruim te laat", "rijp": "oogstrijp",
                  "grijs": "geen prognose", "leeg": "leeg"}
_NU_PER_RUN = {}   # één keer rekenen per scriptrun (Teeltoverzicht, Teeltvergelijking en Planning)


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
    historie, weken = get_teelthistorie_data()
    return prognoselog.bouw_model(_nu_data(versie, dag), historie, weken, _plandatum)


def _plandatum(start):
    return bereken_verwachte_oogstdatum(start)[1]


@st.cache_resource
def _prognose_gelogd():
    """Dagen waarop deze server het prognoselogboek al heeft bijgewerkt."""
    return set()


def _prognose_loggen(vandaag, data, model, stook, afwijking):
    """
    Terugval voor de dagelijkse taak (prognose_loggen.py): de eerste run van de
    dag legt de prognose van alle lopende vakken vast. Een vak dat vandaag al
    gelogd is, blijft staan (ON CONFLICT DO NOTHING).
    """
    gelogd = _prognose_gelogd()
    if not model or vandaag in gelogd:
        return
    gelogd.add(vandaag)
    try:
        schrijf_prognose_log(prognoselog.logregels(data["teelten"], stook, afwijking, vandaag,
                                                   prognoselog.modelversie(model)))
    except Exception as fout:  # het logboek mag de app nooit tegenhouden
        gelogd.discard(vandaag)
        print(f"Prognoselogboek niet bijgewerkt: {fout}")


def _nu_alles(vandaag):
    """
    (data, model, stook, afwijking) voor deze run:
    - stook: {teelt_id: TeeltPrognose.beoordeel-uitkomst} voor alle lopende teelten
    - afwijking: {(tuin_id, afdeling): gemiddelde afwijking van de lichtlijn, laatste 14 dagen}
    """
    if "alles" not in _NU_PER_RUN:
        versie = vakstatus_dataversie()
        data, model = _nu_data(versie, str(vandaag)), _nu_model(versie, str(vandaag))
        stook, afwijking = prognoselog.stand_lopende_teelten(
            data["teelten"], tp.klimaat_per_afdeling(data["klimaat"]), model, vandaag, _plandatum)
        _prognose_loggen(vandaag, data, model, stook, afwijking)
        _NU_PER_RUN["alles"] = (data, model, stook, afwijking)
    return _NU_PER_RUN["alles"]


def _nu_uitval(t):
    """Uitval van een teelt in %: uit de emmers, anders het vastgelegde percentage."""
    planten, emmers = vs._getal(t.get("aantal_planten")), vs._getal(t.get("emmers"))
    if planten and emmers:
        return (planten - emmers * 100) / planten * 100
    return vs._getal(t.get("uitval_pct"))


def _nu_tuin(data, model, stook, afwijking, tuin, vandaag):
    """Status en prognose van alle vakken van één tuin en het stookadvies per afdeling."""
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

    return {"tuin": tuin, "vakken": vakken, "statussen": statussen, "gepland": gepland, "advies": advies,
            "laatste_oogst": laatste_oogst, "alle": alle, "model": model}


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
    delen.append(f"{fmt_getal(u['gedaan'] * 100)} % van wat het vak nodig heeft tot de oogst")
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


def pagina_uitleg(tekst):
    """Uitleg bij een pagina als ⓘ; de naam van de pagina staat al in de navigatiebalk."""
    st.caption("Uitleg bij deze pagina", help=tekst)


def toon_opmerkingen(teelt_id):
    """Opmerkingen van één vak in de vakpopup, oud naar nieuw, elk te wijzigen of te verwijderen."""
    opmerkingen = get_opmerkingen(teelt_id)
    st.write(f"**Opmerkingen** ({len(opmerkingen)})" if opmerkingen else "**Opmerkingen**")
    if not opmerkingen:
        st.caption("Nog geen opmerkingen. Voeg er een toe via Opmerking in de zijbalk.")
        return
    for o in opmerkingen:
        with st.container(border=True):
            kop, knop = st.columns([5, 1], vertical_alignment="center")
            kop.caption(f"{format_datum(o['datum'])} · {o['categorie'] or 'Overig'} · {o['gebruiker'] or '-'}"
                        + (" · gewijzigd" if o["gewijzigd_op"] else ""))
            st.write(o["tekst"])
            with knop.popover("Wijzigen"):
                with st.form(f"opm_wijzig_{o['id']}"):
                    datum = st.date_input("Datum", vs.als_datum(o["datum"]), format="DD-MM-YYYY")
                    categorie = st.selectbox(
                        "Categorie", OPMERKING_CATEGORIEEN,
                        index=OPMERKING_CATEGORIEEN.index(o["categorie"]) if o["categorie"] in OPMERKING_CATEGORIEEN
                        else len(OPMERKING_CATEGORIEEN) - 1)
                    tekst = st.text_area("Opmerking", o["tekst"])
                    weg = st.checkbox("Deze opmerking verwijderen")
                    if st.form_submit_button("Opslaan"):
                        if weg:
                            verwijder_opmerking(o["id"], gebruiker=huidige_gebruiker())
                        elif tekst.strip() and (str(datum), categorie, tekst.strip()) != (
                                str(vs.als_datum(o["datum"])), o["categorie"], o["tekst"]):
                            wijzig_opmerking(o["id"], datum, categorie, tekst.strip(), gebruiker=huidige_gebruiker())
                        st.rerun(scope="fragment")


OPM_KOLOMMEN = [
    ("Datum", "Datum", "datum", None, "small"),
    ("Tuin", "Tuin", "tekst", None, "small"),
    ("Afd.", "Afd.", "getal", "%d", "small"),
    ("Vak", "Vak", "getal", "%d", "small"),
    ("Code", "Code", "tekst", None, "small"),
    ("Teelt", "Teelt", "tekst", None, "small"),
    ("Categorie", "Categorie", "tekst", None, "small"),
    ("Opmerking", "Opmerking", "tekst", None, "large"),
    ("Door", "Door", "tekst", None, "small"),
]


@st.cache_data(ttl=600, show_spinner=False)
def _opm_alle(versie):
    """Alle opmerkingen met hun vak; `versie` (wijzigingenlog) is alleen de cachesleutel."""
    return get_alle_opmerkingen()


def _teelt_label(week):
    return f"wk {week[1]} '{str(week[0])[2:]}"


def toon_opmerkingenlijst(rijen, sleutel, leeg="Geen opmerkingen."):
    """Opmerkingen als tabel (oud naar nieuw); een klik op een regel opent het vak."""
    if not rijen:
        st.caption(leeg)
        return
    df = pd.DataFrame([{
        "Datum": format_datum(o["datum"]), "Tuin": _tuinnaam_van.get(o["tuin_id"], "?"),
        "Afd.": o["afdeling"], "Vak": o["vaknummer"], "Code": o["code"] or "-",
        "Teelt": _teelt_label(opm_logic.teelt_van(o)), "Categorie": o["categorie"] or "Overig",
        "Opmerking": o["tekst"], "Door": o["gebruiker"] or "-",
    } for o in rijen])
    keuze = toon_tabel(df, OPM_KOLOMMEN, vast=("Datum", "Tuin", "Afd.", "Vak"), sleutel=sleutel)
    gekozen = keuze.selection.rows if keuze else []
    if gekozen and gekozen != st.session_state.get(f"{sleutel}_open"):
        st.session_state[f"{sleutel}_open"] = gekozen
        vandaag = date.today()
        _tl_detail_venster(rijen[gekozen[0]]["teelt_id"], _tl_vakken(vakstatus_dataversie(), vandaag), vandaag)
    elif not gekozen:
        st.session_state[f"{sleutel}_open"] = None


def _pagina_opmerkingen_1():
    pagina_uitleg((
        "Alle opmerkingen bij vakken. Filter op tuin, teelt (plantweek), vak, periode, categorie of een woord "
        "uit de tekst. Klik op een regel om het vak te openen; daar kun je een opmerking ook wijzigen. "
        "Nieuwe opmerkingen maak je via Opmerking in de zijbalk."))
    alle = _opm_alle(vakstatus_dataversie())
    if not alle:
        st.info("Nog geen opmerkingen. Maak er een via Opmerking in de zijbalk.")
        return
    tuinen = sorted(TUINEN, key=lambda t: t["nummer"])
    standaard_tuinen = [t["naam"] for t in tuinen if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE]
    teelten = sorted({opm_logic.teelt_van(o) for o in alle})
    vakken = sorted({o["vaknummer"] for o in alle})
    eerste = min(opm_logic._datum(o["datum"]) for o in alle)
    laatste = max(max(opm_logic._datum(o["datum"]) for o in alle), date.today())

    rij = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    tuin_namen = rij.multiselect("Tuin", [t["naam"] for t in tuinen], default=standaard_tuinen,
                                 key=f"opm_tuin_{TUIN_WEERGAVE}", width=220)
    gekozen_teelten = rij.multiselect("Teelt (plantweek)", teelten, format_func=_teelt_label, key="opm_teelt",
                                      placeholder="Alle teelten", width=200)
    gekozen_vakken = rij.multiselect("Vak", vakken, key="opm_vak", placeholder="Alle vakken", width=170)
    periode = rij.date_input("Periode", (eerste, laatste), format="DD-MM-YYYY", key="opm_periode", width=230)
    categorieen = rij.multiselect("Categorie", OPMERKING_CATEGORIEEN, key="opm_categorie",
                                  placeholder="Alle categorieën", width=200)
    zoek = rij.text_input("Zoeken", key="opm_zoek", placeholder="Woord uit de tekst of code", width=220)
    # Tijdens het kiezen van een periode is er even maar één datum.
    van, tot = (periode + (periode[0],))[:2] if len(periode) else (None, None)

    rijen = opm_logic.filter_opmerkingen(
        alle, tuinen={t["id"] for t in tuinen if t["naam"] in tuin_namen}, teelten=set(gekozen_teelten),
        vakken=set(gekozen_vakken), van=van, tot=tot, categorieen=set(categorieen), zoek=zoek)
    st.caption(f"{len(rijen)} van {len(alle)} opmerkingen. Klik op een regel om het vak te openen.")
    toon_opmerkingenlijst(rijen, "opm_lijst", "Geen opmerkingen die aan de filters voldoen.")


def teelt_detail(s, klimaat, water, model=None):
    """
    De hele teelt van één vak: tijdlijn, voortgang (lopend), klimaat tegen de
    lichtlijn, lichtsom, watergift per dag, groei en stek. Voor lopende teelten
    (s["stook"] uit het teeltmodel) en afgeronde (s["teelt"]["datum_oogst"]).
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
                    text=f"Opgebouwd {fmt_getal(u['gedaan'] * 100)} % van wat het vak nodig heeft tot de oogst"
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
                      "Geen watergift in dit vak.")

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
            f"Lijn = mediaan, band = P25–P75 van {len(s['refs'])} referentievakken "
            f"({vs.REFERENTIE_NIVEAUS[s['niveau']]}); rood = gemeten, groen = Florgib, "
            f"stippellijn = {'oogst' if t.get('datum_oogst') else 'vandaag'}.{meting}"
        )
    else:
        st.caption("Te weinig afgeronde vakken met een Florgib- én oogstmeting rond deze plantweek "
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
        toon_opmerkingen(int(t["id"]))
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

    regels = [("Florgib op dag", "florgib", 0), ("Lengte bij Florgib (cm)", "half", 1),
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


def _nu_afdeling_venster(info, afdeling, data, vandaag):
    """Stookadvies van één afdeling: c per vak, een schuif voor de afdelingscorrectie en wat die per vak doet."""
    tuin, a, model = info["tuin"], info["advies"].get(afdeling), info["model"]

    @st.dialog(f"Stookadvies afdeling {afdeling} · {tuin['naam']}", width="large")
    def _venster():
        if a is None or a["c"] is None:
            st.info("Geen lopende vakken met een prognose in deze afdeling.")
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
    """De matrix van één tuin; de afdelingsnaam opent het stookadvies van die afdeling."""
    tuin_nr = info["tuin"]["nummer"]
    st.markdown(f'<div class="vem-kg-titel">{html.escape(info["tuin"]["naam"])}</div>', unsafe_allow_html=True)

    # Per afdeling (in teeltvolgorde) een rij: het label links en de vakken in
    # een eigen raster dat bij een smal scherm naar een volgende regel loopt.
    vakken = info["vakken"]
    for afdeling in sorteer_afdelingen(vakken["afdeling"].dropna(), tuin_nr):
        groep = vakken[vakken["afdeling"] == afdeling]
        with st.container(key=f"nu_rij_{tuin_nr}_{afdeling}"):
            if st.button(f"Afd. {afdeling}", key=f"nu_afdknop_{tuin_nr}_{afdeling}", type="tertiary",
                         help="Stookadvies van deze afdeling"):
                _nu_afdeling_venster(info, afdeling, data, vandaag)
            with st.container(key=f"nu_blokken_{tuin_nr}_{afdeling}"):
                for vak in sorted(int(v) for v in groep["vaknummer"]):
                    s = info["statussen"].get(vak)
                    klasse = s["klasse"] if s else "leeg"
                    rand = "fa" if s and s["florgib_achter"] else "ok"
                    label = _nu_bloklabel(vak, s, info["gepland"].get(vak))
                    tip = _nu_bloktip(vak, s, info["gepland"].get(vak), info["laatste_oogst"].get(vak), info)
                    if st.button(label, key=f"nu_vak_{klasse}_{rand}_{tuin_nr}_{vak}", help=tip, width="stretch"):
                        _nu_vak_venster(info, vak, vandaag, data)


def _pagina_overzicht_1():
    _nu_vandaag = date.today()
    _nu_uitleg = (
        "Per vak: plantweek en leeftijd, de Florgib (geregistreerd of verwacht), de correctie op de lichtlijn "
        "die nodig is om op de plandatum te oogsten (met het effect op het gewicht), en plan en prognose.\n\n"
        "Het teeltmodel telt per dag een deel van de teelt af, afhankelijk van de lichtsom binnen en de "
        f"afwijking van de lichtlijn ({formule_tekst()}), met een correctie per tuin. Het leert van alle "
        "afgeronde vakken (historie uit de klimaatregistratie plus wat in de app is afgerond). Na de Florgib "
        "wordt de voortgang gelijkgezet op het deel waarop meestal gespoten wordt.\n\n"
        f"Prognose = oogst als de afdeling blijft stoken zoals de laatste {AFWIJKING_VENSTER_DAGEN} dagen. "
        "Correctie = de vaste afwijking van de lichtlijn vanaf vandaag waarmee de oogst precies op de plandatum "
        f"valt (tussen {fmt_verschil(C_GRENZEN[0], 0)} en {fmt_verschil(C_GRENZEN[1], 0)} °C). "
        f"Binnen ±{fmt_kort(OP_KOERS_MARGE)} °C: op koers.\n\n"
        "Stookadvies per afdeling (klik op de afdelingsnaam) = de correctie per vak, gewogen naar het aantal "
        "stelen.\n\n"
        "Kleur = prognose t.o.v. plan in dagen: ±1 d op schema, daarna stappen van 2 dagen tot 6 d te vroeg "
        "(donkerblauw) of 7 d te laat (donkerrood)."
    )
    pagina_uitleg(_nu_uitleg)
    _nu_keuze = TUIN_WEERGAVE

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
        "<span>klik op een vak of op de afdelingsnaam voor details</span></div>",
        unsafe_allow_html=True,
    )

# --- TUINVERGELIJKING: wat er in een periode in de kas gebeurde, per m² ---
#
# Tuin 1 naast tuin 3 en het totaal (gewogen naar m²). Het rekenwerk staat in
# logic/tuinvergelijking.py, de tabel in ui/vergelijkingstabel.py.

TV_KENGETALLEN = [
    Kengetal("bezetting", "Bezetting", "Bezetting & productie", "%", 0,
             "Aandeel van het teeltoppervlak met een lopend vak, gemiddeld over de dagen van de periode."),
    Kengetal("geplant", "Geplant", "Bezetting & productie", "st", 0,
             "Aantal planten in de vakken die in de periode geplant zijn.", n_eenheid="vakken"),
    Kengetal("geoogst", "Geoogste stelen", "Bezetting & productie", "st", 0,
             "Emmers × 100 geregistreerd in de periode. Alleen als de emmerregistratie al vóór de periode liep "
             "(tuin 1 sinds 04-06-26, tuin 3 sinds 14-08-26).", n_eenheid="vakken"),
    Kengetal("uitval", "Uitval", "Bezetting & productie", "%", 1,
             "Uitval van de vakken afgerond in de periode, gewogen naar vak-m². Uit de emmers, anders het "
             "vastgelegde percentage.", n_eenheid="vakken"),
    Kengetal("temp", "Etmaaltemperatuur", "Klimaat", "°C", 1,
             "Gemiddeld over de afdelingen, gewogen naar hun m².", n_eenheid="dagen"),
    Kengetal("temp_dag", "Dagtemperatuur", "Klimaat", "°C", 1, "Gemiddeld over de afdelingen, gewogen naar m².",
             n_eenheid="dagen"),
    Kengetal("temp_nacht", "Nachttemperatuur", "Klimaat", "°C", 1, "Gemiddeld over de afdelingen, gewogen naar m².",
             n_eenheid="dagen"),
    Kengetal("rv", "RV", "Klimaat", "%", 0, "Etmaalgemiddelde, gewogen naar m² per afdeling.", n_eenheid="dagen"),
    Kengetal("lichtsom", "Lichtsom binnen per dag", "Klimaat", "J/cm²", 0,
             "Gemiddelde dagsom binnen, gewogen naar m² per afdeling.", n_eenheid="dagen"),
    Kengetal("afwijking", "Afwijking lichtlijn", "Klimaat", "°C", 1,
             f"Etmaaltemperatuur min de lichtlijn ({formule_tekst()}), per afdeling per dag, gewogen naar m². "
             "Positief = warmer gestookt dan de lichtlijn.", teken=True, n_eenheid="dagen"),
    Kengetal("warmte", "Warmte", "Energie & water", "MJ/m²", 1,
             "Geleverde warmte in de periode gedeeld door de m² kas (de hele kas wordt verwarmd). Tuin 3: "
             "Pulsteller; tuin 1: warmtewisselaar (sinds 09-01-26). De warmtelevering is half september 2026 "
             "gestopt; sindsdien stoken de ketels op gas (zie Gas en Energie totaal), dus warmte 0 is dan juist.",
             n_eenheid="dagen"),
    Kengetal("gas", "Gas", "Energie & water", "m³/m²", 2, "Gasverbruik (Pulsteller 1) gedeeld door de m² kas.",
             n_eenheid="dagen"),
    Kengetal("energie", "Energie totaal", "Energie & water", "MJ/m²", 1,
             f"Warmte plus gas omgerekend ({fmt_kort(GAS_CALORISCHE_WAARDE_MJ_PER_M3, 2)} MJ per m³), per m² kas.",
             n_eenheid="dagen"),
    Kengetal("water", "Water", "Energie & water", "l/m²", 1,
             "Watergift van alle vakken samen in de periode, gedeeld door de m² kas.", n_eenheid="dagen"),
]
PERIODE_ENKELVOUD = {"Week": "week", "Maand": "maand", "Kwartaal": "kwartaal", "Jaar": "jaar"}


def _vakken_tekst(aantal):
    return None if aantal is None else f"{aantal} {'vak' if aantal == 1 else 'vakken'}"


@st.cache_resource(ttl=600, show_spinner="Gegevens ophalen…")
def _tv_gegevens(versie):
    """Alle data van de Tuinvergelijking, voorbereid. `versie` (wijzigingenlog) is alleen de cachesleutel."""
    return tuinvgl.Gegevens(get_vergelijking_data())


def _tv_volgorde(tuin_id, afdeling, vak):
    """Sorteersleutel tuin → afdeling (teeltvolgorde) → vak."""
    nummer = _tuinnummer_van.get(tuin_id, tuin_id)
    volgorde = list(sorteer_afdelingen({afdeling} | set(AFDELING_VOLGORDE.get(nummer, ())), nummer))
    return nummer, volgorde.index(afdeling) if afdeling in volgorde else 99, vak


def _tv_tabeldata(g, tuinen, van, tot, v_van, v_tot, label):
    """Tabeldata van de Tuinvergelijking: deze periode tegen de vergelijkingsperiode."""
    nu = tuinvgl.tabelwaarden(g, tuinen, van, tot)
    toen = tuinvgl.tabelwaarden(g, tuinen, v_van, v_tot)
    toelichting = {kolom: {"geplant": _vakken_tekst(nu["verwacht"].get(kolom, {}).get("geplant")),
                           "geoogst": _vakken_tekst(nu["n"].get(kolom, {}).get("geoogst"))}
                   for kolom in nu["waarden"]}
    return vergelijkingstabel.Tabeldata(
        nu=nu["waarden"], toen=toen["waarden"], n=nu["n"], n_toen=toen["n"], verwacht=nu["verwacht"],
        bron=nu["bron"], bron_toen=toen["bron"], toelichting=toelichting, ontbreekt=nu["ontbreekt"],
        label_toen=label)


def _tv_uitklappers(g, van, tot, periode_naam):
    """Geplant, geoogst en watergift in de periode, per vak (tuin → afdeling → vak)."""
    afdeling = g.vak_afdeling

    geplant = sorted((t for t in g.teelten if van <= t["start"] <= tot),
                     key=lambda t: _tv_volgorde(t["tuin_id"], afdeling.get((t["tuin_id"], t["vaknummer"])),
                                                t["vaknummer"]))
    with st.expander(f"🌱 Geplant in deze periode ({_vakken_tekst(len(geplant))})"):
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
    with st.expander(f"🌾 Geoogst in deze periode ({_vakken_tekst(len({e['teelt_id'] for e in emmers}))}, "
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


def _pagina_tuinvgl_1():
    pagina_uitleg((
        "Wat er in een periode in de kas gebeurde: tuin 1 naast tuin 3 en het totaal, alles per m². Het totaal "
        "is gewogen naar m² (niet het gemiddelde van twee tuinen). Een kengetal zonder data toont – (waarom: "
        "beweeg over de cel)."))
    _tv_laatste_priva = laatste_priva_ophaling()
    if _tv_laatste_priva:
        st.caption(f"Klimaat, watergift en energie bijgewerkt tot {format_datum(_tv_laatste_priva.date())} "
                   f"{_tv_laatste_priva:%H:%M}.")
    _tv_vandaag = date.today()
    _tv_g = _tv_gegevens(vakstatus_dataversie())
    _tv_tuinen = [(t["naam"], t["id"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])]

    # Eén compacte rij, links uitgelijnd: periode · welke (◀ label ▶) · vergelijk met.
    _tv_rij = st.container(horizontal=True, vertical_alignment="bottom", gap="large")
    _tv_periode = _tv_rij.segmented_control("Periode", list(perioden.PERIODEN), default="Week", key="tv_periode",
                                            width="content") or "Week"
    _tv_sleutel_key = f"tv_sleutel_{_tv_periode}"
    if _tv_sleutel_key not in st.session_state:
        st.session_state[_tv_sleutel_key] = perioden.laatste_volledige(_tv_periode, _tv_vandaag)
    _tv_huidig = perioden.periode_sleutel(_tv_vandaag, _tv_periode)[0]

    def _tv_blader(stappen, sleutel_key=_tv_sleutel_key, periode=_tv_periode):
        st.session_state[sleutel_key] = perioden.verschuif(st.session_state[sleutel_key], periode, stappen)

    with _tv_rij.container(width="content"):
        st.markdown('<div style="font-size:14px;margin-bottom:0.3rem">Welke</div>', unsafe_allow_html=True)
        _tv_nav = st.container(horizontal=True, vertical_alignment="center", gap="small", width="content")
        _tv_nav.button("◀", key="tv_terug", on_click=_tv_blader, args=(-1,), help="Vorige periode")
        _tv_sleutel = st.session_state[_tv_sleutel_key]
        _tv_nav.markdown(f"**{perioden.periode_label(_tv_sleutel, _tv_periode)}**", width=150)
        _tv_nav.button("▶", key="tv_verder", on_click=_tv_blader, args=(1,), help="Volgende periode",
                       disabled=_tv_sleutel >= _tv_huidig)
    _tv_vergelijk = _tv_rij.radio("Vergelijk met", ["vorige periode", "zelfde periode vorig jaar"], index=1,
                                  horizontal=True, key="tv_vergelijk", width="content")
    _tv_soort = "vorige" if _tv_vergelijk == "vorige periode" else "vorig_jaar"

    _tv_van, _tv_tot, _tv_loopt = perioden.venster(_tv_sleutel, _tv_periode, _tv_vandaag)
    _tv_v_van, _tv_v_tot, _ = perioden.vergelijk_venster(_tv_sleutel, _tv_periode, _tv_soort, _tv_vandaag)
    _tv_label = perioden.kort_label(_tv_sleutel, _tv_periode, _tv_soort)
    _tv_enkel = PERIODE_ENKELVOUD[_tv_periode]
    st.caption(
        f"{format_datum(_tv_van)} t/m {format_datum(_tv_tot)}" + (" (loopt nog, t/m gisteren)" if _tv_loopt else "")
        + f". Kleine regel = {'zelfde ' + _tv_enkel + ' vorig jaar' if _tv_soort == 'vorig_jaar' else 'vorige ' + _tv_enkel}"
        + (", tot even ver" if _tv_loopt else "")
        + ". Groen/rood pijltje = beter/slechter; lichtgroen vak = beste tuin; ⚠ = niet alle dagen of vakken "
          "met data. Beweeg over een cel voor het verschil en de uitleg."
    )

    def _tv_verloop(k, sleutel=_tv_sleutel, periode=_tv_periode):
        rijen = []
        for stap in range(-11, 1):
            s = perioden.verschuif(sleutel, periode, stap)
            van, tot, _ = perioden.venster(s, periode, _tv_vandaag)
            if tot < van:
                continue
            u = tuinvgl.tabelwaarden(_tv_g, _tv_tuinen, van, tot)
            for naam, _ in _tv_tuinen:
                rijen.append({"Periode": perioden.periode_label(s, periode), "Tuin": naam,
                              "Waarde": u["waarden"][naam].get(k.sleutel), "n": u["n"][naam].get(k.sleutel, 0)})
        return verloop_frame(rijen)

    vergelijkingstabel.toon(
        TV_KENGETALLEN, [n for n, _ in _tv_tuinen] + ["Totaal"],
        _tv_tabeldata(_tv_g, _tv_tuinen, _tv_van, _tv_tot, _tv_v_van, _tv_v_tot, _tv_label),
        sleutel="tv_verloop", verloop=_tv_verloop,
        verloop_titel=f"Verloop over 12 {'weken' if _tv_periode == 'Week' else 'perioden'}")

    # Trend geoogste stelen (uit de emmers), de laatste 12 perioden t/m de gekozen.
    st.write("**Geoogste stelen per periode**")
    _tv_trend = []
    for _tv_stap in range(-11, 1):
        _tv_s = perioden.verschuif(_tv_sleutel, _tv_periode, _tv_stap)
        _tv_pv, _tv_pt, _ = perioden.venster(_tv_s, _tv_periode, _tv_vandaag)
        if _tv_pt < _tv_pv:
            continue
        for _tv_naam, _tv_id in _tv_tuinen:
            _tv_delen = tuinvgl.onderdelen(_tv_g, _tv_id, _tv_pv, _tv_pt).get("geoogst")
            if _tv_delen:
                _tv_trend.append({"Periode": perioden.periode_label(_tv_s, _tv_periode), "Tuin": _tv_naam,
                                  "Stelen": _tv_delen[0], "Vakken": _tv_delen[2]})
    if not _tv_trend:
        st.caption("Nog geen emmers geregistreerd in deze perioden.")
    else:
        _tv_df = pd.DataFrame(_tv_trend)
        st.altair_chart(alt.Chart(_tv_df).mark_bar().encode(
            x=alt.X("Periode:O", sort=list(dict.fromkeys(_tv_df["Periode"])), title=None,
                    axis=alt.Axis(labelAngle=-40 if _tv_periode == "Week" else 0)),
            y=alt.Y("Stelen:Q", title="Geoogste stelen"),
            color=alt.Color("Tuin:N", title=None, legend=alt.Legend(orient="top")),
            tooltip=["Periode", "Tuin", alt.Tooltip("Stelen:Q", format=",.0f"), "Vakken"],
        ).properties(height=240), use_container_width=True)
        st.caption("Uit de emmers (× 100 stelen), gestapeld per tuin: tuin 1 sinds 04-06-26, tuin 3 sinds 14-08-26.")

    _tv_opm_van, _tv_opm_tot = perioden.periode_grenzen(_tv_sleutel, _tv_periode)
    _tv_opm = opm_logic.filter_opmerkingen(_opm_alle(vakstatus_dataversie()), van=_tv_opm_van, tot=_tv_opm_tot)
    _tv_deze = f"{'dit' if _tv_periode in ('Kwartaal', 'Jaar') else 'deze'} {_tv_enkel}"
    st.write(f"**Opmerkingen in {_tv_deze}** ({len(_tv_opm)})" if _tv_opm else f"**Opmerkingen in {_tv_deze}**")
    toon_opmerkingenlijst(_tv_opm, "tv_opm", f"Geen opmerkingen in {_tv_deze}.")

    _tv_uitklappers(_tv_g, _tv_van, _tv_tot, _tv_periode)

# --- TEELTVERGELIJKING: een teelt = alle vakken uit één plantweek ---
#
# Bovenaan een samenvatting per tuin (gewogen naar m² van het vak), daaronder
# de vakken naast elkaar. Rekenwerk in logic/teeltvergelijking.py.


def _tl_tekst(waarde, n):
    return waarde or LEEG


TL_KENGETALLEN = [
    Kengetal("aantal", "Vakken", "Teelt", "", 0, "Vakken met een plantdatum in deze week.",
             formaat=lambda w, n: LEEG if w is None else f"{int(w)} ({n} afgerond)"),
    Kengetal("plantdatum", "Plantdatum", "Teelt", uitleg="Eerste en laatste plantdatum.", formaat=_tl_tekst,
             verschil=False),
    Kengetal("florgib", "Florgib", "Teelt", uitleg="Eerste en laatste Florgib-datum (app, anders klimaatregistratie).",
             formaat=_tl_tekst, verschil=False),
    Kengetal("fase1", "Fase 1 (planten → Florgib)", "Teelt", "d", 0, "Dagen van planten tot de Florgib.",
             n_eenheid="vakken"),
    Kengetal("oogst", "Oogst", "Teelt", uitleg="Eerste en laatste oogstdatum; ⏳ = met de prognose van het teeltmodel (Teeltoverzicht) "
             "voor lopende vakken.", formaat=_tl_tekst, verschil=False),
    Kengetal("fase2", "Fase 2 (Florgib → oogst)", "Teelt", "d", 0, "Dagen van de Florgib tot de oogst (⏳ = met prognose).",
             n_eenheid="vakken"),
    Kengetal("teeltduur", "Teeltduur", "Teelt", "d", 0, "Dagen van planten tot oogst (⏳ = met prognose).",
             n_eenheid="vakken"),
    Kengetal("lichtsom", "Lichtsom binnen per dag", "Klimaat tijdens de teelt", "J/cm²", 0,
             "Gemiddelde dagsom binnen, eigen afdeling, van planten tot de oogst (lopende vakken: t/m gisteren, ⏳).",
             n_eenheid="vakken"),
    Kengetal("temp", "Etmaaltemperatuur", "Klimaat tijdens de teelt", "°C", 1,
             "Gemiddeld, eigen afdeling, van planten tot de oogst (lopende vakken: t/m gisteren, ⏳).",
             n_eenheid="vakken"),
    Kengetal("afwijking", "Afwijking lichtlijn", "Klimaat tijdens de teelt", "°C", 1,
             f"Etmaaltemperatuur min de lichtlijn ({formule_tekst()}), gemiddeld over de dagen.",
             teken=True, n_eenheid="vakken"),
    Kengetal("warmte", "Warmte", "Input (per m²)", "MJ/m²", 0,
             "Warmte en gas per bezette m² van planten tot de oogst; alleen als (vrijwel) elke dag gemeten is.",
             n_eenheid="vakken"),
    Kengetal("water", "Water", "Input (per m²)", "l/m²", 0, "Watergift van het vak van planten tot de oogst.",
             n_eenheid="vakken"),
    Kengetal("stelen_m2", "Stelen per m²", "Resultaat", "", 1,
             "Geoogste stelen (emmers × 100, anders geplant × (1 − uitval)) per m² vak. Alleen afgeronde vakken.",
             n_eenheid="vakken"),
    Kengetal("uitval", "Uitval", "Resultaat", "%", 1, "Uit de emmers, anders het vastgelegde percentage.",
             n_eenheid="vakken"),
    Kengetal("lengte", "Oogstlengte", "Resultaat", "cm", 1, "Lengte bij de oogst.", n_eenheid="vakken"),
    Kengetal("gewicht", "Oogstgewicht", "Resultaat", "g", 0, "Vastgelegd oogstgewicht (tuin 1 weegt niet).",
             n_eenheid="vakken"),
    Kengetal("lengte_fg", "Lengte bij Florgib", "Resultaat", "cm", 1, "Lengtemeting bij de Florgib.",
             n_eenheid="vakken"),
    Kengetal("lengtefactor", "Lengtefactor", "Resultaat", "", 2, "Oogstlengte gedeeld door de lengte bij de Florgib.",
             n_eenheid="vakken"),
    Kengetal("stek", "Stekcijfer", "Stek", "", 1, "Gemiddeld cijfer van de stekbeoordeling.", n_eenheid="vakken"),
    Kengetal("stek_matig", "Stek matig of slechter", "Stek", "", 0,
             "Vakken met wortel, plantmaat of uniformiteit 'Matig' of 'Slecht'.",
             formaat=lambda w, n: LEEG if w is None else f"{int(w)} van {n} vakken"),
]

# Kolommen van de vakkentabel: (sleutel, kop, decimalen)
TL_KOLOMMEN = [("fase1", "Fase 1 (d)", 0), ("fase2", "Fase 2 (d)", 0), ("teeltduur", "Duur (d)", 0),
               ("lichtsom", "Licht/dag", 0), ("temp", "Etmaal °C", 1), ("afwijking", "Afw. lichtlijn", 1),
               ("warmte", "Warmte MJ/m²", 0), ("water", "Water l/m²", 0), ("stelen_m2", "Stelen/m²", 1),
               ("uitval", "Uitval %", 1), ("lengte", "Lengte cm", 1), ("gewicht", "Gewicht g", 0),
               ("stek", "Stekcijfer", 0)]


@st.cache_data(ttl=600, show_spinner="Vakken ophalen…")
def _tl_ruw(versie):
    """Gegevens van alle vakken (zie database.get_teeltvergelijking_data); `versie` is de cachesleutel."""
    return get_teeltvergelijking_data()


@st.cache_resource(ttl=600, show_spinner="Dagdata klaarzetten…")
def _tl_dagdata(versie):
    """Klimaat, water en warmte per dag voor de vensters per vak; `versie` is de cachesleutel."""
    g = _tv_gegevens(versie)
    return teeltvgl.Dagdata(g.klimaat, g.water, {t["id"]: warmte_per_bezette_m2(t["id"]) for t in TUINEN})


def _tl_vakken(versie, vandaag):
    """Alle vakken (vaste gegevens) als dicts van logic.teeltvergelijking, met de prognose van het teeltmodel."""
    g = _tv_gegevens(versie)
    stook = _nu_alles(vandaag)[2]
    return [teeltvgl.teelt(k, g.vak_m2.get((k["tuin_id"], int(k["vaknummer"]))),
                           prognose=(stook.get(k["id"]) or {}).get("prognose"),
                           florgib_historie=k.get("florgib_historie"))
            for k in _tl_ruw(versie) if vs.als_datum(k["datum_teelt_start"]) <= vandaag]


def _tl_detail_venster(teelt_id, vakken, vandaag):
    """Popup met één vak: dezelfde weergave als het vakvenster in Teeltoverzicht, ook voor afgeronde vakken."""
    data, model, stook, _ = _nu_alles(vandaag)
    alle = data["teelten"].to_dict("records")
    t = next((r for r in alle if r["id"] == teelt_id), None)
    rij = next((r for r in vakken if r["id"] == teelt_id), None)
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
        toon_opmerkingen(teelt_id)
        teelt_detail(s, klimaat, water, model)

    _venster()


def _tl_vakkentabel(groep, vandaag, markeer=()):
    """De vakken van de teelt naast elkaar; een klik op een regel opent het vak. `markeer`: ids om op te lichten."""
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

    # Kleur: afwijking van het (m²-gewogen) gemiddelde van de teelt, alleen
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

    for i, t in enumerate(groep):
        if t["id"] in markeer:
            for kop in ("Tuin", "Afd.", "Vak", "Code"):
                kleuren.loc[i, kop] = "background-color: rgba(237,161,0,0.30); font-weight: 600"

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
    st.caption("Groen/rood = minstens 5 % beter/slechter dan het gemiddelde van deze teelt (alleen waar beter "
               "vastligt). ⏳ = lopend vak: klimaat en input t/m gisteren, oogst en duur zijn de prognose. "
               "Klik op een regel voor het vak.")
    gekozen = keuze.selection.rows if keuze else []
    vorige = st.session_state.get("tl_gekozen")
    if gekozen and gekozen != vorige:
        st.session_state["tl_gekozen"] = gekozen
        _tl_detail_venster(groep[gekozen[0]]["id"], groep, vandaag)
    elif not gekozen:
        st.session_state["tl_gekozen"] = None


def _pagina_teeltvgl_1():
    pagina_uitleg((
        "Een teelt = alle vakken uit één plantweek. Bovenaan per tuin samengevat (gewogen naar de m² van het vak), "
        "daaronder de vakken naast elkaar. De kleine regel is dezelfde plantweek vorig jaar."))
    _tl_vandaag = date.today()
    _tl_gisteren = _tl_vandaag - timedelta(days=1)
    _tl_versie = vakstatus_dataversie()
    _tl_alle = _tl_vakken(_tl_versie, _tl_vandaag)
    _tl_dd = _tl_dagdata(_tl_versie)
    _tl_weken = teeltvgl.plantweken(_tl_alle)
    _tl_lijst = sorted(_tl_weken, reverse=True)
    if not _tl_lijst:
        st.info("Nog geen vakken.")
    else:
        # Kiezen met losse velden: tuin, week, vak, jaar. Een gekozen vak licht op
        # in de vakkenlijst; het vak bepaalt ook welke jaren er te kiezen zijn.
        _tl_items = [{"id": t["id"], "tuin_id": t["tuin_id"], "vak": t["vak"],
                      "jaar": teeltvgl.plantweek(t["start"])[0], "week": teeltvgl.plantweek(t["start"])[1]}
                     for t in _tl_alle]
        _tl_tuin_id = {t["nummer"]: t["id"] for t in TUINEN}
        _tl_tuin_opties = ["beide"] + sorted(_tl_tuin_id)
        if st.session_state.get("tl_week") not in _tl_lijst:
            st.session_state["tl_week"] = teeltvgl.standaard_plantweek(_tl_weken)
        if st.session_state.get("tl_tuin") not in _tl_tuin_opties:
            st.session_state["tl_tuin"] = TUIN_WEERGAVE if TUIN_WEERGAVE in _tl_tuin_opties else "beide"

        def _tl_tuin():
            keuze = st.session_state["tl_tuin"]
            return None if keuze == "beide" else _tl_tuin_id[keuze]

        def _tl_zet(week):
            st.session_state.update(tl_week=week, tl_wk=week[1], tl_jaar=week[0])

        def _tl_na_tuin():
            st.session_state["tl_vak"] = "alle"

        def _tl_plantweken():
            """De plantweken (oud naar nieuw) met vakken in de gekozen tuin."""
            return sorted({(i["jaar"], i["week"]) for i in selectie.gekozen(_tl_items, _tl_tuin())})

        def _tl_blader(stappen):
            huidig, lijst = st.session_state["tl_week"], _tl_plantweken()
            verder = [w for w in lijst if (w > huidig if stappen > 0 else w < huidig)]
            if verder:
                st.session_state["tl_vak"] = "alle"
                _tl_zet(verder[0] if stappen > 0 else verder[-1])

        # Eén rij, links uitgelijnd, met vaste breedtes (niet over het hele scherm uitgesmeerd).
        _tl_rij = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
        _tl_rij.selectbox("Tuin", _tl_tuin_opties, key="tl_tuin", on_change=_tl_na_tuin, width=130,
                          format_func=lambda n: "Beide" if n == "beide" else f"Tuin {n}")
        _tl_weekopties = selectie.weken(_tl_items, _tl_tuin())
        st.session_state["tl_wk"] = selectie.geldig(
            st.session_state.get("tl_wk"), _tl_weekopties,
            selectie.geldig(st.session_state["tl_week"][1], _tl_weekopties, _tl_weekopties[-1]))
        _tl_rij.selectbox("Week", _tl_weekopties, key="tl_wk", format_func=lambda w: f"wk {w}", width=110)
        # "alle" i.p.v. None: een selectbox toont None als "niets gekozen".
        _tl_vakopties = ["alle"] + selectie.vakken(_tl_items, _tl_tuin(), week=st.session_state["tl_wk"])
        st.session_state["tl_vak"] = selectie.geldig(st.session_state.get("tl_vak"), _tl_vakopties, "alle")
        _tl_rij.selectbox("Vak", _tl_vakopties, key="tl_vak", width=140,
                          format_func=lambda v: "Alle vakken" if v == "alle" else f"Vak {v}")
        _tl_vak = None if st.session_state["tl_vak"] == "alle" else st.session_state["tl_vak"]
        _tl_jaaropties = selectie.jaren(_tl_items, st.session_state["tl_wk"], _tl_tuin(), _tl_vak)
        st.session_state["tl_jaar"] = selectie.geldig(
            st.session_state.get("tl_jaar"), _tl_jaaropties,
            selectie.geldig(st.session_state["tl_week"][0], _tl_jaaropties, _tl_jaaropties[-1]))
        _tl_rij.selectbox("Jaar", _tl_jaaropties, key="tl_jaar", width=110)
        st.session_state["tl_week"] = (st.session_state["tl_jaar"], st.session_state["tl_wk"])
        _tl_pw = _tl_plantweken()
        _tl_rij.button("◀", key="tl_terug", on_click=_tl_blader, args=(-1,), help="Vorige teelt",
                       disabled=not _tl_pw or st.session_state["tl_week"] <= _tl_pw[0])
        _tl_rij.button("▶", key="tl_verder", on_click=_tl_blader, args=(1,), help="Volgende teelt",
                       disabled=not _tl_pw or st.session_state["tl_week"] >= _tl_pw[-1])
        _tl_markeer = {i["id"] for i in selectie.gekozen(
            _tl_items, _tl_tuin(), _tl_vak, st.session_state["tl_wk"], st.session_state["tl_jaar"])
        } if _tl_vak is not None else set()
        _tl_week = st.session_state["tl_week"]
        st.caption(f"Teelt wk {_tl_week[1]} - {_tl_week[0]} · {_vakken_tekst(_tl_weken[_tl_week][0])}, "
                   f"{_tl_weken[_tl_week][1]} afgerond (beide tuinen)")
        _tl_vorig = teeltvgl.vorig_jaar(_tl_week)
        _tl_tuinen = [(t["naam"], t["id"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])]
        _tl_groep = [teeltvgl.met_dagdata(t, _tl_dd, _tl_gisteren)
                     for t in _tl_alle if teeltvgl.plantweek(t["start"]) == _tl_week]
        # Loopt de teelt nog, dan vorig jaar tot dezelfde teeltdag.
        _tl_dag = teeltvgl.teeltdag(_tl_groep, _tl_gisteren)
        _tl_toen_groep = [teeltvgl.met_dagdata(t, _tl_dd, _tl_gisteren, _tl_dag)
                          for t in _tl_alle if teeltvgl.plantweek(t["start"]) == _tl_vorig]
        _tl_nu = teeltvgl.tabelwaarden(_tl_groep, _tl_tuinen)
        _tl_toen = teeltvgl.tabelwaarden(_tl_toen_groep, _tl_tuinen)
        st.caption(
            f"Kleine regel = zelfde plantweek vorig jaar ({_vakken_tekst(len(_tl_toen_groep))})"
            + (f"; klimaat en input tot dezelfde teeltdag (dag {_tl_dag})" if _tl_dag is not None else "")
            + ". Groen/rood pijltje = beter/slechter; lichtgroen vak = beste tuin; ⏳ = met lopende vakken of "
              "prognose; ⚠ = niet alle vakken met data. Beweeg over een cel voor het verschil en de uitleg.")

        def _tl_verloop(k, week=_tl_week):
            rijen = []
            for w in teeltvgl.vorige_weken(week, 12):
                groep = [teeltvgl.met_dagdata(t, _tl_dd, _tl_gisteren)
                         for t in _tl_alle if teeltvgl.plantweek(t["start"]) == w]
                u = teeltvgl.tabelwaarden(groep, _tl_tuinen)
                for naam, _ in _tl_tuinen:
                    waarde = u["waarden"].get(naam, {}).get(k.sleutel)
                    rijen.append({"Periode": f"Wk {w[1]} - {w[0]}", "Tuin": naam,
                                  "Waarde": waarde if isinstance(waarde, (int, float)) else None,
                                  "n": u["n"].get(naam, {}).get(k.sleutel, 0)})
            return verloop_frame(rijen)

        vergelijkingstabel.toon(
            TL_KENGETALLEN, [n for n, _ in _tl_tuinen] + ["Totaal"],
            vergelijkingstabel.Tabeldata(
                nu=_tl_nu["waarden"], toen=_tl_toen["waarden"], n=_tl_nu["n"], n_toen=_tl_toen["n"],
                verwacht=_tl_nu["verwacht"], bron=_tl_nu["bron"], bron_toen=_tl_toen["bron"],
                markering=_tl_nu["markering"], ontbreekt=_tl_nu["ontbreekt"],
                label_toen=f"wk {_tl_vorig[1]} '{str(_tl_vorig[0])[2:]}"),
            sleutel="tl_verloop", verloop=_tl_verloop, verloop_titel="Verloop over 12 plantweken")

        _tl_groep_tuin = [t for t in _tl_groep if _tl_tuin() is None or t["tuin_id"] == _tl_tuin()]
        st.write("**Vakken van deze teelt**" + ("" if _tl_tuin() is None else f" ({_tuinnaam_van[_tl_tuin()]})"))
        _tl_vakkentabel(_tl_groep_tuin, _tl_vandaag, markeer=_tl_markeer)

        _tl_opm = opm_logic.filter_opmerkingen(_opm_alle(_tl_versie), teelt_ids={t["id"] for t in _tl_groep_tuin})
        st.write(f"**Opmerkingen bij deze teelt** ({len(_tl_opm)})" if _tl_opm else "**Opmerkingen bij deze teelt**")
        toon_opmerkingenlijst(_tl_opm, "tl_opm", "Geen opmerkingen bij de vakken van deze teelt.")

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
        f"In {eenheid.lower()}. Plant = concept-plantingen die week; oogst = lopende vakken en concepten "
        "waarvan de (verwachte) oogst in die week valt. Voor lopende vakken is dat de prognose van het "
        "teeltmodel bij de huidige stooklijn (zoals in Teeltoverzicht), voor concepten de plandatum. Een oogst die al "
        "werd verwacht vóór deze week telt mee bij 'deze week', zodat die niet uit beeld verdwijnt. Stelen bij "
        "een concept zijn een schatting op de standaarddichtheid voor die plantweek."
    )


# --- VAKKENREGISTER (Teeltoverzicht, onder de matrix) ---
#
# Alle vakken in drie tabellen: lopend, te starten (bevestigd, startdatum in
# de toekomst) en afgerond. Een klik op een regel opent de vakpopup.

REGISTER_LOPEND = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Plantweek", "getal0"), ("Leeftijd (d)", "getal0"), ("Planten", "getal0"), ("Florgib", "datum"),
    ("Lengte bij Florgib (cm)", "getal1"), ("Plan-oogst", "datum"), ("Prognose", "datum"),
    ("Voor (−) / achter (+) (d)", "teken0"), ("Emmers tot nu", "getal0"),
]
REGISTER_TE_STARTEN = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Plantweek", "getal0"), ("Planten", "getal0"), ("Plan-oogst", "datum"),
]
REGISTER_AFGEROND = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Florgib", "datum"), ("Oogstdatum", "datum"), ("Teeltduur (d)", "getal0"), ("Fase 1 (d)", "getal0"),
    ("Fase 2 (d)", "getal0"), ("Stelen/m²", "getal1"), ("Uitval (%)", "getal1"), ("Oogstlengte (cm)", "getal1"),
    ("Oogstgewicht (g)", "getal0"), ("Lichtsom/dag", "getal0"), ("Etmaal (°C)", "getal1"),
    ("Afw. lichtlijn (°C)", "teken1"), ("Water (l/m²)", "getal0"), ("Warmte (MJ/m²)", "getal0"),
]


def _register_kolommen(kolommen):
    """Registerkolommen → het kolomformaat van toon_tabel (kolom, label, soort, formaat, breedte)."""
    uit = []
    for naam, soort in kolommen:
        if soort == "datum":
            uit.append((naam, naam, "datum", None, "small"))
        elif soort == "tekst":
            uit.append((naam, naam, "tekst", None, "medium" if naam == "Code" else "small"))
        else:
            decimalen = int(soort[-1])
            uit.append((naam, naam, "getal", f"%.{decimalen}f" if decimalen else "%d", "small"))
    return uit


def _register_rijen(vandaag):
    """(lopend, te_starten, afgerond, vakken): de rijen per tabel en de vakken voor de popup."""
    versie = vakstatus_dataversie()
    g = _tv_gegevens(versie)
    dd = _tl_dagdata(versie)
    stook = _nu_alles(vandaag)[2]
    gisteren = vandaag - timedelta(days=1)
    lopend, te_starten, afgerond, vakken = [], [], [], []
    for k in _tl_ruw(versie):
        start = vs.als_datum(k["datum_teelt_start"])
        tuin_id, vak_nr = k["tuin_id"], int(k["vaknummer"])
        afdeling = int(k["afdeling"]) if vs._getal(k.get("afdeling")) is not None else None
        prognose = (stook.get(k["id"]) or {}).get("prognose")
        t = teeltvgl.teelt(k, g.vak_m2.get((tuin_id, vak_nr)), prognose=prognose,
                           florgib_historie=k.get("florgib_historie"))
        basis = {"id": k["id"], "Tuin": _tuinnaam_van.get(tuin_id, "?"), "Afd.": afdeling, "Vak": vak_nr,
                 "Code": k.get("code") or "-", "Plantdatum": start, "Plantweek": start.isocalendar()[1],
                 "Ras": k.get("ras") or "", "_tuin_id": tuin_id,
                 "_sorteer": _tv_volgorde(tuin_id, afdeling, vak_nr)}
        plan = bereken_verwachte_oogstdatum(start)[1]
        if start > vandaag:
            te_starten.append({**basis, "Planten": vs._getal(k.get("aantal_planten")), "Plan-oogst": plan})
            continue
        vakken.append(t)
        if not t["afgerond"]:
            stelen = vs._getal(k.get("stelen"))
            lopend.append({**basis, "Leeftijd (d)": (vandaag - start).days,
                           "Planten": vs._getal(k.get("aantal_planten")), "Florgib": t["florgib"],
                           "Lengte bij Florgib (cm)": vs._getal(k.get("lengte_half")), "Plan-oogst": plan,
                           "Prognose": prognose,
                           "Voor (−) / achter (+) (d)": (prognose - plan).days if prognose and plan else None,
                           "Emmers tot nu": stelen / 100 if stelen else None})
        else:
            t = teeltvgl.met_dagdata(t, dd, gisteren)
            afgerond.append({**basis, "Florgib": t["florgib"], "Oogstdatum": t["oogst_echt"],
                             "Teeltduur (d)": t["teeltduur"], "Fase 1 (d)": t["fase1"], "Fase 2 (d)": t["fase2"],
                             "Stelen/m²": t["stelen_m2"], "Uitval (%)": t["uitval"], "Oogstlengte (cm)": t["lengte"],
                             "Oogstgewicht (g)": t["gewicht"], "Lichtsom/dag": t["lichtsom"],
                             "Etmaal (°C)": t["temp"], "Afw. lichtlijn (°C)": t["afwijking"],
                             "Water (l/m²)": t["water"], "Warmte (MJ/m²)": t["warmte"]})
    return lopend, te_starten, afgerond, vakken


def _register_tabel(rijen, kolommen, sleutel, vakken, vandaag, klikbaar=True, sorteer=None):
    """Eén registertabel; bij klikbaar opent een klik op een regel de vakpopup (één keer per keuze)."""
    if not rijen:
        st.caption("Geen vakken die aan de filters voldoen.")
        return
    rijen = sorted(rijen, key=sorteer or (lambda r: (r["_sorteer"], r["Plantdatum"])))
    soorten = dict(kolommen)
    df = pd.DataFrame([{naam: (format_datum(r.get(naam)) if soorten[naam] == "datum" and r.get(naam) else r.get(naam))
                        for naam, _ in kolommen} for r in rijen])
    vast = ("Tuin", "Afd.", "Vak", "Code")
    if not klikbaar:
        toon_tabel(df, _register_kolommen(kolommen), vast=vast)
        return
    keuze = toon_tabel(df, _register_kolommen(kolommen), vast=vast, sleutel=sleutel)
    gekozen = keuze.selection.rows if keuze else []
    if gekozen and gekozen != st.session_state.get(f"{sleutel}_open"):
        st.session_state[f"{sleutel}_open"] = gekozen
        _tl_detail_venster(rijen[gekozen[0]]["id"], vakken, vandaag)
    elif not gekozen:
        st.session_state[f"{sleutel}_open"] = None


def toon_vakkenregister(vandaag, tuin_weergave):
    """Filters en de drie tabellen Lopend / Te starten / Afgerond."""
    lopend, te_starten, afgerond, vakken = _register_rijen(vandaag)
    alle = lopend + te_starten + afgerond
    if not alle:
        st.info("Nog geen vakken geregistreerd. Start ze in het tabblad Planning.")
        return
    st.write("**Vakkenregister**")
    tuin_namen = [t["naam"] for t in sorted(TUINEN, key=lambda t: t["nummer"])]
    standaard_tuinen = tuin_namen if tuin_weergave == "beide" else [_tuin_labels.get(tuin_weergave)]
    rij = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    # Volgt de tuinkeuze bovenaan; binnen die keuze vrij aan te passen.
    tuinen = rij.multiselect("Tuin", tuin_namen, default=standaard_tuinen, key=f"reg_tuin_{tuin_weergave}",
                             width=220)
    nummer = _tuinnummer_van.get(next((t["id"] for t in TUINEN if [t["naam"]] == tuinen), None))
    afdelingen = sorteer_afdelingen({r["Afd."] for r in alle if r["Afd."] is not None}, nummer)
    gekozen_afd = rij.multiselect("Afdeling", afdelingen, key="reg_afd", placeholder="Alle", width=170)
    weken = sorted({(r["Plantdatum"].isocalendar()[0], r["Plantweek"]) for r in alle})
    van_wk, tot_wk = rij.select_slider("Plantweek", options=weken, value=(weken[0], weken[-1]), key="reg_weken",
                                       format_func=lambda w: f"wk {w[1]} '{str(w[0])[2:]}", width=320)
    rassen = sorted({r["Ras"] for r in alle if r["Ras"]})
    gekozen_ras = rij.multiselect("Ras", rassen, key="reg_ras", placeholder="Alle", width=170)
    zoek = rij.text_input("Zoek vak of code", key="reg_zoek", placeholder="bijv. 12 of 263401", width=200).strip()

    def past(r):
        week = (r["Plantdatum"].isocalendar()[0], r["Plantweek"])
        return (r["Tuin"] in tuinen and (not gekozen_afd or r["Afd."] in gekozen_afd)
                and van_wk <= week <= tot_wk and (not gekozen_ras or r["Ras"] in gekozen_ras)
                and (not zoek or zoek == str(r["Vak"]) or zoek.lower() in str(r["Code"]).lower()))

    lopend, te_starten, afgerond = ([r for r in rijen if past(r)] for rijen in (lopend, te_starten, afgerond))
    tab_l, tab_s, tab_a = st.tabs([f"Lopend ({len(lopend)})", f"Te starten ({len(te_starten)})",
                                   f"Afgerond ({len(afgerond)})"])
    with tab_l:
        _register_tabel(lopend, REGISTER_LOPEND, "reg_lopend", vakken, vandaag)
        st.caption("Prognose = het teeltmodel bij de huidige stooklijn (zoals in de matrix hierboven). "
                   "Klik op een regel voor het vak.")
    with tab_s:
        _register_tabel(te_starten, REGISTER_TE_STARTEN, "reg_starten", vakken, vandaag, klikbaar=False)
        st.caption("Bevestigde vakken met een startdatum in de toekomst; concepten staan in Planning.")
    with tab_a:
        # Laatst geoogst bovenaan, bij dezelfde oogstdatum in kasvolgorde.
        _register_tabel(afgerond, REGISTER_AFGEROND, "reg_afgerond", vakken, vandaag,
                        sorteer=lambda r: (-(r["Oogstdatum"] or date.min).toordinal(), r["_sorteer"]))
        st.caption("Klimaat en input over de hele teelt van het vak (planten t/m oogst). Klik op een regel voor "
                   "het vak.")


def _pagina_overzicht_2():
    st.markdown("---")
    toon_vakkenregister(date.today(), TUIN_WEERGAVE)

# --- PLANNING (TOEKOMSTIGE TEELTEN) ---
def _pagina_planning_1():
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
            "Strokenplanning: grijs = afgerond, groen = lopend vak, blauw = concept-planning. "
            "Getal op de as = ISO-weeknummer; rode stippellijn = vandaag. Een rode stippelrand om "
            "een deel van een balk = die dagen overlappen met de vorige ronde in dat vak. Oogstdatum "
            "van lopende vakken en concepten is de verwachte datum uit de teeltduur-tabel. Beweeg "
            "over een balk voor weeknummer + dag van start en oogst en de teeltduur in weken."
        )

    # --- Strokenplanning (Gantt): vakken verticaal, weken horizontaal ---
    stroken = get_strokenplanning(weken_terug=8)
    if stroken:
        toon_strokenplanning(stroken, get_vaknummers())
        st.markdown("---")

    toon_vooruitblik(date.today())

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

    st.markdown("---")
    st.write("**Concept-planningen**")
    if st.session_state.get("planning_melding"):
        st.success(st.session_state.pop("planning_melding"))
    planning_rijen = get_planning()  # gesorteerd op startdatum (dus per week), dan vaknummer
    if not planning_rijen:
        st.info("Nog geen concept-planningen.")
    else:
        alles_tonen = st.toggle("Alles tonen", key="planning_alles",
                                help="Standaard alleen de concepten die in de komende 8 weken starten.")
        grens = date.today() + timedelta(weeks=8)
        stelen_60 = {v: g["stelen_bij_60"] for v, g in get_vakgegevens(TUIN_ID).items()}
        origineel, regels = {}, []
        for planning_id, vaknummer, start, duur, eind, _notitie in planning_rijen:
            start_d = vs.als_datum(start)
            if not alles_tonen and start_d > grens:
                continue
            jaar, week, _ = start_d.isocalendar()
            planten = round((stelen_60.get(vaknummer) or 0) / 60 * standaard_dichtheid_voor_plantweek(week))
            origineel[planning_id] = {"start": start_d, "planten": planten, "bevestigen": False, "verwijderen": False}
            regels.append({"id": planning_id, "Week": f"wk {week} '{str(jaar)[2:]}", "Vak": vaknummer,
                           "Startdatum": start_d, "Duur (wk)": duur, "Verwachte oogst": vs.als_datum(eind),
                           "Planten": planten, "✅ Bevestigen": False, "🗑️ Verwijderen": False})
        if not regels:
            st.caption("Geen concepten in de komende 8 weken; zet 'Alles tonen' aan voor de rest.")
        else:
            # De editor krijgt na elke opslag een nieuwe sleutel, zodat de vinkjes weer leeg zijn.
            versie = st.session_state.get("planning_editor_versie", 0)
            bewerkt = st.data_editor(
                pd.DataFrame(regels).set_index("id"), hide_index=True, use_container_width=True,
                key=f"planning_editor_{versie}_{alles_tonen}", disabled=["Week", "Vak", "Duur (wk)", "Verwachte oogst"],
                column_config={
                    "Startdatum": st.column_config.DateColumn(format="DD-MM-YY", required=True),
                    "Verwachte oogst": st.column_config.DateColumn(format="DD-MM-YY",
                                                                   help="Volgt de oude startdatum tot je opslaat"),
                    "Duur (wk)": getalkolom("Duur (wk)", 1),
                    "Planten": st.column_config.NumberColumn(
                        min_value=0, step=1, format="%d",
                        help="Aantal planten bij bevestigen (standaard stelen/m² bij die plantweek)"),
                    "✅ Bevestigen": st.column_config.CheckboxColumn(help="Omzetten naar een gestart vak"),
                    "🗑️ Verwijderen": st.column_config.CheckboxColumn(help="Concept verwijderen"),
                },
            )
            nieuw = {int(i): {"start": vs.als_datum(r["Startdatum"]), "planten": r["Planten"],
                              "bevestigen": bool(r["✅ Bevestigen"]), "verwijderen": bool(r["🗑️ Verwijderen"])}
                     for i, r in bewerkt.iterrows()}
            plan = planning_editor.wijzigingen(origineel, nieuw)
            kolom_knop, kolom_tekst = st.columns([1, 3], vertical_alignment="center")
            if planning_editor.heeft_wijzigingen(plan):
                kolom_tekst.caption(f"Nog niet opgeslagen: {planning_editor.samenvatting(plan)}.")
            if kolom_knop.button("Wijzigingen opslaan", key="planning_opslaan", type="primary",
                                 disabled=not planning_editor.heeft_wijzigingen(plan)):
                gebruiker = huidige_gebruiker()
                for planning_id, start in plan["gewijzigd"]:
                    wijzig_planning(planning_id, start, gebruiker=gebruiker)
                codes = []
                for planning_id, planten in plan["bevestigd"]:
                    resultaat = bevestig_planning(planning_id, planten, gebruiker=gebruiker)
                    if resultaat:
                        codes.append(resultaat[1])
                for planning_id in plan["verwijderd"]:
                    verwijder_planning(planning_id, gebruiker=gebruiker)
                st.session_state["planning_melding"] = (
                    f"Opgeslagen: {planning_editor.samenvatting(plan)}."
                    + (f" Gestart: {', '.join(codes)}." if codes else ""))
                st.session_state["planning_editor_versie"] = versie + 1
                st.rerun()

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


def _pagina_stek_1():
    stekweken = get_stekweken()
    if not stekweken:
        st.info("Er zijn nog geen vakken gestart.")
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

        with st.container(border=True, width=760):
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


# --- DATA IMPORTEREN (onder Meer) ---
def _pagina_import_1():
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
    if not dekking:
        st.info("Nog geen klimaatdata. Upload hierboven een CSV-export uit de klimaatcomputer of haal 'm uit Priva.")

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

# --- LOGBOEK ---
def _pagina_log_1():
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
        # Een regel in de tabel "teelten" is één vak (een teelt = alle vakken uit één plantweek).
        df_log["Type"] = df_log["Type"].replace({"teelt": "vak", "teelten": "vak"})

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

# --- PROGNOSEKWALITEIT (onder Meer) ---
PK_HORIZON_LABEL = {28: "28 d vooraf", 14: "14 d vooraf", 7: "7 d vooraf", prognoselog.FLORGIB: "Na Florgib"}
PK_KOLOMMEN = [
    ("Moment", "Moment", "tekst", None, "medium"),
    ("n", "n", "getal", "%d", "small"),
    ("Gem. fout (d)", "Gem. fout (d)", "getal", "%.1f", "small"),
    ("MAE (d)", "MAE (d)", "getal", "%.1f", "small"),
    ("Binnen ±2 d", "Binnen ±2 d (%)", "getal", "%d", "small"),
]


@st.cache_data(ttl=600, show_spinner="Prognoselogboek ophalen…")
def _pk_gegevens(versie, dag):
    """(log, oogsten) van de geoogste vakken; `versie` en `dag` zijn alleen cachesleutels."""
    log = get_prognose_log()
    oogsten = {teelt_id: prognoselog.werkelijke_oogst(emmers, datum_oogst)
               for teelt_id, (emmers, datum_oogst) in get_oogst_emmers({r["teelt_id"] for r in log}).items()}
    return log, oogsten


def _pk_tabel(kwaliteit, tuin_id):
    rijen = []
    for horizon, label in PK_HORIZON_LABEL.items():
        k = kwaliteit.get((tuin_id, horizon))
        rijen.append({"Moment": label, "n": k["n"] if k else None,
                      "Gem. fout (d)": round(k["gemiddeld"], 1) + 0.0 if k else None,  # geen "-0,0" "MAE (d)": k["mae"] if k else None,
                      "Binnen ±2 d": round(k["binnen_pct"]) if k else None})
    toon_tabel(pd.DataFrame(rijen), PK_KOLOMMEN)


def _pagina_prognosekwaliteit():
    pagina_uitleg((
        "Elke dag legt de app per lopend vak de oogstprognose van het teeltmodel vast. Na de oogst "
        "vergelijkt deze pagina die met de werkelijke oogst: de dag waarop de helft van de emmers binnen "
        "was (zonder emmers de oogstdatum). Fout = werkelijk − voorspeld in dagen: positief = later "
        "geoogst dan voorspeld. MAE = gemiddelde fout zonder teken."))
    vandaag = date.today()
    log, oogsten = _pk_gegevens(vakstatus_dataversie(), str(vandaag))
    rijen = prognoselog.fouten(log, oogsten)
    n = prognoselog.aantal_vakken(rijen)
    if n < prognoselog.MIN_VAKKEN:
        st.info(f"Nog te weinig data (n = {n}): er zijn minstens {prognoselog.MIN_VAKKEN} geoogste vakken "
                "met een prognoselogboek nodig. Het logboek loopt sinds de invoering elke dag mee.")
        return

    tuinen = [t for t in sorted(TUINEN, key=lambda t: t["nummer"])
              if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE]
    for titel, veld in (("Prognose teeltmodel", "fout_prognose"), ("Plandatum", "fout_plan")):
        st.write(f"**{titel}**")
        kwaliteit = prognoselog.kwaliteit(rijen, veld)
        for kolom, tuin in zip(st.columns(len(tuinen)), tuinen):
            with kolom:
                st.caption(tuin["naam"])
                _pk_tabel(kwaliteit, tuin["id"])

    st.write("**Fout naar dagen vóór de oogst**")
    per_dag = pd.DataFrame(prognoselog.fout_per_dag(log, oogsten))
    if not per_dag.empty:
        per_dag = per_dag[per_dag["tuin_id"].isin([t["id"] for t in tuinen])]
        per_dag["Tuin"] = per_dag["tuin_id"].map(_tuinnaam_van)
        per_dag = (per_dag.groupby(["Tuin", "dagen_voor_oogst"])["fout"]
                   .agg(fout="mean", mae=lambda x: x.abs().mean()).reset_index())
    basis = alt.Chart(per_dag).encode(
        x=alt.X("dagen_voor_oogst:Q", title="Dagen vóór de oogst", scale=alt.Scale(reverse=True)),
        color=alt.Color("Tuin:N", legend=alt.Legend(title=None, orient="top")))
    grafiek = (basis.mark_line().encode(
                   y=alt.Y("fout:Q", title="Gem. fout (d)"),
                   tooltip=[alt.Tooltip("Tuin:N"), alt.Tooltip("dagen_voor_oogst:Q", title="Dagen vóór oogst"),
                            alt.Tooltip("fout:Q", title="Gem. fout (d)", format=".1f"),
                            alt.Tooltip("mae:Q", title="MAE (d)", format=".1f")])
               + alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[3, 3], color="#8a8a80").encode(y="y:Q"))
    toon_grafiek(grafiek, per_dag, "Nog geen logregels van geoogste vakken.")

    st.write("**Grootste missers**")
    missers = prognoselog.grootste_missers([r for r in rijen if r["tuin_id"] in {t["id"] for t in tuinen}])
    tabel = pd.DataFrame([{
        "Tuin": _tuinnaam_van.get(m["tuin_id"], "?"), "Vak": m["vaknummer"], "Code": m["code"],
        "Eerste emmer": format_datum(m["eerste_emmer"]) if m["eerste_emmer"] else None,
        "Oogst (50 %)": format_datum(m["werkelijk"]),
        **{f"Fout {h} d": m["fouten"].get(h) for h in prognoselog.HORIZONS},
        "Fout Florgib": m["fouten"].get(prognoselog.FLORGIB),
    } for m in missers])
    kolommen = ([("Tuin", "Tuin", "tekst", None, "small"), ("Vak", "Vak", "getal", "%d", "small"),
                 ("Code", "Code", "tekst", None, "small"), ("Eerste emmer", "Eerste emmer", "datum", None, "small"),
                 ("Oogst (50 %)", "Oogst (50 %)", "datum", None, "small")]
                + [(k, k, "getal", "%d", "small") for k in tabel.columns if k.startswith("Fout")])
    keuze = toon_tabel(tabel, kolommen, vast=("Tuin", "Vak", "Code"), sleutel="pk_missers")
    st.caption("Klik op een regel voor het vak. Fout = werkelijk − voorspeld, in dagen.")
    gekozen = keuze.selection.rows if keuze else []
    if gekozen and gekozen != st.session_state.get("pk_missers_open"):
        st.session_state["pk_missers_open"] = gekozen
        _tl_detail_venster(missers[gekozen[0]]["teelt_id"], _tl_vakken(vakstatus_dataversie(), vandaag), vandaag)
    elif not gekozen:
        st.session_state["pk_missers_open"] = None


# --- HOE DIT WERKT (onder Meer) ---
def _pagina_help_1():
    st.write("""
    **Begrippen**
    - **Vak**: één vak in de kas met één teeltronde. Elke ronde krijgt een eigen code:
      jaar + plantweek + vaknummer. Hetzelfde vak komt dus meerdere keren voor, één keer per ronde.
    - **Teelt**: alle vakken uit één plantweek (van één of beide tuinen).
    - **Florgib**: de lengtemeting halverwege de teelt; die stuurt de prognose bij.
    - Datums staan als dd-mm-jj met het ISO-weeknummer; lijsten lopen van laag naar hoog.

    **Tuinkeuze**
    - Bovenaan kies je tuin 1, tuin 3 of Beide. Bij Beide tonen de overzichten beide tuinen;
      registratie, Planning, Stek en import werken dan op de werk-tuin die je in de zijbalk kiest.

    **Registratie (zijbalk)**
    - *Florgib lengte*: kies één of meer vakken, vul datum en lengte in; die geldt voor alle
      gekozen vakken.
    - *Oogst › Emmers*: per oogstmoment het aantal emmers (100 stelen per emmer). Vink
      "Vak afronden" aan bij de laatste emmers.
    - *Oogst › Lengte en gewicht*: voor vakken die nog niet zijn afgerond. Rijpheid loopt van
      1 (rauw) tot 4 (rijp).
    - *Opmerking*: een opmerking bij één of meer lopende vakken (zie Opmerkingen hieronder).
    - *Wijzigen of verwijderen*: kies het vak met drie velden (plantweek, vak, jaar; standaard
      de laatst gestarte week en het recentste jaar) en daarna wat je wilt wijzigen: startdatum, planten en ras;
      Florgib; oogst en emmers; of opmerkingen. Onderaan kun je het hele vak verwijderen.
      Elk vak begint als Cameron; een nieuw ras typ je bij "Ander ras".

    **Teeltoverzicht** (startpagina)
    - De vakkenmatrix per afdeling, in teeltvolgorde. De kleur van een vak is de prognose:
      aantal dagen te vroeg (−7) of te laat (+7) ten opzichte van de geplande oogst.
      Klik op een vak voor klimaat, water, groei en stek; klik op de afdelingsnaam voor het
      stookadvies van die afdeling.
    - Daaronder het vakkenregister: Lopend, Te starten (bevestigde vakken die nog moeten
      beginnen) en Afgerond, met filters op tuin, afdeling, plantweek, ras en zoeken.
      Uitval staat alleen bij afgeronde vakken. Klik op een regel voor het vak.

    **Planning**
    - Bovenaan de Gantt en de vooruitblik (wat de komende weken te planten en te oogsten staat).
    - Daaronder de concept-planningen als één tabel, standaard de komende 8 weken ("Alles tonen"
      voor de rest). Pas een startdatum aan, vink ✅ aan om een vak te starten (met het aantal
      planten uit de tabel) of 🗑️ om een concept te verwijderen, en klik op "Wijzigingen opslaan".
      Een concept is nog geen gestart vak; pas na ✅ krijgt het een code.
    - *Jaarplanning: vakken per week*: het aantal poot-eenheden per week voor de vak 2-39-cyclus,
      plus een aparte kolom voor vak 1. Een week zonder aantal blijft leeg; klik op "Plan opnieuw
      met deze aantallen" om te (her)plannen. Vak 19 en 20 worden samen gepland; vak 1 loopt op
      een eigen ritme.
    - Elke tuin heeft een eigen planning. Automatisch plannen kent voorlopig alleen het ritme van
      tuin 3; op tuin 1 plan je per vak met "Eén vak handmatig plannen".

    **Stek**
    - Per pootweek het geleverde stek per vak (bakjes, beoordeling); de uitval rekent de app
      zelf uit (bakjes × 600 stekken). De beoordeling vul je één keer voor de hele week in.

    **Teeltvergelijking**
    - Per teelt (plantweek): bovenaan per tuin samengevat, daaronder de vakken naast elkaar.
      Vergelijking met vorig jaar gebeurt op dezelfde teeltdag.
    - Kies met tuin, plantweek, vak en jaar. Een gekozen vak licht op in de vakkenlijst. De tuinkeuze bepaalt de vakkenlijst en de
      opmerkingen; de vergelijkingstabel toont altijd beide tuinen. ◀ ▶ bladert per teelt.

    **Tuin vergelijking**
    - Wat er in een week (of maand, kwartaal, jaar) in de kas gebeurde: tuin 1 naast tuin 3 en
      het totaal, per m². De kleine regel onder een getal is de vorige periode of dezelfde periode
      vorig jaar; het pijltje zegt of het beter (groen) of slechter (rood) is.

    **Opmerkingen**
    - Een opmerking maak je via *Opmerking* in de zijbalk, bij één of meer lopende vakken. Je ziet ze terug in
      de vakpopup (daar ook wijzigen of verwijderen), op de pagina Opmerkingen (zoeken op tuin, teelt, vak,
      periode, categorie of tekst), bij de gekozen teelt in Teeltvergelijking en bij de gekozen periode in
      Tuin vergelijking.

    **Meer**
    - *Data importeren*: klimaat- en energiedata uit de Priva-export.
    - *Prognosekwaliteit*: hoe goed de oogstprognose en de plandatum achteraf klopten.
    - *Logboek*: elke wijziging, met wie en wanneer.
    """)

# --- NAVIGATIE ---
#
# Losse pagina's (st.navigation): een klik voert alleen de code van die pagina
# uit, niet die van alle tabbladen. Elke pagina heeft een eigen adres
# (bijv. /planning) voor links en bladwijzers; de app opent op Teeltoverzicht.

def pagina_planning():
    _pagina_planning_1()


def pagina_stek():
    _pagina_stek_1()


def pagina_teeltoverzicht():
    _pagina_overzicht_1()
    _pagina_overzicht_2()


def pagina_teeltvergelijking():
    _pagina_teeltvgl_1()


def pagina_tuinvergelijking():
    _pagina_tuinvgl_1()


def pagina_opmerkingen():
    _pagina_opmerkingen_1()


def pagina_meer():
    """Weinig gebruikt: import, prognosekwaliteit, logboek en uitleg als subtabbladen."""
    tab_import, tab_prognose, tab_log, tab_help = st.tabs(
        ["Data importeren", "Prognosekwaliteit", "Logboek", "Hoe dit werkt"])
    with tab_import:
        _pagina_import_1()
    with tab_prognose:
        _pagina_prognosekwaliteit()
    with tab_log:
        _pagina_log_1()
    with tab_help:
        _pagina_help_1()


_pagina.run()

# Lokaal meten: maak een leeg bestand .vem_tijd naast app.py; elke run schrijft
# dan zijn duur (en de actieve pagina) in .vem_tijd.log.
_VEM_TIJD = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vem_tijd")
if os.path.exists(_VEM_TIJD):
    with open(_VEM_TIJD + ".log", "a", encoding="utf-8") as _f:
        _f.write(f"{datetime.now():%H:%M:%S} {_pagina.title} {time.perf_counter() - _VEM_T0:.2f}\n")

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
from datetime import datetime, timedelta, timezone, date
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
    get_water_kwaliteit_dekking,
    get_watergift_overzicht,
    get_watergift_vak,
    get_watergift_dagen_voor_periode,
    verwerk_energie_csv,
    GAS_CALORISCHE_WAARDE_MJ_PER_M3,
    get_vakgegevens,
    ideale_etmaaltemperatuur,
    LICHT_TEMP_FACTOR,
    LICHT_TEMP_BASIS,
    get_isojaar_week,
    get_wijzigingenlog,
    lees_ruwe_tabel,
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
    get_opzoek_gegevens,
    WATERGIFT_BRON_BESTAND_VANDAAG,
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
    get_behandelingen,
    get_pats_tellingen,
    get_gewasmetingen,
    get_klimaat_uur,
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
from logic import opzoeken
from logic import selectie
from logic import watergift as wg
from logic import pats as pats_logic
from logic import weken as kalender
from logic import tuinvergelijking as tuinvgl
from logic import tuin_overzicht as tuin_ov
from logic import teeltvergelijking as teeltvgl
from logic import teeltprognose as tp
from logic import registreren as reg
from logic import tijdlijn
from logic import ruwe_data
from logic.afdelingen import sorteer_afdelingen
from logic.lichtlijn import formule_tekst, t_ideaal
from ui import filters, layout, legend, styles, vergelijkingstabel
from ui import help as uitleg_help
from ui.vergelijkingstabel import Kengetal, verloop_frame
from config import (
    PATS_TRAPEYE_VAKKEN,
    AFDELING_VOLGORDE, AFWIJKING_VENSTER_DAGEN, C_GRENZEN, FLORGIB_ACHTERSTAND_DAGEN,
    OP_KOERS_MARGE, OPMERKING_CATEGORIEEN, APP_VERSIE, WATERSYSTEMEN,
    DIF_MIN, STOOK_MAX, EC_BEREIK, PH_BEREIK,
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
/* Kengetallen: compacte tegels naast elkaar, elk zo breed als de inhoud (nooit een waarde over twee
   regels), die doorlopen naar een volgende regel; i.p.v. brede st.metric-kaders met veel lege ruimte. */
.vem-kg-titel {
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; opacity: 0.6; margin: 0.9rem 0 0.35rem;
}
.vem-kg { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.4rem; }
.vem-kg-tegel {
    flex: 0 0 auto; min-width: 6.5rem; border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 0.2rem;
    padding: 0.3rem 0.6rem; line-height: 1.25;
}
.vem-kg-label, .vem-kg-waarde, .vem-kg-delta { white-space: nowrap; }
.vem-kg-label { font-size: 0.72rem; opacity: 0.7; }
.vem-kg-label abbr { text-decoration: none; cursor: help; opacity: 0.8; margin-left: 0.2rem; }
.vem-kg-waarde { font-size: 1rem; font-weight: 600; margin-top: 0.1rem; }
.vem-kg-delta { font-size: 0.68rem; opacity: 0.65; margin-top: 0.1rem; }


/* Kop: naam van de app en het bedrijf links, week, datum en versie rechts. */
.vem-kop {
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    margin: 0 0 0.6rem 0; padding: 0.9rem 1.3rem; border-radius: 0.2rem;
    background: linear-gradient(100deg, #2E6A4C 0%, #3d8761 100%); color: #fff;
}
.vem-merk { display: flex; flex-direction: column; line-height: 1.2; }
.vem-titel { font-size: 1.45rem; font-weight: 700; letter-spacing: 0.01em; }
.vem-bedrijf { font-size: 0.9rem; opacity: 0.85; }
.vem-meta { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.35; white-space: nowrap; }
.vem-week { font-size: 0.9rem; font-weight: 600; }
.vem-versie { font-size: 0.75rem; opacity: 0.75; }
@media (max-width: 700px) { .vem-titel { font-size: 1.15rem; } .vem-kop { padding: 0.7rem 0.9rem; } }

/* Navigatiebalk onder de kop: knoppen per pagina, de huidige gevuld groen. Zelfde ronding als de
   knoppen van Streamlit (theme.buttonRadius in .streamlit/config.toml). */
.st-key-vem_nav { gap: 0.25rem; flex-wrap: wrap; }
/* Stek, "Hele week invullen": alle velden op één regel, dicht op elkaar. */
.st-key-stek_week_rij { flex-wrap: wrap; gap: 0.5rem !important; }
.st-key-vem_nav [data-testid="stPageLink"] a {
    padding: 0.3rem 0.65rem; border-radius: 0.2rem; border: 1px solid rgba(46, 106, 76, 0.35);
    background: transparent;
}
.st-key-vem_nav [data-testid="stPageLink"] a p { font-size: 0.92rem; }
.st-key-vem_nav [data-testid="stPageLink"] a:hover { background: rgba(46, 106, 76, 0.10); }
/* Streamlit geeft een paginaknop een negatieve marge (−6 px boven en onder); lopen de knoppen op een smal
   scherm door naar een tweede regel, dan schuiven ze daardoor over elkaar. Marge weg, knop iets compacter. */
.st-key-vem_nav [data-testid="stElementContainer"] { margin: 0 !important; }
.st-key-vem_nav [data-testid="stPageLink"] a { margin: 0; line-height: 1.5; }
.st-key-vem_nav_actief [data-testid="stPageLink"] a,
.st-key-vem_nav_actief [data-testid="stPageLink"] a:hover { background: #2E6A4C; border-color: #2E6A4C; }
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
        <button id="knop" style="font:inherit;padding:0.35rem 0.75rem;border-radius:0.2rem;
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
                elif soort == "getal":
                    # Streamlit kapt af op de stapgrootte (21,89 → 21,8); zelf eerst afronden.
                    gelezen = gelezen.round(decimalen)
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


def excel_bestand(bladen):
    """Excel-bestand (bytes) met per blad een DataFrame: {bladnaam: df}. Tekens die Excel niet toestaat in een
    bladnaam ([ ] : * ? / \\) worden een streepje, en de naam hooguit 31 tekens."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as schrijver:
        for naam, df in bladen.items():
            df.to_excel(schrijver, index=False, sheet_name=re.sub(r"[\[\]:*?/\\]", "-", str(naam))[:31])
    return buffer.getvalue()


def ga_naar(url_path, keuzes=None, tuin=None):
    """
    Naar een andere pagina met de filters al goed gezet: `keuzes` = {sleutel: waarde} in de opslag van
    ui/filters (None = terug naar de standaard), `tuin` = de tuinweergave ("beide" of een nummer).
    """
    for sleutel, waarde in (keuzes or {}).items():
        if waarde is None:
            st.session_state.pop(filters.opslag(sleutel), None)
        else:
            filters.bewaar(sleutel, waarde)
    if tuin is not None:
        st.session_state["tuin_weergave"] = tuin
        if tuin != "beide":
            st.session_state["tuin_nummer"] = tuin
    # De standaardpagina heeft in Streamlit een lege url_path; daarom zoeken op de titel.
    titel = next(t for _, t, adres in PAGINA_DEFINITIES if adres == url_path)
    st.switch_page(next(p for p in _pagina_lijst if p.title == titel))


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
    lang["Type"] = lang["_v"].map({"temp_24h": "Werkelijk", "ideaal": "Berekende etmaaltemp."})

    chart = alt.Chart(lang).mark_line().encode(
        x=datum_as(),
        y=y_as("waarde", "Etmaaltemperatuur (°C)"),
        color=kleur,
        strokeDash=alt.StrokeDash(
            "Type:N", legend=alt.Legend(title=None, orient="bottom"),
            scale=alt.Scale(domain=["Werkelijk", "Berekende etmaaltemp."], range=[[1, 0], [6, 3]]),
        ),
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"), "Afdeling:N", "Type:N",
                 alt.Tooltip("waarde:Q", title="°C", format=".1f")],
    )
    st.caption(
        f"Berekende etmaaltemperatuur = {fmt_kort(LICHT_TEMP_FACTOR, 4)} x lichtsom + {fmt_kort(LICHT_TEMP_BASIS, 1)} °C "
        "van diezelfde dag. Werkelijk erboven: relatief te warm gestookt voor het licht. Eronder: te koud."
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


# De pagina's (zie NAVIGATIE onderaan): (naam van de functie, titel, adres).
PAGINA_DEFINITIES = [
    ("pagina_registreren", "Registreren", "registreren"),
    ("pagina_overzicht", "Overzicht", "overzicht"),
    ("pagina_teelt", "Teelt", "teelt"),
    ("pagina_tuinvergelijking", "Tuin", "tuinvergelijking"),
    ("pagina_opmerkingen", "Opmerkingen", "opmerkingen"),
    ("pagina_meer", "Meer", "meer"),
]


def _mobiel():
    """True op een telefoon (aan de browser te zien)."""
    try:
        agent = st.context.headers.get("User-Agent") or ""
    except Exception:          # geen headers (bijv. in een test)
        agent = ""
    return bool(re.search(r"Mobi|Android|iPhone", agent))


def _startpagina():
    """Het adres waarop de app opent: Overzicht, op een telefoon Registreren (daar wordt in de kas ingevuld)."""
    return "registreren" if _mobiel() else "overzicht"


def _paginas():
    """st.Page-objecten; de paginafuncties zelf worden pas bij het draaien opgezocht (ze staan onderaan)."""
    def pagina(naam):
        def draai():
            globals()[naam]()
        draai.__name__ = naam
        return draai
    start = _startpagina()
    return [st.Page(pagina(naam), title=titel, url_path=adres, default=adres == start)
            for naam, titel, adres in PAGINA_DEFINITIES]


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
    f'<span class="vem-week">Week {kalender.weeknummer(_vandaag_kop)} · '
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
# st.rerun() kan geven (tuinkeuze, opslaan): een herhaalde run onthoudt dan de
# gekozen pagina. Uitgevoerd wordt de pagina pas onderaan (_pagina.run()).
# Het menu van Streamlit zelf blijft verborgen; de knoppen staan in een eigen
# balk onder de kop, met de huidige pagina gevuld.
_pagina_lijst = _paginas()
_pagina = st.navigation(_pagina_lijst, position="hidden")
# Eén kopbalk: de tabbladknoppen (genummerd, voor feedback: "scherm 2.3"), daarachter de tuinkeuze en rechts
# de knop Uitleg (zie hieronder).
_kopbalk = st.container(horizontal=True, vertical_alignment="center", gap="small", key="vem_kopbalk")
with _kopbalk.container(horizontal=True, width="content", key="vem_nav"):
    for _nr, _p in enumerate(_pagina_lijst, 1):
        with st.container(width="content", key="vem_nav_actief" if _p.title == _pagina.title
                          else f"vem_nav_{_p.url_path or 'start'}"):
            st.page_link(_p, label=f"{_nr}. {_p.title}")
layout.begin_pagina(next(i for i, _p in enumerate(_pagina_lijst, 1) if _p.title == _pagina.title))

# --- TUIN KIEZEN ---
#
# Eén app voor beide tuinen, met de tuin als keuze bovenaan. Alles wat daarna
# uit de database komt gaat over die tuin: teelten, klimaat, water, energie en
# het registratieformulier. Zo kun je niet per ongeluk op de verkeerde tuin
# registreren, en kun je de tuinen wel naast elkaar leggen.
TUINEN = get_tuinen()
if "tuin_nummer" not in st.session_state:
    st.session_state["tuin_nummer"] = get_standaard_tuin_van_gebruiker(st.session_state.get("username"))

_tuin_labels = {t["nummer"]: t["naam"] for t in TUINEN}
_tuinnummer_van = {t["id"]: t["nummer"] for t in TUINEN}
_tuinnaam_van = {t["id"]: t["naam"] for t in TUINEN}
_tuin_nummers = [t["nummer"] for t in TUINEN]
# De tuinkeuze staat alleen hier in de kop (ui/filters.tuin). Per pagina: "vrij" = Tuin 1 / Tuin 3 /
# Beide; "een" = de pagina werkt per tuin (Beide kan niet); "beide" = de pagina gaat altijd over beide
# tuinen (keuze uitgeschakeld). Registreren werkt per tuin; bij Beide registreer je in de laatst gekozen tuin.
TUIN_MODUS = {
    "registreren": ("een", "Registreren kan maar in één tuin."),
    "meer": ("een", "Import en prognosekwaliteit werken per tuin."),
}
# Op titel, niet op _pagina.url_path: dat is leeg voor de startpagina.
_adres = next(a for _, t, a in PAGINA_DEFINITIES if t == _pagina.title)
_tuin_modus, _tuin_reden = TUIN_MODUS.get(_adres, ("vrij", None))
_tuin_rij = _kopbalk.container(horizontal=True, vertical_alignment="center", gap="small", width="content",
                               key="vem_tuinkeuze")
TUIN_WEERGAVE, _ = filters.tuin([(t["nummer"], t["naam"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])],
                                modus=_tuin_modus, reden=_tuin_reden, plek=_tuin_rij)
if _tuin_modus == "een" and st.session_state["tuin_weergave"] == "beide":
    _tuin_rij.caption(f"Beide kan hier niet: {_tuin_reden[:-1].lower()}")
elif _tuin_modus == "beide":
    _tuin_rij.caption(_tuin_reden)
# De knop Uitleg van de pagina komt klein rechts in de kopbalk (ui/layout.pagina_kop); een paginatitel is er
# niet, want de gevulde knop in de navigatiebalk laat al zien op welke pagina je bent.
layout.kop_plek(_kopbalk.container(width="content", key="vem_uitleg"))
# De tuin waarin geregistreerd en gepland wordt: de gekozen tuin, bij Beide de laatst gekozen tuin.
TUIN_NUMMER = st.session_state["tuin_nummer"]
TUIN_ID = get_tuin_id(TUIN_NUMMER)
TUIN_NAAM = _tuin_labels.get(TUIN_NUMMER, f"Tuin {TUIN_NUMMER}")
# Vanaf hier werken alle databasefuncties zonder expliciete tuin op deze tuin.
zet_actieve_tuin(TUIN_ID)


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

# --- REGISTREREN: de invoer per tuin (vroeger de zijbalk) ---
#
# Florgib, emmers, lengte en gewicht en opmerkingen voor één of meer vakken, en wijzigen of verwijderen per
# vak. Bij Florgib, emmers en lengte/gewicht een tabel met één regel per lopend vak: een eigen waarde per vak,
# of één waarde voor alle aangevinkte vakken. Rechts wat er nog te doen is en de laatste registraties.
# Rekenwerk in logic/registreren.py. Een nieuwe teelt begint niet hier maar op Overzicht: daar staat het
# concept al klaar in de tijdlijn en zet je het met één knop om in een lopende teelt.
INV_STEK, INV_FLORGIB, INV_EMMERS, INV_LENGTE, INV_OPMERKING, INV_WIJZIGEN = (
    "Stek", "Florgib", "Emmers", "Lengte en gewicht", "Opmerking", "Wijzigen")
# In de volgorde van de teelt: stek bij het poten, Florgib halverwege, emmers en lengte/gewicht bij de oogst.
INV_ACTIES = [INV_STEK, INV_FLORGIB, INV_EMMERS, INV_LENGTE, INV_OPMERKING, INV_WIJZIGEN]
INV_SOORT = {INV_FLORGIB: "florgib", INV_EMMERS: "emmers", INV_LENGTE: "lengte", INV_OPMERKING: "opmerking"}
WIJZIG_ONDERDELEN = ["Startdatum en planten", "Florgib", "Oogst", "Opmerkingen"]
RIJPHEID_TEKSTEN = ["1", "2", "3", "4", "1-2", "2-3", "3-4", "1-3", "2-4", "1-4"]


def _pagina_registreren():
    vandaag = date.today()
    layout.pagina_kop(
        "Registreren",
        wat="Invullen wat er in de kas gebeurd is, in de tuin die bovenaan gekozen is: het stek per pootweek (met "
            "het weekrapport voor de stekleverancier), de Florgib (lengte en gram), de emmers, de oogstlengte en het "
            "oogstgewicht, een opmerking, of iets wijzigen of verwijderen. "
            "Een nieuwe teelt start je op Overzicht (klik op een concept in de tijdlijn).",
        lezen=[
            "Kies bovenaan wat je registreert. Bij Florgib, Emmers en Lengte en gewicht staat elk lopend vak op "
            "een eigen regel.",
            "**Eén waarde voor meerdere vakken**: vul die boven de tabel in en vink de vakken aan. **Een eigen "
            "waarde per vak**: vul die in de tabel in (die gaat voor). Een vak met een ingevulde waarde doet "
            "ook mee zonder vinkje.",
            "**Emmers**: 100 stelen per emmer. Vink *Afronden* aan bij de laatste emmers van een vak (ook "
            "zonder emmers: dan wordt het vak alleen afgerond).",
            "**Rijpheid**: 1 = rauw, 4 = rijp; een bereik als 1-3 voor een mengsel.",
            "**Nog te doen** (rechts): bij Florgib de vakken waarvan het teeltmodel de Florgib binnen 3 dagen "
            "verwacht (of die over tijd zijn); bij Emmers de vakken in de oogst en die binnen 3 dagen oogstrijp "
            "zijn; bij Lengte en gewicht de vakken in de oogst zonder oogstlengte.",
            "**Wijzigen**: kies het vak met week, vak en jaar; daaronder per onderdeel een tabblad.",
            "**Stek**: kies de pootweek met ◀ ▶ of klik op het label (standaard de huidige week; is daar nog niets "
            "gepoot, dan de laatste week waarin wel). *Hele week invullen*: het stek van een week komt meestal uit "
            "één partij; vul het één keer in en pas een afwijkend vak in de tabel aan. *Weekrapport*: kopieer de "
            "tabel, open de mail (onderwerp en ontvangers staan klaar) en plak hem boven je handtekening.",
        ],
        bron="Alles wat je hier opslaat komt in het logboek (Meer), met jouw naam; *Laatst geregistreerd* komt "
             "daaruit. Stek: te poten komt uit de teeltregistratie; de stekuitval rekent de app zelf uit (bakjes × "
             "600 stekken). De pootweek is de plantweek van het vak (ma t/m zo, zoals de teeltcode).",
    )
    if st.session_state.get("inv_melding"):
        st.success(st.session_state.pop("inv_melding"))
    balk = layout.filterbalk("registreren")
    actie = filters.weergave("Wat registreer je?", INV_ACTIES, "inv_actie", INV_FLORGIB, plek=balk)

    if actie == INV_WIJZIGEN:
        layout.sectie(f"Wijzigen of verwijderen · {TUIN_NAAM}")
        _inv_wijzigen()
        return
    if actie == INV_STEK:
        _inv_stek(balk)
        return

    data, _model, stook, _afwijking = _nu_alles(vandaag)
    records = data["teelten"].to_dict("records")
    vakken = reg.lopende_vakken(records, TUIN_ID, vandaag, stook)
    links, rechts = st.columns([3, 1], gap="large")
    with links:
        layout.sectie(f"{actie} · {TUIN_NAAM}")
        if not vakken:
            st.info("Geen lopende vakken in deze tuin. Start ze op Overzicht (klik op een concept in de tijdlijn).")
        elif actie == INV_LENGTE:
            _inv_lengte(vakken)
        else:
            datum = st.date_input("Datum", key="inv_datum", format="DD-MM-YYYY", width=180)
            st.caption(f"Week {kalender.weeknummer(datum)} · {_DAGEN_KORT[datum.weekday()]} {format_datum(datum)}")
            {INV_FLORGIB: _inv_florgib, INV_EMMERS: _inv_emmers, INV_OPMERKING: _inv_opmerking}[actie](vakken, datum)
    with rechts:
        soort = INV_SOORT[actie]
        if soort != "opmerking":
            layout.sectie("Nog te doen")
            te_doen = reg.nog_te_doen(soort, vakken, vandaag)
            if te_doen:
                st.markdown("\n".join(f"- **Vak {vak}** · {tekst}" for vak, tekst in te_doen))
            else:
                st.caption("Niets op dit moment.")
        layout.sectie("Laatst geregistreerd")
        vak_van = {int(t["id"]): int(t["vaknummer"]) for t in records if t["tuin_id"] == TUIN_ID}
        laatste = reg.laatste_registraties(get_wijzigingenlog(500), soort, vak_van)
        if laatste:
            st.markdown("\n".join(f"- {r['tijdstip'].astimezone(_NL_TIJD):%d-%m-%y %H:%M} · vak {r['vak']} · "
                                   f"{html.escape(r['omschrijving'])} · {html.escape(r['gebruiker'] or '-')}"
                                   for r in laatste))
        else:
            st.caption("Nog niets geregistreerd.")


def _inv_klaar(melding):
    """Na opslaan: melding bovenaan, de formulieren leeg (nieuwe sleutel) en alles opnieuw tekenen."""
    st.session_state["inv_melding"] = melding
    st.session_state["inv_versie"] = st.session_state.get("inv_versie", 0) + 1
    st.rerun()


def _inv_vakken_tekst(registraties):
    vakken = [vak for _id, vak, _w in registraties]
    return f"{'vak' if len(vakken) == 1 else 'vakken'} {', '.join(str(v) for v in vakken)}"


def _inv_tabel(rijen, kolommen, sleutel):
    """
    De invultabel: vaste kolommen (alleen lezen) en invulkolommen. kolommen = [(sleutel, kop, soort, invul)]
    met soort "tekst", "getal", "geheel", "ja/nee" of een lijst opties. Volgorde: vinkje, vak, de invulkolommen
    en daarna de rest, zodat je op een telefoon niet opzij hoeft te schuiven om in te vullen. Smalle kolommen
    met een vaste breedte (niet de hele pagina). Geeft de regels als dicts terug.
    """
    config = {"Kies": st.column_config.CheckboxColumn("✓", width=48, help="Meedoen met de waarde hierboven"),
              "id": None}
    breedte = 48
    for kolom, kop, soort, invul in kolommen:
        # Zo smal als de kop of de inhoud toelaat (± 7 px per letter in de kop; een invulkolom heeft er een
        # potloodje bij).
        basis = {"getal": 70, "geheel": 52, "ja/nee": 64}.get(soort, 72) if isinstance(soort, str) else 72
        px = max(basis, int(len(kop) * 7 + 26)) + 18 * invul   # soort kan een lijst opties zijn (rijpheid)
        breedte += px
        if soort == "getal":
            config[kolom] = st.column_config.NumberColumn(kop, min_value=0.0, step=0.1, format="%.1f", width=px)
        elif soort == "geheel":
            config[kolom] = st.column_config.NumberColumn(kop, min_value=0, step=1, format="%d", width=px)
        elif soort == "ja/nee":
            config[kolom] = st.column_config.CheckboxColumn(kop, width=px)
        elif isinstance(soort, list):
            config[kolom] = st.column_config.SelectboxColumn(kop, options=soort, width=px)
        else:
            config[kolom] = st.column_config.TextColumn(kop, width=px)
    df = pd.DataFrame(rijen)
    bewerkt = st.data_editor(df, key=sleutel, hide_index=True, width=breedte + 4, column_config=config,
                             column_order=["Kies", "vak"] + [k for k, _kop, _soort, invul in kolommen if invul]
                             + [k for k, _kop, _soort, invul in kolommen if not invul and k != "vak"],
                             disabled=[k for k, _kop, _soort, invul in kolommen if not invul],
                             # Een derde van de volle hoogte (hooguit ± 7 regels); de rest scroll je.
                             height=max(140, min(36 * (len(df) + 1) + 3, 800) // 3))
    return bewerkt.to_dict("records")


def _inv_florgib(vakken, datum):
    open_ = [r for r in vakken if r["lengte_half"] is None]
    if not open_:
        st.info("Alle lopende vakken hebben hun Florgib al. Wijzigen kan via Wijzigen.")
        return
    versie = st.session_state.get("inv_versie", 0)
    with st.form(f"inv_florgib_{versie}", border=False):
        st.caption("Voor alle aangevinkte vakken (een waarde in de tabel gaat voor):")
        k1, k2 = st.columns(2)
        lengte = k1.number_input("Lengte (cm)", min_value=0.0, format="%.1f")
        gram = k2.number_input("Florgib (g) per vak", min_value=0.0, step=0.5, format="%.1f")
        regels = _inv_tabel(
            [{"id": r["id"], "Kies": False, "vak": r["vak"], "pw": r["plantweek"],
              "geplant": format_datum(r["geplant"]),
              "verwacht": format_datum(r["florgib_verwacht"]) if r["florgib_verwacht"] else "",
              "lengte": float("nan"), "gram": float("nan")} for r in open_],
            [("vak", "Vak", "geheel", False), ("pw", "Pw", "geheel", False), ("geplant", "Geplant", "tekst", False),
             ("verwacht", "Verwacht", "tekst", False), ("lengte", "Lengte", "getal", True),
             ("gram", "Gram", "getal", True)], f"inv_florgib_tabel_{versie}")
        if st.form_submit_button("Opslaan", type="primary"):
            registraties = reg.te_registreren(regels, ["lengte", "gram"], {"lengte": lengte, "gram": gram})
            if not registraties:
                st.warning("Vink minstens één vak aan of vul een waarde in de tabel in.")
            elif reg.zonder(registraties, "lengte"):
                st.warning(f"Geen lengte voor vak {', '.join(map(str, reg.zonder(registraties, 'lengte')))}: vul die "
                           "in de tabel of boven de tabel in.")
            else:
                for teelt_id, _vak, w in registraties:
                    update_halverwege(teelt_id, datum, w["lengte"], gebruiker=huidige_gebruiker(),
                                      florgib_gram=w["gram"])
                _inv_klaar(f"Florgib opgeslagen voor {_inv_vakken_tekst(registraties)}.")


def _inv_emmers(vakken, datum):
    versie = st.session_state.get("inv_versie", 0)
    # Vakken in de oogst eerst, daarna op de verwachte oogst.
    volgorde = sorted(vakken, key=lambda r: (not r["emmers"], r["prognose"] or date.max, r["vak"]))
    with st.form(f"inv_emmers_{versie}", border=False):
        st.caption("Voor alle aangevinkte vakken (een waarde in de tabel gaat voor):")
        emmers = st.number_input("Emmers", min_value=0, step=1, width=180)
        regels = _inv_tabel(
            [{"id": r["id"], "Kies": False, "vak": r["vak"], "pw": r["plantweek"],
              "prognose": format_datum(r["prognose"]) if r["prognose"] else "",
              "tot_nu": int(r["emmers"]), "uitval": fmt_pct(r["uitval"]) if r["uitval"] is not None else "",
              "emmers": float("nan"), "afronden": False} for r in volgorde],
            [("vak", "Vak", "geheel", False), ("pw", "Pw", "geheel", False),
             ("prognose", "Prognose", "tekst", False), ("tot_nu", "Tot nu", "geheel", False),
             ("uitval", "Uitval", "tekst", False), ("emmers", "Emmers", "geheel", True),
             ("afronden", "Afronden", "ja/nee", True)], f"inv_emmers_tabel_{versie}")
        if st.form_submit_button("Opslaan", type="primary"):
            for r in regels:                       # alleen afronden telt ook als meedoen
                r["Kies"] = bool(r["Kies"]) or bool(r["afronden"])
            afronden = {int(r["id"]) for r in regels if r["afronden"]}
            registraties = reg.te_registreren(regels, ["emmers"], {"emmers": emmers})
            leeg = [vak for teelt_id, vak, w in registraties if not w["emmers"] and teelt_id not in afronden]
            if not registraties:
                st.warning("Vink minstens één vak aan of vul emmers in de tabel in.")
            elif leeg:
                st.warning(f"Geen emmers voor vak {', '.join(map(str, leeg))}: vul die in, of vink Afronden aan.")
            else:
                for teelt_id, _vak, w in registraties:
                    if w["emmers"]:
                        voeg_oogstregistratie_toe(teelt_id, datum, int(w["emmers"]), gebruiker=huidige_gebruiker())
                    if teelt_id in afronden:
                        markeer_teelt_afgerond(teelt_id, datum, gebruiker=huidige_gebruiker())
                tekst = f"Emmers opgeslagen voor {_inv_vakken_tekst(registraties)}"
                if afronden:
                    tekst += f"; afgerond: vak {', '.join(str(v) for i, v, _w in registraties if i in afronden)}"
                _inv_klaar(tekst + ".")
    # Corrigeren van eerdere oogstmomenten, per vak.
    in_oogst = [r for r in volgorde if r["emmers"]]
    if in_oogst:
        with layout.uitklap("Oogstmomenten van een vak aanpassen of verwijderen"):
            gekozen = st.selectbox("Vak", in_oogst, format_func=lambda r: f"Vak {r['vak']} · {r['code'] or '-'}",
                                   key="inv_oogstmomenten_vak", width=260)
            toon_oogstregistraties_beheer(gekozen["id"], get_teelt_by_id(gekozen["id"]))


def _inv_lengte(vakken):
    versie = st.session_state.get("inv_versie", 0)
    volgorde = sorted(vakken, key=lambda r: (not r["emmers"], r["vak"]))       # in de oogst eerst
    with st.form(f"inv_lengte_{versie}", border=False):
        st.caption("Voor alle aangevinkte vakken (een waarde in de tabel gaat voor):")
        k1, k2, k3 = st.columns([1, 1, 2])
        lengte = k1.number_input("Lengte (cm)", min_value=0.0, format="%.1f")
        gewicht = k2.number_input("Gewicht (g)", min_value=0, step=1)
        rijpheid = k3.select_slider("Rijpheid", options=RIJPHEID_OPTIES, value=(1, 4),
                                    help="1 = rauw, 4 = rijp. Zet beide punten gelijk voor één stadium.")
        regels = _inv_tabel(
            [{"id": r["id"], "Kies": False, "vak": r["vak"], "pw": r["plantweek"], "tot_nu": int(r["emmers"]),
              "nu": fmt_getal(r["lengte_eind"], 1) if r["lengte_eind"] else "",
              "lengte": float("nan"), "gewicht": float("nan"), "rijpheid": None} for r in volgorde],
            [("vak", "Vak", "geheel", False), ("pw", "Pw", "geheel", False),
             ("tot_nu", "Emmers", "geheel", False), ("nu", "Lengte nu", "tekst", False),
             ("lengte", "Lengte", "getal", True), ("gewicht", "Gewicht", "geheel", True),
             ("rijpheid", "Rijpheid", RIJPHEID_TEKSTEN, True)], f"inv_lengte_tabel_{versie}")
        if st.form_submit_button("Opslaan", type="primary"):
            registraties = reg.te_registreren(regels, ["lengte", "gewicht", "rijpheid"],
                                              {"lengte": lengte, "gewicht": gewicht,
                                               "rijpheid": rijpheid_bereik_naar_tekst(rijpheid)})
            mist = sorted(set(reg.zonder(registraties, "lengte") + reg.zonder(registraties, "gewicht")))
            if not registraties:
                st.warning("Vink minstens één vak aan of vul een waarde in de tabel in.")
            elif mist:
                st.warning(f"Lengte of gewicht ontbreekt voor vak {', '.join(map(str, mist))}.")
            else:
                for teelt_id, _vak, w in registraties:
                    update_oogst(teelt_id, w["lengte"], int(w["gewicht"]), w["rijpheid"],
                                 gebruiker=huidige_gebruiker())
                _inv_klaar(f"Lengte en gewicht opgeslagen voor {_inv_vakken_tekst(registraties)}.")


def _inv_opmerking(vakken, datum):
    """Een opmerking bij één of meer lopende vakken, bijv. een afwijking in de groei; terug te zien in het vak."""
    keuzes = {f"Vak {r['vak']} · pw {r['plantweek']}": r["id"] for r in sorted(vakken, key=lambda r: r["vak"])}
    with st.form(f"inv_opmerking_{st.session_state.get('inv_versie', 0)}", border=False):
        labels = st.multiselect("Vakken", list(keuzes))
        categorie = st.selectbox("Categorie", OPMERKING_CATEGORIEEN, width=260)
        tekst = st.text_area("Opmerking", height=160,
                             placeholder="Bijv. vak 12 blijft achter in lengte, bladpunten geel")
        if st.form_submit_button("Opslaan", type="primary"):
            if not labels:
                st.warning("Kies minstens één vak.")
            elif not tekst.strip():
                st.warning("Schrijf een opmerking.")
            else:
                voeg_opmerking_toe([keuzes[l] for l in labels], datum, categorie, tekst.strip(),
                                   gebruiker=huidige_gebruiker())
                _inv_klaar(f"Opmerking opgeslagen bij {len(labels)} {'vak' if len(labels) == 1 else 'vakken'}.")


def _inv_wijzigen():
    """Eén vak kiezen (week → vak → jaar) en per onderdeel wijzigen; het hele vak verwijderen staat apart."""
    alle_teelten = get_alle_teelten_voor_selectie()

    if alle_teelten:
        # Kiezen met drie losse velden (week → vak → jaar) in plaats van één
        # lange lijst; elk veld toont alleen wat bij de eerdere keuze bestaat.
        # Weken in de tijd (recentste onderaan); standaard de week van de
        # laatst gestarte teelt, en bij een week het meest recente jaar.
        k_week, k_vak, k_jaar, _ = st.columns([1, 1, 1.3, 4])
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

        for tab, onderdeel in zip(st.tabs(WIJZIG_ONDERDELEN), WIJZIG_ONDERDELEN):
            with tab:
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
                        st.caption("Nog geen opmerkingen bij dit vak. Maak er een via Opmerking.")
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
# _pagina.run() onderaan voert alleen die uit. Alles hierboven (login, tuinkeuze, gedeelde functies en
# caches) geldt voor alle pagina's.
styles.laad()

# --- NU: hoe staat elk vak ervoor ---
#
# De status per vak (gebruikt door de tijdlijn, het stookadvies en de vakpopup). Het rekenwerk staat in
# logic/vakstatus.py en logic/teeltprognose.py; hier alleen ophalen (één keer, gecachet).

# Status van een vak = de prognose t.o.v. plan in dagen bij de huidige stooklijn
# (logic/teeltprognose.dagen_klasse), schaal −7 … +7: te vroeg, op schema of te laat; als tekst in het vak.
NU_STATUS_KORT = {"b3": "ruim te vroeg", "b2": "te vroeg", "b1": "iets te vroeg", "n": "op schema",
                  "o1": "iets te laat", "o2": "te laat", "r1": "ruim te laat", "r2": "ruim te laat", "rijp": "oogstrijp",
                  "grijs": "geen prognose", "leeg": "leeg"}
_NU_PER_RUN = {}   # één keer rekenen per scriptrun (Overzicht, Teelt)


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
        _NU_PER_RUN["versie"] = versie
    return _NU_PER_RUN["alles"]


@st.cache_data(ttl=600, show_spinner=False)
def _nu_statussen(versie, dag, tuin_id):
    """
    {vak: vakstatus} van de lopende teelten van één tuin (lengte t.o.v. de referenties). Het zwaarste
    rekenwerk van Overzicht, dus op dezelfde sleutels gecachet als _nu_data; _nu_tuin zet er per run het
    teeltmodel bij.
    """
    vandaag = date.fromisoformat(dag)
    alle = _nu_data(versie, dag)["teelten"].to_dict("records")
    lopend = {}
    for t in alle:
        if t["tuin_id"] != tuin_id:
            continue
        start = vs.als_datum(t["datum_teelt_start"])
        if not vs.als_datum(t["datum_oogst"]) and start <= vandaag:
            if t["vaknummer"] not in lopend or start > vs.als_datum(lopend[t["vaknummer"]]["datum_teelt_start"]):
                lopend[t["vaknummer"]] = t
    basis = vs.referentiebasis(alle)
    return {vak: vs.beoordeel_teelt(t, alle, vandaag, bereken_verwachte_oogstdatum, basis)
            for vak, t in lopend.items()}


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
    statussen = _nu_statussen(_NU_PER_RUN["versie"], str(vandaag), tuin["id"])

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


def _nu_tijdlijn(s, water=None):
    """
    Planten → Florgib → plan en prognose (of de oogst) op één datumas, met vandaag als stippellijn en
    onderaan de watergift per dag als staafjes (water = [{datum, liter}]).
    """
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
    gift = pd.DataFrame([{"datum": pd.Timestamp(w["datum"]), "liter": float(w["liter"])}
                         for w in (water or []) if w.get("liter")])
    # Zonder watergift: de lijn in het midden, labels om en om erboven en eronder. Met watergift staan de
    # staafjes óp de lijn (omhoog, hoogte naar de gift) en komen de labels in twee rijen eronder.
    if gift.empty:
        hoogte, lijn_y, label_dy = 70, 34, (-15, 16)
    else:
        hoogte, lijn_y, label_dy = 100, 58, (15, 29)
    midden = alt.value(lijn_y)
    basis = alt.Chart(df)
    lijn = basis.mark_rule(color="#999").encode(x=alt.X("min(datum):T"), x2="max(datum):T", y=midden)
    stippen = basis.mark_point(size=110, filled=True).encode(
        x=as_x, y=midden,
        color=alt.Color("Soort:N", legend=None,
                        scale=alt.Scale(domain=["gedaan", "plan", "verwacht"], range=["#2e7d32", "#555", "#e67e22"])),
        shape=alt.Shape("Soort:N", legend=None,
                        scale=alt.Scale(domain=["gedaan", "plan", "verwacht"], range=["circle", "diamond", "circle"])),
        tooltip=[alt.Tooltip("Moment:N"), alt.Tooltip("datum:T", format="%d-%m-%y")],
    )
    rij1 = basis.transform_filter("datum.rij == 0").mark_text(dy=label_dy[0], fontSize=11).encode(
        x=as_x, y=midden, text="label:N")
    rij2 = basis.transform_filter("datum.rij == 1").mark_text(dy=label_dy[1], fontSize=11).encode(
        x=as_x, y=midden, text="label:N")
    lagen = []
    if not gift.empty:
        lagen.append(alt.Chart(gift).mark_bar(color="#5b9bd5", size=3).encode(
            x=alt.X("datum:T"),
            y=alt.Y("liter:Q", axis=None,
                    scale=alt.Scale(domain=[0, float(gift["liter"].max())], range=[lijn_y, lijn_y - 40])),
            y2=alt.value(lijn_y),
            tooltip=[alt.Tooltip("datum:T", title="Datum", format="%d-%m-%y"),
                     alt.Tooltip("liter:Q", title="Watergift (l/m²)", format=".1f")]))
    lagen += [lijn, stippen, rij1, rij2]
    if not oogst:
        lagen.append(alt.Chart(pd.DataFrame({"datum": [pd.Timestamp(date.today())]})).mark_rule(
            color="#888", strokeDash=[4, 3]).encode(x="datum:T"))
    st.altair_chart(alt.layer(*lagen).properties(height=hoogte).resolve_scale(y="independent"),
                    use_container_width=True)


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
                  {"datum": r.datum, "Reeks": "Berekende etmaaltemp.", "waarde": t_ideaal(r.lichtsom)}]
    if u and u["c"] is not None and s["plan"]:
        vandaag = date.today()
        for i in range(max((s["plan"] - vandaag).days, 0) + 1):
            dag, licht = vandaag + timedelta(days=i), u["L_verw"][min(i, len(u["L_verw"]) - 1)]
            rijen += [{"datum": str(dag), "Reeks": "Berekende etmaaltemp.", "waarde": t_ideaal(licht)},
                      {"datum": str(dag), "Reeks": "Doel (berekend + c)", "waarde": t_ideaal(licht) + u["c"]}]
    if not rijen:
        st.caption("Geen klimaatdata sinds planten.")
        return
    df = pd.DataFrame(rijen)
    stijl = {"Werkelijk": ("#c0392b", [1, 0]), "Berekende etmaaltemp.": ("#777", [6, 3]),
             "Doel (berekend + c)": ("#e67e22", [2, 2])}
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
    st.caption(f"Berekende etmaaltemperatuur = {formule_tekst()}."
               + (f" Doel = berekend + de benodigde correctie ({_nu_c_tekst(u)}) bij de gemiddelde lichtsom van "
                  "die kalenderweek, tot de plandatum." if u and u["c"] is not None else ""))


def toon_opmerkingen(teelt_id):
    """Opmerkingen van één vak in de vakpopup, oud naar nieuw, elk te wijzigen of te verwijderen."""
    opmerkingen = get_opmerkingen(teelt_id)
    st.write(f"**Opmerkingen** ({len(opmerkingen)})" if opmerkingen else "**Opmerkingen**")
    if not opmerkingen:
        st.caption("Nog geen opmerkingen. Voeg er een toe via Registreren → Opmerking.")
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
        vak_venster(rijen[gekozen[0]]["teelt_id"], vandaag)
    elif not gekozen:
        st.session_state[f"{sleutel}_open"] = None


OPM_LENGTES = ("Week", "Maand", "Kwartaal", "Jaar", "Alles")


def _pagina_opmerkingen_1():
    layout.pagina_kop(
        "Opmerkingen",
        wat="Alle opmerkingen bij vakken, oud naar nieuw.",
        lezen=["Filter op periode, teelt (plantweek), vak, categorie of een woord uit de tekst of de code. De tuin "
               "kies je bovenaan.",
               "Klik op een regel om het vak te openen; daar kun je een opmerking ook wijzigen of verwijderen.",
               "Nieuwe opmerkingen maak je via Registreren → Opmerking."],
        bron="Wat er via Registreren is ingevoerd, met de gebruiker die het invoerde.",
    )
    alle = _opm_alle(vakstatus_dataversie())
    if not alle:
        st.info("Nog geen opmerkingen. Maak er een via Registreren → Opmerking.")
        return
    vandaag = date.today()
    tuin_ids = {t["id"] for t in TUINEN if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE}
    in_tuin = [o for o in alle if o["tuin_id"] in tuin_ids]
    eerste = min((opm_logic._datum(o["datum"]) for o in alle), default=vandaag)

    balk = layout.filterbalk("opmerkingen")
    lengte, periode = filters.periode(
        "opm_periode", OPM_LENGTES, "Alles",
        opties_van=lambda n: [] if n == "Alles" else perioden.reeks(eerste, vandaag, n),
        standaard_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(vandaag, n)[0],
        format_van=lambda n: lambda k: perioden.periode_label(k, n),
        huidig_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(vandaag, n)[0], plek=balk)
    van, tot = perioden.periode_grenzen(periode, lengte) if periode else (None, None)
    teelten = filters.keuzes("Teelt (plantweek)", sorted({opm_logic.teelt_van(o) for o in in_tuin}), "opm_teelt",
                             plek=balk, format_func=_teelt_label, placeholder="Alle teelten")
    vakken = filters.keuzes("Vak", sorted({o["vaknummer"] for o in in_tuin}), "opm_vak", plek=balk,
                            placeholder="Alle vakken")
    categorieen = filters.keuzes("Categorie", OPMERKING_CATEGORIEEN, "opm_categorie", plek=balk)
    zoek = filters.zoekveld("opm_zoek", "Woord uit de tekst of code", plek=balk)

    rijen = opm_logic.filter_opmerkingen(
        alle, tuinen=tuin_ids, teelten=set(teelten), vakken=set(vakken), van=van, tot=tot,
        categorieen=set(categorieen), zoek=zoek)
    layout.sectie("Opmerkingen", f"{len(rijen)} van {len(in_tuin)}")
    toon_opmerkingenlijst(rijen, "opm_lijst", "Geen opmerkingen die aan de filters voldoen.")
    if rijen:
        layout.export(excel_bestand({"Opmerkingen": pd.DataFrame([{
            "Datum": opm_logic._datum(o["datum"]), "Tuin": _tuinnaam_van.get(o["tuin_id"], "?"),
            "Afd.": o["afdeling"], "Vak": o["vaknummer"], "Code": o["code"] or "-",
            "Teelt": _teelt_label(opm_logic.teelt_van(o)), "Categorie": o["categorie"] or "Overig",
            "Opmerking": o["tekst"], "Door": o["gebruiker"] or "-"} for o in rijen])}),
            f"opmerkingen_{vandaag:%d-%m-%y}.xlsx", sleutel="opm_excel")


def teelt_detail(s, klimaat, water, model=None):
    """
    De hele teelt van één vak: tijdlijn, voortgang (lopend), klimaat tegen de
    lichtlijn, lichtsom, watergift per dag, groei en stek. Voor lopende teelten
    (s["stook"] uit het teeltmodel) en afgeronde (s["teelt"]["datum_oogst"]).
    - s: een vakstatus-dict (logic.vakstatus.beoordeel_teelt) met "stook" (of None)
    - klimaat: DataFrame met datum, temp_24h, lichtsom van de afdeling sinds planten
    - water: [{datum, liter}] van het vak sinds planten (als staafjes op de tijdlijn)
    """
    t, u = s["teelt"], s.get("stook")
    _nu_tijdlijn(s, water)
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
    if not vs.als_datum(t["datum_oogst"]):
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


def _pagina_overzicht():
    """
    Overzicht = de tijdlijn per vak met de bespuitingen en de watergift, in drie weergaven (Standaard,
    Bespuitingen, Watergift), daaronder het plannen in openklapmenu's en het vakkenregister. Vroeger de losse
    pagina's Teeltoverzicht, Planning en Watergift.
    """
    vandaag = date.today()
    layout.pagina_kop(
        "Overzicht",
        wat="Per vak hoe de teelt ervoor staat en wat er gepland staat: de tijdlijn in teeltvolgorde, met per dag "
            "de bespuitingen en de watergift. Daaronder het plannen (concepttabel, jaarplanning, "
            "overzicht per plantweek, vooruitblik) en het vakkenregister: alle vakken als lopend, te starten of "
            "afgerond.",
        lezen=[
            "**Tijdlijn**: per vak één regel. Weken lopen van zondag t/m zaterdag; bovenaan het weeknummer en "
            "daaronder de weekdag en de datum. De lopende teelt is groen tot vandaag en loopt daarna doorzichtig "
            "door tot de prognose-oogst; per teelt (plantweek) wisselen donker en licht; het zwarte streepje is de "
            "plan-oogst. Hoeveel de prognose voor of achter loopt op plan staat in het vak (klik op de balk).",
            "**Weergave** *Standaard*: een driehoekje bovenin de balk op elke dag met een behandeling (kleur = "
            "soort) en een blauw vakje op elke dag met water, met het aantal l/m² erin "
            "(met een decimaal als de dag breed genoeg is, anders in hele liters; past er niets, klik dan op het "
            "vakje; dat hangt af van de periode en de breedte van het scherm).",
            "*Bespuitingen*: grotere driehoekjes met de afkortingen van de middelen erachter, zoals in de "
            "klimaatregistratie (bijv. Ri = Rizolex, B5 = Biota 500; ingekort tot wat er past tot de "
            "volgende behandeling; klik voor de volledige namen en doseringen); de watergift als dun streepje "
            "onderin.",
            "Bij Standaard en Watergift staat achter het vaknummer het totaal gegoten van de lopende teelt sinds het "
            "planten (l/m², bijv. Vak 2 · 145).",
            "*Watergift*: per vak drie regels: de liters (l/m²) en daaronder de EC en pH van de gift van dat vak; "
            "bovenaan de EC van de voorregeling (het uitgangswater vóór bemesting). EC/pH sinds 27-09-26.",
            "*Waarnemingen*: bovenaan per insect de tellingen van PATS voor de hele tuin: het aantal nieuwe insecten "
            "op alle vangplaten (Trap-Eye, ± 3 foto's per week: trips) of in de insectensensoren (PATS-C, per dag "
            "van 12 tot 12 uur: turkse mot); een grijs getal = 0. Onder elk vak de regel *plaat*: de nieuwe trips "
            "op de Trap-Eye(s) naast dat vak (een plaat hangt tussen twee vakken en telt voor allebei). In de balk "
            "de gewasmetingen: de lengte bij de Florgib en de eindmeting (lengte · gewicht · rijpheid) op de dag "
            "dat ze geregistreerd is. Klik op een getal voor de telling per plaat, op een meting voor het vak.",
            "Klik op een balk voor het vak, op een driehoekje voor de middelen, op een watergift voor alle "
            "gietbeurten van die dag, op een concept om het te verschuiven, te starten als teelt of te verwijderen, "
            "en op een lege plek in een vakregel (vanaf deze week) om daar een concept te plannen.",
            f"**Prognose** = oogst als de afdeling blijft stoken zoals de laatste {AFWIJKING_VENSTER_DAGEN} dagen.",
            "**Plannen**: de concepttabel is voor veel concepten tegelijk (startdatum, Bevestigen, Verwijderen, "
            "daarna Wijzigingen opslaan); in de jaarplanning vul je per week in hoeveel vakken je wilt poten en "
            "plan je opnieuw. Plannen werkt per tuin: bij Beide de laatst gekozen tuin.",
            "In het register opent een klik op een regel het vak.",
        ],
        bron="Watergift: Priva (API), elke ochtend opgehaald. Behandelingen: Agro4all, daarvoor de "
             "klimaatregistratie. Insectentellingen: PATS, elk uur opgehaald (tuin 1: nog alleen de twee PATS-C's). Het teeltmodel telt per dag een deel van de teelt af, afhankelijk van de "
             "lichtsom binnen en de "
             f"afwijking van de lichtlijn ({formule_tekst()}), met een correctie per tuin. Het leert van alle "
             "afgeronde vakken (historie uit de klimaatregistratie plus wat in de app is afgerond). Na de Florgib "
             "wordt de voortgang gelijkgezet op het deel waarop meestal gespoten wordt. De planner plant vooruit "
             "vanaf waar de huidige teelt van elk vak en de bestaande concepten gebleven zijn, met het aantal vakken "
             f"per week uit de jaarplanning (nooit meer dan {MAX_VAKKEN_PER_WEEK} per week); tuin 3: vak 19+20 als "
             "één eenheid, vak 1 op een eigen ritme. Oogst van concepten = de teeltduur-tabel.",
        kleuren="Groen = lopend, doorzichtig groen = verwacht tot de prognose-oogst, grijs = afgerond; per teelt "
                "(plantweek) om en om donker en licht. "
                "Grijze rand = bevestigd maar nog niet geplant, blauwe stippelrand = concept, "
                "rode stippelrand = overlapt met een andere ronde, zwarte stippelrand = Florgib meer dan "
                f"{FLORGIB_ACHTERSTAND_DAGEN} dagen over tijd, paarse stip/ring = (verwachte) Florgib, rode "
                "stippellijn = vandaag. Driehoekje: rood = gewasbescherming, groen = biologie, bruin = voeding. "
                "Blauw streepje = watergift.",
    )
    if st.session_state.get("tl_melding"):
        st.success(st.session_state.pop("tl_melding"))

    data, model, stook, afwijking = _nu_alles(vandaag)
    if model is None:
        st.warning("Nog geen teelthistorie in de database: draai importeer_teelt_historie.py. "
                   "Tot die tijd geen prognose en geen correctie.")
    tuinen = [t for t in sorted(TUINEN, key=lambda t: t["nummer"])
              if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE]
    infos = [_nu_tuin(data, model, stook, afwijking, t, vandaag) for t in tuinen]

    balk = layout.filterbalk("overzicht")
    van, tot, weken = _tl_periode(balk, vandaag)
    weergave = filters.weergave("Weergave", TL_WEERGAVEN, "ov_weergave", TL_WEERGAVEN[0], plek=balk)
    # Altijd alle afdelingen, in teeltvolgorde (zonder kopregels per afdeling).
    afdelingen = {i["tuin"]["id"]: {int(a) for a in i["vakken"]["afdeling"].dropna()} for i in infos}

    layout.sectie("Tijdlijn")
    water = _tl_toon(infos, afdelingen, van, tot, weken, vandaag, weergave)
    _tl_legenda(weergave)
    if weergave == "Watergift" and weken > 4:
        uitleg_help.voetnoot("Grijze blokjes bij EC en pH: het getal past niet in een dag; klik erop of kies 4 wk "
                             "voor alle getallen.")

    _planning_uitklappen(vandaag)
    toon_vakkenregister(vandaag, TUIN_WEERGAVE, afdelingen)
    for tuin, tabel in water:
        eind = min(tot, vandaag)
        layout.export(_wg_excel(tabel, tuin, van, eind),
                      f"watergift_{tuin['naam'].replace(' ', '_').lower()}_{van:%d-%m-%y}_{eind:%d-%m-%y}.xlsx",
                      f"Excel watergift ({tuin['naam']})" if len(water) > 1 else "Excel watergift",
                      sleutel=f"ov_water_excel_{tuin['id']}")


# --- TIJDLIJN: vakkenmatrix, strokenplanning en watergift in één beeld (Overzicht) ---
#
# Per vak één regel op een tijdlijn: afgeronde teelten (grijs), de lopende
# teelt tot vandaag in de statuskleur van de vakkenmatrix en daarna licht tot
# de prognose, bevestigde teelten die nog moeten beginnen (rand) en concepten
# (blauwe stippelrand). De vakken staan in teeltvolgorde. Per dag de bespuitingen
# (driehoekjes) en de watergift (blauwe vakjes); de weergave Bespuitingen of Watergift
# toont daar meer van (middelen; EC/pH per vak en de voorregeling).
# Rekenwerk in logic/tijdlijn.py en logic/watergift.py.
# Lopend groen, afgerond grijs; per teelt (plantweek) om en om donker en licht, zodat je ziet waar de ene teelt
# ophoudt en de volgende begint. De prognose t.o.v. plan staat in het vak (klik op de balk).
TL_LOPEND = ("#9fc58c", "#cbe1bf")
TL_AFGEROND_TINT = ("#a8a8a3", "#cacac5")
TL_CONCEPT, TL_FLORGIB, TL_ROOD = "#2a78d6", "#8e44ad", "#e34948"


def _tl_tint(start):
    """0 of 1, om en om per plantweek (ISO-week van de plantdatum), ook over de jaargrens heen."""
    return ((start - timedelta(days=start.weekday())).toordinal() // 7) % 2
TL_VENSTERS = {"4 wk": 4, "3 mnd": 13, "6 mnd": 26, "1 jaar": 52}
TL_WEERGAVEN = ["Standaard", "Bespuitingen", "Watergift", "Waarnemingen"]
TL_WATER = "#2a6fb5"           # watergift: blauw, dekking naar de liters
TL_WATER_LICHT = "#9cc4ec"     # watergift in de weergave Bespuitingen: licht blauw, zodat de middelen opvallen
TL_PATS, TL_PATS_NUL = "#6b4f2a", "#b5b5b0"   # PATS-tellingen (weergave Waarnemingen): bruin, 0 in grijs
TL_METING = "#1f1f1f"                            # gewasmetingen (weergave Waarnemingen)
TL_RIJ = 22   # hoogte van een regel (px)
TL_RIJ_PLAAT = 12   # de regel "plaat" onder een vak (weergave Waarnemingen) is lager


def _tl_rij_hoogte(regel):
    return TL_RIJ_PLAAT if regel.startswith("§val") else TL_RIJ


def _tl_label(regel, met_totaal):
    """De tekst links van een regel: "Vak 2 · 145" (watergift), EC/pH, "plaat", niets bij andere §-regels."""
    if regel in met_totaal:
        return met_totaal[regel]
    for begin, tekst in (("§ec", "EC"), ("§ph", "pH"), ("§val", "plaat"), ("§", "")):
        if regel.startswith(begin):
            return tekst
    return regel


def _tl_stap(weken):
    """Om de hoeveel weken een weeknummer en een oogsttotaal: elke week bij 3 mnd, anders per 2 of 4 weken."""
    return 1 if weken <= 13 else 2 if weken <= 26 else 4


def _tl_venster_label(zondag, weken):
    eind = zondag + timedelta(weeks=weken) - timedelta(days=1)
    return f"wk {kalender.weeknummer(zondag)} – wk {kalender.weeknummer(eind)} '{eind:%y}"


def _tl_frames(info, afdelingen, van, tot, vandaag, weken, weergave):
    """
    De DataFrames voor de grafiek van één tuin: (balken, randen, florgib, plan, kopteksten, weeknummers, dagen,
    behandelingen, watergift, waarden), de volgorde van de regels (y): de vakken in teeltvolgorde, bij de
    weergave Watergift met onder elk vak een regel EC ("§ec<vak>") en pH ("§ph<vak>") en bovenaan "EC voorr.",
    bij de weergave Waarnemingen bovenaan een regel per insect met PATS-tellingen (frame "plagen") en onder elk
    vak met een Trap-Eye een regel "plaat" ("§val<vak>", frame "vangst"), en de gewasmetingen (frame "metingen");
    de stukken en (Excel-tabel watergift, watergiftdata voor het dagvenster).
    """
    tuin = info["tuin"]
    eigen = [t for t in info["alle"] if t["tuin_id"] == tuin["id"]]
    concepten = get_planning(tuin["id"])
    stukken = tijdlijn.stukken(eigen, info["statussen"], concepten, vandaag, _plandatum)
    vak_afd = {int(v): int(a) for v, a in zip(info["vakken"]["vaknummer"], info["vakken"]["afdeling"]) if a == a}

    stap = _tl_stap(weken)
    waarnemingen = weergave == "Waarnemingen"
    volgorde, kopteksten = ["Week", "Dag", "Datum"], []
    for afdeling in sorteer_afdelingen(set(vak_afd.values()), tuin["nummer"]):
        if afdelingen is not None and afdeling not in afdelingen:
            continue
        for vak in sorted(v for v, a in vak_afd.items() if a == afdeling):
            volgorde += [f"Vak {vak}"] + ([f"§ec{vak}", f"§ph{vak}"] if weergave == "Watergift" else
                                          [f"§val{vak}"] if waarnemingen and tuin["nummer"] in PATS_TRAPEYE_VAKKEN
                                          else [])
    if weergave == "Watergift":
        volgorde.insert(3, "EC voorr.")
    plagen = _tl_plagen(tuin["id"], van, min(tot, vandaag)) if waarnemingen else pd.DataFrame()
    if not plagen.empty:
        volgorde[3:3] = list(dict.fromkeys(plagen["y"]))
    zichtbaar = set(volgorde)

    def periode(s):
        return f"{format_datum(s['start'])} → {format_datum(s['eind'])}"

    balken, randen = [], []
    # Onder de balken per vak per week (vanaf deze week) een onzichtbaar vakje: een klik op een lege plek
    # plant daar een concept. Waar een balk ligt, vangt de balk de klik.
    eerste_week = max(van, kalender.week_begin(vandaag))
    for y in volgorde:
        if not y.startswith("Vak "):
            continue
        for i in range((tot - eerste_week).days // 7 + 1):
            zo = eerste_week + timedelta(weeks=i)
            balken.append({"y": y, "start": zo, "eind": min(zo + timedelta(days=7), tot), "kleur": "#000000",
                           "dekking": 0.001, "lijn": 0, "sleutel": f"n:{y[4:]}:{zo.isoformat()}", "Wat": "lege plek",
                           "Periode": f"wk {kalender.weeknummer(zo)}", "Toelichting": "Klik om hier een concept te plannen"})
    namen = {"afgerond": "afgerond", "lopend": "lopend", "prognose": "lopend, tot de prognose",
             "gepland": "bevestigd, nog niet geplant", "concept": "concept"}
    # De plantdatum per teelt (het stuk "prognose" begint vandaag, niet bij het planten).
    plantdag = {s["teelt_id"]: s["start"] for s in stukken if s.get("teelt_id") and s["soort"] != "prognose"}
    for s in stukken:
        y = f"Vak {s['vak']}"
        if y not in zichtbaar or s["eind"] < van or s["start"] > tot:
            continue
        tint = _tl_tint(plantdag.get(s.get("teelt_id"), s["start"]))
        status = info["statussen"].get(s["vak"])
        toelichting = s.get("code") or ""
        if s["soort"] in ("lopend", "prognose") and status:
            toelichting = _nu_bloktip(s["vak"], status, info["gepland"].get(s["vak"]),
                                      info["laatste_oogst"].get(s["vak"]), info)
        rij = {"y": y, "start": max(s["start"], van), "eind": min(s["eind"], tot), "Wat": namen[s["soort"]],
               "Periode": periode(s), "Toelichting": toelichting,
               "sleutel": f"c:{s['concept_id']}" if s["soort"] == "concept" else f"t:{s['teelt_id']}"}
        if s["soort"] == "afgerond":
            balken.append({**rij, "kleur": TL_AFGEROND_TINT[tint], "dekking": 1.0})
        elif s["soort"] == "lopend":
            balken.append({**rij, "kleur": TL_LOPEND[tint], "dekking": 1.0})
            if status and status.get("florgib_achter"):
                randen.append({**rij, "rand": "#1f1f1f", "streep": "florgib"})
        elif s["soort"] == "prognose":
            balken.append({**rij, "kleur": TL_LOPEND[tint], "dekking": 0.45})
        elif s["soort"] == "gepland":
            balken.append({**rij, "kleur": "#808080", "dekking": 0.12})
            randen.append({**rij, "rand": "#6f6f6a", "streep": "vol"})
        else:
            balken.append({**rij, "kleur": TL_CONCEPT, "dekking": 0.12})
            randen.append({**rij, "rand": TL_CONCEPT, "streep": "concept"})
    for o in tijdlijn.overlap(stukken):
        y = f"Vak {o['vak']}"
        if y in zichtbaar and o["eind"] >= van and o["start"] <= tot:
            randen.append({"y": y, "start": max(o["start"], van), "eind": min(o["eind"], tot),
                           "rand": TL_ROOD, "streep": "overlap"})

    florgib, plan = [], []
    for vak, s in info["statussen"].items():
        y = f"Vak {vak}"
        if y not in zichtbaar:
            continue
        u = s.get("stook")
        if s.get("florgib"):
            florgib.append({"y": y, "x": s["florgib"], "soort": "geregistreerd",
                            "Florgib": f"geregistreerd {format_datum(s['florgib'])}"})
        elif u and u.get("florgib_verwacht"):
            florgib.append({"y": y, "x": u["florgib_verwacht"], "soort": "verwacht",
                            "Florgib": f"verwacht {format_datum(u['florgib_verwacht'])}"})
        if s.get("plan"):
            plan.append({"y": y, "x": s["plan"], "Plan-oogst": format_datum(s["plan"])})
    florgib = [f for f in florgib if van <= f["x"] <= tot]
    plan = [p for p in plan if van <= p["x"] <= tot]

    # Het weeknummer per blok van `stap` weken (zondag t/m zaterdag): bij één week midden in de week, bij meer
    # weken links in het blok, vanaf de weeklijn van de eerste week.
    plek = timedelta(days=3, hours=12) if stap == 1 else timedelta(hours=10)

    def blok_start(i):
        return van + timedelta(weeks=i * stap)

    # Onder de weeknummers per dag de weekdag (regel "Dag") en het dagnummer (regel "Datum").
    dagnamen = [{"y": regel, "x": pd.Timestamp(dag) + pd.Timedelta(hours=12), "vandaag": dag == vandaag,
                 "tekst": _DAGEN_KORT[dag.weekday()] if regel == "Dag" else str(dag.day)}
                for dag in wg.dagen(van, tot) for regel in ("Dag", "Datum")]
    weeknummers = [{"y": "Week", "x": blok_start(i) + plek, "tekst": str(kalender.weeknummer(blok_start(i)))}
                   for i in range((tot - van).days // (7 * stap) + 1)]
    balken = pd.DataFrame(balken)
    balken["lijn"] = balken["lijn"].fillna(0.12)   # dunne rand om elke balk, niet om lege plekken
    frames = [balken] + [pd.DataFrame(x) for x in (randen, florgib, plan, kopteksten, weeknummers, dagnamen)]
    water, waarden, tabel, wgdata = _tl_watergift(tuin, volgorde, van, min(tot, vandaag), weergave == "Watergift")
    if waarnemingen:
        water = pd.DataFrame()
        vangst = _tl_vangst(tuin, volgorde, van, min(tot, vandaag))
        metingen = _tl_metingen(tuin["id"], volgorde, van, tot)
    else:
        vangst = metingen = pd.DataFrame()
    return (volgorde, frames + [_tl_behandelingen(tuin["id"], volgorde, van, tot), water, waarden, plagen, vangst,
                                metingen], stukken,
            (tabel, wgdata, _tl_water_totaal(tuin, info["statussen"], vandaag)))


def _tl_water_totaal(tuin, statussen, vandaag):
    """{vak: l/m²}: de totale watergift van de lopende teelt per vak, van het planten t/m vandaag."""
    starts = {int(vak): s["start"] for vak, s in statussen.items() if s.get("start")}
    if not starts:
        return {}
    d = _wg_data(tuin["id"], min(starts.values()), vandaag, vakstatus_dataversie())
    totaal = {}
    for r in d["gift"]:
        vak, dag = int(r["vaknummer"]), wg.als_datum(r["datum"])
        if vak in starts and starts[vak] <= dag <= vandaag and r["liter_per_m2"]:
            totaal[vak] = totaal.get(vak, 0.0) + r["liter_per_m2"]
    return totaal


def _tl_watergift(tuin, volgorde, van, tot, met_ecph=False):
    """
    Per vak per dag met watergift één vakje (dekking naar de liters, met het getal), met_ecph: ook de EC en pH
    van de gift per vak en de EC van de voorregeling als tekst ("waarden"). Plus de tabel vak × dag voor Excel
    en de watergiftdata (voor het dagvenster).
    """
    d = _wg_data(tuin["id"], van, tot, vakstatus_dataversie()) if van <= tot else {
        "gift": [], "kwaliteit": [], "beurten": []}
    zichtbaar = set(volgorde)
    gegeven = [r for r in d["gift"] if r["liter_per_m2"] and f"Vak {int(r['vaknummer'])}" in zichtbaar]
    rijen, waarden, tabel = [], [], {}
    for r in gegeven:
        dag, vak, liter = wg.als_datum(r["datum"]), int(r["vaknummer"]), r["liter_per_m2"]
        beurten = f" in {r['beurten']} beurt{'en' if r['beurten'] != 1 else ''}" if r["beurten"] else ""
        ecph = (f" · EC {fmt_getal(r['ec'], 2)} · pH {fmt_getal(r['ph'], 2)}" if r.get("ec") is not None else "")
        rijen.append({"y": f"Vak {vak}", "start": pd.Timestamp(dag), "eind": pd.Timestamp(dag + timedelta(days=1)),
                      "x": pd.Timestamp(dag) + pd.Timedelta(hours=12), "tekst": fmt_kort(liter, 1),
                      "heel": str(int(liter + 0.5)),
                      "sleutel": f"w:{vak}:{dag.isoformat()}",
                      "Watergift": f"{DAGEN_KORT_WG[dag.weekday()]} {format_datum(dag)} · {fmt_getal(liter, 1)} l/m²"
                                   f"{beurten}{ecph} · klik voor alle gietbeurten van die dag"})
        tabel.setdefault(vak, {})[dag] = liter
        if met_ecph and r.get("ec") is not None:
            for regel, waarde, dec in ((f"§ec{vak}", r["ec"], 2), (f"§ph{vak}", r["ph"], 1)):
                if waarde is not None and regel in zichtbaar:
                    waarden.append({"y": regel, "x": pd.Timestamp(dag) + pd.Timedelta(hours=12),
                                    "tekst": fmt_getal(waarde, dec), "kort": fmt_getal(waarde, 1),
                                    "sleutel": f"w:{vak}:{dag.isoformat()}",
                                    "Watergift": rijen[-1]["Watergift"]})
    if met_ecph:
        # De voorregeling: EC van het uitgangswater vóór bemesting, per dag voor de hele tuin.
        voorregeling = {}
        for k in d["kwaliteit"]:
            if k.get("ec_aanvoer") is not None:
                voorregeling.setdefault(wg.als_datum(k["datum"]), k["ec_aanvoer"])
        for dag, ec in sorted(voorregeling.items()):
            if van <= dag <= tot:
                waarden.append({"y": "EC voorr.", "x": pd.Timestamp(dag) + pd.Timedelta(hours=12),
                                "tekst": fmt_getal(ec, 2), "kort": fmt_getal(ec, 1), "sleutel": f"w:0:{dag.isoformat()}",
                                "Watergift": f"{DAGEN_KORT_WG[dag.weekday()]} {format_datum(dag)} · EC voorregeling "
                                             f"(uitgangswater vóór bemesting) {fmt_getal(ec, 2)} mS/cm"})
    dagen = wg.dagen(van, tot) if van <= tot else []
    excel = pd.DataFrame([{"Vak": vak, **{format_datum(dag): tabel.get(vak, {}).get(dag) for dag in dagen}}
                          for vak in (int(y[4:]) for y in volgorde if y.startswith("Vak "))])
    return pd.DataFrame(rijen), pd.DataFrame(waarden), excel, d


def _tl_behandelingen(tuin_id, volgorde, van, tot):
    """
    Per vak per dag met behandelingen één punt: kleur = de hoofdsoort, klik = de middelen. "Middelen" = de
    middelen kort en "ruimte" = het aantal dagen tot de volgende behandeling in dat vak: de grafiek kort de
    middelen in tot wat er op het scherm past (weergave Bespuitingen).
    """
    zichtbaar = set(volgorde)
    per = wg.behandelingen_per_vak_dag(_behandelingen(tuin_id, van, tot))
    dagen_per_vak = {}
    for vak, dag in per:
        dagen_per_vak.setdefault(vak, []).append(dag)
    rijen = []
    for (vak, dag), regels in sorted(per.items()):
        if f"Vak {vak}" not in zichtbaar:
            continue
        soort = wg.hoofdsoort(regels)
        volgende = min([d for d in dagen_per_vak[vak] if d > dag] or [tot + timedelta(days=1)])
        rijen.append({"x": pd.Timestamp(dag) + pd.Timedelta(hours=12), "y": f"Vak {vak}",
                      "kleur": wg.BEHANDELING_KLEUR.get(soort, "#777"), "sleutel": f"b:{vak}:{dag.isoformat()}",
                      "Middelen": wg.middelen_kort(regels), "ruimte": (volgende - dag).days,
                      "Behandeling": f"{format_datum(dag)} · " + "; ".join(wg.behandeling_tekst(r) for r in regels)})
    return pd.DataFrame(rijen)


@st.cache_data(ttl=600, show_spinner=False)
def _pats_tellingen(tuin_id, van, tot):
    """PATS-tellingen van een tuin over van..tot; tien minuten bewaard (de import draait elk uur)."""
    return get_pats_tellingen(tuin_id, van, tot)


def _tl_plagen(tuin_id, van, tot):
    """
    Weergave Bespuitingen: per insect (regel "y" = de naam) en dag met een PATS-telling het aantal nieuwe
    insecten van de hele tuin (logic/pats.dagtotalen), als getal; klik = de telling per vangplaat of sensor.
    """
    rijen = []
    for d in pats_logic.dagtotalen(_pats_tellingen(tuin_id, van, tot) if van <= tot else []):
        dag = d["datum"]
        rijen.append({"y": d["insect"], "x": pd.Timestamp(dag) + pd.Timedelta(hours=12),
                      "tekst": fmt_kort(d["totaal"], 1), "nul": d["totaal"] == 0,
                      "sleutel": f"p:{d['klasse_id']}:{dag.isoformat()}"})
    return pd.DataFrame(rijen)


def _tl_vangst(tuin, volgorde, van, tot):
    """
    Weergave Waarnemingen: onder elk vak (regel "§val<vak>") per fotodag de nieuwe vangst op de Trap-Eye(s) naast
    het vak (logic/pats.per_vak, "T3 M1"); "ruimte" = dagen tot de volgende foto, voor het inkorten.
    """
    verschuiving = PATS_TRAPEYE_VAKKEN.get(tuin["nummer"])
    zichtbaar = {int(y[4:]) for y in volgorde if y.startswith("§val")}
    if not verschuiving or not zichtbaar or van > tot:
        return pd.DataFrame()
    per = pats_logic.per_vak(_pats_tellingen(tuin["id"], van, tot), verschuiving, zichtbaar)
    dagen = {}
    for r in per:
        dagen.setdefault(r["vak"], []).append(r["datum"])
    rijen = []
    for r in per:
        dag = r["datum"]
        volgende = min([d for d in dagen[r["vak"]] if d > dag] or [tot + timedelta(days=1)])
        tekst = pats_logic.kort(r["nieuw"])
        rijen.append({"y": f"§val{r['vak']}", "x": pd.Timestamp(dag), "xm": pd.Timestamp(dag) + pd.Timedelta(hours=12),
                      "tekst": tekst, "nul": tekst == "0",
                      "ruimte": (volgende - dag).days, "sleutel": f"v:{r['vak']}:{dag.isoformat()}"})
    return pd.DataFrame(rijen)


@st.cache_data(ttl=600, show_spinner=False)
def _gewasmetingen(tuin_id, van, tot, versie):
    """Gewasmetingen van een tuin; `versie` (vakstatus_dataversie) is alleen de cachesleutel."""
    return get_gewasmetingen(tuin_id, van, tot)


def _tl_metingen(tuin_id, volgorde, van, tot):
    """
    Weergave Waarnemingen: de gewasmetingen in de balk van het vak: de lengte bij de Florgib (op de Florgibdag)
    en de eindmeting (lengte · gewicht · rijpheid) op de dag dat ze geregistreerd is; klik = het vak.
    """
    zichtbaar = set(volgorde)
    rijen = []
    for m in _gewasmetingen(tuin_id, van, tot, vakstatus_dataversie()):
        y = f"Vak {m['vaknummer']}"
        if y not in zichtbaar:
            continue
        sleutel = f"t:{m['id']}"
        florgib = vs.als_datum(m["datum_half"])
        if florgib and m["lengte_half"] and van <= florgib <= tot:
            rijen.append({"y": y, "x": pd.Timestamp(florgib) + pd.Timedelta(hours=12), "soort": "florgib",
                          "tekst": f"{fmt_kort(m['lengte_half'], 1)} cm", "sleutel": sleutel})
        if m["lengte_eind"] or m["oogstgewicht"]:
            gemeten = m["gemeten_op"]
            dag = (gemeten.astimezone(_NL_TIJD).date() if gemeten else
                   vs.als_datum(m["eerste_emmers"]) or vs.als_datum(m["datum_oogst"]))
            if dag and van <= dag <= tot:
                delen = ([f"{fmt_kort(m['lengte_eind'], 1)} cm"] if m["lengte_eind"] else []) + (
                    [f"{fmt_getal(m['oogstgewicht'], 0)} g"] if m["oogstgewicht"] else []) + (
                    [f"R{m['rijpheid']}"] if m.get("rijpheid") else [])
                rijen.append({"y": y, "x": pd.Timestamp(dag) + pd.Timedelta(hours=12), "soort": "eind",
                              "tekst": " · ".join(delen), "sleutel": sleutel})
    return pd.DataFrame(rijen)


def _tl_grafiek(volgorde, frames, van, tot, vandaag, weken, weergave, water_totaal=None):
    """
    De Altair-grafiek van één tuin in de weergave Standaard, Bespuitingen of Watergift. Klikbaar: de balken
    ('tl_klik'), de behandelingen ('tl_beh', 'tl_btekst'), de watergift ('tl_water', 'tl_wtekst', 'tl_ecph') en
    de PATS-tellingen ('tl_pats', 'tl_pats_blok', 'tl_vangst', 'tl_vangst_blok') en de gewasmetingen
    ('tl_meting');
    elke laag een eigen selectie (dezelfde selectie op twee lagen geeft een dubbel signaal in Vega).
    water_totaal ({vak: l/m²}): achter het vaknummer het totaal gegoten van de lopende teelt ("Vak 2 · 145").
    """
    (balken, randen, florgib, plan, kopteksten, weeknummers, dagnamen, behandelingen, water, waarden, plagen, vangst,
     metingen) = frames
    # Hoe breed een dag op het scherm is, weet alleen de grafiek zelf ("width" = de breedte van het
    # tekenvlak). Getallen en middelen kiezen daarop wat er past: volledig, korter of niets.
    px = f"(width / {(tot - van).days + 1})"
    schaal = alt.Scale(domain=[pd.Timestamp(van).isoformat(), pd.Timestamp(tot).isoformat()])
    met_totaal = {f"Vak {v}": f"Vak {v} · {fmt_getal(t, 0)}" for v, t in (water_totaal or {}).items()}
    x = alt.X("start:T", title=None, scale=schaal, axis=alt.Axis(
        orient="top", grid=True, labels=False, ticks=False, domain=False,
        tickCount={"interval": "week", "step": 1}))
    # Elke regel een eigen hoogte (de regel "plaat" is lager): y is de positie van het midden van de regel in px
    # vanaf boven ("pos"), met de tekst van de regel als aslabel.
    pos, boven = {}, 0
    for regel in volgorde:
        pos[regel] = boven + _tl_rij_hoogte(regel) / 2
        boven += _tl_rij_hoogte(regel)
    for f in frames:
        if not f.empty and "y" in f:
            f["pos"] = f["y"].map(pos)
    labels = {f"{p:g}": _tl_label(regel, met_totaal) for regel, p in pos.items()}
    y_schaal = alt.Scale(domain=[0, boven], reverse=True, nice=False, zero=False)
    y_as = alt.Axis(values=list(pos.values()), labelExpr=f"({json.dumps(labels, ensure_ascii=False)})[datum.value] || ''",
                    labelLimit=110, minExtent=0, grid=False, ticks=False, domain=False, labelFontSize=11,
                    labelOverlap=False)
    y = alt.Y("pos:Q", title=None, scale=y_schaal, axis=y_as)

    def balk(f, hoogte, midden=0.0):
        """De boven- en onderkant (b1, b2) van een balk van `hoogte` px rond het midden van de regel (+ midden)."""
        if not f.empty:
            f["b1"] = f["pos"] + midden - hoogte / 2
            f["b2"] = f["pos"] + midden + hoogte / 2
        return {"y": alt.Y("b1:Q", title=None, scale=y_schaal, axis=y_as), "y2": "b2:Q"}

    balk_y = balk(balken, TL_RIJ - 8)
    randen_y = balk(randen, TL_RIJ - 8)
    klik = alt.selection_point(name="tl_klik", fields=["sleutel"], on="click")
    lagen = [
        alt.Chart(balken).mark_bar(tooltip=None, cornerRadius=2, stroke="#000000", clip=True, cursor="pointer")
        .encode(x=x, x2="eind:T", **balk_y, color=alt.Color("kleur:N", scale=None),
                opacity=alt.Opacity("dekking:Q", scale=None), strokeOpacity=alt.StrokeOpacity("lijn:Q", scale=None))
        .add_params(klik)
    ]
    for streep, dash, breedte in (("vol", [1, 0], 1.2), ("concept", [4, 2], 1.5),
                                  ("florgib", [2, 2], 1.5), ("overlap", [4, 2], 2)):
        deel = randen[randen["streep"] == streep] if not randen.empty else randen
        if not deel.empty:
            lagen.append(alt.Chart(deel).mark_bar(tooltip=None, cornerRadius=2, filled=False, clip=True,
                                                  strokeDash=dash, strokeWidth=breedte)
                         .encode(x="start:T", x2="eind:T", **randen_y, stroke=alt.Stroke("rand:N", scale=None)))
    # Dunne lijnen op dagniveau over de balken heen (de weeklijnen zijn de rasterlijnen van de as). Bij een dag
    # smaller dan 6 px staan ze te dicht op elkaar: dan niet.
    dagen = pd.DataFrame({"d": pd.date_range(pd.Timestamp(van), pd.Timestamp(tot) + pd.Timedelta(days=1))})
    lagen.append(alt.Chart(dagen).mark_rule(tooltip=None, color="#808080", strokeWidth=0.5,
                                            opacity=alt.expr(f"{px} >= 6 ? 0.25 : 0"))
                 .encode(x="d:T"))
    if not plan.empty:
        lagen.append(alt.Chart(plan).mark_tick(tooltip=None, orient="vertical", thickness=2, size=TL_RIJ - 4,
                                               color="#1f1f1f")
                     .encode(x="x:T", y=y))
    if not florgib.empty:
        lagen.append(alt.Chart(florgib).mark_point(tooltip=None, size=45, strokeWidth=2, color=TL_FLORGIB, opacity=1)
                     .encode(x="x:T", y=y, fill=alt.condition("datum.soort == 'geregistreerd'",
                                                               alt.value(TL_FLORGIB), alt.value("transparent"))))
    if not water.empty:
        # Watergift: een blauw vakje per dag met water (één kleur), met de liters erin (met een decimaal als de dag
        # breed genoeg is, anders in hele liters). Bij Bespuitingen een dun licht streepje onderin, zonder getal.
        groot = weergave != "Bespuitingen"
        hoogte = TL_RIJ - 8 if groot else 4
        water_y = balk(water, hoogte, 0 if groot else (TL_RIJ - 8) / 2 - hoogte / 2)
        lagen.append(alt.Chart(water).mark_bar(tooltip=None, color=TL_WATER if groot else TL_WATER_LICHT,
                                               cursor="pointer")
                     .encode(x="start:T", x2="eind:T", **water_y)
                     .add_params(alt.selection_point(name="tl_water", fields=["sleutel"], on="click")))
        if groot:
            # Bij ≥ 30 px per dag met een decimaal, daaronder in hele liters (kleiner naarmate de dag smaller
            # is); pas onder 8 px niet (klik voor de gietbeurten).
            lagen.append(alt.Chart(water).mark_text(tooltip=None,
                                                    fontSize=alt.expr(f"{px} >= 30 ? 12 : {px} >= 17 ? 11 : 9"),
                                                    fontWeight="bold", color="white", cursor="pointer")
                         .transform_calculate(lbl=f"{px} >= 30 ? datum.tekst : {px} >= 8 ? datum.heel : ''")
                         .encode(x="x:T", y=y, text="lbl:N")
                         .add_params(alt.selection_point(name="tl_wtekst", fields=["sleutel"], on="click")))
    if not waarden.empty:
        # Weergave Watergift: de EC en pH van de gift per vak en de EC van de voorregeling, als getal (EC met
        # 2 decimalen bij ≥ 26 px per dag, met 1 bij ≥ 16 px). Past er geen getal, dan een grijs blokje met de
        # zodat je ziet dat er een meting is (klik voor de waarden).
        lagen.append(alt.Chart(waarden).mark_square(tooltip=None, size=30, color="#8a8a85", cursor="pointer",
                                                    opacity=alt.expr(f"{px} >= 16 ? 0 : 1"))
                     .encode(x="x:T", y=y)
                     .add_params(alt.selection_point(name="tl_ecph_blok", fields=["sleutel"], on="click")))
        lagen.append(alt.Chart(waarden).mark_text(tooltip=None, fontSize=alt.expr(f"{px} >= 26 ? 11 : 9"),
                                                  color="#3d3d3a",
                                                  cursor="pointer")
                     .transform_calculate(lbl=f"{px} >= 26 ? datum.tekst : {px} >= 16 ? datum.kort : ''")
                     .encode(x="x:T", y=y, text="lbl:N")
                     .add_params(alt.selection_point(name="tl_ecph", fields=["sleutel"], on="click")))
    if not vangst.empty:
        # Weergave Waarnemingen, regel "plaat" onder elk vak: de nieuwe vangst vanaf de fotodag ("T3 M1", ± 6 px per
        # teken, ingekort tot wat er past tot de volgende foto); past er niets, dan een blokje (klik voor de platen).
        kleur = alt.condition("datum.nul", alt.value(TL_PATS_NUL), alt.value(TL_PATS))
        tekens = f"floor((datum.ruimte * {px} - 4) / 6)"
        lagen.append(alt.Chart(vangst).mark_square(tooltip=None, size=30, cursor="pointer",
                                                   opacity=alt.expr(f"{px} >= 14 ? 0 : 1"))
                     .encode(x="xm:T", y=y, color=kleur)
                     .add_params(alt.selection_point(name="tl_vangst_blok", fields=["sleutel"], on="click")))
        lagen.append(alt.Chart(vangst).mark_text(tooltip=None, align="left", dx=2, fontSize=10, fontWeight="bold",
                                                 cursor="pointer")
                     .transform_calculate(lbl=f"{px} < 14 || {tekens} < 1 ? '' : length(datum.tekst) <= {tekens} ? "
                                              f"datum.tekst : {tekens} < 3 ? '…' : "
                                              f"slice(datum.tekst, 0, {tekens} - 1) + '…'")
                     .encode(x="x:T", y=y, text="lbl:N", color=kleur)
                     .add_params(alt.selection_point(name="tl_vangst", fields=["sleutel"], on="click")))
    if not metingen.empty:
        # Weergave Waarnemingen: de gewasmetingen in de balk: een ruitje met de meting erachter (Florgib in paars,
        # bij de Florgibstip); bij < 8 px per dag alleen het ruitje.
        kleur = alt.condition("datum.soort == 'florgib'", alt.value(TL_FLORGIB), alt.value(TL_METING))
        eind = metingen[metingen["soort"] == "eind"]
        if not eind.empty:
            lagen.append(alt.Chart(eind).mark_point(tooltip=None, shape="diamond", size=50, filled=True, opacity=1,
                                                    color=TL_METING, cursor="pointer")
                         .encode(x="x:T", y=y))
        lagen.append(alt.Chart(metingen).mark_text(tooltip=None, align="left", dx=7, fontSize=10, fontWeight="bold",
                                                   cursor="pointer")
                     .transform_calculate(lbl=f"{px} >= 8 ? datum.tekst : ''")
                     .encode(x="x:T", y=y, text="lbl:N", color=kleur)
                     .add_params(alt.selection_point(name="tl_meting", fields=["sleutel"], on="click")))
    if not plagen.empty:
        # Weergave Waarnemingen: de PATS-tellingen per insect als getal (0 in grijs); past er geen getal (< 14 px
        # per dag), dan een blokje (klik voor de telling).
        kleur = alt.condition("datum.nul", alt.value(TL_PATS_NUL), alt.value(TL_PATS))
        lagen.append(alt.Chart(plagen).mark_square(tooltip=None, size=30, cursor="pointer",
                                                   opacity=alt.expr(f"{px} >= 14 ? 0 : 1"))
                     .encode(x="x:T", y=y, color=kleur)
                     .add_params(alt.selection_point(name="tl_pats_blok", fields=["sleutel"], on="click")))
        lagen.append(alt.Chart(plagen).mark_text(tooltip=None, fontSize=alt.expr(f"{px} >= 26 ? 11 : 10"),
                                                 fontWeight="bold", cursor="pointer")
                     .transform_calculate(lbl=f"{px} >= 14 ? datum.tekst : ''")
                     .encode(x="x:T", y=y, text="lbl:N", color=kleur)
                     .add_params(alt.selection_point(name="tl_pats", fields=["sleutel"], on="click")))
    if not behandelingen.empty:
        # Bespuitingen: een driehoekje bovenin de regel, zodat de balk zichtbaar blijft. In de weergave
        # Bespuitingen groter, met de afkortingen van de middelen erachter (logic/klimaatregistratie.afkorting).
        groot = weergave == "Bespuitingen"
        lagen.append(alt.Chart(behandelingen).mark_point(tooltip=None, shape="triangle-down", size=130 if groot else 55,
                                                         filled=True, opacity=1, stroke="white", strokeWidth=1,
                                                         yOffset=-(TL_RIJ - 8) / 2 + (1 if groot else 0),
                                                         cursor="pointer")
                     .encode(x="x:T", y=y, color=alt.Color("kleur:N", scale=None))
                     .add_params(alt.selection_point(name="tl_beh", fields=["sleutel"], on="click")))
        if groot:
            # De middelen tot de volgende behandeling in het vak (± 6 px per letter); past er te weinig, dan
            # ingekort met "…" of niets (klik voor alles).
            tekens = f"floor((datum.ruimte * {px} - 10) / 6)"
            lagen.append(alt.Chart(behandelingen).mark_text(tooltip=None, align="left", dx=6, dy=1, fontSize=10,
                                                            fontWeight="bold",
                                                            cursor="pointer")
                         .transform_calculate(lbl=f"{tekens} < 3 ? '' : length(datum.Middelen) <= {tekens} ? "
                                                  f"datum.Middelen : slice(datum.Middelen, 0, {tekens} - 1) + '…'")
                         .encode(x="x:T", y=y, text="lbl:N", color=alt.Color("kleur:N", scale=None))
                         .add_params(alt.selection_point(name="tl_btekst", fields=["sleutel"], on="click")))
    if not kopteksten.empty:
        lagen.append(alt.Chart(kopteksten).mark_text(tooltip=None, align="left", dx=6, fontSize=11, fontWeight="bold")
                     .encode(x="x:T", y=y, text="tekst:N"))
    uitlijning = "center" if _tl_stap(weken) == 1 else "left"
    lagen.append(alt.Chart(weeknummers).mark_text(tooltip=None, fontSize=11, opacity=0.6, align=uitlijning)
                 .encode(x="x:T", y=y, text="tekst:N"))
    # Weekdag en dagnummer: bij ≥ 10 px per dag (anders staan ze over elkaar); vandaag in rood.
    lagen.append(alt.Chart(dagnamen).mark_text(tooltip=None, fontSize=alt.expr(f"{px} >= 20 ? 10 : 9"))
                 .transform_calculate(lbl=f"{px} >= 10 ? datum.tekst : ''")
                 .encode(x="x:T", y=y, text="lbl:N",
                         color=alt.condition("datum.vandaag", alt.value(TL_ROOD), alt.value("#8a8a85"))))
    lagen.append(alt.Chart(pd.DataFrame({"d": [pd.Timestamp(vandaag)]}))
                 .mark_rule(tooltip=None, color=TL_ROOD, strokeDash=[4, 3]).encode(x="d:T"))
    # Alleen de breedte passend maken (fit-x): bij "fit" (de standaard van Streamlit bij een vaste hoogte) tellen
    # de weeklijnen over de hele hoogte mee en wordt het tekenvlak 0 px hoog.
    return (alt.layer(*lagen).properties(height=boven, autosize=alt.AutoSizeParams(type="fit-x", contains="padding"))
            .configure_view(strokeOpacity=0).configure_axis(gridOpacity=0.5)
            # Geen tooltips: Streamlit zet anders op elk merkteken een kader met alle velden (x, y, lbl), dat op een
            # telefoon half buiten beeld valt en niet weggaat. Meer weten = klikken.
            .configure_mark(tooltip=None))


def _tl_geklikt(widget, versie):
    """Callback van de tijdlijn: onthoud wat er geklikt is en begin de grafiek opnieuw (lege keuze)."""
    selectie = (st.session_state.get(widget) or {}).get("selection", {})
    items = next((selectie[n] for n in ("tl_beh", "tl_btekst", "tl_water", "tl_wtekst", "tl_ecph", "tl_ecph_blok",
                                        "tl_pats", "tl_pats_blok", "tl_vangst", "tl_vangst_blok", "tl_meting",
                                        "tl_klik")
                  if selectie.get(n)), [])
    if items and items[0].get("sleutel"):
        st.session_state[f"{versie}_klik"] = items[0]["sleutel"]
        st.session_state[versie] += 1


def _tl_planten_standaard(tuin_id, vak, start):
    """Aantal planten bij starten, zoals in de concepttabel: stelen bij 60/m² naar de dichtheid van die plantweek."""
    stelen_60 = (get_vakgegevens(tuin_id).get(vak) or {}).get("stelen_bij_60") or 0
    return round(stelen_60 / 60 * standaard_dichtheid_voor_plantweek(get_weeknummer(start)))


def _tl_plan_tekst(start):
    """Plantweek, teeltduur en verwachte oogst bij een startdatum."""
    duur, eind = bereken_verwachte_oogstdatum(start)
    if duur is None:
        return "Geen teeltduur bekend voor deze plantweek (bijv. week 53)."
    return (f"Plantweek {get_weeknummer(start)} → teeltduur {fmt_kort(duur, 1)} weken, "
            f"verwachte oogst {format_datum(eind)}.")


def _tl_overlap_melding(stukken, vak, start, behalve_concept=None):
    """Waarschuwing als een planting vanaf `start` (tot de verwachte oogst) overlapt met een andere ronde in het vak."""
    eind = bereken_verwachte_oogstdatum(start)[1] or start + timedelta(weeks=8)
    for begin, einde in tijdlijn.overlappend(stukken, vak, start, eind, behalve_concept):
        if begin <= start:
            st.warning(f"Overlapt met de vorige ronde in vak {vak}: die is pas op {format_datum(einde)} klaar "
                       f"({(einde - start).days} d na deze plantdatum).")
        else:
            st.warning(f"Overlapt met de volgende ronde in vak {vak}: die begint al op {format_datum(begin)}, "
                       f"vóór de verwachte oogst van {format_datum(eind)}.")


def _tl_klaar(melding):
    """Na opslaan: melding bovenaan de pagina en alles opnieuw tekenen (sluit het venster)."""
    st.session_state["tl_melding"] = melding
    st.rerun()


def _tl_concept_venster(concept_id, info, stukken, vandaag):
    """Klik op een concept: verschuiven, starten als teelt of verwijderen (dezelfde functies als de concepttabel)."""
    tuin = info["tuin"]
    rij = next((c for c in get_planning(tuin["id"]) if int(c[0]) == concept_id), None)
    vak = int(rij[1]) if rij else None

    @st.dialog(f"Concept vak {vak} · {tuin['naam']}" if rij else "Concept")
    def _venster():
        if rij is None:
            st.info("Dit concept bestaat niet meer.")
            return
        _id, _vak, start, duur, eind, notitie = rij
        start = vs.als_datum(start)
        toon_kengetallen([
            {"label": "Plantdatum", "waarde": format_datum(start)},
            {"label": "Plantweek", "waarde": str(get_weeknummer(start))},
            {"label": "Verwachte oogst", "waarde": format_datum(eind) if eind else LEEG},
            {"label": "Teeltduur", "waarde": fmt_weken(duur) if duur else LEEG},
        ])
        if notitie:
            st.caption(notitie)
        _tl_overlap_melding(stukken, vak, start, concept_id)
        gebruiker = huidige_gebruiker()

        layout.sectie("Verschuiven")
        nieuw = st.date_input("Nieuwe plantdatum", value=start, format="DD-MM-YYYY", key=f"tl_c_start_{concept_id}")
        if nieuw != start:
            st.caption(_tl_plan_tekst(nieuw))
            _tl_overlap_melding(stukken, vak, nieuw, concept_id)
        if st.button("Verschuiven", key=f"tl_c_schuif_{concept_id}", disabled=nieuw == start):
            wijzig_planning(concept_id, nieuw, gebruiker=gebruiker)
            _tl_klaar(f"Concept vak {vak} verschoven naar {format_datum(nieuw)}.")

        layout.sectie("Starten als teelt")
        planten = st.number_input(
            "Aantal planten", min_value=0, step=1, value=_tl_planten_standaard(tuin["id"], vak, start),
            key=f"tl_c_planten_{concept_id}", help="Standaard: stelen per m² bij die plantweek (zoals de concepttabel).")
        if start > vandaag:
            st.caption(f"De plantdatum ligt nog {(start - vandaag).days} d vooruit; het vak wordt een bevestigde "
                       "teelt die op die dag begint.")
        if st.button("Starten", key=f"tl_c_start_knop_{concept_id}", type="primary"):
            resultaat = bevestig_planning(concept_id, planten, gebruiker=gebruiker)
            _tl_klaar(f"Vak {vak} gestart als teelt {resultaat[1]}." if resultaat else "Dit concept bestond niet meer.")

        layout.sectie("Verwijderen")
        zeker = st.checkbox("Ja, dit concept verwijderen", key=f"tl_c_zeker_{concept_id}")
        if st.button("Verwijderen", key=f"tl_c_weg_{concept_id}", disabled=not zeker):
            verwijder_planning(concept_id, gebruiker=gebruiker)
            _tl_klaar(f"Concept vak {vak} verwijderd.")

    _venster()


def _tl_nieuw_venster(vak, zondag, info, stukken, vandaag):
    """Klik op een lege plek: een concept plannen in dat vak, standaard op de maandag van die week."""
    tuin = info["tuin"]

    @st.dialog(f"Nieuw concept vak {vak} · {tuin['naam']}")
    def _venster():
        standaard = max(zondag + timedelta(days=1), vandaag)
        start = st.date_input("Plantdatum", value=standaard, min_value=vandaag, format="DD-MM-YYYY",
                              key=f"tl_n_start_{tuin['nummer']}_{vak}_{zondag}")
        st.caption(_tl_plan_tekst(start))
        _tl_overlap_melding(stukken, vak, start)
        if st.button("Toevoegen aan planning", key=f"tl_n_toevoegen_{tuin['nummer']}_{vak}", type="primary"):
            voeg_planning_toe(vak, start, gebruiker=huidige_gebruiker(), tuin_id=tuin["id"])
            _tl_klaar(f"Concept vak {vak} gepland op {format_datum(start)}.")

    _venster()


def _tl_periode(balk, vandaag):
    """
    Periode van de tijdlijn in de filterbalk: 4 wk / 3 mnd / 6 mnd / 1 jaar + ◀ [wk – wk] ▶. Standaard 3 mnd, op
    een telefoon 4 wk; de periode kijkt verder terug dan vooruit (± 60 % terug). Geeft (van, tot, weken).
    """
    deze_zondag = kalender.week_begin(vandaag)
    zondagen = [deze_zondag + timedelta(weeks=i) for i in range(-52, 40)]

    def standaard(n):
        return deze_zondag - timedelta(weeks=round(TL_VENSTERS[n] * 0.6))

    lengte, van = filters.periode(
        "tl_venster", list(TL_VENSTERS), "4 wk" if _mobiel() else "3 mnd", opties_van=lambda n: zondagen, standaard_van=standaard,
        format_van=lambda n: lambda zo: _tl_venster_label(zo, TL_VENSTERS[n]), huidig_van=standaard,
        plek=balk, breedte=260)
    weken = TL_VENSTERS[lengte]
    return van, van + timedelta(weeks=weken) - timedelta(days=1), weken


def _tl_toon(infos, afdelingen, van, tot, weken, vandaag, weergave):
    """
    De tijdlijn van elke tuin, met de klikken naar het vak, een concept, een lege plek, een behandeling of een
    watergift. Geeft [(tuin, Excel-tabel watergift)] terug.
    """
    water = []
    for info in infos:
        tuin = info["tuin"]
        if len(infos) > 1:
            st.markdown(f'<div class="vem-kg-titel">{html.escape(tuin["naam"])}</div>', unsafe_allow_html=True)
        volgorde, frames, stukken, wgdata = _tl_frames(info, afdelingen.get(tuin["id"]), van, tot, vandaag, weken,
                                                       weergave)
        water.append((tuin, wgdata[0]))
        # De selecties die in de grafiek zitten (zie _tl_grafiek): een laag zonder gegevens heeft er geen.
        beh, gift, ecph, plagen, vangst, metingen = (not f.empty for f in frames[-6:])
        selecties = (["tl_klik"] + (["tl_beh"] if beh else [])
                     + (["tl_btekst"] if beh and weergave == "Bespuitingen" else [])
                     + (["tl_water"] if gift else [])
                     + (["tl_wtekst"] if gift and weergave != "Bespuitingen" else [])
                     + (["tl_ecph", "tl_ecph_blok"] if ecph else [])
                     + (["tl_pats", "tl_pats_blok"] if plagen else [])
                     + (["tl_vangst", "tl_vangst_blok"] if vangst else [])
                     + (["tl_meting"] if metingen else []))
        # Een klik wordt in de callback opgepakt (vóór de nieuwe run): die onthoudt wat er geklikt is en geeft
        # de grafiek een nieuwe sleutel, zodat de keuze leeg begint en je hetzelfde vak na het sluiten van het
        # venster opnieuw kunt aanklikken.
        versie = f"tl_grafiek_{tuin['nummer']}_versie"
        st.session_state.setdefault(versie, 0)
        widget = f"tl_grafiek_{tuin['nummer']}_{st.session_state[versie]}"
        totaal = wgdata[2] if weergave in ("Standaard", "Watergift") else {}
        st.altair_chart(_tl_grafiek(volgorde, frames, van, tot, vandaag, weken, weergave, totaal),
                        use_container_width=True,
                        on_select=lambda w=widget, v=versie: _tl_geklikt(w, v),
                        selection_mode=selecties, key=widget)
        geklikt = st.session_state.pop(f"{versie}_klik", None)
        if geklikt:
            soort, nummer = geklikt.split(":")[:2]
            if soort == "t":
                vak_venster(int(nummer), vandaag)
            elif soort == "c":
                _tl_concept_venster(int(nummer), info, stukken, vandaag)
            elif soort == "b":
                _tl_behandeling_venster(info, int(nummer), date.fromisoformat(geklikt.split(":", 2)[2]))
            elif soort == "w":
                d = wgdata[1]
                _wg_dag_venster(tuin, date.fromisoformat(geklikt.split(":", 2)[2]), d["gift"], d["kwaliteit"],
                                info["vakken"], d["beurten"])
            elif soort == "p":
                _tl_pats_venster(tuin, int(nummer), date.fromisoformat(geklikt.split(":", 2)[2]))
            elif soort == "v":
                _tl_plaat_venster(tuin, int(nummer), date.fromisoformat(geklikt.split(":", 2)[2]))
            elif soort == "n":
                vak, zondag = nummer, date.fromisoformat(geklikt.split(":", 2)[2])
                _tl_nieuw_venster(int(vak), zondag, info, stukken, vandaag)
    return water


def _tl_behandeling_venster(info, vak, dag):
    """Klik op een driehoekje: de behandelingen van die dag op dat vak, met de vakken van elke registratie."""
    tuin = info["tuin"]

    @st.dialog(f"Behandeling vak {vak} · {tuin['naam']} · {format_datum(dag)}", width="large")
    def _venster():
        alle = _behandelingen(tuin["id"], dag, dag)
        registraties = {b["registratie"] for b in alle if int(b["vaknummer"]) == vak}
        rijen = [b for b in alle if b["registratie"] in registraties and int(b["vaknummer"]) == vak]
        vakken = {r: sorted({int(b["vaknummer"]) for b in alle if b["registratie"] == r}) for r in registraties}
        for r in sorted(registraties, key=str):
            eerste = next(b for b in rijen if b["registratie"] == r)
            historie = str(eerste.get("bron") or "").startswith("klimaatregistratie")
            st.markdown(f"**{eerste['type'].capitalize() if eerste['type'] else 'Behandeling'}**"
                        + (" · klimaatregistratie" if historie else "")
                        + (f" · {eerste['methode']}" if eerste.get("methode") else "")
                        + (f" · tankmix {eerste['mix']}" if eerste.get("mix") else "")
                        + f" · op {len(vakken[r])} {'vak' if len(vakken[r]) == 1 else 'vakken'}: "
                        + ", ".join(str(v) for v in vakken[r]))
            st.markdown("\n".join(f"- {wg.behandeling_tekst(b)}"
                                   + (" (toevoeging)" if b.get("opmerking") == "toevoeging" else "")
                                   + (f" · totaal {fmt_kort(b['dosering_totaal'], 2)} {b['eenheid'] or ''}".rstrip()
                                      + (f" in {b['mix_totaal']}" if b.get("mix_totaal") else "")
                                      if b.get("dosering_totaal") is not None and len(vakken[r]) > 1 else "")
                                   for b in rijen if b["registratie"] == r))
        uitleg_help.voetnoot("Agro4all: hoeveelheid voor dit vak (het totaal van de registratie naar rato van de m² "
                             "over de vakken verdeeld). Klimaatregistratie (vóór Agro4all): alleen het middel, op de "
                             "eerste dag van een reeks codes.")

    _venster()


def _tl_pats_venster(tuin, klasse_id, dag):
    """Klik op een PATS-telling: per vangplaat (Trap-Eye) of sensor (PATS-C) het aantal nieuwe van die dag."""
    insect = pats_logic.INSECTEN.get(klasse_id, str(klasse_id))

    @st.dialog(f"{insect} · {tuin['naam']} · {DAGEN_KORT_WG[dag.weekday()]} {format_datum(dag)}", width="large")
    def _venster():
        regels = [t for t in _pats_tellingen(tuin["id"], dag, dag) if t["klasse_id"] == klasse_id]
        if not regels:
            st.caption("Geen telling op deze dag.")
            return
        regels.sort(key=lambda t: (-(t["nieuw"] or 0), t["apparaat"], t["rij"], t["paal"]))
        toon_kengetallen([
            {"label": "Nieuw", "waarde": fmt_kort(sum(t["nieuw"] or 0 for t in regels), 1),
             "help": "Nieuwe insecten op deze dag, alle vangplaten of sensoren van de tuin samen."},
            {"label": "Met vangst", "waarde": f"{sum(1 for t in regels if t['nieuw'])} van {len(regels)}"},
        ])
        toon_tabel(pd.DataFrame([{"Apparaat": pats_logic.APPARAAT[t["apparaat"]], "Rij": t["rij"], "Paal": t["paal"],
                                  "Nieuw": t["nieuw"], "Op de plaat": t["stand"]} for t in regels]), [
            ("Apparaat", "Apparaat", "tekst", None, "small"), ("Rij", "Rij", "getal", "%d", "small"),
            ("Paal", "Paal", "getal", "%d", "small"), ("Nieuw", "Nieuw", "getal", "%g", "small"),
            ("Op de plaat", "Op de plaat", "getal", "%g", "small")], verberg_leeg=True)
        uitleg_help.voetnoot("Rij en paal zoals bij PATS. Trap-Eye: nieuw sinds de vorige foto, op de plaat = de "
                             "stand op de vangplaat. PATS-C: van 12 uur deze dag tot 12 uur de volgende dag.")

    _venster()


def _tl_plaat_venster(tuin, vak, dag):
    """Klik op de vangst bij een vak: per Trap-Eye naast het vak de nieuwe insecten en de stand op de plaat."""
    verschuiving = PATS_TRAPEYE_VAKKEN.get(tuin["nummer"])

    @st.dialog(f"Vangplaten vak {vak} · {tuin['naam']} · {DAGEN_KORT_WG[dag.weekday()]} {format_datum(dag)}",
               width="large")
    def _venster():
        tellingen = [t for t in _pats_tellingen(tuin["id"], dag, dag) if t["apparaat"] == "trapeye"
                     and t["klasse_id"] in pats_logic.PLAAT_INSECTEN and verschuiving
                     and vak in pats_logic.vakken_van_rij(t["rij"], verschuiving)]
        if not tellingen:
            st.caption("Geen telling op deze dag.")
            return
        platen = {}
        for t in tellingen:
            p = platen.setdefault((t["rij"], t["paal"]), {"Rij": t["rij"], "Paal": t["paal"]})
            naam = pats_logic.INSECTEN[t["klasse_id"]]
            p[naam] = t["nieuw"]
            p[f"{naam} op plaat"] = t["stand"]
        namen = [pats_logic.INSECTEN[k] for k in pats_logic.PLAAT_INSECTEN]
        toon_tabel(pd.DataFrame([platen[k] for k in sorted(platen)]),
                   [("Rij", "Rij", "getal", "%d", "small"), ("Paal", "Paal", "getal", "%d", "small")]
                   + [(n, f"{n} nieuw", "getal", "%g", "small") for n in namen]
                   + [(f"{n} op plaat", f"{n} op plaat", "getal", "%g", "small") for n in namen],
                   verberg_leeg=True)
        buren = ", ".join(str(v) for v in pats_logic.vakken_van_rij(tellingen[0]["rij"], verschuiving))
        uitleg_help.voetnoot(f"Rij en paal zoals bij PATS; een plaat hangt tussen twee vakken (deze: vak {buren}). "
                             "Nieuw = sinds de vorige foto; op plaat = de stand op de vangplaat.")

    _venster()


def _tl_legenda(weergave):
    legend.legenda([
        {"label": "lopend (per teelt donker/licht)",
         "stijl": f"width:1.6rem;background:linear-gradient(90deg,{TL_LOPEND[0]} 50%,{TL_LOPEND[1]} 50%);"},
        {"kleur": TL_LOPEND[0], "label": "verwacht, tot de prognose-oogst", "stijl": "opacity:0.45;"},
        {"label": "afgerond (per teelt donker/licht)",
         "stijl": f"width:1.6rem;background:linear-gradient(90deg,{TL_AFGEROND_TINT[0]} 50%,{TL_AFGEROND_TINT[1]} 50%);"},
        {"kleur": "#6f6f6a", "vorm": "rand", "label": "bevestigd, nog niet geplant"},
        {"kleur": TL_CONCEPT, "vorm": "stippelrand", "label": "concept"},
        {"kleur": TL_ROOD, "vorm": "stippelrand", "label": "overlapt met een andere ronde"},
        {"kleur": "#1f1f1f", "vorm": "stippelrand", "label": f"Florgib > {FLORGIB_ACHTERSTAND_DAGEN} d over tijd"},
        {"kleur": "#1f1f1f", "vorm": "lijn", "label": "plan-oogst", "stijl": "transform:rotate(90deg);width:0.8rem;"},
        {"kleur": TL_FLORGIB, "vorm": "stip", "label": "Florgib"},
        {"kleur": TL_FLORGIB, "vorm": "ring", "label": "verwachte Florgib"},
        {"kleur": TL_ROOD, "vorm": "lijn", "label": "vandaag", "stijl": "border-top-style:dashed;"},
    ])
    legend.legenda([{"kleur": kleur, "label": soort, "stijl": "clip-path:polygon(0 0,100% 0,50% 100%);"}
                    for soort, kleur in wg.BEHANDELING_KLEUR.items()]
                   + ([] if weergave == "Waarnemingen" else
                      [{"kleur": TL_WATER, "label": "watergift in l/m² (klik voor de gietbeurten)",
                        "stijl": f"height:0.3rem;background:{TL_WATER_LICHT};" if weergave == "Bespuitingen"
                        else ""}]),
                   titel="Bespuitingen (▼)" + ("" if weergave == "Waarnemingen" else " en watergift") + ":")
    if weergave == "Waarnemingen":
        legend.legenda([{"kleur": TL_PATS, "label": "aantal nieuw (PATS); plaat = nieuwe trips naast het vak"},
                        {"kleur": TL_PATS_NUL, "label": "telling 0"},
                        {"kleur": TL_METING, "label": "eindmeting (lengte · gewicht · rijpheid)",
                         "stijl": "transform:rotate(45deg);width:0.55rem;height:0.55rem;"},
                        {"kleur": TL_FLORGIB, "vorm": "stip", "label": "lengte bij de Florgib"}],
                       titel="Waarnemingen:")


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


def _tv_geoogst(g, van, tot):
    """Openklapmenu met de emmers per vak en de afgeronde vakken in de periode (tuin → afdeling → vak)."""
    afdeling = g.vak_afdeling
    emmers = [e for e in g.emmers if van <= e["datum"] <= tot]
    afgerond = sorted((t for t in g.teelten if t["oogst"] and van <= t["oogst"] <= tot),
                      key=lambda t: _tv_volgorde(t["tuin_id"], afdeling.get((t["tuin_id"], t["vaknummer"])),
                                                 t["vaknummer"]))
    with layout.uitklap(f"Geoogst in deze periode ({_vakken_tekst(len({e['teelt_id'] for e in emmers}))}, "
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


def _tv_links(g, sleutel, periode_naam, van, tot, n_opmerkingen):
    """Doorklikken naar de thuispagina van de details: register (geplant), Overzicht en Opmerkingen."""
    geplant = sum(1 for t in g.teelten if van <= t["start"] <= tot)
    rij = st.container(horizontal=True, gap="medium", key="tv_links")
    if rij.button(f"Bekijk de {_vakken_tekst(geplant)} geplant in het register", icon=":material/arrow_forward:",
                  type="tertiary", key="tv_naar_register", disabled=not geplant):
        ga_naar("overzicht", {"reg_plantperiode_lengte": periode_naam,
                                   f"reg_plantperiode_{periode_naam}": sleutel, "reg_ras": None, "reg_zoek": None,
                                   **{f"afd_t{t['nummer']}": None for t in TUINEN}}, tuin="beide")
    if rij.button("Watergift in deze periode", icon=":material/arrow_forward:", type="tertiary",
                  key="tv_naar_watergift"):
        lengte = {"Week": "4 wk", "Maand": "4 wk", "Kwartaal": "3 mnd"}.get(periode_naam, "6 mnd")
        ga_naar("overzicht", {"ov_weergave": "Watergift", "tl_venster_lengte": lengte,
                              f"tl_venster_{lengte}": wg.week_begin(van)}, tuin="beide")
    if rij.button(f"{n_opmerkingen} opmerking{'' if n_opmerkingen == 1 else 'en'} in deze periode",
                  icon=":material/arrow_forward:", type="tertiary", key="tv_naar_opmerkingen",
                  disabled=not n_opmerkingen):
        ga_naar("opmerkingen", {"opm_periode_lengte": periode_naam, f"opm_periode_{periode_naam}": sleutel,
                                "opm_teelt": None, "opm_vak": None, "opm_categorie": None, "opm_zoek": None},
                tuin="beide")


def _tuinvgl_inhoud():
    """Pagina Tuin bij Beide: Tuin 1 naast Tuin 3 en het totaal, per m²."""
    _tv_vandaag = date.today()
    _tv_g = _tv_gegevens(vakstatus_dataversie())
    _tv_tuinen = [(t["naam"], t["id"]) for t in sorted(TUINEN, key=lambda t: t["nummer"])]

    _tv_balk = layout.filterbalk("tuinvgl")
    _tv_eerste = min((t["start"] for t in _tv_g.teelten), default=_tv_vandaag)
    _tv_periode, _tv_sleutel = filters.periode(
        "tv_periode", perioden.PERIODEN, "Week",
        opties_van=lambda n: perioden.reeks(_tv_eerste, _tv_vandaag, n),
        standaard_van=lambda n: perioden.laatste_volledige(n, _tv_vandaag),
        format_van=lambda n: lambda k: perioden.periode_label(k, n),
        huidig_van=lambda n: perioden.periode_sleutel(_tv_vandaag, n)[0], plek=_tv_balk)
    _tv_soort = filters.weergave("Vergelijk met", ("vorig_jaar", "vorige"), "tv_vergelijk", "vorig_jaar",
                                 plek=_tv_balk, format_func=lambda k: {"vorig_jaar": "zelfde periode vorig jaar",
                                                                       "vorige": "vorige periode"}[k])

    _tv_van, _tv_tot, _tv_loopt = perioden.venster(_tv_sleutel, _tv_periode, _tv_vandaag)
    _tv_v_van, _tv_v_tot, _ = perioden.vergelijk_venster(_tv_sleutel, _tv_periode, _tv_soort, _tv_vandaag)
    _tv_label = perioden.kort_label(_tv_sleutel, _tv_periode, _tv_soort)
    _tv_enkel = PERIODE_ENKELVOUD[_tv_periode]

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

    layout.sectie("Tuin 1 naast Tuin 3")
    vergelijkingstabel.toon(
        TV_KENGETALLEN, [n for n, _ in _tv_tuinen] + ["Totaal"],
        _tv_tabeldata(_tv_g, _tv_tuinen, _tv_van, _tv_tot, _tv_v_van, _tv_v_tot, _tv_label),
        sleutel="tv_verloop", verloop=_tv_verloop,
        verloop_titel=f"Verloop over 12 {'weken' if _tv_periode == 'Week' else 'perioden'}")
    _tv_priva = laatste_priva_ophaling()
    uitleg_help.voetnoot(
        f"{format_datum(_tv_van)} t/m {format_datum(_tv_tot)}" + (" (loopt nog, t/m gisteren)" if _tv_loopt else "")
        + f" · kleine regel = {'zelfde ' + _tv_enkel + ' vorig jaar' if _tv_soort == 'vorig_jaar' else 'vorige ' + _tv_enkel}"
        + (f" · Priva bijgewerkt tot {format_datum(_tv_priva.date())} {_tv_priva:%H:%M}" if _tv_priva else ""))

    # Trend geoogste stelen (uit de emmers), de laatste 12 perioden t/m de gekozen.
    layout.sectie("Geoogste stelen per periode")
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
            color=alt.Color("Tuin:N", title=None, legend=alt.Legend(orient="bottom")),
            tooltip=["Periode", "Tuin", alt.Tooltip("Stelen:Q", format=",.0f"), "Vakken"],
        ).properties(height=240), use_container_width=True)
        uitleg_help.voetnoot("Uit de emmers (× 100 stelen), gestapeld per tuin.")

    _tv_opm_van, _tv_opm_tot = perioden.periode_grenzen(_tv_sleutel, _tv_periode)
    _tv_opm = opm_logic.filter_opmerkingen(_opm_alle(vakstatus_dataversie()), van=_tv_opm_van, tot=_tv_opm_tot)
    _tv_geoogst(_tv_g, _tv_van, _tv_tot)
    _tv_links(_tv_g, _tv_sleutel, _tv_periode, _tv_van, _tv_tot, len(_tv_opm))


# --- TUIN: de pagina met de tuinkeuze als weergave ---
#
# Beide = de Tuinvergelijking hierboven; Tuin 1 / Tuin 3 = wat er op een dag of in een week in die tuin
# gebeurde, per afdeling, met het klimaat per uur uit de Priva-bestanden (tabel klimaat_uur, via
# priva_klimaat.py). Rekenwerk in logic/tuin_overzicht.py.

def _pagina_tuin():
    layout.pagina_kop(
        "Tuin",
        wat="Met de tuinkeuze bovenaan wissel je van weergave. **Beide**: wat er in een periode in de kas gebeurde, "
            "tuin 1 naast tuin 3 en het totaal, alles per m². **Tuin 1 / Tuin 3**: wat er op een dag of in een week "
            "in die tuin gebeurde: de registraties, de kengetallen per afdeling en het verloop van temperatuur en "
            "RV.",
        lezen=["Kies de lengte en blader met ◀ ▶; klik op het label om direct naar een periode te springen. Weken "
               "lopen van zondag t/m zaterdag. Loopt de periode nog, dan telt hij t/m gisteren (een dag: t/m het "
               "laatste hele uur) en loopt de vergelijking tot even ver.",
               "Kleine regel onder elke waarde = de vergelijkingsperiode. Beweeg over een cel voor het verschil en de "
               "uitleg; klik op een kengetal voor het verloop over 12 perioden.",
               "**Beide**: het totaal is gewogen naar m² (niet het gemiddelde van twee tuinen). Onderaan door naar de "
               "geplante vakken, de watergift en de opmerkingen van de periode.",
               "**Tuin 1 / Tuin 3**: een klik op een regel bij *Wat er gebeurde* opent het vak. In de grafieken: beweeg over een tijdstip voor "
               "alle afdelingen tegelijk."],
        bron="Klimaat per dag, watergift en energie uit Priva. Klimaat per uur uit de Priva-bestanden op de NAS, elk "
             "uur bijgewerkt: het gemiddelde van de minuten (tuin 3 vóór 7 oktober 2026 de waarde op het hele uur; "
             "tuin 1 sinds 21 oktober 2026). "
             "Geplant, Florgib, geoogst en opmerkingen uit de registratie; geoogste stelen = emmers × 100.",
        kleuren="Groen/rood pijltje = beter/slechter dan de vergelijking; lichtgroen vak = de beste tuin (Beide); "
                "⚠ = niet alle dagen, uren of vakken met data. Grafieken: vaste kleur per afdeling, grijs gestippeld "
                "= buiten.",
    )
    if TUIN_WEERGAVE == "beide":
        _tuinvgl_inhoud()
    else:
        _tuin_inhoud()


TU_PERIODEN = (perioden.DAG, "Week")
_TV_PER_SLEUTEL = {k.sleutel: k for k in TV_KENGETALLEN}
TU_KENGETALLEN = [
    *(_TV_PER_SLEUTEL[s] for s in ("temp", "temp_dag", "temp_nacht")),
    Kengetal("dif", "DIF (dag − nacht)", "Klimaat", "°C", 1,
             f"Dagtemperatuur min nachttemperatuur. Streven: altijd minstens {fmt_kort(DIF_MIN, 1)} °C "
             "(dag warmer dan nacht).", n_eenheid="dagen"),
    Kengetal("temp_min", "Laagste uur", "Klimaat", "°C", 1, "Het koudste uur (uurgemiddelde) in de periode.",
             n_eenheid="uren"),
    Kengetal("temp_max", "Hoogste uur", "Klimaat", "°C", 1, "Het warmste uur (uurgemiddelde) in de periode.",
             n_eenheid="uren"),
    _TV_PER_SLEUTEL["afwijking"], _TV_PER_SLEUTEL["lichtsom"], _TV_PER_SLEUTEL["rv"],
    Kengetal("rv_hoog", f"Uren RV ≥ {tuin_ov.RV_HOOG} %", "Klimaat", "u", 1,
             f"Uren per etmaal met een RV van {tuin_ov.RV_HOOG} % of meer (bij ontbrekende uren omgerekend naar 24).",
             n_eenheid="uren"),
    Kengetal("vd", "Vochtdeficit", "Klimaat", "g/m³", 1, "Gemiddeld over de uren.", n_eenheid="uren"),
    Kengetal("co2", "CO₂", "Klimaat", "ppm", 0, "Gemiddeld over de uren (een afdeling zonder meter: –).",
             n_eenheid="uren"),
    Kengetal("stook", "Stooktemperatuur", "Klimaat", "°C", 1,
             "Door Priva berekende verwarmingstemperatuur (de stooklijn), gemiddeld over de uren.",
             n_eenheid="uren"),
    Kengetal("stook_max", "Hoogste stooktemperatuur", "Klimaat", "°C", 1,
             f"Het hoogste uur van de stooklijn. Streven: nooit boven {fmt_kort(STOOK_MAX, 1)} °C.",
             n_eenheid="uren"),
    *(_TV_PER_SLEUTEL[s] for s in ("bezetting", "geplant", "geoogst", "uitval")),
    _TV_PER_SLEUTEL["water"],
    Kengetal("ec", "EC gift", "Energie & water", "mS/cm", 1,
             f"EC van de watergift, gewogen naar liters × m² vak. Streven: {fmt_kort(EC_BEREIK[0], 1)}–"
             f"{fmt_kort(EC_BEREIK[1], 1)}.", n_eenheid="dagen"),
    Kengetal("ph", "pH gift", "Energie & water", "", 1,
             f"pH van de watergift, gewogen naar liters × m² vak. Streven: {fmt_kort(PH_BEREIK[0], 1)}–"
             f"{fmt_kort(PH_BEREIK[1], 1)} (tuin 3 heeft geen pH-regeling).", n_eenheid="dagen"),
    *(_TV_PER_SLEUTEL[s] for s in ("warmte", "gas", "energie")),
]
BUITEN = "Buiten"
BUITEN_KLEUR = "#8a8a80"


@st.cache_data(ttl=600, show_spinner=False)
def _tu_uur(tuin_id, van, tot):
    """(klimaat, meteo) per uur van een tuin over [van, tot]; tien minuten bewaard (elk uur nieuwe data)."""
    return get_klimaat_uur(tuin_id, van, tot)


def _tu_reeksen(uur, meteo, g, tuin_id, van, tot):
    """
    (DataFrame met Reeks, tijd, temp, rv, per_uur) voor de grafieken: per uur uit klimaat_uur, met buiten
    erbij; zonder uurdata de etmaalwaarden per afdeling uit het klimaat per dag.
    """
    if not uur.empty:
        df = pd.DataFrame({"Reeks": uur["afdeling"].map(tuin_ov.kolom), "tijd": pd.to_datetime(uur["tijdstip"]),
                           "temp": uur["temp"], "rv": uur["rv"]})
        if not meteo.empty:
            df = pd.concat([df, pd.DataFrame({"Reeks": BUITEN, "tijd": pd.to_datetime(meteo["tijdstip"]),
                                              "temp": meteo["buiten_temp"], "rv": meteo["buiten_rv"]})])
        return df, True
    dag = g.klimaat[(g.klimaat["tuin_id"] == tuin_id) & (g.klimaat["datum"] >= str(van))
                    & (g.klimaat["datum"] <= str(tot))]
    return pd.DataFrame({"Reeks": dag["afdeling"].astype(int).map(tuin_ov.kolom),
                         "tijd": pd.to_datetime(dag["datum"]), "temp": dag["temp_24h"], "rv": dag["rv_24h"]}), False


def _tu_grafiek(df, veld, titel, volgorde, per_uur, een_dag):
    """Lijn per afdeling (vaste kleur) en buiten (grijs gestippeld); over een tijdstip alle waarden tegelijk."""
    df = df.dropna(subset=[veld])
    if df.empty:
        st.caption(f"Geen {titel.split(' (')[0].lower()} in deze periode.")
        return
    domein = [r for r in volgorde + [BUITEN] if r in set(df["Reeks"])]
    kleuren = [AFDELING_KLEUR.get(int(r.split()[-1]), BUITEN_KLEUR) if r != BUITEN else BUITEN_KLEUR for r in domein]
    strepen = [[4, 3] if r == BUITEN else [1, 0] for r in domein]
    if een_dag:
        as_ = alt.Axis(format="%H:%M", labelAngle=0)
    else:
        as_ = alt.Axis(labelExpr="['zo','ma','di','wo','do','vr','za'][day(datum.value)] + ' ' "
                                 "+ timeFormat(datum.value, '%d-%m')",
                       tickCount="day", labelAngle=0, grid=True)
    basis = alt.Chart(df).encode(x=alt.X("tijd:T", title=None, axis=as_))
    lijnen = basis.mark_line(strokeWidth=2, point=not per_uur).encode(
        y=alt.Y(f"{veld}:Q", title=titel, scale=alt.Scale(zero=False)),
        color=alt.Color("Reeks:N", scale=alt.Scale(domain=domein, range=kleuren), legend=None),
        strokeDash=alt.StrokeDash("Reeks:N", scale=alt.Scale(domain=domein, range=strepen), legend=None),
        detail="Reeks:N")
    kies = alt.selection_point(nearest=True, on="pointerover", fields=["tijd"], empty=False, clear="pointerout")
    decimalen = 1 if veld == "temp" else 0
    regel = basis.transform_pivot("Reeks", value=veld, groupby=["tijd"]).mark_rule(color="#6f6f6a").encode(
        opacity=alt.condition(kies, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("tijd:T", title="Tijd" if per_uur else "Dag",
                             format="%d-%m %H:%M" if per_uur else "%d-%m-%y")]
        + [alt.Tooltip(f"{r.replace('.', chr(92) + '.')}:Q", title=r, format=f",.{decimalen}f") for r in domein],
    ).add_params(kies)
    st.altair_chart((lijnen + regel).properties(height=230), use_container_width=True)


def _tu_verloop_fn(g, tuin_id, sleutel, periode, vandaag, volgorde):
    """Verloop over 12 perioden per afdeling en de hele tuin (voor de knopjes onder de tabel)."""
    stappen = []
    for stap in range(-11, 1):
        s = perioden.verschuif(sleutel, periode, stap)
        van, tot, _ = perioden.venster(s, periode, vandaag)
        if tot >= van:
            stappen.append((s, van, tot))

    def verloop(k):
        if not stappen:
            return verloop_frame([])
        uur = _tu_uur(tuin_id, stappen[0][1], stappen[-1][2])[0] if k.sleutel in tuin_ov.UUR_SLEUTELS else None
        rijen = []
        for s, van, tot in stappen:
            u = tuin_ov.tabelwaarden(g, uur, tuin_id, van, tot)
            for kol in volgorde:
                rijen.append({"Periode": perioden.periode_label(s, periode), "Tuin": kol,
                              "Waarde": u["waarden"].get(kol, {}).get(k.sleutel),
                              "n": u["n"].get(kol, {}).get(k.sleutel, 0)})
        return verloop_frame(rijen)

    return verloop


TU_GEBEURTENIS_KOLOMMEN = [
    ("Datum", "Datum", "datum", None, "small"), ("Afd.", "Afd.", "getal", "%d", "small"),
    ("Vak", "Vak", "getal", "%d", "small"), ("Code", "Code", "tekst", None, "medium"),
    ("Wat", "Wat", "tekst", None, 90), ("Toelichting", "Toelichting", "tekst", None, "large"),
]


def _tuin_inhoud():
    """Pagina Tuin bij Tuin 1 / Tuin 3: een dag of week in één tuin, per afdeling."""
    vandaag = date.today()
    g = _tv_gegevens(vakstatus_dataversie())
    balk = layout.filterbalk("tuin")
    eerste = min((t["start"] for t in g.teelten if t["tuin_id"] == TUIN_ID), default=vandaag - timedelta(days=365))
    periode, sleutel = filters.periode(
        "tu_periode", TU_PERIODEN, perioden.DAG,
        opties_van=lambda n: perioden.reeks(eerste, vandaag, n),
        standaard_van=lambda n: perioden.laatste_volledige(n, vandaag),
        format_van=lambda n: lambda k: perioden.periode_label(k, n),
        huidig_van=lambda n: perioden.periode_sleutel(vandaag, n)[0], plek=balk)
    enkel = "dag" if periode == perioden.DAG else "week"
    soort = filters.weergave("Vergelijk met", ("vorige", "vorig_jaar"), "tu_vergelijk", "vorige", plek=balk,
                             format_func=lambda k: {"vorige": f"vorige {enkel}",
                                                    "vorig_jaar": f"zelfde {enkel} vorig jaar"}[k])

    van, tot, loopt = perioden.venster(sleutel, periode, vandaag)
    if tot < van:
        st.info("Deze week is vandaag begonnen: er is nog geen hele dag. Kies de vorige week of vandaag bij Dag.")
        return
    v_van, v_tot, _ = perioden.vergelijk_venster(sleutel, periode, soort, vandaag)
    label = perioden.kort_label(sleutel, periode, soort)
    uur, meteo = _tu_uur(TUIN_ID, van, tot)
    uur_toen, _ = _tu_uur(TUIN_ID, v_van, v_tot)
    nu = tuin_ov.tabelwaarden(g, uur, TUIN_ID, van, tot)
    toen = tuin_ov.tabelwaarden(g, uur_toen, TUIN_ID, v_van, v_tot)
    afds = sorteer_afdelingen(tuin_ov.afdelingen(g, TUIN_ID), TUIN_NUMMER)
    volgorde = [tuin_ov.kolom(a) for a in afds]

    # Samenvatting: wat er gebeurde.
    rijen = tuin_ov.gebeurtenissen(g, _opm_alle(vakstatus_dataversie()), TUIN_ID, van, tot)
    layout.sectie("Wat er gebeurde", len(rijen))
    if rijen:
        st.caption(tuin_ov.samenvatting(rijen))
        gebeurd = pd.DataFrame([{"Datum": format_datum(r["datum"]), "Afd.": r["afdeling"], "Vak": r["vak"],
                                 "Code": r["code"] or "-", "Wat": r["soort"], "Toelichting": r["tekst"]}
                                for r in rijen])
        keuze = toon_tabel(gebeurd, TU_GEBEURTENIS_KOLOMMEN, vast=("Datum",), sleutel="tu_gebeurd")
        gekozen = keuze.selection.rows if keuze else []
        if gekozen and gekozen != st.session_state.get("tu_gebeurd_open"):
            st.session_state["tu_gebeurd_open"] = gekozen
            if rijen[gekozen[0]]["teelt_id"]:
                vak_venster(rijen[gekozen[0]]["teelt_id"], vandaag)
        elif not gekozen:
            st.session_state["tu_gebeurd_open"] = None
    else:
        gebeurd = pd.DataFrame()
        st.caption("Niets geregistreerd: geen planten, Florgib, oogst of opmerkingen.")

    # Hoofdweergave: de kengetallen per afdeling, dan het verloop per uur.
    layout.sectie("Per afdeling")
    kolommen = volgorde + [tuin_ov.HELE_TUIN]
    vergelijkingstabel.toon(
        TU_KENGETALLEN, kolommen,
        vergelijkingstabel.Tabeldata(nu=nu["waarden"], toen=toen["waarden"], n=nu["n"], n_toen=toen["n"],
                                     verwacht=nu["verwacht"], ontbreekt=nu["ontbreekt"], label_toen=label,
                                     beste=False, totaal_kolom=tuin_ov.HELE_TUIN),
        sleutel="tu_verloop", verloop=_tu_verloop_fn(g, TUIN_ID, sleutel, periode, vandaag, kolommen),
        verloop_titel=f"Verloop over 12 {'dagen' if periode == perioden.DAG else 'weken'}")
    laatste_uur = uur["tijdstip"].max() if not uur.empty else None
    uitleg_help.voetnoot(
        (format_datum(van) if van == tot else f"{format_datum(van)} t/m {format_datum(tot)}")
        + (" (loopt nog)" if loopt else "")
        + f" · kleine regel = {'vorige ' + enkel if soort == 'vorige' else 'zelfde ' + enkel + ' vorig jaar'}"
        + (f" · klimaat per uur t/m {laatste_uur[8:10]}-{laatste_uur[5:7]} {laatste_uur[11:]}" if laatste_uur else ""))

    reeksen, per_uur = _tu_reeksen(uur, meteo, g, TUIN_ID, van, tot)
    layout.sectie("Temperatuur en RV " + ("per uur" if per_uur else "per dag"))
    if not per_uur and van == tot:
        st.caption(f"Voor {TUIN_NAAM} is er (nog) geen klimaat per uur; kies Week voor het verloop per dag.")
    else:
        _tu_grafiek(reeksen, "temp", "Temperatuur (°C)", volgorde, per_uur, van == tot)
        _tu_grafiek(reeksen, "rv", "RV (%)", volgorde, per_uur, van == tot)
        legend.legenda([{"kleur": AFDELING_KLEUR.get(a, BUITEN_KLEUR), "vorm": "lijn", "label": tuin_ov.kolom(a)}
                        for a in afds]
                       + ([{"kleur": BUITEN_KLEUR, "vorm": "lijn", "label": "buiten",
                            "stijl": "border-top-style:dashed;"}] if per_uur and not meteo.empty else []))

    if not uur.empty:
        with layout.uitklap("Klimaat per uur", len(uur) // max(len(afds), 1)):
            breed = uur.pivot_table(index="tijdstip", columns="afdeling", values=["temp", "rv"]).sort_index()
            breed.columns = [f"{'Temp' if v == 'temp' else 'RV'} afd. {a}" for v, a in breed.columns]
            breed = breed[[f"{v} afd. {a}" for a in afds for v in ("Temp", "RV") if f"{v} afd. {a}" in breed]]
            if not meteo.empty:
                breed = breed.join(meteo.set_index("tijdstip")[["buiten_temp", "buiten_rv", "straling"]].rename(
                    columns={"buiten_temp": "Temp buiten", "buiten_rv": "RV buiten", "straling": "Straling"}))
            breed = breed.reset_index().rename(columns={"tijdstip": "Tijd"})
            toon_tabel(breed, [("Tijd", "Tijd", "tekst", None, "medium")]
                       + [(k, k, "getal", "%d" if k.startswith("RV") or k == "Straling" else "%.1f", "small")
                          for k in breed.columns if k != "Tijd"], vast=("Tijd",))

    tabel = pd.DataFrame([{"Groep": k.groep, "Kengetal": k.label, "Eenheid": k.eenheid,
                           **{kol: nu["waarden"].get(kol, {}).get(k.sleutel) for kol in kolommen},
                           **{f"{kol} ({label})": toen["waarden"].get(kol, {}).get(k.sleutel) for kol in kolommen}}
                          for k in TU_KENGETALLEN])
    layout.export(excel_bestand({"Per afdeling": tabel, "Wat er gebeurde": gebeurd,
                                 "Klimaat per uur": uur, "Buiten per uur": meteo}),
                  f"{TUIN_NAAM.lower().replace(' ', '_')}_{van:%d-%m-%y}" + ("" if van == tot else f"_{tot:%d-%m-%y}")
                  + ".xlsx", sleutel="tu_excel")


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
    Kengetal("geplant", "Geplant", "Teelt", "st", 0, "Totaal aantal planten in de vakken van de teelt.",
             n_eenheid="vakken"),
    Kengetal("fase1", "Fase 1 (planten → Florgib)", "Teelt", "d", 0, "Dagen van planten tot de Florgib.",
             n_eenheid="vakken"),
    Kengetal("oogst", "Oogst", "Teelt", uitleg="Eerste en laatste oogstdatum; ⏳ = met de prognose van het teeltmodel (Overzicht) "
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
    Kengetal("geoogst", "Geoogste stelen", "Resultaat", "st", 0,
             "Totaal geoogste stelen: emmers × 100, anders geplant × (1 − uitval). ⏳ = met lopende vakken "
             "(de emmers tot nu).", n_eenheid="vakken"),
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
TL_KOLOMMEN = [("geplant", "Planten", 0), ("geoogst", "Geoogst (st)", 0), ("uitval", "Uitval %", 1),
               ("lengte_fg", "Lengte half cm", 1), ("lengte", "Lengte cm", 1), ("gewicht", "Gewicht g", 0),
               ("fase1", "Fase 1 (d)", 0), ("fase2", "Fase 2 (d)", 0), ("teeltduur", "Duur (d)", 0),
               ("lichtsom", "Licht/dag", 0), ("temp", "Etmaal °C", 1), ("afwijking", "Afw. lichtlijn", 1),
               ("warmte", "Warmte MJ/m²", 0), ("water", "Water l/m²", 0), ("stek", "Stekcijfer", 0)]


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


def vak_venster(teelt_id, vandaag, vakken=None):
    """
    De vakpopup: één voor de hele app, vanuit elke pagina hetzelfde, voor lopende en afgeronde vakken. De
    inhoud is vak_details(); onderaan de knop naar de pagina Teelt (in de tuin van het vak) met alle gegevens.
    """
    data = _nu_alles(vandaag)[0]
    t = next((r for r in data["teelten"].to_dict("records") if r["id"] == teelt_id), None)
    if t is None:
        return
    tuin = next(x for x in TUINEN if x["id"] == t["tuin_id"])

    @st.dialog(f"Vak {t['vaknummer']} · {tuin['naam']} · {t['code'] or '-'}", width="large")
    def _venster():
        vak_details(teelt_id, vandaag, vakken)
        if st.button("Alles over dit vak", key=f"vak_opzoeken_{teelt_id}", icon=":material/search:"):
            ga_naar("teelt", {"tl_teelt": teeltvgl.plantweek(vs.als_datum(t["datum_teelt_start"])),
                              "op_vak": int(teelt_id), "op_zoek": None}, tuin=tuin["nummer"])

    _venster()


@st.cache_data(ttl=600, show_spinner=False)
def _behandelingen(tuin_id, van, tot):
    """Behandelingen (Agro4all) van een tuin over van..tot; tien minuten bewaard (de import draait elk uur)."""
    return get_behandelingen(tuin_id, van, tot)


BEH_KOLOMMEN = [
    ("Datum", "Datum", "datum", None, "small"), ("Vak", "Vak", "getal", "%d", "small"),
    ("Soort", "Soort", "tekst", None, "medium"), ("Middel", "Middel", "tekst", None, "medium"),
    ("Hoeveelheid", "Hoeveelheid", "tekst", None, "medium"), ("Tegen", "Tegen", "tekst", None, "medium"),
    ("Methode", "Methode", "tekst", None, "small"), ("Vakken", "Op vakken", "tekst", None, "medium"),
]


def toon_behandelingen(rijen, sleutel=None, met_vak=False):
    """
    Behandelingen als tabel, oud naar nieuw: per middel de hoeveelheid voor het vak (het totaal van de
    registratie naar rato van de m²; in de tankmix) en op hoeveel vakken die registratie is uitgevoerd.
    """
    if not rijen:
        st.caption("Geen behandelingen geregistreerd (Agro4all en klimaatregistratie; behandelingen op de hele "
                   "tuin staan er niet bij).")
        return
    vakken_per_registratie = {}
    for b in rijen:
        vakken_per_registratie.setdefault(b.get("registratie"), set()).add(int(b["vaknummer"]))
    df = pd.DataFrame([{
        "Datum": format_datum(b["datum"]), "Vak": b["vaknummer"], "Soort": b["type"] or "-", "Middel": b["middel"],
        "Hoeveelheid": (f"{fmt_kort(b['dosering'], 2)} {b['eenheid'] or ''}".strip() if b["dosering"] is not None
                        else "-") + (f" in {b['mix']}" if b.get("mix") else "")
                       + (" (toevoeging)" if b.get("opmerking") == "toevoeging" else ""),
        "Tegen": b.get("doel") or "-", "Methode": b.get("methode") or "-",
        "Vakken": str(b["aantal_vakken"]) if b.get("aantal_vakken") else "-",
    } for b in rijen])
    if met_vak:
        df["Vakken"] = [", ".join(str(v) for v in sorted(vakken_per_registratie.get(b.get("registratie"), ())))
                        for b in rijen]
    kolommen = [k for k in BEH_KOLOMMEN if met_vak or k[0] != "Vak"]
    toon_tabel(df, kolommen, vast=("Datum",), sleutel=sleutel)


def vak_details(teelt_id, vandaag, vakken=None):
    """
    Alles over één vak, voor lopende en afgeronde vakken: kengetallen, opmerkingen, tijdlijn (met watergift),
    voortgang, klimaat, lichtsom, groei, stek, de watergift per dag en de vergelijking met vorig jaar en de
    referentievakken. In de vakpopup en op de pagina Teelt (één tuin). `vakken` = rijen uit _tl_vakken (voor
    uitval, lengte en gewicht); standaard alle.
    """
    data, model, stook, _ = _nu_alles(vandaag)
    alle = data["teelten"].to_dict("records")
    t = next((r for r in alle if r["id"] == teelt_id), None)
    if t is None:
        return
    if vakken is None:
        vakken = _tl_vakken(vakstatus_dataversie(), vandaag)
    rij = next((r for r in vakken if r["id"] == teelt_id), None) or {}
    tuin = next(x for x in TUINEN if x["id"] == t["tuin_id"])

    start, oogst = vs.als_datum(t["datum_teelt_start"]), vs.als_datum(t["datum_oogst"])
    s = vs.beoordeel_teelt(t, alle, oogst or vandaag, bereken_verwachte_oogstdatum)
    u = s["stook"] = stook.get(teelt_id) if not oogst else None
    s["prognose"] = u["prognose"] if u else None
    s["prognose_dagen"] = (u["prognose"] - s["plan"]).days if u and u["prognose"] and s["plan"] else None
    s["klasse"] = "grijs" if not u else ("rijp" if u["oogstrijp"] else tp.dagen_klasse(s["prognose_dagen"]))
    if not s["florgib"] and rij.get("florgib"):
        s["florgib"] = rij["florgib"]
    florgib = (format_datum(s["florgib"]) if s["florgib"]
               else f"verw. {format_datum(u['florgib_verwacht'])}" if u and u["florgib_verwacht"] else LEEG)
    kengetallen = [
        {"label": "Afdeling", "waarde": fmt_kort(t["afdeling"])},
        {"label": "Ras", "waarde": t["ras"] or LEEG},
        {"label": "Geplant", "waarde": f"{format_datum(start)} (wk {s['plantweek']})"},
        {"label": "Teeltduur" if oogst else "Leeftijd",
         "waarde": fmt_dagen((oogst - start).days if oogst else s["leeftijd"])},
        {"label": "Florgib", "waarde": florgib,
         "help": "Geregistreerde Florgib, of de verwachte: de dag waarop het model het deel van de teelt "
                 "bereikt waarop meestal gespoten wordt"
                 + (f" ({fmt_getal(model.florgib_fractie * 100)} %)." if model and model.florgib_fractie else ".")},
    ]
    if not oogst:
        kengetallen += [
            {"label": "Correctie", "waarde": _nu_c_tekst(u),
             "delta": (f"{fmt_verschil(u['gewicht'], 0, 'g')} gewicht" if u and u["gewicht"] is not None
                       and u["c"] is not None and not tp.op_koers(u["c"]) else None),
             "help": "Constante afwijking van de lichtlijn vanaf vandaag waarmee de teelt precies op de "
                     f"plandatum oogstrijp is (grenzen {fmt_verschil(C_GRENZEN[0], 0)} tot "
                     f"{fmt_verschil(C_GRENZEN[1], 0)} °C). Gewichtseffect = correctie × het verband tussen "
                     "stooklijn en oogstgewicht in de historie (indicatief)."},
            {"label": "Status", "waarde": NU_STATUS_KORT[s["klasse"]]},
        ]
    kengetallen.append({"label": "Plan-oogst", "waarde": format_datum(s["plan"]) if s["plan"] else LEEG,
                        "help": "Startdatum + teeltduur uit de teeltduur-tabel."})
    if oogst:
        kengetallen += [
            {"label": "Oogst", "waarde": format_datum(oogst)},
            {"label": "Uitval", "waarde": fmt_pct(rij.get("uitval"))},
            {"label": "Oogstlengte", "waarde": fmt_getal(rij.get("lengte"), 1, "cm")},
            {"label": "Oogstgewicht", "waarde": fmt_getal(rij.get("gewicht"), 0, "g")},
        ]
    else:
        kengetallen.append(
            {"label": "Prognose", "waarde": format_datum(s["prognose"]) if s["prognose"] else LEEG,
             "delta": f"{fmt_verschil(s['prognose_dagen'], 0)} d t.o.v. plan" if s["prognose_dagen"] else None,
             "help": f"Oogst als de afdeling blijft stoken zoals de laatste {AFWIJKING_VENSTER_DAGEN} dagen "
                     "(gemiddelde afwijking van de lichtlijn), bij de gemiddelde lichtsom per kalenderweek."})
    toon_kengetallen(kengetallen)

    eind = oogst or vandaag
    klimaat = pd.DataFrame(
        get_klimaatdata_dagen_voor_periode(t["afdeling"], str(start), str(eind), t["tuin_id"]),
        columns=["datum", "temp_24h", "rv_24h", "lichtsom", "temp_dag", "temp_nacht", "rv_dag", "rv_nacht"])
    water = [{"datum": d, "liter": liter}
             for d, liter in get_watergift_dagen_voor_periode(t["vaknummer"], str(start), str(eind), t["tuin_id"])]
    toon_opmerkingen(teelt_id)
    teelt_detail(s, klimaat, water, model)
    toon_watergift_vak(t["tuin_id"], t["vaknummer"], start, eind, florgib=s["florgib"])
    behandeld = [b for b in _behandelingen(t["tuin_id"], start, eind) if int(b["vaknummer"]) == int(t["vaknummer"])]
    with layout.uitklap("Behandelingen", len(behandeld)):
        toon_behandelingen(behandeld)
    with layout.uitklap("Vergelijking met vorig jaar en de referentievakken"):
        st.dataframe(_nu_vergelijking(s, {"tuin": tuin, "alle": alle}, data), hide_index=True,
                     use_container_width=True)


def _tl_vakkentabel(groep, vandaag, markeer=(), sleutel="tl_teelten", bij_klik=None):
    """
    De vakken van de teelt naast elkaar; een klik op een regel opent het vak (of roept `bij_klik(teelt_id)`
    aan). `markeer`: ids om op te lichten.
    """
    groep = sorted(groep, key=lambda t: _tv_volgorde(t["tuin_id"], t["afdeling"], t["vak"]))
    meer_tuinen = len({t["tuin_id"] for t in groep}) > 1
    rijen = []
    for t in groep:
        rij = {**({"Tuin": _tuinnaam_van.get(t["tuin_id"], "?")} if meer_tuinen else {}),
               "Afd.": t["afdeling"], "Vak": t["vak"],
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
        # Totalen (geplant, geoogst) hangen af van de grootte van het vak: niet kleuren.
        if not richting or sleutel in teeltvgl.SOMMEN:
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
                if kop in kleuren.columns:
                    kleuren.loc[i, kop] = "background-color: rgba(237,161,0,0.30); font-weight: 600"

    def _opmaak(sleutel, decimalen):
        def formatteer(x):
            if x is None or x != x:
                return LEEG
            return fmt_verschil(x, decimalen) if sleutel == "afwijking" else fmt_getal(x, decimalen)
        return formatteer

    # Streamlit toont een ontbrekend getal als "None", ook met een Styler-opmaak: de kengetallen worden zelf
    # tekst ("–" als leeg), rechts uitgelijnd en met cijferspaties tot gelijke breedte, zodat sorteren klopt.
    for sleutel, kop, d in TL_KOLOMMEN:
        tekst = df[kop].map(_opmaak(sleutel, d))
        breed = tekst.str.len().max()
        df[kop] = tekst.map(lambda t: t if t == LEEG else t.rjust(breed, "\u2007"))
    styler = df.style.apply(lambda _: kleuren, axis=None)
    keuze = st.dataframe(
        styler, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
        key=sleutel, column_config={
            "Tuin": st.column_config.TextColumn(pinned=True), "Afd.": st.column_config.NumberColumn(pinned=True),
            "Vak": st.column_config.NumberColumn(pinned=True), "Code": st.column_config.TextColumn(pinned=True),
            **{kop: st.column_config.TextColumn(alignment="right") for _, kop, _ in TL_KOLOMMEN},
        })
    uitleg_help.voetnoot("Klik op een regel voor het vak. Groen/rood = minstens 5 % beter/slechter dan het "
                         "gemiddelde van de teelt.")
    gekozen = keuze.selection.rows if keuze else []
    vorige = st.session_state.get(f"{sleutel}_gekozen")
    if gekozen and gekozen != vorige:
        st.session_state[f"{sleutel}_gekozen"] = gekozen
        if bij_klik:
            bij_klik(groep[gekozen[0]]["id"])
        else:
            vak_venster(groep[gekozen[0]]["id"], vandaag, groep)
    elif not gekozen:
        st.session_state[f"{sleutel}_gekozen"] = None


# --- TEELT bij één tuin (vroeger Opzoeken): een teelt of één vak met alle informatie die er is ---
#
# Een teelt = alle vakken uit één plantweek (dezelfde keuze als bij Beide, sleutel tl_teelt). Kies je
# één vak, dan bovenaan alles uit de vakpopup (vak_details) en daaronder elke bron als tabel. Het knippen per
# vak op de eigen periode (planten t/m oogst) staat in logic/opzoeken.py.
OP_ALLE = "alle"


@st.cache_data(ttl=600, show_spinner="Gegevens ophalen…")
def _op_gegevens(versie, ids, van, tot):
    """Alle bronnen voor de vakken `ids` (database.get_opzoek_gegevens). `versie` is alleen een cachesleutel."""
    return get_opzoek_gegevens(list(ids), van, tot)


def _op_tabel(rijen, kolommen, leeg="Niets vastgelegd."):
    """
    Een tabel uit rijen (dicts of DataFrame) met `kolommen` = [(veld, kop, soort)], soort = datum / tijd /
    getal:<decimalen> / tekst. Geeft het DataFrame terug (voor de export).
    """
    rijen = rijen.to_dict("records") if isinstance(rijen, pd.DataFrame) else list(rijen)
    if not rijen:
        st.caption(leeg)
        return pd.DataFrame(columns=[kop for _, kop, _ in kolommen])

    def waarde(r, veld, soort):
        w = r.get(veld)
        if w is None or w != w:
            return None
        if soort == "datum":
            return format_datum(str(w)[:10])
        if soort == "tijd":
            t = pd.Timestamp(w)
            t = t.tz_convert("Europe/Amsterdam") if t.tzinfo else t
            return f"{t:%d-%m-%y %H:%M}"
        if soort.startswith("getal"):
            return float(w)
        return w

    df = pd.DataFrame([{kop: waarde(r, veld, soort) for veld, kop, soort in kolommen} for r in rijen])
    config = {kop: st.column_config.NumberColumn(format=f"%.{soort.split(':')[1]}f" if ":" in soort else None)
              for _veld, kop, soort in kolommen if soort.startswith("getal")}
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=config)
    return df


def _op_samenvatting(groep_db, emmers, week):
    """Kengetallen van de hele teelt."""
    s = opzoeken.samenvatting(groep_db, emmers)

    def bereik(a, b):
        if not a:
            return LEEG
        if a == b:
            return format_datum(a)
        return f"{a:%d-%m} – {format_datum(b)}" if a.year == b.year else f"{format_datum(a)} – {format_datum(b)}"

    toon_kengetallen([
        {"label": "Teelt", "waarde": f"wk {week[1]} '{str(week[0])[2:]}"},
        {"label": "Vakken", "waarde": str(s["vakken"]),
         "delta": f"{s['lopend']} lopend" if s["lopend"] else "alle afgerond"},
        {"label": "Geplant", "waarde": bereik(s["eerste_start"], s["laatste_start"])},
        {"label": "Ras", "waarde": ", ".join(s["rassen"])},
        {"label": "Planten", "waarde": fmt_kort(s["planten"]) if s["planten"] else LEEG},
        {"label": "Florgib", "waarde": bereik(s["eerste_florgib"], s["laatste_florgib"])},
        {"label": "Oogst", "waarde": bereik(s["eerste_oogst"], s["laatste_oogst"]),
         "delta": "nog niet alles geoogst" if s["lopend"] and s["eerste_oogst"] else None},
        {"label": "Geoogst", "waarde": f"{fmt_kort(s['stelen'])} stelen", "delta": f"{fmt_kort(s['emmers'])} emmers"},
        {"label": "Uitval", "waarde": fmt_pct(s["uitval"]),
         "help": "Over de afgeronde vakken met een plantaantal: (planten − emmers × 100) / planten."},
    ])


def _op_prognosegrafiek(prognose):
    """Hoe de prognose-oogst per vak in de loop van de teelt veranderde, met de plan-oogst gestippeld."""
    if prognose.empty:
        return
    df = prognose.dropna(subset=["prognose_oogst"]).copy()
    if df.empty:
        return
    for kolom in ("datum", "prognose_oogst", "plan_oogst"):
        df[kolom] = pd.to_datetime(df[kolom])
    basis = alt.Chart(df).encode(x=alt.X("datum:T", title="Dag van de prognose", axis=alt.Axis(format="%d-%m")))
    lijnen = basis.mark_line(point=alt.OverlayMarkDef(size=18)).encode(
        y=alt.Y("prognose_oogst:T", title="Prognose-oogst", axis=alt.Axis(format="%d-%m")),
        color=alt.Color("code:N", title="Vak", legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("code:N", title="Code"), alt.Tooltip("datum:T", title="Dag", format="%d-%m-%y"),
                 alt.Tooltip("prognose_oogst:T", title="Prognose", format="%d-%m-%y"),
                 alt.Tooltip("plan_oogst:T", title="Plan", format="%d-%m-%y")])
    plan = basis.mark_line(strokeDash=[4, 3], opacity=0.6).encode(
        y="plan_oogst:T", color=alt.Color("code:N", legend=None))
    st.altair_chart(alt.layer(plan, lijnen).properties(height=240), use_container_width=True)
    uitleg_help.voetnoot("Doorgetrokken = prognose-oogst zoals die die dag berekend werd; gestippeld = plan-oogst.")


OP_SECTIES = [
    ("Oogst (emmers)", "emmers", [("datum", "Datum", "datum"), ("code", "Code", "tekst"),
                                  ("emmers", "Emmers", "getal:0"), ("stelen", "Stelen", "getal:0")]),
    ("Florgib en lengtes", "vakken", [
        ("code", "Code", "tekst"), ("start", "Geplant", "datum"), ("planten", "Planten", "getal:0"),
        ("florgib", "Florgib", "datum"), ("lengte_florgib", "Lengte bij Florgib (cm)", "getal:1"),
        ("florgib_gram", "Florgib (g)", "getal:1"), ("oogstdatum", "Oogst", "datum"),
        ("oogstlengte", "Oogstlengte (cm)", "getal:1"), ("oogstgewicht", "Oogstgewicht (g)", "getal:0"),
        ("rijpheid", "Rijpheid", "tekst"), ("uitval_pct", "Uitval vastgelegd (%)", "getal:1")]),
    ("Opmerkingen", "opmerkingen", [
        ("datum", "Datum", "datum"), ("code", "Code", "tekst"), ("categorie", "Categorie", "tekst"),
        ("tekst", "Opmerking", "tekst"), ("gebruiker", "Door", "tekst")]),
    ("Stek", "stek", [
        ("code", "Code", "tekst"), ("ras", "Ras", "tekst"), ("bakjes", "Bakjes", "getal:0"),
        ("wortel", "Wortel", "tekst"), ("plantmaat", "Plantmaat", "tekst"), ("uniformiteit", "Uniformiteit", "tekst"),
        ("beoordeling", "Cijfer", "getal:1"), ("opmerking", "Opmerking", "tekst")]),
    ("Watergift: alle dagen", "water", [
        ("datum", "Datum", "datum"), ("code", "Code", "tekst"), ("liter_per_m2", "l/m²", "getal:1"),
        ("beurten", "Beurten", "getal:0"), ("ec", "EC", "getal:2"), ("ph", "pH", "getal:2"), ("bron", "Bron", "tekst")]),
    ("Gietbeurten", "beurten", [
        ("start", "Start", "tijd"), ("eind", "Eind", "tijd"), ("code", "Code", "tekst"),
        ("liter_per_m2", "l/m²", "getal:2"), ("ec", "EC", "getal:2"), ("ph", "pH", "getal:2"),
        ("flow", "Flow (m³/u)", "getal:2")]),
    ("EC/pH watersysteem", "kwaliteit", [
        ("datum", "Datum", "datum"), ("watersysteem", "Systeem", "getal:0"), ("ec_gift", "EC gift", "getal:2"),
        ("ph_gift", "pH gift", "getal:2"), ("ec_gem", "EC gemeten", "getal:2"), ("ph_gem", "pH gemeten", "getal:2"),
        ("ec_doel", "EC ingesteld", "getal:2"), ("ph_doel", "pH ingesteld", "getal:2"),
        ("ec_aanvoer", "EC uitgangswater", "getal:3"), ("recept", "Recept", "getal:0")]),
    ("Klimaat van de afdeling", "klimaat", [
        ("datum", "Datum", "datum"), ("afdeling", "Afd.", "getal:0"), ("etmaal_temp", "Etmaal (°C)", "getal:1"),
        ("temp_dag", "Dag (°C)", "getal:1"), ("temp_nacht", "Nacht (°C)", "getal:1"), ("rv", "RV (%)", "getal:1"),
        ("rv_dag", "RV dag", "getal:1"), ("rv_nacht", "RV nacht", "getal:1"),
        ("lichtsom", "Lichtsom (J/cm²)", "getal:0")]),
    ("Warmte en gas (hele kas)", "energie", [
        ("datum", "Datum", "datum"), ("warmte_mj_per_m2", "Warmte (MJ/m²)", "getal:2"),
        ("warmte_mj_totaal", "Warmte totaal (MJ)", "getal:0"), ("gas_m3_per_m2", "Gas (m³/m²)", "getal:3"),
        ("gas_m3_totaal", "Gas totaal (m³)", "getal:0")]),
    ("Verloop van de prognose", "prognose", [
        ("datum", "Dag", "datum"), ("code", "Code", "tekst"), ("leeftijd_d", "Leeftijd (d)", "getal:0"),
        ("fase", "Fase", "tekst"), ("gedaan", "Gedaan", "getal:2"), ("plan_oogst", "Plan", "datum"),
        ("prognose_oogst", "Prognose", "datum"), ("correctie_c", "Correctie (°C)", "getal:1"),
        ("stooklijn", "Stooklijn (°C)", "getal:1")]),
    ("Behandelingen", "behandelingen", [
        ("datum", "Datum", "datum"), ("code", "Code", "tekst"), ("type", "Soort", "tekst"),
        ("middel", "Middel", "tekst"), ("dosering", "Hoeveelheid", "getal:2"), ("eenheid", "Eenheid", "tekst"),
        ("mix", "Tankmix", "tekst"), ("doel", "Tegen", "tekst"), ("methode", "Methode", "tekst"),
        ("aantal_vakken", "Op vakken", "getal:0"), ("opmerking", "Opmerking", "tekst")]),
    ("Teelthistorie (leerdata)", "historie", [
        ("code", "Code", "tekst"), ("startdatum", "Geplant", "datum"), ("oogstdatum", "Oogst", "datum"),
        ("teeltduur_dagen", "Teeltduur (d)", "getal:0"), ("florgib_datum", "Florgib", "datum"),
        ("florgib_bron", "Florgib uit", "tekst"), ("lengte_eind", "Lengte (cm)", "getal:1"),
        ("oogstgewicht", "Gewicht (g)", "getal:0"), ("bron", "Bron", "tekst")]),
    ("Wijzigingen", "wijzigingen", [
        ("tijdstip", "Wanneer", "tijd"), ("gebruiker", "Wie", "tekst"), ("actie", "Actie", "tekst"),
        ("entiteit", "Wat", "tekst"), ("omschrijving", "Omschrijving", "tekst")]),
]


def _op_bronnen(gegevens, groep_db, keuze_ids, vandaag):
    """{bron: rijen} voor de gekozen vakken: op teelt-id, of per vak/afdeling/tuin op de eigen periode."""
    perioden_ = opzoeken.perioden(groep_db, vandaag)
    codes = {int(r["id"]): r["code"] for r in groep_db}

    def op_id(df):
        return df[df["teelt_id"].isin(keuze_ids)] if not df.empty else df

    def rijen(df):
        return df.to_dict("records") if not df.empty else []

    energie = pd.DataFrame()
    if not gegevens["warmte"].empty or not gegevens["gas"].empty:
        energie = gegevens["warmte"].merge(gegevens["gas"], on=["tuin_id", "datum"], how="outer").sort_values("datum")
    wijzigingen = gegevens["wijzigingen"]
    if not wijzigingen.empty:
        wijzigingen = wijzigingen[wijzigingen["entiteit_id"].isin({str(i) for i in keuze_ids})]
    return {
        "emmers": op_id(gegevens["emmers"]), "vakken": groep_db, "opmerkingen": op_id(gegevens["opmerkingen"]),
        "stek": op_id(gegevens["stek"]), "prognose": op_id(gegevens["prognose"]),
        "historie": op_id(gegevens["historie"]), "wijzigingen": wijzigingen,
        "water": opzoeken.bij_vak(rijen(gegevens["water"]), perioden_, codes),
        "beurten": opzoeken.bij_vak(rijen(gegevens["beurten"]), perioden_, codes),
        "behandelingen": opzoeken.bij_vak(rijen(gegevens["behandelingen"]), perioden_, codes),
        "klimaat": opzoeken.bij_afdeling(rijen(gegevens["klimaat"]), perioden_),
        "kwaliteit": opzoeken.bij_tuin(rijen(gegevens["kwaliteit"]), perioden_),
        "energie": opzoeken.bij_tuin(rijen(energie), perioden_),
    }


def _opzoeken_inhoud():
    """Pagina Teelt bij één tuin: de teelt (of één vak) in die tuin met alle informatie die er is."""
    vandaag = date.today()
    versie = vakstatus_dataversie()
    alle = _tl_vakken(versie, vandaag)
    tuin_ids = {t["id"] for t in TUINEN if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE}
    vakken = [t for t in alle if t["tuin_id"] in tuin_ids]
    if not vakken:
        st.info("Nog geen geplante vakken in deze tuin.")
        return

    # Zoeken vóór het tekenen van de keuzes: een gevonden code zet de teelt en het vak meteen goed.
    vak_gevonden, melding = opzoeken.zoek(vakken, filters.bewaard("op_zoek", ""))
    if vak_gevonden:
        filters.bewaar("tl_teelt", teeltvgl.plantweek(vak_gevonden["start"]))
        filters.bewaar("op_vak", vak_gevonden["id"])
        filters.bewaar("op_zoek", "")

    per_week = {}
    for t in vakken:
        w = teeltvgl.plantweek(t["start"])
        per_week[w] = per_week.get(w, 0) + 1
    balk = layout.filterbalk("opzoeken")
    week = filters.bladeraar(
        "tl_teelt", sorted(per_week), teeltvgl.standaard_plantweek(teeltvgl.plantweken(alle)), plek=balk,
        naam="teelt", format_func=lambda w: f"Teelt wk {w[1]} '{str(w[0])[2:]} · {_vakken_tekst(per_week[w])}",
        breedte=230, spring_label="Spring naar plantweek")
    dagdata = _tl_dagdata(versie)
    groep = sorted([teeltvgl.met_dagdata(t, dagdata, vandaag - timedelta(days=1))
                    for t in vakken if teeltvgl.plantweek(t["start"]) == week],
                   key=lambda t: _tv_volgorde(t["tuin_id"], t["afdeling"], t["vak"]))
    meer_tuinen = len({t["tuin_id"] for t in groep}) > 1
    namen = {OP_ALLE: "Alle vakken", **{
        t["id"]: (f"{_tuinnaam_van.get(t['tuin_id'], '?')} · " if meer_tuinen else "") + f"vak {t['vak']} · {t['code']}"
        for t in groep}}
    gekozen = filters.keuze("Vak", [OP_ALLE] + [t["id"] for t in groep], "op_vak", OP_ALLE, plek=balk,
                            format_func=namen.get, breedte=175)
    filters.zoekveld("op_zoek", "Code of vak", plek=balk, breedte=150)
    if melding:
        st.warning(melding)

    ids = tuple(sorted(int(t["id"]) for t in groep))
    gegevens = _op_gegevens(versie, ids, min(vs.als_datum(t["start"]) for t in groep), vandaag)
    keuze_ids = set(ids) if gekozen == OP_ALLE else {int(gekozen)}
    groep_db = [r for r in gegevens["vakken"].to_dict("records") if int(r["id"]) in keuze_ids]
    bronnen = _op_bronnen(gegevens, groep_db, keuze_ids, vandaag)

    if gekozen == OP_ALLE:
        _op_samenvatting(groep_db, bronnen["emmers"].to_dict("records"), week)
    else:
        vak_details(int(gekozen), vandaag, alle)

    # De vakken van de teelt staan er altijd bij; een klik kiest dat vak op deze pagina. De tabel krijgt dan
    # een nieuwe sleutel, zodat de keuze leeg begint.
    layout.sectie("Vakken in deze teelt", len(groep))
    versie_tabel = st.session_state.setdefault("op_vakken_versie", 0)

    def kies(teelt_id):
        filters.bewaar("op_vak", int(teelt_id))
        st.session_state["op_vakken_versie"] = versie_tabel + 1
        st.rerun()

    _tl_vakkentabel(groep, vandaag, markeer=keuze_ids if gekozen != OP_ALLE else (),
                    sleutel=f"op_vakken_{versie_tabel}", bij_klik=kies)

    export = {}
    for titel, bron, kolommen in OP_SECTIES:
        rijen = bronnen[bron]
        with layout.uitklap(titel, len(rijen)):
            if bron == "prognose":
                _op_prognosegrafiek(rijen)
            export[titel] = _op_tabel(rijen, kolommen)
    naam = f"teelt_wk{week[1]}_{week[0]}" if gekozen == OP_ALLE else f"vak_{groep_db[0]['code'] if groep_db else gekozen}"
    layout.export(excel_bestand(export), f"{naam}.xlsx")


def _teelt_vak_in_tuin(vak):
    """Naar één vak in zijn eigen tuin op de pagina Teelt (tuinkeuze, teelt en vak gezet) en opnieuw tekenen."""
    nummer = _tuinnummer_van.get(vak["tuin_id"])
    st.session_state["tuin_weergave"] = nummer
    st.session_state["tuin_nummer"] = nummer
    filters.bewaar("tl_teelt", teeltvgl.plantweek(vak["start"]))
    filters.bewaar("op_vak", int(vak["id"]))
    st.rerun()


def _pagina_teelt():
    """
    Eén teelt (alle vakken uit één plantweek). De tuinkeuze bovenaan kiest de weergave: Beide = Tuin 1 naast
    Tuin 3 (vroeger Teeltvergelijking), Tuin 1 of Tuin 3 = alles over de teelt of één vak in die tuin (vroeger
    Opzoeken). De teeltkeuze (tl_teelt) blijft staan als je wisselt.
    """
    layout.pagina_kop(
        "Teelt",
        wat="Eén teelt = alle vakken uit één plantweek. Met de tuinkeuze bovenaan wissel je van weergave: bij "
            "**Beide** staan Tuin 1, Tuin 3 en het totaal naast elkaar (vergelijken); bij **Tuin 1** of **Tuin 3** "
            "zie je alles over de teelt of één vak in die tuin (opzoeken).",
        lezen=[
            "Blader met ◀ ▶ door de teelten, of klik op het label om direct naar een plantweek te springen. De "
            "teelt blijft staan als je van tuin wisselt.",
            "Zoek op een teeltcode (bijv. 2634301) of een vaknummer (de laatste planting in dat vak): het vak opent "
            "in zijn eigen tuin.",
            "**Beide**: kleine regel = dezelfde plantweek vorig jaar; loopt de teelt nog, dan klimaat en input van "
            "vorig jaar tot dezelfde teeltdag. Beweeg over een cel voor het verschil; klik op een kengetal voor het "
            "verloop over 12 plantweken. ⏳ = lopend vak (t/m gisteren; oogst en duur zijn de prognose). Een klik "
            "op een vak opent het in zijn eigen tuin.",
            "**Tuin 1 / Tuin 3**: kies bij Vak één vak of alle vakken. Bij één vak bovenaan alles uit de vakpopup; "
            "de vakken van de teelt staan er altijd bij (klik op een regel om dat vak te kiezen). Elke bron staat in "
            "een openklapmenu; watergift, klimaat, EC/pH, warmte en gas per vak van planten tot de oogst (of tot "
            "vandaag). Onderaan alles in één Excel-bestand.",
        ],
        bron="Samenvatting gewogen naar de m² van het vak. Registratie (vakken, emmers, opmerkingen, stek), Priva "
             "(klimaat, watergift, gietbeurten, EC/pH, energie), het prognoselogboek en het wijzigingenlog. Warmte "
             "en gas gelden voor de hele kas (per m²).",
        kleuren="Beide: groen/rood pijltje = beter/slechter dan vorig jaar; lichtgroen vak = beste tuin; ⚠ = niet "
                "alle vakken met data. Vakkentabel: groen/rood = minstens 5 % beter/slechter dan het gemiddelde van "
                "de teelt (alleen waar beter vastligt); oranje = het gekozen vak.",
    )
    if TUIN_WEERGAVE == "beide":
        _teeltvgl_inhoud()
    else:
        _opzoeken_inhoud()


def _teeltvgl_inhoud():
    """Pagina Teelt bij Beide: de teelt in Tuin 1 naast Tuin 3 en het totaal, het verloop en de vakken."""
    _tl_vandaag = date.today()
    _tl_gisteren = _tl_vandaag - timedelta(days=1)
    _tl_versie = vakstatus_dataversie()
    _tl_alle = _tl_vakken(_tl_versie, _tl_vandaag)
    _tl_dd = _tl_dagdata(_tl_versie)
    _tl_weken = teeltvgl.plantweken(_tl_alle)
    if not _tl_weken:
        st.info("Nog geen vakken.")
    else:
        _tl_tuin_ids = {t["id"] for t in TUINEN if TUIN_WEERGAVE == "beide" or t["nummer"] == TUIN_WEERGAVE}
        _tl_per_week = {}
        for t in _tl_alle:
            if t["tuin_id"] in _tl_tuin_ids:
                w = teeltvgl.plantweek(t["start"])
                _tl_per_week[w] = _tl_per_week.get(w, 0) + 1
        _tl_opties = sorted(_tl_per_week)
        if not _tl_opties:
            st.info("Nog geen vakken in deze tuin.")
            return
        _tl_gevonden, _tl_melding = opzoeken.zoek(_tl_alle, filters.bewaard("op_zoek", ""))
        if _tl_gevonden:
            filters.bewaar("op_zoek", "")
            _teelt_vak_in_tuin(_tl_gevonden)
        _tl_balk = layout.filterbalk("teeltvgl")
        _tl_week = filters.bladeraar(
            "tl_teelt", _tl_opties, teeltvgl.standaard_plantweek(_tl_weken), plek=_tl_balk, naam="teelt",
            format_func=lambda w: f"Teelt wk {w[1]} '{str(w[0])[2:]} · {_vakken_tekst(_tl_per_week[w])}",
            breedte=230, spring_label="Spring naar plantweek")
        filters.zoekveld("op_zoek", "Code of vak", plek=_tl_balk, breedte=150)
        if _tl_melding:
            st.warning(_tl_melding)
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

        layout.sectie("Tuin 1 naast Tuin 3")
        vergelijkingstabel.toon(
            TL_KENGETALLEN, [n for n, _ in _tl_tuinen] + ["Totaal"],
            vergelijkingstabel.Tabeldata(
                nu=_tl_nu["waarden"], toen=_tl_toen["waarden"], n=_tl_nu["n"], n_toen=_tl_toen["n"],
                verwacht=_tl_nu["verwacht"], bron=_tl_nu["bron"], bron_toen=_tl_toen["bron"],
                markering=_tl_nu["markering"], ontbreekt=_tl_nu["ontbreekt"],
                label_toen=f"wk {_tl_vorig[1]} '{str(_tl_vorig[0])[2:]}"),
            sleutel="tl_verloop", verloop=_tl_verloop, verloop_titel="Verloop over 12 plantweken")
        uitleg_help.voetnoot(
            f"Kleine regel = wk {_tl_vorig[1]} '{str(_tl_vorig[0])[2:]} ({_vakken_tekst(len(_tl_toen_groep))})"
            + (f", klimaat en input tot dezelfde teeltdag (dag {_tl_dag})" if _tl_dag is not None else ""))

        _tl_groep_tuin = [t for t in _tl_groep if t["tuin_id"] in _tl_tuin_ids]
        layout.sectie("Vakken van deze teelt", len(_tl_groep_tuin))
        _tl_vakkentabel(_tl_groep_tuin, _tl_vandaag, sleutel="tl_teelten",
                        bij_klik=lambda i: _teelt_vak_in_tuin(next(t for t in _tl_groep_tuin if t["id"] == i)))

        _tl_opm = opm_logic.filter_opmerkingen(_opm_alle(_tl_versie), teelt_ids={t["id"] for t in _tl_groep_tuin})
        if st.button(f"{len(_tl_opm)} opmerking{'' if len(_tl_opm) == 1 else 'en'} bij deze teelt",
                     icon=":material/arrow_forward:", type="tertiary", key="tl_naar_opmerkingen",
                     disabled=not _tl_opm):
            ga_naar("opmerkingen", {"opm_periode_lengte": "Alles", "opm_teelt": [_tl_week], "opm_vak": None,
                                    "opm_categorie": None, "opm_zoek": None})


# --- WATERGIFT: de gegevens achter het detail Watergift op Overzicht en het dagvenster ---
#
# Alles uit de database (watergift_dag, water_kwaliteit_dag, behandeling); rekenwerk in logic/watergift.py.


@st.cache_data(ttl=600, show_spinner="Watergift ophalen…")
def _wg_data(tuin_id, van, tot, versie):
    """Watergift, EC/pH, behandelingen en eerste emmers van één tuin; `versie` is alleen de cachesleutel."""
    return get_watergift_overzicht(tuin_id, van, tot)


DAGEN_KORT_WG = ["ma", "di", "wo", "do", "vr", "za", "zo"]


try:
    from zoneinfo import ZoneInfo
    _NL_TIJD = ZoneInfo("Europe/Amsterdam")
except Exception:                      # geen tijdzonedata op de server: vaste zomertijd, zoals priva_client
    _NL_TIJD = timezone(timedelta(hours=2))


def _wg_tijd(iso):
    """Een UTC-tijd uit watergift_beurt als Nederlandse kloktijd (uu:mm); de server zelf draait in UTC."""
    return datetime.fromisoformat(str(iso)).astimezone(_NL_TIJD).strftime("%H:%M")


def _wg_dag_venster(tuin, dag, gift, kwaliteit, vakken_df, beurten):
    """Popup met één dag: EC/pH van de giften, elke gietbeurt per vak en de opmerkingen van die dag."""
    @st.dialog(f"{DAGEN_KORT_WG[dag.weekday()]} {format_datum(dag)} · {tuin['naam']}", width="large")
    def _venster():
        k = next((x for x in kwaliteit if wg.als_datum(x["datum"]) == dag), None)
        if k:
            toon_kengetallen([
                {"label": "EC giften", "waarde": fmt_getal(k["ec_gift"], 2) if k["ec_gift"] is not None else LEEG,
                 "help": "Gemiddelde EC van alle giften van deze dag, gewogen naar de liters (mS/cm)."},
                {"label": "pH giften", "waarde": fmt_getal(k["ph_gift"], 2) if k["ph_gift"] is not None else LEEG,
                 "help": "Gemiddelde pH van alle giften van deze dag, gewogen naar de liters."},
                {"label": "EC ingesteld", "waarde": fmt_getal(k["ec_doel"], 2) if k["ec_doel"] is not None else LEEG},
                {"label": "EC uitgangswater", "waarde": fmt_getal(k["ec_aanvoer"], 2) if k["ec_aanvoer"] is not None
                 else LEEG, "help": "Gemeten EC van het water vóór bemesting (voorregeling)."},
                {"label": "Recept", "waarde": str(k["recept"]) if k["recept"] is not None else LEEG},
            ])
        else:
            st.caption("Geen EC/pH van deze dag (EC/pH wordt pas sinds 27-09-26 uit Priva gehaald).")
        vak_afd = {int(r.vaknummer): int(r.afdeling) for r in vakken_df.itertuples() if r.afdeling == r.afdeling}
        van_dag = [b for b in beurten if wg.als_datum(b["datum"]) == dag]
        if van_dag:
            # Elke gietbeurt, met EC/pH en flow gemiddeld over de beurt (zoals het kraanoverzicht in Priva).
            regels = [{"Afd.": vak_afd.get(int(b["vaknummer"])), "Vak": int(b["vaknummer"]),
                       "Tijd": f"{_wg_tijd(b['start'])}–{_wg_tijd(b['eind'])}", "Gift (l/m²)": b["liter_per_m2"],
                       "EC": b["ec"], "pH": b["ph"], "Flow (m³/uur)": b["flow"]} for b in van_dag]
            regels.sort(key=lambda x: (x["Tijd"], x["Vak"]))
            st.write("**Gietbeurten**")
            toon_tabel(pd.DataFrame(regels), [
                ("Tijd", "Tijd", "tekst", None, "small"), ("Afd.", "Afd.", "getal", "%d", "small"),
                ("Vak", "Vak", "getal", "%d", "small"), ("Gift (l/m²)", "Gift (l/m²)", "getal", "%.2f", "small"),
                ("EC", "EC", "getal", "%.2f", "small"), ("pH", "pH", "getal", "%.2f", "small"),
                ("Flow (m³/uur)", "Flow (m³/uur)", "getal", "%.1f", "small")], verberg_leeg=True)
        else:
            regels = [{"Afd.": vak_afd.get(int(r["vaknummer"])), "Vak": int(r["vaknummer"]),
                       "Gift (l/m²)": r["liter_per_m2"] or None, "Beurten": r["beurten"]}
                      for r in gift if wg.als_datum(r["datum"]) == dag and r["liter_per_m2"]]
            regels.sort(key=lambda x: (_tv_volgorde(tuin["id"], x["Afd."], x["Vak"]), x["Vak"]))
            st.write("**Gift per vak**")
            if regels:
                toon_tabel(pd.DataFrame(regels), [
                    ("Afd.", "Afd.", "getal", "%d", "small"), ("Vak", "Vak", "getal", "%d", "small"),
                    ("Gift (l/m²)", "Gift (l/m²)", "getal", "%.1f", "small"),
                    ("Beurten", "Beurten", "getal", "%d", "small")], verberg_leeg=True)
                st.caption("Van deze dag zijn geen losse gietbeurten bewaard (die worden sinds 2.4.1 opgeslagen).")
            else:
                st.caption("Geen watergift geregistreerd op deze dag.")
        opm = opm_logic.filter_opmerkingen(_opm_alle(vakstatus_dataversie()), tuinen={tuin["id"]}, van=dag, tot=dag)
        st.write("**Opmerkingen van deze dag**")
        toon_opmerkingenlijst(opm, f"wg_dag_opm_{tuin['id']}", "Geen opmerkingen op deze dag.")
    _venster()


def toon_watergift_vak(tuin_id, vaknummer, start, eind, florgib=None):
    """Voor de vakpopup: de watergift per dag van de teelt, met gietbeurten en de EC/pH van de gift van dit vak."""
    rijen = get_watergift_vak(tuin_id, vaknummer, start, eind)
    gegeven = [r for r in rijen if r[1]]
    with layout.uitklap(f"Watergift per dag ({len(gegeven)} giftdagen, "
                        f"{fmt_getal(sum(r[1] for r in gegeven), 0)} l/m² totaal)"):
        if florgib:
            uitleg_help.voetnoot(f"Na de Florgib ({format_datum(florgib)}) wordt er geen water meer gegeven.")
        if not gegeven:
            st.caption("Geen watergift geregistreerd in deze teelt.")
            return
        toon_tabel(pd.DataFrame([{"Datum": format_datum(d), "Gift (l/m²)": liter, "Beurten": beurten,
                                  "EC": ec, "pH": ph}
                                 for d, liter, beurten, _bron, ec, ph in gegeven]), [
            ("Datum", "Datum", "datum", None, "small"), ("Gift (l/m²)", "Gift (l/m²)", "getal", "%.1f", "small"),
            ("Beurten", "Beurten", "getal", "%d", "small"),
            ("EC", "EC", "getal", "%.2f", "small"), ("pH", "pH", "getal", "%.2f", "small")], verberg_leeg=True)


def _wg_excel(df, tuin, van, tot):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as schrijver:
        df.to_excel(schrijver, index=False, sheet_name=f"Watergift {tuin['naam']}"[:31])
    return buffer.getvalue()


# --- VOORUITBLIK: wat er de komende weken te planten en te oogsten staat (beide tuinen) ---
#
# Tuin 1 heeft grotere vakken dan tuin 3 (883 vs 550 m², 53064 vs 32688
# stelen bij 60/m²). "3 vakken" betekent dus niet in beide tuinen evenveel
# areaal of planten — daarom is dit om te zetten naar m² of aantal stelen.

def toon_vooruitblik(vandaag, n_weken=6, kop=True):
    """Tabel met per week en per tuin wat er geplant (concepten) en geoogst (lopend + concepten) wordt."""
    if kop:
        layout.sectie(f"Vooruitblik komende {n_weken} weken (beide tuinen)")
    eenheid = filters.weergave("Eenheid", ["Aantal vakken", "m²", "Aantal stelen"], "vooruitblik_eenheid",
                               "Aantal vakken")
    tuinen = sorted(TUINEN, key=lambda t: t["nummer"])
    vakgegevens = {t["id"]: get_vakgegevens(t["id"]) for t in tuinen}
    zondag_nu = kalender.week_begin(vandaag)
    week_starts = [zondag_nu + timedelta(weeks=i) for i in range(n_weken)]
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
        """Zondag van de week (zo–za); een oogst die al vóór deze week verwacht werd telt bij deze week."""
        return max(week_starts[0], kalender.week_begin(dag))

    rijen = [{"Week": "Week {1} - {0}".format(*kalender.week_sleutel(w)) + (" (deze week)" if i == 0 else "")}
             for i, w in enumerate(week_starts)]
    for tuin in tuinen:
        plant, oogst = {w: 0 for w in week_starts}, {w: 0 for w in week_starts}
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
        for rij, w in zip(rijen, week_starts):
            rij[f"{tuin['naam']} plant"] = round(plant[w])
            rij[f"{tuin['naam']} oogst"] = round(oogst[w])
    kolommen = [("Week", "Week", "tekst", None, "medium")]
    for tuin in tuinen:
        kolommen += [(f"{tuin['naam']} plant", f"{tuin['naam']} plant", "getal", "%d", "small"),
                     (f"{tuin['naam']} oogst", f"{tuin['naam']} oogst", "getal", "%d", "small")]
    toon_tabel(pd.DataFrame(rijen), kolommen)
    uitleg_help.voetnoot(
        f"In {eenheid.lower()}. Plant = concept-plantingen die week; oogst = lopende vakken en concepten waarvan "
        "de (verwachte) oogst in die week valt."
    )


# --- VAKKENREGISTER (Overzicht, onder de tijdlijn) ---
#
# Alle vakken in drie tabellen: lopend, te starten (bevestigd, startdatum in
# de toekomst) en afgerond. Een klik op een regel opent de vakpopup.

REGISTER_LOPEND = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Plantweek", "getal0"), ("Leeftijd (d)", "getal0"), ("Planten", "getal0"), ("Florgib", "datum"),
    ("Lengte bij Florgib (cm)", "getal1"), ("Plan-oogst", "datum"), ("Prognose", "datum"),
    ("Voor (−) / achter (+) (d)", "teken0"), ("Emmers tot nu", "getal0"), ("Water tot nu (l/m²)", "getal0"),
    ("Water tot nu (l)", "getal0"),
]
REGISTER_TE_STARTEN = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Plantweek", "getal0"), ("Planten", "getal0"), ("Plan-oogst", "datum"),
]
REGISTER_AFGEROND = [
    ("Tuin", "tekst"), ("Afd.", "getal0"), ("Vak", "getal0"), ("Code", "tekst"), ("Plantdatum", "datum"),
    ("Florgib", "datum"), ("Oogstdatum", "datum"), ("Teeltduur (d)", "getal0"), ("Fase 1 (d)", "getal0"),
    ("Fase 2 (d)", "getal0"), ("Geplant", "getal0"), ("Geoogst (stelen)", "getal0"), ("Uitval (%)", "getal1"),
    ("Oogstlengte (cm)", "getal1"),
    ("Oogstgewicht (g)", "getal0"), ("Lichtsom/dag", "getal0"), ("Etmaal (°C)", "getal1"),
    ("Afw. lichtlijn (°C)", "teken1"), ("Water (l/m²)", "getal0"), ("Water (l)", "getal0"),
    ("Warmte (MJ/m²)", "getal0"),
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


def _liters(liter_per_m2, m2):
    """Watergift van het hele vak (l) uit l/m² × de oppervlakte van het vak; None als een van beide ontbreekt."""
    return liter_per_m2 * m2 if liter_per_m2 is not None and m2 else None


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
            water = teeltvgl.met_dagdata(t, dd, gisteren)["water"]     # l/m² van planten t/m gisteren
            lopend.append({**basis, "Leeftijd (d)": (vandaag - start).days,
                           "Planten": vs._getal(k.get("aantal_planten")), "Florgib": t["florgib"],
                           "Lengte bij Florgib (cm)": vs._getal(k.get("lengte_half")), "Plan-oogst": plan,
                           "Prognose": prognose,
                           "Voor (−) / achter (+) (d)": (prognose - plan).days if prognose and plan else None,
                           "Emmers tot nu": stelen / 100 if stelen else None,
                           "Water tot nu (l/m²)": water, "Water tot nu (l)": _liters(water, t["m2"])})
        else:
            t = teeltvgl.met_dagdata(t, dd, gisteren)
            afgerond.append({**basis, "Florgib": t["florgib"], "Oogstdatum": t["oogst_echt"],
                             "Teeltduur (d)": t["teeltduur"], "Fase 1 (d)": t["fase1"], "Fase 2 (d)": t["fase2"],
                             "Geplant": vs._getal(k.get("aantal_planten")), "Geoogst (stelen)": vs._getal(k.get("stelen")),
                             "Uitval (%)": t["uitval"], "Oogstlengte (cm)": t["lengte"],
                             "Oogstgewicht (g)": t["gewicht"], "Lichtsom/dag": t["lichtsom"],
                             "Etmaal (°C)": t["temp"], "Afw. lichtlijn (°C)": t["afwijking"],
                             "Water (l/m²)": t["water"], "Water (l)": _liters(t["water"], t["m2"]),
                             "Warmte (MJ/m²)": t["warmte"]})
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
        vak_venster(rijen[gekozen[0]]["id"], vandaag, vakken)
    elif not gekozen:
        st.session_state[f"{sleutel}_open"] = None


REGISTER_LENGTES = ("Week", "Maand", "Kwartaal", "Jaar", "Alles")


def toon_vakkenregister(vandaag, tuin_weergave, afdelingen):
    """
    Vakkenregister onder de matrix: eigen filterbalk (plantperiode, ras, zoeken; tuin en afdeling komen van
    de kop en de filterbalk erboven), de tabbladen Lopend / Te starten / Afgerond en de export.
    """
    lopend, te_starten, afgerond, vakken = _register_rijen(vandaag)
    tuin_ids = {t["id"] for t in TUINEN if tuin_weergave == "beide" or t["nummer"] == tuin_weergave}
    alle = [r for r in lopend + te_starten + afgerond if r["_tuin_id"] in tuin_ids]
    layout.sectie("Vakkenregister")
    if not alle:
        st.info("Nog geen vakken geregistreerd. Plan en start ze in de tijdlijn hierboven.")
        return
    balk = layout.filterbalk("register")
    eerste, laatste = min(r["Plantdatum"] for r in alle), max(r["Plantdatum"] for r in alle)
    lengte, plantperiode = filters.periode(
        "reg_plantperiode", REGISTER_LENGTES, "Alles",
        opties_van=lambda n: [] if n == "Alles" else perioden.reeks(eerste, laatste, n),
        standaard_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(min(vandaag, laatste), n)[0],
        format_van=lambda n: lambda k: perioden.periode_label(k, n),
        huidig_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(vandaag, n)[0],
        label="Plantperiode", plek=balk)
    van, tot = perioden.periode_grenzen(plantperiode, lengte) if plantperiode else (date.min, date.max)
    rassen = sorted({r["Ras"] for r in alle if r["Ras"]})
    gekozen_ras = filters.keuzes("Ras", rassen, "reg_ras", plek=balk) if rassen else []
    zoek = filters.zoekveld("reg_zoek", "Vak of code, bijv. 12 of 2634301", plek=balk)

    def past(r):
        afd = afdelingen.get(r["_tuin_id"])
        return (r["_tuin_id"] in tuin_ids and (afd is None or r["Afd."] in afd)
                and van <= r["Plantdatum"] <= tot and (not gekozen_ras or r["Ras"] in gekozen_ras)
                and (not zoek or zoek == str(r["Vak"]) or zoek.lower() in str(r["Code"]).lower()))

    lopend, te_starten, afgerond = ([r for r in rijen if past(r)] for rijen in (lopend, te_starten, afgerond))
    tab_l, tab_s, tab_a = st.tabs([f"Lopend ({len(lopend)})", f"Te starten ({len(te_starten)})",
                                   f"Afgerond ({len(afgerond)})"])
    with tab_l:
        _register_tabel(lopend, REGISTER_LOPEND, "reg_lopend", vakken, vandaag)
        uitleg_help.voetnoot("Prognose = het teeltmodel bij de huidige stooklijn, zoals in de matrix.")
    with tab_s:
        _register_tabel(te_starten, REGISTER_TE_STARTEN, "reg_starten", vakken, vandaag, klikbaar=False)
        uitleg_help.voetnoot("Bevestigde vakken met een startdatum in de toekomst; concepten staan in de tijdlijn en de concepttabel.")
    with tab_a:
        # Laatst geoogst bovenaan, bij dezelfde oogstdatum in kasvolgorde.
        _register_tabel(afgerond, REGISTER_AFGEROND, "reg_afgerond", vakken, vandaag,
                        sorteer=lambda r: (-(r["Oogstdatum"] or date.min).toordinal(), r["_sorteer"]))
        uitleg_help.voetnoot("Klimaat en input over de hele teelt van het vak (planten t/m oogst).")

    def blad(rijen, kolommen):
        rijen = sorted(rijen, key=lambda r: (r["_sorteer"], r["Plantdatum"]))
        return pd.DataFrame([{naam: r.get(naam) for naam, _ in kolommen} for r in rijen],
                            columns=[naam for naam, _ in kolommen])

    layout.export(excel_bestand({"Lopend": blad(lopend, REGISTER_LOPEND),
                                 "Te starten": blad(te_starten, REGISTER_TE_STARTEN),
                                 "Afgerond": blad(afgerond, REGISTER_AFGEROND)}),
                  f"vakkenregister_{vandaag:%d-%m-%y}.xlsx", "Excel (register)", sleutel="reg_excel")


# --- PLANNEN (openklapmenu's op Overzicht) ---
def _planning_uitklappen(vandaag):
    """
    Het plannen onder de tijdlijn: de concepttabel (veel concepten tegelijk), de jaarplanning, het overzicht
    per plantweek en de vooruitblik. Plannen werkt per tuin: de tuin van de kop, bij Beide de laatst gekozen
    tuin.
    """
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

    with layout.uitklap(f"Concept-planningen · {TUIN_NAAM}"):
        alles_tonen = filters.schakelaar("Alle concepten tonen", "planning_alles", False,
                                         help="Standaard alleen de concepten die in de komende 8 weken starten.")
        planning_rijen = get_planning()  # gesorteerd op startdatum (dus per week), dan vaknummer
        if not planning_rijen:
            st.info("Nog geen concept-planningen.")
        else:
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
                st.caption("Geen concepten in de komende 8 weken; zet 'Alle concepten tonen' aan voor de rest.")
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
                    st.session_state["tl_melding"] = (
                        f"Opgeslagen: {planning_editor.samenvatting(plan)}."
                        + (f" Gestart: {', '.join(codes)}." if codes else ""))
                    st.session_state["planning_editor_versie"] = versie + 1
                    st.rerun()

    with layout.uitklap(f"Jaarplanning: vakken per week · {TUIN_NAAM}"):
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

    with layout.uitklap(f"Overzicht per plantweek · {TUIN_NAAM}"):
        _planning_per_plantweek()

    with layout.uitklap("Vooruitblik komende 6 weken (beide tuinen)"):
        toon_vooruitblik(vandaag, kop=False)


def _planning_per_plantweek():
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
NIET_WIJZIGEN = "zo laten"


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


def _inv_stek(balk):
    """
    Registreren → Stek (vroeger het tabblad Stek): per pootweek het geleverde stek per vak, en het weekrapport
    voor de stekleverancier. De pootweek-kiezer komt in de filterbalk van Registreren (`balk`).
    """
    stekweken = get_stekweken()
    if not stekweken:
        st.info("Er zijn nog geen vakken gestart.")
    else:
        vandaag_stek = date.today()
        deze_maandag = vandaag_stek - timedelta(days=vandaag_stek.weekday())
        # Standaard de huidige week; is daar nog niets gepoot, dan de laatste week waarin wel.
        standaard_stekweek = next((m for m in stekweken if m <= deze_maandag), stekweken[-1])  # stekweken: nieuw → oud

        def _stekweek_label(maandag):
            jaar_s, week_s = get_isojaar_week(maandag)
            return f"Pootweek {week_s} '{str(jaar_s)[2:]} · {format_datum(maandag)} t/m {format_datum(maandag + timedelta(days=6))}"

        stek_maandag = filters.bladeraar(
            f"stek_week_t{TUIN_NUMMER}", sorted(stekweken), standaard_stekweek, format_func=_stekweek_label,
            huidig=deze_maandag if deze_maandag in stekweken else None, plek=balk,
            naam="pootweek", breedte=330, spring_label="Spring naar pootweek")
        stek_jaar, stek_week = get_isojaar_week(stek_maandag)
        rijen_stek = get_stek_voor_week(stek_maandag)
        # Het stek van een week komt uit dezelfde partij, dus de beoordeling is
        # meestal voor alle vakken gelijk: hier één keer invullen, daarna in de
        # tabel per vak aanpassen als een vak afwijkt.
        def _gedeeld(veld):
            """De waarde als alle ingevulde vakken het erover eens zijn, anders None."""
            waarden = {r[veld] for r in rijen_stek if r[veld] not in (None, "")}
            return waarden.pop() if len(waarden) == 1 else None

        layout.sectie("Hele week invullen")
        # Alle velden op één regel, elk zo breed als nodig; op een smal scherm lopen ze door.
        rij = st.container(horizontal=True, vertical_alignment="bottom", gap="small", key="stek_week_rij")
        totaal_bakjes = rij.number_input(
            "Totaal bakjes", min_value=0.0, step=0.25, format="%.2f", width=110,
            value=float(sum(r["bakjes"] or 0 for r in rijen_stek)),
            help="Totaal geleverde bakjes. Wordt verdeeld naar rato van het aantal te poten planten, zodat een "
                 "half vak de helft krijgt. Afronding op kwart bakjes; de som klopt precies.",
            key=f"stek_totaal_{stek_maandag}",
        )

        def _keuze(veld, label, opties, breedte):
            huidig = _gedeeld(veld)
            keuzes = [NIET_WIJZIGEN] + list(opties)
            return rij.selectbox(
                label, keuzes, width=breedte,
                index=keuzes.index(huidig) if huidig in keuzes else 0,
                key=f"stek_week_{veld}_{stek_maandag}",
            )

        week_wortel = _keuze("wortel", "Wortel", STEK_KEUZES["wortel"], 115)
        week_plantmaat = _keuze("plantmaat", "Plantmaat", STEK_KEUZES["plantmaat"], 115)
        week_uniformiteit = _keuze("uniformiteit", "Uniformiteit", STEK_KEUZES["uniformiteit"], 115)
        week_cijfer = _keuze("beoordeling", "Cijfer", range(1, 11), 100)
        week_opmerking = rij.text_input(
            "Opmerking", value=_gedeeld("opmerking") or "", width=170,
            key=f"stek_week_opmerking_{stek_maandag}",
        )
        if rij.button("📋 Invullen", key=f"stek_week_vullen_{stek_maandag}",
                      disabled=not rijen_stek,
                      help=f"Vult alle {len(rijen_stek)} vakken in één keer; '{NIET_WIJZIGEN}' laat staan wat "
                           "er per vak staat."):
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

        layout.sectie("Stek per vak")
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
        with layout.uitklap(f"Weekrapport voor de stekleverancier (week {stek_week})"):
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

        with layout.uitklap("Ontvangers van de mail"):
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

        # Export: tabel kopiëren (voor in de mail), mail opstellen, Excel.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            with st.container(width=190):
                kopieerknop(mailhtml_stek, "📋 Kopieer de tabel")
            st.link_button(
                "✉️ Mail opstellen",
                f"mailto:{urllib.parse.quote(leverancier_email)}"
                f"?cc={urllib.parse.quote(leverancier_cc)}"
                f"&subject={urllib.parse.quote(onderwerp_stek)}",
            )
            layout.export(excel_buffer.getvalue(), f"Stekresultaten week {stek_week:02d}-{stek_jaar}.xlsx",
                          sleutel="stek_download")
        uitleg_help.voetnoot(f"Onderwerp: {onderwerp_stek} · totaal geplant {_stek_getal(totaal_geplant)}"
                             + (" · let op: ook wat nog niet is opgeslagen" if niet_opgeslagen else ""))


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
                "klimaat, watergift en EC/pH van de gift. Historische CSV-data blijft staan."
            )
            if st.button("📡 Haal laatste dagen op uit Priva"):
                try:
                    aantal_k, _ = importeer_klimaat_uit_priva(
                        gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID)
                    aantal_w, _, aantal_ec = importeer_watergift_uit_priva(
                        gebruiker=huidige_gebruiker(), tuin_id=TUIN_ID)
                    st.success(f"✅ {aantal_k} afdeling-dagen klimaat, {aantal_w} vak-dagen watergift en "
                               f"{aantal_ec} dagen EC/pH opgehaald.")
                except Exception as e:
                    st.error(f"❌ Kon niet uit Priva ophalen: {e}")

            water_dekking = get_watergift_dekking()
            if water_dekking:
                laatste_water = max(r[2] for r in water_dekking)
                st.caption(f"Watergift: {len(water_dekking)} vakken, tot {format_datum(laatste_water)}.")
            ec_dekking = get_water_kwaliteit_dekking(TUIN_ID)
            if ec_dekking:
                st.caption("EC/pH: " + "; ".join(
                    f"watersysteem {systeem} {format_datum(eerste)} t/m {format_datum(laatste)} ({aantal} dagen"
                    + (f", {ontbreekt} ontbrekend" if ontbreekt else "") + ")"
                    for systeem, eerste, laatste, aantal, ontbreekt in ec_dekking))
            else:
                st.caption("EC/pH: nog niets opgehaald. Priva bewaart 5 dagen; eerdere EC/pH is niet op te halen.")

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
    balk = layout.filterbalk("logboek")
    limiet_log = filters.weergave("Regels", (100, 300, 1000, 2000), "log_limiet", 300, plek=balk)
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

        gekozen_gebruikers = filters.keuzes("Gebruiker", sorted(df_log["Gebruiker"].unique()), "log_gebruiker",
                                            plek=balk)
        gekozen_types = filters.keuzes("Type", sorted(df_log["Type"].unique()), "log_type", plek=balk)
        zoek = filters.zoekveld("log_zoek", "Woord uit de omschrijving", plek=balk)

        if gekozen_gebruikers:
            df_log = df_log[df_log["Gebruiker"].isin(gekozen_gebruikers)]
        if gekozen_types:
            df_log = df_log[df_log["Type"].isin(gekozen_types)]
        if zoek:
            df_log = df_log[df_log["Omschrijving"].fillna("").str.contains(zoek, case=False, regex=False)]

        uitleg_help.voetnoot(f"{len(df_log)} regels · nieuwste bovenaan")
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

# --- RUWE DATA (onder Meer) ---
RD_LENGTES = ("Week", "Maand", "Kwartaal", "Jaar", "Alles")
_RD_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RD_TIJD = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _rd_frame(kolommen, rijen):
    """
    De rijen als DataFrame met datums als datum (dd-mm-yy in beeld) en tijden in Nederlandse tijd;
    plus de column_config voor st.dataframe.
    """
    df = pd.DataFrame(rijen, columns=kolommen)
    config = {}
    for k in df.columns:
        waarden = df[k].dropna()
        if waarden.empty:
            continue
        eerste = waarden.iloc[0]
        if (isinstance(eerste, str) and all(_RD_DATUM.match(w) for w in waarden.astype(str))) or (
                isinstance(eerste, date) and not isinstance(eerste, datetime)):
            df[k] = pd.to_datetime(df[k])          # NaT blijft leeg in beeld
            config[k] = st.column_config.DateColumn(k, format="DD-MM-YY")
        elif isinstance(eerste, datetime) or (isinstance(eerste, str) and all(_RD_TIJD.match(w) for w in waarden.astype(str))):
            tijden = pd.to_datetime(df[k], utc=True)
            df[k] = tijden.dt.tz_convert("Europe/Amsterdam").dt.tz_localize(None)
            config[k] = st.column_config.DatetimeColumn(k, format="DD-MM-YY HH:mm")
    # Lege tekstcellen leeg tonen i.p.v. "None".
    for k in df.columns:
        if df[k].dtype == object:
            df[k] = df[k].where(df[k].notna(), "")
    return df, config


def _pagina_ruwe_data():
    """De onderliggende tabellen, alleen lezen, met dezelfde filters als de rest van de app."""
    vandaag = date.today()
    balk = layout.filterbalk("ruwe_data")
    t = ruwe_data.tabel(filters.keuze("Tabel", [t.naam for t in ruwe_data.TABELLEN], "rd_tabel",
                                      "Vakken (teelten)", plek=balk))
    van = tot = None
    if t.datum:
        # Van de oudste historie tot een jaar vooruit (planning).
        eerste, laatste = date(vandaag.year - 4, 1, 1), vandaag + timedelta(days=366)
        lengte, periode = filters.periode(
            "rd_periode", RD_LENGTES, "Alles",
            opties_van=lambda n: [] if n == "Alles" else perioden.reeks(eerste, laatste, n),
            standaard_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(vandaag, n)[0],
            format_van=lambda n: lambda k: perioden.periode_label(k, n),
            huidig_van=lambda n: None if n == "Alles" else perioden.periode_sleutel(vandaag, n)[0], plek=balk)
        if periode:
            van, tot = perioden.periode_grenzen(periode, lengte)
    vakken = (filters.keuzes("Vak", get_vaknummers() or [], f"rd_vak_t{TUIN_NUMMER}", plek=balk,
                             placeholder="Alle vakken") if t.vak else [])
    zoek = filters.zoekveld("rd_zoek", "Woord, code of getal", plek=balk)

    kolommen, rijen = lees_ruwe_tabel(*ruwe_data.query(t, TUIN_ID, van, tot, vakken))
    rijen = ruwe_data.zoek([dict(zip(kolommen, r)) for r in rijen], zoek)
    df, config = _rd_frame(kolommen, [list(r.values()) for r in rijen])
    if df.empty:
        st.caption("Geen rijen die aan de filters voldoen.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=config, height=560)
    uitleg_help.voetnoot(f"{len(df)} rijen · {TUIN_NAAM} · {t.uitleg}")
    bestand = f"{t.naam.split(' (')[0].lower().replace(' ', '_').replace('/', '-')}_{TUIN_NAAM.replace(' ', '').lower()}"
    with st.container(horizontal=True, gap="small"):
        layout.export(excel_bestand({t.naam: df}), f"{bestand}.xlsx", sleutel="rd_excel")
        layout.export(df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), f"{bestand}.csv", "CSV",
                      sleutel="rd_csv", mime="text/csv")


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
    uitleg_help.voetnoot("Fout = werkelijk − voorspeld, in dagen (positief = later geoogst dan voorspeld); "
                         "MAE = gemiddelde fout zonder teken.")
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
        layout.sectie(titel)
        kwaliteit = prognoselog.kwaliteit(rijen, veld)
        for kolom, tuin in zip(st.columns(len(tuinen)), tuinen):
            with kolom:
                st.caption(tuin["naam"])
                _pk_tabel(kwaliteit, tuin["id"])

    layout.sectie("Fout naar dagen vóór de oogst")
    per_dag = pd.DataFrame(prognoselog.fout_per_dag(log, oogsten))
    if not per_dag.empty:
        per_dag = per_dag[per_dag["tuin_id"].isin([t["id"] for t in tuinen])]
        per_dag["Tuin"] = per_dag["tuin_id"].map(_tuinnaam_van)
        per_dag = (per_dag.groupby(["Tuin", "dagen_voor_oogst"])["fout"]
                   .agg(fout="mean", mae=lambda x: x.abs().mean()).reset_index())
    basis = alt.Chart(per_dag).encode(
        x=alt.X("dagen_voor_oogst:Q", title="Dagen vóór de oogst", scale=alt.Scale(reverse=True)),
        color=alt.Color("Tuin:N", legend=alt.Legend(title=None, orient="bottom")))
    grafiek = (basis.mark_line().encode(
                   y=alt.Y("fout:Q", title="Gem. fout (d)"),
                   tooltip=[alt.Tooltip("Tuin:N"), alt.Tooltip("dagen_voor_oogst:Q", title="Dagen vóór oogst"),
                            alt.Tooltip("fout:Q", title="Gem. fout (d)", format=".1f"),
                            alt.Tooltip("mae:Q", title="MAE (d)", format=".1f")])
               + alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[3, 3], color="#8a8a80").encode(y="y:Q"))
    toon_grafiek(grafiek, per_dag, "Nog geen logregels van geoogste vakken.")

    layout.sectie("Grootste missers")
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
    uitleg_help.voetnoot("Klik op een regel voor het vak.")
    gekozen = keuze.selection.rows if keuze else []
    if gekozen and gekozen != st.session_state.get("pk_missers_open"):
        st.session_state["pk_missers_open"] = gekozen
        vak_venster(missers[gekozen[0]]["teelt_id"], vandaag)
    elif not gekozen:
        st.session_state["pk_missers_open"] = None


# --- NAVIGATIE ---
#
# Losse pagina's (st.navigation): een klik voert alleen de code van die pagina
# uit, niet die van alle tabbladen. Elke pagina heeft een eigen adres
# (bijv. /stek) voor links en bladwijzers; de app opent op Overzicht.

def pagina_registreren():
    _pagina_registreren()


def pagina_overzicht():
    _pagina_overzicht()


def pagina_teelt():
    _pagina_teelt()


def pagina_tuinvergelijking():
    _pagina_tuin()


def pagina_opmerkingen():
    _pagina_opmerkingen_1()



def pagina_meer():
    """Weinig gebruikt: import, prognosekwaliteit en logboek als subtabbladen."""
    layout.pagina_kop(
        "Meer",
        wat="Wat weinig gebruikt wordt: data importeren, de kwaliteit van de oogstprognose, het logboek van "
            "alle wijzigingen en de ruwe data (de onderliggende tabellen). De uitleg van elke pagina staat achter "
            "de knop Uitleg op die pagina.",
        lezen=[
            "**Vak** = één vak in de kas met één teeltronde; elke ronde krijgt een code: jaar + plantweek + tuin + "
            "vak, bijv. 2634301 = 2026, week 34, tuin 3, vak 1. "
            "**Teelt** = alle vakken uit één plantweek. **Florgib** = de lengtemeting halverwege de teelt; die "
            "stuurt de prognose bij.",
            "Datums staan als dd-mm-jj; weken lopen van zondag t/m zaterdag (de plantweek in de code blijft de "
            "ISO-week van de plantdatum). Lijsten lopen van laag naar hoog.",
            "**Tuin** kies je alleen bovenaan. Pagina's die per tuin werken (Registreren, Meer, het "
            "plannen op Overzicht) tonen bij Beide de laatst gekozen tuin.",
            "**Registreren**: *Florgib* (lengte en gram), *Emmers* (100 stelen per emmer; vink Afronden aan bij de "
            "laatste), *Lengte en gewicht* (rijpheid 1 rauw – 4 rijp) en *Opmerking*, voor één of meer vakken; "
            "*Wijzigen* per vak en per onderdeel. Op een telefoon opent de app op Registreren.",
            "**Prognosekwaliteit**: per tuin hoe goed de prognose en de plandatum achteraf klopten; klik op een "
            "misser voor het vak.",
            "**Logboek**: filter op gebruiker, type of een woord; nieuwste bovenaan.",
            "**Ruwe data**: kies een tabel en filter op periode, vak of een woord (zoekt in alle kolommen). Alleen "
            "lezen; aanpassen gaat via Registreren of de pagina's. Export naar Excel of CSV (puntkomma, "
            "decimale komma)."],
        bron="Import: dagexport van de klimaatcomputer en de energie-export uit Priva; de Priva-API wordt elke "
             "ochtend automatisch opgehaald. Prognosekwaliteit: elke dag legt de app per lopend vak de "
             "oogstprognose vast; na de oogst wordt die vergeleken met de dag waarop de helft van de emmers "
             "binnen was (zonder emmers de oogstdatum).",
    )
    # Ingelogd als … en uitloggen (vroeger in de zijbalk).
    gebruiker = st.container(horizontal=True, vertical_alignment="center", gap="small")
    gebruiker.caption(f"👤 Ingelogd als {st.session_state.get('name')}")
    with gebruiker:
        authenticator.logout("Uitloggen", location="main", key="uitloggen_meer")
    tab_import, tab_prognose, tab_log, tab_ruw = st.tabs(
        ["Data importeren", "Prognosekwaliteit", "Logboek", "Ruwe data"])
    with tab_import:
        _pagina_import_1()
    with tab_prognose:
        _pagina_prognosekwaliteit()
    with tab_log:
        _pagina_log_1()
    with tab_ruw:
        _pagina_ruwe_data()


_pagina.run()

# Lokaal meten: maak een leeg bestand .vem_tijd naast app.py; elke run schrijft
# dan zijn duur (en de actieve pagina) in .vem_tijd.log.
_VEM_TIJD = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vem_tijd")
if os.path.exists(_VEM_TIJD):
    with open(_VEM_TIJD + ".log", "a", encoding="utf-8") as _f:
        _f.write(f"{datetime.now():%H:%M:%S} {_pagina.title} {time.perf_counter() - _VEM_T0:.2f}\n")

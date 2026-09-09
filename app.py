import os
import secrets

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, date
from database import (
    init_db,
    start_nieuwe_teelt,
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
    afdeling_van_vaknummer,
    get_klimaatdata_dagen_voor_periode,
    get_klimaatdata_dekking,
    get_klimaat_voor_periode,
    importeer_watergift_uit_priva,
    get_watergift_dekking,
    get_watergift_voor_periode,
    get_watergift_dagen_voor_periode,
    get_teeltduur,
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
    bereken_verwachte_oogstdatum,
    get_lege_vakken_per_week,
    get_strokenplanning,
)

# --- PAGINA-INSTELLINGEN ---
# Moet de eerste Streamlit-aanroep zijn. Bepaalt o.a. de titel van het
# browsertabblad.
st.set_page_config(page_title="VEM teeltregistratie", page_icon="🌱", layout="wide")

# Standaard rendert Streamlit st.metric-waarden in een erg groot lettertype;
# hier wereldwijd verkleind zodat de kopgegevens (bijv. bij Teelt-detail)
# leesbaar blijven zonder de pagina te domineren.
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.25rem; }
[data-testid="stMetricLabel"] { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# Vaste kleur per afdeling, zodat afd. 1 overal dezelfde kleur heeft.
AFDELING_KLEUR = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#eda100"}


def klimaat_grafieken(dagen_records, toon_dagnacht=False, temp_max=30, licht_max=2500):
    """
    Tekent twee grafieken uit dagrecords (dicts met datum, afdeling, temp_24h,
    temp_dag, temp_nacht, rv_24h, rv_dag, rv_nacht, lichtsom):
    1) temperatuur als lijn (linker-as 0..temp_max) gecombineerd met de
       lichtsom per dag als staaf (rechter-as 0..licht_max, gemiddeld over de
       gekozen afdelingen);
    2) relatieve luchtvochtigheid als lijn.
    De assen zijn temporeel, dus altijd chronologisch.
    """
    if not dagen_records:
        st.caption("Geen klimaatdata in deze periode.")
        return

    df = pd.DataFrame(dagen_records)
    df["datum"] = pd.to_datetime(df["datum"])
    df["Afdeling"] = "Afd. " + df["afdeling"].astype(str)
    afdelingen = sorted(df["afdeling"].unique())
    kleur = alt.Color(
        "Afdeling:N",
        scale=alt.Scale(
            domain=[f"Afd. {a}" for a in afdelingen],
            range=[AFDELING_KLEUR.get(a, "#8a8a80") for a in afdelingen],
        ),
        legend=alt.Legend(title=None, orient="top"),
    )
    streepjes = (
        alt.StrokeDash("Deel:N", legend=alt.Legend(title=None, orient="top"))
        if toon_dagnacht else alt.value([1, 0])
    )
    x_as = alt.X("datum:T", title=None)

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

    licht = df.groupby("datum", as_index=False)["lichtsom"].mean().dropna(subset=["lichtsom"])
    licht_laag = alt.Chart(licht).mark_bar(color="#e7c98a", opacity=0.75).encode(
        x=x_as,
        y=alt.Y("lichtsom:Q", title="Lichtsom per dag",
                scale=alt.Scale(domain=[0, licht_max], clamp=True)),
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                 alt.Tooltip("lichtsom:Q", title="lichtsom", format=".0f")],
    )
    temp_laag = alt.Chart(_lang("temp")).mark_line().encode(
        x=x_as,
        y=alt.Y("waarde:Q", title="Temperatuur (°C)",
                scale=alt.Scale(domain=[0, temp_max], clamp=True)),
        color=kleur, strokeDash=streepjes,
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                 "Afdeling:N", "Deel:N", alt.Tooltip("waarde:Q", title="°C", format=".1f")],
    )
    st.caption("Temperatuur (lijn, links) + lichtsom per dag (staaf, gemiddeld over de afdelingen, rechts)")
    st.altair_chart(
        alt.layer(licht_laag, temp_laag).resolve_scale(y="independent"),
        use_container_width=True,
    )

    rv_chart = alt.Chart(_lang("rv")).mark_line().encode(
        x=x_as,
        y=alt.Y("waarde:Q", title="RV (%)"),
        color=kleur, strokeDash=streepjes,
        tooltip=[alt.Tooltip("datum:T", title="datum", format="%d-%m-%y"),
                 "Afdeling:N", "Deel:N", alt.Tooltip("waarde:Q", title="%", format=".0f")],
    )
    st.caption("Relatieve luchtvochtigheid (%)")
    st.altair_chart(rv_chart, use_container_width=True)


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


st.title("🌱 Teeltregistratie & Dashboard")
st.write("Beheer je teeltvakken en volg de groei van start tot oogst.")

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


def huidige_gebruiker():
    """Identificeert de ingelogde gebruiker voor het wijzigingenlog."""
    return st.session_state.get("username") or st.session_state.get("name")


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


PLANTDICHTHEID_OPTIES = [40, 50, 60]  # stelen per m²


def standaard_aantal_stelen(vaknummer):
    """
    Aantal stelen per teeltvak bij 60 stelen per m² — de oorspronkelijke,
    vaste basiswaarden per vak. Dient als basis voor bereken_aantal_stelen()
    bij een andere plantdichtheid (40/50/60 stelen per m²).
    """
    standaardwaarden = {1: 34000, 19: 15436, 20: 15436, 39: 31780}
    if vaknummer in standaardwaarden:
        return standaardwaarden[vaknummer]
    if 2 <= vaknummer <= 38:
        return 32688
    return 0


def bereken_aantal_stelen(vaknummer, stelen_per_m2):
    """
    Vooringevuld aantal stelen voor een vak bij de gekozen plantdichtheid
    (40, 50 of 60 stelen per m²), herschaald vanaf de vaste 60-stelen/m²-
    basiswaarde van dat vak. Wordt bij het aanmaken van een nieuwe teelt als
    beginwaarde gebruikt; je kunt het altijd handmatig overschrijven.
    """
    basis_60 = standaard_aantal_stelen(vaknummer)
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
        st.info("Nog geen oogstmomenten geregistreerd voor deze teelt.")
        return

    totaal_emmers = sum(r[2] for r in registraties)
    totaal_stelen = totaal_emmers * 100
    st.markdown(f"**Totaal tot nu toe:** {totaal_emmers:g} emmers ({totaal_stelen:g} stelen)")

    if teelt_info.get("aantal_planten"):
        uitval_pct = (
            (teelt_info["aantal_planten"] - totaal_stelen) / teelt_info["aantal_planten"] * 100
        )
        st.markdown(f"**Uitval t.o.v. {teelt_info['aantal_planten']} planten:** {uitval_pct:.2f}%")

    st.caption("Pas een oogstmoment aan met 💾, of verwijder het met 🗑️.")
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

# Zijbalk voor invoer
st.sidebar.header("Registratie bijwerken")

# Keuze uit de 3 stappen
actie = st.sidebar.radio("Wat wil je doen?", [
    "1. Nieuwe teelt registreren",
    "2. Florgib lengte registreren",
    "3. Oogst registeren",
    "4. Registratie wijzigen of verwijderen",
])

# --- ACTIE 1: NIEUWE TEELT STARTEN ---
if actie == "1. Nieuwe teelt registreren":
    st.sidebar.subheader("Nieuwe teelt registreren")

    # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
    datum_teelt_start = st.sidebar.date_input(
        "Startdatum teelt (planten/potten)", key="start_datum", format="DD-MM-YYYY"
    )
    week_start = get_weeknummer(datum_teelt_start)
    st.sidebar.caption(f"📅 Weeknummer: {week_start}")

    # Vaknummer en plantdichtheid buiten het formulier: zo wordt het aantal
    # stelen meteen vooringevuld zodra je een van beide kiest.
    vaknummer = st.sidebar.number_input(
        "Vaknummer", min_value=1, max_value=39, step=1, value=1, key="start_vaknummer"
    )
    voorgestelde_dichtheid = standaard_dichtheid_voor_plantweek(week_start)
    dichtheid = st.sidebar.radio(
        "Plantdichtheid (stelen per m²)", PLANTDICHTHEID_OPTIES,
        index=PLANTDICHTHEID_OPTIES.index(voorgestelde_dichtheid),
        key=f"start_dichtheid_{week_start}", horizontal=True,
        help=f"Voorgesteld op basis van plantweek {week_start}: {voorgestelde_dichtheid} stelen/m². Pas gerust aan.",
    )
    standaard_stelen = bereken_aantal_stelen(int(vaknummer), dichtheid)

    with st.sidebar.form("start_form"):
        aantal_planten = st.number_input(
            "Aantal geplante planten",
            min_value=0, step=1, value=standaard_stelen,
            key=f"start_aantal_{int(vaknummer)}_{dichtheid}",
            help=f"Vooringevuld op basis van het vaknummer bij {dichtheid} stelen per m²; pas aan indien nodig.",
        )

        submit_start = st.form_submit_button("Teelt aanmaken")

        if submit_start:
            try:
                teelt_id, code = start_nieuwe_teelt(
                    int(vaknummer),
                    datum_teelt_start,
                    aantal_planten if aantal_planten else None,
                    gebruiker=huidige_gebruiker(),
                )
                st.sidebar.success(
                    f"✅ Vak {int(vaknummer)} gestart op {format_datum(datum_teelt_start)} (week {week_start}) "
                    f"- code **{code}** (teelt-ID: {teelt_id})"
                )
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Vak {int(vaknummer)}: {e}")

# --- ACTIE 2: HALVERWEGE VOOR MEERDERE VAKKEN ---
elif actie == "2. Florgib lengte registreren":
    st.sidebar.subheader("Florgib lengte registreren voor meerdere teelten")
    
    lopende = get_lopende_teelten()
    
    if lopende:
        # Maak lookup dict
        keuzes = {label: teelt_id for teelt_id, label in lopende}
        
        # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
        datum_half = st.sidebar.date_input(
            "Datum meting Florgib lengte", key="half_datum", format="DD-MM-YYYY"
        )
        week_half = get_weeknummer(datum_half)
        st.sidebar.caption(f"📅 Weeknummer: {week_half}")

        with st.sidebar.form("half_form"):
            # Multi-select voor meerdere teelten
            geselecteerde_labels = st.multiselect(
                "Kies teelten (je kunt meerdere kiezen)",
                list(keuzes.keys()),
                help="Selecteer één of meer teelten om de halverwege-meting in te voeren"
            )

            lengte_half = st.number_input("Florgib lengte (cm)", min_value=0.0, format="%.1f")
            
            submit_half = st.form_submit_button("Halverwege meting opslaan")
            
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
                    st.sidebar.success(
                        f"Florgib lengte opgeslagen op {format_datum(datum_half)} (week {week_half}):\n"
                        + "\n".join(successen)
                    )
                if fouten:
                    st.sidebar.warning("Enkele updates mislukt:\n" + "\n".join(fouten))
                
                if successen:
                    st.rerun()
            elif submit_half and not geselecteerde_labels:
                st.sidebar.warning("Selecteer alstublieft minstens één teelt.")
    else:
        st.sidebar.info("Er zijn nog geen teeltvakken gestart. Kies eerst optie 1.")

# --- ACTIE 3: UITVAL (EMMERS) + OOGSTGEWICHT EN LENGTE ---
elif actie == "3. Oogst registeren":
    st.sidebar.subheader("Oogst registeren")

    tab_uitval, tab_eind = st.sidebar.tabs(["🪣 Uitval", "📏 Oogstgewicht en lengte"])

    # --- TABBLAD: UITVAL (EMMERS, 100 STELEN PER EMMER) ---
    with tab_uitval:
        lopende_uitval = get_lopende_teelten()

        if lopende_uitval:
            keuzes_uitval = {label: teelt_id for teelt_id, label in lopende_uitval}

            uitval_label = st.selectbox(
                "Kies de teelt",
                list(keuzes_uitval.keys()),
                key="uitval_selectie"
            )
            uitval_id = keuzes_uitval[uitval_label]
            huidige_uitval = get_teelt_by_id(uitval_id)

            st.caption(
                f"Vak {huidige_uitval['vaknummer']} · code {huidige_uitval['code'] or '-'}"
                + (f" · {huidige_uitval['aantal_planten']} planten" if huidige_uitval["aantal_planten"] else "")
            )

            if "emmers_form_versie" not in st.session_state:
                st.session_state["emmers_form_versie"] = 0

            with st.form("emmers_form"):
                datum_emmers = st.date_input(
                    "Datum oogstmoment", key="emmers_datum", format="DD-MM-YYYY"
                )
                st.caption(f"📅 Weeknummer: {get_weeknummer(datum_emmers)}")
                aantal_emmers = st.number_input("Aantal emmers", min_value=0, step=1)
                laatste_emmers = st.checkbox(
                    "Dit waren de laatste emmers van dit vak (teelt afronden)",
                    key=f"emmers_laatste_{st.session_state['emmers_form_versie']}",
                )

                submit_emmers = st.form_submit_button("Oogstmoment registreren")

                if submit_emmers:
                    if aantal_emmers > 0:
                        voeg_oogstregistratie_toe(uitval_id, datum_emmers, aantal_emmers, gebruiker=huidige_gebruiker())
                        if laatste_emmers:
                            markeer_teelt_afgerond(uitval_id, datum_emmers, gebruiker=huidige_gebruiker())
                            st.success(
                                f"✅ {aantal_emmers} emmers geregistreerd op {format_datum(datum_emmers)} "
                                "- teelt is gemarkeerd als afgerond."
                            )
                        else:
                            st.success(
                                f"✅ {aantal_emmers} emmers geregistreerd op {format_datum(datum_emmers)}."
                            )
                        # Nieuwe key voor het vinkje bij de volgende weergave, zodat het
                        # altijd weer uit staat na het opslaan (i.p.v. aan te blijven staan).
                        st.session_state["emmers_form_versie"] += 1
                        st.rerun()
                    else:
                        st.warning("Vul een aantal emmers groter dan 0 in.")

            toon_oogstregistraties_beheer(uitval_id, huidige_uitval)
        else:
            st.info(
                "Er zijn geen lopende teelten. Kies eerst optie 1, of pas het aantal emmers van een "
                "afgeronde teelt aan via optie 4 (Registratie wijzigen of verwijderen)."
            )

    # --- TABBLAD: OOGSTGEWICHT EN LENGTE ---
    with tab_eind:
        # Alleen teelten die nog niet zijn afgerond bij de uitval.
        alle_teelten = get_lopende_teelten()

        if alle_teelten:
            keuzes_eind = {label: teelt_id for teelt_id, label in alle_teelten}

            with st.form("oogst_form"):
                geselecteerde_labels = st.multiselect(
                    "Kies teelten (je kunt meerdere tegelijk selecteren)",
                    list(keuzes_eind.keys()),
                    help="Selecteer één of meer teelten om dezelfde lengte/gewicht/rijpheid in te voeren"
                )

                lengte_eind = st.number_input("Oogstlengte (cm)", min_value=0.0, format="%.1f")
                oogstgewicht = st.number_input("Oogstgewicht (gram)", min_value=0, step=1)
                rijpheid_bereik = st.select_slider(
                    "Rijpheidsstadium (1 = rauw, 4 = rijp)",
                    options=RIJPHEID_OPTIES,
                    value=(1, 4),
                    help="Sleep beide punten naar dezelfde waarde voor één stadium (bijv. '3'), of laat ze uit elkaar staan voor een bereik (bijv. '1-3')"
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
                        st.success("Opgeslagen:\n" + "\n".join(successen))
                    if fouten:
                        st.warning("Enkele updates mislukt:\n" + "\n".join(fouten))
                    if successen:
                        st.rerun()
                elif submit_oogst and not geselecteerde_labels:
                    st.warning("Selecteer alstublieft minstens één teelt.")
        else:
            st.info("Er zijn geen lopende teelten. Afgeronde teelten regel je via het tabblad 🪣 Uitval of optie 4.")

# --- ACTIE 4: WIJZIGEN / VERWIJDEREN ---
elif actie == "4. Registratie wijzigen of verwijderen":
    st.sidebar.subheader("Registratie wijzigen of verwijderen")

    alle_teelten = get_alle_teelten_voor_selectie()

    if alle_teelten:
        keuzes = {label: teelt_id for teelt_id, label in alle_teelten}
        geselecteerd_label = st.sidebar.selectbox(
            "Kies de teelt die je wilt wijzigen of verwijderen",
            list(keuzes.keys()),
            key="wijzig_selectie"
        )
        geselecteerd_id = keuzes[geselecteerd_label]
        huidige = get_teelt_by_id(geselecteerd_id)

        st.sidebar.markdown(f"**Teeltvak:** {huidige['teeltvak_naam']} (vaknummer {huidige['vaknummer']})")
        st.sidebar.markdown(f"**Code:** {huidige['code'] or '-'}")

        # Helper om string-datums om te zetten naar date-objecten voor de widgets
        def naar_date(waarde):
            if waarde:
                return datetime.strptime(waarde, "%Y-%m-%d").date()
            return None

        with st.sidebar.form("wijzig_form"):
            st.write("**Startgegevens**")
            nieuwe_start = st.date_input(
                "Startdatum teelt",
                value=naar_date(huidige["datum_teelt_start"]) or datetime.today().date(),
                format="DD-MM-YYYY"
            )
            st.caption(f"📅 Weeknummer: {get_weeknummer(nieuwe_start)}")

            nieuw_aantal_planten = st.number_input(
                "Aantal geplante planten",
                min_value=0, step=1,
                value=int(huidige["aantal_planten"]) if huidige["aantal_planten"] else 0
            )

            st.write("**Florgib lengte**")
            half_ingevuld = st.checkbox("Florgib lengte bekend", value=huidige["datum_half"] is not None)
            nieuwe_datum_half = st.date_input(
                "Datum Florgib lengte",
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

            st.write("**Oogst**")
            oogst_ingevuld = st.checkbox("Oogst bekend", value=huidige["datum_oogst"] is not None)
            nieuwe_datum_oogst = st.date_input(
                "Datum oogst",
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
                "Oogstgewicht (gram)",
                min_value=0, step=1,
                value=int(round(huidige["oogstgewicht"])) if huidige["oogstgewicht"] else 0,
                disabled=not oogst_ingevuld
            )
            nieuwe_rijpheid_bereik = st.select_slider(
                "Rijpheidsstadium (1 = rauw, 4 = rijp)",
                options=RIJPHEID_OPTIES,
                value=rijpheid_tekst_naar_bereik(huidige["rijpheid"]),
                disabled=not oogst_ingevuld
            )

            opslaan = st.form_submit_button("💾 Wijzigingen opslaan")

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
                    st.sidebar.success(f"✅ '{huidige['teeltvak_naam']}' bijgewerkt!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ Fout: {e}")

        # Oogstregistraties (emmers) staan hier ook, zodat je ze ook voor
        # een afgeronde teelt nog kunt corrigeren.
        st.sidebar.markdown("---")
        st.sidebar.write("**🪣 Oogstregistraties (emmers)**")
        with st.sidebar:
            toon_oogstregistraties_beheer(geselecteerd_id, huidige)

        # Verwijderen staat buiten het formulier, met expliciete bevestiging
        st.sidebar.markdown("---")
        st.sidebar.write("**⚠️ Registratie verwijderen**")
        bevestig_verwijderen = st.sidebar.checkbox(
            f"Ja, ik wil '{geselecteerd_label}' definitief verwijderen",
            key="bevestig_verwijderen"
        )
        if st.sidebar.button("🗑️ Verwijder deze registratie", disabled=not bevestig_verwijderen):
            delete_teelt(geselecteerd_id, gebruiker=huidige_gebruiker())
            st.sidebar.success(f"🗑️ '{geselecteerd_label}' is verwijderd.")
            st.rerun()
    else:
        st.sidebar.info("Er zijn nog geen registraties om te wijzigen.")

# --- HOOFDSCHERM: TABBLADEN ---
tab_overzicht, tab_detail, tab_planning, tab_klimaat, tab_stats, tab_log, tab_help = st.tabs([
    "📊 Overzicht", "🔍 Teelt-detail", "🗓️ Planning", "🌡️ Klimaatdata", "📈 Statistieken", "🧾 Logboek",
    "ℹ️ Hoe dit werkt",
])

kolommen, rijen = get_overzicht_dataframe()

# --- OVERZICHT ---
with tab_overzicht:
    st.subheader("📊 Overzicht Teelten")

    if rijen:
        # Maak een DataFrame van de rijen (zonder de ID-kolom voor display)
        df = pd.DataFrame(rijen, columns=kolommen)

        # Rijen komen al gesorteerd uit de database (op code, laag naar hoog).
        # Lopende teelten + nog te starten altijd zichtbaar; afgeronde teelten
        # in een dichtgeklapte uitklapper zodat de tabel opent op de scheiding
        # tussen de laatste afgeronde en de eerste lopende teelt.
        verborgen = ['ID', '_startdatum_iso']
        mask_afgerond = df['Status'] == 'Afgerond'
        df_ov_actief = df.loc[~mask_afgerond].drop(columns=verborgen)
        df_ov_afgerond = (
            df.loc[mask_afgerond]
            .sort_values('_startdatum_iso', ascending=False)
            .drop(columns=verborgen)
        )

        st.dataframe(df_ov_actief, use_container_width=True, hide_index=True)

        if not df_ov_afgerond.empty:
            with st.expander(f"Toon afgeronde teelten ({len(df_ov_afgerond)}) — nieuwste startdatum eerst"):
                st.dataframe(df_ov_afgerond, use_container_width=True, hide_index=True)

        # Statistieken
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            actieve_teelten = len(df[df['Status'] == 'Lopend'])
            st.metric("Actieve teelten", actieve_teelten)
        with col2:
            nog_te_starten = len(df[df['Status'] == 'Nog te starten'])
            st.metric("Nog te starten", nog_te_starten)
        with col3:
            afgeronde_teelten = len(df[df['Status'] == 'Afgerond'])
            st.metric("Afgeronde teelten", afgeronde_teelten)
        with col4:
            gem_duur = df[df['Teeltduur (dagen)'] != '-']['Teeltduur (dagen)'].astype(float).mean()
            if not pd.isna(gem_duur):
                st.metric("Gem. teeltduur (dagen)", f"{gem_duur:.0f}")
            else:
                st.metric("Gem. teeltduur (dagen)", "-")
    else:
        st.info("Nog geen teelten geregistreerd. Gebruik de zijbalk om te beginnen.")

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
        week_label = st.selectbox("Kies een plantweek", list(keuzes_weken.keys()), key="detail_week_selectie")
        teelten_groep = groepen_detail[keuzes_weken[week_label]]

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
        dagen_lijst, temp_lijst, rv_lijst, straling_lijst, water_lijst = [], [], [], [], []
        for t in teelten_groep:
            if not t["datum_oogst"] and t["datum_teelt_start"] > vandaag_detail:
                continue  # nog niet gestart: geen teeltduur/klimaat "tot nu toe" om te middelen

            eind_t = t["datum_oogst"] or vandaag_detail
            dagen_t = get_teeltduur(t["datum_teelt_start"], eind_t)
            if dagen_t is not None:
                dagen_lijst.append(dagen_t)

            afdeling_t = afdeling_van_vaknummer(t["vaknummer"])
            if afdeling_t:
                klimaat_t = get_klimaat_voor_periode(afdeling_t, t["datum_teelt_start"], eind_t)
                if klimaat_t:
                    if klimaat_t["gem_temperatuur"] is not None:
                        temp_lijst.append(klimaat_t["gem_temperatuur"])
                    if klimaat_t["gem_rv"] is not None:
                        rv_lijst.append(klimaat_t["gem_rv"])
                    if klimaat_t["gem_stralingssom_dag"] is not None:
                        straling_lijst.append(klimaat_t["gem_stralingssom_dag"])

            if t["vaknummer"]:
                water_t = get_watergift_voor_periode(t["vaknummer"], t["datum_teelt_start"], eind_t)
                if water_t:
                    water_lijst.append(water_t["totaal_liter_per_m2"])

        if dagen_lijst:
            gem_dagen = sum(dagen_lijst) / len(dagen_lijst)
            gem_weken = round(gem_dagen / 7 * 2) / 2
            teeltduur_tekst = f"{gem_weken:g} weken ({gem_dagen:.0f} dagen)"
        else:
            teeltduur_tekst = "-"

        rij_data = st.columns(4)
        rij_data[0].metric("Eerste startdatum", format_datum(start_datums[0]))
        rij_data[1].metric("Laatste startdatum", format_datum(start_datums[-1]))
        rij_data[2].metric("Gem. teeltduur", teeltduur_tekst)
        rij_data[3].metric("Status", status_tekst)

        rij_klimaat = st.columns(4)
        rij_klimaat[0].metric(
            "Gem. temperatuur", f"{sum(temp_lijst) / len(temp_lijst):.1f} °C" if temp_lijst else "-"
        )
        rij_klimaat[1].metric(
            "Gem. RV", f"{sum(rv_lijst) / len(rv_lijst):.0f} %" if rv_lijst else "-"
        )
        rij_klimaat[2].metric(
            "Gem. lichtsom (per dag)", f"{sum(straling_lijst) / len(straling_lijst):.0f}" if straling_lijst else "-"
        )
        rij_klimaat[3].metric(
            "Gem. water per vak", f"{sum(water_lijst) / len(water_lijst):.0f} l/m²" if water_lijst else "-"
        )

        if aantal_afgerond > 0:
            afgeronde_groep = [t for t in teelten_groep if t["datum_oogst"]]
            lengtes = [t["lengte_eind"] for t in afgeronde_groep if t["lengte_eind"]]
            gewichten = [t["oogstgewicht"] for t in afgeronde_groep if t["oogstgewicht"]]

            uitval_lijst = []
            for t in afgeronde_groep:
                if t["aantal_planten"]:
                    registraties_t = get_oogstregistraties_voor_teelt(t["id"])
                    totaal_stelen_t = sum(r[2] for r in registraties_t) * 100 if registraties_t else 0
                    uitval_lijst.append((t["aantal_planten"] - totaal_stelen_t) / t["aantal_planten"] * 100)

            rij_oogst = st.columns(3)
            rij_oogst[0].metric(
                "Gem. taklengte", f"{sum(lengtes) / len(lengtes):.1f} cm" if lengtes else "-"
            )
            rij_oogst[1].metric(
                "Gem. takgewicht", f"{round(sum(gewichten) / len(gewichten))} gram" if gewichten else "-"
            )
            rij_oogst[2].metric(
                "Gem. uitval", f"{sum(uitval_lijst) / len(uitval_lijst):.1f} %" if uitval_lijst else "-"
            )

        st.markdown("---")

        st.write("**Lengtegroei (gemiddeld over de plantweek)**")
        halve_lengtes = [t["lengte_half"] for t in teelten_groep if t["lengte_half"]]
        eind_lengtes = [t["lengte_eind"] for t in teelten_groep if t["lengte_eind"]]
        groei_data = {}
        if halve_lengtes:
            groei_data["Florgib (halverwege)"] = sum(halve_lengtes) / len(halve_lengtes)
        if eind_lengtes:
            groei_data["Eindlengte (oogst)"] = sum(eind_lengtes) / len(eind_lengtes)
        if groei_data:
            st.bar_chart(pd.Series(groei_data, name="Lengte (cm)"))
        else:
            st.caption("Nog geen lengtemetingen voor deze plantweek.")

        st.write("**Oogst per moment (emmers, opgeteld over de plantweek)**")
        alle_registraties = []
        for t in teelten_groep:
            alle_registraties.extend(get_oogstregistraties_voor_teelt(t["id"]))
        if alle_registraties:
            df_oogst = pd.DataFrame(alle_registraties, columns=["id", "datum", "emmers"])
            df_oogst_som = df_oogst.groupby("datum", as_index=False)["emmers"].sum()
            df_oogst_som["datum"] = pd.to_datetime(df_oogst_som["datum"])
            df_oogst_som = df_oogst_som.set_index("datum").sort_index()
            st.bar_chart(df_oogst_som["emmers"])
            st.line_chart(df_oogst_som["emmers"].cumsum().rename("Cumulatief aantal emmers"))
        else:
            st.caption("Nog geen oogstmomenten geregistreerd voor deze plantweek.")

        st.write("**Klimaat tijdens deze plantweek**")
        afdelingen_groep = sorted({
            afdeling_van_vaknummer(t["vaknummer"]) for t in teelten_groep
            if afdeling_van_vaknummer(t["vaknummer"])
        })
        if afdelingen_groep:
            eind_groep = max(t["datum_oogst"] or vandaag_detail for t in teelten_groep)
            records_temp, records_rv, records_straling = [], [], []
            for afdeling in afdelingen_groep:
                dagen = get_klimaatdata_dagen_voor_periode(afdeling, start_datums[0], eind_groep)
                for datum, temp, rv, straling, temp_dag, temp_nacht, rv_dag, rv_nacht in dagen:
                    kolom = f"Afd. {afdeling}"
                    records_temp.append({
                        "datum": datum,
                        f"{kolom} 24h": temp, f"{kolom} dag": temp_dag, f"{kolom} nacht": temp_nacht,
                    })
                    records_rv.append({
                        "datum": datum,
                        f"{kolom} 24h": rv, f"{kolom} dag": rv_dag, f"{kolom} nacht": rv_nacht,
                    })
                    records_straling.append({"datum": datum, kolom: straling})

            def _pivot_klimaat(records):
                if not records:
                    return None
                df = pd.DataFrame(records).groupby("datum", as_index=True).first().sort_index()
                if df.dropna(how="all").empty:
                    return None
                df.index = pd.to_datetime(df.index)
                return df

            df_temp = _pivot_klimaat(records_temp)
            df_rv = _pivot_klimaat(records_rv)
            df_straling = _pivot_klimaat(records_straling)

            if df_temp is not None:
                st.caption("Temperatuur: 24-uurs, dag- en nachtgemiddelde (°C)")
                st.line_chart(df_temp)
                st.caption("RV: 24-uurs, dag- en nachtgemiddelde (%)")
                st.line_chart(df_rv)
                st.caption("Lichtsom (per dag)")
                st.line_chart(df_straling)
            else:
                st.caption("Nog geen klimaatdata gekoppeld aan deze plantweek.")
        else:
            st.caption("Onbekend vaknummer; kan geen afdeling/klimaatdata bepalen.")

        st.write("**Watergift tijdens deze plantweek**")
        eind_water = max(t["datum_oogst"] or vandaag_detail for t in teelten_groep)
        records_water = []
        for vak in vakken_groep:
            for datum, liter in get_watergift_dagen_voor_periode(vak, start_datums[0], eind_water):
                records_water.append({"datum": datum, f"Vak {vak}": liter})
        if records_water:
            df_water = pd.DataFrame(records_water).groupby("datum", as_index=True).first().sort_index()
            df_water.index = pd.to_datetime(df_water.index)
            st.caption("Watergift per vak (l/m² per dag)")
            st.bar_chart(df_water)
        else:
            st.caption("Nog geen watergift gekoppeld aan deze plantweek.")
    else:
        st.info("Nog geen teelten geregistreerd.")

# --- PLANNING (TOEKOMSTIGE TEELTEN) ---
with tab_planning:
    st.subheader("🗓️ Planning")
    st.caption(
        "Concept-planning voor toekomstige teelten: plant vooruit vanaf waar de huidige teelt van "
        "elk vak en de bestaande concept-planning gebleven zijn. Vak 19+20 worden als één eenheid "
        "gepland, vak 1 is een uitzondering op de vaste onderlinge volgorde, en het aantal vakken "
        "per week verschilt nooit meer dan 1 met de vorige/volgende week. Binnen een week worden de "
        "vakken over maandag t/m donderdag verdeeld (laagste vaknummer op maandag). Een vak wordt "
        "nooit eerder gepland dan de (verwachte) oogst van de lopende teelt in dat vak."
    )

    # --- Strokenplanning (Gantt): vakken verticaal, weken horizontaal ---
    stroken = get_strokenplanning(weken_terug=8)
    if stroken:
        df_stroken = pd.DataFrame(stroken)
        df_stroken["start"] = pd.to_datetime(df_stroken["start"])
        df_stroken["eind"] = pd.to_datetime(df_stroken["eind"])
        df_stroken["water_tekst"] = df_stroken["water_l_m2"].apply(
            lambda x: f"{x:.0f} l/m²" if pd.notna(x) else "–"
        )

        kleur = alt.Color(
            "status:N",
            scale=alt.Scale(
                domain=["afgerond", "lopend", "concept"],
                range=["#b8b8b3", "#1baf7a", "#2a78d6"],
            ),
            legend=alt.Legend(title=None, orient="top"),
        )
        balken = (
            alt.Chart(df_stroken)
            .mark_bar(height=13, cornerRadius=3, stroke="white", strokeWidth=1)
            .encode(
                y=alt.Y(
                    "vaknummer:O", title="Vak", sort="ascending",
                    scale=alt.Scale(domain=list(range(1, 40))),
                ),
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
                    alt.Tooltip("start:T", title="Start", format="%d-%m-%y"),
                    alt.Tooltip("eind:T", title="Oogst", format="%d-%m-%y"),
                    alt.Tooltip("water_tekst:N", title="Water tot nu toe"),
                ],
            )
        )
        vandaag_lijn = (
            alt.Chart(pd.DataFrame({"d": [pd.Timestamp(date.today())]}))
            .mark_rule(color="#e34948", strokeDash=[4, 3])
            .encode(x="d:T")
        )
        st.altair_chart(
            (balken + vandaag_lijn).properties(height=640).configure_view(strokeOpacity=0),
            use_container_width=True,
        )
        st.caption(
            "Strokenplanning: grijs = afgerond, groen = lopende teelt, blauw = concept-planning. "
            "Getal op de as = ISO-weeknummer; rode stippellijn = vandaag. Oogstdatum van lopende "
            "teelten en concepten is de verwachte datum uit de teeltduur-tabel. Beweeg over een "
            "balk voor de watergift (l/m²) tot nu toe."
        )
        st.markdown("---")

    st.write("**X weken vooruit plannen**")
    col_weken, col_knop = st.columns([1, 2])
    aantal_weken_vooruit = col_weken.number_input(
        "Aantal weken vooruit", min_value=1, max_value=52, value=8, step=1, key="plan_weken_vooruit"
    )
    with col_knop:
        st.write("")
        if st.button("📅 Plan vooruit", key="plan_x_weken"):
            resultaten = plan_x_weken_vooruit(int(aantal_weken_vooruit), gebruiker=huidige_gebruiker())
            gepland = [r for r in resultaten if r[1] == "gepland"]
            buiten_horizon = [r for r in resultaten if r[1] == "buiten_horizon"]
            geen_geschiedenis = [r for r in resultaten if r[1] == "geen_geschiedenis"]

            if gepland:
                st.success(
                    f"✅ {len(gepland)} vakken gepland: "
                    + ", ".join(f"vak {v} ({format_datum(d)})" for v, _, d in gepland)
                )
            else:
                st.info("Geen nieuwe vakken gepland binnen deze horizon.")
            if buiten_horizon:
                st.info(
                    f"ℹ️ {len(buiten_horizon)} vakken vallen buiten deze horizon — druk nogmaals op de "
                    "knop (evt. met meer weken) om verder te plannen: "
                    + ", ".join(str(v) for v, _, _ in buiten_horizon)
                )
            if geen_geschiedenis:
                st.warning(
                    f"⚠️ {len(geen_geschiedenis)} vakken hebben nog geen teeltgeschiedenis, dus geen "
                    "voorstel: " + ", ".join(str(v) for v, _, _ in geen_geschiedenis)
                )
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
        st.dataframe(df_planning_week, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen concept-planningen om per week te tonen.")

    st.markdown("---")
    st.write("**Lege vakken per week**")
    st.caption(
        "Hoeveel vakken op dit moment geen werkelijke (lopende) teelt hebben, per week — dus hoeveel "
        "grond er leeg ligt. Kijkt alleen naar echte teelten, niet naar concept-planningen."
    )
    lege_vakken_per_week = get_lege_vakken_per_week(12)
    df_leeg = pd.DataFrame(
        [
            (f"Week {week} - {jaar}", aantal_leeg, ", ".join(str(v) for v in vakken) if vakken else "-")
            for jaar, week, aantal_leeg, vakken in lege_vakken_per_week
        ],
        columns=["Week", "Aantal leeg", "Vakken"]
    )
    st.dataframe(df_leeg, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.write("**Eén vak handmatig plannen**")
    col_plan_vak, col_plan_datum = st.columns(2)
    plan_vaknummer = col_plan_vak.number_input(
        "Vaknummer", min_value=1, max_value=39, step=1, value=1, key="plan_vaknummer"
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
        keuzes_bulk = {
            f"Vak {vaknummer} — week {get_weeknummer(start)} ({format_datum(start)})": planning_id
            for planning_id, vaknummer, start, _duur, _eind, _notitie in planning_rijen
        }
        geselecteerde_bulk = st.multiselect(
            "Selecteer concept-planningen om in één keer te verwijderen",
            list(keuzes_bulk.keys()),
            key="plan_bulk_selectie",
        )
        if st.button(
            f"🗑️ Verwijder {len(geselecteerde_bulk)} geselecteerde concept-planning(en)",
            key="plan_bulk_verwijder",
            disabled=not geselecteerde_bulk,
        ):
            for label in geselecteerde_bulk:
                verwijder_planning(keuzes_bulk[label], gebruiker=huidige_gebruiker())
            st.success(f"🗑️ {len(geselecteerde_bulk)} concept-planning(en) verwijderd.")
            st.rerun()

        st.markdown("---")

        huidige_weeksleutel = None
        for planning_id, vaknummer, start, duur, eind, notitie in planning_rijen:
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
                "Startdatum", value=datetime.strptime(start, "%Y-%m-%d").date(),
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

# --- KLIMAATDATA (KLIMAATCOMPUTER-CSV) ---
with tab_klimaat:
    st.subheader("🌡️ Klimaatdata")

    klimaat_csv = st.file_uploader(
        "Upload de klimaatcomputer-export (.csv)",
        type=["csv"],
        key="klimaat_csv_upload",
        help="Dagexport met kolommen label, pcu, type_1, idx_1, type_2, idx_2, startdate, enddate, value.",
    )

    if klimaat_csv is not None:
        try:
            aantal_verwerkt, aantal_overgeslagen = verwerk_klimaat_csv(klimaat_csv, gebruiker=huidige_gebruiker())
            melding = f"✅ {aantal_verwerkt} afdeling-dagen verwerkt en opgeslagen."
            if aantal_overgeslagen:
                melding += (
                    f" {aantal_overgeslagen} nog niet afgeronde afdeling-dagen zijn overgeslagen "
                    "(einddatum ligt nog niet in het verleden)."
                )
            st.success(melding)
        except Exception as e:
            st.error(f"❌ Kon de CSV niet verwerken: {e}")

    # --- Rechtstreeks ophalen uit de Priva Horti API ---
    if os.environ.get("PRIVA_CLIENT_ID"):
        st.caption(
            "Of haal de laatste afgeronde dagen rechtstreeks uit Priva (tuin 3): klimaat per "
            "afdeling en watergift (l/m²) per vak. Historische CSV-data blijft staan; alleen de "
            "opgehaalde dagen worden bijgewerkt."
        )
        if st.button("📡 Haal laatste dagen op uit Priva"):
            try:
                aantal_k, _ = importeer_klimaat_uit_priva(gebruiker=huidige_gebruiker())
                aantal_w, _ = importeer_watergift_uit_priva(gebruiker=huidige_gebruiker())
                st.success(
                    f"✅ {aantal_k} afdeling-dagen klimaat en {aantal_w} vak-dagen watergift "
                    "opgehaald uit Priva."
                )
            except Exception as e:
                st.error(f"❌ Kon niet uit Priva ophalen: {e}")

        water_dekking = get_watergift_dekking()
        if water_dekking:
            laatste_water = max(r[2] for r in water_dekking)
            st.caption(f"Watergift geregistreerd voor {len(water_dekking)} vakken, tot {format_datum(laatste_water)}.")
    else:
        st.caption("Priva-koppeling niet geconfigureerd (PRIVA_CLIENT_ID ontbreekt).")

    dekking = get_klimaatdata_dekking()

    kolommen_klimaat, rijen_klimaat = get_klimaat_overzicht_dataframe()
    if rijen_klimaat:
        st.write("**Gemiddelden per teelt**")
        df_klimaat = pd.DataFrame(rijen_klimaat, columns=kolommen_klimaat)
        st.dataframe(df_klimaat, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Nog geen gekoppelde klimaatdata. Upload hierboven een CSV-export uit de klimaatcomputer; "
            "de gemiddelde temperatuur, gemiddelde RV en gemiddelde dagstralingssom worden automatisch "
            "gekoppeld aan elke teelt op basis van vaknummer (→ afdeling) en teeltperiode."
        )

    # --- Grafieken: klimaatverloop per afdeling over een vrije periode ---
    if dekking:
        st.markdown("---")
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
        toon_dagnacht = st.checkbox(
            "Toon ook dag- en nachtgemiddelde", value=False, key="klimaat_grafiek_dagnacht"
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
            klimaat_grafieken(records, toon_dagnacht=toon_dagnacht)
        elif datum_van > datum_tot:
            st.warning("'Van' ligt na 'Tot en met'.")

    # --- Geïmporteerd t/m: per afdeling tot welke dag er data is (onderaan) ---
    if dekking:
        st.markdown("---")
        st.write("**Geïmporteerd t/m**")
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
        st.dataframe(pd.DataFrame(dekking_rijen), use_container_width=True, hide_index=True)
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

        # Teelten per vak (op vaknummer-volgorde, laag naar hoog)
        st.write("**Teelten per vak:**")
        per_vak = (
            pd.to_numeric(df_stats['Teeltvak'], errors='coerce').dropna().astype(int)
            .value_counts().reindex(range(1, 40), fill_value=0)
            .rename_axis('Vak').reset_index(name='Aantal teelten')
        )
        st.altair_chart(
            alt.Chart(per_vak).mark_bar().encode(
                x=alt.X('Vak:O', title='Vak'),
                y=alt.Y('Aantal teelten:Q', title='Aantal teelten'),
                tooltip=['Vak:O', 'Aantal teelten:Q'],
            ),
            use_container_width=True,
        )

        # Teeltduur analyse
        df_afgerond = df_stats[df_stats['Oogstdatum'] != '-'].copy()
        if len(df_afgerond) > 0:
            st.write("**Teeltduur analyse (afgeronde teelten):**")
            df_afgerond['Teeltduur (dagen)'] = pd.to_numeric(df_afgerond['Teeltduur (dagen)'], errors='coerce')
            gemiddeld = df_afgerond['Teeltduur (dagen)'].mean()
            minimum = df_afgerond['Teeltduur (dagen)'].min()
            maximum = df_afgerond['Teeltduur (dagen)'].max()

            col1, col2, col3 = st.columns(3)
            col1.metric("Gemiddeld", f"{gemiddeld:.0f} dagen")
            col2.metric("Shortest", f"{minimum:.0f} dagen")
            col3.metric("Longest", f"{maximum:.0f} dagen")
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

        st.dataframe(df_log, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen logregels.")

# --- EXTRA INFO ---
with tab_help:
    st.write("""
    **Stap 1: Nieuwe teelt registreren**
    - Je vult het vaknummer (1-39) in en kiest de plantdichtheid (40, 50 of 60 stelen per m²)
    - Het aantal stelen wordt daarbij automatisch vooringevuld per vak, uitgaande van de vaste
      basiswaarden bij 60 stelen per m² (vak 1 → 34000, vak 2-18 en 21-38 → 32688, vak 19 en 20 →
      15436, vak 39 → 31780) en naar evenredigheid herschaald voor 40 of 50 stelen per m².
      Je kunt de waarde altijd handmatig aanpassen.
    - Er wordt automatisch een unieke code aangemaakt: jaar + plantweek + vaknummer
    - Wil je meerdere vakken op dezelfde dag starten? Vul het formulier gewoon opnieuw in per vak

    **Stap 2: Florgib lengte registreren**
    - Je selecteert één of meer teelten uit het overzicht
    - Je vult de datum en de Florgib lengte in
    - Deze meting wordt voor alle gekozen teelten opgeslagen

    **Stap 3: Oogst registeren**
    - Tabblad 🪣 Uitval: registreer per oogstmoment het aantal emmers (100 stelen per emmer),
      voor lopende teelten. Vink "laatste emmers" aan om de teelt af te ronden.
    - Tabblad 📏 Oogstgewicht en lengte: alleen voor teelten die nog niet zijn afgerond.
      Je vult de oogstlengte, oogstgewicht (in gram) en rijpheidsstadium in.
    - Rijpheid loopt van 1 (rauw) tot 4 (rijp); sleep de slider naar één punt voor een enkel
      stadium (bijv. "3") of laat een bereik staan voor bijv. "1-3" of "2-3"
    - Deze gegevens worden voor alle gekozen teelten opgeslagen
    - Wil je het aantal emmers van een **afgeronde** teelt achteraf corrigeren? Dat doe je bij
      optie 4 (Registratie wijzigen of verwijderen) — daar staat dezelfde emmers-editor (💾/🗑️).

    **Teelt-detail**
    - Kies een teelt in het tabblad 🔍 Teelt-detail voor een grafisch overzicht: lengtegroei,
      oogst per moment (en cumulatief), en het klimaat (temperatuur, RV, stralingssom) tijdens
      de teeltperiode.

    **Planning**
    - Tabblad 🗓️ Planning plant vooruit vanaf waar de huidige teelt van elk vak en de bestaande
      concept-planning gebleven zijn. Kies het aantal weken vooruit en klik op "Plan vooruit";
      vakken die buiten die horizon vallen, plan je met een volgende klik verder in.
    - Vak 19 en 20 worden altijd samen (als één eenheid) gepland; vak 1 is een uitzondering op de
      vaste onderlinge volgorde. Het aantal vakken per week verschilt nooit meer dan 1 met de
      vorige/volgende week, voor een werkbare arbeidsplanning.
    - Een concept-planning is nog geen echte teelt: pas nadat je 'm bevestigt (✅) wordt er een
      teeltregistratie met een eigen code aangemaakt. Met 🗑️ verwijder je een concept weer (los of
      met meerdere tegelijk via de multiselect).

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

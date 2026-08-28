import os
import secrets

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
from datetime import datetime
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
    verwijder_oogstregistratie,
    markeer_teelt_afgerond,
    get_gebruikers_credentials,
)

# --- PAGINA-INSTELLINGEN ---
# Moet de eerste Streamlit-aanroep zijn. Bepaalt o.a. de titel van het
# browsertabblad.
st.set_page_config(page_title="VEM teeltregistratie", page_icon="🌱")


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

    with st.sidebar.form("start_form"):
        vaknummer = st.number_input("Vaknummer", min_value=1, max_value=39, step=1, value=1)
        aantal_planten = st.number_input("Aantal geplante planten", min_value=0, step=1, value=0)

        submit_start = st.form_submit_button("Teelt aanmaken")

        if submit_start:
            try:
                teelt_id, code = start_nieuwe_teelt(
                    int(vaknummer),
                    datum_teelt_start,
                    aantal_planten if aantal_planten else None,
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
                        update_halverwege(geselecteerd_id, datum_half, lengte_half)
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
        lopende_teelten = get_lopende_teelten()

        if lopende_teelten:
            keuzes_uitval = {label: teelt_id for teelt_id, label in lopende_teelten}
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

            with st.form("emmers_form"):
                datum_emmers = st.date_input(
                    "Datum oogstmoment", key="emmers_datum", format="DD-MM-YYYY"
                )
                st.caption(f"📅 Weeknummer: {get_weeknummer(datum_emmers)}")
                aantal_emmers = st.number_input("Aantal emmers", min_value=0, step=1)
                laatste_emmers = st.checkbox("Dit waren de laatste emmers van dit vak (teelt afronden)")

                submit_emmers = st.form_submit_button("Oogstmoment registreren")

                if submit_emmers:
                    if aantal_emmers > 0:
                        voeg_oogstregistratie_toe(uitval_id, datum_emmers, aantal_emmers)
                        if laatste_emmers:
                            markeer_teelt_afgerond(uitval_id, datum_emmers)
                            st.success(
                                f"✅ {aantal_emmers} emmers geregistreerd op {format_datum(datum_emmers)} "
                                "- teelt is gemarkeerd als afgerond."
                            )
                        else:
                            st.success(
                                f"✅ {aantal_emmers} emmers geregistreerd op {format_datum(datum_emmers)}."
                            )
                        st.rerun()
                    else:
                        st.warning("Vul een aantal emmers groter dan 0 in.")

            # Overzicht van reeds geregistreerde oogstmomenten voor deze teelt
            registraties = get_oogstregistraties_voor_teelt(uitval_id)
            if registraties:
                totaal_emmers = sum(r[2] for r in registraties)
                totaal_stelen = totaal_emmers * 100
                st.markdown(f"**Totaal tot nu toe:** {totaal_emmers:g} emmers ({totaal_stelen:g} stelen)")

                if huidige_uitval["aantal_planten"]:
                    uitval_pct = (
                        (huidige_uitval["aantal_planten"] - totaal_stelen) / huidige_uitval["aantal_planten"] * 100
                    )
                    st.markdown(
                        f"**Uitval t.o.v. {huidige_uitval['aantal_planten']} planten:** {uitval_pct:.2f}%"
                    )

                for reg_id, reg_datum, reg_emmers in registraties:
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"{format_datum(reg_datum)}: {reg_emmers:g} emmers")
                    if col_b.button("🗑️", key=f"del_emmer_{reg_id}"):
                        verwijder_oogstregistratie(reg_id)
                        st.rerun()
            else:
                st.info("Nog geen oogstmomenten geregistreerd voor deze teelt.")
        else:
            st.info("Er zijn geen lopende teelten. Kies eerst optie 1.")

    # --- TABBLAD: OOGSTGEWICHT EN LENGTE ---
    with tab_eind:
        alle_teelten = get_alle_teelten_voor_selectie()

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
                            update_oogst(keuzes_eind[label], lengte_eind, oogstgewicht, rijpheid_tekst)
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
            st.info("Er zijn nog geen teeltvakken gestart. Kies eerst optie 1.")

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
                    )
                    st.sidebar.success(f"✅ '{huidige['teeltvak_naam']}' bijgewerkt!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ Fout: {e}")

        # Verwijderen staat buiten het formulier, met expliciete bevestiging
        st.sidebar.markdown("---")
        st.sidebar.write("**⚠️ Registratie verwijderen**")
        bevestig_verwijderen = st.sidebar.checkbox(
            f"Ja, ik wil '{geselecteerd_label}' definitief verwijderen",
            key="bevestig_verwijderen"
        )
        if st.sidebar.button("🗑️ Verwijder deze registratie", disabled=not bevestig_verwijderen):
            delete_teelt(geselecteerd_id)
            st.sidebar.success(f"🗑️ '{geselecteerd_label}' is verwijderd.")
            st.rerun()
    else:
        st.sidebar.info("Er zijn nog geen registraties om te wijzigen.")

# --- OVERZICHT OP HET HOOFDSCHERM ---
st.subheader("📊 Overzicht Teelten")

kolommen, rijen = get_overzicht_dataframe()

if rijen:
    # Maak een DataFrame van de rijen (zonder de ID-kolom voor display)
    df = pd.DataFrame(rijen, columns=kolommen)

    # Rijen komen al gesorteerd uit de database (op code, laag naar hoog)
    st.dataframe(df.drop(columns=['ID']), use_container_width=True)

    # Statistieken
    col1, col2, col3 = st.columns(3)
    with col1:
        actieve_teelten = len(df[df['Oogstdatum'] == '-'])
        st.metric("Actieve teelten", actieve_teelten)
    with col2:
        afgeronde_teelten = len(df[df['Oogstdatum'] != '-'])
        st.metric("Afgeronde teelten", afgeronde_teelten)
    with col3:
        gem_duur = df[df['Teeltduur (dagen)'] != '-']['Teeltduur (dagen)'].astype(float).mean()
        if not pd.isna(gem_duur):
            st.metric("Gem. teeltduur (dagen)", f"{gem_duur:.0f}")
        else:
            st.metric("Gem. teeltduur (dagen)", "-")
else:
    st.info("Nog geen teelten geregistreerd. Gebruik de zijbalk om te beginnen.")

# --- EXTRA INFO ---
with st.expander("ℹ️ Hoe dit werkt"):
    st.write("""
    **Stap 1: Nieuwe teelt registreren**
    - Je vult het vaknummer (1-39) en het aantal geplante planten in
    - Er wordt automatisch een unieke code aangemaakt: jaar + plantweek + vaknummer
    - Wil je meerdere vakken op dezelfde dag starten? Vul het formulier gewoon opnieuw in per vak

    **Stap 2: Florgib lengte registreren**
    - Je selecteert één of meer teelten uit het overzicht
    - Je vult de datum en de Florgib lengte in
    - Deze meting wordt voor alle gekozen teelten opgeslagen

    **Stap 3: Oogst registeren**
    - Je selecteert één of meer teelten
    - Je vult de oogstdatum, oogstlengte, oogstgewicht (in gram) en rijpheidsstadium in
    - Rijpheid loopt van 1 (rauw) tot 4 (rijp); sleep de slider naar één punt voor een enkel
      stadium (bijv. "3") of laat een bereik staan voor bijv. "1-3" of "2-3"
    - Deze gegevens worden voor alle gekozen teelten opgeslagen
    
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

# --- HANDIGE STATISTIEKEN ---
with st.expander("📈 Statistieken & Inzichten"):
    if rijen:
        kolommen_stats, rijen_stats = get_overzicht_dataframe()
        df_stats = pd.DataFrame(rijen_stats, columns=kolommen_stats)
        
        # Teelten per vak
        st.write("**Teelten per vak:**")
        teelten_per_vak = df_stats['Teeltvak'].value_counts()
        st.bar_chart(teelten_per_vak)
        
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

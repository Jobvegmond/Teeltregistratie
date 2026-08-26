import streamlit as st
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
    get_teeltduur,
    get_alle_teelten_voor_selectie,
    get_teelt_by_id,
    update_teelt_volledig,
    delete_teelt,
    voeg_oogstregistratie_toe,
    get_oogstregistraties_voor_teelt,
    verwijder_oogstregistratie,
)

# --- INITIALISATIE ---
init_db()

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

st.title("🌱 Teeltregistratie & Dashboard")
st.write("Beheer je teeltvakken en volg de groei van start tot oogst.")

# Zijbalk voor invoer
st.sidebar.header("Registratie bijwerken")

# Keuze uit de 3 stappen
actie = st.sidebar.radio("Wat wil je doen?", [
    "1. Nieuw teeltvak(ken) starten",
    "2. Lengte halverwege toevoegen",
    "3. Eindstand / Oogst toevoegen",
    "4. Registratie wijzigen / verwijderen",
    "5. Emmers oogst registreren",
])

# --- ACTIE 1: MEERDERE TEELTVAKKEN STARTEN ---
if actie == "1. Nieuw teeltvak(ken) starten":
    st.sidebar.subheader("Start één of meer teeltvakken")

    # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
    datum_teelt_start = st.sidebar.date_input("Startdatum teelt (planten/potten)", key="start_datum")
    week_start = get_weeknummer(datum_teelt_start)
    st.sidebar.caption(f"📅 Weeknummer: {week_start}")

    with st.sidebar.form("start_form"):
        st.caption("Voer per teeltvak het vaknummer (1-39), optioneel een label en het aantal geplante planten in.")
        vakken_df = st.data_editor(
            pd.DataFrame([{"Vaknummer": None, "Label (optioneel)": "", "Aantal Planten": None}]),
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            column_config={
                "Vaknummer": st.column_config.NumberColumn(min_value=1, max_value=39, step=1, required=True),
                "Label (optioneel)": st.column_config.TextColumn(),
                "Aantal Planten": st.column_config.NumberColumn(min_value=0, step=1),
            },
            key="start_editor",
        )

        submit_start = st.form_submit_button("Teeltvak(ken) aanmaken")

        if submit_start:
            successen = []
            fouten = []

            for _, rij in vakken_df.iterrows():
                vaknummer = rij["Vaknummer"]
                if pd.isna(vaknummer):
                    continue
                vaknummer = int(vaknummer)
                naam = rij["Label (optioneel)"].strip() if isinstance(rij["Label (optioneel)"], str) and rij["Label (optioneel)"].strip() else None
                aantal_planten = int(rij["Aantal Planten"]) if not pd.isna(rij["Aantal Planten"]) else None

                try:
                    teelt_id, code = start_nieuwe_teelt(vaknummer, datum_teelt_start, aantal_planten, naam)
                    successen.append(f"✅ Vak {vaknummer} - code **{code}** (teelt-ID: {teelt_id})")
                except Exception as e:
                    fouten.append(f"❌ Vak {vaknummer}: {e}")

            if successen:
                st.sidebar.success(f"Gestart op {datum_teelt_start} (week {week_start}):\n" + "\n".join(successen))
            if fouten:
                st.sidebar.warning("Enkele teeltvakken konden niet worden aangemaakt:\n" + "\n".join(fouten))
            if not successen and not fouten:
                st.sidebar.warning("Voer alstublieft minstens één vaknummer in.")

            if successen:
                st.rerun()

# --- ACTIE 2: HALVERWEGE VOOR MEERDERE VAKKEN ---
elif actie == "2. Lengte halverwege toevoegen":
    st.sidebar.subheader("Halverwege meting voor meerdere teelten")
    
    lopende = get_lopende_teelten()
    
    if lopende:
        # Maak lookup dict
        keuzes = {label: teelt_id for teelt_id, label in lopende}
        
        # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
        datum_half = st.sidebar.date_input("Datum meting halverwege", key="half_datum")
        week_half = get_weeknummer(datum_half)
        st.sidebar.caption(f"📅 Weeknummer: {week_half}")

        with st.sidebar.form("half_form"):
            # Multi-select voor meerdere teelten
            geselecteerde_labels = st.multiselect(
                "Kies teelten (je kunt meerdere kiezen)",
                list(keuzes.keys()),
                help="Selecteer één of meer teelten om de halverwege-meting in te voeren"
            )

            lengte_half = st.number_input("Lengte halverwege (cm)", min_value=0.0, format="%.1f")
            
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
                        f"Halverwege metingen opgeslagen op {datum_half} (week {week_half}):\n"
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

# --- ACTIE 3: OOGST VOOR MEERDERE VAKKEN ---
elif actie == "3. Eindstand / Oogst toevoegen":
    st.sidebar.subheader("Eindstand / Oogst voor meeldere teelten")
    
    lopende = get_lopende_teelten()
    
    if lopende:
        # Maak lookup dict
        keuzes = {label: teelt_id for teelt_id, label in lopende}
        
        # Datum buiten het formulier: zo ververst het weeknummer meteen bij het kiezen
        datum_oogst = st.sidebar.date_input("Datum oogst / eindmeting", key="oogst_datum")
        week_oogst = get_weeknummer(datum_oogst)
        st.sidebar.caption(f"📅 Weeknummer: {week_oogst}")

        with st.sidebar.form("oogst_form"):
            # Multi-select voor meerdere teelten
            geselecteerde_labels = st.multiselect(
                "Kies teelten (je kunt meerdere kiezen)",
                list(keuzes.keys()),
                help="Selecteer één of meer teelten om de oogstgegevens in te voeren"
            )

            lengte_eind = st.number_input("Lengte aan het einde (cm)", min_value=0.0, format="%.1f")
            oogstgewicht = st.number_input("Oogstgewicht per teelt (kg)", min_value=0.0, format="%.1f")
            rijpheid_bereik = st.select_slider(
                "Rijpheidsstadium (1 = rauw, 4 = rijp)",
                options=RIJPHEID_OPTIES,
                value=(1, 4),
                help="Sleep beide punten naar dezelfde waarde voor één stadium (bijv. '3'), of laat ze uit elkaar staan voor een bereik (bijv. '1-3')"
            )

            submit_oogst = st.form_submit_button("Eindstand opslaan")

            if submit_oogst and geselecteerde_labels:
                successen = []
                fouten = []
                rijpheid_tekst = rijpheid_bereik_naar_tekst(rijpheid_bereik)

                for label in geselecteerde_labels:
                    geselecteerd_id = keuzes[label]
                    try:
                        update_oogst(geselecteerd_id, datum_oogst, lengte_eind, oogstgewicht, rijpheid_tekst)
                        successen.append(f"✅ {label}")
                    except Exception as e:
                        fouten.append(f"❌ {label}: {e}")
                
                if successen:
                    st.sidebar.success(
                        f"Eindstanden opgeslagen op {datum_oogst} (week {week_oogst}):\n"
                        + "\n".join(successen)
                    )
                if fouten:
                    st.sidebar.warning("Enkele updates mislukt:\n" + "\n".join(fouten))
                
                if successen:
                    st.rerun()
            elif submit_oogst and not geselecteerde_labels:
                st.sidebar.warning("Selecteer alstublieft minstens één teelt.")
    else:
        st.sidebar.info("Er zijn nog geen teeltvakken gestart. Kies eerst optie 1.")

# --- ACTIE 4: WIJZIGEN / VERWIJDEREN ---
elif actie == "4. Registratie wijzigen / verwijderen":
    st.sidebar.subheader("Bestaande registratie aanpassen")

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
                value=naar_date(huidige["datum_teelt_start"]) or datetime.today().date()
            )
            st.caption(f"📅 Weeknummer: {get_weeknummer(nieuwe_start)}")

            nieuw_aantal_planten = st.number_input(
                "Aantal geplante planten",
                min_value=0, step=1,
                value=int(huidige["aantal_planten"]) if huidige["aantal_planten"] else 0
            )

            st.write("**Halverwege**")
            half_ingevuld = st.checkbox("Halverwege-meting bekend", value=huidige["datum_half"] is not None)
            nieuwe_datum_half = st.date_input(
                "Datum halverwege",
                value=naar_date(huidige["datum_half"]) or datetime.today().date(),
                disabled=not half_ingevuld
            )
            nieuwe_lengte_half = st.number_input(
                "Lengte halverwege (cm)",
                min_value=0.0, format="%.1f",
                value=float(huidige["lengte_half"]) if huidige["lengte_half"] else 0.0,
                disabled=not half_ingevuld
            )

            st.write("**Oogst**")
            oogst_ingevuld = st.checkbox("Oogst bekend", value=huidige["datum_oogst"] is not None)
            nieuwe_datum_oogst = st.date_input(
                "Datum oogst",
                value=naar_date(huidige["datum_oogst"]) or datetime.today().date(),
                disabled=not oogst_ingevuld
            )
            nieuwe_lengte_eind = st.number_input(
                "Lengte einde (cm)",
                min_value=0.0, format="%.1f",
                value=float(huidige["lengte_eind"]) if huidige["lengte_eind"] else 0.0,
                disabled=not oogst_ingevuld
            )
            nieuw_gewicht = st.number_input(
                "Oogstgewicht (kg)",
                min_value=0.0, format="%.1f",
                value=float(huidige["oogstgewicht"]) if huidige["oogstgewicht"] else 0.0,
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

# --- ACTIE 5: EMMERS OOGST REGISTREREN ---
elif actie == "5. Emmers oogst registreren":
    st.sidebar.subheader("Emmers oogst registreren (100 stelen per emmer)")

    alle_teelten = get_alle_teelten_voor_selectie()

    if alle_teelten:
        keuzes = {label: teelt_id for teelt_id, label in alle_teelten}
        geselecteerd_label = st.sidebar.selectbox(
            "Kies de teelt waarvoor je een oogstmoment wilt registreren",
            list(keuzes.keys()),
            key="emmers_selectie"
        )
        geselecteerd_id = keuzes[geselecteerd_label]
        huidige = get_teelt_by_id(geselecteerd_id)

        with st.sidebar.form("emmers_form"):
            datum_emmers = st.date_input("Datum oogstmoment", key="emmers_datum")
            st.caption(f"📅 Weeknummer: {get_weeknummer(datum_emmers)}")
            aantal_emmers = st.number_input("Aantal emmers", min_value=0.0, step=0.5, format="%.1f")

            submit_emmers = st.form_submit_button("Oogstmoment registreren")

            if submit_emmers:
                if aantal_emmers > 0:
                    voeg_oogstregistratie_toe(geselecteerd_id, datum_emmers, aantal_emmers)
                    st.sidebar.success(f"✅ {aantal_emmers} emmers geregistreerd op {datum_emmers}.")
                    st.rerun()
                else:
                    st.sidebar.warning("Vul een aantal emmers groter dan 0 in.")

        # Overzicht van reeds geregistreerde oogstmomenten voor deze teelt
        registraties = get_oogstregistraties_voor_teelt(geselecteerd_id)
        if registraties:
            totaal_emmers = sum(r[2] for r in registraties)
            totaal_stelen = totaal_emmers * 100
            st.sidebar.markdown(f"**Totaal tot nu toe:** {totaal_emmers:g} emmers ({totaal_stelen:g} stelen)")

            if huidige["aantal_planten"]:
                uitval = round((huidige["aantal_planten"] - totaal_stelen) / huidige["aantal_planten"] * 100, 1)
                st.sidebar.markdown(f"**Uitval t.o.v. {huidige['aantal_planten']} planten:** {uitval}%")

            for reg_id, reg_datum, reg_emmers in registraties:
                col_a, col_b = st.sidebar.columns([3, 1])
                col_a.write(f"{reg_datum}: {reg_emmers:g} emmers")
                if col_b.button("🗑️", key=f"del_emmer_{reg_id}"):
                    verwijder_oogstregistratie(reg_id)
                    st.rerun()
        else:
            st.sidebar.info("Nog geen oogstmomenten geregistreerd voor deze teelt.")
    else:
        st.sidebar.info("Er zijn nog geen teeltvakken gestart. Kies eerst optie 1.")

# --- OVERZICHT OP HET HOOFDSCHERM ---
st.subheader("📊 Overzicht Teelten")

kolommen, rijen = get_overzicht_dataframe()

if rijen:
    # Maak een DataFrame van de rijen (zonder de ID-kolom voor display)
    df = pd.DataFrame(rijen, columns=kolommen)
    
    # Sorteer op Teeltvak en start-datum (nieuwste eerst)
    df = df.sort_values(by=["Teeltvak", "Start (week)"], ascending=[True, False])
    
    st.dataframe(df.drop(columns=['ID']), use_container_width=True)
    
    # Statistieken
    col1, col2, col3 = st.columns(3)
    with col1:
        actieve_teelten = len(df[df['Oogst (week)'] == '-'])
        st.metric("Actieve teelten", actieve_teelten)
    with col2:
        afgeronde_teelten = len(df[df['Oogst (week)'] != '-'])
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
    **Stap 1: Meerdere teeltvakken starten**
    - Je voert één of meer teeltvaknamen in (gescheiden door komma's), bijv: "Vak A1, Vak A2, Vak B1"
    - Alle gekozen vakken starten op dezelfde datum
    - Het systeem slaat dit op als aparte teelten per vak
    
    **Stap 2: Halverwege meting**
    - Je selecteert één of meer teelten uit het overzicht
    - Je vult de halverwege-datum en lengte in
    - Deze meting wordt voor alle gekozen teelten opgeslagen
    
    **Stap 3: Eindstand/Oogst**
    - Je selecteert één of meer teelten
    - Je vult de oogstdatum, eindlengte, gewicht en rijpheidsstadium in
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
        df_afgerond = df_stats[df_stats['Oogst (week)'] != '-'].copy()
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

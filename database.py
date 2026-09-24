import os
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import pool as psycopg2_pool


def _laad_dotenv():
    """
    Leest een .env-bestand naast dit script in en zet de waarden in os.environ,
    zodat je DATABASE_URL lokaal niet handmatig hoeft te exporteren. Bestaande
    omgevingsvariabelen worden niet overschreven (die winnen altijd). Geen
    externe dependency nodig.
    """
    env_pad = Path(__file__).with_name(".env")
    if not env_pad.exists():
        return
    for regel in env_pad.read_text(encoding="utf-8").splitlines():
        regel = regel.strip()
        if not regel or regel.startswith("#") or "=" not in regel:
            continue
        sleutel, _, waarde = regel.partition("=")
        sleutel = sleutel.strip()
        waarde = waarde.strip().strip('"').strip("'")
        os.environ.setdefault(sleutel, waarde)


_laad_dotenv()

# De connectiegegevens komen uit de omgevingsvariabele DATABASE_URL, bijvoorbeeld
# de "Connection string" van je Supabase-project:
#   postgresql://postgres:<wachtwoord>@db.<ref>.supabase.co:5432/postgres
# Zet hem NOOIT letterlijk in de code. Lokaal komt hij uit het .env-bestand
# (zie .env.example); op de server komt hij uit een environment variable
# (Render-service VEMteelt, EU-regio).
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_weeknummer(datum):
    """Geeft het weeknummer van een datum terug (ISO-week: 1-53)."""
    if isinstance(datum, str):
        datum = datetime.strptime(datum, "%Y-%m-%d").date()
    return datum.isocalendar()[1]


def get_teeltduur(datum_start, datum_einde):
    """Berekent het aantal dagen tussen twee datums."""
    if isinstance(datum_start, str):
        datum_start = datetime.strptime(datum_start, "%Y-%m-%d").date()
    if isinstance(datum_einde, str):
        datum_einde = datetime.strptime(datum_einde, "%Y-%m-%d").date()

    if datum_einde and datum_start:
        return (datum_einde - datum_start).days
    return None


def format_datum(datum):
    """
    Zet een datum om naar weergaveformaat dd-mm-jj (bijv. '27-08-26').
    Accepteert een date-object of een string in ISO-formaat (zoals opgeslagen
    in de database). Geeft een lege string terug bij een lege waarde.
    """
    if not datum:
        return ""
    if isinstance(datum, str):
        try:
            datum = datetime.strptime(datum, "%Y-%m-%d").date()
        except ValueError:
            return datum
    return datum.strftime("%d-%m-%y")


def genereer_teelt_code(datum_teelt_start, vaknummer):
    """
    Bouwt de unieke teelt-code: laatste 2 cijfers van het jaar + plantweek (2 cijfers)
    + vaknummer (2 cijfers). Bijv. gestart in 2026, week 9, vak 4 -> '260904'.

    Het jaar is het ISO-jaar dat bij de plantweek hoort, niet het kalenderjaar:
    29-12-2025 valt in week 1 van 2026 en krijgt dus '2601..'. Met het
    kalenderjaar stond daar '2501..', een week 1 in een jaar dat toen al bijna
    om was.
    """
    if isinstance(datum_teelt_start, str):
        datum_teelt_start = datetime.strptime(datum_teelt_start, "%Y-%m-%d").date()

    isojaar, plantweek = get_isojaar_week(datum_teelt_start)
    return f"{isojaar % 100:02d}{plantweek:02d}{int(vaknummer):02d}"


# --- VERBINDING (POOL) ---
#
# Eén verbindingenpool per proces, lui aangemaakt. Dit geeft dezelfde
# "één keer opzetten en hergebruiken"-levensduur als @st.cache_resource, maar
# werkt ook in de losse scripts (beheer_gebruikers.py,
# migratie_sqlite_naar_postgres.py) die niet onder Streamlit draaien.
# psycopg2's ThreadedConnectionPool is veilig voor de meerdere threads die
# Streamlit voor verschillende sessies kan gebruiken.

_POOL_MIN = 1
_POOL_MAX = 10
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """Geeft de proces-brede verbindingenpool terug en maakt hem zo nodig aan."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "De omgevingsvariabele DATABASE_URL is niet gezet. Zet hem op de "
                        "PostgreSQL-connectiestring van je Supabase-project."
                    )
                _pool = psycopg2_pool.ThreadedConnectionPool(
                    _POOL_MIN, _POOL_MAX, DATABASE_URL
                )
    return _pool


def _verbinding_werkt(conn):
    """
    Controleert met een lichte query of een geleende verbinding nog leeft.
    Supabase (Supavisor-pooler) sluit inactieve verbindingen na verloop van
    tijd; zonder deze check zou de eerste echte query dan falen.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except psycopg2.Error:
        return False


@contextmanager
def get_connection():
    """
    Leent een databaseverbinding uit de proces-brede pool en geeft hem daarna
    weer terug (dus niet echt afsluiten). Te gebruiken als context manager:

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
            conn.commit()

    Een verbinding die de server intussen heeft gesloten wordt weggegooid en
    vervangen door een nieuwe.
    """
    pool = _get_pool()
    conn = pool.getconn()
    if not _verbinding_werkt(conn):
        pool.putconn(conn, close=True)
        conn = pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except psycopg2.Error:
            pass
        raise
    finally:
        pool.putconn(conn)


def init_db():
    """Maakt de tabellen aan als ze nog niet bestaan."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teeltvakken (
                id SERIAL PRIMARY KEY,
                naam TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teelten (
                id SERIAL PRIMARY KEY,
                teeltvak_id INTEGER NOT NULL,
                datum_teelt_start TEXT NOT NULL,
                datum_half TEXT,
                lengte_half REAL,
                datum_oogst TEXT,
                lengte_eind REAL,
                oogstgewicht REAL,
                rijpheid TEXT,
                FOREIGN KEY (teeltvak_id) REFERENCES teeltvakken (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oogstregistraties (
                id SERIAL PRIMARY KEY,
                teelt_id INTEGER NOT NULL,
                datum TEXT NOT NULL,
                aantal_emmers REAL NOT NULL,
                FOREIGN KEY (teelt_id) REFERENCES teelten (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gebruikers (
                username TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                wachtwoord_hash TEXT NOT NULL,
                email TEXT
            )
        """)

        # Vervangen door klimaatdata_dag (dagniveau i.p.v. weekniveau) — de
        # oude weektabel en alle daarin geuploade data vervallen bewust.
        cursor.execute("DROP TABLE IF EXISTS klimaatdata_week")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS klimaatdata_dag (
                id SERIAL PRIMARY KEY,
                afdeling INTEGER NOT NULL,
                datum TEXT NOT NULL,
                gem_temperatuur REAL,
                gem_rv REAL,
                gem_temperatuur_dag REAL,
                gem_temperatuur_nacht REAL,
                gem_rv_dag REAL,
                gem_rv_nacht REAL,
                stralingssom_dag REAL,
                UNIQUE (afdeling, datum)
            )
        """)
        # Migratie: dag/nacht-kolommen toevoegen aan een reeds aangemaakte klimaatdata_dag.
        cursor.execute("ALTER TABLE klimaatdata_dag ADD COLUMN IF NOT EXISTS gem_temperatuur_dag REAL")
        cursor.execute("ALTER TABLE klimaatdata_dag ADD COLUMN IF NOT EXISTS gem_temperatuur_nacht REAL")
        cursor.execute("ALTER TABLE klimaatdata_dag ADD COLUMN IF NOT EXISTS gem_rv_dag REAL")
        cursor.execute("ALTER TABLE klimaatdata_dag ADD COLUMN IF NOT EXISTS gem_rv_nacht REAL")

        # Watergift per vak per dag (liter/m²), opgehaald uit Priva
        # (KRAAN.VERBRUIKM2). Per vak i.p.v. per afdeling, want de kranen in
        # Priva komen 1-op-1 overeen met onze vaknummers 1-39.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watergift_dag (
                id SERIAL PRIMARY KEY,
                vaknummer INTEGER NOT NULL,
                datum TEXT NOT NULL,
                liter_per_m2 REAL,
                UNIQUE (vaknummer, datum)
            )
        """)

        # Warmteverbruik per dag voor de hele kas (Priva Pulsteller,
        # label Sum_24h_PtEnergyUse), niet per afdeling of vak — er is één
        # warmtemeter voor heel tuin 3. warmte_mj_per_m2 wordt bij het
        # opslaan al berekend (totaal / TUIN3_OPPERVLAKTE_M2) zodat we 'm
        # per vak kunnen uitrekenen op basis van de oppervlakte van dat vak.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS energiedata_dag (
                id SERIAL PRIMARY KEY,
                datum TEXT NOT NULL UNIQUE,
                warmte_mj_totaal REAL,
                warmte_mj_per_m2 REAL
            )
        """)

        # Gasverbruik van de gasketel (bijstook) per dag voor de hele kas, uit
        # dezelfde Rapport Energie-CSV als energiedata_dag: zelfde label
        # (Sum_24h_PtEnergyUse) maar Pulsteller-index 1 in plaats van 2 — dit
        # kanaal heeft een gasmeter als pulsgever en levert dus m3, niet GJ
        # (correctie van Job, sept 2026). Wordt bij het opslaan omgerekend
        # naar MJ (zie GAS_CALORISCHE_WAARDE_MJ_PER_M3) en meegeteld in de
        # warmte per vak en teelt naast energiedata_dag.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gasdata_dag (
                id SERIAL PRIMARY KEY,
                datum TEXT NOT NULL UNIQUE
            )
        """)
        cursor.execute("ALTER TABLE gasdata_dag ADD COLUMN IF NOT EXISTS gas_m3_totaal REAL")
        cursor.execute("ALTER TABLE gasdata_dag ADD COLUMN IF NOT EXISTS gas_m3_per_m2 REAL")
        cursor.execute("ALTER TABLE gasdata_dag ADD COLUMN IF NOT EXISTS gas_mj_totaal REAL")
        cursor.execute("ALTER TABLE gasdata_dag ADD COLUMN IF NOT EXISTS gas_mj_per_m2 REAL")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teeltplanning (
                id SERIAL PRIMARY KEY,
                vaknummer INTEGER NOT NULL,
                verwachte_startdatum TEXT NOT NULL,
                verwachte_duur_weken REAL,
                verwachte_oogstdatum TEXT,
                notitie TEXT,
                aangemaakt_op TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Losse app-instellingen (sleutel/waarde). Bijv. 'planning_besteld_tot':
        # concept-planningen met startdatum t/m die datum staan vast (planten
        # besteld) en worden door plan_x_weken_vooruit niet meer aangepast.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_instelling (
                sleutel TEXT PRIMARY KEY,
                waarde TEXT
            )
        """)

        # Handmatig ingevulde jaarplanning per plantweek: het streefaantal
        # poot-eenheden voor de vak 2-39-cyclus (19+20 = 1), en of vak 1 die
        # week gepoot moet worden (los daarvan, zie VAK_VOLGORDE_UITZONDERING).
        # Geen weekdoel/vak1-vlag voor een week betekent: die week niets
        # plannen — plan_x_weken_vooruit vult zelf niets meer aan.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS planning_weekdoel (
                week_start TEXT PRIMARY KEY,
                aantal_vakken INTEGER
            )
        """)
        cursor.execute("ALTER TABLE planning_weekdoel ALTER COLUMN aantal_vakken DROP NOT NULL")
        cursor.execute(
            "ALTER TABLE planning_weekdoel ADD COLUMN IF NOT EXISTS vak1_planten BOOLEAN NOT NULL DEFAULT FALSE"
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wijzigingenlog (
                id SERIAL PRIMARY KEY,
                tijdstip TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                gebruiker TEXT,
                actie TEXT NOT NULL,
                entiteit TEXT NOT NULL,
                entiteit_id TEXT,
                omschrijving TEXT
            )
        """)

        # Beoordeling van het geleverde stek, één per teelt, ingevuld bij het poten.
        # De stekuitval wordt niet opgeslagen maar berekend uit bakjes en
        # teelten.aantal_planten (zie stek_uitval_pct).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stekbeoordelingen (
                id SERIAL PRIMARY KEY,
                teelt_id INTEGER NOT NULL UNIQUE REFERENCES teelten (id),
                ras TEXT,
                bakjes REAL,
                wortel TEXT,
                plantmaat TEXT,
                uniformiteit TEXT,
                beoordeling INTEGER,
                opmerking TEXT
            )
        """)

        # Migratie: voeg ontbrekende kolommen toe aan bestaande databases.
        # Waar komt een watergiftwaarde vandaan: 'priva' (gemeten) of 'excel'
        # (ingesteld, uit de oude registratie). Alles wat er al stond kwam uit
        # Priva. Zie ook WATERGIFT_BRONNEN.
        cursor.execute("ALTER TABLE watergift_dag ADD COLUMN IF NOT EXISTS bron TEXT")
        cursor.execute("UPDATE watergift_dag SET bron = 'priva' WHERE bron IS NULL")

        # Tuinen: tuin 3 (Hartweg 20) en tuin 1 (Hartweg 29). Alles wat er al
        # stond is van tuin 3; die blijft de standaard, zodat bestaande code
        # zonder tuin blijft werken.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tuinen (
                id SERIAL PRIMARY KEY,
                nummer INTEGER UNIQUE NOT NULL,
                naam TEXT NOT NULL,
                adres TEXT,
                priva_site_id TEXT,
                priva_device_id TEXT
            )
        """)
        for nummer, naam, adres in (
            (1, "Tuin 1", "Albert van 't Hartweg 29"),
            (3, "Tuin 3", "Albert van 't Hartweg 20"),
        ):
            cursor.execute("""
                INSERT INTO tuinen (nummer, naam, adres) VALUES (%s, %s, %s)
                ON CONFLICT (nummer) DO NOTHING
            """, (nummer, naam, adres))

        # Vakken horen bij een tuin en een afdeling; het aantal stelen bij 60/m2
        # verschilt per vak (halve vakken) en stond eerst hard in de app.
        cursor.execute("ALTER TABLE teeltvakken ADD COLUMN IF NOT EXISTS tuin_id INTEGER REFERENCES tuinen (id)")
        cursor.execute("ALTER TABLE teeltvakken ADD COLUMN IF NOT EXISTS afdeling INTEGER")
        cursor.execute("ALTER TABLE teeltvakken ADD COLUMN IF NOT EXISTS stelen_bij_60 INTEGER")
        cursor.execute("SELECT id FROM tuinen WHERE nummer = 3")
        tuin3_id = cursor.fetchone()[0]
        cursor.execute("UPDATE teeltvakken SET tuin_id = %s WHERE tuin_id IS NULL", (tuin3_id,))
        for vaknummer in range(1, 40):
            cursor.execute("""
                UPDATE teeltvakken SET afdeling = %s, stelen_bij_60 = %s
                WHERE tuin_id = %s AND vaknummer = %s AND (afdeling IS NULL OR stelen_bij_60 IS NULL)
            """, (_TUIN3_AFDELING(vaknummer), _TUIN3_STELEN(vaknummer), tuin3_id, vaknummer))

        # Vaknamen zijn alleen binnen een tuin uniek: beide tuinen hebben een vak 1.
        cursor.execute("ALTER TABLE teeltvakken DROP CONSTRAINT IF EXISTS teeltvakken_naam_key")
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS teeltvakken_tuin_vaknummer
            ON teeltvakken (tuin_id, vaknummer) WHERE vaknummer IS NOT NULL
        """)

        # Meetgegevens horen bij een tuin. Alles wat er al stond is van tuin 3.
        # De unieke sleutels gingen uit van een enkele tuin (bijv. een datum kon
        # maar een keer voorkomen in energiedata_dag); die worden vervangen door
        # dezelfde sleutel met de tuin erbij.
        for tabel, sleutel in (
            ("klimaatdata_dag", "tuin_id, afdeling, datum"),
            ("watergift_dag", "tuin_id, vaknummer, datum"),
            ("energiedata_dag", "tuin_id, datum"),
            ("gasdata_dag", "tuin_id, datum"),
        ):
            cursor.execute(f"ALTER TABLE {tabel} ADD COLUMN IF NOT EXISTS tuin_id INTEGER REFERENCES tuinen (id)")
            cursor.execute(f"UPDATE {tabel} SET tuin_id = %s WHERE tuin_id IS NULL", (tuin3_id,))
            # Oude unieke sleutel(s) weg, ongeacht hoe ze heten.
            cursor.execute("""
                SELECT conname FROM pg_constraint
                WHERE conrelid = %s::regclass AND contype = 'u'
            """, (tabel,))
            for (naam,) in cursor.fetchall():
                cursor.execute(f'ALTER TABLE {tabel} DROP CONSTRAINT "{naam}"')
            cursor.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {tabel}_tuin_sleutel ON {tabel} ({sleutel})"
            )

        # Ook de planning hoort bij een tuin: elke tuin plant zijn eigen vakken,
        # en wat er al stond is van tuin 3. Zonder deze kolom zou je op tuin 1
        # de concepten van tuin 3 zien staan en per ongeluk kunnen bevestigen.
        cursor.execute("ALTER TABLE teeltplanning ADD COLUMN IF NOT EXISTS tuin_id INTEGER REFERENCES tuinen (id)")
        cursor.execute("UPDATE teeltplanning SET tuin_id = %s WHERE tuin_id IS NULL", (tuin3_id,))
        cursor.execute("ALTER TABLE planning_weekdoel ADD COLUMN IF NOT EXISTS tuin_id INTEGER REFERENCES tuinen (id)")
        cursor.execute("UPDATE planning_weekdoel SET tuin_id = %s WHERE tuin_id IS NULL", (tuin3_id,))
        # De jaarplanning had de week als sleutel; dat moet nu week + tuin zijn.
        cursor.execute("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'planning_weekdoel'::regclass AND contype = 'p'
        """)
        for (naam,) in cursor.fetchall():
            if naam != "planning_weekdoel_tuin_week":
                cursor.execute(f'ALTER TABLE planning_weekdoel DROP CONSTRAINT "{naam}"')
        cursor.execute("""
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'planning_weekdoel'::regclass AND conname = 'planning_weekdoel_tuin_week'
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE planning_weekdoel ADD CONSTRAINT planning_weekdoel_tuin_week "
                           "PRIMARY KEY (tuin_id, week_start)")

        # Standaardtuin per gebruiker: Kees en Robert werken op tuin 1.
        cursor.execute("ALTER TABLE gebruikers ADD COLUMN IF NOT EXISTS standaard_tuin INTEGER")
        cursor.execute("UPDATE gebruikers SET standaard_tuin = 1 WHERE standaard_tuin IS NULL "
                       "AND username IN ('kees', 'robert')")
        cursor.execute("UPDATE gebruikers SET standaard_tuin = %s WHERE standaard_tuin IS NULL",
                       (STANDAARD_TUIN,))

        cursor.execute("ALTER TABLE teelten ADD COLUMN IF NOT EXISTS rijpheid TEXT")
        # Ras (cultivar) per teelt. Leeg betekent het vaste ras (zie STANDAARD_RAS);
        # zo hoeven de honderden bestaande teelten niet bijgewerkt te worden.
        cursor.execute("ALTER TABLE teelten ADD COLUMN IF NOT EXISTS ras TEXT")
        cursor.execute("ALTER TABLE teelten ADD COLUMN IF NOT EXISTS aantal_planten INTEGER")
        cursor.execute("ALTER TABLE teelten ADD COLUMN IF NOT EXISTS code TEXT")

        # Migratie: voeg het vaknummer toe aan teeltvakken.
        cursor.execute("ALTER TABLE teeltvakken ADD COLUMN IF NOT EXISTS vaknummer INTEGER")
        # Best-effort: bestaande vakken die al puur numeriek genoemd zijn
        # (bijv. naam "19") krijgen dat getal meteen als vaknummer.
        cursor.execute("SELECT id, naam FROM teeltvakken WHERE vaknummer IS NULL")
        for vak_id, naam in cursor.fetchall():
            if naam and naam.strip().isdigit():
                cursor.execute(
                    "UPDATE teeltvakken SET vaknummer = %s WHERE id = %s",
                    (int(naam.strip()), vak_id)
                )

        # Migratie: teeltvakken die automatisch als "Vak {nummer}" benoemd zijn,
        # krijgen alsnog gewoon het kale nummer als naam.
        cursor.execute("SELECT id, naam, vaknummer FROM teeltvakken WHERE vaknummer IS NOT NULL")
        for vak_id, naam, vaknummer in cursor.fetchall():
            if naam == f"Vak {vaknummer}":
                cursor.execute("UPDATE teeltvakken SET naam = %s WHERE id = %s", (str(vaknummer), vak_id))

        # Migratie: bestaande teelten krijgen alsnog een code als hun vak een vaknummer heeft.
        cursor.execute("""
            SELECT t.id, t.datum_teelt_start, v.vaknummer
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE t.code IS NULL AND v.vaknummer IS NOT NULL
        """)
        for teelt_id, datum_start, vaknummer in cursor.fetchall():
            code = genereer_teelt_code(datum_start, vaknummer)
            cursor.execute("UPDATE teelten SET code = %s WHERE id = %s", (code, teelt_id))

        conn.commit()


# --- WIJZIGINGENLOG ---

def log_wijziging(gebruiker, actie, entiteit, entiteit_id=None, omschrijving=None):
    """
    Legt één regel vast in het logboek: wie (gebruiker) wat deed (actie,
    bijv. 'aangemaakt'/'gewijzigd'/'verwijderd'/'geupload') op welk record
    (entiteit + entiteit_id), met een leesbare omschrijving. Faalt een
    logregel om wat voor reden dan ook, dan mag dat de eigenlijke
    databasewijziging niet blokkeren.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO wijzigingenlog (gebruiker, actie, entiteit, entiteit_id, omschrijving)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                gebruiker, actie, entiteit,
                str(entiteit_id) if entiteit_id is not None else None,
                omschrijving,
            ))
            conn.commit()
    except psycopg2.Error:
        pass


def get_wijzigingenlog(limiet=300):
    """Geeft de meest recente logregels terug (nieuwste eerst)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tijdstip, gebruiker, actie, entiteit, entiteit_id, omschrijving
            FROM wijzigingenlog
            ORDER BY tijdstip DESC
            LIMIT %s
        """, (limiet,))
        return cursor.fetchall()


# --- TEELTVAKKEN ---

def get_of_maak_teeltvak(vaknummer, naam=None, tuin_id=None):
    """
    Geeft het id van een teeltvak terug op basis van het vaknummer (1-39);
    maakt het aan als het nog niet bestaat.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        tuin_id = _tuin_of_standaard(tuin_id)
        cursor.execute(
            "SELECT id FROM teeltvakken WHERE vaknummer = %s AND tuin_id = %s",
            (vaknummer, tuin_id),
        )
        resultaat = cursor.fetchone()

        if resultaat:
            teeltvak_id = resultaat[0]
            if naam:
                cursor.execute("UPDATE teeltvakken SET naam = %s WHERE id = %s", (naam, teeltvak_id))
                conn.commit()
        else:
            vak_naam = naam or str(vaknummer)
            cursor.execute(
                "INSERT INTO teeltvakken (naam, vaknummer, tuin_id, afdeling, stelen_bij_60)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (vak_naam, vaknummer, tuin_id, afdeling_van_vak(vaknummer, tuin_id),
                 stelen_bij_60_van_vak(vaknummer, tuin_id))
            )
            teeltvak_id = cursor.fetchone()[0]
            conn.commit()

    return teeltvak_id


def get_alle_teeltvakken():
    """Geeft een lijst van (id, naam, vaknummer) van alle teeltvakken terug."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, naam, vaknummer FROM teeltvakken ORDER BY vaknummer, naam")
        return cursor.fetchall()


# --- TEELTEN ---

def start_nieuwe_teelt(vaknummer, datum_teelt_start, aantal_planten=None, naam=None,
                       gebruiker=None, ras=None, tuin_id=None):
    """
    Start een nieuwe teelt in een teeltvak (op basis van vaknummer 1-39).
    Maakt het teeltvak aan indien het nog niet bestaat.
    Genereert de unieke teelt-code (jaar+week+vaknummer) en slaat het
    aantal geplante planten op.
    Geeft het id van de nieuwe teelt terug.
    """
    teeltvak_id = get_of_maak_teeltvak(vaknummer, naam, tuin_id=tuin_id)
    code = genereer_teelt_code(datum_teelt_start, vaknummer)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teelten (teeltvak_id, datum_teelt_start, aantal_planten, code, ras)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (teeltvak_id, str(datum_teelt_start), aantal_planten, code,
              ras if ras and ras != STANDAARD_RAS else None))
        nieuwe_teelt_id = cursor.fetchone()[0]
        conn.commit()

    log_wijziging(
        gebruiker, "aangemaakt", "teelt", nieuwe_teelt_id,
        f"Nieuwe teelt gestart in vak {vaknummer} op {datum_teelt_start} "
        f"(code {code}, {aantal_planten or 0} planten, ras {ras or STANDAARD_RAS})"
    )

    return nieuwe_teelt_id, code


def get_lopende_teelten(tuin_id=None, zonder_florgib=False):
    """
    Geeft alle teelten terug die daadwerkelijk lopen: nog niet afgerond
    (geen oogstdatum) én al gestart (startdatum ligt niet in de toekomst).
    Een teelt met een toekomstige startdatum is nog niet geplant en hoort
    dus niet tussen de Florgib-/oogstregistratie-keuzes. Handig voor
    selectboxen. Retourneert lijst van tuples: (teelt_id, label_voor_selectbox)

    Met zonder_florgib=True blijven ook de teelten weg die hun Florgib-lengte
    al hebben: bij het invullen daarvan zie je zo alleen wat nog moet.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.tuin_id = %s AND t.datum_oogst IS NULL AND t.datum_teelt_start <= %s
            {"AND t.lengte_half IS NULL" if zonder_florgib else ""}
            ORDER BY t.datum_teelt_start, v.vaknummer
        """, (_tuin_of_standaard(tuin_id), str(date.today())))
        rijen = cursor.fetchall()

    resultaat = []
    for teelt_id, vaknummer, start_datum, code in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        code_deel = code if code else f"ID{teelt_id}"
        label = f"Week {plantweek} - Vak {vak_deel} - {code_deel}"
        resultaat.append((teelt_id, label))
    return resultaat


def update_halverwege(teelt_id, datum_half, lengte_half, gebruiker=None):
    """Slaat de halverwege-meting op voor een specifieke teelt."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teelten
            SET datum_half = %s, lengte_half = %s
            WHERE id = %s
        """, (str(datum_half), lengte_half, teelt_id))
        conn.commit()

    log_wijziging(
        gebruiker, "gewijzigd", "teelt", teelt_id,
        f"Florgib lengte {lengte_half} cm geregistreerd op {datum_half}"
    )


def update_oogst(teelt_id, lengte_eind, oogstgewicht, rijpheid=None, gebruiker=None):
    """
    Slaat lengte, gewicht en rijpheid op voor een specifieke teelt.
    Raakt bewust de oogstdatum niet aan: het afronden van een teelt gebeurt
    los hiervan via markeer_teelt_afgerond (bijv. bij de laatste emmers).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teelten
            SET lengte_eind = %s, oogstgewicht = %s, rijpheid = %s
            WHERE id = %s
        """, (lengte_eind, oogstgewicht, rijpheid, teelt_id))
        conn.commit()

    log_wijziging(
        gebruiker, "gewijzigd", "teelt", teelt_id,
        f"Oogstgegevens geregistreerd: lengte {lengte_eind} cm, gewicht {oogstgewicht} g, rijpheid {rijpheid}"
    )


def markeer_teelt_afgerond(teelt_id, datum_oogst, gebruiker=None):
    """
    Markeert een teelt als afgerond door de oogstdatum te zetten, zonder de
    (eventueel nog onbekende) eindstand-velden lengte/gewicht/rijpheid aan te passen.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE teelten SET datum_oogst = %s WHERE id = %s",
            (str(datum_oogst), teelt_id)
        )
        conn.commit()

    log_wijziging(gebruiker, "gewijzigd", "teelt", teelt_id, f"Teelt afgerond op {datum_oogst}")


def get_alle_teelten_voor_selectie(tuin_id=None):
    """
    Geeft ALLE teelten terug (ook afgeronde), met een duidelijk label.
    Handig voor de 'wijzigen/verwijderen'-selectbox.
    Retourneert lijst van tuples: (teelt_id, label)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.tuin_id = %s
            ORDER BY t.datum_teelt_start, v.vaknummer
        """, (_tuin_of_standaard(tuin_id),))
        rijen = cursor.fetchall()

    resultaat = []
    for teelt_id, vaknummer, start_datum, code in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        code_deel = code if code else f"ID{teelt_id}"
        label = f"Week {plantweek} - Vak {vak_deel} - {code_deel}"
        resultaat.append((teelt_id, label))
    return resultaat


def get_isojaar_week(datum):
    """Geeft (iso-jaar, iso-weeknummer) van een datum terug, voor groepering per plantweek."""
    if isinstance(datum, str):
        datum = datetime.strptime(datum, "%Y-%m-%d").date()
    iso_jaar, week, _ = datum.isocalendar()
    return iso_jaar, week


def get_alle_teelten_detail(tuin_id=None):
    """
    Geeft alle teelten terug met de ruwe (onopgemaakte) velden, voor
    client-side aggregatie in het dashboard (bijv. groeperen per plantweek).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.code, v.vaknummer, t.datum_teelt_start, t.datum_half, t.lengte_half,
                   t.datum_oogst, t.lengte_eind, t.oogstgewicht, t.rijpheid, t.aantal_planten
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.tuin_id = %s
            ORDER BY t.datum_teelt_start, v.vaknummer
        """, (_tuin_of_standaard(tuin_id),))
        rijen = cursor.fetchall()

    resultaat = []
    for (teelt_id, code, vaknummer, start, half_datum, half_lengte,
         oogst_datum, eind_lengte, gewicht, rijpheid, aantal_planten) in rijen:
        resultaat.append({
            "id": teelt_id,
            "code": code,
            "vaknummer": vaknummer,
            "datum_teelt_start": start,
            "datum_half": half_datum,
            "lengte_half": half_lengte,
            "datum_oogst": oogst_datum,
            "lengte_eind": eind_lengte,
            "oogstgewicht": gewicht,
            "rijpheid": rijpheid,
            "aantal_planten": aantal_planten,
        })
    return resultaat


def get_teelt_by_id(teelt_id):
    """Geeft alle gegevens van één teelt terug als dict, of None als niet gevonden."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.naam, v.vaknummer, t.datum_teelt_start, t.datum_half, t.lengte_half,
                   t.datum_oogst, t.lengte_eind, t.oogstgewicht, t.rijpheid,
                   t.aantal_planten, t.code, t.ras
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE t.id = %s
        """, (teelt_id,))
        rij = cursor.fetchone()

    if not rij:
        return None

    return {
        "id": rij[0],
        "teeltvak_naam": rij[1],
        "vaknummer": rij[2],
        "datum_teelt_start": rij[3],
        "datum_half": rij[4],
        "lengte_half": rij[5],
        "datum_oogst": rij[6],
        "lengte_eind": rij[7],
        "oogstgewicht": rij[8],
        "rijpheid": rij[9],
        "aantal_planten": rij[10],
        "code": rij[11],
        "ras": rij[12],
    }


def update_teelt_volledig(teelt_id, datum_teelt_start, datum_half, lengte_half,
                           datum_oogst, lengte_eind, oogstgewicht, rijpheid=None,
                           aantal_planten=None, vaknummer=None, gebruiker=None):
    """Overschrijft alle velden van een bestaande teelt (gebruikt bij handmatige correctie)."""
    code = genereer_teelt_code(datum_teelt_start, vaknummer) if vaknummer else None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teelten
            SET datum_teelt_start = %s, datum_half = %s, lengte_half = %s,
                datum_oogst = %s, lengte_eind = %s, oogstgewicht = %s, rijpheid = %s,
                aantal_planten = %s, code = COALESCE(%s, code)
            WHERE id = %s
        """, (
            str(datum_teelt_start) if datum_teelt_start else None,
            str(datum_half) if datum_half else None,
            lengte_half,
            str(datum_oogst) if datum_oogst else None,
            lengte_eind,
            oogstgewicht,
            rijpheid,
            aantal_planten,
            code,
            teelt_id
        ))
        conn.commit()

    log_wijziging(
        gebruiker, "gewijzigd", "teelt", teelt_id,
        f"Volledige correctie: start {datum_teelt_start}, half {datum_half or '-'} "
        f"({lengte_half or '-'} cm), oogst {datum_oogst or '-'} ({lengte_eind or '-'} cm, "
        f"{oogstgewicht or '-'} g, rijpheid {rijpheid or '-'}), {aantal_planten or '-'} planten"
    )


def delete_teelt(teelt_id, gebruiker=None):
    """Verwijdert een teelt permanent, inclusief de bijbehorende oogstregistraties."""
    teelt = get_teelt_by_id(teelt_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM oogstregistraties WHERE teelt_id = %s", (teelt_id,))
        cursor.execute("DELETE FROM teelten WHERE id = %s", (teelt_id,))
        conn.commit()

    if teelt:
        omschrijving = f"Teelt verwijderd: vak {teelt['vaknummer']}, code {teelt['code'] or '-'}"
    else:
        omschrijving = "Teelt verwijderd"
    log_wijziging(gebruiker, "verwijderd", "teelt", teelt_id, omschrijving)


# --- OOGSTREGISTRATIES (EMMERS) ---

def voeg_oogstregistratie_toe(teelt_id, datum, aantal_emmers, gebruiker=None):
    """Voegt een oogstmoment (aantal emmers, 100 stelen per emmer) toe aan een teelt."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO oogstregistraties (teelt_id, datum, aantal_emmers)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (teelt_id, str(datum), aantal_emmers))
        registratie_id = cursor.fetchone()[0]
        conn.commit()

    log_wijziging(
        gebruiker, "aangemaakt", "oogstregistratie", registratie_id,
        f"{aantal_emmers:g} emmers geregistreerd op {datum} voor teelt {teelt_id}"
    )


def get_oogstregistraties_voor_teelt(teelt_id):
    """Geeft alle oogstmomenten van een teelt terug: lijst van (id, datum, aantal_emmers)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, datum, aantal_emmers
            FROM oogstregistraties
            WHERE teelt_id = %s
            ORDER BY datum
        """, (teelt_id,))
        return cursor.fetchall()


def wijzig_oogstregistratie(registratie_id, datum, aantal_emmers, gebruiker=None):
    """Past de datum en het aantal emmers van een bestaand oogstmoment aan."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE oogstregistraties SET datum = %s, aantal_emmers = %s WHERE id = %s",
            (str(datum), aantal_emmers, registratie_id)
        )
        conn.commit()

    log_wijziging(
        gebruiker, "gewijzigd", "oogstregistratie", registratie_id,
        f"Aangepast naar {aantal_emmers:g} emmers op {datum}"
    )


def verwijder_oogstregistratie(registratie_id, gebruiker=None):
    """Verwijdert een enkel oogstmoment."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT teelt_id, datum, aantal_emmers FROM oogstregistraties WHERE id = %s",
            (registratie_id,)
        )
        bestaand = cursor.fetchone()
        cursor.execute("DELETE FROM oogstregistraties WHERE id = %s", (registratie_id,))
        conn.commit()

    if bestaand:
        teelt_id, datum, aantal_emmers = bestaand
        omschrijving = f"{aantal_emmers:g} emmers op {datum} verwijderd (teelt {teelt_id})"
    else:
        omschrijving = "Oogstregistratie verwijderd"
    log_wijziging(gebruiker, "verwijderd", "oogstregistratie", registratie_id, omschrijving)


def get_totaal_emmers_per_teelt():
    """Geeft een dict {teelt_id: totaal_aantal_emmers} terug voor alle teelten met registraties."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT teelt_id, SUM(aantal_emmers)
            FROM oogstregistraties
            GROUP BY teelt_id
        """)
        return {teelt_id: totaal for teelt_id, totaal in cursor.fetchall()}


def get_oogstregistraties_voor_periode(datum_start, datum_eind):
    """
    Geeft alle oogstmomenten (emmers) binnen een periode terug, met vak en
    teeltcode erbij — voor het weekoverzicht. Lijst van dicts, gesorteerd op
    vaknummer en datum.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.datum, v.vaknummer, t.code, o.aantal_emmers
            FROM oogstregistraties o
            JOIN teelten t ON o.teelt_id = t.id
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE o.datum BETWEEN %s AND %s
            ORDER BY v.vaknummer, o.datum
        """, (str(datum_start), str(datum_eind)))
        return [
            {"datum": datum, "vaknummer": vaknummer, "code": code, "aantal_emmers": emmers}
            for datum, vaknummer, code, emmers in cursor.fetchall()
        ]


def get_watergift_per_vak_voor_periode(datum_start, datum_eind, tuin_id=None):
    """
    Totale watergift (liter/m²) per vak binnen een periode, voor alle vakken
    met data in die periode. Lijst van (vaknummer, totaal_liter_per_m2,
    aantal_dagen), gesorteerd op vaknummer (laag naar hoog).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vaknummer, SUM(liter_per_m2), COUNT(*)
            FROM watergift_dag
            WHERE tuin_id = %s AND datum BETWEEN %s AND %s
            GROUP BY vaknummer
            ORDER BY vaknummer
        """, (_tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


# --- GEBRUIKERS (INLOG) ---

def get_gebruikers_credentials():
    """
    Geeft alle gebruikers terug in het formaat dat streamlit-authenticator
    verwacht:
        {"usernames": {username: {"name": ..., "password": <hash>, "email": ...}}}
    De wachtwoorden zijn de bcrypt-hashes zoals ze in de database staan.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, naam, wachtwoord_hash, email FROM gebruikers")
        rijen = cursor.fetchall()

    usernames = {}
    for username, naam, wachtwoord_hash, email in rijen:
        usernames[username] = {
            "name": naam,
            "password": wachtwoord_hash,
            "email": email or "",
        }
    return {"usernames": usernames}


def voeg_gebruiker_toe(username, naam, wachtwoord_hash, email=None, gebruiker=None):
    """
    Voegt een gebruiker toe of werkt een bestaande bij (op username).
    Het wachtwoord moet al gehasht zijn, bijv. met
    streamlit_authenticator.Hasher.hash(...). Er wordt nooit een wachtwoord in
    platte tekst opgeslagen (ook niet in het wijzigingenlog).
    """
    username = username.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gebruikers (username, naam, wachtwoord_hash, email)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET naam = EXCLUDED.naam,
                          wachtwoord_hash = EXCLUDED.wachtwoord_hash,
                          email = EXCLUDED.email
        """, (username, naam, wachtwoord_hash, email))
        conn.commit()

    log_wijziging(
        gebruiker, "aangemaakt/gewijzigd", "gebruiker", username,
        f"Gebruiker '{username}' ({naam}) aangemaakt of bijgewerkt"
    )


def verwijder_gebruiker(username, gebruiker=None):
    """Verwijdert een gebruiker."""
    username = username.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gebruikers WHERE username = %s", (username,))
        conn.commit()

    log_wijziging(gebruiker, "verwijderd", "gebruiker", username, f"Gebruiker '{username}' verwijderd")


def get_alle_gebruikers():
    """Geeft (username, naam, email) van alle gebruikers terug."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, naam, email FROM gebruikers ORDER BY username")
        return cursor.fetchall()


def get_overzicht_dataframe(tuin_id=None):
    """
    Geeft alle teelten terug inclusief teeltvaknaam, code, weeknummers,
    teeltduur, geoogste emmers en uitvalpercentage.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                t.id,
                t.code,
                v.naam,
                t.aantal_planten,
                t.datum_teelt_start,
                t.datum_half,
                t.lengte_half,
                t.datum_oogst,
                t.lengte_eind,
                t.oogstgewicht,
                t.rijpheid
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.tuin_id = %s
            ORDER BY (t.code IS NULL), t.code
        """, (_tuin_of_standaard(tuin_id),))
        teelt_rijen = cursor.fetchall()

    totaal_emmers_per_teelt = get_totaal_emmers_per_teelt()
    vandaag_iso = str(date.today())

    rijen_uitgebreid = []
    for row in teelt_rijen:
        (teelt_id, code, naam, aantal_planten, start, half_datum, half_lengte,
         oogst_datum, eind_lengte, gewicht, rijpheid) = row

        start_week = get_weeknummer(start) if start else "-"
        teeltduur = get_teeltduur(start, oogst_datum) if (start and oogst_datum) else "-"

        totaal_emmers = totaal_emmers_per_teelt.get(teelt_id)
        totaal_stelen = totaal_emmers * 100 if totaal_emmers else "-"

        if aantal_planten and totaal_emmers:
            uitval_pct = f"{(aantal_planten - totaal_emmers * 100) / aantal_planten * 100:.2f}"
        else:
            uitval_pct = "-"

        if oogst_datum:
            status = "Afgerond"
        elif start and start > vandaag_iso:
            status = "Nog te starten"
        else:
            status = "Lopend"

        rijen_uitgebreid.append((
            teelt_id,
            str(start) if start else "",  # verborgen sorteersleutel (ISO)
            naam,
            start_week,
            status,
            get_weeknummer(half_datum) if half_datum else "-",
            half_lengte if half_lengte else "-",
            get_weeknummer(oogst_datum) if oogst_datum else "-",
            teeltduur,
            eind_lengte if eind_lengte else "-",
            round(gewicht) if gewicht else "-",
            rijpheid if rijpheid else "-",
            uitval_pct,
            aantal_planten if aantal_planten else "-",
            totaal_emmers if totaal_emmers else "-",
            totaal_stelen,
            code if code else "-",
            format_datum(start) if start else "-",
            format_datum(half_datum) if half_datum else "-",
            format_datum(oogst_datum) if oogst_datum else "-",
        ))

    kolommen = ["ID", "_startdatum_iso", "Teeltvak", "Startweek", "Status",
                "Week Halverwege", "Lengte Half (cm)", "Oogstweek", "Teeltduur (dagen)",
                "Oogstlengte (cm)", "Oogstgewicht (gram)", "Rijpheid", "Uitval (%)",
                "Aantal Planten", "Aantal Emmers", "Aantal Stelen", "Code",
                "Startdatum", "Datum Halverwege", "Oogstdatum"]
    return kolommen, rijen_uitgebreid


# --- KLIMAATDATA (KLIMAATCOMPUTER-CSV) ---
#
# Kasindeling: afdeling 1 = vak 1-9, afdeling 2 = vak 30-39,
# afdeling 3 = vak 10-19, afdeling 4 = vak 20-29.
#
# De klimaatcomputer-export bevat dagregels (startdate = enddate, per dag)
# per variabele (label) en afdeling. Voor de teeltkoppeling gebruiken we
# Ave_24h_CompTemp (gemiddelde temperatuur), Ave_24h_CompRV (gemiddelde RV)
# en de som van Sum_Day_CalculatedRadiation + Sum_Night_CalculatedRadiation
# (stralingssom van die dag). Rijen voor een andere "Afdeling"-index dan 1-4
# (bijv. index 5) horen niet bij een van onze kasafdelingen en worden genegeerd.

KLIMAAT_TEMP_LABEL = "Ave_24h_CompTemp"
KLIMAAT_TEMP_DAG_LABEL = "Ave_Day_CompTemp"
KLIMAAT_TEMP_NACHT_LABEL = "Ave_Night_CompTemp"
KLIMAAT_RV_LABEL = "Ave_24h_CompRV"
KLIMAAT_RV_DAG_LABEL = "Ave_Day_CompRV"
KLIMAAT_RV_NACHT_LABEL = "Ave_Night_CompRV"
KLIMAAT_STRALING_LABELS = ["Sum_Day_CalculatedRadiation", "Sum_Night_CalculatedRadiation"]
KLIMAAT_GELDIGE_AFDELINGEN = {1, 2, 3, 4}

# Vuistregel licht/temperatuur (Job): bij een hogere lichtsom hoort een
# hogere etmaaltemperatuur, in een vaste verhouding. Buiten die
# verhouding wordt er relatief te warm of te koud gestookt t.o.v. het licht.
LICHT_TEMP_FACTOR = 0.0072
LICHT_TEMP_BASIS = 11.7


def ideale_etmaaltemperatuur(lichtsom):
    """
    Streefwaarde voor de etmaaltemperatuur (°C) op basis van de lichtsom:
    LICHT_TEMP_FACTOR x lichtsom + LICHT_TEMP_BASIS. Werkt ook op een
    pandas Series (voor grafieken). Geeft None terug bij lichtsom=None.
    """
    if lichtsom is None:
        return None
    return LICHT_TEMP_FACTOR * lichtsom + LICHT_TEMP_BASIS


def afdeling_van_vaknummer(vaknummer):
    """Vertaalt een vaknummer (1-39) naar het bijbehorende afdelingsnummer (1-4)."""
    if vaknummer is None:
        return None
    vaknummer = int(vaknummer)
    if 1 <= vaknummer <= 9:
        return 1
    if 30 <= vaknummer <= 39:
        return 2
    if 10 <= vaknummer <= 19:
        return 3
    if 20 <= vaknummer <= 29:
        return 4
    return None


def upsert_klimaatdata_dag(afdeling, datum, gem_temperatuur, gem_rv, stralingssom_dag,
                            gem_temperatuur_dag=None, gem_temperatuur_nacht=None,
                            gem_rv_dag=None, gem_rv_nacht=None, tuin_id=None):
    """Slaat één afdeling-dag klimaatgegevens op (of overschrijft de bestaande dag bij een herupload)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO klimaatdata_dag
                (tuin_id, afdeling, datum, gem_temperatuur, gem_rv, stralingssom_dag,
                 gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tuin_id, afdeling, datum)
            DO UPDATE SET gem_temperatuur = EXCLUDED.gem_temperatuur,
                          gem_rv = EXCLUDED.gem_rv,
                          stralingssom_dag = EXCLUDED.stralingssom_dag,
                          gem_temperatuur_dag = EXCLUDED.gem_temperatuur_dag,
                          gem_temperatuur_nacht = EXCLUDED.gem_temperatuur_nacht,
                          gem_rv_dag = EXCLUDED.gem_rv_dag,
                          gem_rv_nacht = EXCLUDED.gem_rv_nacht
        """, (
            _tuin_of_standaard(tuin_id), afdeling, str(datum), gem_temperatuur, gem_rv,
            stralingssom_dag, gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht,
        ))
        conn.commit()


def verwerk_klimaat_csv(bestand, gebruiker=None, tuin_id=None):
    """
    Leest een klimaatcomputer-CSV in (tab- of puntkomma-gescheiden, decimale
    komma) en zet de dagregels om naar rijen in klimaatdata_dag, per
    afdeling (1-4). Dagen die nog niet helemaal voorbij zijn (einddatum
    vandaag of later) worden overgeslagen, want die staan al wel in de
    export maar zijn nog niet compleet. Geeft (aantal verwerkte
    afdeling-dagen, aantal overgeslagen onvolledige afdeling-dagen) terug.
    """
    try:
        df = pd.read_csv(bestand, sep=None, engine="python", decimal=",")
    except Exception:
        bestand.seek(0)
        df = pd.read_csv(bestand, sep="\t", decimal=",")

    df.columns = df.columns.str.strip()
    df = df[df["type_1"] == "Afdeling"].copy()
    df["idx_1"] = pd.to_numeric(df["idx_1"], errors="coerce")
    df = df[df["idx_1"].isin(KLIMAAT_GELDIGE_AFDELINGEN)]

    df["datum"] = pd.to_datetime(df["startdate"], dayfirst=True, format="mixed").dt.date
    df["datum_tot"] = pd.to_datetime(df["enddate"], dayfirst=True, format="mixed").dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    alle_dagen = df[["idx_1", "datum"]].drop_duplicates()
    df = df[df["datum_tot"] < date.today()]
    volledige_dagen = df[["idx_1", "datum"]].drop_duplicates()
    overgeslagen = len(alle_dagen) - len(volledige_dagen)

    relevante_labels = [
        KLIMAAT_TEMP_LABEL, KLIMAAT_TEMP_DAG_LABEL, KLIMAAT_TEMP_NACHT_LABEL,
        KLIMAAT_RV_LABEL, KLIMAAT_RV_DAG_LABEL, KLIMAAT_RV_NACHT_LABEL,
    ] + KLIMAAT_STRALING_LABELS
    df = df[df["label"].isin(relevante_labels)]

    def _eerste_waarde(groep, label):
        reeks = groep.loc[groep["label"] == label, "value"].dropna()
        return float(reeks.iloc[0]) if not reeks.empty else None

    verwerkt = 0
    for (afdeling, datum), groep in df.groupby(["idx_1", "datum"]):
        straling = groep.loc[groep["label"].isin(KLIMAAT_STRALING_LABELS), "value"].dropna()
        stralingssom_dag = float(straling.sum()) if not straling.empty else None

        upsert_klimaatdata_dag(
            int(afdeling), datum,
            _eerste_waarde(groep, KLIMAAT_TEMP_LABEL),
            _eerste_waarde(groep, KLIMAAT_RV_LABEL),
            stralingssom_dag,
            gem_temperatuur_dag=_eerste_waarde(groep, KLIMAAT_TEMP_DAG_LABEL),
            gem_temperatuur_nacht=_eerste_waarde(groep, KLIMAAT_TEMP_NACHT_LABEL),
            gem_rv_dag=_eerste_waarde(groep, KLIMAAT_RV_DAG_LABEL),
            gem_rv_nacht=_eerste_waarde(groep, KLIMAAT_RV_NACHT_LABEL),
        )
        verwerkt += 1

    log_wijziging(
        gebruiker, "geupload", "klimaatdata_csv", None,
        f"{verwerkt} afdeling-dagen verwerkt, {overgeslagen} overgeslagen (nog niet afgerond)"
    )

    return verwerkt, overgeslagen


def importeer_klimaat_uit_priva(dagen_terug=4, gebruiker=None, tuin_id=None):
    """
    Haalt de etmaalklimaatcijfers (etmaaltemperatuur en dag/nacht, gemiddelde
    RV en dag/nacht, stralingssom) van de laatste afgeronde dagen rechtstreeks
    op uit de Priva Horti API en zet ze via upsert in klimaatdata_dag — het
    alternatief voor de handmatige klimaatcomputer-CSV. Historische CSV-rijen
    blijven ongemoeid; alleen dagen die de API teruggeeft worden
    geschreven/overschreven.

    Geeft (aantal geschreven afdeling-dagen, aantal overgeslagen) terug.
    Overgeslagen = dagen die nog niet compleet in het verleden liggen.
    """
    from priva_client import PrivaHortiClient

    rijen = PrivaHortiClient().haal_etmaal_dagwaarden(dagen_terug)

    verwerkt = 0
    overgeslagen = 0
    for rij in rijen:
        if rij["datum"] >= date.today():
            overgeslagen += 1
            continue
        upsert_klimaatdata_dag(
            rij["afdeling"], rij["datum"],
            rij["gem_temperatuur"], rij["gem_rv"], rij["stralingssom_dag"],
            gem_temperatuur_dag=rij.get("gem_temperatuur_dag"),
            gem_temperatuur_nacht=rij.get("gem_temperatuur_nacht"),
            gem_rv_dag=rij.get("gem_rv_dag"),
            gem_rv_nacht=rij.get("gem_rv_nacht"),
        )
        verwerkt += 1

    if rijen:
        eerste = min(r["datum"] for r in rijen)
        laatste = max(r["datum"] for r in rijen)
        periode = f"{format_datum(eerste)} t/m {format_datum(laatste)}"
    else:
        periode = "geen data"
    log_wijziging(
        gebruiker, "opgehaald", "klimaatdata_priva", None,
        f"{verwerkt} afdeling-dagen uit Priva ({periode}), {overgeslagen} overgeslagen"
    )

    return verwerkt, overgeslagen


# --- WATERGIFT PER VAK (uit Priva) ---

WATERGIFT_BRONNEN = ("priva", "excel")


def upsert_watergift_dag(vaknummer, datum, liter_per_m2, bron="priva", tuin_id=None):
    """
    Slaat één vak-dag watergift op (of overschrijft bij een herhaalde ophaal).

    `bron` is 'priva' (gemeten) of 'excel' (ingesteld, uit de oude registratie).
    Een gemeten waarde overschrijft altijd; een waarde uit Excel alleen als er
    nog niets staat of als daar ook Excel staat. Zo blijft de meting leidend.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO watergift_dag (tuin_id, vaknummer, datum, liter_per_m2, bron)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tuin_id, vaknummer, datum)
            DO UPDATE SET liter_per_m2 = EXCLUDED.liter_per_m2, bron = EXCLUDED.bron
            WHERE EXCLUDED.bron = 'priva' OR watergift_dag.bron = 'excel'
        """, (_tuin_of_standaard(tuin_id), int(vaknummer), str(datum), liter_per_m2, bron))
        conn.commit()


def importeer_watergift_uit_priva(dagen_terug=4, gebruiker=None, tuin_id=None):
    """
    Haalt de daggift (liter/m²) per vak van de laatste afgeronde dagen op uit
    de Priva Horti API en zet die via upsert in watergift_dag.

    Geeft (aantal geschreven vak-dagen, aantal overgeslagen) terug.
    """
    from priva_client import PrivaHortiClient

    rijen = PrivaHortiClient().haal_watergift_dagwaarden(dagen_terug)

    verwerkt = 0
    overgeslagen = 0
    for rij in rijen:
        if rij["datum"] >= date.today():
            overgeslagen += 1
            continue
        upsert_watergift_dag(rij["vaknummer"], rij["datum"], rij["liter_per_m2"])
        verwerkt += 1

    if rijen:
        eerste = min(r["datum"] for r in rijen)
        laatste = max(r["datum"] for r in rijen)
        periode = f"{format_datum(eerste)} t/m {format_datum(laatste)}"
    else:
        periode = "geen data"
    log_wijziging(
        gebruiker, "opgehaald", "watergift_priva", None,
        f"{verwerkt} vak-dagen uit Priva ({periode}), {overgeslagen} overgeslagen"
    )

    return verwerkt, overgeslagen


def get_watergift_voor_periode(vaknummer, datum_start, datum_eind, tuin_id=None):
    """
    Geeft het totaal aan watergift (liter/m²) en het aantal gemeten dagen
    terug voor een vak binnen een periode. Geeft None als er geen data is.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(liter_per_m2), COUNT(*)
            FROM watergift_dag
            WHERE tuin_id = %s AND vaknummer = %s AND datum BETWEEN %s AND %s
        """, (_tuin_of_standaard(tuin_id), int(vaknummer), str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[1] == 0:
        return None
    return {"totaal_liter_per_m2": rij[0] or 0.0, "aantal_dagen": rij[1]}


def get_watergift_dagen_voor_periode(vaknummer, datum_start, datum_eind, tuin_id=None):
    """Losse dagregels (datum, liter_per_m2) voor grafieken, gesorteerd op datum."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, liter_per_m2
            FROM watergift_dag
            WHERE tuin_id = %s AND vaknummer = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (_tuin_of_standaard(tuin_id), int(vaknummer), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_watergift_per_dag_voor_periode(datum_start, datum_eind, tuin_id=None):
    """
    Losse (datum, vaknummer, liter_per_m2)-regels voor alle vakken binnen een
    periode, gesorteerd op datum en daarna vaknummer (laag naar hoog) — voor
    een dagoverzicht van wat er water heeft gehad.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, vaknummer, liter_per_m2
            FROM watergift_dag
            WHERE tuin_id = %s AND datum BETWEEN %s AND %s
            ORDER BY datum, vaknummer
        """, (_tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_watergift_dekking(tuin_id=None):
    """
    Per vak: (vaknummer, eerste_datum, laatste_datum, aantal_dagen). Gesorteerd
    op vaknummer (laag naar hoog).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vaknummer, MIN(datum), MAX(datum), COUNT(*)
            FROM watergift_dag
            WHERE tuin_id = %s
            GROUP BY vaknummer
            ORDER BY vaknummer
        """, (_tuin_of_standaard(tuin_id),))
        return [(v, str(mn), str(mx), n) for v, mn, mx, n in cursor.fetchall()]


# --- WARMTEVERBRUIK (KLIMAATCOMPUTER-CSV, PULSTELLER VOOR HELE KAS) ---
#
# Vakoppervlaktes tuin 3: vak 1-18 en 21-39 zijn 550 m2, vak 19 en 20 zijn
# 275 m2 (smallere vakken). Totaal 37 * 550 + 2 * 275 = 20.900 m2.
#
# De Pulsteller-export levert Sum_24h_PtEnergyUse in GJ per dag; we slaan
# alles op in MJ (x 1000).

ENERGIE_LABEL = "Sum_24h_PtEnergyUse"
ENERGIE_EENHEID_NAAR_MJ = 1000  # ruwe waarde staat in GJ

# Gasgestookte warmte (bijv. bijstook in enkele weken) staat in dezelfde
# export, onder hetzelfde label Sum_24h_PtEnergyUse maar op een andere
# Pulsteller-index: idx_1 = 2 is de hoofdwarmte (GJ/dag, energiedata_dag),
# idx_1 = 1 is de gasketel (gasdata_dag) — dat kanaal heeft een gasmeter als
# pulsgever en levert dus m3/dag, geen GJ (correctie van Job, sept 2026).
# Calorische waarde: bovenwaarde Groningen-gas, geen rendementscorrectie.
PULSTELLER_IDX_WARMTE = 2
PULSTELLER_IDX_GAS = 1
GAS_CALORISCHE_WAARDE_MJ_PER_M3 = 31.65

VAK_OPPERVLAKTE_STANDAARD = 550
VAK_OPPERVLAKTE_SMAL = 275
VAKKEN_SMAL = {19, 20}


def oppervlakte_van_vaknummer(vaknummer):
    """Geeft de kasoppervlakte (m2) van een vaknummer (1-39) terug."""
    if vaknummer is None:
        return None
    vaknummer = int(vaknummer)
    if vaknummer in VAKKEN_SMAL:
        return VAK_OPPERVLAKTE_SMAL
    if 1 <= vaknummer <= 39:
        return VAK_OPPERVLAKTE_STANDAARD
    return None


TUIN3_OPPERVLAKTE_M2 = (39 - len(VAKKEN_SMAL)) * VAK_OPPERVLAKTE_STANDAARD + len(VAKKEN_SMAL) * VAK_OPPERVLAKTE_SMAL


def upsert_energiedata_dag(datum, warmte_mj_totaal, tuin_id=None):
    """Slaat het totale warmteverbruik (MJ) van de hele kas voor één dag op."""
    tuin_id = _tuin_of_standaard(tuin_id)
    oppervlakte = oppervlakte_van_tuin(tuin_id)
    warmte_mj_per_m2 = warmte_mj_totaal / oppervlakte if warmte_mj_totaal is not None else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO energiedata_dag (tuin_id, datum, warmte_mj_totaal, warmte_mj_per_m2)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tuin_id, datum)
            DO UPDATE SET warmte_mj_totaal = EXCLUDED.warmte_mj_totaal,
                          warmte_mj_per_m2 = EXCLUDED.warmte_mj_per_m2
        """, (tuin_id, str(datum), warmte_mj_totaal, warmte_mj_per_m2))
        conn.commit()


def upsert_gasdata_dag(datum, gas_m3_totaal, tuin_id=None):
    """Slaat het gasverbruik (m3 en omgerekend naar MJ) van de hele kas voor één dag op."""
    tuin_id = _tuin_of_standaard(tuin_id)
    oppervlakte = oppervlakte_van_tuin(tuin_id)
    gas_m3_per_m2 = gas_m3_totaal / oppervlakte if gas_m3_totaal is not None else None
    gas_mj_totaal = gas_m3_totaal * GAS_CALORISCHE_WAARDE_MJ_PER_M3 if gas_m3_totaal is not None else None
    gas_mj_per_m2 = gas_mj_totaal / oppervlakte if gas_mj_totaal is not None else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gasdata_dag (tuin_id, datum, gas_m3_totaal, gas_m3_per_m2, gas_mj_totaal, gas_mj_per_m2)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tuin_id, datum)
            DO UPDATE SET gas_m3_totaal = EXCLUDED.gas_m3_totaal,
                          gas_m3_per_m2 = EXCLUDED.gas_m3_per_m2,
                          gas_mj_totaal = EXCLUDED.gas_mj_totaal,
                          gas_mj_per_m2 = EXCLUDED.gas_mj_per_m2
        """, (tuin_id, str(datum), gas_m3_totaal, gas_m3_per_m2, gas_mj_totaal, gas_mj_per_m2))
        conn.commit()


def verwerk_energie_csv(bestand, gebruiker=None, tuin_id=None):
    """
    Leest een energiecomputer-CSV in (Priva-export "Rapport Energie") en
    verwerkt twee bronnen uit dezelfde upload, beide onder het label
    Sum_24h_PtEnergyUse maar met een andere Pulsteller-index:
    - PULSTELLER_IDX_WARMTE (2): de hoofdwarmte, in GJ -> energiedata_dag;
    - PULSTELLER_IDX_GAS (1): de gasketel (bijstook), in m3 (gasmeter als
      pulsgever) -> omgerekend naar MJ, in gasdata_dag.
    Er kan per dag meer dan één rij per teller in de export staan; die
    worden per bron per dag bij elkaar opgeteld. Dagen die nog niet helemaal
    voorbij zijn worden overgeslagen. Geeft terug: (aantal dagen warmte
    verwerkt, aantal dagen warmte overgeslagen, aantal dagen gas verwerkt).
    """
    try:
        df = pd.read_csv(bestand, sep=None, engine="python", decimal=",")
    except Exception:
        bestand.seek(0)
        df = pd.read_csv(bestand, sep="\t", decimal=",")

    df.columns = df.columns.str.strip()
    df["datum"] = pd.to_datetime(df["startdate"], dayfirst=True, format="mixed").dt.date
    df["datum_tot"] = pd.to_datetime(df["enddate"], dayfirst=True, format="mixed").dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    def _verwerk_bron(subset, upsert_fn):
        alle_dagen = subset["datum"].drop_duplicates()
        volledig = subset[subset["datum_tot"] < date.today()]
        volledige_dagen = volledig["datum"].drop_duplicates()
        overgeslagen = len(alle_dagen) - len(volledige_dagen)
        verwerkt = 0
        for datum, groep in volledig.groupby("datum"):
            waarden = groep["value"].dropna()
            if waarden.empty:
                continue
            upsert_fn(datum, float(waarden.sum()))
            verwerkt += 1
        return verwerkt, overgeslagen

    is_pulsteller = (df["type_1"] == "Pulsteller") & (df["label"] == ENERGIE_LABEL)

    df_warmte = df[is_pulsteller & (df["idx_1"] == PULSTELLER_IDX_WARMTE)].copy()
    verwerkt, overgeslagen = _verwerk_bron(
        df_warmte, lambda d, v: upsert_energiedata_dag(d, v * ENERGIE_EENHEID_NAAR_MJ)
    )

    df_gas = df[is_pulsteller & (df["idx_1"] == PULSTELLER_IDX_GAS)].copy()
    verwerkt_gas, _overgeslagen_gas = _verwerk_bron(df_gas, upsert_gasdata_dag)

    log_wijziging(
        gebruiker, "geupload", "energiedata_csv", None,
        f"{verwerkt} dagen warmte verwerkt, {overgeslagen} overgeslagen (nog niet afgerond), "
        f"{verwerkt_gas} dagen gasverbruik verwerkt"
    )

    return verwerkt, overgeslagen, verwerkt_gas


def get_energiedata_dagen_voor_periode(datum_start, datum_eind, tuin_id=None):
    """Losse dagregels (datum, warmte_mj_totaal, warmte_mj_per_m2) voor grafieken."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, warmte_mj_totaal, warmte_mj_per_m2
            FROM energiedata_dag
            WHERE tuin_id = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (_tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_energiedata_dekking(tuin_id=None):
    """(eerste_datum, laatste_datum, aantal_dagen, ontbrekende_dagen) of None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(datum), MAX(datum), COUNT(*) FROM energiedata_dag WHERE tuin_id = %s",
                       (_tuin_of_standaard(tuin_id),))
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    eerste_d = datetime.strptime(str(rij[0]), "%Y-%m-%d").date()
    laatste_d = datetime.strptime(str(rij[1]), "%Y-%m-%d").date()
    verwacht = (laatste_d - eerste_d).days + 1
    ontbrekend = max(verwacht - rij[2], 0)
    return (str(rij[0]), str(rij[1]), rij[2], ontbrekend)


def get_gasdata_dagen_voor_periode(datum_start, datum_eind, tuin_id=None):
    """Losse dagregels (datum, gas_m3_totaal, gas_mj_totaal, gas_mj_per_m2) voor grafieken."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, gas_m3_totaal, gas_mj_totaal, gas_mj_per_m2
            FROM gasdata_dag
            WHERE tuin_id = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (_tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_gasdata_dekking(tuin_id=None):
    """(eerste_datum, laatste_datum, aantal_dagen) of None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(datum), MAX(datum), COUNT(*) FROM gasdata_dag WHERE tuin_id = %s",
                       (_tuin_of_standaard(tuin_id),))
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    return (str(rij[0]), str(rij[1]), rij[2])


def get_warmte_voor_periode(vaknummer, datum_start, datum_eind, tuin_id=None):
    """
    Geeft het totale warmteverbruik (MJ) van één vak binnen een periode terug
    — Pulsteller-warmte plus (in weken met bijstook) gasgestookte warmte
    opgeteld — berekend als de kaswaarde per m2 per dag keer de oppervlakte
    van dat vak. Geeft None als er geen data of geen bekende oppervlakte is.
    """
    oppervlakte = oppervlakte_van_vaknummer(vaknummer)
    if not oppervlakte:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(totaal), COUNT(*)
            FROM (
                SELECT datum, SUM(mj_per_m2) AS totaal
                FROM (
                    SELECT datum, warmte_mj_per_m2 AS mj_per_m2
                    FROM energiedata_dag WHERE tuin_id = %s AND datum BETWEEN %s AND %s
                    UNION ALL
                    SELECT datum, gas_mj_per_m2 AS mj_per_m2
                    FROM gasdata_dag WHERE tuin_id = %s AND datum BETWEEN %s AND %s
                ) per_bron
                GROUP BY datum
            ) per_dag
        """, (_tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind),
              _tuin_of_standaard(tuin_id), str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[1] == 0:
        return None
    return {"totaal_mj": (rij[0] or 0.0) * oppervlakte, "aantal_dagen": rij[1]}


def get_klimaat_voor_periode(afdeling, datum_start, datum_eind, tuin_id=None):
    """
    Geeft de gemiddelde temperatuur, gemiddelde RV en gemiddelde dagstralingssom
    terug over alle opgeslagen dagen binnen de opgegeven periode (bijv. de
    looptijd van een teelt). Geeft None terug als er geen data is.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(gem_temperatuur), AVG(gem_rv), AVG(stralingssom_dag)
            FROM klimaatdata_dag
            WHERE tuin_id = %s AND afdeling = %s AND datum BETWEEN %s AND %s
        """, (_tuin_of_standaard(tuin_id), afdeling, str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    return {"gem_temperatuur": rij[0], "gem_rv": rij[1], "gem_stralingssom_dag": rij[2]}


def get_klimaatdata_dagen_voor_periode(afdeling, datum_start, datum_eind, tuin_id=None):
    """
    Geeft de losse dagregels terug (voor grafieken) binnen de opgegeven
    periode, gesorteerd op datum. Retourneert een lijst van tuples
    (datum, gem_temperatuur, gem_rv, stralingssom_dag,
    gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, gem_temperatuur, gem_rv, stralingssom_dag,
                   gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht
            FROM klimaatdata_dag
            WHERE tuin_id = %s AND afdeling = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (_tuin_of_standaard(tuin_id), afdeling, str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_klimaatdata_dekking(tuin_id=None):
    """
    Geeft per afdeling terug tot welke dag er klimaatdata is geimporteerd:
    (afdeling, eerste_datum, laatste_datum, aantal_dagen, ontbrekende_dagen).
    ontbrekende_dagen = het aantal kalenderdagen tussen eerste en laatste dag
    waarvoor geen rij bestaat (gaten in de import). Gesorteerd op afdeling.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT afdeling, MIN(datum), MAX(datum), COUNT(*)
            FROM klimaatdata_dag
            WHERE tuin_id = %s
            GROUP BY afdeling
            ORDER BY afdeling
        """, (_tuin_of_standaard(tuin_id),))
        rijen = cursor.fetchall()

    resultaat = []
    for afdeling, eerste, laatste, aantal in rijen:
        eerste_d = datetime.strptime(str(eerste), "%Y-%m-%d").date()
        laatste_d = datetime.strptime(str(laatste), "%Y-%m-%d").date()
        verwacht = (laatste_d - eerste_d).days + 1
        ontbrekend = max(verwacht - aantal, 0)
        resultaat.append((afdeling, str(eerste), str(laatste), aantal, ontbrekend))
    return resultaat


def get_klimaat_overzicht_dataframe():
    """
    Koppelt de opgeslagen klimaatdata aan elke teelt (via vaknummer ->
    afdeling en de teeltperiode) en geeft kolommen + rijen terug voor
    weergave in het dashboard. Teelten zonder overlappende klimaatdata worden
    overgeslagen.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.code, v.naam, v.vaknummer, t.datum_teelt_start, t.datum_oogst
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            ORDER BY (t.code IS NULL), t.code
        """)
        teelt_rijen = cursor.fetchall()

    rijen = []
    for teelt_id, code, naam, vaknummer, start, oogst in teelt_rijen:
        afdeling = afdeling_van_vaknummer(vaknummer)
        if not afdeling:
            continue

        eind = oogst or str(date.today())
        klimaat = get_klimaat_voor_periode(afdeling, start, eind)
        if not klimaat:
            continue

        water = get_watergift_voor_periode(vaknummer, start, eind) if vaknummer else None
        warmte = get_warmte_voor_periode(vaknummer, start, eind) if vaknummer else None

        ideaal = ideale_etmaaltemperatuur(klimaat["gem_stralingssom_dag"])
        if ideaal is not None and klimaat["gem_temperatuur"] is not None:
            verschil = klimaat["gem_temperatuur"] - ideaal
            if verschil > 0.3:
                verschil_tekst = f"↑ +{verschil:.1f}"
            elif verschil < -0.3:
                verschil_tekst = f"↓ {verschil:.1f}"
            else:
                verschil_tekst = f"≈ {verschil:+.1f}"
        else:
            verschil_tekst = "-"

        rijen.append((
            code if code else f"ID{teelt_id}",
            naam,
            afdeling,
            format_datum(start),
            format_datum(oogst) if oogst else "lopend",
            round(klimaat["gem_temperatuur"], 1) if klimaat["gem_temperatuur"] is not None else "-",
            round(klimaat["gem_rv"], 1) if klimaat["gem_rv"] is not None else "-",
            round(klimaat["gem_stralingssom_dag"]) if klimaat["gem_stralingssom_dag"] is not None else "-",
            round(ideaal, 1) if ideaal is not None else "-",
            verschil_tekst,
            round(water["totaal_liter_per_m2"], 1) if water else "-",
            round(warmte["totaal_mj"] / 1000, 2) if warmte else "-",
        ))

    kolommen = ["Code", "Teeltvak", "Afdeling", "Startdatum", "Oogstdatum",
                "Gem. temperatuur (°C)", "Gem. RV (%)", "Gem. stralingssom (per dag)",
                "Ideale temp (°C)", "Verschil (°C)",
                "Totaal water (l/m²)", "Totaal warmte (GJ)"]
    return kolommen, rijen


# --- PLANNING (TOEKOMSTIGE TEELTEN) ---
#
# Geeft per plantweek (ISO-weeknummer 1-52) de verwachte teeltduur in weken,
# geldig voor de hele kas (niet per afdeling). Voorlopige tabel, aangeleverd
# 2026-09-04. Week 53 (niet elk jaar aanwezig) heeft bewust geen waarde.
TEELTDUUR_PER_PLANTWEEK = {
    1: 11.0, 2: 10.0, 3: 10.0, 4: 9.0, 5: 9.0, 6: 8.5, 7: 8.0, 8: 8.0, 9: 8.0, 10: 8.0,
    11: 7.0, 12: 7.0, 13: 7.0, 14: 7.0, 15: 7.0, 16: 7.0, 17: 7.0, 18: 7.0, 19: 7.0, 20: 7.0,
    21: 7.0, 22: 6.3, 23: 6.8, 24: 6.5, 25: 6.4, 26: 6.6, 27: 6.7, 28: 6.8, 29: 7.0, 30: 7.0,
    31: 7.0, 32: 7.2, 33: 7.8, 34: 8.3, 35: 9.0, 36: 9.4, 37: 9.6, 38: 10.3, 39: 10.8, 40: 11.6,
    41: 12.6, 42: 13.5, 43: 14.0, 44: 14.0, 45: 14.7, 46: 15.3, 47: 15.0, 48: 15.0, 49: 14.5,
    50: 14.0, 51: 14.0, 52: 13.0,
}

# Harde bovengrens: er kunnen nooit meer dan zoveel poot-eenheden in één week
# gepoot worden (arbeid/plantcapaciteit). Geldt ook boven een handmatig weekdoel.
MAX_VAKKEN_PER_WEEK = 5

# Vak 19 en 20 zijn qua formaat/aantal samen gelijk aan één regulier vak
# en worden daarom als één eenheid gepland (altijd dezelfde week).
VAK_GECOMBINEERD = (19, 20)

# Vak 1 loopt zelf op een ander ritme dan de rest en zou anders de hele
# vaste volgorde blokkeren tot het zover is; het wordt daarom apart
# ingepast in plaats van als eerste in de keten van vak 2..39.
VAK_VOLGORDE_UITZONDERING = 1


def teeltduur_voor_plantweek(week):
    """
    Geeft de verwachte teeltduur (in weken) voor een ISO-plantweek terug.
    ISO-week 53 (schrikkeljaren, eind december) staat niet apart in de tabel en
    valt terug op week 52. Geeft None als de week echt onbekend is.
    """
    if week == 53 and 53 not in TEELTDUUR_PER_PLANTWEEK:
        return TEELTDUUR_PER_PLANTWEEK.get(52)
    return TEELTDUUR_PER_PLANTWEEK.get(week)


def bereken_verwachte_oogstdatum(datum_start):
    """
    Berekent de verwachte oogstdatum op basis van de teeltduur-per-plantweek-
    tabel. De teeltduur wordt lineair geïnterpoleerd tussen de plantweek en de
    week erna aan de hand van de weekdag, zodat de oogstdatum geleidelijk
    opschuift i.p.v. met sprongen per week. De oogst valt nooit op za/zo (dan de
    vrijdag ervoor). Geeft (verwachte_duur_weken, verwachte_oogstdatum) terug, of
    (None, None) als de plantweek niet in de tabel staat.
    """
    if isinstance(datum_start, str):
        datum_start = datetime.strptime(datum_start, "%Y-%m-%d").date()
    d0 = teeltduur_voor_plantweek(get_weeknummer(datum_start))
    if d0 is None:
        return None, None
    d1 = teeltduur_voor_plantweek(get_weeknummer(datum_start + timedelta(days=7)))
    frac = datum_start.weekday() / 7.0
    duur_weken = d0 + (d1 - d0) * frac if d1 is not None else d0
    oogst = datum_start + timedelta(days=round(duur_weken * 7))
    while oogst.weekday() > 4:  # za/zo -> vrijdag ervoor
        oogst -= timedelta(days=1)
    return round(duur_weken, 2), oogst


def _harde_bodem_vak(vaknummer):
    """
    Geeft de harde ondergrens voor een vak terug: de oogstdatum van de meest
    recente teelt (werkelijk als al afgerond, anders de via de teeltduur-tabel
    verwachte oogstdatum). Een vak kan nooit eerder dan dit gepland worden — de
    vorige teelt staat er dan immers nog. Zónder wisseltijd. Geeft None terug
    als het vak nog geen teeltgeschiedenis heeft.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.datum_teelt_start, t.datum_oogst
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.vaknummer = %s AND v.tuin_id = %s
            ORDER BY t.datum_teelt_start DESC LIMIT 1
        """, (vaknummer, get_tuin_id(STANDAARD_TUIN)))
        rij = cursor.fetchone()

    if not rij:
        return None

    start, oogst = rij
    if oogst:
        return datetime.strptime(oogst, "%Y-%m-%d").date()
    _, verwacht = bereken_verwachte_oogstdatum(start)
    return verwacht


def _laatste_concept_oogst(vaknummer):
    """Verwachte oogstdatum van de laatste concept-planning van dit vak, of None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(verwachte_oogstdatum) FROM teeltplanning
            WHERE vaknummer = %s AND tuin_id = %s AND verwachte_oogstdatum IS NOT NULL
        """, (vaknummer, get_tuin_id(STANDAARD_TUIN)))
        rij = cursor.fetchone()
    if rij and rij[0]:
        return datetime.strptime(rij[0], "%Y-%m-%d").date()
    return None


def _bodem_incl_concept(vaknummer):
    """
    Harde ondergrens voor de volgende teeltronde van een vak: de laatste van
    (a) de oogst van de laatste echte teelt en (b) de verwachte oogst van de
    laatste concept-planning. Zo kan er meerdere rondes vooruit gepland worden:
    elke ronde schuift de bodem op naar de oogst van de zojuist geplande ronde.
    """
    echt = _harde_bodem_vak(vaknummer)
    concept = _laatste_concept_oogst(vaknummer)
    if echt is None:
        return concept
    if concept is None:
        return echt
    return max(echt, concept)


def _maandag(datum):
    """De maandag van de week waarin `datum` valt (date-object)."""
    if isinstance(datum, str):
        datum = datetime.strptime(datum, "%Y-%m-%d").date()
    return datum - timedelta(days=datum.weekday())


def get_instelling(sleutel, standaard=None):
    """Leest een app-instelling (sleutel/waarde). Geeft `standaard` als hij er niet is."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT waarde FROM app_instelling WHERE sleutel = %s", (sleutel,))
        rij = cursor.fetchone()
    return rij[0] if rij and rij[0] is not None else standaard


def set_instelling(sleutel, waarde, gebruiker=None):
    """Zet of wist (waarde None) een app-instelling."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if waarde is None:
            cursor.execute("DELETE FROM app_instelling WHERE sleutel = %s", (sleutel,))
        else:
            cursor.execute("""
                INSERT INTO app_instelling (sleutel, waarde) VALUES (%s, %s)
                ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde
            """, (sleutel, str(waarde)))
        conn.commit()
    log_wijziging(gebruiker, "gewijzigd", "app_instelling", sleutel,
                  f"{sleutel} = {waarde}" if waarde is not None else f"{sleutel} gewist")


def get_planning_besteld_tot():
    """
    Datum (date) t/m wanneer de planten besteld zijn: concept-planningen met
    startdatum t/m deze datum staan vast. Geeft None als er niets is ingesteld.
    """
    waarde = get_instelling("planning_besteld_tot")
    if not waarde:
        return None
    try:
        return datetime.strptime(waarde, "%Y-%m-%d").date()
    except ValueError:
        return None


def set_planning_besteld_tot(datum, gebruiker=None):
    set_instelling("planning_besteld_tot",
                   datum.isoformat() if datum else None, gebruiker=gebruiker)


def get_planning_weekdoelen(tuin_id=None):
    """
    Handmatig ingevulde jaarplanning per plantweek. Geeft
    {week_start (maandag-date): {"aantal_vakken": int of None,
    "vak1_planten": bool}} terug. Een week zonder rij (of met
    aantal_vakken=None) betekent: geen streefaantal ingevuld voor de
    vak 2-39-cyclus die week.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT week_start, aantal_vakken, vak1_planten FROM planning_weekdoel WHERE tuin_id = %s",
            (_tuin_of_standaard(tuin_id),),
        )
        return {
            datetime.strptime(w, "%Y-%m-%d").date(): {
                "aantal_vakken": int(a) if a is not None else None,
                "vak1_planten": bool(v1),
            }
            for w, a, v1 in cursor.fetchall()
        }


def set_planning_weekdoel(week_start, aantal_vakken, gebruiker=None, tuin_id=None):
    """
    Zet (of wist bij aantal_vakken=None) het handmatige streefaantal
    poot-eenheden (vak 2-39-cyclus) voor de plantweek waarin `week_start`
    valt. Laat een eventuele vak1_planten-vlag voor die week ongemoeid.
    """
    week = _maandag(week_start)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO planning_weekdoel (tuin_id, week_start, aantal_vakken)
            VALUES (%s, %s, %s)
            ON CONFLICT (tuin_id, week_start) DO UPDATE SET aantal_vakken = EXCLUDED.aantal_vakken
        """, (_tuin_of_standaard(tuin_id), str(week),
              int(aantal_vakken) if aantal_vakken is not None else None))
        conn.commit()
    log_wijziging(
        gebruiker, "gewijzigd", "planning_weekdoel", str(week),
        f"Streefaantal gezet op {aantal_vakken}" if aantal_vakken is not None
        else "Streefaantal gewist"
    )


def set_planning_weekdoel_vak1(week_start, vak1_planten, gebruiker=None, tuin_id=None):
    """
    Zet of vak 1 in de plantweek waarin `week_start` valt gepoot moet
    worden. Laat een eventueel streefaantal voor die week ongemoeid.
    """
    week = _maandag(week_start)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO planning_weekdoel (tuin_id, week_start, vak1_planten)
            VALUES (%s, %s, %s)
            ON CONFLICT (tuin_id, week_start) DO UPDATE SET vak1_planten = EXCLUDED.vak1_planten
        """, (_tuin_of_standaard(tuin_id), str(week), bool(vak1_planten)))
        conn.commit()
    log_wijziging(
        gebruiker, "gewijzigd", "planning_weekdoel", str(week),
        f"Vak 1 {'wel' if vak1_planten else 'niet'} gepland die week"
    )


def wis_planning_weekdoelen(gebruiker=None, tuin_id=None):
    """Wist de hele handmatig ingevulde jaarplanning (streefaantallen en vak1-vlaggen)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM planning_weekdoel WHERE tuin_id = %s",
                       (_tuin_of_standaard(tuin_id),))
        conn.commit()
    log_wijziging(gebruiker, "verwijderd", "planning_weekdoel", None,
                  "Alle handmatige weekstreefaantallen gewist")


def get_planning_weekoverzicht(aantal_weken=8, tuin_id=None):
    """
    Per plantweek vanaf deze week t/m de horizon een dict met:
      week_start (maandag-date), jaar, week (ISO), concepten (aantal
      concept-planningen die week voor de vak 2-39-cyclus, in poot-eenheden:
      vak 19+20 telt als 1, vak 1 telt hier niet in mee), weekdoel
      (handmatig ingevuld streefaantal voor die cyclus, of None),
      vak1_planten (handmatig ingevulde vlag of vak 1 die week gepoot moet
      worden).
    Voedt de "vakken per week"-invoertabel in de planningsmodule.
    """
    maandag_nu = _maandag(date.today())
    weekdoelen = get_planning_weekdoelen(tuin_id)

    concept_vak_per_week = {}
    for _pid, vaknummer, start, _d, _e, _n in get_planning(tuin_id):
        w = _maandag(start)
        concept_vak_per_week.setdefault(w, []).append(vaknummer)

    concept_per_week = {}
    for w, vakken in concept_vak_per_week.items():
        vakken_zonder_1 = [v for v in vakken if v != VAK_VOLGORDE_UITZONDERING]
        aantal = len(vakken_zonder_1)
        if VAK_GECOMBINEERD[0] in vakken_zonder_1 and VAK_GECOMBINEERD[1] in vakken_zonder_1:
            aantal -= 1  # 19+20 samen = 1 poot-eenheid
        concept_per_week[w] = aantal

    resultaat = []
    for i in range(max(1, aantal_weken)):
        w = maandag_nu + timedelta(weeks=i)
        jaar, week, _ = w.isocalendar()
        doel = weekdoelen.get(w, {})
        resultaat.append({
            "week_start": w,
            "jaar": jaar,
            "week": week,
            "concepten": concept_per_week.get(w, 0),
            "weekdoel": doel.get("aantal_vakken"),
            "vak1_planten": doel.get("vak1_planten", False),
        })
    return resultaat


def voeg_planning_toe(vaknummer, verwachte_startdatum, notitie=None, gebruiker=None, tuin_id=None):
    """Maakt een concept-planningsregel aan voor een vak; duur/oogst worden automatisch berekend."""
    duur_weken, eind = bereken_verwachte_oogstdatum(verwachte_startdatum)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teeltplanning (tuin_id, vaknummer, verwachte_startdatum, verwachte_duur_weken, verwachte_oogstdatum, notitie)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (_tuin_of_standaard(tuin_id), vaknummer, str(verwachte_startdatum), duur_weken,
              str(eind) if eind else None, notitie))
        planning_id = cursor.fetchone()[0]
        conn.commit()

    log_wijziging(
        gebruiker, "aangemaakt", "planning", planning_id,
        f"Concept-planning vak {vaknummer}, start {verwachte_startdatum}"
        + (f", verwachte oogst {eind}" if eind else "")
    )
    return planning_id


def wijzig_planning(planning_id, nieuwe_startdatum, gebruiker=None):
    """Past de startdatum van een concept-planningsregel aan; duur/oogst worden herberekend."""
    duur_weken, eind = bereken_verwachte_oogstdatum(nieuwe_startdatum)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teeltplanning
            SET verwachte_startdatum = %s, verwachte_duur_weken = %s, verwachte_oogstdatum = %s
            WHERE id = %s
        """, (str(nieuwe_startdatum), duur_weken, str(eind) if eind else None, planning_id))
        conn.commit()

    log_wijziging(
        gebruiker, "gewijzigd", "planning", planning_id,
        f"Startdatum aangepast naar {nieuwe_startdatum}" + (f", verwachte oogst {eind}" if eind else "")
    )


def get_planning(tuin_id=None):
    """
    Geeft alle concept-planningsregels terug, gesorteerd op startdatum (dus
    chronologisch/per week) en bij een gelijke datum op vaknummer.
    Retourneert een lijst van tuples:
    (id, vaknummer, verwachte_startdatum, verwachte_duur_weken, verwachte_oogstdatum, notitie)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, vaknummer, verwachte_startdatum, verwachte_duur_weken, verwachte_oogstdatum, notitie
            FROM teeltplanning
            WHERE tuin_id = %s
            ORDER BY verwachte_startdatum, vaknummer
        """, (_tuin_of_standaard(tuin_id),))
        return cursor.fetchall()


def get_planning_per_week(tuin_id=None):
    """
    Groepeert alle concept-planningen per plantweek (iso-jaar + weeknummer
    van verwachte_startdatum), met de vaknummers in oplopende volgorde per
    week. Geeft een lijst van tuples (jaar, week, [vaknummers], arbeidsaantal)
    terug, gesorteerd op jaar/week. Het arbeidsaantal is het aantal vakken
    dat voor de arbeidsplanning telt: vak 19+20 samen tellen daarin als 1
    (net als bij het maken van de planning), ook al staan ze allebei apart
    in de vakkenlijst.
    """
    rijen = get_planning(tuin_id)
    groepen = {}
    for _planning_id, vaknummer, start, _duur, _eind, _notitie in rijen:
        sleutel = get_isojaar_week(start)
        groepen.setdefault(sleutel, []).append(vaknummer)

    resultaat = []
    for jaar, week in sorted(groepen.keys()):
        vakken = sorted(groepen[(jaar, week)])
        arbeidsaantal = len(vakken)
        if VAK_GECOMBINEERD[0] in vakken and VAK_GECOMBINEERD[1] in vakken:
            arbeidsaantal -= 1
        resultaat.append((jaar, week, vakken, arbeidsaantal))
    return resultaat


def verwijder_planning(planning_id, gebruiker=None):
    """Verwijdert een concept-planningsregel (zonder gevolgen voor eventuele echte teelten)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM teeltplanning WHERE id = %s", (planning_id,))
        conn.commit()
    log_wijziging(gebruiker, "verwijderd", "planning", planning_id, "Concept-planning verwijderd")


def bevestig_planning(planning_id, aantal_planten=None, gebruiker=None):
    """
    Zet een concept-planningsregel om in een echte teelt-registratie (via
    start_nieuwe_teelt) en verwijdert daarna de planningsregel. Geeft
    (teelt_id, code) terug, of None als de planningsregel niet bestaat.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT vaknummer, verwachte_startdatum, tuin_id FROM teeltplanning WHERE id = %s",
            (planning_id,),
        )
        rij = cursor.fetchone()

    if not rij:
        return None

    # De tuin komt uit de planningsregel zelf, niet uit de actieve tuin: zo komt
    # de teelt altijd in de tuin waarvoor het concept gemaakt is.
    vaknummer, verwachte_startdatum, planning_tuin = rij
    teelt_id, code = start_nieuwe_teelt(vaknummer, verwachte_startdatum, aantal_planten,
                                        gebruiker=gebruiker, tuin_id=planning_tuin)
    verwijder_planning(planning_id, gebruiker=gebruiker)
    return teelt_id, code


def plan_x_weken_vooruit(aantal_weken, gebruiker=None, verwijder_bestaande=False):
    """
    Plant vakken tot `aantal_weken` weken vooruit als één doorlopende cyclus
    2, 3, ..., 39, 2, ... (met 19+20 als één eenheid), strikt in die volgorde.
    Het streefaantal per week komt volledig uit de handmatig ingevulde
    jaarplanning (planning_weekdoel): een week zonder ingevuld aantal plant
    niets voor deze cyclus, en een ingevuld aantal wordt altijd letterlijk
    gehaald (zolang er nog vakken in de cyclus zitten) — ook als dat betekent
    dat een vak een nieuwe ronde begint vóór de oogst van z'n vorige ronde in
    hetzelfde plan (overlap is toegestaan, op Jobs verzoek sept 2026: de
    teler regelt dat zelf, de app hoeft niet op teeltduur te wachten). Vak 1 loopt op zijn
    eigen ritme, los van de cyclus, en wordt alleen gepland in de weken die
    daarvoor zijn aangevinkt (vak1_planten) — kan dat niet (nog niet
    geoogst, of de week zit al vol), dan schuift het door naar de eerste
    week erna die wel kan.

    verwijder_bestaande=True wist alle bestaande concepten en plant helemaal
    opnieuw (zodat een bewerkte jaarplanning altijd letterlijk wordt
    overgenomen, zonder oude concepten die in de weg zitten). Zonder de
    vlag blijven alle concepten staan en wordt er alleen achteraan bijgepland.

    Geeft (resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen):
    - resultaten: [(vaknummer, 'gepland'|'geen_geschiedenis'|'buiten_horizon',
      eerste_startdatum)];
    - weekdoel_waarschuwingen: [(week_start, gevraagd, geplant)] voor niet
      gehaalde weekdoelen;
    - vak1_waarschuwingen: [(week_gevraagd, week_gepland)] voor vak1-weken
      die niet in de gevraagde week zelf gepland konden worden;
      week_gepland is None als het zelfs niet binnen de horizon paste.
    """
    # Deze planner rekent met de vakindeling van tuin 3 (de cyclus 2 t/m 39, met
    # 19+20 als één eenheid en vak 1 op een eigen ritme). Voor een andere tuin
    # klopt die volgorde niet, dus daar plan je voorlopig met de hand.
    if get_actieve_tuin() != get_tuin_id(STANDAARD_TUIN):
        raise ValueError(f"Automatisch plannen kan alleen voor tuin {STANDAARD_TUIN}.")

    if verwijder_bestaande:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM teeltplanning WHERE tuin_id = %s",
                           (get_tuin_id(STANDAARD_TUIN),))
            conn.commit()
        log_wijziging(
            gebruiker, "verwijderd", "planning", None,
            "Concept-planningen gewist om opnieuw te plannen")

    ruwe_weekdoelen = get_planning_weekdoelen()
    weekdoelen = {
        w: min(MAX_VAKKEN_PER_WEEK, d["aantal_vakken"])
        for w, d in ruwe_weekdoelen.items() if d["aantal_vakken"] is not None
    }
    vak1_weken = {w for w, d in ruwe_weekdoelen.items() if d["vak1_planten"]}
    vandaag = date.today()
    horizon_eind = vandaag + timedelta(weeks=aantal_weken)
    gecombineerd_laag, gecombineerd_hoog = VAK_GECOMBINEERD
    geen_geschiedenis = set()

    # Cyclus-eenheden vak 2..39 (19+20 samen). Vak 1 apart, zie onder.
    eenheden = []  # (representatief_vaknummer, [vakken])
    for v in range(2, 40):
        if v == gecombineerd_hoog:
            continue
        if v == gecombineerd_laag:
            eenheden.append((gecombineerd_laag, [gecombineerd_laag, gecombineerd_hoog]))
        else:
            eenheden.append((v, [v]))

    # Oogstfront per eenheid = oogst laatste echte teelt of laatste concept.
    front = {}
    for rep, vakken in eenheden:
        obs = [_bodem_incl_concept(v) for v in vakken]
        if any(o is None for o in obs):
            geen_geschiedenis.update(vakken)
        else:
            front[rep] = max(obs)
    bruikbaar = [e for e in eenheden if e[0] in front]
    if not bruikbaar:
        return _planresultaat(weekdoelen, geen_geschiedenis, [])
    reps = [e[0] for e in bruikbaar]

    # Cyclus-startpunt: het vak met het vroegste oogstfront.
    start_rep = min(bruikbaar, key=lambda e: (front[e[0]], e[0]))[0]
    si = reps.index(start_rep)
    cyclus = bruikbaar[si:] + bruikbaar[:si]

    def _cap(week):
        """Streefaantal voor deze week: alleen wat handmatig is ingevuld, anders 0."""
        return weekdoelen.get(week, 0)

    # Twee tellers: 'cyclus' (alleen vak 2-39) toetst aan _cap (zijn eigen
    # ingevulde aantal, onaangetast door vak 1), 'totaal' (cyclus + vak 1)
    # toetst aan MAX_VAKKEN_PER_WEEK — de fysieke bovengrens. Zo gaat vak 1
    # nooit ten koste van het ingevulde cyclus-aantal, maar samen nooit over
    # de fysieke weekgrens heen.
    week_teller_cyclus = {}
    week_teller_totaal = {}
    laatste_week = None
    sweep_vanaf = vandaag

    earliest = {}  # planning_id -> vroegste plantdatum (voor de dagverdeling)

    def _kies_week(vroegst, teller, cap_fn):
        """Zoekt de eerstvolgende maandag-week vanaf `vroegst` die volgens
        `teller`/`cap_fn` niet vol zit en een ma–do-dag heeft die ≥ `vroegst`
        ligt. Normaal begint een week met een planting op maandag; kan de
        eerste eenheid van een week niet op maandag starten (bodem valt
        later), dan mag die week toch beginnen op di/wo/do i.p.v. een hele
        week niet te planten. Bumpt nooit terug vóór `laatste_week`, zodat
        cyclus en vak 1 chronologisch door elkaar heen blijven lopen."""
        nonlocal laatste_week
        vroegst = max(vroegst, sweep_vanaf)
        week = _maandag(vroegst)
        if laatste_week is not None and week < laatste_week:
            week = laatste_week
        for _ in range(520):
            bezet = teller.get(week, 0)
            if bezet < cap_fn(week) and vroegst <= week + timedelta(days=3):
                break
            week += timedelta(days=7)
        laatste_week = week
        return week

    def _plaats(vakken, vroegst):
        """Plaatst een cyclus-eenheid (vak 2-39); geeft de maandag terug, de
        exacte dag ma→do volgt in _naverwerk_planning."""
        week = _kies_week(vroegst, week_teller_cyclus, _cap)
        week_teller_cyclus[week] = week_teller_cyclus.get(week, 0) + 1
        week_teller_totaal[week] = week_teller_totaal.get(week, 0) + 1
        return week

    def _plaats_vak1(vroegst):
        """Plaatst vak 1, tegen de fysieke weekgrens (MAX_VAKKEN_PER_WEEK)
        i.p.v. het ingevulde cyclus-aantal — telt niet mee voor _cap."""
        week = _kies_week(vroegst, week_teller_totaal, lambda _w: MAX_VAKKEN_PER_WEEK)
        week_teller_totaal[week] = week_teller_totaal.get(week, 0) + 1
        return week

    vak1_front = _bodem_incl_concept(VAK_VOLGORDE_UITZONDERING)
    if vak1_front is None:
        geen_geschiedenis.add(VAK_VOLGORDE_UITZONDERING)

    # Vak 1 wordt alleen gepland in de weken die daarvoor zijn aangevinkt
    # (vak1_weken), op volgorde — letterlijk, ook als dat een nieuwe ronde
    # vóór de oogst van de vorige oplevert (overlap toegestaan).
    vak1_wachtrij = sorted(w for w in vak1_weken if w <= horizon_eind)
    vak1_idx = 0
    vak1_waarschuwingen = []

    def _verwerk_vak1(week_gevraagd):
        nonlocal vak1_front
        if vak1_front is None:
            return None
        vroegst1 = max(week_gevraagd, sweep_vanaf)
        if _maandag(vroegst1) > horizon_eind:
            vak1_waarschuwingen.append((week_gevraagd, None))
            return None
        d1 = _plaats_vak1(vroegst1)
        if d1 > horizon_eind:
            vak1_waarschuwingen.append((week_gevraagd, None))
            return None
        pid = voeg_planning_toe(VAK_VOLGORDE_UITZONDERING, d1, gebruiker=gebruiker)
        earliest[pid] = vroegst1
        if d1 != week_gevraagd:
            vak1_waarschuwingen.append((week_gevraagd, d1))
        _, o1 = bereken_verwachte_oogstdatum(d1)
        vak1_front = o1 or (d1 + timedelta(weeks=13))
        return d1

    # Doorlopende sweep langs de cyclus. Elke eenheid komt strikt op z'n
    # beurt aan de rand; niet meer gewacht op de oogst van de vorige ronde
    # van diezelfde eenheid (overlap toegestaan, zie docstring) — alleen de
    # cyclusvolgorde (vorige_datum) en het ingevulde weekaantal (_cap) tellen.
    pos = 0
    vorige_datum = None
    for _ in range(4000):
        rep, vakken = cyclus[pos % len(cyclus)]
        vroegst = max(vorige_datum, sweep_vanaf) if vorige_datum is not None else sweep_vanaf
        if _maandag(vroegst) > horizon_eind:
            break
        datum = _plaats(vakken, vroegst)
        if datum > horizon_eind:
            break
        for v in vakken:
            pid = voeg_planning_toe(v, datum, gebruiker=gebruiker)
            earliest[pid] = vroegst
        vorige_datum = datum

        # Aangevinkte vak1-weken verwerken zodra de sweep ze bereikt heeft.
        while vak1_idx < len(vak1_wachtrij) and vak1_wachtrij[vak1_idx] <= vorige_datum + timedelta(days=3):
            d1 = _verwerk_vak1(vak1_wachtrij[vak1_idx])
            vak1_idx += 1
            if d1 is not None and d1 > vorige_datum:
                vorige_datum = d1

        pos += 1

    # Eventuele vak1-weken die de sweep niet meer bereikte (bijv. horizon-rand).
    while vak1_idx < len(vak1_wachtrij):
        _verwerk_vak1(vak1_wachtrij[vak1_idx])
        vak1_idx += 1

    _naverwerk_planning(earliest)
    return _planresultaat(weekdoelen, geen_geschiedenis, vak1_waarschuwingen)


def _naverwerk_planning(earliest=None):
    """
    Naverwerking van de hele concept-planning, per maandag-week in
    cyclusvolgorde (= id-volgorde van de sweep):
    - dagverdeling ma→do: t/m 4 op ma/di/wo/do, meer eerst de maandag dubbel,
      dan de dinsdag, enz.; nooit vr/za/zo. Een vak nooit vóór zijn eigen
      vroegste dag (`earliest`); een nieuwe ronde in hetzelfde vak mag wél
      vóór de oogst van de vorige ronde vallen (overlap toegestaan). Kan de
      eerste planting van een week niet op maandag (bodem valt later), dan mag
      die week op di/wo/do beginnen i.p.v. helemaal over te slaan. Nooit meer
      dan MAX_VAKKEN_PER_WEEK eenheden per week; het teveel schuift door.
    - teeltduur per concrete plantdag geïnterpoleerd tussen plantweek en week
      erna op weekdag (zelfde methode als bereken_verwachte_oogstdatum);
    - verwachte oogstdatum op ma–vr (weekend → vrijdag ervoor) en monotoon in
      cyclusvolgorde (altijd in dezelfde volgorde geoogst als geplant). Vak 1
      loopt op een eigen ritme en telt niet mee in die keten.
    """
    earliest = earliest or {}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, vaknummer, verwachte_startdatum FROM teeltplanning "
                       "WHERE tuin_id = %s ORDER BY id", (get_tuin_id(STANDAARD_TUIN),))
        rijen = cursor.fetchall()

    per_week = {}
    for pid, vak, s in rijen:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        per_week.setdefault(_maandag(d), []).append((pid, vak))

    # Voor vak 1: de maandag van de eerstvolgende vak-1-planting, zodat z'n
    # oogst daar nooit overheen loopt.
    vak1_maandagen = [_maandag(datetime.strptime(s, "%Y-%m-%d").date())
                      for pid, vak, s in rijen if vak == VAK_VOLGORDE_UITZONDERING]
    vak1_volgende = {}
    v1p = [pid for pid, vak, _s in rijen if vak == VAK_VOLGORDE_UITZONDERING]
    for i, pid in enumerate(v1p):
        vak1_volgende[pid] = vak1_maandagen[i + 1] if i + 1 < len(vak1_maandagen) else None

    def _naar_werkdag(d):  # za/zo -> vrijdag ervoor (oogsten kan ma-vr)
        while d.weekday() > 4:
            d -= timedelta(days=1)
        return d

    def _naar_plantdag(d):  # vr/za/zo -> volgende maandag
        while d.weekday() > 3:
            d += timedelta(days=1)
        return d

    def _duur_voor(start):
        """Teeltduur voor een concrete plantdag: lineair geïnterpoleerd tussen de
        plantweek en de week erna op basis van de weekdag (zelfde methode als
        bereken_verwachte_oogstdatum, zodat de sweep-schatting en deze klopt)."""
        a = teeltduur_voor_plantweek(get_weeknummer(start))
        if a is None:
            return None
        b = teeltduur_voor_plantweek(get_weeknummer(start + timedelta(days=7)))
        return a + (b - a) * (start.weekday() / 7.0) if b is not None else a

    vorige_oogst = None
    nv_week = {}             # maandag -> aantal poot-eenheden (19+20 telt als 1)
    with get_connection() as conn:
        cursor = conn.cursor()
        for maandag in sorted(per_week):
            leden = per_week[maandag]
            n = len(leden)
            basis, rest = divmod(n, 4)
            offsets = [d for d in range(4) for _ in range(basis + (1 if d < rest else 0))]
            laatste_start = None
            for (pid, vak), offset in zip(leden, offsets):
                start = maandag + timedelta(days=offset)
                vr = earliest.get(pid)
                if vr is not None and start < vr:
                    start = _naar_plantdag(vr)
                # cyclusvolgorde binnen de week: nooit vóór de vorige planting
                # (dubbel op één dag mag wél, dat is de "maandag dubbel"-regel).
                if laatste_start is not None and start < laatste_start:
                    start = laatste_start
                # harde bovengrens: nooit meer dan MAX_VAKKEN_PER_WEEK eenheden
                # in één week; het teveel schuift naar de eerstvolgende week.
                if vak != VAK_GECOMBINEERD[1]:
                    while nv_week.get(_maandag(start), 0) >= MAX_VAKKEN_PER_WEEK:
                        start = _naar_plantdag(_maandag(start) + timedelta(days=7))
                    nv_week[_maandag(start)] = nv_week.get(_maandag(start), 0) + 1
                laatste_start = start
                duur = _duur_voor(start)
                if duur is None:
                    cursor.execute("UPDATE teeltplanning SET verwachte_startdatum = %s WHERE id = %s",
                                   (start.isoformat(), pid))
                    continue
                oogst = _naar_werkdag(start + timedelta(days=round(duur * 7)))
                if vak == VAK_VOLGORDE_UITZONDERING:
                    grens = vak1_volgende.get(pid)
                    if grens is not None and oogst >= grens:
                        oogst = grens - timedelta(days=1)
                        while oogst.weekday() > 4:  # terug naar vrijdag
                            oogst -= timedelta(days=1)
                else:
                    if vorige_oogst is not None and oogst <= vorige_oogst:
                        oogst = _naar_werkdag(vorige_oogst + timedelta(days=1))
                    vorige_oogst = oogst
                cursor.execute(
                    "UPDATE teeltplanning SET verwachte_startdatum = %s, verwachte_duur_weken = %s, "
                    "verwachte_oogstdatum = %s WHERE id = %s",
                    (start.isoformat(), round(duur, 2), oogst.isoformat(), pid))
        conn.commit()


def _planresultaat(weekdoelen, geen_geschiedenis, vak1_waarschuwingen=None):
    """
    Bouwt (resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen) op uit
    de uiteindelijke concept-planning in de database.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT vaknummer, verwachte_startdatum FROM teeltplanning WHERE tuin_id = %s",
                       (get_tuin_id(STANDAARD_TUIN),))
        rijen = cursor.fetchall()

    eerste_start = {}
    per_week = {}
    for vak, start in rijen:
        datum = datetime.strptime(start, "%Y-%m-%d").date()
        if vak not in eerste_start or datum < eerste_start[vak]:
            eerste_start[vak] = datum
        per_week.setdefault(_maandag(datum), []).append(vak)

    resultaten = []
    for vaknummer in range(1, 40):
        if vaknummer in eerste_start:
            resultaten.append((vaknummer, "gepland", eerste_start[vaknummer]))
        elif vaknummer in geen_geschiedenis:
            resultaten.append((vaknummer, "geen_geschiedenis", None))
        else:
            resultaten.append((vaknummer, "buiten_horizon", None))

    gecombineerd_laag, gecombineerd_hoog = VAK_GECOMBINEERD
    weekdoel_waarschuwingen = []
    for week, doel in sorted(weekdoelen.items()):
        vakken = [v for v in per_week.get(week, []) if v != VAK_VOLGORDE_UITZONDERING]
        aantal = len(vakken)
        if gecombineerd_laag in vakken and gecombineerd_hoog in vakken:
            aantal -= 1  # 19+20 samen = 1 poot-eenheid
        if aantal < doel:
            weekdoel_waarschuwingen.append((week, doel, aantal))

    return resultaten, weekdoel_waarschuwingen, vak1_waarschuwingen or []


def get_lege_vakken_per_week(aantal_weken=12):
    """
    Telt per week, vanaf de huidige week, hoeveel vakken geen actieve
    (werkelijke) teelt hebben lopen — dus hoeveel grond er leeg ligt.
    Kijkt alleen naar echte teelten, niet naar concept-planningen. Geeft
    een lijst van tuples (jaar, week, aantal_leeg, [vaknummers]) terug.
    """
    vandaag = date.today()
    start_week = vandaag - timedelta(days=vandaag.weekday())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.vaknummer, t.datum_teelt_start, t.datum_oogst
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
        """)
        rijen = cursor.fetchall()

    resultaat = []
    for i in range(aantal_weken):
        week_start = start_week + timedelta(weeks=i)
        week_eind = week_start + timedelta(days=6)

        bezet = set()
        for vak, start, oogst in rijen:
            start_datum = datetime.strptime(start, "%Y-%m-%d").date()
            oogst_datum = datetime.strptime(oogst, "%Y-%m-%d").date() if oogst else None
            if start_datum <= week_eind and (oogst_datum is None or oogst_datum >= week_start):
                bezet.add(vak)

        leeg = sorted(set(range(1, 40)) - bezet)
        jaar, week, _ = week_start.isocalendar()
        resultaat.append((jaar, week, len(leeg), leeg))

    return resultaat


def get_strokenplanning(weken_terug=8):
    """
    Bouwt de gegevens voor een strokenplanning (Gantt): per vak elke teelt
    en elke concept-planning als balk van startdatum tot (verwachte) oogst.

    Geeft een lijst dicts terug met: vaknummer, soort ('teelt'/'concept'),
    status ('afgerond'/'lopend'/'concept'), label (code of 'concept'),
    start (date), eind (date), teeltduur_weken (float, looptijd start→oogst).
    Teelten die meer dan `weken_terug` weken geleden zijn geoogst worden
    weggelaten; concept-planningen altijd getoond.
    """
    ondergrens = date.today() - timedelta(weeks=weken_terug)
    rijen = []

    def _duur_weken(start, eind):
        return round((eind - start).days / 7, 1)

    for t in get_alle_teelten_detail():
        start = datetime.strptime(t["datum_teelt_start"], "%Y-%m-%d").date()
        if t["datum_oogst"]:
            eind = datetime.strptime(t["datum_oogst"], "%Y-%m-%d").date()
            status = "afgerond"
        else:
            _, verwacht = bereken_verwachte_oogstdatum(t["datum_teelt_start"])
            eind = verwacht or (start + timedelta(weeks=8))
            status = "lopend"
        if eind < ondergrens:
            continue
        rijen.append({
            "vaknummer": t["vaknummer"],
            "soort": "teelt",
            "status": status,
            "label": t["code"] or f"ID{t['id']}",
            "start": start,
            "eind": eind,
            "teeltduur_weken": _duur_weken(start, eind),
        })

    for _pid, vaknummer, start, duur, eind, _notitie in get_planning():
        start_d = datetime.strptime(start, "%Y-%m-%d").date()
        eind_d = (
            datetime.strptime(eind, "%Y-%m-%d").date() if eind
            else start_d + timedelta(weeks=8)
        )
        rijen.append({
            "vaknummer": vaknummer,
            "soort": "concept",
            "status": "concept",
            "label": "concept",
            "start": start_d,
            "eind": eind_d,
            "teeltduur_weken": round(duur, 1) if duur else _duur_weken(start_d, eind_d),
        })

    rijen.sort(key=lambda r: (r["vaknummer"], r["start"]))
    return rijen



# --- STEKBEOORDELING ---
#
# Bij het poten wordt het geleverde stek beoordeeld; wekelijks gaat een overzicht
# naar de stekleverancier. Vroeger in Excel (blad Stek / Weekrapport).

STEK_PER_BAKJE = 600  # afgeleid uit de Excel-registratie: klopt voor alle Cameron-regels
STEK_KEUZES = {
    "wortel": ["Goed", "Redelijk", "Matig", "Slecht"],
    "plantmaat": ["Goed", "Redelijk", "Matig", "Klein", "Groot", "Slecht"],
    "uniformiteit": ["Goed", "Matig", "Slecht"],
}
STEK_VELDEN = ("ras", "bakjes", "wortel", "plantmaat", "uniformiteit", "beoordeling", "opmerking")
STEK_STANDAARD_RAS = "Cameron"


def stek_uitval_pct(aantal_planten, bakjes):
    """
    Uitval van het stek in %: het deel van de geleverde stekken (bakjes x 600)
    dat niet gepoot is. None als een van beide ontbreekt.
    """
    if not aantal_planten or not bakjes:
        return None
    geleverd = bakjes * STEK_PER_BAKJE
    return (geleverd - aantal_planten) / geleverd * 100


def get_stekweken(tuin_id=None):
    """Maandagen (date) van alle weken waarin een teelt gestart is, nieuwste eerst."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT t.datum_teelt_start
            FROM teelten t JOIN teeltvakken v ON v.id = t.teeltvak_id
            WHERE v.tuin_id = %s
        """, (_tuin_of_standaard(tuin_id),))
        startdatums = [r[0] for r in cursor.fetchall()]
    return sorted({_maandag(d) for d in startdatums}, reverse=True)


def get_stek_voor_week(maandag, tuin_id=None):
    """
    Alle teelten die gestart zijn in de week vanaf `maandag`, met hun
    stekbeoordeling (lege velden als die er nog niet is). Gesorteerd op
    datum en vak.
    """
    zondag = maandag + timedelta(days=6)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.datum_teelt_start, v.vaknummer, t.aantal_planten,
                   s.ras, s.bakjes, s.wortel, s.plantmaat, s.uniformiteit, s.beoordeling, s.opmerking
            FROM teelten t
            JOIN teeltvakken v ON v.id = t.teeltvak_id
            LEFT JOIN stekbeoordelingen s ON s.teelt_id = t.id
            WHERE v.tuin_id = %s AND t.datum_teelt_start BETWEEN %s AND %s
            ORDER BY t.datum_teelt_start, v.vaknummer
        """, (_tuin_of_standaard(tuin_id), str(maandag), str(zondag)))
        rijen = cursor.fetchall()
    return [
        {"teelt_id": r[0], "datum": r[1], "vaknummer": r[2], "aantal_planten": r[3],
         **dict(zip(STEK_VELDEN, r[4:]))}
        for r in rijen
    ]


def sla_stekbeoordeling_op(teelt_id, velden, gebruiker=None):
    """
    Slaat de stekbeoordeling van één teelt op (nieuw of bijwerken). `velden` is
    een dict met (een deel van) STEK_VELDEN. Logt alleen als er iets verandert.
    """
    waarden = {k: velden.get(k) for k in STEK_VELDEN}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(STEK_VELDEN)} FROM stekbeoordelingen WHERE teelt_id = %s", (teelt_id,)
        )
        oud = cursor.fetchone()
        if oud is not None and dict(zip(STEK_VELDEN, oud)) == waarden:
            return False
        cursor.execute(f"""
            INSERT INTO stekbeoordelingen (teelt_id, {', '.join(STEK_VELDEN)})
            VALUES (%s, {', '.join(['%s'] * len(STEK_VELDEN))})
            ON CONFLICT (teelt_id) DO UPDATE SET
                {', '.join(f'{k} = EXCLUDED.{k}' for k in STEK_VELDEN)}
        """, (teelt_id, *waarden.values()))
        conn.commit()
    log_wijziging(
        gebruiker, "aangemaakt" if oud is None else "gewijzigd", "stekbeoordeling", teelt_id,
        "Stekbeoordeling: " + ", ".join(f"{k} {v}" for k, v in waarden.items() if v not in (None, "")),
    )
    return True


def verdeel_bakjes(totaal_bakjes, planten_per_vak, stap=0.25):
    """
    Verdeelt het totaal geleverde aantal bakjes over de vakken naar rato van
    het aantal te poten planten (een half vak krijgt dus de helft), afgerond
    op `stap` bakjes. De restjes gaan naar de vakken die het meest zijn
    afgerond, zodat de som precies het totaal blijft.
    """
    totaal_planten = sum(p or 0 for p in planten_per_vak)
    if not totaal_bakjes or not totaal_planten:
        return [None] * len(planten_per_vak)

    exact = [totaal_bakjes * (p or 0) / totaal_planten for p in planten_per_vak]
    naar_beneden = [int(e / stap) * stap for e in exact]
    te_verdelen = round((totaal_bakjes - sum(naar_beneden)) / stap)
    volgorde = sorted(range(len(exact)), key=lambda i: exact[i] - naar_beneden[i], reverse=True)
    for i in volgorde[:te_verdelen]:
        naar_beneden[i] += stap
    return [round(b, 2) for b in naar_beneden]


# --- TEELTOVERZICHT ---

def get_teeltkengetallen(tuin_id=None):
    """
    Geeft per teelt de kengetallen die je naast elkaar wilt zien: klimaat
    (lichtsom en etmaaltemperatuur van de eigen afdeling), watergift van het
    vak, warmteverbruik van de kas en het oogstresultaat.

    Alles in één query: per teelt losse vragen stellen kost bij ruim 200
    teelten te veel tijd. De klimaat-, water- en energietellingen zeggen over
    hoeveel dagen het gaat, zodat de app een half gevulde periode kan herkennen
    (bijv. een teelt uit 2025, waarvan alleen het laatste stuk klimaatdata heeft).

    Een lopende teelt rekent t/m vandaag.
    """
    vandaag = str(date.today())
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            WITH basis AS (
                SELECT t.id, t.code, v.vaknummer, t.datum_teelt_start AS start,
                       t.datum_oogst,
                       COALESCE(t.datum_oogst, %s) AS eind,
                       t.aantal_planten, t.lengte_half, t.lengte_eind, t.oogstgewicht, t.rijpheid,
                       COALESCE(NULLIF(t.ras, ''), %s) AS ras,
                       v.tuin_id, v.afdeling
                FROM teelten t
                JOIN teeltvakken v ON v.id = t.teeltvak_id
                WHERE v.vaknummer IS NOT NULL AND v.tuin_id = %s
            )
            SELECT b.id, b.code, b.vaknummer, b.afdeling, b.start, b.datum_oogst, b.eind,
                   b.aantal_planten, b.lengte_half, b.lengte_eind, b.oogstgewicht, b.rijpheid, b.ras,
                   k.lichtsom, k.gem_temperatuur, k.dagen,
                   w.liters, w.dagen, w.excel_dagen,
                   e.mj_per_m2, e.dagen,
                   o.emmers
            FROM basis b
            LEFT JOIN LATERAL (
                SELECT SUM(stralingssom_dag) AS lichtsom, AVG(gem_temperatuur) AS gem_temperatuur,
                       COUNT(*) AS dagen
                FROM klimaatdata_dag k
                WHERE k.tuin_id = b.tuin_id AND k.afdeling = b.afdeling
                  AND k.datum BETWEEN b.start AND b.eind
            ) k ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(liter_per_m2) AS liters, COUNT(*) AS dagen,
                       COUNT(*) FILTER (WHERE bron = 'excel') AS excel_dagen
                FROM watergift_dag w
                WHERE w.tuin_id = b.tuin_id AND w.vaknummer = b.vaknummer
                  AND w.datum BETWEEN b.start AND b.eind
            ) w ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(mj) AS mj_per_m2, COUNT(*) AS dagen
                FROM (
                    SELECT datum, SUM(mj_per_m2) AS mj
                    FROM (
                        SELECT datum, warmte_mj_per_m2 AS mj_per_m2 FROM energiedata_dag
                        WHERE tuin_id = b.tuin_id AND datum BETWEEN b.start AND b.eind
                        UNION ALL
                        SELECT datum, gas_mj_per_m2 AS mj_per_m2 FROM gasdata_dag
                        WHERE tuin_id = b.tuin_id AND datum BETWEEN b.start AND b.eind
                    ) bronnen
                    GROUP BY datum
                ) per_dag
            ) e ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(aantal_emmers) AS emmers
                FROM oogstregistraties o WHERE o.teelt_id = b.id
            ) o ON TRUE
            ORDER BY b.start, b.vaknummer
        """, (vandaag, STANDAARD_RAS, _tuin_of_standaard(tuin_id)))
        rijen = cursor.fetchall()

    kengetallen = []
    for (teelt_id, code, vaknummer, afdeling, start, datum_oogst, eind, aantal_planten,
         lengte_half, lengte_eind, oogstgewicht, rijpheid, ras, lichtsom, gem_temperatuur,
         klimaatdagen, liters, waterdagen, water_excel_dagen, mj_per_m2, energiedagen,
         emmers) in rijen:
        looptijd = (datetime.strptime(eind, "%Y-%m-%d").date()
                    - datetime.strptime(start, "%Y-%m-%d").date()).days + 1
        isojaar, week = get_isojaar_week(start)
        kengetallen.append({
            "id": teelt_id, "code": code, "vaknummer": vaknummer, "afdeling": afdeling,
            "datum_teelt_start": start, "datum_oogst": datum_oogst,
            "plantjaar": isojaar, "plantweek": week, "looptijd_dagen": looptijd,
            "teeltduur": (datetime.strptime(datum_oogst, "%Y-%m-%d").date()
                          - datetime.strptime(start, "%Y-%m-%d").date()).days if datum_oogst else None,
            "aantal_planten": aantal_planten, "lengte_half": lengte_half,
            "lengte_eind": lengte_eind, "oogstgewicht": oogstgewicht, "rijpheid": rijpheid,
            "ras": ras,
            "stelen": (emmers or 0) * 100 if emmers else None,
            "lichtsom": lichtsom, "gem_temperatuur": gem_temperatuur,
            "klimaatdagen": klimaatdagen or 0,
            "liters": liters, "waterdagen": waterdagen or 0,
            "water_uit_excel": bool(water_excel_dagen),
            "warmte_mj_per_m2": mj_per_m2, "energiedagen": energiedagen or 0,
        })
    return kengetallen


# --- RASSEN (CULTIVARS) ---
#
# Vrijwel alles is Cameron; af en toe staat er een vak met een ander ras. Dat
# hoort apart herkenbaar te zijn, anders vervuilt het de teeltduur- en
# oogstvergelijkingen. Een lege ras-kolom betekent STANDAARD_RAS.

STANDAARD_RAS = "Cameron"


def get_rassen():
    """Alle rassen die in de teelten voorkomen, standaardras eerst."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ras FROM teelten WHERE ras IS NOT NULL AND ras <> '' ORDER BY ras")
        overige = [r[0] for r in cursor.fetchall()]
    return [STANDAARD_RAS] + [r for r in overige if r != STANDAARD_RAS]


def zet_ras(teelt_id, ras, gebruiker=None):
    """Zet (of wist) het ras van een bestaande teelt."""
    waarde = ras if ras and ras != STANDAARD_RAS else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE teelten SET ras = %s WHERE id = %s", (waarde, teelt_id))
        conn.commit()
    log_wijziging(gebruiker, "gewijzigd", "teelt", teelt_id, f"Ras gezet op {ras or STANDAARD_RAS}")


# --- TUINEN ---
#
# Tuin 3 (Hartweg 20) en tuin 1 (Hartweg 29). Tuin 3 is de standaard: alle
# gegevens van voor deze uitbreiding horen daarbij, en functies zonder tuin
# werken daarop verder.

STANDAARD_TUIN = 3
TUIN1_AFDELINGEN = {1: range(1, 8), 2: range(8, 14), 3: range(14, 21), 4: range(21, 28)}
TUIN1_STELEN_BIJ_60 = {1: 26532}   # vak 1 is een half vak
TUIN1_STELEN_STANDAARD = 53064     # vak 2 t/m 27


def _TUIN3_AFDELING(vaknummer):
    """Afdelingsindeling van tuin 3, zoals die eerder in afdeling_van_vaknummer stond."""
    return afdeling_van_vaknummer(vaknummer)


def _TUIN3_STELEN(vaknummer):
    """Aantal stelen bij 60 per m2 voor een vak van tuin 3 (halve vakken: 19, 20)."""
    vast = {1: 34000, 19: 15436, 20: 15436, 39: 31780}
    if vaknummer in vast:
        return vast[vaknummer]
    return 32688 if 2 <= vaknummer <= 38 else None


def tuin1_afdeling(vaknummer):
    """Afdeling van een vak op tuin 1: 1-7, 8-13, 14-20, 21-27."""
    for afdeling, vakken in TUIN1_AFDELINGEN.items():
        if vaknummer in vakken:
            return afdeling
    return None


def get_tuinen():
    """Alle tuinen: [{'id', 'nummer', 'naam', 'adres', 'priva_site_id', 'priva_device_id'}], op nummer."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nummer, naam, adres, priva_site_id, priva_device_id
            FROM tuinen ORDER BY nummer
        """)
        velden = ("id", "nummer", "naam", "adres", "priva_site_id", "priva_device_id")
        return [dict(zip(velden, rij)) for rij in cursor.fetchall()]


def get_tuin_id(nummer=STANDAARD_TUIN):
    """Het id van een tuin op basis van het tuinnummer (1 of 3)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tuinen WHERE nummer = %s", (nummer,))
        rij = cursor.fetchone()
    return rij[0] if rij else None


def maak_vakken_tuin1(gebruiker=None):
    """
    Zet de 27 vakken van tuin 1 klaar (afdeling en aantal stelen bij 60/m2).
    Bestaande vakken worden bijgewerkt, niet gedupliceerd. Geeft het aantal
    aangemaakte vakken terug.
    """
    tuin_id = get_tuin_id(1)
    aangemaakt = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for vaknummer in range(1, 28):
            stelen = TUIN1_STELEN_BIJ_60.get(vaknummer, TUIN1_STELEN_STANDAARD)
            cursor.execute(
                "SELECT id FROM teeltvakken WHERE tuin_id = %s AND vaknummer = %s", (tuin_id, vaknummer)
            )
            bestaand = cursor.fetchone()
            if bestaand:
                cursor.execute("""
                    UPDATE teeltvakken SET afdeling = %s, stelen_bij_60 = %s WHERE id = %s
                """, (tuin1_afdeling(vaknummer), stelen, bestaand[0]))
            else:
                cursor.execute("""
                    INSERT INTO teeltvakken (naam, vaknummer, tuin_id, afdeling, stelen_bij_60)
                    VALUES (%s, %s, %s, %s, %s)
                """, (str(vaknummer), vaknummer, tuin_id, tuin1_afdeling(vaknummer), stelen))
                aangemaakt += 1
        conn.commit()
    if aangemaakt:
        log_wijziging(gebruiker, "aangemaakt", "teeltvak", None,
                      f"{aangemaakt} vakken aangemaakt voor tuin 1")
    return aangemaakt


# De app zet per scherm welke tuin actief is; alle queries zonder expliciete
# tuin volgen die. Per thread, want Streamlit draait elke gebruiker in een eigen
# thread binnen hetzelfde proces: een gewone globale zou van Job naar Kees lekken.
_actieve_tuin = threading.local()


def zet_actieve_tuin(tuin_id):
    """Zet de tuin waar queries zonder expliciete tuin op werken (None = standaard)."""
    _actieve_tuin.id = tuin_id


def get_actieve_tuin():
    """De actieve tuin van deze sessie, of de standaardtuin."""
    return getattr(_actieve_tuin, "id", None) or get_tuin_id(STANDAARD_TUIN)


def _tuin_of_standaard(tuin_id=None):
    """Het opgegeven tuin-id, of de actieve tuin van deze sessie."""
    return tuin_id if tuin_id is not None else get_actieve_tuin()


def oppervlakte_van_tuin(tuin_id=None):
    """
    Teeltoppervlak (m2) van een tuin, om verbruik per m2 uit te rekenen.
    Tuin 3 houdt zijn vaste 20.900 m2 aan, zodat eerder opgeslagen waarden
    vergelijkbaar blijven; voor andere tuinen volgt het uit de vakken
    (stelen bij 60 per m2, gedeeld door 60).
    """
    tuin_id = _tuin_of_standaard(tuin_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nummer FROM tuinen WHERE id = %s", (tuin_id,))
        rij = cursor.fetchone()
        if rij and rij[0] == STANDAARD_TUIN:
            return TUIN3_OPPERVLAKTE_M2
        cursor.execute(
            "SELECT SUM(stelen_bij_60) FROM teeltvakken WHERE tuin_id = %s AND vaknummer IS NOT NULL",
            (tuin_id,),
        )
        totaal_stelen = cursor.fetchone()[0]
    return (totaal_stelen / 60) if totaal_stelen else None


def _tuinnummer(tuin_id):
    """Het tuinnummer (1 of 3) bij een tuin-id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nummer FROM tuinen WHERE id = %s", (tuin_id,))
        rij = cursor.fetchone()
    return rij[0] if rij else STANDAARD_TUIN


def afdeling_van_vak(vaknummer, tuin_id=None):
    """
    Afdeling van een vak binnen een tuin. Komt uit de tabel; staat hij daar nog
    niet, dan uit de vaste indeling van die tuin.
    """
    tuin_id = _tuin_of_standaard(tuin_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT afdeling FROM teeltvakken WHERE tuin_id = %s AND vaknummer = %s",
            (tuin_id, vaknummer),
        )
        rij = cursor.fetchone()
    if rij and rij[0] is not None:
        return rij[0]
    return tuin1_afdeling(vaknummer) if _tuinnummer(tuin_id) == 1 else afdeling_van_vaknummer(vaknummer)


def stelen_bij_60_van_vak(vaknummer, tuin_id=None):
    """Aantal stelen bij 60 per m2 voor een vak; uit de tabel, anders de vaste waarde."""
    tuin_id = _tuin_of_standaard(tuin_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stelen_bij_60 FROM teeltvakken WHERE tuin_id = %s AND vaknummer = %s",
            (tuin_id, vaknummer),
        )
        rij = cursor.fetchone()
    if rij and rij[0] is not None:
        return rij[0]
    if _tuinnummer(tuin_id) == 1:
        return TUIN1_STELEN_BIJ_60.get(vaknummer, TUIN1_STELEN_STANDAARD)
    return _TUIN3_STELEN(vaknummer)


def get_vaknummers(tuin_id=None):
    """De vaknummers van een tuin, laag naar hoog."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT vaknummer FROM teeltvakken WHERE tuin_id = %s AND vaknummer IS NOT NULL "
            "ORDER BY vaknummer",
            (_tuin_of_standaard(tuin_id),),
        )
        return [r[0] for r in cursor.fetchall()]


def get_standaard_tuin_van_gebruiker(username):
    """Het tuinnummer waarmee deze gebruiker begint (Kees en Robert: tuin 1)."""
    if not username:
        return STANDAARD_TUIN
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT standaard_tuin FROM gebruikers WHERE username = %s", (username,))
        rij = cursor.fetchone()
    return (rij[0] if rij and rij[0] else STANDAARD_TUIN)

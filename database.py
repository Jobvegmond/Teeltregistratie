import os
import threading
from contextlib import contextmanager
from datetime import date, datetime
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
    """
    if isinstance(datum_teelt_start, str):
        datum_teelt_start = datetime.strptime(datum_teelt_start, "%Y-%m-%d").date()

    jaar_kort = datum_teelt_start.year % 100
    plantweek = get_weeknummer(datum_teelt_start)
    return f"{jaar_kort:02d}{plantweek:02d}{int(vaknummer):02d}"


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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS klimaatdata_week (
                id SERIAL PRIMARY KEY,
                afdeling INTEGER NOT NULL,
                datum_van TEXT NOT NULL,
                datum_tot TEXT NOT NULL,
                gem_temperatuur REAL,
                gem_rv REAL,
                stralingssom_week REAL,
                stralingssom_dag REAL,
                UNIQUE (afdeling, datum_van)
            )
        """)

        # Migratie: voeg ontbrekende kolommen toe aan bestaande databases.
        cursor.execute("ALTER TABLE teelten ADD COLUMN IF NOT EXISTS rijpheid TEXT")
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


# --- TEELTVAKKEN ---

def get_of_maak_teeltvak(vaknummer, naam=None):
    """
    Geeft het id van een teeltvak terug op basis van het vaknummer (1-39);
    maakt het aan als het nog niet bestaat.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM teeltvakken WHERE vaknummer = %s", (vaknummer,))
        resultaat = cursor.fetchone()

        if resultaat:
            teeltvak_id = resultaat[0]
            if naam:
                cursor.execute("UPDATE teeltvakken SET naam = %s WHERE id = %s", (naam, teeltvak_id))
                conn.commit()
        else:
            vak_naam = naam or str(vaknummer)
            cursor.execute(
                "INSERT INTO teeltvakken (naam, vaknummer) VALUES (%s, %s) RETURNING id",
                (vak_naam, vaknummer)
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

def start_nieuwe_teelt(vaknummer, datum_teelt_start, aantal_planten=None, naam=None):
    """
    Start een nieuwe teelt in een teeltvak (op basis van vaknummer 1-39).
    Maakt het teeltvak aan indien het nog niet bestaat.
    Genereert de unieke teelt-code (jaar+week+vaknummer) en slaat het
    aantal geplante planten op.
    Geeft het id van de nieuwe teelt terug.
    """
    teeltvak_id = get_of_maak_teeltvak(vaknummer, naam)
    code = genereer_teelt_code(datum_teelt_start, vaknummer)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teelten (teeltvak_id, datum_teelt_start, aantal_planten, code)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (teeltvak_id, str(datum_teelt_start), aantal_planten, code))
        nieuwe_teelt_id = cursor.fetchone()[0]
        conn.commit()

    return nieuwe_teelt_id, code


def get_lopende_teelten():
    """
    Geeft alle teelten terug die nog niet zijn afgerond (geen oogstdatum),
    samen met de naam van het teeltvak. Handig voor selectboxen.
    Retourneert lijst van tuples: (teelt_id, label_voor_selectbox)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE t.datum_oogst IS NULL
            ORDER BY t.datum_teelt_start, v.vaknummer
        """)
        rijen = cursor.fetchall()

    resultaat = []
    for teelt_id, vaknummer, start_datum, code in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        code_deel = code if code else f"ID{teelt_id}"
        label = f"Week {plantweek} - Vak {vak_deel} - {code_deel}"
        resultaat.append((teelt_id, label))
    return resultaat


def update_halverwege(teelt_id, datum_half, lengte_half):
    """Slaat de halverwege-meting op voor een specifieke teelt."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE teelten
            SET datum_half = %s, lengte_half = %s
            WHERE id = %s
        """, (str(datum_half), lengte_half, teelt_id))
        conn.commit()


def update_oogst(teelt_id, lengte_eind, oogstgewicht, rijpheid=None):
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


def markeer_teelt_afgerond(teelt_id, datum_oogst):
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


def get_alle_teelten_voor_selectie():
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
            ORDER BY t.datum_teelt_start, v.vaknummer
        """)
        rijen = cursor.fetchall()

    resultaat = []
    for teelt_id, vaknummer, start_datum, code in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        code_deel = code if code else f"ID{teelt_id}"
        label = f"Week {plantweek} - Vak {vak_deel} - {code_deel}"
        resultaat.append((teelt_id, label))
    return resultaat


def get_teelt_by_id(teelt_id):
    """Geeft alle gegevens van één teelt terug als dict, of None als niet gevonden."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.naam, v.vaknummer, t.datum_teelt_start, t.datum_half, t.lengte_half,
                   t.datum_oogst, t.lengte_eind, t.oogstgewicht, t.rijpheid,
                   t.aantal_planten, t.code
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
    }


def update_teelt_volledig(teelt_id, datum_teelt_start, datum_half, lengte_half,
                           datum_oogst, lengte_eind, oogstgewicht, rijpheid=None,
                           aantal_planten=None, vaknummer=None):
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


def delete_teelt(teelt_id):
    """Verwijdert een teelt permanent, inclusief de bijbehorende oogstregistraties."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM oogstregistraties WHERE teelt_id = %s", (teelt_id,))
        cursor.execute("DELETE FROM teelten WHERE id = %s", (teelt_id,))
        conn.commit()


# --- OOGSTREGISTRATIES (EMMERS) ---

def voeg_oogstregistratie_toe(teelt_id, datum, aantal_emmers):
    """Voegt een oogstmoment (aantal emmers, 100 stelen per emmer) toe aan een teelt."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO oogstregistraties (teelt_id, datum, aantal_emmers)
            VALUES (%s, %s, %s)
        """, (teelt_id, str(datum), aantal_emmers))
        conn.commit()


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


def wijzig_oogstregistratie(registratie_id, datum, aantal_emmers):
    """Past de datum en het aantal emmers van een bestaand oogstmoment aan."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE oogstregistraties SET datum = %s, aantal_emmers = %s WHERE id = %s",
            (str(datum), aantal_emmers, registratie_id)
        )
        conn.commit()


def verwijder_oogstregistratie(registratie_id):
    """Verwijdert een enkel oogstmoment."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM oogstregistraties WHERE id = %s", (registratie_id,))
        conn.commit()


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


def voeg_gebruiker_toe(username, naam, wachtwoord_hash, email=None):
    """
    Voegt een gebruiker toe of werkt een bestaande bij (op username).
    Het wachtwoord moet al gehasht zijn, bijv. met
    streamlit_authenticator.Hasher.hash(...). Er wordt nooit een wachtwoord in
    platte tekst opgeslagen.
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


def verwijder_gebruiker(username):
    """Verwijdert een gebruiker."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gebruikers WHERE username = %s", (username.strip().lower(),))
        conn.commit()


def get_alle_gebruikers():
    """Geeft (username, naam, email) van alle gebruikers terug."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, naam, email FROM gebruikers ORDER BY username")
        return cursor.fetchall()


def get_overzicht_dataframe():
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
            ORDER BY (t.code IS NULL), t.code
        """)
        teelt_rijen = cursor.fetchall()

    totaal_emmers_per_teelt = get_totaal_emmers_per_teelt()

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

        rijen_uitgebreid.append((
            teelt_id,
            f"{format_datum(start)} (week {start_week})" if start else "-",
            naam,
            f"{format_datum(half_datum)} (week {get_weeknummer(half_datum)})" if half_datum else "-",
            half_lengte if half_lengte else "-",
            f"{format_datum(oogst_datum)} (week {get_weeknummer(oogst_datum)})" if oogst_datum else "-",
            teeltduur,
            eind_lengte if eind_lengte else "-",
            round(gewicht) if gewicht else "-",
            rijpheid if rijpheid else "-",
            uitval_pct,
            aantal_planten if aantal_planten else "-",
            totaal_emmers if totaal_emmers else "-",
            totaal_stelen,
            code if code else "-",
        ))

    kolommen = ["ID", "Startdatum", "Teeltvak", "Datum Halverwege", "Lengte Half (cm)",
                "Oogstdatum", "Teeltduur (dagen)", "Oogstlengte (cm)", "Oogstgewicht (gram)",
                "Rijpheid", "Uitval (%)", "Aantal Planten", "Aantal Emmers", "Aantal Stelen",
                "Code"]
    return kolommen, rijen_uitgebreid


# --- KLIMAATDATA (KLIMAATCOMPUTER-CSV) ---
#
# Kasindeling: afdeling 1 = vak 1-9, afdeling 2 = vak 30-39,
# afdeling 3 = vak 10-19, afdeling 4 = vak 20-29.
#
# De klimaatcomputer-export bevat weekregels (startdate-enddate, maandag t/m
# zondag) per variabele (label) en afdeling. Voor de teeltkoppeling gebruiken
# we Ave_24h_CompTemp (gemiddelde temperatuur), Ave_24h_CompRV (gemiddelde
# RV) en de som van Sum_Day_CalculatedRadiation + Sum_Night_CalculatedRadiation
# (stralingssom, weeksom). Rijen voor een andere "Afdeling"-index dan 1-4
# (bijv. index 5) horen niet bij een van onze kasafdelingen en worden genegeerd.

KLIMAAT_TEMP_LABEL = "Ave_24h_CompTemp"
KLIMAAT_RV_LABEL = "Ave_24h_CompRV"
KLIMAAT_STRALING_LABELS = ["Sum_Day_CalculatedRadiation", "Sum_Night_CalculatedRadiation"]
KLIMAAT_GELDIGE_AFDELINGEN = {1, 2, 3, 4}


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


def upsert_klimaatdata_week(afdeling, datum_van, datum_tot, gem_temperatuur, gem_rv, stralingssom_week):
    """
    Slaat één afdeling-week klimaatgegevens op (of overschrijft de bestaande
    week bij een herupload). De stralingssom wordt meteen ook per dag
    opgeslagen (weeksom / 7).
    """
    stralingssom_dag = stralingssom_week / 7 if stralingssom_week is not None else None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO klimaatdata_week
                (afdeling, datum_van, datum_tot, gem_temperatuur, gem_rv, stralingssom_week, stralingssom_dag)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (afdeling, datum_van)
            DO UPDATE SET datum_tot = EXCLUDED.datum_tot,
                          gem_temperatuur = EXCLUDED.gem_temperatuur,
                          gem_rv = EXCLUDED.gem_rv,
                          stralingssom_week = EXCLUDED.stralingssom_week,
                          stralingssom_dag = EXCLUDED.stralingssom_dag
        """, (
            afdeling, str(datum_van), str(datum_tot),
            gem_temperatuur, gem_rv, stralingssom_week, stralingssom_dag
        ))
        conn.commit()


def verwerk_klimaat_csv(bestand):
    """
    Leest een klimaatcomputer-CSV in (tab- of puntkomma-gescheiden, decimale
    komma) en zet de weekregels om naar rijen in klimaatdata_week, per
    afdeling (1-4). Geeft het aantal verwerkte afdeling-weken terug.
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

    df["datum_van"] = pd.to_datetime(df["startdate"], dayfirst=True, format="mixed").dt.date
    df["datum_tot"] = pd.to_datetime(df["enddate"], dayfirst=True, format="mixed").dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    relevante_labels = [KLIMAAT_TEMP_LABEL, KLIMAAT_RV_LABEL] + KLIMAAT_STRALING_LABELS
    df = df[df["label"].isin(relevante_labels)]

    verwerkt = 0
    for (afdeling, datum_van, datum_tot), groep in df.groupby(["idx_1", "datum_van", "datum_tot"]):
        temp = groep.loc[groep["label"] == KLIMAAT_TEMP_LABEL, "value"].dropna()
        rv = groep.loc[groep["label"] == KLIMAAT_RV_LABEL, "value"].dropna()
        straling = groep.loc[groep["label"].isin(KLIMAAT_STRALING_LABELS), "value"].dropna()

        gem_temperatuur = float(temp.iloc[0]) if not temp.empty else None
        gem_rv = float(rv.iloc[0]) if not rv.empty else None
        stralingssom_week = float(straling.sum()) if not straling.empty else None

        upsert_klimaatdata_week(int(afdeling), datum_van, datum_tot, gem_temperatuur, gem_rv, stralingssom_week)
        verwerkt += 1

    return verwerkt


def get_klimaat_voor_periode(afdeling, datum_start, datum_eind):
    """
    Geeft de gemiddelde temperatuur, gemiddelde RV en gemiddelde dagstralingssom
    terug over alle opgeslagen weken die overlappen met de opgegeven periode
    (bijv. de looptijd van een teelt). Geeft None terug als er geen data is.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(gem_temperatuur), AVG(gem_rv), AVG(stralingssom_dag)
            FROM klimaatdata_week
            WHERE afdeling = %s AND datum_van <= %s AND datum_tot >= %s
        """, (afdeling, str(datum_eind), str(datum_start)))
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    return {"gem_temperatuur": rij[0], "gem_rv": rij[1], "gem_stralingssom_dag": rij[2]}


def get_klimaatdata_weken_voor_periode(afdeling, datum_start, datum_eind):
    """
    Geeft de losse weekregels terug (voor grafieken) die overlappen met de
    opgegeven periode, gesorteerd op datum. Retourneert een lijst van tuples
    (datum_van, gem_temperatuur, gem_rv, stralingssom_dag).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum_van, gem_temperatuur, gem_rv, stralingssom_dag
            FROM klimaatdata_week
            WHERE afdeling = %s AND datum_van <= %s AND datum_tot >= %s
            ORDER BY datum_van
        """, (afdeling, str(datum_eind), str(datum_start)))
        return cursor.fetchall()


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

        rijen.append((
            code if code else f"ID{teelt_id}",
            naam,
            afdeling,
            format_datum(start),
            format_datum(oogst) if oogst else "lopend",
            round(klimaat["gem_temperatuur"], 1) if klimaat["gem_temperatuur"] is not None else "-",
            round(klimaat["gem_rv"], 1) if klimaat["gem_rv"] is not None else "-",
            round(klimaat["gem_stralingssom_dag"]) if klimaat["gem_stralingssom_dag"] is not None else "-",
        ))

    kolommen = ["Code", "Teeltvak", "Afdeling", "Startdatum", "Oogstdatum",
                "Gem. temperatuur (°C)", "Gem. RV (%)", "Gem. stralingssom (per dag)"]
    return kolommen, rijen

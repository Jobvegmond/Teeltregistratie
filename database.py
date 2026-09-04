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

def start_nieuwe_teelt(vaknummer, datum_teelt_start, aantal_planten=None, naam=None, gebruiker=None):
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

    log_wijziging(
        gebruiker, "aangemaakt", "teelt", nieuwe_teelt_id,
        f"Nieuwe teelt gestart in vak {vaknummer} op {datum_teelt_start} "
        f"(code {code}, {aantal_planten or 0} planten)"
    )

    return nieuwe_teelt_id, code


def get_lopende_teelten():
    """
    Geeft alle teelten terug die daadwerkelijk lopen: nog niet afgerond
    (geen oogstdatum) én al gestart (startdatum ligt niet in de toekomst).
    Een teelt met een toekomstige startdatum is nog niet geplant en hoort
    dus niet tussen de Florgib-/oogstregistratie-keuzes. Handig voor
    selectboxen. Retourneert lijst van tuples: (teelt_id, label_voor_selectbox)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, v.vaknummer, t.datum_teelt_start, t.code
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE t.datum_oogst IS NULL AND t.datum_teelt_start <= %s
            ORDER BY t.datum_teelt_start, v.vaknummer
        """, (str(date.today()),))
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


def get_isojaar_week(datum):
    """Geeft (iso-jaar, iso-weeknummer) van een datum terug, voor groepering per plantweek."""
    if isinstance(datum, str):
        datum = datetime.strptime(datum, "%Y-%m-%d").date()
    iso_jaar, week, _ = datum.isocalendar()
    return iso_jaar, week


def get_alle_teelten_detail():
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
            ORDER BY t.datum_teelt_start, v.vaknummer
        """)
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
            f"{format_datum(start)} (week {start_week})" if start else "-",
            status,
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

    kolommen = ["ID", "Startdatum", "Status", "Teeltvak", "Datum Halverwege", "Lengte Half (cm)",
                "Oogstdatum", "Teeltduur (dagen)", "Oogstlengte (cm)", "Oogstgewicht (gram)",
                "Rijpheid", "Uitval (%)", "Aantal Planten", "Aantal Emmers", "Aantal Stelen",
                "Code"]
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
                            gem_rv_dag=None, gem_rv_nacht=None):
    """Slaat één afdeling-dag klimaatgegevens op (of overschrijft de bestaande dag bij een herupload)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO klimaatdata_dag
                (afdeling, datum, gem_temperatuur, gem_rv, stralingssom_dag,
                 gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (afdeling, datum)
            DO UPDATE SET gem_temperatuur = EXCLUDED.gem_temperatuur,
                          gem_rv = EXCLUDED.gem_rv,
                          stralingssom_dag = EXCLUDED.stralingssom_dag,
                          gem_temperatuur_dag = EXCLUDED.gem_temperatuur_dag,
                          gem_temperatuur_nacht = EXCLUDED.gem_temperatuur_nacht,
                          gem_rv_dag = EXCLUDED.gem_rv_dag,
                          gem_rv_nacht = EXCLUDED.gem_rv_nacht
        """, (
            afdeling, str(datum), gem_temperatuur, gem_rv, stralingssom_dag,
            gem_temperatuur_dag, gem_temperatuur_nacht, gem_rv_dag, gem_rv_nacht,
        ))
        conn.commit()


def verwerk_klimaat_csv(bestand, gebruiker=None):
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


def get_klimaat_voor_periode(afdeling, datum_start, datum_eind):
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
            WHERE afdeling = %s AND datum BETWEEN %s AND %s
        """, (afdeling, str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    return {"gem_temperatuur": rij[0], "gem_rv": rij[1], "gem_stralingssom_dag": rij[2]}


def get_klimaatdata_dagen_voor_periode(afdeling, datum_start, datum_eind):
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
            WHERE afdeling = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (afdeling, str(datum_start), str(datum_eind)))
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


# --- PLANNING (TOEKOMSTIGE TEELTEN) ---
#
# Geeft per plantweek (ISO-weeknummer 1-52) de verwachte teeltduur in weken,
# geldig voor de hele kas (niet per afdeling). Voorlopige tabel, aangeleverd
# 2026-09-04; kan later nog worden bijgewerkt of verfijnd per afdeling.
# Week 53 (niet elk jaar aanwezig) heeft bewust geen waarde.
TEELTDUUR_PER_PLANTWEEK = {
    1: 11.0, 2: 10.0, 3: 10.0, 4: 9.0, 5: 9.0, 6: 8.5, 7: 8.0, 8: 8.0, 9: 8.0, 10: 8.0,
    11: 7.0, 12: 7.0, 13: 7.0, 14: 7.0, 15: 7.0, 16: 7.0, 17: 7.0, 18: 7.0, 19: 7.0, 20: 7.0,
    21: 7.0, 22: 6.3, 23: 6.8, 24: 6.5, 25: 6.4, 26: 6.6, 27: 6.7, 28: 6.8, 29: 7.0, 30: 7.0,
    31: 7.0, 32: 7.2, 33: 7.8, 34: 8.3, 35: 9.0, 36: 9.4, 37: 9.6, 38: 10.3, 39: 10.8, 40: 11.6,
    41: 12.6, 42: 13.5, 43: 14.0, 44: 14.0, 45: 14.7, 46: 15.3, 47: 15.0, 48: 15.0, 49: 14.5,
    50: 14.0, 51: 14.0, 52: 13.0,
}

# Vaste wisseltijd (schoonmaak/omschakelen) tussen de oogst van de ene teelt
# en het planten van de volgende in hetzelfde vak. Voorlopige waarde,
# aangeleverd 2026-09-04 ("houdt voor nu maar aan").
WISSELTIJD_DAGEN = 4


def teeltduur_voor_plantweek(week):
    """Geeft de verwachte teeltduur (in weken) voor een ISO-plantweek terug, of None als onbekend."""
    return TEELTDUUR_PER_PLANTWEEK.get(week)


def bereken_verwachte_oogstdatum(datum_start):
    """
    Berekent de verwachte oogstdatum op basis van de teeltduur-per-plantweek-
    tabel. Geeft (verwachte_duur_weken, verwachte_oogstdatum) terug, of
    (None, None) als de plantweek niet in de tabel staat.
    """
    if isinstance(datum_start, str):
        datum_start = datetime.strptime(datum_start, "%Y-%m-%d").date()
    duur_weken = teeltduur_voor_plantweek(get_weeknummer(datum_start))
    if duur_weken is None:
        return None, None
    return duur_weken, datum_start + timedelta(days=round(duur_weken * 7))


def volgende_startdatum_vak(vaknummer):
    """
    Stelt de volgende startdatum voor een vak voor: wisseltijd na de laatst
    bekende (of al geplande) oogst van dat vak. Kijkt in volgorde van
    voorkeur naar: de laatste concept-planning voor dit vak, dan de meest
    recente teelt (afgerond -> werkelijke oogstdatum, lopend -> verwachte
    oogstdatum via de duur-tabel). Geeft None terug als er nog niets bekend
    is om op verder te bouwen (nooit een teelt of planning gehad).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT verwachte_oogstdatum FROM teeltplanning
            WHERE vaknummer = %s AND verwachte_oogstdatum IS NOT NULL
            ORDER BY verwachte_startdatum DESC LIMIT 1
        """, (vaknummer,))
        planning_rij = cursor.fetchone()

    if planning_rij:
        laatste_eind = datetime.strptime(planning_rij[0], "%Y-%m-%d").date()
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.datum_teelt_start, t.datum_oogst
                FROM teelten t
                JOIN teeltvakken v ON t.teeltvak_id = v.id
                WHERE v.vaknummer = %s
                ORDER BY t.datum_teelt_start DESC LIMIT 1
            """, (vaknummer,))
            teelt_rij = cursor.fetchone()

        if not teelt_rij:
            return None

        start, oogst = teelt_rij
        if oogst:
            laatste_eind = datetime.strptime(oogst, "%Y-%m-%d").date()
        else:
            _, verwacht = bereken_verwachte_oogstdatum(start)
            if not verwacht:
                return None
            laatste_eind = verwacht

    return laatste_eind + timedelta(days=WISSELTIJD_DAGEN)


def voeg_planning_toe(vaknummer, verwachte_startdatum, notitie=None, gebruiker=None):
    """Maakt een concept-planningsregel aan voor een vak; duur/oogst worden automatisch berekend."""
    duur_weken, eind = bereken_verwachte_oogstdatum(verwachte_startdatum)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO teeltplanning (vaknummer, verwachte_startdatum, verwachte_duur_weken, verwachte_oogstdatum, notitie)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (vaknummer, str(verwachte_startdatum), duur_weken, str(eind) if eind else None, notitie))
        planning_id = cursor.fetchone()[0]
        conn.commit()

    log_wijziging(
        gebruiker, "aangemaakt", "planning", planning_id,
        f"Concept-planning vak {vaknummer}, start {verwachte_startdatum}"
        + (f", verwachte oogst {eind}" if eind else "")
    )
    return planning_id


def get_planning():
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
            ORDER BY verwachte_startdatum, vaknummer
        """)
        return cursor.fetchall()


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
        cursor.execute("SELECT vaknummer, verwachte_startdatum FROM teeltplanning WHERE id = %s", (planning_id,))
        rij = cursor.fetchone()

    if not rij:
        return None

    vaknummer, verwachte_startdatum = rij
    teelt_id, code = start_nieuwe_teelt(vaknummer, verwachte_startdatum, aantal_planten, gebruiker=gebruiker)
    verwijder_planning(planning_id, gebruiker=gebruiker)
    return teelt_id, code


def plan_alle_vakken(gebruiker=None):
    """
    Maakt in één keer voor elk vak (1-39) een concept-planning aan, met de
    voorgestelde volgende startdatum (zie volgende_startdatum_vak). Slaat
    vakken over die al een openstaand concept hebben, of waarvoor nog geen
    teeltgeschiedenis bestaat om een voorstel op te baseren. Geeft een lijst
    van tuples (vaknummer, status, verwachte_startdatum) terug, met status
    'gepland', 'al_gepland' of 'geen_geschiedenis'.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT vaknummer FROM teeltplanning")
        al_gepland = {rij[0] for rij in cursor.fetchall()}

    resultaten = []
    for vaknummer in range(1, 40):
        if vaknummer in al_gepland:
            resultaten.append((vaknummer, "al_gepland", None))
            continue

        voorstel = volgende_startdatum_vak(vaknummer)
        if voorstel is None:
            resultaten.append((vaknummer, "geen_geschiedenis", None))
            continue

        voeg_planning_toe(vaknummer, voorstel, gebruiker=gebruiker)
        resultaten.append((vaknummer, "gepland", voorstel))

    return resultaten


def _harde_bodem_vak(vaknummer):
    """
    Geeft de harde ondergrens voor een vak terug: de verwachte oogstdatum
    van de meest recente teelt (werkelijk als al afgerond, anders berekend
    via de teeltduur-tabel), zónder wisseltijd. Een vak kan nooit eerder dan
    dit gepland worden. Geeft None terug als het vak nog geen teeltgeschiedenis heeft.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.datum_teelt_start, t.datum_oogst
            FROM teelten t
            JOIN teeltvakken v ON t.teeltvak_id = v.id
            WHERE v.vaknummer = %s
            ORDER BY t.datum_teelt_start DESC LIMIT 1
        """, (vaknummer,))
        rij = cursor.fetchone()

    if not rij:
        return None

    start, oogst = rij
    if oogst:
        return datetime.strptime(oogst, "%Y-%m-%d").date()
    _, verwacht = bereken_verwachte_oogstdatum(start)
    return verwacht


def plan_alle_vakken_op_volgorde(gebruiker=None):
    """
    Plant alle vakken in strikt oplopende volgorde (eerst vak 1, dan 2, dan
    3, enz.) en probeert daarbij elke week gevuld te houden — geen weken
    zonder productie — door de wisseltijd flexibel in te zetten (0 tot
    WISSELTIJD_DAGEN dagen) in plaats van altijd de volle wisseltijd aan te
    houden. De harde ondergrens per vak blijft de eigen verwachte
    oogstdatum (zónder wisseltijd): een vak wordt nooit eerder gepland dan
    dat, en de volgorde wordt nooit doorbroken.

    Vakken die al een openstaand concept hebben, en vakken zonder
    teeltgeschiedenis, worden overgeslagen (niet opnieuw aangemaakt, en niet
    gebruikt als anker voor de overige vakken — die vormen hun eigen
    aaneengesloten, gelijkmatig verdeelde reeks). Geeft een lijst van
    tuples (vaknummer, status, verwachte_startdatum) terug, met status
    'gepland', 'al_gepland' of 'geen_geschiedenis'.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT vaknummer FROM teeltplanning")
        al_gepland = {rij[0] for rij in cursor.fetchall()}

    bodems = {}
    geen_geschiedenis = set()
    for vaknummer in range(1, 40):
        if vaknummer in al_gepland:
            continue
        bodem = _harde_bodem_vak(vaknummer)
        if bodem is None:
            geen_geschiedenis.add(vaknummer)
        else:
            bodems[vaknummer] = bodem

    resultaten = []
    if not bodems:
        for vaknummer in range(1, 40):
            if vaknummer in al_gepland:
                resultaten.append((vaknummer, "al_gepland", None))
            elif vaknummer in geen_geschiedenis:
                resultaten.append((vaknummer, "geen_geschiedenis", None))
        return resultaten

    # Streefaantal per week: totaal aantal te plannen vakken verdeeld over
    # de natuurlijke spreiding van hun harde bodems (plus maximale
    # wisseltijd), zo gelijkmatig mogelijk.
    vroegste = min(bodems.values())
    laatste = max(bodems.values()) + timedelta(days=WISSELTIJD_DAGEN)
    weken_beschikbaar = max(1, (laatste - vroegste).days // 7 + 1)
    quotum_per_week = max(1, -(-len(bodems) // weken_beschikbaar))

    cursor_week_start = None
    aantal_in_week = 0
    gekozen_data = {}
    for vaknummer in sorted(bodems):
        bodem = bodems[vaknummer]
        bodem_week_start = bodem - timedelta(days=bodem.weekday())
        kandidaat = bodem_week_start if cursor_week_start is None else max(bodem_week_start, cursor_week_start)

        if kandidaat == cursor_week_start and aantal_in_week >= quotum_per_week:
            kandidaat = cursor_week_start + timedelta(days=7)

        if kandidaat != cursor_week_start:
            cursor_week_start = kandidaat
            aantal_in_week = 0

        gekozen_data[vaknummer] = max(bodem, cursor_week_start)
        aantal_in_week += 1

    for vaknummer in range(1, 40):
        if vaknummer in al_gepland:
            resultaten.append((vaknummer, "al_gepland", None))
        elif vaknummer in geen_geschiedenis:
            resultaten.append((vaknummer, "geen_geschiedenis", None))
        else:
            gekozen_start = gekozen_data[vaknummer]
            voeg_planning_toe(vaknummer, gekozen_start, gebruiker=gebruiker)
            resultaten.append((vaknummer, "gepland", gekozen_start))

    return resultaten


def get_planning_per_week():
    """
    Groepeert alle concept-planningen per plantweek (iso-jaar + weeknummer
    van verwachte_startdatum), met de vaknummers in oplopende volgorde per
    week. Geeft een lijst van tuples (jaar, week, [vaknummers]) terug,
    gesorteerd op jaar/week.
    """
    rijen = get_planning()
    groepen = {}
    for _planning_id, vaknummer, start, _duur, _eind, _notitie in rijen:
        sleutel = get_isojaar_week(start)
        groepen.setdefault(sleutel, []).append(vaknummer)

    return [
        (jaar, week, sorted(groepen[(jaar, week)]))
        for jaar, week in sorted(groepen.keys())
    ]

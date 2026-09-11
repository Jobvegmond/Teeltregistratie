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

        # Handmatig streefaantal te poten vakken per plantweek. Als een week
        # hierin staat, houdt plan_x_weken_vooruit dat aantal aan en geldt de
        # "max 1 vak verschil met de buurweek"-regel niet meer voor die week.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS planning_weekdoel (
                week_start TEXT PRIMARY KEY,
                aantal_vakken INTEGER NOT NULL
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


def importeer_klimaat_uit_priva(dagen_terug=4, gebruiker=None):
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

def upsert_watergift_dag(vaknummer, datum, liter_per_m2):
    """Slaat één vak-dag watergift op (of overschrijft bij een herhaalde ophaal)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO watergift_dag (vaknummer, datum, liter_per_m2)
            VALUES (%s, %s, %s)
            ON CONFLICT (vaknummer, datum)
            DO UPDATE SET liter_per_m2 = EXCLUDED.liter_per_m2
        """, (int(vaknummer), str(datum), liter_per_m2))
        conn.commit()


def importeer_watergift_uit_priva(dagen_terug=4, gebruiker=None):
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


def get_watergift_voor_periode(vaknummer, datum_start, datum_eind):
    """
    Geeft het totaal aan watergift (liter/m²) en het aantal gemeten dagen
    terug voor een vak binnen een periode. Geeft None als er geen data is.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(liter_per_m2), COUNT(*)
            FROM watergift_dag
            WHERE vaknummer = %s AND datum BETWEEN %s AND %s
        """, (int(vaknummer), str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[1] == 0:
        return None
    return {"totaal_liter_per_m2": rij[0] or 0.0, "aantal_dagen": rij[1]}


def get_watergift_dagen_voor_periode(vaknummer, datum_start, datum_eind):
    """Losse dagregels (datum, liter_per_m2) voor grafieken, gesorteerd op datum."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, liter_per_m2
            FROM watergift_dag
            WHERE vaknummer = %s AND datum BETWEEN %s AND %s
            ORDER BY datum
        """, (int(vaknummer), str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_watergift_dekking():
    """
    Per vak: (vaknummer, eerste_datum, laatste_datum, aantal_dagen). Gesorteerd
    op vaknummer (laag naar hoog).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vaknummer, MIN(datum), MAX(datum), COUNT(*)
            FROM watergift_dag
            GROUP BY vaknummer
            ORDER BY vaknummer
        """)
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


def upsert_energiedata_dag(datum, warmte_mj_totaal):
    """Slaat het totale warmteverbruik (MJ) van de hele kas voor één dag op."""
    warmte_mj_per_m2 = warmte_mj_totaal / TUIN3_OPPERVLAKTE_M2 if warmte_mj_totaal is not None else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO energiedata_dag (datum, warmte_mj_totaal, warmte_mj_per_m2)
            VALUES (%s, %s, %s)
            ON CONFLICT (datum)
            DO UPDATE SET warmte_mj_totaal = EXCLUDED.warmte_mj_totaal,
                          warmte_mj_per_m2 = EXCLUDED.warmte_mj_per_m2
        """, (str(datum), warmte_mj_totaal, warmte_mj_per_m2))
        conn.commit()


def verwerk_energie_csv(bestand, gebruiker=None):
    """
    Leest een energiecomputer-CSV in (Priva-export "Rapport Energie") en zet
    de Pulsteller-dagwaarden (Sum_24h_PtEnergyUse, in GJ) om naar het totale
    warmteverbruik (MJ) per dag voor de hele kas, in energiedata_dag. Er
    kunnen meerdere Pulsteller-tellers (idx_1) in de export staan; die worden
    per dag bij elkaar opgeteld tot één totaal voor de kas. Dagen die nog
    niet helemaal voorbij zijn worden overgeslagen. Geeft (aantal verwerkte
    dagen, aantal overgeslagen onvolledige dagen) terug.
    """
    try:
        df = pd.read_csv(bestand, sep=None, engine="python", decimal=",")
    except Exception:
        bestand.seek(0)
        df = pd.read_csv(bestand, sep="\t", decimal=",")

    df.columns = df.columns.str.strip()
    df = df[(df["type_1"] == "Pulsteller") & (df["label"] == ENERGIE_LABEL)].copy()

    df["datum"] = pd.to_datetime(df["startdate"], dayfirst=True, format="mixed").dt.date
    df["datum_tot"] = pd.to_datetime(df["enddate"], dayfirst=True, format="mixed").dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    alle_dagen = df["datum"].drop_duplicates()
    df = df[df["datum_tot"] < date.today()]
    volledige_dagen = df["datum"].drop_duplicates()
    overgeslagen = len(alle_dagen) - len(volledige_dagen)

    verwerkt = 0
    for datum, groep in df.groupby("datum"):
        waarden = groep["value"].dropna()
        if waarden.empty:
            continue
        warmte_mj_totaal = float(waarden.sum()) * ENERGIE_EENHEID_NAAR_MJ
        upsert_energiedata_dag(datum, warmte_mj_totaal)
        verwerkt += 1

    log_wijziging(
        gebruiker, "geupload", "energiedata_csv", None,
        f"{verwerkt} dagen verwerkt, {overgeslagen} overgeslagen (nog niet afgerond)"
    )

    return verwerkt, overgeslagen


def get_energiedata_dagen_voor_periode(datum_start, datum_eind):
    """Losse dagregels (datum, warmte_mj_totaal, warmte_mj_per_m2) voor grafieken."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT datum, warmte_mj_totaal, warmte_mj_per_m2
            FROM energiedata_dag
            WHERE datum BETWEEN %s AND %s
            ORDER BY datum
        """, (str(datum_start), str(datum_eind)))
        return cursor.fetchall()


def get_energiedata_dekking():
    """(eerste_datum, laatste_datum, aantal_dagen, ontbrekende_dagen) of None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(datum), MAX(datum), COUNT(*) FROM energiedata_dag")
        rij = cursor.fetchone()

    if not rij or rij[0] is None:
        return None
    eerste_d = datetime.strptime(str(rij[0]), "%Y-%m-%d").date()
    laatste_d = datetime.strptime(str(rij[1]), "%Y-%m-%d").date()
    verwacht = (laatste_d - eerste_d).days + 1
    ontbrekend = max(verwacht - rij[2], 0)
    return (str(rij[0]), str(rij[1]), rij[2], ontbrekend)


def get_warmte_voor_periode(vaknummer, datum_start, datum_eind):
    """
    Geeft het totale warmteverbruik (MJ) van één vak binnen een periode terug,
    berekend als de kaswaarde per m2 per dag keer de oppervlakte van dat vak.
    Geeft None als er geen data of geen bekende oppervlakte is.
    """
    oppervlakte = oppervlakte_van_vaknummer(vaknummer)
    if not oppervlakte:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(warmte_mj_per_m2), COUNT(*)
            FROM energiedata_dag
            WHERE datum BETWEEN %s AND %s
        """, (str(datum_start), str(datum_eind)))
        rij = cursor.fetchone()

    if not rij or rij[1] == 0:
        return None
    return {"totaal_mj": (rij[0] or 0.0) * oppervlakte, "aantal_dagen": rij[1]}


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


def get_klimaatdata_dekking():
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
            GROUP BY afdeling
            ORDER BY afdeling
        """)
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

        rijen.append((
            code if code else f"ID{teelt_id}",
            naam,
            afdeling,
            format_datum(start),
            format_datum(oogst) if oogst else "lopend",
            round(klimaat["gem_temperatuur"], 1) if klimaat["gem_temperatuur"] is not None else "-",
            round(klimaat["gem_rv"], 1) if klimaat["gem_rv"] is not None else "-",
            round(klimaat["gem_stralingssom_dag"]) if klimaat["gem_stralingssom_dag"] is not None else "-",
            round(water["totaal_liter_per_m2"], 1) if water else "-",
            round(warmte["totaal_mj"] / 1000, 2) if warmte else "-",
        ))

    kolommen = ["Code", "Teeltvak", "Afdeling", "Startdatum", "Oogstdatum",
                "Gem. temperatuur (°C)", "Gem. RV (%)", "Gem. stralingssom (per dag)",
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

# Wisseltijd (schoonmaak/omschakelen) tussen de oogst van de ene teelt en het
# planten van de volgende in hetzelfde vak: de volgende planting kan pas zoveel
# dagen ná de verwachte oogst.
WISSELTIJD_DAGEN = 1

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


def _laatste_concept_oogst(vaknummer):
    """Verwachte oogstdatum van de laatste concept-planning van dit vak, of None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(verwachte_oogstdatum) FROM teeltplanning
            WHERE vaknummer = %s AND verwachte_oogstdatum IS NOT NULL
        """, (vaknummer,))
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


def get_planning_weekdoelen():
    """
    Handmatig ingestelde streefaantallen te poten vakken per plantweek.
    Geeft {week_start (maandag-date): aantal_vakken} terug.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT week_start, aantal_vakken FROM planning_weekdoel")
        return {
            datetime.strptime(w, "%Y-%m-%d").date(): int(a)
            for w, a in cursor.fetchall()
        }


def set_planning_weekdoel(week_start, aantal_vakken, gebruiker=None):
    """
    Zet (of wist bij aantal_vakken=None) het handmatige streefaantal vakken
    voor de plantweek waarin `week_start` valt.
    """
    week = _maandag(week_start)
    with get_connection() as conn:
        cursor = conn.cursor()
        if aantal_vakken is None:
            cursor.execute("DELETE FROM planning_weekdoel WHERE week_start = %s", (str(week),))
        else:
            cursor.execute("""
                INSERT INTO planning_weekdoel (week_start, aantal_vakken)
                VALUES (%s, %s)
                ON CONFLICT (week_start) DO UPDATE SET aantal_vakken = EXCLUDED.aantal_vakken
            """, (str(week), int(aantal_vakken)))
        conn.commit()
    log_wijziging(
        gebruiker, "gewijzigd", "planning_weekdoel", str(week),
        f"Streefaantal gezet op {aantal_vakken}" if aantal_vakken is not None
        else "Streefaantal gewist"
    )


def wis_planning_weekdoelen(gebruiker=None):
    """Wist alle handmatige weekstreefaantallen."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM planning_weekdoel")
        conn.commit()
    log_wijziging(gebruiker, "verwijderd", "planning_weekdoel", None,
                  "Alle handmatige weekstreefaantallen gewist")


def get_planning_weekoverzicht(aantal_weken=8):
    """
    Per plantweek vanaf deze week t/m de horizon een dict met:
      week_start (maandag-date), jaar, week (ISO), concepten (aantal
      concept-planningen die week, in poot-eenheden: vak 19+20 telt als 1),
      weekdoel (handmatig ingesteld streefaantal of None).
    Voedt de handmatige "vakken per week"-tabel in de planningsmodule.
    """
    maandag_nu = _maandag(date.today())
    weekdoelen = get_planning_weekdoelen()

    concept_vak_per_week = {}
    for _pid, vaknummer, start, _d, _e, _n in get_planning():
        w = _maandag(start)
        concept_vak_per_week.setdefault(w, []).append(vaknummer)

    concept_per_week = {}
    for w, vakken in concept_vak_per_week.items():
        aantal = len(vakken)
        if VAK_GECOMBINEERD[0] in vakken and VAK_GECOMBINEERD[1] in vakken:
            aantal -= 1  # 19+20 samen = 1 poot-eenheid
        concept_per_week[w] = aantal

    resultaat = []
    for i in range(max(1, aantal_weken)):
        w = maandag_nu + timedelta(weeks=i)
        jaar, week, _ = w.isocalendar()
        resultaat.append({
            "week_start": w,
            "jaar": jaar,
            "week": week,
            "concepten": concept_per_week.get(w, 0),
            "weekdoel": weekdoelen.get(w),
        })
    return resultaat


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


def get_planning_per_week():
    """
    Groepeert alle concept-planningen per plantweek (iso-jaar + weeknummer
    van verwachte_startdatum), met de vaknummers in oplopende volgorde per
    week. Geeft een lijst van tuples (jaar, week, [vaknummers], arbeidsaantal)
    terug, gesorteerd op jaar/week. Het arbeidsaantal is het aantal vakken
    dat voor de arbeidsplanning telt: vak 19+20 samen tellen daarin als 1
    (net als bij het maken van de planning), ook al staan ze allebei apart
    in de vakkenlijst.
    """
    rijen = get_planning()
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
        cursor.execute("SELECT vaknummer, verwachte_startdatum FROM teeltplanning WHERE id = %s", (planning_id,))
        rij = cursor.fetchone()

    if not rij:
        return None

    vaknummer, verwachte_startdatum = rij
    teelt_id, code = start_nieuwe_teelt(vaknummer, verwachte_startdatum, aantal_planten, gebruiker=gebruiker)
    verwijder_planning(planning_id, gebruiker=gebruiker)
    return teelt_id, code


def plan_x_weken_vooruit(aantal_weken, gebruiker=None, verwijder_bestaande=False):
    """
    Plant vakken tot `aantal_weken` weken vooruit als één doorlopende cyclus
    2, 3, ..., 39, 2, ... (met 19+20 als één eenheid, vak 1 op eigen ritme
    ertussen). Vak N wordt altijd vóór N+1 geplant én geoogst; een eenheid pas
    na de verwachte oogst van de vorige teelt + WISSELTIJD_DAGEN. Het aantal
    per week verschilt hooguit 1 met de buurweek (streefaantal ~ n/teeltduur),
    tenzij een week een handmatig weekdoel (planning_weekdoel) heeft.

    verwijder_bestaande=True wist de concepten en plant opnieuw, behalve de
    concepten t/m "planten besteld t/m" (die blijven vast). Zonder de vlag
    blijven alle concepten staan en wordt er alleen achteraan bijgepland.

    Geeft (resultaten, weekdoel_waarschuwingen):
    - resultaten: [(vaknummer, 'gepland'|'geen_geschiedenis'|'buiten_horizon',
      eerste_startdatum)];
    - weekdoel_waarschuwingen: [(week_start, gevraagd, geplant)] voor niet
      gehaalde weekdoelen.
    """
    besteld_tot = get_planning_besteld_tot()

    if verwijder_bestaande:
        with get_connection() as conn:
            cursor = conn.cursor()
            if besteld_tot is not None:
                cursor.execute(
                    "DELETE FROM teeltplanning WHERE verwachte_startdatum > %s",
                    (besteld_tot.isoformat(),),
                )
            else:
                cursor.execute("DELETE FROM teeltplanning")
            conn.commit()
        log_wijziging(
            gebruiker, "verwijderd", "planning", None,
            "Concept-planningen gewist om opnieuw te plannen"
            + (f" (besteld t/m {besteld_tot} blijft staan)" if besteld_tot else ""))

    weekdoelen = {w: min(MAX_VAKKEN_PER_WEEK, n)
                  for w, n in get_planning_weekdoelen().items()}
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
        return _planresultaat(weekdoelen, geen_geschiedenis)
    reps = [e[0] for e in bruikbaar]
    vak_naar_rep = {v: rep for rep, vakken in bruikbaar for v in vakken}

    # Vaste (besteld) concepten: staan vast; de cyclus hervat erna. Op id
    # herkend zodat de post-passes ze met rust laten.
    vaste = []          # (vaknummer, startdatum)
    vaste_ids = set()
    if besteld_tot is not None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, vaknummer, verwachte_startdatum FROM teeltplanning "
                "WHERE verwachte_startdatum <= %s",
                (besteld_tot.isoformat(),),
            )
            for pid, vak, s in cursor.fetchall():
                vaste.append((vak, datetime.strptime(s, "%Y-%m-%d").date()))
                vaste_ids.add(pid)

    # Cyclus-startpunt: het vak ná het laatst vastgezette (besteld), anders het
    # vak met het vroegste oogstfront.
    if vaste:
        laatste_vast_vak, _ = max(vaste, key=lambda x: (x[1], x[0]))
        laatste_rep = vak_naar_rep.get(laatste_vast_vak)
        if laatste_rep in reps:
            start_rep = reps[(reps.index(laatste_rep) + 1) % len(reps)]
        else:
            start_rep = min(bruikbaar, key=lambda e: (front[e[0]], e[0]))[0]
    else:
        start_rep = min(bruikbaar, key=lambda e: (front[e[0]], e[0]))[0]
    si = reps.index(start_rep)
    cyclus = bruikbaar[si:] + bruikbaar[:si]

    # Streefaantal per week ~ n/teeltduur (sneller in de zomer), maar van week
    # op week hooguit 1 verschil.
    def _ideaal(week_start):
        duur = teeltduur_voor_plantweek(get_weeknummer(week_start)) or 13.0
        return min(MAX_VAKKEN_PER_WEEK, max(1, round(len(bruikbaar) / max(6.0, duur))))

    weken_reeks = []
    w = _maandag(vandaag)
    while w <= horizon_eind + timedelta(days=7):
        weken_reeks.append(w)
        w += timedelta(days=7)
    streef_map = {}
    s = _ideaal(weken_reeks[0]) if weken_reeks else 3
    for w in weken_reeks:
        ideaal = _ideaal(w)
        s += (1 if ideaal > s else -1 if ideaal < s else 0)
        streef_map[w] = max(1, s)
    laatste_streef = streef_map[weken_reeks[-1]] if weken_reeks else 3

    # Handmatig weekdoel dat hoger is dan het natuurlijke tempo: de weken
    # ervóór minder laten planten zodat de eenheden opsparen en het doel echt
    # gehaald wordt.
    for wd_week in sorted(weekdoelen):
        tekort = weekdoelen[wd_week] - streef_map.get(wd_week, laatste_streef)
        w = wd_week - timedelta(days=7)
        while tekort > 0 and w in streef_map:
            if w not in weekdoelen and streef_map[w] > 1:
                streef_map[w] -= 1
                tekort -= 1
            w -= timedelta(days=7)

    def _cap(week):
        doel = weekdoelen.get(week)
        rauw = doel if doel is not None else streef_map.get(week, laatste_streef)
        return min(MAX_VAKKEN_PER_WEEK, rauw)

    # Vaste weken meetellen voor de capaciteit; sweep hervat na de laatste.
    week_teller = {}
    laatste_week = None
    sweep_vanaf = vandaag
    for _vak, s in vaste:
        wk = _maandag(s)
        week_teller[wk] = week_teller.get(wk, 0) + 1
        laatste_week = wk if laatste_week is None else max(laatste_week, wk)
        sweep_vanaf = max(sweep_vanaf, s + timedelta(days=1))

    earliest = {}  # planning_id -> vroegste plantdatum (voor de dagverdeling)

    def _plaats(vakken, vroegst):
        """Wijst een eenheid toe aan de eerstvolgende maandag-week die niet vol
        zit en een ma–do-dag heeft die ≥ `vroegst` ligt. Normaal begint een week
        met een planting op maandag; kan de eerste eenheid van een week niet op
        maandag starten (bodem valt later), dan mag die week toch beginnen op
        di/wo/do i.p.v. een hele week niet te planten. Geeft de maandag terug;
        de exacte dag ma→do volgt in _naverwerk_planning."""
        nonlocal laatste_week
        vroegst = max(vroegst, sweep_vanaf)
        week = _maandag(vroegst)
        if laatste_week is not None and week < laatste_week:
            week = laatste_week
        for _ in range(520):
            bezet = week_teller.get(week, 0)
            if bezet < _cap(week) and vroegst <= week + timedelta(days=3):
                break
            week += timedelta(days=7)
        week_teller[week] = bezet + 1
        laatste_week = week
        return week

    vak1_front = _bodem_incl_concept(VAK_VOLGORDE_UITZONDERING)
    if vak1_front is None:
        geen_geschiedenis.add(VAK_VOLGORDE_UITZONDERING)

    # Doorlopende sweep langs de cyclus.
    pos = 0
    vorige_datum = None
    for _ in range(4000):
        rep, vakken = cyclus[pos % len(cyclus)]
        vroegst = front[rep] + timedelta(days=WISSELTIJD_DAGEN)
        if vorige_datum is not None and vroegst < vorige_datum:
            vroegst = vorige_datum
        if _maandag(max(vroegst, sweep_vanaf)) > horizon_eind:
            break
        datum = _plaats(vakken, vroegst)
        if datum > horizon_eind:
            break
        for v in vakken:
            pid = voeg_planning_toe(v, datum, gebruiker=gebruiker)
            earliest[pid] = max(vroegst, sweep_vanaf)
        vorige_datum = datum
        _, nieuwe_oogst = bereken_verwachte_oogstdatum(datum)
        front[rep] = nieuwe_oogst or (datum + timedelta(weeks=13))

        # Vak 1 tussenvoegen zodra het klaar is, zonder de cyclus te blokkeren.
        vak1_vroegst = None if vak1_front is None else vak1_front + timedelta(days=WISSELTIJD_DAGEN)
        if vak1_vroegst is not None and vak1_vroegst <= (vorige_datum + timedelta(days=1)) \
                and _maandag(max(vak1_vroegst, sweep_vanaf)) <= horizon_eind:
            d1 = _plaats([VAK_VOLGORDE_UITZONDERING], max(vak1_vroegst, sweep_vanaf))
            if d1 <= horizon_eind:
                pid = voeg_planning_toe(VAK_VOLGORDE_UITZONDERING, d1, gebruiker=gebruiker)
                earliest[pid] = max(vak1_vroegst, sweep_vanaf)
                _, o1 = bereken_verwachte_oogstdatum(d1)
                vak1_front = o1 or (d1 + timedelta(weeks=13))
                if d1 > vorige_datum:
                    vorige_datum = d1

        pos += 1

    _naverwerk_planning(vaste_ids, earliest)
    return _planresultaat(weekdoelen, geen_geschiedenis)


def _naverwerk_planning(vaste_ids=None, earliest=None):
    """
    Naverwerking van de concept-planning (behalve `vaste_ids`), per maandag-week
    in cyclusvolgorde (= id-volgorde van de sweep):
    - dagverdeling ma→do: t/m 4 op ma/di/wo/do, meer eerst de maandag dubbel,
      dan de dinsdag, enz.; nooit vr/za/zo. Een vak nooit vóór zijn eigen
      vroegste dag (`earliest`) of vóór de oogst van z'n vorige ronde. Kan de
      eerste planting van een week niet op maandag (bodem valt later), dan mag
      die week op di/wo/do beginnen i.p.v. helemaal over te slaan. Nooit meer
      dan MAX_VAKKEN_PER_WEEK eenheden per week; het teveel schuift door.
    - teeltduur per concrete plantdag geïnterpoleerd tussen plantweek en week
      erna op weekdag (zelfde methode als bereken_verwachte_oogstdatum);
    - verwachte oogstdatum op ma–vr (weekend → vrijdag ervoor) en monotoon in
      cyclusvolgorde (altijd in dezelfde volgorde geoogst als geplant). Vak 1
      loopt op een eigen ritme en telt niet mee in die keten.
    """
    vaste_ids = vaste_ids or set()
    earliest = earliest or {}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, vaknummer, verwachte_startdatum FROM teeltplanning ORDER BY id")
        rijen = cursor.fetchall()

    per_week = {}
    for pid, vak, s in rijen:
        if pid in vaste_ids:
            continue
        d = datetime.strptime(s, "%Y-%m-%d").date()
        per_week.setdefault(_maandag(d), []).append((pid, vak))

    # Voor vak 1: de maandag van de eerstvolgende vak-1-planting, zodat z'n
    # oogst daar nooit overheen loopt.
    vak1_maandagen = [_maandag(datetime.strptime(s, "%Y-%m-%d").date())
                      for pid, vak, s in rijen
                      if vak == VAK_VOLGORDE_UITZONDERING and pid not in vaste_ids]
    vak1_volgende = {}
    v1p = [pid for pid, vak, _s in rijen
           if vak == VAK_VOLGORDE_UITZONDERING and pid not in vaste_ids]
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
    laatste_oogst_vak = {}  # vaknummer -> verwachte oogst vorige ronde in dit plan
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
                # nooit planten vóór de oogst van de vorige ronde in ditzelfde vak
                vorige_vak_oogst = laatste_oogst_vak.get(vak)
                if vorige_vak_oogst is not None and start <= vorige_vak_oogst:
                    start = _naar_plantdag(vorige_vak_oogst + timedelta(days=1))
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
                laatste_oogst_vak[vak] = oogst
                cursor.execute(
                    "UPDATE teeltplanning SET verwachte_startdatum = %s, verwachte_duur_weken = %s, "
                    "verwachte_oogstdatum = %s WHERE id = %s",
                    (start.isoformat(), round(duur, 2), oogst.isoformat(), pid))
        conn.commit()


def _planresultaat(weekdoelen, geen_geschiedenis):
    """
    Bouwt (resultaten, weekdoel_waarschuwingen) op uit de uiteindelijke
    concept-planning in de database.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT vaknummer, verwachte_startdatum FROM teeltplanning")
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
        vakken = per_week.get(week, [])
        aantal = len(vakken)
        if gecombineerd_laag in vakken and gecombineerd_hoog in vakken:
            aantal -= 1  # 19+20 samen = 1 poot-eenheid
        if aantal < doel:
            weekdoel_waarschuwingen.append((week, doel, aantal))

    return resultaten, weekdoel_waarschuwingen


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


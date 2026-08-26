import sqlite3
from datetime import datetime

DB_NAAM = "teeltdata.db"


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


def get_connection():
    """Geeft een databaseverbinding terug."""
    conn = sqlite3.connect(DB_NAAM)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Maakt de tabellen aan als ze nog niet bestaan."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teeltvakken (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            naam TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teelten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teelt_id INTEGER NOT NULL,
            datum TEXT NOT NULL,
            aantal_emmers REAL NOT NULL,
            FOREIGN KEY (teelt_id) REFERENCES teelten (id)
        )
    """)

    # Migratie: voeg de rijpheid-kolom toe aan bestaande databases die hem nog missen.
    cursor.execute("PRAGMA table_info(teelten)")
    bestaande_kolommen = [rij[1] for rij in cursor.fetchall()]
    if "rijpheid" not in bestaande_kolommen:
        cursor.execute("ALTER TABLE teelten ADD COLUMN rijpheid TEXT")
    if "aantal_planten" not in bestaande_kolommen:
        cursor.execute("ALTER TABLE teelten ADD COLUMN aantal_planten INTEGER")
    if "code" not in bestaande_kolommen:
        cursor.execute("ALTER TABLE teelten ADD COLUMN code TEXT")

    # Migratie: voeg het vaknummer toe aan teeltvakken.
    cursor.execute("PRAGMA table_info(teeltvakken)")
    vak_kolommen = [rij[1] for rij in cursor.fetchall()]
    if "vaknummer" not in vak_kolommen:
        cursor.execute("ALTER TABLE teeltvakken ADD COLUMN vaknummer INTEGER")
        # Best-effort: bestaande vakken die al puur numeriek genoemd zijn
        # (bijv. naam "19") krijgen dat getal meteen als vaknummer.
        cursor.execute("SELECT id, naam FROM teeltvakken WHERE vaknummer IS NULL")
        for vak_id, naam in cursor.fetchall():
            if naam and naam.strip().isdigit():
                cursor.execute(
                    "UPDATE teeltvakken SET vaknummer = ? WHERE id = ?",
                    (int(naam.strip()), vak_id)
                )

    # Migratie: bestaande teelten krijgen alsnog een code als hun vak een vaknummer heeft.
    cursor.execute("""
        SELECT t.id, t.datum_teelt_start, v.vaknummer
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        WHERE t.code IS NULL AND v.vaknummer IS NOT NULL
    """)
    for teelt_id, datum_start, vaknummer in cursor.fetchall():
        code = genereer_teelt_code(datum_start, vaknummer)
        cursor.execute("UPDATE teelten SET code = ? WHERE id = ?", (code, teelt_id))

    conn.commit()
    conn.close()


# --- TEELTVAKKEN ---

def get_of_maak_teeltvak(vaknummer, naam=None):
    """
    Geeft het id van een teeltvak terug op basis van het vaknummer (1-39);
    maakt het aan als het nog niet bestaat.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM teeltvakken WHERE vaknummer = ?", (vaknummer,))
    resultaat = cursor.fetchone()

    if resultaat:
        teeltvak_id = resultaat[0]
        if naam:
            cursor.execute("UPDATE teeltvakken SET naam = ? WHERE id = ?", (naam, teeltvak_id))
            conn.commit()
    else:
        vak_naam = naam or f"Vak {vaknummer}"
        cursor.execute(
            "INSERT INTO teeltvakken (naam, vaknummer) VALUES (?, ?)",
            (vak_naam, vaknummer)
        )
        conn.commit()
        teeltvak_id = cursor.lastrowid

    conn.close()
    return teeltvak_id


def get_alle_teeltvakken():
    """Geeft een lijst van (id, naam, vaknummer) van alle teeltvakken terug."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, naam, vaknummer FROM teeltvakken ORDER BY vaknummer, naam")
    vakken = cursor.fetchall()
    conn.close()
    return vakken


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

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO teelten (teeltvak_id, datum_teelt_start, aantal_planten, code)
        VALUES (?, ?, ?, ?)
    """, (teeltvak_id, str(datum_teelt_start), aantal_planten, code))
    conn.commit()
    nieuwe_teelt_id = cursor.lastrowid
    conn.close()
    return nieuwe_teelt_id, code


def get_lopende_teelten():
    """
    Geeft alle teelten terug die nog niet zijn afgerond (geen oogstdatum),
    samen met de naam van het teeltvak. Handig voor selectboxen.
    Retourneert lijst van tuples: (teelt_id, label_voor_selectbox)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, v.vaknummer, t.datum_teelt_start
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        WHERE t.datum_oogst IS NULL
        ORDER BY v.vaknummer, t.datum_teelt_start
    """)
    rijen = cursor.fetchall()
    conn.close()

    resultaat = []
    for teelt_id, vaknummer, start_datum in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        label = f"Vak {vak_deel} - Teelt {teelt_id} - week {plantweek}"
        resultaat.append((teelt_id, label))
    return resultaat


def update_halverwege(teelt_id, datum_half, lengte_half):
    """Slaat de halverwege-meting op voor een specifieke teelt."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teelten
        SET datum_half = ?, lengte_half = ?
        WHERE id = ?
    """, (str(datum_half), lengte_half, teelt_id))
    conn.commit()
    conn.close()


def update_oogst(teelt_id, datum_oogst, lengte_eind, oogstgewicht, rijpheid=None):
    """Slaat de oogstgegevens op voor een specifieke teelt."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teelten
        SET datum_oogst = ?, lengte_eind = ?, oogstgewicht = ?, rijpheid = ?
        WHERE id = ?
    """, (str(datum_oogst), lengte_eind, oogstgewicht, rijpheid, teelt_id))
    conn.commit()
    conn.close()


def get_alle_teelten_voor_selectie():
    """
    Geeft ALLE teelten terug (ook afgeronde), met een duidelijk label.
    Handig voor de 'wijzigen/verwijderen'-selectbox.
    Retourneert lijst van tuples: (teelt_id, label)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, v.vaknummer, t.datum_teelt_start
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        ORDER BY v.vaknummer, t.datum_teelt_start DESC
    """)
    rijen = cursor.fetchall()
    conn.close()

    resultaat = []
    for teelt_id, vaknummer, start_datum in rijen:
        plantweek = get_weeknummer(start_datum)
        vak_deel = vaknummer if vaknummer is not None else "?"
        label = f"Vak {vak_deel} - Teelt {teelt_id} - week {plantweek}"
        resultaat.append((teelt_id, label))
    return resultaat


def get_teelt_by_id(teelt_id):
    """Geeft alle gegevens van één teelt terug als dict, of None als niet gevonden."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, v.naam, v.vaknummer, t.datum_teelt_start, t.datum_half, t.lengte_half,
               t.datum_oogst, t.lengte_eind, t.oogstgewicht, t.rijpheid,
               t.aantal_planten, t.code
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        WHERE t.id = ?
    """, (teelt_id,))
    rij = cursor.fetchone()
    conn.close()

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

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teelten
        SET datum_teelt_start = ?, datum_half = ?, lengte_half = ?,
            datum_oogst = ?, lengte_eind = ?, oogstgewicht = ?, rijpheid = ?,
            aantal_planten = ?, code = COALESCE(?, code)
        WHERE id = ?
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
    conn.close()


def delete_teelt(teelt_id):
    """Verwijdert een teelt permanent, inclusief de bijbehorende oogstregistraties."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM oogstregistraties WHERE teelt_id = ?", (teelt_id,))
    cursor.execute("DELETE FROM teelten WHERE id = ?", (teelt_id,))
    conn.commit()
    conn.close()


# --- OOGSTREGISTRATIES (EMMERS) ---

def voeg_oogstregistratie_toe(teelt_id, datum, aantal_emmers):
    """Voegt een oogstmoment (aantal emmers, 100 stelen per emmer) toe aan een teelt."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO oogstregistraties (teelt_id, datum, aantal_emmers)
        VALUES (?, ?, ?)
    """, (teelt_id, str(datum), aantal_emmers))
    conn.commit()
    conn.close()


def get_oogstregistraties_voor_teelt(teelt_id):
    """Geeft alle oogstmomenten van een teelt terug: lijst van (id, datum, aantal_emmers)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, datum, aantal_emmers
        FROM oogstregistraties
        WHERE teelt_id = ?
        ORDER BY datum
    """, (teelt_id,))
    rijen = cursor.fetchall()
    conn.close()
    return rijen


def verwijder_oogstregistratie(registratie_id):
    """Verwijdert een enkel oogstmoment."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM oogstregistraties WHERE id = ?", (registratie_id,))
    conn.commit()
    conn.close()


def get_totaal_emmers_per_teelt():
    """Geeft een dict {teelt_id: totaal_aantal_emmers} terug voor alle teelten met registraties."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT teelt_id, SUM(aantal_emmers)
        FROM oogstregistraties
        GROUP BY teelt_id
    """)
    resultaat = {teelt_id: totaal for teelt_id, totaal in cursor.fetchall()}
    conn.close()
    return resultaat


def get_overzicht_dataframe():
    """
    Geeft alle teelten terug inclusief teeltvaknaam, code, weeknummers,
    teeltduur, geoogste emmers en uitvalpercentage.
    """
    conn = get_connection()
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
        ORDER BY v.naam, t.datum_teelt_start DESC
    """)
    teelt_rijen = cursor.fetchall()
    conn.close()

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
            uitval_pct = round((aantal_planten - totaal_emmers * 100) / aantal_planten * 100, 1)
        else:
            uitval_pct = "-"

        rijen_uitgebreid.append((
            teelt_id,
            code if code else "-",
            naam,
            aantal_planten if aantal_planten else "-",
            f"{start} (week {start_week})" if start else "-",
            f"{half_datum} (week {get_weeknummer(half_datum)})" if half_datum else "-",
            half_lengte if half_lengte else "-",
            f"{oogst_datum} (week {get_weeknummer(oogst_datum)})" if oogst_datum else "-",
            eind_lengte if eind_lengte else "-",
            gewicht if gewicht else "-",
            rijpheid if rijpheid else "-",
            teeltduur,
            totaal_emmers if totaal_emmers else "-",
            totaal_stelen,
            uitval_pct
        ))

    kolommen = ["ID", "Code", "Teeltvak", "Aantal Planten", "Start (week)", "Halverwege (week)",
                "Lengte Half (cm)", "Oogst (week)", "Lengte Einde (cm)", "Gewicht (kg)",
                "Rijpheid", "Teeltduur (dagen)", "Emmers Geoogst", "Stelen Geoogst",
                "Uitval (%)"]
    return kolommen, rijen_uitgebreid

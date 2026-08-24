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
            FOREIGN KEY (teeltvak_id) REFERENCES teeltvakken (id)
        )
    """)

    conn.commit()
    conn.close()


# --- TEELTVAKKEN ---

def get_of_maak_teeltvak(naam):
    """Geeft het id van een teeltvak terug; maakt het aan als het nog niet bestaat."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM teeltvakken WHERE naam = ?", (naam,))
    resultaat = cursor.fetchone()

    if resultaat:
        teeltvak_id = resultaat[0]
    else:
        cursor.execute("INSERT INTO teeltvakken (naam) VALUES (?)", (naam,))
        conn.commit()
        teeltvak_id = cursor.lastrowid

    conn.close()
    return teeltvak_id


def get_alle_teeltvakken():
    """Geeft een lijst van (id, naam) van alle teeltvakken terug."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, naam FROM teeltvakken ORDER BY naam")
    vakken = cursor.fetchall()
    conn.close()
    return vakken


# --- TEELTEN ---

def start_nieuwe_teelt(teeltvak_naam, datum_teelt_start):
    """
    Start een nieuwe teelt in een teeltvak.
    Maakt het teeltvak aan indien het nog niet bestaat.
    Geeft het id van de nieuwe teelt terug.
    """
    teeltvak_id = get_of_maak_teeltvak(teeltvak_naam)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO teelten (teeltvak_id, datum_teelt_start)
        VALUES (?, ?)
    """, (teeltvak_id, str(datum_teelt_start)))
    conn.commit()
    nieuwe_teelt_id = cursor.lastrowid
    conn.close()
    return nieuwe_teelt_id


def get_lopende_teelten():
    """
    Geeft alle teelten terug die nog niet zijn afgerond (geen oogstdatum),
    samen met de naam van het teeltvak. Handig voor selectboxen.
    Retourneert lijst van tuples: (teelt_id, label_voor_selectbox)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, v.naam, t.datum_teelt_start
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        WHERE t.datum_oogst IS NULL
        ORDER BY v.naam, t.datum_teelt_start
    """)
    rijen = cursor.fetchall()
    conn.close()

    resultaat = []
    for teelt_id, vak_naam, start_datum in rijen:
        label = f"{vak_naam} (gestart {start_datum})"
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


def update_oogst(teelt_id, datum_oogst, lengte_eind, oogstgewicht):
    """Slaat de oogstgegevens op voor een specifieke teelt."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teelten
        SET datum_oogst = ?, lengte_eind = ?, oogstgewicht = ?
        WHERE id = ?
    """, (str(datum_oogst), lengte_eind, oogstgewicht, teelt_id))
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
        SELECT t.id, v.naam, t.datum_teelt_start, t.datum_oogst
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        ORDER BY v.naam, t.datum_teelt_start DESC
    """)
    rijen = cursor.fetchall()
    conn.close()

    resultaat = []
    for teelt_id, vak_naam, start_datum, oogst_datum in rijen:
        status = "afgerond" if oogst_datum else "lopend"
        label = f"{vak_naam} - gestart {start_datum} ({status})"
        resultaat.append((teelt_id, label))
    return resultaat


def get_teelt_by_id(teelt_id):
    """Geeft alle gegevens van één teelt terug als dict, of None als niet gevonden."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, v.naam, t.datum_teelt_start, t.datum_half, t.lengte_half,
               t.datum_oogst, t.lengte_eind, t.oogstgewicht
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
        "datum_teelt_start": rij[2],
        "datum_half": rij[3],
        "lengte_half": rij[4],
        "datum_oogst": rij[5],
        "lengte_eind": rij[6],
        "oogstgewicht": rij[7],
    }


def update_teelt_volledig(teelt_id, datum_teelt_start, datum_half, lengte_half,
                           datum_oogst, lengte_eind, oogstgewicht):
    """Overschrijft alle velden van een bestaande teelt (gebruikt bij handmatige correctie)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teelten
        SET datum_teelt_start = ?, datum_half = ?, lengte_half = ?,
            datum_oogst = ?, lengte_eind = ?, oogstgewicht = ?
        WHERE id = ?
    """, (
        str(datum_teelt_start) if datum_teelt_start else None,
        str(datum_half) if datum_half else None,
        lengte_half,
        str(datum_oogst) if datum_oogst else None,
        lengte_eind,
        oogstgewicht,
        teelt_id
    ))
    conn.commit()
    conn.close()


def delete_teelt(teelt_id):
    """Verwijdert een teelt permanent. Het teeltvak zelf blijft bestaan."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teelten WHERE id = ?", (teelt_id,))
    conn.commit()
    conn.close()


def get_overzicht_dataframe():
    """
    Geeft alle teelten terug inclusief teeltvaknaam, weeknummers en teeltduur.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            t.id,
            v.naam,
            t.datum_teelt_start,
            t.datum_half,
            t.lengte_half,
            t.datum_oogst,
            t.lengte_eind,
            t.oogstgewicht
        FROM teelten t
        JOIN teeltvakken v ON t.teeltvak_id = v.id
        ORDER BY v.naam, t.datum_teelt_start DESC
    """)
    
    rijen_uitgebreid = []
    for row in cursor.fetchall():
        teelt_id, naam, start, half_datum, half_lengte, oogst_datum, eind_lengte, gewicht = row
        
        start_week = get_weeknummer(start) if start else "-"
        teeltduur = get_teeltduur(start, oogst_datum) if (start and oogst_datum) else "-"
        
        rijen_uitgebreid.append((
            teelt_id,
            naam,
            f"{start} (week {start_week})" if start else "-",
            f"{half_datum} (week {get_weeknummer(half_datum)})" if half_datum else "-",
            half_lengte if half_lengte else "-",
            f"{oogst_datum} (week {get_weeknummer(oogst_datum)})" if oogst_datum else "-",
            eind_lengte if eind_lengte else "-",
            gewicht if gewicht else "-",
            teeltduur
        ))
    
    conn.close()
    
    kolommen = ["ID", "Teeltvak", "Start (week)", "Halverwege (week)",
                "Lengte Half (cm)", "Oogst (week)", "Lengte Einde (cm)", "Gewicht (kg)", "Teeltduur (dagen)"]
    return kolommen, rijen_uitgebreid

"""
Eenmalige migratie van de oude SQLite-database (teeltdata.db) naar PostgreSQL
(Supabase). Leest de connectiestring uit DATABASE_URL (zie .env), net als
database.py.

Gebruik:
    python migratie_sqlite_naar_postgres.py            # migreert als doel leeg is
    python migratie_sqlite_naar_postgres.py --force    # eerst doeltabellen legen

De id's blijven behouden zodat de onderlinge verwijzingen (teeltvak_id,
teelt_id) blijven kloppen. Daarna worden de SERIAL-sequences bijgewerkt zodat
nieuwe rijen weer een vrij id krijgen.
"""

import sqlite3
import sys

import database

SQLITE_BESTAND = "teeltdata.db"

# Volgorde is belangrijk vanwege de foreign keys.
TABELLEN = {
    "teeltvakken": ["id", "naam", "vaknummer"],
    "teelten": [
        "id", "teeltvak_id", "datum_teelt_start", "datum_half", "lengte_half",
        "datum_oogst", "lengte_eind", "oogstgewicht", "rijpheid",
        "aantal_planten", "code",
    ],
    "oogstregistraties": ["id", "teelt_id", "datum", "aantal_emmers"],
}


def main():
    force = "--force" in sys.argv

    database.init_db()

    sqlite_conn = sqlite3.connect(SQLITE_BESTAND)
    sqlite_conn.row_factory = sqlite3.Row
    scur = sqlite_conn.cursor()

    pg_conn = database.get_connection()
    pcur = pg_conn.cursor()

    try:
        # Controleer of het doel leeg is.
        niet_leeg = []
        for tabel in TABELLEN:
            pcur.execute(f"SELECT COUNT(*) FROM {tabel}")
            if pcur.fetchone()[0] > 0:
                niet_leeg.append(tabel)

        if niet_leeg and not force:
            print(
                "Doeltabellen bevatten al data: "
                + ", ".join(niet_leeg)
                + "\nDraai opnieuw met --force om ze eerst te legen, of ruim ze "
                "handmatig op."
            )
            return

        if niet_leeg and force:
            for tabel in reversed(list(TABELLEN)):
                pcur.execute(f"DELETE FROM {tabel}")
            print("Doeltabellen geleegd.")

        # Kopieer per tabel.
        for tabel, kolommen in TABELLEN.items():
            rijen = scur.execute(
                f"SELECT {', '.join(kolommen)} FROM {tabel}"
            ).fetchall()

            if not rijen:
                print(f"{tabel}: 0 rijen (overgeslagen)")
                continue

            placeholders = ", ".join(["%s"] * len(kolommen))
            insert_sql = (
                f"INSERT INTO {tabel} ({', '.join(kolommen)}) "
                f"VALUES ({placeholders})"
            )
            pcur.executemany(
                insert_sql, [tuple(rij[k] for k in kolommen) for rij in rijen]
            )
            print(f"{tabel}: {len(rijen)} rijen gekopieerd")

            # Zet de SERIAL-sequence op het hoogste id.
            pcur.execute(
                f"SELECT setval(pg_get_serial_sequence('{tabel}', 'id'), "
                f"(SELECT COALESCE(MAX(id), 1) FROM {tabel}))"
            )

        pg_conn.commit()

        # Controle achteraf.
        print("\nControle (SQLite -> PostgreSQL):")
        for tabel in TABELLEN:
            s = scur.execute(f"SELECT COUNT(*) FROM {tabel}").fetchone()[0]
            pcur.execute(f"SELECT COUNT(*) FROM {tabel}")
            p = pcur.fetchone()[0]
            vlag = "OK" if s == p else "!! VERSCHIL"
            print(f"  {tabel}: {s} -> {p}  {vlag}")

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()

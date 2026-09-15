"""Kopieert alle data van Supabase naar de PostgreSQL op de NAS.

Supabase wordt read-only geopend; er wordt daar niets gewijzigd of verwijderd.
Alleen de NAS-kant wordt geschreven.
"""
import os
import re
import sys

import psycopg2

ENV_BESTAND = r"C:\Users\Job\Downloads\VEMteelt.env"
NAS_ENV_BESTAND = r"C:\Users\Job\OneDrive\Python\.env.nas"

# Volgorde is belangrijk: ouders voor kinderen (foreign keys).
TABELLEN = [
    "teeltvakken",
    "teelten",
    "oogstregistraties",
    "gebruikers",
    "wijzigingenlog",
    "klimaatdata_dag",
    "teeltplanning",
    "watergift_dag",
    "planning_weekdoel",
    "app_instelling",
    "energiedata_dag",
]

# Tabellen met een auto-ophogende id; de sequence moet na de import bijgewerkt.
SEQUENCES = {
    "teeltvakken": "id",
    "teelten": "id",
    "oogstregistraties": "id",
    "wijzigingenlog": "id",
    "klimaatdata_dag": "id",
    "teeltplanning": "id",
    "watergift_dag": "id",
    "energiedata_dag": "id",
}


def lees_database_url(pad):
    with open(pad, encoding="utf-8") as f:
        for regel in f:
            match = re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\n]+)"?', regel)
            if match:
                return match.group(1)
    sys.exit(f"Geen DATABASE_URL gevonden in {pad}")


bron = psycopg2.connect(lees_database_url(ENV_BESTAND))
bron.set_session(readonly=True)
print("Verbonden met Supabase (read-only)")

doel = psycopg2.connect(lees_database_url(NAS_ENV_BESTAND))
print("Verbonden met NAS")

bron_cur = bron.cursor()
doel_cur = doel.cursor()

print("\nKopieren:")
resultaat = []

for tabel in TABELLEN:
    bron_cur.execute(f"SELECT * FROM {tabel}")
    rijen = bron_cur.fetchall()
    kolommen = [d[0] for d in bron_cur.description]

    doel_cur.execute(f"TRUNCATE TABLE {tabel} CASCADE")

    if rijen:
        placeholders = ",".join(["%s"] * len(kolommen))
        kolomlijst = ",".join(f'"{k}"' for k in kolommen)
        doel_cur.executemany(
            f"INSERT INTO {tabel} ({kolomlijst}) VALUES ({placeholders})", rijen
        )

    if tabel in SEQUENCES and rijen:
        kolom = SEQUENCES[tabel]
        doel_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{tabel}', '{kolom}'),"
            f" COALESCE((SELECT MAX({kolom}) FROM {tabel}), 1))"
        )

    doel.commit()
    print(f"  {tabel:<20} {len(rijen):>6} rijen")
    resultaat.append((tabel, len(rijen)))

print("\nControle (bron vs NAS):")
alles_goed = True
for tabel, verwacht in resultaat:
    doel_cur.execute(f"SELECT COUNT(*) FROM {tabel}")
    werkelijk = doel_cur.fetchone()[0]
    status = "ok" if werkelijk == verwacht else "AFWIJKING"
    if werkelijk != verwacht:
        alles_goed = False
    print(f"  {tabel:<20} {verwacht:>6} / {werkelijk:<6} {status}")

bron.close()
doel.close()

print("\nKlaar." if alles_goed else "\nLet op: er zijn afwijkingen.")

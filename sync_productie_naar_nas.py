"""
Kopieert de productiedatabase (Supabase) naar de PostgreSQL op de NAS, zodat
de NAS een verse kopie heeft (bijv. wekelijks via de Taakplanner).

Supabase wordt alleen gelezen (read-only sessie); er wordt daar nooit iets
gewijzigd of verwijderd. Op de NAS wordt alles in één transactie vervangen:
gaat er onderweg iets mis, dan blijft de NAS-database zoals hij was.
Alles wat alleen op de NAS is ingevoerd, is na een kopie weg.

Op de NAS (Taakplanner, Door gebruiker gedefinieerd script, root), vanuit de
map met docker-compose.yml:
    docker run --rm --network vemteelt_default --env-file .env --env-file .env.taak \\
        vemteelt-app:latest python sync_productie_naar_nas.py
    - .env.taak levert DATABASE_URL = Supabase (de bron)
    - .env levert DB_WACHTWOORD; het doel is dan de db-container (host "db")

Vanaf een laptop (bron .env.productie, doel .env in deze map):
    python sync_productie_naar_nas.py --lokaal
"""
import argparse
import os
import re
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

HIER = os.path.dirname(os.path.abspath(__file__))


def lees_database_url(pad):
    with open(pad, encoding="utf-8") as f:
        for regel in f:
            match = re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\n]+)"?', regel)
            if match:
                return match.group(1).strip()
    sys.exit(f"FOUT: geen DATABASE_URL in {pad}")


def bepaal_urls(lokaal):
    """(bron, doel), met controles dat de bron Supabase is en het doel niet."""
    if lokaal:
        bron = lees_database_url(os.path.join(HIER, ".env.productie"))
        doel = lees_database_url(os.path.join(HIER, ".env"))
    else:
        bron = os.environ.get("DATABASE_URL", "")
        wachtwoord = os.environ.get("DB_WACHTWOORD")
        if not wachtwoord:
            sys.exit("FOUT: DB_WACHTWOORD ontbreekt (geef .env mee met --env-file).")
        doel = f"postgresql://vem:{wachtwoord}@{os.environ.get('NAS_DB_HOST', 'db')}:5432/vem_teelt"
    if "supabase" not in bron:
        sys.exit("GESTOPT: de bron is niet de productiedatabase (Supabase).")
    if "supabase" in doel:
        sys.exit("GESTOPT: het doel is Supabase. Dit script schrijft nooit naar productie.")
    return bron, doel


def tabellen_in_volgorde(cursor, tabellen):
    """De tabellen zo gesorteerd dat een tabel na de tabellen komt waarnaar hij verwijst."""
    cursor.execute("""
        SELECT kind.relname, ouder.relname
        FROM pg_constraint c
        JOIN pg_class kind ON kind.oid = c.conrelid
        JOIN pg_class ouder ON ouder.oid = c.confrelid
        JOIN pg_namespace n ON n.oid = kind.relnamespace
        WHERE c.contype = 'f' AND n.nspname = 'public'
    """)
    ouders = {t: set() for t in tabellen}
    for kind, ouder in cursor.fetchall():
        if kind in ouders and ouder in ouders and kind != ouder:
            ouders[kind].add(ouder)
    volgorde, gedaan = [], set()
    while len(volgorde) < len(tabellen):
        klaar = sorted(t for t in tabellen if t not in gedaan and ouders[t] <= gedaan)
        if not klaar:
            sys.exit(f"FOUT: kringverwijzing tussen {sorted(set(tabellen) - gedaan)}")
        volgorde += klaar
        gedaan.update(klaar)
    return volgorde


def kolommen(cursor, tabel):
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position
    """, (tabel,))
    return [r[0] for r in cursor.fetchall()]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lokaal", action="store_true", help="bron .env.productie, doel .env (vanaf een laptop)")
    args = parser.parse_args()
    begin = datetime.now()
    bron_url, doel_url = bepaal_urls(args.lokaal)

    # Eerst het schema op de NAS bijwerken met de migraties uit database.py,
    # zodat nieuwe tabellen en kolommen van productie er ook zijn.
    os.environ["DATABASE_URL"] = doel_url
    sys.path.insert(0, HIER)
    from database import init_db
    init_db()

    bron = psycopg2.connect(bron_url)
    bron.set_session(readonly=True)
    doel = psycopg2.connect(doel_url)
    bron_cur, doel_cur = bron.cursor(), doel.cursor()

    bron_cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    bron_tabellen = {r[0] for r in bron_cur.fetchall()}
    doel_cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    doel_tabellen = {r[0] for r in doel_cur.fetchall()}
    tabellen = tabellen_in_volgorde(doel_cur, sorted(bron_tabellen & doel_tabellen))
    for tabel in sorted(bron_tabellen - doel_tabellen):
        print(f"LET OP: {tabel} staat niet op de NAS en wordt overgeslagen.")

    telling = []
    try:
        # Alles in één transactie: pas bij de commit is de NAS vervangen.
        doel_cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tabellen) + " CASCADE")
        for tabel in tabellen:
            gedeeld = [k for k in kolommen(bron_cur, tabel) if k in set(kolommen(doel_cur, tabel))]
            kolomlijst = ", ".join(f'"{k}"' for k in gedeeld)
            bron_cur.execute(f'SELECT {kolomlijst} FROM "{tabel}"')
            rijen = bron_cur.fetchall()
            if rijen:
                # In blokken: rij voor rij kost duizenden heen-en-weertjes.
                execute_values(doel_cur, f'INSERT INTO "{tabel}" ({kolomlijst}) VALUES %s', rijen, page_size=1000)
            if "id" in gedeeld:
                doel_cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (tabel,))
                sequence = doel_cur.fetchone()[0]
                if sequence:
                    doel_cur.execute(
                        f'SELECT setval(%s, COALESCE((SELECT MAX(id) FROM "{tabel}"), 0) + 1, false)', (sequence,)
                    )
            telling.append((tabel, len(rijen)))

        # Controle vóór de commit: evenveel rijen als in productie.
        afwijkingen = []
        for tabel, verwacht in telling:
            doel_cur.execute(f'SELECT COUNT(*) FROM "{tabel}"')
            if doel_cur.fetchone()[0] != verwacht:
                afwijkingen.append(tabel)
        if afwijkingen:
            raise RuntimeError(f"aantallen wijken af in {', '.join(afwijkingen)}")
        doel.commit()
    except Exception as fout:
        doel.rollback()
        print(f"FOUT: {fout}. De NAS-database is ongewijzigd gebleven.", file=sys.stderr)
        sys.exit(1)
    finally:
        bron.close()
        doel.close()

    duur = (datetime.now() - begin).seconds
    print(f"[{begin:%d-%m-%y %H:%M}] Productie naar NAS gekopieerd in {duur} s: "
          + ", ".join(f"{t} {n}" for t, n in telling))


if __name__ == "__main__":
    main()

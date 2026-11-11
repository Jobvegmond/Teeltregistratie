"""Tests voor database.init_db: het volledige schema alleen als het veranderd is (geen DDL-slot bij elke start)."""
import unittest
from contextlib import contextmanager
from unittest import mock

import database


class NepCursor:
    def __init__(self, db):
        self.db, self.rij = db, None

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.db.log.append(sql)
        if sql.startswith("SELECT to_regclass"):
            self.rij = ("schema_versie",) if self.db.tabel else (None,)
        elif sql.startswith("SELECT waarde FROM schema_versie"):
            self.rij = (self.db.waarde,) if self.db.waarde else None
        elif sql.startswith("CREATE TABLE IF NOT EXISTS schema_versie"):
            self.db.tabel = True
        elif sql.startswith("INSERT INTO schema_versie"):
            self.db.waarde = params[0]

    def fetchone(self):
        return self.rij


class NepDb:
    def __init__(self, tabel=False, waarde=None):
        self.tabel, self.waarde, self.log = tabel, waarde, []

    @contextmanager
    def verbinding(self):
        yield mock.Mock(cursor=lambda: NepCursor(self))


class TestInitDb(unittest.TestCase):
    def draai(self, db):
        volledig = mock.Mock()
        vingerafdruk = database.schema_vingerafdruk()      # vóór het vervangen van _init_db_volledig
        with mock.patch.object(database, "get_connection", db.verbinding), \
                mock.patch.object(database, "_init_db_volledig", volledig), \
                mock.patch.object(database, "schema_vingerafdruk", lambda: vingerafdruk):
            database.init_db()
        return volledig

    def test_eerste_keer_volledig_en_vingerafdruk_opgeslagen(self):
        db = NepDb()
        self.assertEqual(self.draai(db).call_count, 1)
        self.assertEqual(db.waarde, database.schema_vingerafdruk())
        # met een advisory lock voor de duur van de transactie
        self.assertTrue(any("pg_advisory_xact_lock" in s for s in db.log))

    def test_zelfde_schema_geen_ddl(self):
        db = NepDb(tabel=True, waarde=database.schema_vingerafdruk())
        self.assertEqual(self.draai(db).call_count, 0)
        self.assertFalse(any(s.startswith(("CREATE", "ALTER")) or "advisory" in s for s in db.log))

    def test_ander_schema_volledig(self):
        db = NepDb(tabel=True, waarde="oud")
        self.assertEqual(self.draai(db).call_count, 1)
        self.assertEqual(db.waarde, database.schema_vingerafdruk())

    def test_vingerafdruk_volgt_de_tabellen(self):
        oud = database.schema_vingerafdruk()
        with mock.patch.object(database, "NOTIFICATIE_WEG_TABEL", database.NOTIFICATIE_WEG_TABEL + " -- nieuw"):
            self.assertNotEqual(database.schema_vingerafdruk(), oud)
        self.assertEqual(database.schema_vingerafdruk(), oud)


if __name__ == "__main__":
    unittest.main()

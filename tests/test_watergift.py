"""Tests voor logic/watergift.py en de adapter voor behandelingen."""
import unittest
from datetime import date

from integrations import behandelingen as beh
from logic import watergift as wg

WATERSYSTEMEN = {1: {1: None}, 3: {1: [1, 2, 3], 2: [4, 5]}}


class TestKoppeling(unittest.TestCase):
    def test_alle_vakken(self):
        self.assertEqual(wg.watersysteem_van_vak(WATERSYSTEMEN, 1, 17), 1)
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 1, 1, [3, 1, 2]), [1, 2, 3])

    def test_vakken_per_systeem(self):
        self.assertEqual(wg.watersysteem_van_vak(WATERSYSTEMEN, 3, 5), 2)
        self.assertIsNone(wg.watersysteem_van_vak(WATERSYSTEMEN, 3, 9))
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 3, 2, range(1, 40)), [4, 5])
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 3, 7, range(1, 40)), [])


class NepDatabase:
    def __init__(self):
        self.middelen, self.behandelingen = {}, []

    def upsert_middel(self, middel, bron):
        return self.middelen.setdefault((bron, middel.code), len(self.middelen) + 1)

    def upsert_behandeling(self, behandeling, middel_id, bron):
        self.behandelingen.append((bron, behandeling.extern_id, middel_id))


class NepBron:
    naam = "test"

    def fetch_behandelingen(self, van, tot):
        m = beh.Middel("ENT", "Entonem", "biologie")
        return [beh.Behandeling(date(2026, 9, 28), 3, 12, m, extern_id="a"),
                beh.Behandeling(date(2026, 9, 28), 3, 13, m, extern_id="b")]


class TestBehandelingen(unittest.TestCase):
    def test_lege_bron_schrijft_niets(self):
        db = NepDatabase()
        self.assertEqual(beh.synchroniseer(beh.LegeBron(), date(2026, 9, 1), date(2026, 9, 30), database=db), 0)
        self.assertEqual((db.middelen, db.behandelingen), ({}, []))

    def test_bron_via_dezelfde_vorm(self):
        db = NepDatabase()
        self.assertEqual(beh.synchroniseer(NepBron(), date(2026, 9, 1), date(2026, 9, 30), database=db), 2)
        self.assertEqual(db.middelen, {("test", "ENT"): 1})
        self.assertEqual(db.behandelingen, [("test", "a", 1), ("test", "b", 1)])


if __name__ == "__main__":
    unittest.main()

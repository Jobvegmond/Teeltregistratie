"""Tests voor logic/opzoeken.py: zoeken, perioden, rijen bij het juiste vak en de samenvatting."""
import unittest
from datetime import date

from logic import opzoeken

VANDAAG = date(2026, 10, 8)
VAKKEN = [
    {"id": 1, "tuin_id": 2, "vak": 12, "afdeling": 3, "code": "2626312", "start": "2026-06-22",
     "oogstdatum": "2026-08-31", "florgib": "2026-07-20", "planten": 33000, "ras": None},
    {"id": 2, "tuin_id": 2, "vak": 12, "afdeling": 3, "code": "2636312", "start": "2026-09-01",
     "oogstdatum": None, "florgib": None, "planten": 32000, "ras": None},
    {"id": 3, "tuin_id": 1, "vak": 12, "afdeling": 2, "code": "2636112", "start": "2026-09-02",
     "oogstdatum": None, "florgib": None, "planten": None, "ras": "Bridal"},
]


class TestZoek(unittest.TestCase):
    def test_code_en_vaknummer(self):
        self.assertEqual(opzoeken.zoek(VAKKEN, "2626312")[0]["id"], 1)
        # Vaknummer in één tuin: de laatst geplante teelt.
        alleen_tuin3 = [v for v in VAKKEN if v["tuin_id"] == 2]
        self.assertEqual(opzoeken.zoek(alleen_tuin3, "12")[0]["id"], 2)
        # In beide tuinen: geen vak maar een melding.
        vak, melding = opzoeken.zoek(VAKKEN, "12")
        self.assertIsNone(vak)
        self.assertIn("beide tuinen", melding)
        self.assertEqual(opzoeken.zoek(VAKKEN, ""), (None, None))
        self.assertIsNone(opzoeken.zoek(VAKKEN, "9999999")[0])


class TestRijen(unittest.TestCase):
    def setUp(self):
        self.p = opzoeken.perioden(VAKKEN[:2], VANDAAG)

    def test_periode_tot_oogst_of_vandaag(self):
        self.assertEqual(self.p[1][3:], (date(2026, 6, 22), date(2026, 8, 31)))
        self.assertEqual(self.p[2][3:], (date(2026, 9, 1), VANDAAG))

    def test_bij_vak_kiest_de_juiste_ronde(self):
        rijen = [{"tuin_id": 2, "vak": 12, "datum": "2026-08-30", "l": 5},     # ronde 1
                 {"tuin_id": 2, "vak": 12, "datum": "2026-09-15", "l": 6},     # ronde 2
                 {"tuin_id": 2, "vak": 13, "datum": "2026-09-15", "l": 7},     # ander vak
                 {"tuin_id": 1, "vak": 12, "datum": "2026-09-15", "l": 8}]     # andere tuin
        uit = opzoeken.bij_vak(rijen, self.p, {1: "2626312", 2: "2636312"})
        self.assertEqual([(r["l"], r["code"]) for r in uit], [(5, "2626312"), (6, "2636312")])

    def test_bij_afdeling_en_tuin(self):
        rijen = [{"tuin_id": 2, "afdeling": 3, "datum": "2026-07-01"}, {"tuin_id": 2, "afdeling": 4, "datum": "2026-07-01"},
                 {"tuin_id": 2, "afdeling": 3, "datum": "2026-08-31"}, {"tuin_id": 2, "afdeling": 3, "datum": "2026-06-01"}]
        self.assertEqual(len(opzoeken.bij_afdeling(rijen, self.p)), 2)
        dagen = [{"tuin_id": 2, "datum": "2026-07-01"}, {"tuin_id": 2, "datum": "2026-06-01"},
                 {"tuin_id": 1, "datum": "2026-07-01"}]
        self.assertEqual(opzoeken.bij_tuin(dagen, self.p), [dagen[0]])


class TestSamenvatting(unittest.TestCase):
    def test_uitval_alleen_over_afgeronde_vakken(self):
        emmers = [{"teelt_id": 1, "emmers": 300}, {"teelt_id": 2, "emmers": 10}]
        s = opzoeken.samenvatting(VAKKEN[:2], emmers)
        self.assertEqual((s["vakken"], s["lopend"], s["emmers"], s["stelen"]), (2, 1, 310, 31000))
        self.assertAlmostEqual(s["uitval"], (33000 - 30000) / 33000 * 100)
        self.assertEqual((s["eerste_start"], s["laatste_start"]), (date(2026, 6, 22), date(2026, 9, 1)))
        self.assertEqual(s["rassen"], ["Cameron"])
        self.assertEqual(s["planten"], 65000)


if __name__ == "__main__":
    unittest.main()

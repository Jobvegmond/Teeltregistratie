"""Tests voor logic/ruwe_data.py: de querybouwer en het zoeken."""
import re
import unittest
from datetime import date

from logic import ruwe_data as rd


class TestQuery(unittest.TestCase):
    def test_tuin_periode_en_vakken_als_parameters(self):
        sql, params = rd.query(rd.tabel("Watergift per dag"), 3, date(2026, 9, 1), date(2026, 9, 30), [7, 8])
        self.assertIn("WHERE tuin_id = %s AND SUBSTRING(CAST(datum AS TEXT), 1, 10) BETWEEN %s AND %s "
                      "AND vaknummer IN (%s, %s)", sql)
        self.assertTrue(sql.endswith("ORDER BY datum, vaknummer"))
        self.assertEqual(params, [3, "2026-09-01", "2026-09-30", 7, 8])

    def test_zonder_periode_of_vak(self):
        sql, params = rd.query(rd.tabel("Vakgegevens"), 1, date(2026, 9, 1), date(2026, 9, 30), [3])
        self.assertNotIn("BETWEEN", sql)                     # vakgegevens hebben geen datum
        self.assertEqual(params, [1, 3])
        sql, params = rd.query(rd.tabel("Klimaat per dag"), 1, vakken=[3])
        self.assertNotIn("IN (", sql)                        # klimaat is per afdeling, niet per vak
        self.assertEqual(params, [1])

    def test_geen_gevoelige_tabellen(self):
        tekst = " ".join(t.select for t in rd.TABELLEN)
        for verboden in ("gebruikers", "wachtwoord", "app_instelling", "wijzigingenlog"):
            self.assertNotIn(verboden, tekst)
        self.assertTrue(all(re.match(r"^SELECT ", t.select) for t in rd.TABELLEN))
        self.assertEqual(len({t.naam for t in rd.TABELLEN}), len(rd.TABELLEN))


class TestZoek(unittest.TestCase):
    def test_zoekt_in_alle_kolommen(self):
        rijen = [{"vak": 12, "code": "263912", "tekst": "Trips gezien"}, {"vak": 3, "code": "263903", "tekst": None}]
        self.assertEqual(rd.zoek(rijen, "trips"), [rijen[0]])
        self.assertEqual(rd.zoek(rijen, "2639"), rijen)
        self.assertEqual(rd.zoek(rijen, " "), rijen)


if __name__ == "__main__":
    unittest.main()

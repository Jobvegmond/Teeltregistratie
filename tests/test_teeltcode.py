"""Tests voor database.genereer_teelt_code: jaar + plantweek + tuin + vak (sinds 2.7.0)."""
import unittest
from datetime import date

import database


class TestTeeltcode(unittest.TestCase):
    def test_tuin_tussen_week_en_vak(self):
        self.assertEqual(database.genereer_teelt_code(date(2026, 8, 17), 1, 3), "2634301")
        self.assertEqual(database.genereer_teelt_code(date(2026, 8, 17), 1, 1), "2634101")
        self.assertEqual(database.genereer_teelt_code("2026-02-25", 39, 3), "2609339")

    def test_iso_jaar_van_de_plantweek(self):
        # 29-12-2025 valt in week 1 van 2026.
        self.assertEqual(database.genereer_teelt_code(date(2025, 12, 29), 4, 1), "2601104")


if __name__ == "__main__":
    unittest.main()

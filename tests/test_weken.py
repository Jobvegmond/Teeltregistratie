"""Tests voor logic/weken.py: de week loopt van zondag t/m zaterdag."""
import unittest
from datetime import date

from logic import weken


class TestWeken(unittest.TestCase):
    def test_zondag_hoort_bij_de_nieuwe_week(self):
        self.assertEqual(weken.weeknummer(date(2026, 9, 27)), 40)   # zondag
        self.assertEqual(weken.weeknummer(date(2026, 9, 26)), 39)   # zaterdag
        self.assertEqual(weken.weeknummer(date(2026, 9, 28)), 40)   # maandag
        self.assertEqual(weken.week_begin(date(2026, 10, 3)), date(2026, 9, 27))

    def test_jaargrens(self):
        # zondag 27-12-2026 begint week 53 van 2026; zondag 03-01-2027 week 1 van 2027
        self.assertEqual(weken.week_sleutel(date(2026, 12, 27)), (2026, 53))
        self.assertEqual(weken.week_sleutel(date(2027, 1, 3)), (2027, 1))
        self.assertEqual(weken.week_dagen(2027, 1), (date(2027, 1, 3), date(2027, 1, 9)))

    def test_week_53_bestaat_niet_elk_jaar(self):
        self.assertEqual(weken.laatste_week(2025), 52)
        self.assertEqual(weken.week_zondag(2025, 53), weken.week_zondag(2025, 52))


if __name__ == "__main__":
    unittest.main()

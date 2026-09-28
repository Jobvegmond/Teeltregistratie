"""Tests voor logic/perioden.py: bladeren, laatste volledige periode en de vergelijkingsperiode."""
import unittest
from datetime import date

from logic import perioden as p

MAANDAG = date(2026, 9, 28)   # maandag, week 40


class TestPerioden(unittest.TestCase):
    def test_laatste_volledige_en_bladeren(self):
        self.assertEqual(p.laatste_volledige("Week", MAANDAG), (2026, 39))
        self.assertEqual(p.laatste_volledige("Maand", MAANDAG), (2026, 8))
        self.assertEqual(p.verschuif((2026, 1), "Week", -1), (2025, 52))
        self.assertEqual(p.verschuif((2026, 12), "Maand", 1), (2027, 1))
        self.assertEqual(p.verschuif((2026, 1), "Kwartaal", -2), (2025, 3))

    def test_venster_loopt_tot_gisteren(self):
        self.assertEqual(p.venster((2026, 40), "Week", MAANDAG), (date(2026, 9, 28), date(2026, 9, 27), True))
        van, tot, loopt = p.venster((2026, 9), "Maand", date(2026, 9, 16))
        self.assertEqual((van, tot, loopt), (date(2026, 9, 1), date(2026, 9, 15), True))
        self.assertFalse(p.venster((2026, 39), "Week", MAANDAG)[2])

    def test_vergelijking_vorig_jaar_en_vorige(self):
        self.assertEqual(p.vergelijk_venster((2026, 39), "Week", "vorig_jaar", MAANDAG),
                         (date(2025, 9, 22), date(2025, 9, 28), "Wk 39 - 2025"))
        self.assertEqual(p.vergelijk_venster((2026, 39), "Week", "vorige", MAANDAG),
                         (date(2026, 9, 14), date(2026, 9, 20), "Wk 38 - 2026"))

    def test_lopende_periode_tot_even_ver(self):
        # September loopt t/m 15 september: augustus en september 2025 ook t/m de 15e.
        vandaag = date(2026, 9, 16)
        self.assertEqual(p.vergelijk_venster((2026, 9), "Maand", "vorige", vandaag)[:2],
                         (date(2026, 8, 1), date(2026, 8, 15)))
        self.assertEqual(p.vergelijk_venster((2026, 9), "Maand", "vorig_jaar", vandaag)[:2],
                         (date(2025, 9, 1), date(2025, 9, 15)))

    def test_week_53_bestaat_niet_elk_jaar(self):
        # 2026 heeft week 53; 2025 niet: dan de laatste week van 2025.
        self.assertEqual(p.vergelijk_venster((2026, 53), "Week", "vorig_jaar", date(2027, 2, 1))[:2],
                         (date(2025, 12, 22), date(2025, 12, 28)))


if __name__ == "__main__":
    unittest.main()

"""Tests voor logic/mailopmaak.py: tegels, staafgrafiekjes en tabellen voor de rapportmails."""
import unittest
from datetime import date, timedelta

from logic import mailopmaak as mo

DAGEN = [date(2026, 11, 3) - timedelta(days=13 - i) for i in range(14)]


class TestTegels(unittest.TestCase):
    def test_tegel_met_toon_eenheid_en_verschil(self):
        uit = mo.tegels([{"label": "Etmaal", "waarde": "14,2", "eenheid": "°C", "sub": "+0,3 t.o.v. vorige dag"},
                         {"label": "Afw.", "waarde": "+0,8", "toon": "let op"}], label="Tuin 3")
        self.assertIn("Tuin 3", uit)
        self.assertIn("+0,3 t.o.v. vorige dag", uit)
        self.assertIn(mo.ORANJE, uit)

    def test_meer_dan_zes_tegels_lopen_door(self):
        uit = mo.tegels([{"label": str(i), "waarde": "1"} for i in range(8)], breedte=6)
        self.assertEqual(uit.count("<table"), 2)

    def test_verschil_tekst(self):
        self.assertEqual(mo.verschil_tekst(14.2, 13.9, 1, "°C"), "+0,3 °C")
        self.assertIsNone(mo.verschil_tekst(14.2, None))


class TestStaafgrafiek(unittest.TestCase):
    def test_een_balk_per_dag_met_laatste_waarde_en_hint(self):
        waarden = [None] * 12 + [10.0, 20.0]
        uit = mo.staafgrafiek("RV", DAGEN, [("Tuin 3", waarden)], lambda v: mo.ROOD, "uur", 0, minimum=24)
        self.assertEqual(uit.count('valign="bottom"'), 14)
        self.assertIn("20", uit)                                  # laatste waarde achter de rij
        self.assertIn('title="3 nov: 20 uur"', uit)
        self.assertIn('title="1 nov: –"', uit)               # een dag zonder meting

    def test_schaal_is_gedeeld_en_het_minimum_geldt(self):
        uit = mo.staafgrafiek("x", DAGEN[:2], [("a", [12.0, 0.0]), ("b", [6.0, 0.0])], lambda v: mo.GROEN, hoogte=40,
                              minimum=24)
        self.assertIn('height="20"', uit)                          # 12 van 24 uur op 40 px
        self.assertIn('height="10"', uit)                          # 6 van 24 uur

    def test_tweezijdig_zet_negatieve_waarden_onder_de_streep(self):
        uit = mo.staafgrafiek("Afw", DAGEN[:2], [("Tuin 1", [1.0, -1.0])], lambda v: mo.BLAUW, "°C", 1,
                              tweezijdig=True, hoogte=30)
        self.assertIn('valign="top"', uit)
        self.assertEqual(uit.count('bgcolor="%s"' % mo.BLAUW), 2)   # beide balken (boven en onder) in de kleur

    def test_labels_om_de_week_bij_28_dagen(self):
        dagen = [date(2026, 11, 3) - timedelta(days=27 - i) for i in range(28)]
        uit = mo.staafgrafiek("x", dagen, [("a", [1.0] * 28)], lambda v: mo.GROEN)
        self.assertEqual(uit.count(">3 nov<"), 1)
        self.assertEqual(uit.count(">27 okt<"), 1)
        self.assertNotIn(">2 nov<", uit)


class TestTabel(unittest.TestCase):
    def test_rijen_als_lijst_en_als_dict(self):
        uit = mo.tabel(["A", "B"], [["x", "1"], {"A": "y", "B": "2"}])
        self.assertIn(">x<", uit)
        self.assertIn(">2<", uit)
        self.assertIn("text-align:right", uit)


if __name__ == "__main__":
    unittest.main()

"""Tests voor logic/watergift.py."""
import unittest
from datetime import date, timedelta

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


if __name__ == "__main__":
    unittest.main()


class TestSamenvatting(unittest.TestCase):
    def test_samenvatting_leeg_vak_telt_niet_mee(self):
        gift = {(1, date(2026, 9, 28)): 4.0, (2, date(2026, 9, 28)): 0.0}
        bezet = lambda vak, dag: vak == 1                     # vak 2 staat leeg
        uit = wg.samenvatting(gift, [1, 2], {1: 550, 2: 550}, bezet, date(2026, 9, 28), date(2026, 9, 29))
        self.assertEqual((uit["gift_per_dag"], uit["giftdagen"], uit["laatste"]), (2.0, 1, date(2026, 9, 28)))

    def test_weken_van_zondag_tot_zaterdag(self):
        self.assertEqual(wg.week_begin(date(2026, 9, 30)), date(2026, 9, 27))     # wo → zo ervoor
        self.assertEqual(wg.week_begin(date(2026, 9, 27)), date(2026, 9, 27))     # zo blijft zo
        self.assertEqual(wg.weeknummer(date(2026, 9, 27)), 40)                     # zo hoort bij de week erna
        self.assertEqual(wg.weeknummer(date(2026, 10, 3)), 40)                     # za


class TestBehandelingen(unittest.TestCase):
    """De kleur van een behandeling volgt de belangrijkste soort; de middelen staan in de tooltip."""

    def test_hoofdsoort(self):
        per_dag = wg.behandelingen_per_vak_dag([{"vaknummer": 3, "datum": "2026-09-29", "type": "biologie"},
                                                {"vaknummer": 3, "datum": "2026-09-29", "type": "gewasbescherming"}])
        self.assertEqual(list(per_dag), [(3, date(2026, 9, 29))])
        self.assertEqual(wg.hoofdsoort(per_dag[(3, date(2026, 9, 29))]), "gewasbescherming")   # gaat voor biologie
        self.assertEqual(wg.hoofdsoort([]), None)

    def test_tekst(self):
        self.assertEqual(wg.behandeling_tekst({"naam": "Rizolex vloeibaar", "dosering": 900.0, "eenheid": "ml",
                                               "mix": "100 l", "doel": "Rhizoctonia soorten"}),
                         "Rizolex vloeibaar 900 ml in 100 l (tegen Rhizoctonia soorten)")
        self.assertEqual(wg.behandeling_tekst({"middel": "Power Food 3.0", "dosering": 2.5, "eenheid": "kg"}),
                         "Power Food 3.0 2,5 kg")

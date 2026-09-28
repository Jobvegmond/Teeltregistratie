"""Tests voor logic/kengetallen.py (de vergelijkingstabellen)."""
import unittest

from logic import kengetallen as kg


class TestKengetallen(unittest.TestCase):
    def test_verschil_klasse_naar_betekenis(self):
        self.assertEqual(kg.verschil_klasse(5, kg.RICHTING["stelen"]), "beter")
        self.assertEqual(kg.verschil_klasse(-5, kg.RICHTING["stelen"]), "slechter")
        self.assertEqual(kg.verschil_klasse(1.2, kg.RICHTING["uitval"], 1), "slechter")
        self.assertEqual(kg.verschil_klasse(-1.2, kg.RICHTING["water"]), "beter")
        self.assertEqual(kg.verschil_klasse(3, kg.RICHTING.get("teeltduur")), "neutraal")
        self.assertEqual(kg.verschil_klasse(0.04, 1, 1), "neutraal")
        self.assertEqual(kg.verschil_klasse(None, 1), "leeg")

    def test_beste(self):
        self.assertEqual(kg.beste({"Tuin 1": 14.1, "Tuin 3": 4.0}, -1, 1), "Tuin 3")
        self.assertEqual(kg.beste({"Tuin 1": 51.6, "Tuin 3": 57.0}, 1, 1), "Tuin 3")
        self.assertIsNone(kg.beste({"Tuin 1": None, "Tuin 3": 715}, 1))       # maar één waarde
        self.assertIsNone(kg.beste({"Tuin 1": 60, "Tuin 3": 70}, 0))          # neutraal
        self.assertIsNone(kg.beste({"Tuin 1": 55.04, "Tuin 3": 55.01}, 1, 1))  # gelijk na afronden

    def test_totaal_vergelijkbaar(self):
        nu = {"Tuin 1": {"stelen": 10, "gewicht": None}, "Tuin 3": {"stelen": 20, "gewicht": 700}}
        toen = {"Tuin 1": {"stelen": None, "gewicht": None}, "Tuin 3": {"stelen": 18, "gewicht": 680}}
        ok = {"Tuin 1": False, "Tuin 3": True}
        self.assertFalse(kg.totaal_vergelijkbaar(nu, toen, "stelen", ok))     # tuin 1 oogstte toen niet
        self.assertTrue(kg.totaal_vergelijkbaar(nu, toen, "gewicht", ok))     # beide keren alleen tuin 3
        self.assertFalse(kg.totaal_vergelijkbaar(nu, toen, "gewicht", {"Tuin 3": False}))
        self.assertEqual(kg.bijdragers(nu, "gewicht"), frozenset({"Tuin 3"}))


if __name__ == "__main__":
    unittest.main()

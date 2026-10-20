"""Tests voor logic/teelt_rapport.py: welke teelten af zijn, en het rapport per tuin en per vak."""
import unittest
from datetime import date

from logic import teelt_rapport as tr
from tests.test_teeltvergelijking import regel, vak

TUINEN = [("Tuin 1", 1), ("Tuin 3", 3)]


def vakken():
    # Plantweek 32 van 2026: twee vakken in tuin 3, één in tuin 1, alle drie geoogst. Plantweek 33: één loopt nog.
    return [
        vak(regel(1, 3, 5, "2026-08-03", oogst="2026-09-22", half="2026-09-01", lengte_eind=80.0, stelen=30000.0,
                  aantal_planten=32000.0, oogstgewicht=650.0)),
        vak(regel(2, 3, 6, "2026-08-04", oogst="2026-09-24", lengte_eind=76.0, stelen=29000.0, aantal_planten=32000.0)),
        vak(regel(3, 1, 2, "2026-08-05", oogst="2026-09-20", lengte_eind=70.0), m2=883.2),
        vak(regel(4, 3, 7, "2026-08-10")),
    ]


class TestAfgerond(unittest.TestCase):
    def test_alleen_plantweken_waarvan_elk_vak_geoogst_is(self):
        af = tr.afgeronde_plantweken(vakken())
        self.assertEqual(list(af), [(2026, 32)])
        laatste, groep = af[(2026, 32)]
        self.assertEqual((laatste, len(groep)), (date(2026, 9, 24), 3))

    def test_onderwerp(self):
        self.assertEqual(tr.onderwerp((2026, 32)), "Teelt afgerond; plantweek 32 (2026)")


class TestBericht(unittest.TestCase):
    def test_samenvatting_en_per_vak(self):
        laatste, groep = tr.afgeronde_plantweken(vakken())[(2026, 32)]
        onderwerp, tekst, html = tr.bericht((2026, 32), groep, [], TUINEN, laatste, app_url="https://voorbeeld")
        self.assertEqual(onderwerp, "Teelt afgerond; plantweek 32 (2026)")
        self.assertIn("3 vakken (Tuin 1: 1, Tuin 3: 2)", tekst)
        self.assertIn("wk 39 do (24-09-2026)", tekst)          # do 24-09: week van zo 20-09 t/m za 26-09
        kolommen, samen = tr.samenvatting(groep, [], TUINEN)
        self.assertEqual(kolommen, ["Tuin 1", "Tuin 3", "Totaal", "Vorig jaar"])
        lengte = dict(samen)["Oogstlengte"]
        self.assertEqual((lengte["Tuin 3"], lengte["Vorig jaar"]), ("78,0 cm", "–"))   # (80 + 76) / 2, zelfde m²
        rijen = tr.per_vak(groep, dict((i, n) for n, i in TUINEN))
        self.assertEqual([(r["Tuin"], r["Vak"], r["Geplant"], r["Oogst"]) for r in rijen],
                         [("Tuin 1", "2", "wk 32 wo", "wk 39 zo"), ("Tuin 3", "5", "wk 32 ma", "wk 39 di"),
                          ("Tuin 3", "6", "wk 32 di", "wk 39 do")])
        self.assertNotIn("Code", rijen[0])
        self.assertNotIn("Afd.", rijen[0])
        self.assertNotIn("Planten", rijen[0])
        self.assertNotIn("Fase 1 d", rijen[0])
        self.assertIn("Uitval %", rijen[0])
        self.assertEqual(list(rijen[0])[-1], "Gewicht g")          # klimaat, water, energie en stek alleen bovenaan
        self.assertEqual(rijen[1]["Gewicht g"], "650")
        self.assertIn("<table", html)
        self.assertIn("Plantweek 32 (2026) is afgerond", html)


if __name__ == "__main__":
    unittest.main()

"""Tests voor logic/tuin_overzicht.py: kengetallen per afdeling, klimaat per uur, opvallend en gebeurtenissen."""
import unittest
from datetime import date

import pandas as pd

from logic import tuin_overzicht as to
from tests.test_tuinvergelijking import TOT, VAN, gegevens

HT = to.HELE_TUIN


def uur(rijen):
    return pd.DataFrame(rijen, columns=["afdeling", "tijdstip", "temp", "rv", "vd", "co2", "verwarming"])


class TestPerAfdeling(unittest.TestCase):
    def test_afdeling_rekent_als_een_tuin(self):
        u = to.tabelwaarden(gegevens(), None, 3, VAN, TOT)
        w = u["waarden"]
        self.assertEqual(u["kolommen"], ["Afd. 1", "Afd. 2", HT])
        self.assertEqual((w["Afd. 1"]["temp"], w["Afd. 2"]["temp"], w[HT]["temp"]), (19.0, 20.0, 19.5))
        # Water: vak 1 (afd. 1) 4 l/m² op één dag; per m² afdeling 4, per m² tuin 2.
        self.assertEqual((w["Afd. 1"]["water"], w[HT]["water"]), (4.0, 2.0))
        self.assertNotIn("water", w["Afd. 2"])
        # Gas alleen voor de hele kas.
        self.assertEqual(w[HT]["gas"], 700 / 1000)
        self.assertNotIn("gas", w["Afd. 1"])
        self.assertEqual(u["ontbreekt"]["Afd. 1"]["gas"], "Alleen voor de hele kas gemeten")
        # Bezetting: vak 1 tot de oogst op 25-09 (5 van 7 dagen), vak 2 leeg.
        self.assertAlmostEqual(w["Afd. 1"]["bezetting"], 5 / 7 * 100)
        self.assertEqual(w["Afd. 2"]["bezetting"], 0.0)

    def test_klimaat_per_uur(self):
        rijen = uur([(1, "2026-09-21 00:00", 15.0, 92.0, 1.0, 400.0, 15.0),
                     (1, "2026-09-21 01:00", 17.0, 80.0, 3.0, 600.0, 16.2),
                     (2, "2026-09-21 00:00", 14.0, 95.0, None, None, None),
                     (2, "2026-09-28 00:00", 1.0, 99.0, None, None, None)])     # buiten de periode
        u = to.tabelwaarden(gegevens(), rijen, 3, VAN, TOT)
        w, n = u["waarden"], u["n"]
        self.assertEqual((w["Afd. 1"]["temp_min"], w["Afd. 1"]["temp_max"]), (15.0, 17.0))
        self.assertEqual((w["Afd. 1"]["vd"], w["Afd. 1"]["co2"]), (2.0, 500.0))
        # Stooktemperatuur: gemiddeld 15,6, hoogste 16,2.
        self.assertAlmostEqual(w["Afd. 1"]["stook"], 15.6)
        self.assertEqual((w["Afd. 1"]["stook_max"], w[HT]["stook_max"]), (16.2, 16.2))
        self.assertEqual((n["Afd. 1"]["vd"], u["verwacht"]["Afd. 1"]["vd"]), (2, 7 * 24))
        # Uren RV ≥ 90 per 24 gemeten uren: afd. 1 1 van 2, afd. 2 1 van 1; tuin gewogen (500 m² elk).
        self.assertEqual((w["Afd. 1"]["rv_hoog"], w["Afd. 2"]["rv_hoog"], w[HT]["rv_hoog"]), (12.0, 24.0, 18.0))
        self.assertEqual((w[HT]["temp_min"], w[HT]["temp_max"]), (14.0, 17.0))
        self.assertEqual(w[HT]["vd"], 2.0)      # alleen afd. 1 heeft een vochtdeficit
        self.assertIn("klimaat per uur", u["ontbreekt"]["Afd. 2"]["vd"])


class TestTeeltstrategie(unittest.TestCase):
    def gegevens(self):
        g = gegevens()
        dagen = [str(date(2026, 9, 21 + i)) for i in range(7)]
        # Tuin 3: afd. 1 dag 20 / nacht 18,5 (DIF 1,5) op twee dagen, verder DIF 3; afd. 2 altijd DIF 3.
        g.klimaat = pd.DataFrame([{"tuin_id": 3, "afdeling": a, "datum": d, "temp_24h": 19.0,
                                   "temp_dag": 20.0, "temp_nacht": 18.5 if a == 1 and i < 2 else 17.0,
                                   "rv_24h": 80.0, "lichtsom": 1000.0}
                                  for i, d in enumerate(dagen) for a in (1, 2)])
        g.water = pd.DataFrame([
            {"tuin_id": 3, "vaknummer": 1, "datum": dagen[0], "liter_per_m2": 3.0, "ec": 1.6, "ph": 6.0},
            {"tuin_id": 3, "vaknummer": 1, "datum": dagen[1], "liter_per_m2": 1.0, "ec": 2.4, "ph": 6.4},
            {"tuin_id": 3, "vaknummer": 2, "datum": dagen[0], "liter_per_m2": 2.0, "ec": 1.5, "ph": 5.4},
            {"tuin_id": 3, "vaknummer": 2, "datum": dagen[1], "liter_per_m2": 0.0, "ec": 9.9, "ph": 9.9},  # geen gift
        ])
        return g

    def test_dif_en_water(self):
        u = to.tabelwaarden(self.gegevens(), None, 3, VAN, TOT)
        w = u["waarden"]
        self.assertAlmostEqual(w["Afd. 1"]["dif"], 3 - 1.5 * 2 / 7)
        # Vak 1: EC (1,6 × 3 + 2,4 × 1) / 4 = 1,8; hele tuin gewogen naar liters × 500 m².
        self.assertAlmostEqual(w["Afd. 1"]["ec"], 1.8)
        self.assertAlmostEqual(w[HT]["ec"], (1.6 * 3 + 2.4 + 1.5 * 2) / 6)

class TestGebeurtenissen(unittest.TestCase):
    def test_per_vak_op_datum(self):
        opm = [{"datum": "2026-09-22", "tuin_id": 1, "afdeling": 1, "vaknummer": 2, "code": "x", "teelt_id": 2,
                "categorie": "Ziekte", "tekst": "Meeldauw"},
               {"datum": "2026-09-22", "tuin_id": 3, "afdeling": 1, "vaknummer": 1, "code": "y", "teelt_id": 3,
                "categorie": None, "tekst": "andere tuin"}]
        rijen = to.gebeurtenissen(gegevens(), opm, 1, VAN, TOT)
        self.assertEqual([(r["datum"], r["soort"], r["vak"], r["tekst"]) for r in rijen], [
            (date(2026, 9, 22), "Opmerking", 2, "Ziekte: Meeldauw"),
            (date(2026, 9, 24), "Geplant", 2, "1.000 planten"),
            (date(2026, 9, 25), "Oogst", 1, "8 emmers"),
            (date(2026, 9, 27), "Afgerond", 1, "9 emmers in totaal"),
        ])
        self.assertEqual(to.samenvatting(rijen), "1 vak geplant · 8 emmers uit 1 vak · 1 vak afgerond · 1 opmerking")


if __name__ == "__main__":
    unittest.main()

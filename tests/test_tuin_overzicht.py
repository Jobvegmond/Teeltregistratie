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
        rijen = uur([(1, "2026-09-21 00:00", 15.0, 92.0, 1.0, 400.0, 40.0),
                     (1, "2026-09-21 01:00", 17.0, 80.0, 3.0, 600.0, 50.0),
                     (2, "2026-09-21 00:00", 14.0, 95.0, None, None, None),
                     (2, "2026-09-28 00:00", 1.0, 99.0, None, None, None)])     # buiten de periode
        u = to.tabelwaarden(gegevens(), rijen, 3, VAN, TOT)
        w, n = u["waarden"], u["n"]
        self.assertEqual((w["Afd. 1"]["temp_min"], w["Afd. 1"]["temp_max"]), (15.0, 17.0))
        self.assertEqual((w["Afd. 1"]["vd"], w["Afd. 1"]["co2"], w["Afd. 1"]["buis"]), (2.0, 500.0, 45.0))
        self.assertEqual((n["Afd. 1"]["vd"], u["verwacht"]["Afd. 1"]["vd"]), (2, 7 * 24))
        # Uren RV ≥ 90 per 24 gemeten uren: afd. 1 1 van 2, afd. 2 1 van 1; tuin gewogen (500 m² elk).
        self.assertEqual((w["Afd. 1"]["rv_hoog"], w["Afd. 2"]["rv_hoog"], w[HT]["rv_hoog"]), (12.0, 24.0, 18.0))
        self.assertEqual((w[HT]["temp_min"], w[HT]["temp_max"]), (14.0, 17.0))
        self.assertEqual(w[HT]["vd"], 2.0)      # alleen afd. 1 heeft een vochtdeficit
        self.assertIn("klimaat per uur", u["ontbreekt"]["Afd. 2"]["vd"])


class TestOpvallend(unittest.TestCase):
    def test_zinnen(self):
        nu = {"Afd. 1": {"afwijking": 1.4, "temp": 19.0, "rv_hoog": 6.0, "temp_min": 9.5},
              "Afd. 2": {"afwijking": 0.2, "temp": 20.2},
              HT: {"temp": 19.6, "rv": 80.0, "lichtsom": 600.0}}
        toen = {HT: {"temp": 17.8, "rv": 78.0, "lichtsom": 1000.0}}
        n, verwacht = {HT: {"temp": 7}}, {HT: {"temp": 7}}
        zinnen = to.opvallend(nu, toen, n, verwacht, "wk 38", 7)
        self.assertEqual(zinnen, [
            "**Warmer dan de lichtlijn**: afd. 1 (+1,4 °C).",
            "**Verschil tussen afdelingen**: afd. 1 was 1,2 °C kouder dan afd. 2 (19,0 °C tegen 20,2 °C).",
            "**Hoge RV**: afd. 1 6 uur per dag boven 90 %.",
            "**Koud uur**: laagste uur afd. 1 (9,5 °C).",
            "**Etmaaltemperatuur 1,8 °C hoger** dan wk 38 (19,6 °C tegen 17,8 °C).",
            "**Lichtsom 40 % lager** dan wk 38.",
        ])

    def test_onvolledig_en_leeg(self):
        self.assertEqual(to.opvallend({HT: {"temp": 18.0}}, {}, {HT: {"temp": 5}}, {HT: {"temp": 7}}, "", 7),
                         ["Klimaat niet compleet: 5 van 7 dagen met data."])
        self.assertEqual(to.opvallend({}, {}, {}, {}, "", 1), ["Geen klimaatdata in deze periode."])
        self.assertEqual(to.opvallend({HT: {"water": 0.0, "temp_max": 20.0}}, {HT: {"water": 2.1}}, {}, {}, "9 okt", 1),
                         ["**Geen watergift**, 9 okt wel."])


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

"""Tests voor logic/tuinvergelijking.py: m²-weging, het totaal en ontbrekende data."""
import unittest
from datetime import date

import pandas as pd

from logic import tuinvergelijking as tv
from logic.lichtlijn import t_ideaal

VAN, TOT = date(2026, 9, 21), date(2026, 9, 27)   # week 39


def gegevens(emmers_vanaf="2026-09-01"):
    # Tuin 1: twee vakken van 800 m² (afd. 1); tuin 3: twee vakken van 500 m² (afd. 1 en 2).
    vakken = pd.DataFrame([
        {"tuin_id": 1, "vaknummer": 1, "afdeling": 1, "m2": 800.0},
        {"tuin_id": 1, "vaknummer": 2, "afdeling": 1, "m2": 800.0},
        {"tuin_id": 3, "vaknummer": 1, "afdeling": 1, "m2": 500.0},
        {"tuin_id": 3, "vaknummer": 2, "afdeling": 2, "m2": 500.0},
    ])
    teelten = pd.DataFrame([
        # tuin 1 vak 1: de hele week bezet, afgerond op 27-09 met 10 % uitval (uit emmers)
        {"id": 1, "tuin_id": 1, "vaknummer": 1, "datum_teelt_start": "2026-08-01", "datum_oogst": "2026-09-27",
         "aantal_planten": 1000, "emmers": 9, "uitval_pct": None},
        # tuin 1 vak 2: geplant op 24-09 (4 van de 7 dagen bezet)
        {"id": 2, "tuin_id": 1, "vaknummer": 2, "datum_teelt_start": "2026-09-24", "datum_oogst": None,
         "aantal_planten": 1000, "emmers": None, "uitval_pct": None},
        # tuin 3 vak 1: de hele week bezet, afgerond met 20 % uitval (vastgelegd)
        {"id": 3, "tuin_id": 3, "vaknummer": 1, "datum_teelt_start": "2026-08-01", "datum_oogst": "2026-09-25",
         "aantal_planten": None, "emmers": None, "uitval_pct": 20.0},
    ])
    emmers = pd.DataFrame([
        {"tuin_id": 1, "vaknummer": 1, "teelt_id": 1, "datum": emmers_vanaf, "aantal_emmers": 1},
        {"tuin_id": 1, "vaknummer": 1, "teelt_id": 1, "datum": "2026-09-25", "aantal_emmers": 8},
    ])
    dagen = [str(date(2026, 9, 21 + i)) for i in range(7)]
    klimaat = pd.DataFrame(
        [{"tuin_id": 1, "afdeling": 1, "datum": d, "temp_24h": 20.0, "temp_dag": 22.0, "temp_nacht": 18.0,
          "rv_24h": 80.0, "lichtsom": 1000.0} for d in dagen]
        + [{"tuin_id": 3, "afdeling": a, "datum": d, "temp_24h": 18.0 + a, "temp_dag": None, "temp_nacht": None,
            "rv_24h": 70.0, "lichtsom": 1000.0} for d in dagen for a in (1, 2)])
    energie = pd.DataFrame([{"tuin_id": 1, "datum": d, "warmte_mj": 1600.0} for d in dagen])
    gas = pd.DataFrame([{"tuin_id": 3, "datum": d, "gas_m3": 100.0} for d in dagen])
    water = pd.DataFrame([{"tuin_id": 3, "vaknummer": 1, "datum": dagen[0], "liter_per_m2": 4.0}])
    return tv.Gegevens({"vakken": vakken, "teelten": teelten, "emmers": emmers, "klimaat": klimaat,
                        "energie": energie, "gas": gas, "water": water})


TUINEN = [("Tuin 1", 1), ("Tuin 3", 3)]


class TestTuinvergelijking(unittest.TestCase):
    def test_bezetting_en_geplant(self):
        w, n, _ = tv.tabelwaarden(gegevens(), TUINEN, VAN, TOT)
        # Tuin 1: vak 1 7 dagen + vak 2 4 dagen = 11 × 800 m² van 7 × 1600 m²
        self.assertAlmostEqual(w["Tuin 1"]["bezetting"], 11 * 800 / (7 * 1600) * 100)
        # Tuin 3: vak 1 geoogst op 25-09, dus 5 dagen × 500 m² van 7 × 1000 m²
        self.assertAlmostEqual(w["Tuin 3"]["bezetting"], 5 * 500 / 7000 * 100)
        # Totaal gewogen naar m²: (8800 + 2500) / (7 × 2600)
        self.assertAlmostEqual(w["Totaal"]["bezetting"], (8800 + 2500) / (7 * 2600) * 100)
        self.assertEqual((w["Tuin 1"]["geplant"], n["Tuin 1"]["geplant"]), (800.0, 1))
        self.assertEqual(w["Tuin 3"]["geplant"], 0.0)
        self.assertEqual((w["Totaal"]["geplant"], n["Totaal"]["geplant"]), (800.0, 1))   # som, geen gemiddelde

    def test_uitval_gewogen_naar_m2(self):
        w, n, _ = tv.tabelwaarden(gegevens(), TUINEN, VAN, TOT)
        self.assertAlmostEqual(w["Tuin 1"]["uitval"], 10.0)
        self.assertAlmostEqual(w["Tuin 3"]["uitval"], 20.0)
        self.assertAlmostEqual(w["Totaal"]["uitval"], (10 * 800 + 20 * 500) / 1300)
        self.assertEqual(n["Totaal"]["uitval"], 2)

    def test_klimaat_gewogen_naar_afdeling_m2(self):
        w, n, _ = tv.tabelwaarden(gegevens(), TUINEN, VAN, TOT)
        self.assertAlmostEqual(w["Tuin 3"]["temp"], 19.5)
        # Tuin 1 afd. 1 (1600 m², 20 °C) en tuin 3 (2 × 500 m², 19 en 20 °C)
        self.assertAlmostEqual(w["Totaal"]["temp"], (20 * 1600 + 19 * 500 + 20 * 500) / 2600)
        self.assertAlmostEqual(w["Tuin 1"]["afwijking"], 20.0 - t_ideaal(1000.0))
        self.assertEqual(n["Totaal"]["temp"], 7)                  # dagen, niet opgeteld
        self.assertNotIn("temp_dag", w["Tuin 3"])                 # geen data → ontbreekt, geen 0

    def test_energie_per_m2_kas_en_totaal_op_een_tuin(self):
        w, _, _ = tv.tabelwaarden(gegevens(), TUINEN, VAN, TOT)
        self.assertAlmostEqual(w["Tuin 1"]["warmte"], 7 * 1600 / 1600)
        self.assertNotIn("warmte", w["Tuin 3"])
        self.assertAlmostEqual(w["Totaal"]["warmte"], 7.0)        # alleen tuin 1 draagt bij
        self.assertAlmostEqual(w["Tuin 3"]["gas"], 700 / 1000)
        self.assertAlmostEqual(w["Tuin 3"]["water"], 4 * 500 / 1000)

    def test_stelen_alleen_als_emmerregistratie_al_liep(self):
        w, n, _ = tv.tabelwaarden(gegevens(), TUINEN, VAN, TOT)
        # 8 emmers in de week = 800 stelen, gemiddeld 11×800/7 m² bezet
        self.assertAlmostEqual(w["Tuin 1"]["stelen_m2"], 800 / (8800 / 7))
        self.assertNotIn("stelen_m2", w["Tuin 3"])                # tuin 3 registreerde nog geen emmers
        w, _, _ = tv.tabelwaarden(gegevens(emmers_vanaf="2026-09-23"), TUINEN, VAN, TOT)
        self.assertNotIn("stelen_m2", w["Tuin 1"])                # registratie begon midden in de week

    def test_bezetting_pas_vanaf_eerste_teelt(self):
        # Tuin 1 begon op 01-08: in juli–augustus telt alleen augustus mee.
        w, n, _ = tv.tabelwaarden(gegevens(), TUINEN, date(2026, 7, 1), date(2026, 8, 31))
        self.assertEqual(n["Tuin 1"]["bezetting"], 31)
        self.assertAlmostEqual(w["Tuin 1"]["bezetting"], 50.0)   # vak 1 van de 2 bezet

    def test_dagsom_totaal_alleen_bij_gelijke_dekking(self):
        g = gegevens()
        g.water = pd.concat([g.water, pd.DataFrame(
            [{"tuin_id": 1, "vaknummer": 1, "datum": f"2026-09-{d}", "liter_per_m2": 2.0} for d in range(21, 28)])])
        w, n, bron = tv.tabelwaarden(g, TUINEN, VAN, TOT)
        # Tuin 1 heeft 7 dagen water, tuin 3 maar 1: het totaal rust alleen op tuin 1.
        self.assertEqual(bron["water"], frozenset({"Tuin 1"}))
        self.assertAlmostEqual(w["Totaal"]["water"], w["Tuin 1"]["water"])

    def test_tuin_bestond_nog_niet(self):
        w, _, _ = tv.tabelwaarden(gegevens(), TUINEN, date(2025, 9, 22), date(2025, 9, 28))
        self.assertNotIn("bezetting", w["Tuin 1"])
        self.assertNotIn("geplant", w["Tuin 1"])


if __name__ == "__main__":
    unittest.main()

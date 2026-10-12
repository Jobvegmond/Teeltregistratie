"""Tests voor logic/klimaat_uur.py: Priva-historie per uur en minuutdata naar klimaat per uur."""
import json
import unittest
from datetime import datetime

from logic import klimaat_uur as ku


def t(dag, uur, minuut=0):
    return datetime(2026, 10, dag, uur, minuut)


class TestInlezen(unittest.TestCase):
    def test_historie_csv_met_lege_cellen_en_nullen(self):
        regels = ["tijdstip;afd1.klimaatOverzicht.gemetenKasTemperatuur;afd1.klimaatOverzicht.gemetenCO2Concentratie;"
                  "afd2.klimaatOverzicht.gemetenCO2Concentratie;meteo.buitenTemperatuur",
                  "2026-10-06 14:00:00;20.8;412.7;0;12.5", "2026-10-06 15:00:00;;;0;"]
        uit = ku.lees_historie_csv(regels)
        self.assertEqual(uit[0], (t(6, 14), {(1, "temp"): 20.8, (1, "co2"): 412.7}, {"buiten_temp": 12.5}))
        self.assertEqual(uit[1], (t(6, 15), {}, {}))     # leeg = geen data; CO2 0 in afd 2 = geen sensor

    def test_live_jsonl(self):
        regels = [json.dumps({"t": "2026-10-09T14:05:00+02:00",
                              "v": {"afd3.klimaatOverzicht.gemetenRelatieveLuchtvochtigheid": 88,
                                    "meteo.stralingsMeter.stralingsIntensiteit": 310}}), '{"t":"2026-10-09T14:0']
        self.assertEqual(ku.lees_live_jsonl(regels), [(t(9, 14, 5), {(3, "rv"): 88.0}, {"straling": 310.0})])


class TestPerUur(unittest.TestCase):
    def test_live_gemiddeld_per_uur_en_alleen_voorbije_uren(self):
        live = [(t(9, 14, 0), {(1, "temp"): 20.0}, {"straling": 100.0}),
                (t(9, 14, 30), {(1, "temp"): 22.0}, {"straling": 300.0}),
                (t(9, 15, 10), {(1, "temp"): 23.0}, {})]          # uur 15 loopt nog
        afd, meteo = ku.per_uur([], live)
        self.assertEqual(afd, {(t(9, 14), 1): {"temp": 21.0}})
        self.assertEqual(meteo, {t(9, 14): {"straling": 200.0}})

    def test_live_gaat_voor_historie(self):
        historie = [(t(7, 16), {(1, "temp"): 19.0}, {}), (t(7, 17), {(1, "temp"): 19.5}, {})]
        live = [(t(7, 17, 21), {(1, "temp"): 21.0}, {}), (t(7, 18, 1), {(1, "temp"): 21.4}, {})]
        afd, _ = ku.per_uur(historie, live)
        self.assertEqual(afd[(t(7, 16), 1)], {"temp": 19.0})
        self.assertEqual(afd[(t(7, 17), 1)], {"temp": 21.0})    # minuten van 17:21–17:59, niet de momentwaarde


if __name__ == "__main__":
    unittest.main()

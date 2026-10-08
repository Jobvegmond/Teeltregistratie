"""Tests voor logic/pulsmeters.py: inlezen van de Priva-bestanden en verbruik per dag uit de tellerstand."""
import unittest
from datetime import date, datetime

from logic import pulsmeters as pm


def t(dag, uur, minuut=0):
    return datetime(2026, 10, dag, uur, minuut)


class TestInlezen(unittest.TestCase):
    def test_historie_csv(self):
        regels = ["tijdstip;pulsmeter1.pulsMeterStand;pulsmeter1.pulsMeterTotaal;pulsmeter2.pulsMeterStand",
                  "2026-10-06 00:00:00;122385;0;50800", "2026-10-06 01:00:00;;0;50801.5"]
        uit = pm.lees_historie_csv(regels)
        self.assertEqual(uit[1], [(t(6, 0), 122385.0)])                 # lege cel = geen data
        self.assertEqual(uit[2], [(t(6, 0), 50800.0), (t(6, 1), 50801.5)])

    def test_live_jsonl_slaat_kapotte_regels_over(self):
        regels = ['{"t":"2026-10-07T17:21:48+02:00","v":{}}',
                  '{"t":"2026-10-07T17:22:48+02:00","v":{"pulsmeter2.pulsMeterStand":50850,"pulsmeter1.pulsMeterStand":122385}}',
                  '{"t":"2026-10-07T17:23:4']                              # onvolledige laatste regel
        uit = pm.lees_live_jsonl(regels)
        self.assertEqual(uit[2], [(t(7, 17, 22).replace(second=48), 50850.0)])
        self.assertEqual(len(uit[1]), 1)

    def test_samenvoegen(self):
        a = {2: [(t(6, 0), 1.0), (t(6, 1), 2.0)]}
        b = {2: [(t(6, 1), 2.0), (t(6, 2), 3.0)]}
        self.assertEqual(pm.samenvoegen(a, b)[2], [(t(6, 0), 1.0), (t(6, 1), 2.0), (t(6, 2), 3.0)])


class TestDagverbruik(unittest.TestCase):
    def test_per_dag_met_middernacht_bij_de_dag_ervoor(self):
        reeks = [(t(5, 0), 100.0), (t(5, 12), 110.0), (t(6, 0), 120.0), (t(6, 12), 125.0), (t(7, 0), 131.0)]
        verbruik, onvolledig = pm.dagverbruik(reeks)
        self.assertEqual(verbruik, {date(2026, 10, 5): 20.0, date(2026, 10, 6): 11.0})
        self.assertEqual(onvolledig, set())

    def test_gat_binnen_een_dag_maakt_niet_uit(self):
        # Zoals 7 okt: uurhistorie tot 00:00, dan live vanaf 17:21; de dag is wel volledig.
        reeks = [(t(7, 0), 50836.0), (t(7, 17, 21), 50846.0), (t(8, 0), 50850.0)]
        self.assertEqual(pm.dagverbruik(reeks)[0], {date(2026, 10, 7): 14.0})

    def test_lang_gat_over_middernacht_en_randdagen_onvolledig(self):
        reeks = [(t(5, 6), 0.0), (t(6, 0), 10.0), (t(6, 20), 20.0), (t(7, 6), 30.0), (t(8, 0), 40.0)]
        verbruik, onvolledig = pm.dagverbruik(reeks)
        # 5 okt begint pas om 06:00; 6/7 okt hebben een gat van 10 uur over middernacht; 7 okt eindigt op 8 okt 00:00
        self.assertEqual(verbruik, {})
        self.assertEqual(onvolledig, {date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)})

    def test_kort_interval_over_middernacht_wordt_verdeeld(self):
        reeks = [(t(5, 0), 0.0), (t(5, 23), 10.0), (t(6, 1), 14.0), (t(7, 0), 20.0)]
        verbruik, _ = pm.dagverbruik(reeks)
        self.assertAlmostEqual(verbruik[date(2026, 10, 5)], 12.0)   # 10 + de helft van 4
        self.assertAlmostEqual(verbruik[date(2026, 10, 6)], 8.0)

    def test_reset_telt_niet(self):
        # Pulsmeter 1 op 20 april 2026: 526.144 → 69.631, daarna gewoon verder.
        reeks = [(t(5, 0), 526100.0), (t(5, 6), 526144.0), (t(5, 7), 69631.0), (t(6, 0), 69700.0)]
        self.assertEqual(pm.dagverbruik(reeks)[0], {date(2026, 10, 5): 113.0})


if __name__ == "__main__":
    unittest.main()

"""Tests voor logic/warmte_afdeling.py en database.energie_verdeling: de verdeling van de warmte over de afdelingen."""
import io
import json
import unittest
from datetime import date

import database
from logic import warmte_afdeling as wa

CATALOGUS = '''"id";"adres";"naam";"eenheid";"soort";"type";"scad";"vervallen"
"10";"/afdeling[VP9508:1]/verwarmingToestand/verwarmingsRegeling[1]/gerealiseerdVermogenVerwarmingsNet";"AFD 1";"kW";"meting";"getal";"M112.0N1R12.1V1";"0"
"11";"/afdeling[VP9508:1]/verwarmingToestand/verwarmingsRegeling[1]/gewenstVermogenVerwarmingsNet";"AFD 1";"kW";"meting";"getal";"M112.0N1R6.1V1";"0"
"20";"/afdeling[VP9508:2]/verwarmingToestand/verwarmingsRegeling[1]/gerealiseerdVermogenVerwarmingsNet";"AFD 2";"kW";"meting";"getal";"M112.0N2R12.1V1";"0"
"30";"/afdeling[VP9508:3]/verwarmingToestand/verwarmingsRegeling[1]/gerealiseerdVermogenVerwarmingsNet";"AFD 3";"kW";"meting";"getal";"M112.0N3R12.1V1";"1"
'''


def regel(t, v=None, soort="meting"):
    return json.dumps({"t": t, "soort": soort, "v": v or {}})


class TestPunten(unittest.TestCase):
    def test_alleen_gerealiseerd_vermogen(self):
        # Het gewenste vermogen en een vervallen punt tellen niet.
        self.assertEqual(wa.punten(io.StringIO(CATALOGUS)), {"10": 1, "20": 2})


class TestDagKwh(unittest.TestCase):
    P = {"10": 1, "20": 2}

    def test_vermogen_maal_tijd_per_afdeling(self):
        regels = [regel("2026-11-09T00:00:30+01:00", {"10": 100, "20": 0, "x": 1}, "basis"),
                  regel("2026-11-09T12:00:00+01:00", {"20": 200}),       # afd. 2: 200 kW van 12:00 tot 24:00
                  regel("2026-11-09T18:00:00+01:00", {"x": 2}),          # ander punt: standen blijven
                  regel("2026-11-09T23:59:00+01:00", {"10": 100}),
                  '{"t": "2026-11-09T23:59:5']                           # half geschreven regel
        dag, kwh = wa.dag_kwh(regels, self.P)
        self.assertEqual(dag, date(2026, 11, 9))
        self.assertAlmostEqual(kwh[1], 2400.0)
        self.assertAlmostEqual(kwh[2], 2400.0)

    def test_onvolledige_dag(self):
        vandaag = [regel("2026-11-10T00:00:30+01:00", {"10": 100}, "basis"),
                   regel("2026-11-10T06:11:00+01:00", {"10": 120})]
        self.assertEqual(wa.dag_kwh(vandaag, self.P), (date(2026, 11, 10), None))
        zonder_vermogen = [regel("2026-11-09T00:00:30+01:00", {"x": 1}, "basis"),
                           regel("2026-11-09T23:59:00+01:00", {"x": 2})]
        self.assertEqual(wa.dag_kwh(zonder_vermogen, self.P), (date(2026, 11, 9), None))
        self.assertEqual(wa.dag_kwh([], self.P), (None, None))


class TestAandelen(unittest.TestCase):
    def test_aandelen(self):
        self.assertEqual(wa.aandelen({1: 3.0, 2: 1.0, 5: 0.0}), {1: 0.75, 2: 0.25, 5: 0.0})
        self.assertIsNone(wa.aandelen({1: 0.0, 2: 0.0}))
        self.assertIsNone(wa.aandelen({}))


EXPORT = """label;pcu;type_1;idx_1;type_2;idx_2;startdate;enddate;value
Sum_24h_Gas_use;VP9508;Afdeling;1;;;22-10-26;22-10-26;176
Sum_24h_Gas_use;VP9508;Afdeling;2;;;22-10-26;22-10-26;211
Sum_24h_Gas_use/m2;VP9508;Afdeling;1;;;22-10-26;22-10-26;0,03
Sum_24h_Gas_use;VP9508;Afdeling;1;;;23-10-26;23-10-26;0
Sum_24h_Gas_use;VP9508;Afdeling;2;;;23-10-26;23-10-26;0
Sum_24h_Gas_use;VP9508;Gas verdeler;1;;;22-10-26;22-10-26;999
"""


class TestEnergieVerdeling(unittest.TestCase):
    def test_priva_verdeling_uit_de_export(self):
        df = database._lees_energie_df(io.StringIO(EXPORT))
        # Alleen Sum_24h_Gas_use per afdeling; een dag met alleen nullen valt weg.
        self.assertEqual(database.energie_verdeling(df), {date(2026, 10, 22): {1: 176.0, 2: 211.0}})


if __name__ == "__main__":
    unittest.main()

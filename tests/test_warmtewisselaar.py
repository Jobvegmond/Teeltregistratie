"""Tests voor logic/warmtewisselaar.py: warmte per dag uit het vermogen van de warmtewisselaar."""
import json
import unittest
from datetime import date

from logic import warmtewisselaar as ww

P = "M340.0N1R11.1V1"


def regel(t, v=None, soort="meting"):
    return json.dumps({"t": t, "soort": soort, "v": v or {}})


class TestDagKwh(unittest.TestCase):
    def test_vermogen_maal_tijd(self):
        regels = [regel("2026-10-22T00:00:06+02:00", {P: 0, "x": 1}, "basis"),
                  regel("2026-10-22T06:00:00+02:00", {P: 1000}),         # 1000 kW van 06:00 tot 08:00
                  regel("2026-10-22T07:00:00+02:00", {"x": 2}),          # ander punt: stand blijft
                  regel("2026-10-22T08:00:00+02:00", {P: 0}),
                  regel("2026-10-22T23:00:00+02:00", {P: 500}),          # 500 kW tot middernacht
                  regel("2026-10-22T23:59:50+02:00", {"x": 3}),
                  '{"t": "2026-10-22T23:59:5']                           # half geschreven regel
        self.assertEqual(ww.dag_kwh(regels, P), (date(2026, 10, 22), 2500.0))

    def test_onvolledige_dag(self):
        laat_begonnen = [regel("2026-10-21T20:00:00+02:00", {P: 100}, "basis"),
                         regel("2026-10-21T23:59:00+02:00", {"x": 1})]
        self.assertEqual(ww.dag_kwh(laat_begonnen, P), (date(2026, 10, 21), None))
        met_storing = [regel("2026-10-22T00:00:06+02:00", {P: 0}, "basis"),
                       regel("2026-10-22T10:00:00+02:00", soort="storing"),
                       regel("2026-10-22T23:59:50+02:00", {"x": 3})]
        self.assertEqual(ww.dag_kwh(met_storing, P), (date(2026, 10, 22), None))
        self.assertEqual(ww.dag_kwh([], P), (None, None))

    def test_wintertijd_telt_25_uur(self):
        regels = [regel("2026-10-25T00:00:05+02:00", {P: 100}, "basis"),
                  regel("2026-10-25T23:59:55+01:00", {"x": 1})]
        dag, kwh = ww.dag_kwh(regels, P)
        self.assertAlmostEqual(kwh, 2500.0, places=3)


class TestGisteren(unittest.TestCase):
    def test_dagwaarde_bij_de_afgelopen_dag_ook_na_wintertijd(self):
        G = ww.GISTEREN
        # Zoals in de bestanden van tuin 1 rond 25-10-2026: de regelaar blijft op zomertijd, dus na de
        # wintertijd komt de nieuwe waarde om ± 23:00 binnen in plaats van om 0:10.
        regels = [regel("2026-10-25T00:00:03+02:00", {G: 245}, "basis"),          # oude stand: niet gebruiken
                  regel("2026-10-25T00:13:34+02:00", {G: 276}),                   # 24-10
                  regel("2026-10-25T12:00:00+01:00", {G: 999}),                   # niet rond de daggrens
                  regel("2026-10-25T23:15:29+01:00", {G: 133}),                   # 25-10
                  regel("2026-10-26T23:02:17+01:00", {G: 223})]                   # 26-10
        self.assertEqual(ww.gisteren_kw(regels), {date(2026, 10, 24): 276.0, date(2026, 10, 25): 133.0,
                                                  date(2026, 10, 26): 223.0})


if __name__ == "__main__":
    unittest.main()

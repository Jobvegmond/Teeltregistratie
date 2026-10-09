"""Tests voor logic/priva_watergift.py: kraan-per-dag.csv en de stand van vandaag uit water-actueel.json."""
import json
import unittest
from datetime import date, datetime, timezone

from logic import priva_watergift as pwg

UTC = timezone.utc

KOP = "datum;kraan;ec_mS_cm;ph;liter;ml_per_eenheid;l_per_m2;m3_per_uur;procent;kraanstart_1;kraanstart_2;kraanstart_3"


class TestKraanPerDag(unittest.TestCase):
    def test_echte_regels_van_8_oktober(self):
        regels = [KOP, "2026-10-08;10;;;0;0;0;;;0;0;0", "2026-10-08;11;1.7;6.2;1641.2;3000.4;3;21.11;5;1;0;1",
                  "2026-10-08;12;1.6;6.1;1649.5;3015.5;3.015;21.62;8;1;0;1", "kapot;regel"]
        self.assertEqual(pwg.lees_kraan_per_dag(regels), [
            {"vak": 10, "datum": date(2026, 10, 8), "liter_per_m2": 0.0, "ec": None, "ph": None},
            {"vak": 11, "datum": date(2026, 10, 8), "liter_per_m2": 3.0, "ec": 1.7, "ph": 6.2},
            {"vak": 12, "datum": date(2026, 10, 8), "liter_per_m2": 3.02, "ec": 1.6, "ph": 6.1},
        ])


class TestVandaag(unittest.TestCase):
    def actueel(self, tijdstip, waarden):
        return json.dumps({"tijdstip": tijdstip, "pcu": "VP9508", "waarden": waarden})

    def test_stand_per_kraan_met_paginas(self):
        tekst = self.actueel("2026-10-09T18:17:48+02:00", {
            "M412.0N1R1.1V5": 0.507, "M412.0N1R1.1V1": 1.6, "M412.0N1R1.1V2": 6.2,
            "M412.0N1R1.2V5": 0, "M412.0N1R1.2V1": 0,
            "M412.0N2R1.39V5": 16.524, "M412.0N2R1.39V1": 1.6, "M412.0N2R1.39V2": 6.1})
        dag, rijen = pwg.lees_vandaag(tekst, datetime(2026, 10, 9, 16, 30, tzinfo=UTC))
        self.assertEqual(dag, date(2026, 10, 9))
        self.assertEqual(rijen, [
            {"vak": 1, "datum": date(2026, 10, 9), "liter_per_m2": 0.51, "ec": 1.6, "ph": 6.2},
            {"vak": 2, "datum": date(2026, 10, 9), "liter_per_m2": 0.0, "ec": None, "ph": None},
            {"vak": 39, "datum": date(2026, 10, 9), "liter_per_m2": 16.52, "ec": 1.6, "ph": 6.1},
        ])

    def test_te_oud_of_vlak_na_middernacht_telt_niet(self):
        waarden = {"M412.0N1R1.1V5": 2.0}
        self.assertEqual(pwg.lees_vandaag(self.actueel("2026-10-09T12:00:00+02:00", waarden),
                                          datetime(2026, 10, 9, 16, 0, tzinfo=UTC)), (None, []))
        self.assertEqual(pwg.lees_vandaag(self.actueel("2026-10-10T00:03:00+02:00", waarden),
                                          datetime(2026, 10, 9, 22, 4, tzinfo=UTC)), (None, []))
        self.assertEqual(pwg.lees_vandaag("{kapot", datetime(2026, 10, 10, 7, 0, tzinfo=UTC)), (None, []))


if __name__ == "__main__":
    unittest.main()

"""Tests voor logic/status.py: logboeken lezen en de kleur per onderdeel."""
import unittest
from datetime import datetime, timedelta

from logic import status

UURTAAK = """\
2026-10-29  afd 1  13.0 °C ( 5 u)
--- klaar met code 0
--- 29-10-26 06:00 start
--- 29-10-26 05:00 UTC priva_pulsmeters.py --tuin 3
[29-10-26 05:00 UTC] Tuin 3: 2 dagen warmte
--- 29-10-26 05:01 UTC priva_klimaat.py --tuin 1
Traceback (most recent call last):
ValueError: kapot
--- 29-10-26 05:01 UTC pats_import.py
[29-10-26 05:01 UTC] 832 tellingen
FOUT in: priva_klimaat.py --tuin 1
--- klaar met code 1
--- 29-10-26 07:00 start
--- 29-10-26 06:00 UTC priva_pulsmeters.py --tuin 3
"""

PRIVA = """\
--- 28-10-26 18:00 start
[28-10-26 17:00] Tuin 1: klimaat 4 afdeling-dagen (12 overgeslagen), watergift 81 vak-dagen
--- 29-10-26 06:00 start
[29-10-26 05:00] Tuin 1: FOUT bij ophalen uit Priva: Priva klimaat-call mislukt (500)
"""


class TestLogboek(unittest.TestCase):
    def test_runs_en_stappen(self):
        runs = status.lees_runs(UURTAAK)
        self.assertEqual(len(runs), 2)                    # het afgekapte begin telt niet
        eerste, tweede = runs
        self.assertEqual(eerste["start"], datetime(2026, 10, 29, 6, 0))
        self.assertEqual(eerste["code"], 1)
        self.assertEqual(eerste["fout_in"], ["priva_klimaat.py --tuin 1"])
        self.assertEqual([s[0] for s in eerste["stappen"]],
                         ["priva_pulsmeters.py --tuin 3", "priva_klimaat.py --tuin 1", "pats_import.py"])
        self.assertIsNone(tweede["code"])                 # loopt nog
        self.assertIs(status.laatste_afgeronde(runs), eerste)

    def test_status_per_stap(self):
        run = status.lees_runs(UURTAAK)[0]
        self.assertEqual(status.stap(run, "priva_pulsmeters.py --tuin 3"),
                         (status.GROEN, "[29-10-26 05:00 UTC] Tuin 3: 2 dagen warmte"))
        self.assertEqual(status.stap(run, "priva_klimaat.py --tuin 1")[0], status.ROOD)
        self.assertEqual(status.stap(run, "pats_import.py")[0], status.GROEN)   # "FOUT in" hoort bij de run
        self.assertEqual(status.stap(run, "teelt_rapport.py")[0], status.GRIJS)
        self.assertEqual(status.stap(None, "pats_import.py")[0], status.GRIJS)

    def test_logboek_zonder_klaar_regel(self):
        runs = status.lees_runs(PRIVA)
        self.assertEqual([r["start"] for r in runs], [datetime(2026, 10, 28, 18), datetime(2026, 10, 29, 6)])
        self.assertEqual(len(runs[1]["fouten"]), 1)
        self.assertIs(status.laatste_gelukte(runs), runs[0])     # de run met de fout telt niet als gelukt


class TestStatusbestand(unittest.TestCase):
    def test_dagrapport(self):
        s = status.statusbestand('﻿{"taak": "dagrapport", "pc": "KLIMAAT", '
                                 '"tijdstip": "2026-10-29T07:00:12+01:00", "status": "ok", "melding": "verstuurd"}')
        self.assertEqual(s, {"moment": datetime(2026, 10, 29, 7, 0, 12), "ok": True, "melding": "verstuurd",
                             "pc": "KLIMAAT"})
        fout = status.statusbestand('{"tijdstip": "2026-10-29T07:00:12", "status": "fout", "melding": "SMTP weg"}')
        self.assertFalse(fout["ok"])
        self.assertEqual(fout["moment"], datetime(2026, 10, 29, 7, 0, 12))   # zonder zone: Nederlandse tijd
        self.assertIsNone(status.statusbestand("geen json"))
        self.assertIsNone(status.statusbestand("[1, 2]"))

    def test_sync_status_tuin1(self):
        s = status.statusbestand('{"locatie": "Tuin 1", "pc": "KLIMAAT", "syncTijdstip": "2026-10-29T07:08:13+01:00", '
                                 '"syncStatus": "ok", "pollerStatus": "ok", "stop": false}')
        self.assertTrue(s["ok"])
        self.assertEqual(s["melding"], "sync ok, poller ok")
        gestopt = status.statusbestand('{"syncTijdstip": "2026-10-29T07:08:13+01:00", "syncStatus": "ok", '
                                       '"pollerStatus": "fout", "stop": true}')
        self.assertFalse(gestopt["ok"])
        self.assertEqual(gestopt["melding"], "sync ok, poller fout, gestopt")

    def test_dagrapport_schema(self):
        # Om 08:00 moet het rapport van 07:00 er zijn; om 07:20 telt dat van gisteren nog.
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 29, 7, 1), datetime(2026, 10, 29, 8, 0),
                                                     "dagrapport"), status.GROEN)
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 28, 7, 1), datetime(2026, 10, 29, 7, 20),
                                                     "dagrapport"), status.GROEN)
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 28, 7, 1), datetime(2026, 10, 29, 8, 0),
                                                     "dagrapport"), status.ORANJE)


class TestKleur(unittest.TestCase):
    def test_uurtaak(self):
        nu = datetime(2026, 10, 29, 7, 30)
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 29, 7, 0), nu, "uurtaak"), status.GROEN)
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 29, 6, 0), nu, "uurtaak"), status.ORANJE)
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 29, 5, 0), nu, "uurtaak"), status.ROOD)
        self.assertEqual(status.kleur_volgens_schema(None, nu, "uurtaak"), status.ROOD)
        # Vlak na het hele uur heeft de nieuwe run nog even de tijd.
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 29, 6, 0),
                                                     datetime(2026, 10, 29, 7, 5), "uurtaak"), status.GROEN)

    def test_uurtaak_slaat_middernacht_over(self):
        # Tussen 23 en 1 uur draait de uurtaak niet: om 00:30 is de run van 23:00 de laatste.
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 28, 23, 0),
                                                     datetime(2026, 10, 29, 0, 30), "uurtaak"), status.GROEN)

    def test_werkdagen(self):
        # Zaterdag: de laatste geplande Agro4all-export was vrijdag 17:00.
        zaterdag = datetime(2026, 10, 31, 10, 0)
        self.assertEqual(status.geplande_momenten(zaterdag, "agro4all"),
                         [datetime(2026, 10, 30, 17), datetime(2026, 10, 30, 12)])
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 30, 17, 6), zaterdag, "agro4all"),
                         status.GROEN)
        # Een run die net vóór het hele uur start (jitter) telt mee.
        self.assertEqual(status.kleur_volgens_schema(datetime(2026, 10, 30, 16, 52), zaterdag, "agro4all"),
                         status.GROEN)

    def test_leeftijd(self):
        nu = datetime(2026, 10, 29, 7, 0)
        kleur = lambda minuten: status.kleur_volgens_leeftijd(nu - timedelta(minutes=minuten), nu,
                                                               timedelta(minutes=20), timedelta(hours=1))
        self.assertEqual([kleur(5), kleur(30), kleur(90)], [status.GROEN, status.ORANJE, status.ROOD])
        self.assertEqual(status.kleur_volgens_leeftijd(None, nu, timedelta(1), timedelta(2)), status.ROOD)

    def test_tekst_en_ergste(self):
        nu = datetime(2026, 10, 29, 7, 0)
        self.assertEqual(status.leeftijd_tekst(datetime(2026, 10, 29, 6, 1), nu), "06:01")
        self.assertEqual(status.leeftijd_tekst(datetime(2026, 10, 28, 18, 0), nu), "gisteren 18:00")
        self.assertEqual(status.leeftijd_tekst(datetime(2026, 10, 26, 18, 0), nu), "26-10 18:00")
        self.assertEqual(status.ergste([status.GROEN, status.ORANJE, status.INFO]), status.ORANJE)
        self.assertEqual(status.utc_naar_nl(datetime(2026, 10, 29, 5, 0)), datetime(2026, 10, 29, 6, 0))
        self.assertEqual(status.utc_naar_nl(datetime(2026, 7, 1, 5, 0)), datetime(2026, 7, 1, 7, 0))


if __name__ == "__main__":
    unittest.main()

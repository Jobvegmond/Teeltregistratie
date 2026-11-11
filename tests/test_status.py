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
    def test_bom_en_ongeldig(self):
        # PowerShell 5 schrijft UTF-8 met BOM; een tijd zonder zone geldt als Nederlandse tijd.
        s = status.statusbestand('﻿{"pc": "KLIMAAT", "syncTijdstip": "2026-10-29T07:08:13+01:00", '
                                 '"syncStatus": "ok", "pollerStatus": "ok"}')
        self.assertEqual(s, {"moment": datetime(2026, 10, 29, 7, 8, 13), "ok": True,
                             "melding": "sync ok, poller ok", "pc": "KLIMAAT"})
        zonder_zone = status.statusbestand('{"syncTijdstip": "2026-10-29T07:08:13", "syncStatus": "ok", '
                                           '"pollerStatus": "ok"}')
        self.assertEqual(zonder_zone["moment"], datetime(2026, 10, 29, 7, 8, 13))
        zonder_tijd = status.statusbestand('{"syncStatus": "ok", "pollerStatus": "ok"}')
        self.assertIsNone(zonder_tijd["moment"])
        self.assertFalse(status.statusbestand('{"syncTijdstip": "2026-10-29T07:08:13"}')["ok"])   # status ontbreekt
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

    def test_dagrapport_claude_taak(self):
        # De Claude-taak is om ± 06:40 klaar; tot 07:30 telt het rapport van gisteren nog.
        def kleur(klaar, nu):
            return status.kleur_volgens_schema(klaar, nu, "dagrapport")
        self.assertEqual(kleur(datetime(2026, 11, 11, 6, 37), datetime(2026, 11, 11, 8, 0)), status.GROEN)
        self.assertEqual(kleur(datetime(2026, 11, 10, 6, 37), datetime(2026, 11, 11, 7, 11)), status.GROEN)
        self.assertEqual(kleur(datetime(2026, 11, 10, 6, 37), datetime(2026, 11, 11, 8, 0)), status.ORANJE)
        self.assertEqual(kleur(datetime(2026, 11, 9, 6, 38), datetime(2026, 11, 11, 8, 0)), status.ROOD)

    def test_dagrapport_mail(self):
        # De uurtaak mailt om 07:00 (met duiding) of om 09:00 (zonder, zoals in het weekend na een uit staande laptop).
        def kleur(verstuurd, nu):
            return status.kleur_volgens_schema(verstuurd, nu, "dagrapport_mail")
        self.assertEqual(kleur(datetime(2026, 11, 11, 7, 1), datetime(2026, 11, 11, 7, 40)), status.GROEN)
        self.assertEqual(kleur(datetime(2026, 11, 7, 9, 1), datetime(2026, 11, 8, 9, 30)), status.ORANJE)   # nog niet binnen
        self.assertEqual(kleur(datetime(2026, 11, 8, 9, 1), datetime(2026, 11, 8, 9, 30)), status.GROEN)


class TestFouten(unittest.TestCase):
    def test_fouten_laatste_uren(self):
        runs = status.lees_runs(UURTAAK)
        nu = datetime(2026, 10, 29, 7, 30)
        samen = status.fouten_laatste_uren(runs, nu)
        self.assertEqual((samen["totaal"], samen["met_fout"]), (2, 1))        # de laatste run loopt nog en telt mee
        self.assertEqual(samen["recent"], [(datetime(2026, 10, 29, 6, 0), ["priva_klimaat.py --tuin 1"])])
        ver_weg = status.fouten_laatste_uren(runs, nu + timedelta(days=3))
        self.assertEqual((ver_weg["totaal"], ver_weg["met_fout"], ver_weg["recent"]), (0, 0, []))

    def test_logboek_zonder_klaar_regel(self):
        runs = status.lees_runs(PRIVA)
        samen = status.fouten_laatste_uren(runs, datetime(2026, 10, 29, 7, 0))
        self.assertEqual((samen["totaal"], samen["met_fout"]), (2, 1))
        self.assertIn("FOUT bij ophalen", samen["recent"][0][1][0])

    def test_hint_bij_deadlock(self):
        self.assertIn("uurtaak", status.hint("[11-11-26 05:00] FOUT bij het opstarten: deadlock detected"))
        self.assertIsNone(status.hint("FOUT: geen klimaatmetingen"))
        self.assertIsNone(status.hint(None))


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

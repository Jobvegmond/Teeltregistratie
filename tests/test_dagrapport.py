"""Tests voor logic/dagrapport.py: de controles, herhaling en feedback, en de mail."""
import os
import unittest
from datetime import date, timedelta
from unittest import mock

import dagrapport as script
from integrations import mail
from logic import dagrapport as dr

VANDAAG = date(2026, 11, 4)
GISTEREN = VANDAAG - timedelta(days=1)


def teelt(vak, start, **extra):
    return {"vak": vak, "afdeling": 1, "start": start, "florgib": None, "florgib_verwacht": None, "prognose": None,
            "plan": None, "emmers": 0, "laatste_emmers": None, "oogst": None, "lengte_eind": None, "gewicht": None,
            "stek": True, **extra}


def sleutels(signalen):
    return [s["sleutel"] for s in signalen]


class TestRegistraties(unittest.TestCase):
    def test_florgib_achter_en_oogstrijp_zonder_emmers(self):
        t = teelt(5, date(2026, 8, 20), florgib_verwacht=VANDAAG - timedelta(days=5),
                  prognose=VANDAAG - timedelta(days=4))
        uit = dr.registraties(3, [t], [], VANDAAG)
        self.assertEqual(sleutels(uit), ["registratie:florgib:t3:v5", "registratie:oogst:t3:v5"])

    def test_binnen_de_marge_niets(self):
        t = teelt(5, date(2026, 8, 20), florgib_verwacht=VANDAAG - timedelta(days=3), prognose=VANDAAG)
        self.assertEqual(dr.registraties(3, [t], [], VANDAAG), [])

    def test_afronden_eindmeting_stek_en_concept(self):
        lopend = teelt(6, date(2026, 8, 1), emmers=40, laatste_emmers=VANDAAG - timedelta(days=9))
        afgerond = teelt(7, date(2026, 8, 1), oogst=VANDAAG - timedelta(days=5), lengte_eind=72)
        nieuw = teelt(8, VANDAAG - timedelta(days=5), stek=False)
        uit = dr.registraties(3, [lopend, afgerond, nieuw], [(9, VANDAAG - timedelta(days=2))], VANDAAG)
        self.assertEqual([s["sleutel"].split(":")[1] for s in uit], ["afronden", "eindmeting", "stek", "planten"])
        self.assertIn("zonder gewicht", uit[1]["tekst"])


class TestBespuitingen(unittest.TestCase):
    def test_rizolex_ontbreekt_en_leeg_vak(self):
        teelten = [teelt(10, VANDAAG - timedelta(days=5)), teelt(11, VANDAAG - timedelta(days=5))]
        behandelingen = [{"vak": 10, "datum": VANDAAG - timedelta(days=5), "middel": "Rizolex", "type": "gewasbescherming"},
                         {"vak": 30, "datum": GISTEREN, "middel": "ConSecta", "type": "biologie"}]
        bezetting = {10: [(VANDAAG - timedelta(days=5), None)], 11: [(VANDAAG - timedelta(days=5), None)]}
        uit = dr.bespuitingen(3, teelten, behandelingen, [], bezetting, GISTEREN, GISTEREN, VANDAAG)
        self.assertEqual(sleutels(uit), ["bespuiting:rizolex:t3:v11", "bespuiting:leeg:t3:v30"])
        self.assertEqual(uit[1]["ernst"], "fout")

    def test_zonder_agro4all_geen_controles_op_behandelingen(self):
        teelten = [teelt(11, VANDAAG - timedelta(days=5))]
        self.assertEqual(dr.bespuitingen(1, teelten, [], [], {}, GISTEREN, GISTEREN, VANDAAG), [])

    def test_cxds_achter_uit_de_werkplanning(self):
        taken = [{"soort": "cxds", "vakken": [17, 18], "titel": "CXDS-blok vak 17–18",
                  "toelichting": "Tuin 3 · plantweek 43, loopt achter"},
                 {"soort": "planten", "vakken": [25], "titel": "Planten vak 25", "toelichting": "…, loopt achter"}]
        uit = dr.bespuitingen(3, [], [], taken, {}, GISTEREN, GISTEREN, VANDAAG)
        self.assertEqual(sleutels(uit), ["bespuiting:cxds-17:t3"])


class TestKlimaatEnWater(unittest.TestCase):
    def test_een_signaal_per_tuin_met_de_afdelingen(self):
        waarden = {"Afd. 1": {"dif": 1.5, "rv_hoog": 21, "stook_max": 15.0},
                   "Afd. 2": {"dif": 2.5, "rv_hoog": 13, "stook_max": 16.0}, "Hele tuin": {"dif": 0.1}}
        uit = dr.klimaat(3, waarden, {1: {"c": 1.0, "nu": -0.2}, 2: {"c": 0.1, "nu": 0.3}})
        self.assertEqual([s["sleutel"] for s in uit], ["klimaat:dif:t3", "klimaat:stook:t3", "klimaat:rv:t3",
                                                       "klimaat:stookadvies:t3"])
        self.assertIn("afd. 1 1,5 °C", uit[0]["tekst"])
        self.assertEqual(uit[2]["ernst"], "let op")
        self.assertIn("warmer stoken", uit[3]["tekst"])
        self.assertNotIn("afd. 2", uit[3]["tekst"])

    def test_ph_alleen_met_regeling(self):
        waarden = {"Afd. 1": {"ec": 2.4, "ph": 6.3}}
        self.assertEqual(sleutels(dr.water(3, waarden, [], {})), ["water:ec:t3"])
        self.assertEqual(sleutels(dr.water(1, waarden, [], {})), ["water:ec:t1", "water:ph:t1"])

    def test_leeg_vak_inwateren_en_uitschieter(self):
        bezetting = {1: [(date(2026, 9, 1), None)], 2: [(date(2026, 9, 1), None)], 3: [(date(2026, 9, 1), None)],
                     4: [(GISTEREN + timedelta(days=3), None)], 5: [(GISTEREN - timedelta(days=4), None)]}
        giften = [{"vak": v, "afdeling": 1, "datum": GISTEREN, "liter": l}
                  for v, l in ((1, 1.0), (2, 1.2), (3, 9.0), (4, 9.0), (5, 1.1), (6, 2.0))]
        uit = dr.water(3, {}, giften, bezetting)
        self.assertEqual(sleutels(uit), ["water:leeg:t3:v6", "water:uitschieter:t3:v3"])


class TestPlagenEnData(unittest.TestCase):
    def test_stijging(self):
        rijen = [{"insect": "Trips", "datum": VANDAAG - timedelta(days=d), "totaal": t}
                 for d, t in ((10, 1), (8, 2), (6, 1), (3, 8), (2, 9), (1, 12))]
        self.assertEqual(sleutels(dr.plagen(3, rijen, VANDAAG)), ["plaag:stijging-trips:t3"])
        laag = [{**r, "totaal": 1} for r in rijen]
        self.assertEqual(dr.plagen(3, laag, VANDAAG), [])

    def test_data_actueel(self):
        verwacht = {"klimaat": ("Klimaat", 1), "pats": ("PATS", 4), "water": ("Water", 1)}
        laatste = {"klimaat": GISTEREN, "pats": VANDAAG - timedelta(days=5), "water": None}
        uit = dr.data_actueel(3, laatste, verwacht, VANDAAG)
        self.assertEqual([(s["sleutel"], s["ernst"]) for s in uit], [("data:pats:t3", "let op"),
                                                                     ("data:water:t3", "fout")])


class TestHerhalingFeedbackMail(unittest.TestCase):
    def signalen(self):
        return [dr.signaal("klimaat", "info", 3, "RV hoog", "rv"), dr.signaal("data", "fout", 1, "geen klimaat", "klimaat")]

    def test_herhaling_demp_en_sorteer(self):
        s = dr.herhaling(self.signalen(), {"klimaat:rv:t3": 4})
        s = dr.demp(s, [{"sleutels": ["klimaat:rv:t3"], "oordeel": "bewust zo", "tekst": "scherm dicht", "datum": "x"},
                        {"sleutels": ["data:klimaat:t1"], "oordeel": "klopt", "datum": "x"}])
        s = dr.sorteer(s)
        self.assertEqual([x["sleutel"] for x in s], ["data:klimaat:t1", "klimaat:rv:t3"])
        self.assertEqual(s[1]["eerder"], 4)
        self.assertEqual(s[1]["feedback"]["oordeel"], "bewust zo")
        self.assertNotIn("feedback", s[0])

    def test_bericht(self):
        signalen = dr.herhaling(self.signalen(), {"klimaat:rv:t3": 2})
        bundel = {"sleutel": "2026-11-03-dag", "soort": "dag", "van": "2026-11-03", "tot": "2026-11-03",
                  "signalen": dr.sorteer(signalen),
                  "tuinen": [{"naam": "Tuin 3", "samenvatting": "1 vak geplant", "kolommen": ["Afd. 1"],
                              "kengetallen": {"Afd. 1": {"temp": 14.2, "afwijking": 0.8}},
                              "behandelingen": [{"datum": "2026-11-03", "middel": "ConSecta", "vakken": "11, 12"}],
                              "pats": [{"insect": "Trips", "totaal": 3, "vorige": 1}]}]}
        duiding = {"samenvatting": "Rustige dag.", "conclusies": [
            {"id": "c1", "soort": "advies", "tuin": 3, "titel": "Stook iets lager", "tekst": "De afwijking <0,8>"}]}
        onderwerp, tekst = dr.bericht(bundel, duiding, "https://app.example")
        self.assertEqual(onderwerp, "Dagrapport teelt di 03-11-2026")
        self.assertIn("rapporten?rapport=2026-11-03-dag&amp;conclusie=c1", tekst)
        self.assertIn("&lt;0,8&gt;", tekst)
        self.assertIn("ook 2× eerder", tekst)
        self.assertIn("+0,8", tekst)
        self.assertIn("di 03-11 ConSecta (11, 12)", tekst)
        _, zonder = dr.bericht(bundel, None)
        self.assertIn("Geen duiding", zonder)


class TestOntvangers(unittest.TestCase):
    def test_dag_naar_job_en_week_naar_info(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DAGRAPPORT_AAN", None)
            os.environ.pop("WEEKRAPPORT_AAN", None)
            self.assertEqual(script.ontvangers(mail, "dag"), ["job@tanacetum.nl"])
            self.assertEqual(script.ontvangers(mail, "week"), ["info@tanacetum.nl"])

    def test_omgeving_overschrijft_en_proefmail_gaat_naar_het_proefadres(self):
        with mock.patch.dict(os.environ, {"DAGRAPPORT_AAN": "a@x.nl, b@x.nl"}):
            self.assertEqual(script.ontvangers(mail, "dag"), ["a@x.nl", "b@x.nl"])
            self.assertEqual(script.ontvangers(mail, "dag", "test@x.nl"), ["test@x.nl"])


if __name__ == "__main__":
    unittest.main()

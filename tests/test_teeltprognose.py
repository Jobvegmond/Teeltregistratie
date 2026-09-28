"""Tests voor logic/teeltprognose.py: prognose, correctie c, Florgib-ijking en afdelingsadvies."""
import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

from logic import teeltprognose as tp
from logic.lichtlijn import t_ideaal
from logic.teeltmodel import LineairModel, MetTuinfactor

VANDAAG = date(2026, 9, 28)
L = 800.0


def prognose(florgib_fractie=0.5, gram=None):
    """Model met een vaste snelheid 0,02 per dag op de lichtlijn en 0,002 extra per °C erboven."""
    basis = LineairModel()
    basis.a, basis.b, basis.c = 0.02, 0.0, 0.002
    model = MetTuinfactor(basis)
    model.factor = {1: 1.0}
    pm = tp.TeeltPrognose()
    pm.model, pm.florgib_fractie, pm.gram_per_graad = model, florgib_fractie, gram
    pm.licht_per_week = {w: L for w in range(1, 54)}
    return pm


def beoordeel(pm, leeftijd=20, plan_dagen=50, afwijking=0.0, florgib=None):
    start = VANDAAG - timedelta(days=leeftijd)
    T = np.full(leeftijd, t_ideaal(L))
    return pm.beoordeel(1, start, VANDAAG, start + timedelta(days=plan_dagen), T, np.full(leeftijd, L),
                        afwijking, florgib)


class TestCorrectie(unittest.TestCase):
    def test_op_koers(self):
        u = beoordeel(prognose())
        self.assertAlmostEqual(u["gedaan"], 0.4)
        self.assertLess(abs(u["c"]), 0.02)
        self.assertFalse(u["begrensd"])
        self.assertEqual(u["prognose"], u["plan"])

    def test_warmer_nodig(self):
        # 0,6 in 25 dagen = 0,024 per dag → 2 °C boven de lichtlijn
        u = beoordeel(prognose(), plan_dagen=45)
        self.assertAlmostEqual(u["c"], 2.0, delta=0.02)
        self.assertEqual(u["prognose"], VANDAAG + timedelta(days=30))
        self.assertEqual(u["prognose_bij_c"], u["plan"])

    def test_begrensd(self):
        u = beoordeel(prognose(), plan_dagen=40)          # zou +5 °C vragen
        self.assertEqual((u["c"], u["begrensd"]), (3.0, True))
        self.assertEqual(u["prognose_bij_c"], VANDAAG + timedelta(days=round(0.6 / 0.026)))
        u = beoordeel(prognose(), plan_dagen=80)          # zou ver onder de lichtlijn vragen
        self.assertEqual((u["c"], u["begrensd"]), (-2.0, True))

    def test_plan_voorbij(self):
        u = beoordeel(prognose(), plan_dagen=15)
        self.assertEqual((u["c"], u["begrensd"]), (3.0, True))

    def test_oogstrijp_geen_correctie(self):
        u = beoordeel(prognose(), leeftijd=52, plan_dagen=50)
        self.assertTrue(u["oogstrijp"])
        self.assertIsNone(u["c"])
        self.assertEqual(u["prognose"], VANDAAG)

    def test_huidige_stooklijn(self):
        # 1 °C boven de lichtlijn: 0,022 per dag → 0,6 in 27,3 dagen
        u = beoordeel(prognose(), afwijking=1.0)
        self.assertEqual(u["prognose"], VANDAAG + timedelta(days=27))

    def test_gewichtseffect(self):
        u = beoordeel(prognose(gram=50.0), plan_dagen=45)
        self.assertAlmostEqual(u["gewicht"], 100.0, delta=1.0)
        self.assertIsNone(beoordeel(prognose())["gewicht"])


class TestFlorgib(unittest.TestCase):
    def test_ijking_op_florgib(self):
        # Florgib op dag 10: vanaf daar 50 % gedaan (mediaan), plus 10 dagen × 0,02
        u = beoordeel(prognose(), florgib=VANDAAG - timedelta(days=10))
        self.assertAlmostEqual(u["gedaan"], 0.7)
        self.assertIsNone(u["florgib_verwacht"])

    def test_verwachte_florgib(self):
        self.assertEqual(beoordeel(prognose())["florgib_verwacht"], VANDAAG + timedelta(days=5))
        # Al voorbij het Florgib-deel zonder registratie: de dag waarop het model er was
        u = beoordeel(prognose(), leeftijd=30)
        self.assertEqual(u["florgib_verwacht"], VANDAAG - timedelta(days=5))

    def test_florgib_voor_planten_telt_niet(self):
        u = beoordeel(prognose(), florgib=VANDAAG - timedelta(days=25))
        self.assertAlmostEqual(u["gedaan"], 0.4)


class TestAfdeling(unittest.TestCase):
    def test_afwijking_laatste_dagen_zonder_vandaag(self):
        dagen = {VANDAAG - timedelta(days=i): (t_ideaal(L) + 1.0, L) for i in range(1, 30)}
        dagen[VANDAAG] = (t_ideaal(L) + 9.0, L)
        dagen[VANDAAG - timedelta(days=20)] = (t_ideaal(L) + 9.0, L)   # buiten 14 dagen
        self.assertAlmostEqual(tp.afwijking_afdeling(dagen, VANDAAG), 1.0)
        self.assertIsNone(tp.afwijking_afdeling({}, VANDAAG))

    def test_advies_gewogen_naar_stelen(self):
        advies, doorslag = tp.afdelingsadvies([
            {"vak": 1, "c": 1.0, "stelen": 100}, {"vak": 2, "c": -1.0, "stelen": 300},
            {"vak": 3, "c": None, "stelen": 500},
        ])
        self.assertAlmostEqual(advies, -0.5)
        self.assertEqual(doorslag, 2)
        self.assertEqual(tp.afdelingsadvies([{"vak": 1, "c": None, "stelen": 10}]), (None, None))

    def test_kleurklasse(self):
        verwacht = {None: "grijs", -9: "b3", -6: "b3", -5: "b2", -4: "b2", -3: "b1", -2: "b1", -1: "n", 0: "n",
                    1: "n", 2: "o1", 3: "o1", 4: "o2", 5: "o2", 6: "r1", 7: "r2", 12: "r2"}
        self.assertEqual({d: tp.dagen_klasse(d) for d in verwacht}, verwacht)


class TestLeerset(unittest.TestCase):
    def test_historie_en_app(self):
        start = date(2026, 3, 2)   # maandag wk 10
        historie = pd.DataFrame([{"id": 1, "tuin_id": 2, "startdatum": str(start), "teeltduur_dagen": 14,
                                  "florgib_datum": str(start + timedelta(days=7)), "oogstgewicht": 40.0,
                                  "lengte_eind": 80.0, "oogst_precisie": "dag", "teelt_id": 7}])
        weken = pd.DataFrame([{"historie_id": 1, "isojaar": 2026, "isoweek": 10, "etmaal_temp": 18.0,
                               "lichtsom_binnen": 500.0},
                              {"historie_id": 1, "isojaar": 2026, "isoweek": 11, "etmaal_temp": 19.0,
                               "lichtsom_binnen": 600.0}])
        a_start = date(2026, 6, 1)
        klimaat = pd.DataFrame([{"tuin_id": 1, "afdeling": 2, "datum": str(a_start + timedelta(days=i)),
                                 "temp_24h": 20.0, "lichtsom": 900.0} for i in range(60)])
        app = pd.DataFrame([
            # al in de historie
            {"id": 7, "tuin_id": 2, "afdeling": 1, "datum_teelt_start": str(start), "datum_half": None,
             "datum_oogst": str(start + timedelta(days=14)), "oogstgewicht": None, "lengte_eind": None,
             "emmers": None},
            # nieuw, dagprecies
            {"id": 8, "tuin_id": 1, "afdeling": 2, "datum_teelt_start": str(a_start), "datum_half": None,
             "datum_oogst": str(a_start + timedelta(days=45)), "oogstgewicht": 50.0, "lengte_eind": 90.0,
             "emmers": 12.0},
            # geschatte oogst (= plan) telt niet
            {"id": 9, "tuin_id": 1, "afdeling": 2, "datum_teelt_start": str(a_start), "datum_half": None,
             "datum_oogst": str(a_start + timedelta(days=50)), "oogstgewicht": None, "lengte_eind": None,
             "emmers": None},
        ])
        leer = tp.bouw_leerset(historie, weken, app, tp.klimaat_per_afdeling(klimaat),
                               lambda s: s + timedelta(days=50))
        self.assertEqual(len(leer), 2)
        h, a = leer
        self.assertEqual((h["tuin"], h["duur"], h["florgib_dag"]), (2, 14.0, 7))
        np.testing.assert_allclose(h["T"], [18.0] * 7 + [19.0] * 7)
        self.assertEqual((a["tuin"], a["duur"], a["precisie"]), (1, 45.0, "dag"))
        licht = tp.weeklicht(weken, klimaat)
        self.assertAlmostEqual(licht[10], 500.0)
        self.assertAlmostEqual(licht[23], 900.0)


if __name__ == "__main__":
    unittest.main()

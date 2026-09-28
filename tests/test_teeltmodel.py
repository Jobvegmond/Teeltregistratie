"""Tests voor logic/lichtlijn.py en logic/teeltmodel.py."""
import unittest

import numpy as np

from logic import teeltmodel as tm
from logic.lichtlijn import afwijking, t_ideaal


class TestLichtlijn(unittest.TestCase):
    def test_formule(self):
        self.assertAlmostEqual(t_ideaal(1000), 11.7 + 7.2)
        self.assertAlmostEqual(t_ideaal(0), 11.7)
        self.assertAlmostEqual(afwijking(20.0, 1000), 20.0 - 18.9)

    def test_werkt_op_arrays_en_none(self):
        np.testing.assert_allclose(t_ideaal(np.array([0, 500])), [11.7, 15.3])
        self.assertIsNone(t_ideaal(None))
        self.assertIsNone(afwijking(None, 500))


def teelt(duur, T=18.0, L=800.0, tuin=3):
    n = int(duur) + 60
    return {"tuin": tuin, "duur": float(duur), "T": np.full(int(duur), T), "L": np.full(int(duur), L),
            "T_ext": np.full(n, T), "L_ext": np.full(n, L)}


class TestSnelheid(unittest.TestCase):
    def test_duur_uit_snelheid_met_fractie(self):
        self.assertAlmostEqual(tm.duur_uit_snelheid([0.25] * 10), 4.0)
        self.assertAlmostEqual(tm.duur_uit_snelheid([0.4] * 10), 2.5)
        self.assertAlmostEqual(tm.duur_uit_snelheid([0.4] * 10, begin=0.6), 1.0)
        self.assertIsNone(tm.duur_uit_snelheid([0.01] * 10))

    def test_lineair_model_vindt_exacte_verband(self):
        # 1/duur = 0,01 + 0,00001·L + 0,001·afwijking: het model moet dat terugvinden.
        teelten = []
        for L in (300, 600, 900, 1200):
            for afw in (-1.0, 0.0, 1.5):
                duur = 1 / (0.01 + 0.00001 * L + 0.001 * afw)
                t = teelt(round(duur), T=t_ideaal(L) + afw, L=L)
                t["duur"] = duur
                teelten.append(t)
        m = tm.LineairModel().fit(teelten)
        self.assertAlmostEqual(m.a, 0.01, places=3)
        self.assertAlmostEqual(m.c, 0.001, places=4)
        self.assertLess(m.dagen_per_graad(900, 1.0), m.dagen_per_graad(900, 0.0))

    def test_graaddagen_som_en_voorspelling(self):
        m = tm.GraaddagenModel(6).fit([teelt(50, T=16.0), teelt(40, T=18.5)])  # sommen 500 en 500
        self.assertAlmostEqual(m.G, 500.0)
        self.assertAlmostEqual(tm.voorspel_duur(m, np.full(100, 16.0), np.full(100, 800.0)), 50.0)

    def test_tuinfactor(self):
        basis = tm.GraaddagenModel(6)
        teelten = [teelt(50, T=16.0, tuin=3), teelt(50, T=16.0, tuin=3), teelt(55, T=16.0, tuin=1)]
        m = tm.MetTuinfactor(basis).fit(teelten)
        self.assertGreater(m.factor[1], 1.0)            # tuin 1 trager dan het model
        self.assertAlmostEqual(m.factor[3], 1.0)
        duur_t1 = tm.voorspel_duur(tm.voor_tuin(m, 1), np.full(120, 16.0), np.full(120, 800.0))
        self.assertAlmostEqual(duur_t1, 55.0, places=5)


class TestCorrectie(unittest.TestCase):
    def setUp(self):
        # Rijp na 50 dagen op de lichtlijn bij 800 J/cm²; elke °C erboven sneller.
        self.m = tm.LineairModel()
        self.m.a, self.m.b, self.m.c = 0.02 - 0.00001 * 800, 0.00001, 0.002

    def test_op_koers_geeft_nul(self):
        c, begrensd = tm.benodigde_correctie(self.m, 0.4, [], [], np.full(200, 800.0), 30)
        self.assertAlmostEqual(c, 0.0, delta=0.02)      # 0,4 gedaan + 30 × 0,02 = 1
        self.assertFalse(begrensd)

    def test_eerder_klaar_vraagt_warmer(self):
        c, _ = tm.benodigde_correctie(self.m, 0.4, [], [], np.full(200, 800.0), 25)
        # 0,6 in 25 dagen → 0,024 per dag → c = (0,024 − 0,02) / 0,002 = 2
        self.assertAlmostEqual(c, 2.0, delta=0.02)

    def test_later_mag_kouder_en_grenzen(self):
        c, _ = tm.benodigde_correctie(self.m, 0.4, [], [], np.full(200, 800.0), 33.33)
        self.assertAlmostEqual(c, -1.0, delta=0.03)
        c, begrensd = tm.benodigde_correctie(self.m, 0.4, [], [], np.full(200, 800.0), 10)
        self.assertEqual((c, begrensd), (3.0, True))    # onhaalbaar: op de bovengrens

    def test_gedaan_uit_gerealiseerde_dagen(self):
        T = np.full(20, t_ideaal(800.0))
        c, _ = tm.benodigde_correctie(self.m, None, T, np.full(20, 800.0), np.full(200, 800.0), 30)
        self.assertAlmostEqual(c, 0.0, delta=0.02)      # 20 × 0,02 = 0,4 gedaan


if __name__ == "__main__":
    unittest.main()

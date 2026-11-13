"""Tests voor logic/pats_foto.py: wat er tussen twee foto's van een vangplaat bij kwam."""
import unittest
from datetime import date

import numpy as np
from PIL import Image, ImageDraw

from logic import pats_foto as pf

GEEL = (200, 200, 40)


def plaat(insecten, verschuif=(0, 0), helderheid=0):
    """Een gele plaat van 600 × 800 met donkere rechthoeken (x, y, b, h), eventueel verschoven of lichter."""
    kleur = tuple(min(255, c + helderheid) for c in GEEL)
    beeld = Image.new("RGB", (600, 800), kleur)
    teken = ImageDraw.Draw(beeld)
    dx, dy = verschuif
    for x, y, b, h in insecten:
        teken.rectangle((x + dx, y + dy, x + dx + b - 1, y + dy + h - 1), fill=(30, 30, 30))
    return beeld


OUD = [(200, 200, 20, 20), (400, 500, 16, 24), (300, 650, 24, 12)]


class TestPatsFoto(unittest.TestCase):
    def test_niets_nieuw(self):
        self.assertEqual(pf.nieuwe_vlekken(plaat(OUD), plaat(OUD)), [])

    def test_nieuwe_vlekken_klein_eerst(self):
        nieuw = pf.nieuwe_vlekken(plaat(OUD), plaat(OUD + [(250, 400, 30, 30), (450, 300, 4, 10)]))
        self.assertEqual(len(nieuw), 2)
        klein, groot = nieuw
        self.assertLess(klein["pixels"], groot["pixels"])
        self.assertTrue(abs(klein["x"] - 452) <= 3 and abs(klein["y"] - 305) <= 3, klein)
        self.assertTrue(abs(groot["x"] - 265) <= 3 and abs(groot["y"] - 415) <= 3, groot)

    def test_verschoven_en_lichter_is_niet_nieuw(self):
        # De plaat hangt 8 px anders en de foto is lichter: alleen het echte nieuwe insect telt.
        na = plaat(OUD + [(250, 400, 30, 30)], verschuif=(8, -4), helderheid=25)
        nieuw = pf.nieuwe_vlekken(plaat(OUD), na)
        self.assertEqual(len(nieuw), 1)
        self.assertTrue(abs(nieuw[0]["x"] - 273) <= 4 and abs(nieuw[0]["y"] - 411) <= 4, nieuw)

    def test_rand_telt_niet(self):
        self.assertEqual(pf.nieuwe_vlekken(plaat(OUD), plaat(OUD + [(10, 10, 20, 20)])), [])

    def test_vlekken(self):
        m = np.zeros((6, 6), dtype=bool)
        m[1, 1:3] = True
        m[4, 4] = True
        self.assertEqual(sorted(pf.vlekken(m)), [(1, 4, 4, 1, 1), (2, 2, 1, 2, 1)])

    def test_uitsnede_en_gemarkeerd(self):
        voor, na = plaat(OUD), plaat(OUD + [(250, 400, 30, 30)])
        vlek = pf.nieuwe_vlekken(voor, na)[0]
        self.assertEqual(pf.uitsnede(voor, na, vlek).size, (pf.VERGROTING, 2 * pf.VERGROTING + 4))
        self.assertEqual(pf.gemarkeerd(na, [vlek], breedte=300).size, (300, 400))

    def test_vorig_moment(self):
        momenten = ["20261107_110214", "20261110_110054", "20261112_110131"]
        self.assertEqual(pf.vorig_moment(momenten, date(2026, 11, 12)), ("20261110_110054", "20261112_110131"))
        self.assertEqual(pf.vorig_moment(momenten, date(2026, 11, 7)), (None, "20261107_110214"))
        self.assertIsNone(pf.vorig_moment(momenten, date(2026, 11, 11)))
        # Twee foto's op één dag: de laatste van die dag tegen de laatste van een eerdere dag.
        dubbel = ["20261105_110149", "20261107_110249", "20261107_110509"]
        self.assertEqual(pf.vorig_moment(dubbel, date(2026, 11, 7)), ("20261105_110149", "20261107_110509"))

    def test_max_buurt(self):
        a = np.zeros((9, 9))
        a[4, 4] = 5
        m = pf._max_buurt(a, 5)
        self.assertEqual(m[2:7, 2:7].min(), 5)
        self.assertEqual(m.sum(), 125)
        a[0, 8] = 7                                 # de rand loopt niet rond
        self.assertEqual(pf._max_buurt(a, 5)[8, 0], 0)


if __name__ == "__main__":
    unittest.main()

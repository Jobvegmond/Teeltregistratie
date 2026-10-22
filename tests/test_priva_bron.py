"""Tests voor logic/priva_bron.py: de mappen per tuin en de controle van de regelaar."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from logic import priva_bron


class TestPrivaBron(unittest.TestCase):
    def test_mappen_per_tuin(self):
        live, historie = priva_bron.mappen("/priva", 1)
        self.assertEqual(live, Path("/priva") / "bron historie/Tuin 1/live")
        self.assertEqual(historie, Path("/priva") / "bron historie/Tuin 1/historie")
        self.assertEqual(priva_bron.mappen("/priva", 3), (Path("/priva/bron live"), Path("/priva/bron historie")))
        with self.assertRaises(ValueError):
            priva_bron.mappen("/priva", 2)

    def test_regelaar_controle(self):
        with tempfile.TemporaryDirectory() as map_:
            self.assertIsNone(priva_bron.controleer_regelaar(map_, 1))          # geen bestanden: de map telt
            with open(os.path.join(map_, "water-actueel.json"), "w", encoding="utf-8") as f:
                json.dump({"pcu": "Matricaria25", "waarden": {}}, f)
            self.assertIsNone(priva_bron.controleer_regelaar(map_, 1))
            fout = priva_bron.controleer_regelaar(map_, 3)                    # tuin 3 verwacht VP9508
            self.assertIn("Matricaria25", fout)

    def test_regelaar_in(self):
        self.assertEqual(priva_bron.regelaar_in('{"pcu": "VP9508"}'), "VP9508")
        self.assertIsNone(priva_bron.regelaar_in("{kapot"))
        self.assertIsNone(priva_bron.regelaar_in("[]"))


if __name__ == "__main__":
    unittest.main()

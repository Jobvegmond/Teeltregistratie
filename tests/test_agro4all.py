"""Tests voor logic/agro4all.py: Agro4all-registraties naar behandelingen per vak."""
import unittest
from datetime import date

from logic import agro4all as a4

VAKKEN = {1: 27, 3: 39}


def registratie(id_, vakken, activiteit="CROP_PROTECTION", producten=None, **rest):
    return {"id": id_, "activiteit": activiteit, "tuin": 3, "start": 1791868680, "eind": 1791872280,
            "datum": None, "methode": "Spuiten", "mix": {"hoeveelheid": 100, "eenheid": "l"}, "vakken": vakken,
            "producten": producten or [{"naam": "Rizolex vloeibaar", "id": "p-riz", "categorie": "CROP_PROTECTION",
                                        "toelating": "11098", "rol": "product", "hoeveelheid": 900, "eenheid": "ml",
                                        "doel": "Rhizoctonia soorten"}], **rest}


class TestSoort(unittest.TestCase):
    def test_soort(self):
        self.assertEqual(a4.soort("CROP_PROTECTION", "CROP_PROTECTION"), "gewasbescherming")
        self.assertEqual(a4.soort("CROP_PROTECTION", "BIOSTIMULANT"), "biologie")
        self.assertEqual(a4.soort("BIO", "CROP_PROTECTION"), "biologie")
        self.assertEqual(a4.soort("FERTILIZER", "FERTILIZER"), "voeding")
        self.assertEqual(a4.soort("CROP_PROTECTION", "BIOCIDE"), "gewasbescherming")

    def test_datum_in_nederlandse_tijd(self):
        # 1790632800 = 28-09-2026 22:00 UTC = 29-09 00:00 in Nederland (in UTC nog de 28e).
        self.assertEqual(a4.datum({"start": None, "datum": 1790632800}), date(2026, 9, 29))
        self.assertEqual(a4.datum({"start": 1791868680}), date(2026, 10, 13))


class TestBehandelingen(unittest.TestCase):
    def test_per_vak_per_middel(self):
        export = {"registraties": [registratie("r1", [12, 11], producten=[
            {"naam": "Serenade Max", "id": "p-ser", "categorie": "CROP_PROTECTION", "rol": "product",
             "hoeveelheid": 1000, "eenheid": "ml", "doel": "Pythium soorten"},
            {"naam": "Natrubac 08", "id": "p-nat", "categorie": "BIOSTIMULANT", "rol": "product",
             "hoeveelheid": 600, "eenheid": "ml", "doel": "Pythium soorten"}])]}
        middelen, regels = a4.behandelingen(export, VAKKEN)
        self.assertEqual({m["code"]: m["type"] for m in middelen}, {"p-ser": "gewasbescherming", "p-nat": "biologie"})
        self.assertEqual([(r["vaknummer"], r["middel_code"], r["dosering"]) for r in regels],
                         [(11, "p-ser", 1000), (12, "p-ser", 1000), (11, "p-nat", 600), (12, "p-nat", 600)])
        r = regels[0]
        self.assertEqual((r["datum"], r["mix"], r["aantal_vakken"], r["registratie"], r["extern_id"]),
                         (date(2026, 10, 13), "100 l", 2, "r1", "r1:11:0"))

    def test_hele_tuin_en_zonder_vakken_vallen_weg(self):
        export = {"registraties": [registratie("alle", list(range(1, 40))), registratie("geen", []),
                                   registratie("twee", [1, 2])]}
        _, regels = a4.behandelingen(export, VAKKEN)
        self.assertEqual({r["registratie"] for r in regels}, {"twee"})
        self.assertEqual(a4.overgeslagen(export, VAKKEN), (1, 1))

    def test_toevoeging_en_mix_met_komma(self):
        export = {"registraties": [registratie("r", [5], mix={"hoeveelheid": 12.5, "eenheid": "l"}, producten=[
            {"naam": "MOTTO", "id": "p-mot", "categorie": "ADMISSION_SUBSTANCE", "rol": "toevoeging",
             "hoeveelheid": 85, "eenheid": "l", "doel": None}])]}
        _, regels = a4.behandelingen(export, VAKKEN)
        self.assertEqual((regels[0]["opmerking"], regels[0]["mix"]), ("toevoeging", "12,5 l"))


if __name__ == "__main__":
    unittest.main()

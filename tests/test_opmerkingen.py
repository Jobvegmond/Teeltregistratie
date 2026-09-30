"""Tests voor logic/opmerkingen.py: zoeken en filteren van opmerkingen per vak."""
import unittest
from datetime import date

from logic import opmerkingen as om


def opm(id_, datum, tuin_id=3, vak=10, start="2026-08-10", categorie="Groei", tekst="groei blijft achter",
        code="263310", teelt_id=None):
    return {"id": id_, "teelt_id": teelt_id or id_, "datum": datum, "categorie": categorie, "tekst": tekst,
            "gebruiker": "job", "tuin_id": tuin_id, "afdeling": 3, "vaknummer": vak, "code": code, "start": start}


ALLE = [
    opm(1, "2026-09-20"),
    opm(2, "2026-09-02", tuin_id=1, vak=5, start="2026-08-04", categorie="Water", tekst="Druppelaar verstopt",
        code="263205"),
    opm(3, "2026-09-25", vak=11, start="2026-08-17", categorie="Ziekte/plagen", tekst="trips", code="263411"),
]


class TestFilter(unittest.TestCase):
    def test_zonder_filters_alles_oud_naar_nieuw(self):
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE)], [2, 1, 3])

    def test_teelt_is_plantweek(self):
        self.assertEqual(om.teelt_van(ALLE[0]), (2026, 33))
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, teelten={(2026, 33)})], [1])

    def test_vak_en_tuin(self):
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, vakken={10, 11}, tuinen={3})], [1, 3])
        self.assertEqual(om.filter_opmerkingen(ALLE, vakken={5}, tuinen={3}), [])

    def test_datum_inclusief(self):
        uit = om.filter_opmerkingen(ALLE, van=date(2026, 9, 20), tot=date(2026, 9, 25))
        self.assertEqual([o["id"] for o in uit], [1, 3])

    def test_categorie_en_zoeken(self):
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, categorieen={"Water"})], [2])
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, zoek="DRUPPEL")], [2])
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, zoek="263411")], [3])

    def test_alleen_gegeven_vakken(self):
        self.assertEqual([o["id"] for o in om.filter_opmerkingen(ALLE, teelt_ids={1, 2})], [2, 1])
        self.assertEqual(om.filter_opmerkingen(ALLE, teelt_ids=set()), [])


if __name__ == "__main__":
    unittest.main()

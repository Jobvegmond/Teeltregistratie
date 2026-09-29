"""Tests voor logic/planning_editor.py: wat de concepttabel in Planning in één keer doorvoert."""
import unittest
from datetime import date

from logic import planning_editor as pe


def rij(start, planten=30000, bevestigen=False, verwijderen=False):
    return {"start": start, "planten": planten, "bevestigen": bevestigen, "verwijderen": verwijderen}


ORIGINEEL = {1: rij(date(2026, 10, 5)), 2: rij(date(2026, 10, 6)), 3: rij(date(2026, 10, 7)),
             4: rij(date(2026, 10, 8))}


class TestPlanningEditor(unittest.TestCase):
    def test_niets_veranderd(self):
        w = pe.wijzigingen(ORIGINEEL, dict(ORIGINEEL))
        self.assertFalse(pe.heeft_wijzigingen(w))
        self.assertEqual(pe.samenvatting(w), "0 gewijzigd, 0 bevestigd, 0 verwijderd")

    def test_wijzigen_bevestigen_verwijderen(self):
        bewerkt = dict(ORIGINEEL)
        bewerkt[1] = rij(date(2026, 10, 12))                                   # andere datum
        bewerkt[2] = rij(date(2026, 10, 9), planten=28000, bevestigen=True)    # datum én bevestigen
        bewerkt[3] = rij(date(2026, 10, 20), verwijderen=True)                 # verwijderen wint van datum
        w = pe.wijzigingen(ORIGINEEL, bewerkt)
        self.assertEqual(w["gewijzigd"], [(1, date(2026, 10, 12)), (2, date(2026, 10, 9))])
        self.assertEqual(w["bevestigd"], [(2, 28000)])
        self.assertEqual(w["verwijderd"], [3])
        self.assertEqual(pe.samenvatting(w), "2 gewijzigd, 1 bevestigd, 1 verwijderd")

    def test_bevestigen_en_verwijderen_tegelijk_is_conflict(self):
        bewerkt = dict(ORIGINEEL)
        bewerkt[4] = rij(date(2026, 10, 8), bevestigen=True, verwijderen=True)
        w = pe.wijzigingen(ORIGINEEL, bewerkt)
        self.assertEqual((w["bevestigd"], w["verwijderd"], w["conflict"]), ([], [], [4]))
        self.assertIn("1 overgeslagen", pe.samenvatting(w))

    def test_alleen_planten_aangepast_wordt_niet_bewaard(self):
        bewerkt = dict(ORIGINEEL)
        bewerkt[1] = rij(date(2026, 10, 5), planten=12345)
        self.assertFalse(pe.heeft_wijzigingen(pe.wijzigingen(ORIGINEEL, bewerkt)))

    def test_bevestigen_zonder_planten(self):
        bewerkt = dict(ORIGINEEL)
        bewerkt[1] = rij(date(2026, 10, 5), planten=None, bevestigen=True)
        self.assertEqual(pe.wijzigingen(ORIGINEEL, bewerkt)["bevestigd"], [(1, None)])


if __name__ == "__main__":
    unittest.main()

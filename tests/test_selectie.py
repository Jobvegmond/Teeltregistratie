"""Tests voor logic/selectie.py: vak/teelt kiezen met losse velden tuin, vak, week en jaar."""
import unittest

from logic import selectie as sel


def item(id_, tuin_id, vak, jaar, week):
    return {"id": id_, "tuin_id": tuin_id, "vak": vak, "jaar": jaar, "week": week}


ITEMS = [
    item(1, 3, 10, 2025, 33), item(2, 3, 10, 2026, 33), item(3, 3, 10, 2026, 45),
    item(4, 3, 11, 2026, 33), item(5, 1, 10, 2026, 34),
]


class TestSelectie(unittest.TestCase):
    def test_vakken_per_tuin(self):
        self.assertEqual(sel.vakken(ITEMS, tuin=3), [10, 11])
        self.assertEqual(sel.vakken(ITEMS), [10, 11])
        self.assertEqual(sel.vakken(ITEMS, tuin=1), [10])

    def test_weken_bij_vak(self):
        self.assertEqual(sel.weken(ITEMS, tuin=3, vak=10), [33, 45])
        self.assertEqual(sel.weken(ITEMS, vak=10), [33, 34, 45])     # beide tuinen
        self.assertEqual(sel.weken(ITEMS), [33, 34, 45])

    def test_weken_in_de_tijd(self):
        items = [item(1, 3, 1, 2025, 50), item(2, 3, 2, 2025, 52), item(3, 3, 3, 2026, 1), item(4, 3, 4, 2026, 2),
                 item(5, 3, 5, 2025, 2)]
        # week 2 kwam ook in 2025 voor, maar telt op zijn laatste keer (2026)
        self.assertEqual(sel.weken(items), [50, 52, 1, 2])

    def test_vakken_in_week(self):
        self.assertEqual(sel.vakken(ITEMS, tuin=3, week=33), [10, 11])
        self.assertEqual(sel.vakken(ITEMS, tuin=3, week=45), [10])

    def test_jaren_bij_week(self):
        self.assertEqual(sel.jaren(ITEMS, 33, tuin=3, vak=10), [2025, 2026])
        self.assertEqual(sel.jaren(ITEMS, 45, tuin=3, vak=10), [2026])
        self.assertEqual(sel.jaren(ITEMS, 34, tuin=3), [])

    def test_laatste_en_gekozen(self):
        self.assertEqual(sel.laatste(ITEMS, tuin=3, vak=10)["id"], 3)
        self.assertIsNone(sel.laatste(ITEMS, tuin=1, vak=11))
        self.assertEqual([i["id"] for i in sel.gekozen(ITEMS, 3, 10, 33, 2025)], [1])

    def test_geldig(self):
        self.assertEqual(sel.geldig(33, [33, 45], 45), 33)
        self.assertEqual(sel.geldig(34, [33, 45], 45), 45)


if __name__ == "__main__":
    unittest.main()

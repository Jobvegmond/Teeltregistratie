"""Tests voor logic/afdelingen.py (teeltvolgorde van de afdelingen)."""
import unittest

from logic.afdelingen import sorteer_afdelingen


class TestAfdelingsvolgorde(unittest.TestCase):
    def test_tuin_3_in_teeltvolgorde(self):
        self.assertEqual(sorteer_afdelingen([4, 2, 1, 3], 3), [1, 3, 4, 2])

    def test_tuin_1_oplopend(self):
        self.assertEqual(sorteer_afdelingen([3, 1, 4, 2], 1), [1, 2, 3, 4])

    def test_onbekende_afdeling_en_dubbelen(self):
        self.assertEqual(sorteer_afdelingen([5, 2, 2, 1, None], 3), [1, 2, 5])

    def test_onbekende_tuin_numeriek(self):
        self.assertEqual(sorteer_afdelingen([3, 1, 2], 9), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()

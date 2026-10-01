"""Tests voor importeer_florgib_overview.koppel: welke Fg bij welk vak hoort."""
import unittest
from datetime import date

from importeer_florgib_overview import koppel

VANDAAG = date(2026, 10, 1)


def teelt(id, vak, start, oogst=None, florgib=None, tuin=3):
    return {"id": id, "tuin": tuin, "vak": vak, "code": None, "start": start, "oogst": oogst, "florgib": florgib}


class TestKoppel(unittest.TestCase):
    def test_eerste_fg_tussen_planten_en_oogst(self):
        teelten = [teelt(1, 4, "2026-02-25", "2026-04-29"), teelt(2, 4, "2026-05-04", "2026-06-25")]
        overview = {3: {4: [date(2026, 3, 30), date(2026, 4, 2), date(2026, 6, 1)]}}
        uit = koppel(teelten, overview, VANDAAG)
        self.assertEqual([(t["id"], fg, n) for t, fg, n in uit],
                         [(1, date(2026, 3, 30), 2), (2, date(2026, 6, 1), 1)])

    def test_app_registratie_blijft_staan(self):
        teelten = [teelt(1, 4, "2026-02-25", "2026-04-29", florgib="2026-03-31")]
        self.assertEqual(koppel(teelten, {3: {4: [date(2026, 3, 30)]}}, VANDAAG), [])

    def test_lopend_vak_tot_de_volgende_planting_of_vandaag(self):
        # Lopend vak: een Fg ná vandaag of ná de volgende planting hoort er niet bij.
        teelten = [teelt(1, 7, "2026-09-01"), teelt(2, 7, "2026-12-01")]
        overview = {3: {7: [date(2026, 9, 20), date(2026, 12, 20)]}}
        self.assertEqual([(t["id"], fg) for t, fg, _ in koppel(teelten, overview, VANDAAG)],
                         [(1, date(2026, 9, 20))])

    def test_andere_tuin_telt_niet(self):
        teelten = [teelt(1, 4, "2026-02-25", "2026-04-29", tuin=1)]
        self.assertEqual(koppel(teelten, {3: {4: [date(2026, 3, 30)]}}, VANDAAG), [])


if __name__ == "__main__":
    unittest.main()

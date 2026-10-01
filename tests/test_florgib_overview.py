"""Tests voor importeer_florgib_overview.koppel: welke Fg bij welk vak hoort."""
import unittest
from datetime import date

from importeer_florgib_overview import gewicht_per_week, koppel, koppel_lengte, koppel_oogst

VANDAAG = date(2026, 10, 1)


def teelt(id, vak, start, oogst=None, florgib=None, tuin=3, lengte_half=None, **rest):
    return {"id": id, "tuin": tuin, "vak": vak, "code": None, "start": start, "oogst": oogst, "florgib": florgib,
            "lengte_half": lengte_half, **rest}


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


class TestKoppelLengte(unittest.TestCase):
    def test_per_plantweek_alleen_met_florgib_en_zonder_lengte(self):
        teelten = [teelt(1, 10, "2026-03-16", florgib="2026-04-20"),          # wk 12, krijgt 42
                   teelt(2, 11, "2026-03-17"),                                 # wk 12, geen Florgib
                   teelt(3, 12, "2026-03-18"),                                 # wk 12, Florgib uit deze import
                   teelt(4, 13, "2026-07-01", florgib="2026-07-28", lengte_half=31.0),  # app gaat voor
                   teelt(5, 14, "2025-03-17", florgib="2025-04-20"),          # ander jaar
                   teelt(6, 15, "2026-03-16", florgib="2026-04-20", tuin=1)]  # tuin 1
        uit = koppel_lengte(teelten, 2026, {12: 42.0, 27: 35.0}, krijgt_florgib={3})
        self.assertEqual([(t["id"], lengte) for t, lengte in uit], [(1, 42.0), (3, 42.0)])


class TestKoppelOogst(unittest.TestCase):
    def test_alleen_lege_velden_van_afgeronde_vakken(self):
        teelten = [teelt(1, 2, "2026-06-08", oogst="2026-07-27"),                      # wk 24: alles leeg
                   teelt(2, 3, "2026-06-15", oogst="2026-08-03", lengte_eind=66.0),     # wk 25: lengte staat er
                   teelt(3, 4, "2026-06-22", oogst="2026-08-10", oogstgewicht=640.0, rijpheid="2-3"),
                   teelt(4, 5, "2026-06-15"),                                           # lopend
                   teelt(5, 6, "2026-06-15", oogst="2026-08-03", rijpheid="2-3")]       # rijpheid blijft
        gewichten = gewicht_per_week({25: 750.0, 26: 625.0}, {24: 800.0, 25: 800.0, 26: 675.0})
        self.assertEqual(gewichten, {24: (800.0, "3-4"), 25: (775.0, "2-4"), 26: (650.0, "2-4")})
        uit = koppel_oogst(teelten, 2026, {24: 65.0, 25: 65.0, 26: 70.0}, gewichten)
        self.assertEqual([(t["id"], v) for t, v in uit], [
            (1, {"lengte_eind": 65.0, "oogstgewicht": 800.0, "rijpheid": "3-4"}),
            (2, {"oogstgewicht": 775.0, "rijpheid": "2-4"}),
            (3, {"lengte_eind": 70.0}),
            (5, {"lengte_eind": 65.0, "oogstgewicht": 775.0}),
        ])

    def test_eigen_import_wordt_bijgewerkt_app_niet(self):
        teelten = [teelt(1, 13, "2026-06-15", oogst="2026-08-03", oogstgewicht=800.0, rijpheid="3-4"),  # eigen
                   teelt(2, 14, "2026-06-15", oogst="2026-08-03", oogstgewicht=640.0, rijpheid="2-3")]  # app
        uit = koppel_oogst(teelten, 2026, {}, {25: (775.0, "2-4")}, eigen={1})
        self.assertEqual([(t["id"], v) for t, v in uit], [(1, {"oogstgewicht": 775.0, "rijpheid": "2-4"})])


if __name__ == "__main__":
    unittest.main()

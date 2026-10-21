"""Tests voor logic/registreren.py."""
import unittest
from datetime import date

from logic import registreren as reg

VANDAAG = date(2026, 10, 21)


def teelt(id_, vak, start, tuin=3, oogst=None, emmers=None, lengte_half=None, planten=None):
    return {"id": id_, "tuin_id": tuin, "vaknummer": vak, "afdeling": 1, "code": f"c{id_}",
            "datum_teelt_start": start, "datum_oogst": oogst, "datum_half": None, "lengte_half": lengte_half,
            "lengte_eind": None, "aantal_planten": planten, "emmers": emmers}


class TestLopendeVakken(unittest.TestCase):
    def test_alleen_lopend_in_deze_tuin(self):
        teelten = [teelt(1, 5, "2026-09-01"), teelt(2, 6, "2026-09-01", tuin=1),
                   teelt(3, 7, "2026-08-01", oogst="2026-10-10"), teelt(4, 8, "2026-11-01"),
                   teelt(5, 2, "2026-08-25", emmers=30.0, planten=4000)]
        stook = {1: {"florgib_verwacht": date(2026, 10, 20), "prognose": date(2026, 11, 20)}}
        vakken = reg.lopende_vakken(teelten, 3, VANDAAG, stook)
        self.assertEqual([r["vak"] for r in vakken], [2, 5])                 # op plantdatum
        self.assertEqual(vakken[0]["uitval"], 25.0)                          # 4000 planten, 3000 stelen
        self.assertEqual(vakken[1]["florgib_verwacht"], date(2026, 10, 20))
        self.assertEqual(vakken[1]["plantweek"], 36)


class TestTeRegistreren(unittest.TestCase):
    def test_eigen_waarde_gaat_voor_de_waarde_voor_alle(self):
        regels = [{"id": 1, "vak": 5, "Kies": True, "lengte": None, "gram": None},
                  {"id": 2, "vak": 6, "Kies": True, "lengte": 31.5, "gram": float("nan")},
                  {"id": 3, "vak": 7, "Kies": False, "lengte": None, "gram": None},     # doet niet mee
                  {"id": 4, "vak": 8, "Kies": False, "lengte": 30.0, "gram": None}]     # ingevuld = doet mee
        uit = reg.te_registreren(regels, ["lengte", "gram"], {"lengte": 32.0, "gram": 2.5})
        self.assertEqual(uit, [(1, 5, {"lengte": 32.0, "gram": 2.5}), (2, 6, {"lengte": 31.5, "gram": 2.5}),
                               (4, 8, {"lengte": 30.0, "gram": 2.5})])

    def test_nul_is_niet_ingevuld_en_tekst_blijft_tekst(self):
        regels = [{"id": 1, "vak": 5, "Kies": True, "lengte": 0, "rijpheid": "3"}]
        uit = reg.te_registreren(regels, ["lengte", "rijpheid"], {"lengte": 0, "rijpheid": None})
        self.assertEqual(uit, [(1, 5, {"lengte": None, "rijpheid": "3"})])
        self.assertEqual(reg.zonder(uit, "lengte"), [5])


class TestNogTeDoen(unittest.TestCase):
    def vakken(self):
        return [{"vak": 5, "lengte_half": None, "florgib_verwacht": date(2026, 10, 19), "emmers": 0,
                 "prognose": date(2026, 10, 23), "lengte_eind": None},
                {"vak": 6, "lengte_half": None, "florgib_verwacht": date(2026, 10, 30), "emmers": 12.0,
                 "prognose": None, "lengte_eind": None},
                {"vak": 7, "lengte_half": 30.0, "florgib_verwacht": date(2026, 10, 18), "emmers": 0,
                 "prognose": date(2026, 12, 1), "lengte_eind": None}]

    def test_florgib(self):
        self.assertEqual(reg.nog_te_doen("florgib", self.vakken(), VANDAAG), [(5, "verwacht 19-10 (2 d over tijd)")])

    def test_emmers(self):
        self.assertEqual(reg.nog_te_doen("emmers", self.vakken(), VANDAAG),
                         [(6, "in de oogst, 12 emmers"), (5, "prognose 23-10 (over 2 d)")])

    def test_lengte(self):
        self.assertEqual(reg.nog_te_doen("lengte", self.vakken(), VANDAAG),
                         [(6, "in de oogst (12 emmers), nog geen lengte")])


class TestLaatsteRegistraties(unittest.TestCase):
    def test_per_soort_en_alleen_deze_tuin(self):
        log = [("t4", "job", "aangemaakt", "oogstregistratie", 90, "3 emmers geregistreerd op 2026-10-21 voor teelt 1"),
               ("t3", "job", "gewijzigd", "teelt", "2", "Florgib lengte 30 cm geregistreerd op 2026-10-20"),  # tekst
               ("t2", "job", "gewijzigd", "teelt", 99, "Florgib lengte 28 cm geregistreerd op 2026-10-20"),  # andere tuin
               ("t1", "job", "gewijzigd", "teelt", 1, "Vak afgerond op 2026-10-19")]
        vak_van = {1: 5, 2: 6}
        self.assertEqual([(r["vak"], r["omschrijving"]) for r in reg.laatste_registraties(log, "emmers", vak_van)],
                         [(5, "3 emmers geregistreerd op 2026-10-21"), (5, "Vak afgerond op 2026-10-19")])
        self.assertEqual([r["vak"] for r in reg.laatste_registraties(log, "florgib", vak_van)], [6])


if __name__ == "__main__":
    unittest.main()

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

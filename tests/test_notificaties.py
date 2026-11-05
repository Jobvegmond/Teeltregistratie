"""Tests voor logic/notificaties.py: meldingen voor water, spuiten en registraties."""
import unittest
from datetime import date

from logic import notificaties as nt

VANDAAG = date(2026, 11, 5)


def advies(vak, soort, vorige_dag=date(2026, 10, 30)):
    return {"vak": vak, "advies": soort, "kans": 0.8, "kans_morgen": None, "reden": f"Vak {vak}",
            "kenmerken": {"leeftijd": 10, "vorige_dag": vorige_dag, "vorige": 10.0, "S": 2000.0, "S_vandaag": 0.0}}


def vak(nummer, **velden):
    basis = {"vak": nummer, "geplant": date(2026, 9, 1), "lengte_half": None, "lengte_eind": None, "emmers": 0,
             "florgib_verwacht": None, "prognose": None}
    return {**basis, **velden}


class TestWater(unittest.TestCase):
    def test_water_en_twijfel_apart(self):
        uit = nt.water([advies(22, "water"), advies(23, "water"), advies(17, "twijfel"), advies(5, "niet nodig"),
                        advies(6, "gegeven")])
        self.assertEqual([m["titel"] for m in uit], ["Water geven: vak 22, 23", "Misschien water: vak 17"])
        self.assertTrue(all(m["soort"] == "water" and m["regels"] for m in uit))

    def test_niets_te_doen(self):
        self.assertEqual(nt.water([advies(5, "niet nodig")]), [])


class TestSpuiten(unittest.TestCase):
    def test_vandaag_en_morgen(self):
        taken = [{"datum": date(2026, 11, 7), "vakken": [9], "titel": "Florgib + CXDS vak 9", "toelichting": "x"},
                 {"datum": date(2026, 11, 6), "vakken": [25], "titel": "Inwateren", "toelichting": "y"},
                 {"datum": date(2026, 11, 5), "vakken": [17], "titel": "CXDS-blok vak 17–21", "toelichting": "z"}]
        uit = nt.spuiten(taken, VANDAAG)
        self.assertEqual([m["titel"] for m in uit], ["CXDS-blok vak 17–21", "Inwateren"])
        self.assertEqual(uit[1]["regels"], ["morgen · y"])


class TestRegistraties(unittest.TestCase):
    def test_alleen_wat_al_had_moeten_gebeuren(self):
        vakken = [vak(9, florgib_verwacht=date(2026, 11, 3)),            # Florgib over tijd
                  vak(10, florgib_verwacht=date(2026, 11, 8)),           # nog niet aan de beurt
                  vak(11, florgib_verwacht=date(2026, 11, 1), lengte_half=32.5),  # al ingevuld
                  vak(12, prognose=date(2026, 11, 4)),                   # oogst verwacht, geen emmers
                  vak(13, prognose=date(2026, 11, 4), emmers=12),        # in de oogst, geen lengte
                  vak(14, emmers=30, lengte_eind=70.0)]                  # alles ingevuld
        uit = nt.registraties(vakken, VANDAAG)
        self.assertEqual([(m["actie"], m["titel"]) for m in uit],
                         [("Florgib", "Florgib invullen: vak 9"), ("Emmers", "Nog geen emmers: vak 12"),
                          ("Lengte en gewicht", "Oogstlengte invullen: vak 13")])
        self.assertEqual(uit[0]["regels"], ["Vak 9 · verwacht 03-11 (2 dagen geleden)"])

    def test_volgorde_van_alles(self):
        uit = nt.alles([advies(22, "water")], [], [vak(9, florgib_verwacht=VANDAAG)], VANDAAG)
        self.assertEqual([m["soort"] for m in uit], ["water", "registratie"])
        self.assertEqual(uit[1]["regels"], ["Vak 9 · verwacht 05-11 (vandaag)"])


if __name__ == "__main__":
    unittest.main()

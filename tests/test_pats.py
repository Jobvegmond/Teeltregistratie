"""Tests voor logic/pats.py: PATS-tellingen naar regels en dagtotalen per insect."""
import unittest
from datetime import date

from logic import pats as lp

ANTWOORD = {
    "trapeye": [
        {"row_id": 2, "post_id": 3,
         "absolute_count": [{"date": "20261020", "24": 1.0, "28": 1.0}, {"date": "20261022", "24": 1.0, "28": 2.0}],
         "new_counts": [{"date": "20261020", "24": None, "28": None}, {"date": "20261022", "24": 0.0, "28": 1.0}]},
        {"row_id": 6, "post_id": 9,
         "absolute_count": [{"date": "20261022", "28": 3.0}],
         "new_counts": [{"date": "20261022", "28": 2.5}]},
    ],
    "c": [
        {"row_id": 39, "post_id": 4, "spot_id": 1, "system_id": 1,
         "counts": [{"date": "20261020", "1": 1, "2": 18, "63": 3, "64": 20}, {"date": "20261021", "1": 0, "2": 10}]},
    ],
}
KLASSEN = {1: "Chrysodeixis chalcites", 2: "Duponchelia fovealis", 24: "Trialeurodes vaporariorum",
           28: "Thysanoptera", 63: "Anomalies", 64: "No size"}


class TestPats(unittest.TestCase):
    def test_regels(self):
        regels = lp.regels(ANTWOORD, KLASSEN, tuin_id=7, section_id=58)
        # Geen Anomalies/No size; Trap-Eye met stand en nieuw, PATS-C alleen nieuw.
        self.assertNotIn(63, {r["klasse_id"] for r in regels})
        plaat = {(r["rij"], r["datum"], r["klasse_id"]): r for r in regels if r["apparaat"] == "trapeye"}
        self.assertEqual(plaat[(2, date(2026, 10, 22), 28)]["stand"], 2.0)
        self.assertEqual(plaat[(2, date(2026, 10, 22), 28)]["nieuw"], 1.0)
        self.assertIsNone(plaat[(2, date(2026, 10, 20), 28)]["nieuw"])
        sensor = [r for r in regels if r["apparaat"] == "c"]
        self.assertEqual(len(sensor), 4)
        self.assertEqual({r["tuin_id"] for r in regels}, {7})
        self.assertEqual(next(r for r in sensor if r["klasse_id"] == 2)["klasse"], "Duponchelia fovealis")

    def test_dagtotalen(self):
        totalen = lp.dagtotalen(lp.regels(ANTWOORD, KLASSEN, 7, 58))
        # Alleen trips en turkse mot (GETOOND); witte vlieg en Duponchelia niet.
        self.assertEqual([(t["insect"], t["datum"], t["totaal"]) for t in totalen], [
            ("Trips", date(2026, 10, 22), 3.5),                    # 1 + 2,5; op 20-10 geen "nieuw"
            ("Turkse mot", date(2026, 10, 20), 1.0), ("Turkse mot", date(2026, 10, 21), 0.0)])
        trips = totalen[0]
        self.assertEqual((trips["apparaten"], trips["met_vangst"]), (2, 2))

    def test_per_vak_beide_buurvakken(self):
        regels = lp.regels(ANTWOORD, KLASSEN, 7, 58)
        uit = lp.per_vak(regels, (-1, 0), set(range(1, 40)))
        # Rij 2 → vak 1 en 2, rij 6 → vak 5 en 6; op 20-10 geen "nieuw"; PATS-C telt niet mee.
        self.assertEqual([(r["vak"], r["datum"]) for r in uit],
                         [(1, date(2026, 10, 22)), (2, date(2026, 10, 22)), (5, date(2026, 10, 22)),
                          (6, date(2026, 10, 22))])
        self.assertEqual(uit[0]["nieuw"], {28: 1.0})
        self.assertEqual(uit[0]["platen"], [(2, 3)])
        self.assertEqual(lp.kort(uit[0]["nieuw"]), "1")             # alleen trips: alleen het getal
        self.assertEqual(lp.kort(uit[2]["nieuw"]), "2,5")
        self.assertEqual(lp.kort({28: 0.0}), "0")
        # Een vak dat niet bestaat (rij 2 → vak 1 en 2, alleen vak 2 gevraagd).
        self.assertEqual({r["vak"] for r in lp.per_vak(regels, (-1, 0), {2})}, {2})


if __name__ == "__main__":
    unittest.main()

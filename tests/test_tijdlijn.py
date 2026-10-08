"""Tests voor logic/tijdlijn.py: stukken per vak, overlap en oogst per week."""
import unittest
from datetime import date, timedelta

from logic import tijdlijn

VANDAAG = date(2026, 10, 8)


def plan_van(start):
    return start + timedelta(days=70)


def teelt(id_, vak, start, oogst=None):
    return {"id": id_, "vaknummer": vak, "datum_teelt_start": start, "datum_oogst": oogst, "code": f"c{id_}", "ras": None}


class TestStukken(unittest.TestCase):
    def setUp(self):
        self.lopend = teelt(2, 1, "2026-09-01")
        self.teelten = [teelt(1, 1, "2026-06-01", "2026-08-20"), self.lopend, teelt(3, 2, "2026-10-20")]
        self.statussen = {1: {"teelt": self.lopend, "start": date(2026, 9, 1), "plan": date(2026, 11, 10),
                              "prognose": date(2026, 11, 14), "klasse": "o1"}}
        self.concepten = [(7, 1, "2026-11-12", 10, "2027-01-21", None)]

    def test_soorten_per_vak(self):
        uit = tijdlijn.stukken(self.teelten, self.statussen, self.concepten, VANDAAG, plan_van)
        vak1 = [(s["soort"], s["start"], s["eind"]) for s in uit if s["vak"] == 1]
        self.assertEqual(vak1, [
            ("afgerond", date(2026, 6, 1), date(2026, 8, 20)),
            ("lopend", date(2026, 9, 1), VANDAAG),
            ("prognose", VANDAAG, date(2026, 11, 14)),
            ("concept", date(2026, 11, 12), date(2027, 1, 21)),
        ])
        gepland, = [s for s in uit if s["vak"] == 2]
        self.assertEqual((gepland["soort"], gepland["eind"]), ("gepland", date(2026, 12, 29)))
        self.assertEqual([s["klasse"] for s in uit if s["soort"] == "lopend"], ["o1"])

    def test_overlap_met_prognose_van_lopende_teelt(self):
        # Het concept start op 12-11, de lopende teelt is volgens de prognose pas op 14-11 klaar.
        uit = tijdlijn.stukken(self.teelten, self.statussen, self.concepten, VANDAAG, plan_van)
        self.assertEqual(tijdlijn.overlap(uit), [{"vak": 1, "start": date(2026, 11, 12), "eind": date(2026, 11, 14)}])

    def test_oogst_per_week(self):
        uit = tijdlijn.stukken(self.teelten, self.statussen, self.concepten, VANDAAG, plan_van)
        per_week = tijdlijn.oogst_per_week(uit, self.statussen, date(2026, 10, 1), date(2026, 12, 31))
        # 14-11 (prognose vak 1) valt in de week van zo 08-11; 29-12 (gepland vak 2) in die van zo 27-12.
        self.assertEqual(per_week, {date(2026, 11, 8): 1, date(2026, 12, 27): 1})


if __name__ == "__main__":
    unittest.main()

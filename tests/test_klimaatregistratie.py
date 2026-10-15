"""Tests voor logic/klimaatregistratie.py: behandelingen uit het blad Overview van de klimaatregistratie."""
import unittest
from datetime import date

from logic import klimaatregistratie as kr

# Kop: kolom 0 = vak, 1 = regel; daarna week 40 van 2026 (zo 27-09 t/m za 03-10) en zo 04-10 (week 41).
KOP = [
    (None, None, 2026, None, None, None, None, None, None, None),
    (None, None, 40, None, None, None, None, None, None, 41),
    (None, None, "Z", "M", "D", "W", "D", "V", "Z", "Z"),
    (None, "Kolom1", "Kolom2", "Kolom3", "Kolom4", "Kolom5", "Kolom6", "Kolom7", "Kolom8", "Kolom9"),
]


def blad(*vakrijen):
    return KOP + list(vakrijen)


class TestReeksen(unittest.TestCase):
    def test_aaneengesloten_dagen_op_de_eerste_dag(self):
        rijen = blad(
            (7, "W", None, None, None, None, None, None, None, None),
            (None, "GBM", None, "Ri", "As Se", None, "Te", None, "Fg", "Xe"),
            (None, "Bio", "B5", None, None, None, None, None, None, None),
        )
        uit = kr.behandelingen(rijen)
        self.assertEqual(uit, [
            (7, date(2026, 9, 28), "GBM", ["Ri", "As", "Se"]),       # ma + di horen bij maandag
            (7, date(2026, 10, 1), "GBM", ["Te"]),
            (7, date(2026, 10, 3), "GBM", ["Fg", "Xe"]),             # za 03-10 en zo 04-10 lopen door de week heen
            (7, date(2026, 9, 27), "Bio", ["B5"]),
        ])
        self.assertEqual(kr.behandelingen(rijen, tot=date(2026, 10, 1)),
                         [(7, date(2026, 9, 28), "GBM", ["Ri", "As", "Se"]), (7, date(2026, 9, 27), "Bio", ["B5"])])


class TestRegels(unittest.TestCase):
    def test_middelen_en_overslaan(self):
        beh = [(7, date(2026, 9, 28), "GBM", ["Ri", "Fg", "La", "Ve", "Vec"]),
               (8, date(2026, 9, 28), "Bio", ["B5", "IM", "Zz"])]
        middelen, regels, onbekend = kr.regels(beh, 3, "klimaatregistratie-tuin3")
        self.assertEqual([(r["vaknummer"], r["middel_code"]) for r in regels],
                         [(7, "Rizolex"), (7, "Vectine"), (8, "Natrubac 08"), (8, "IJzer en mangaan"), (8, "code Zz")])
        self.assertEqual(onbekend, {"Zz": 1})
        soorten = {m["naam"]: m["type"] for m in middelen}
        self.assertEqual((soorten["Rizolex"], soorten["Natrubac 08"], soorten["IJzer en mangaan"], soorten["code Zz"]),
                         ("gewasbescherming", "biologie", "voeding", "biologie"))
        self.assertTrue(all(r["dosering"] is None for r in regels))
        self.assertEqual(regels[0]["registratie"], "klimaatregistratie-tuin3:2026-09-28:GBM:Ri Fg La Ve Vec")


if __name__ == "__main__":
    unittest.main()

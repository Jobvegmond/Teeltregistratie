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
               (8, date(2026, 9, 28), "Bio", ["B5", "IM", "Hy", "Zz"])]
        middelen, regels, onbekend = kr.regels(beh, 3, "klimaatregistratie-tuin3")
        self.assertEqual([(r["vaknummer"], r["middel_code"]) for r in regels],
                         [(7, "Rizolex"), (7, "Vectine"), (8, "Biota 500"), (8, "IJzer en mangaan"), (8, "Hypoaspis"),
                          (8, "code Zz")])
        self.assertEqual(regels[4]["methode"], "gestrooid")
        self.assertEqual(onbekend, {"Zz": 1})
        soorten = {m["naam"]: m["type"] for m in middelen}
        self.assertEqual((soorten["Rizolex"], soorten["Biota 500"], soorten["IJzer en mangaan"], soorten["code Zz"]),
                         ("gewasbescherming", "biologie", "voeding", "biologie"))
        self.assertTrue(all(r["dosering"] is None for r in regels))
        self.assertEqual(regels[0]["registratie"], "klimaatregistratie-tuin3:2026-09-28:GBM:Ri Fg La Ve Vec")




class TestAfkorting(unittest.TestCase):
    """De afkortingen op de tijdlijn (Overzicht, weergave Bespuitingen) voor de namen uit Agro4all."""

    def test_namen_uit_agro4all_en_klimaatregistratie(self):
        verwacht = {
            "Rizolex vloeibaar": "Ri", "ASPERELLO T34 Biocontrol": "As", "CLOSER": "Cl", "Vectine PLUS": "Ve",
            "Sivanto Prime": "Si", "Serenade Max": "Se", "Ranman Top": "Ra", "Luna Privilege": "Lu",
            "MONcontrol Mix": "M", "Power Food 3.0": "P", "Soiltech Root & Shoot": "Rs", "Root & Shoot": "Rs",
            "Biota 500": "B5", "Biota 820": "B8", "D-6 Force": "D6", "SilicaPower": "Sc", "Hypoaspis": "Hy",
            "X-Tend": "Xt", "ConSecta": "Co", "IJzer en mangaan": "IM", "IJzer (Innofer)": "Ijz",
            "Innofer Fe++": "Ijz", "INNO-Mn++": "Mn", "Mangaan (INNO-Mn)": "Mn", "Florgib ST": "Fg",
            "code H": "H", "code Oc": "Oc", "Natrubac 08": "Na", None: "?",
        }
        for naam, code in verwacht.items():
            self.assertEqual(kr.afkorting(naam), code, naam)


if __name__ == "__main__":
    unittest.main()

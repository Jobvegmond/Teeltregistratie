"""Tests voor logic/teeltvergelijking.py: kengetallen per teelt, m²-weging, prognose en vergelijking."""
import unittest
from datetime import date

from logic import teeltvergelijking as tv
from logic.lichtlijn import t_ideaal


def regel(id_, tuin, vak, start, oogst=None, half=None, m2=500.0, **extra):
    k = {"id": id_, "tuin_id": tuin, "vaknummer": vak, "afdeling": 1, "code": f"C{id_}",
         "datum_teelt_start": start, "datum_oogst": oogst, "datum_half": half,
         "lichtsom": 50 * 800.0, "klimaatdagen": 50, "gem_temperatuur": 19.0,
         "liters": 100.0, "warmte_mj_per_m2": 80.0, "energiedagen": 50, "looptijd_dagen": 50,
         "aantal_planten": None, "uitval_pct": None, "stelen": None,
         "lengte_eind": None, "lengte_half": None, "oogstgewicht": None,
         "beoordeling": None, "wortel": None, "plantmaat": None, "uniformiteit": None}
    k.update(extra)
    return k, m2


class TestTeelt(unittest.TestCase):
    def test_fasen_en_klimaat(self):
        k, m2 = regel(1, 3, 5, "2026-08-03", oogst="2026-09-22", half="2026-09-01", lengte_eind=80.0,
                      lengte_half=40.0, stelen=30000.0)
        t = tv.teelt(k, m2)
        self.assertEqual((t["fase1"], t["fase2"], t["teeltduur"]), (29, 21, 50))
        self.assertAlmostEqual(t["lichtsom"], 800.0)
        self.assertAlmostEqual(t["afwijking"], 19.0 - t_ideaal(800.0))
        self.assertAlmostEqual(t["stelen_m2"], 60.0)
        self.assertAlmostEqual(t["lengtefactor"], 2.0)

    def test_lopend_met_prognose_en_florgib_uit_historie(self):
        k, m2 = regel(2, 3, 6, "2026-09-01")
        t = tv.teelt(k, m2, prognose=date(2026, 11, 5), florgib_historie="2026-10-01")
        self.assertTrue(t["prognose"])
        self.assertEqual(t["florgib"], date(2026, 10, 1))
        self.assertEqual(t["teeltduur"], 65)

    def test_warmte_alleen_bij_volledige_meting(self):
        k, m2 = regel(3, 1, 1, "2026-08-03", oogst="2026-09-22", energiedagen=30)
        self.assertIsNone(tv.teelt(k, m2)["warmte"])

    def test_stelen_uit_uitval_als_er_geen_emmers_zijn(self):
        k, m2 = regel(4, 1, 1, "2026-08-03", oogst="2026-09-22", aantal_planten=50000, uitval_pct=10.0, m2=883.2)
        self.assertAlmostEqual(tv.teelt(k, m2)["stelen_m2"], 45000 / 883.2)
        k, m2 = regel(5, 1, 1, "2026-08-03", oogst="2026-09-22", aantal_planten=50000)
        self.assertIsNone(tv.teelt(k, m2)["stelen_m2"])            # uitval onbekend: niet gokken


class TestSamenvatting(unittest.TestCase):
    def teelten(self):
        return [
            tv.teelt(*regel(1, 1, 1, "2026-08-03", oogst="2026-09-22", m2=900.0, lengte_eind=80.0,
                            beoordeling=8, wortel="Goed")),
            tv.teelt(*regel(2, 3, 5, "2026-08-04", oogst="2026-09-20", m2=500.0, lengte_eind=70.0,
                            beoordeling=6, wortel="Matig")),
            tv.teelt(*regel(3, 3, 6, "2026-08-05", m2=500.0, lengte_eind=None), prognose=date(2026, 9, 30)),
        ]

    def test_gewogen_naar_m2_en_totaal(self):
        w, n, bron, mark = tv.tabelwaarden(self.teelten(), [("Tuin 1", 1), ("Tuin 3", 3)])
        self.assertAlmostEqual(w["Totaal"]["lengte"], (80 * 900 + 70 * 500) / 1400)
        self.assertEqual(w["Tuin 3"]["aantal"], 2)
        self.assertEqual(n["Tuin 3"]["aantal"], 1)                  # afgerond
        self.assertEqual(w["Totaal"]["stek_matig"], 1)
        self.assertEqual(w["Totaal"]["plantdatum"], "03-08 – 05-08-26")
        self.assertIn("teeltduur", mark["Tuin 3"])                  # lopende teelt met prognose
        self.assertNotIn("teeltduur", mark["Tuin 1"])
        self.assertEqual(bron["lengte"], frozenset({"Tuin 1", "Tuin 3"}))

    def test_lopende_teelt_telt_niet_mee_voor_klimaat(self):
        w, n, _, _ = tv.tabelwaarden(self.teelten(), [("Tuin 1", 1), ("Tuin 3", 3)])
        self.assertEqual(n["Tuin 3"]["temp"], 1)
        self.assertEqual(n["Tuin 3"]["teeltduur"], 2)

    def test_afwijking_van_gemiddelde(self):
        afw = tv.afwijking_van_gemiddelde(self.teelten(), "lengte")
        gem = (80 * 900 + 70 * 500) / 1400
        self.assertAlmostEqual(afw[2], (70 - gem) / gem)
        self.assertNotIn(3, afw)


class TestPlantweken(unittest.TestCase):
    def test_standaard_en_vorig_jaar(self):
        teelten = [tv.teelt(*regel(1, 3, 1, "2026-08-03", oogst="2026-09-22")),
                   tv.teelt(*regel(2, 3, 2, "2026-09-14"))]
        weken = tv.plantweken(teelten)
        self.assertEqual(weken[(2026, 32)], (1, 1))
        self.assertEqual(tv.standaard_plantweek(weken), (2026, 32))
        self.assertEqual(tv.vorig_jaar((2026, 53)), (2025, 52))
        self.assertEqual(tv.vorige_weken((2026, 2), 3), [(2025, 52), (2026, 1), (2026, 2)])


if __name__ == "__main__":
    unittest.main()

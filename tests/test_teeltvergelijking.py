"""Tests voor logic/teeltvergelijking.py: vakken, dagdata-vensters, m²-weging, teeltdag en vergelijking."""
import unittest
from datetime import date, timedelta

import pandas as pd

from logic import teeltvergelijking as tv
from logic.lichtlijn import t_ideaal

GISTEREN = date(2026, 9, 27)


def regel(id_, tuin, vak, start, oogst=None, half=None, **extra):
    k = {"id": id_, "tuin_id": tuin, "vaknummer": vak, "afdeling": 1, "code": f"C{id_}",
         "datum_teelt_start": start, "datum_oogst": oogst, "datum_half": half,
         "aantal_planten": None, "uitval_pct": None, "stelen": None,
         "lengte_eind": None, "lengte_half": None, "oogstgewicht": None,
         "beoordeling": None, "wortel": None, "plantmaat": None, "uniformiteit": None}
    k.update(extra)
    return k


def dagdata(van=date(2025, 7, 1), tot=GISTEREN, temp=19.0, licht=800.0, water=2.0, warmte=1.0):
    dagen = [van + timedelta(days=i) for i in range((tot - van).days + 1)]
    klimaat = pd.DataFrame([{"tuin_id": t, "afdeling": 1, "datum": str(d), "temp_24h": temp, "lichtsom": licht}
                            for t in (1, 3) for d in dagen])
    water_df = pd.DataFrame([{"tuin_id": t, "vaknummer": v, "datum": str(d), "liter_per_m2": water}
                             for t in (1, 3) for v in range(1, 8) for d in dagen])
    return tv.Dagdata(klimaat, water_df, {t: {str(d): warmte for d in dagen} for t in (1, 3)})


def vak(k, m2=500.0, dd=None, teeltdag=None, **kw):
    return tv.met_dagdata(tv.teelt(k, m2, **kw), dd or dagdata(), GISTEREN, teeltdag)


class TestVak(unittest.TestCase):
    def test_fasen_en_klimaat_uit_dagdata(self):
        t = vak(regel(1, 3, 5, "2026-08-03", oogst="2026-09-22", half="2026-09-01", lengte_eind=80.0,
                      lengte_half=40.0, stelen=30000.0))
        self.assertEqual((t["fase1"], t["fase2"], t["teeltduur"]), (29, 21, 50))
        self.assertAlmostEqual(t["lichtsom"], 800.0)
        self.assertAlmostEqual(t["afwijking"], 19.0 - t_ideaal(800.0))
        self.assertAlmostEqual(t["water"], 2.0 * 51)                 # 03-08 t/m 22-09 = 51 dagen
        self.assertAlmostEqual(t["warmte"], 51.0)
        self.assertAlmostEqual(t["stelen_m2"], 60.0)
        self.assertFalse(t["gedeeltelijk"])

    def test_lopend_vak_tot_gisteren_met_prognose_en_florgib_uit_historie(self):
        t = vak(regel(2, 3, 6, "2026-09-01"), prognose=date(2026, 11, 5), florgib_historie="2026-09-20")
        self.assertTrue(t["prognose"] and t["gedeeltelijk"])
        self.assertEqual(t["florgib"], date(2026, 9, 20))
        self.assertEqual(t["teeltduur"], 65)
        self.assertAlmostEqual(t["water"], 2.0 * 27)                 # 01-09 t/m 27-09

    def test_uitval_alleen_bij_afgeronde_vakken(self):
        # Vak 11 wordt nog geoogst: 90 van de 100 emmers staan er nog niet in, dat is geen 99 % uitval.
        lopend = vak(regel(8, 3, 11, "2026-08-10", aantal_planten=10000, uitval_pct=99.4))
        self.assertIsNone(lopend["uitval"])
        afgerond = vak(regel(9, 3, 11, "2026-08-10", oogst="2026-09-28", aantal_planten=10000, uitval_pct=4.0))
        self.assertAlmostEqual(afgerond["uitval"], 4.0)

    def test_teeltdag_kapt_venster_af(self):
        t = vak(regel(3, 3, 5, "2025-08-04", oogst="2025-09-23"), teeltdag=20)
        self.assertEqual(t["venster_eind"], date(2025, 8, 24))
        self.assertAlmostEqual(t["water"], 2.0 * 21)
        self.assertTrue(t["gedeeltelijk"])

    def test_warmte_alleen_bij_volledige_meting(self):
        dd = dagdata(van=date(2026, 9, 1))                            # warmte pas vanaf 1 september
        self.assertIsNone(vak(regel(4, 1, 1, "2026-08-03", oogst="2026-09-22"), dd=dd)["warmte"])

    def test_stelen_uit_uitval_als_er_geen_emmers_zijn(self):
        t = vak(regel(5, 1, 1, "2026-08-03", oogst="2026-09-22", aantal_planten=50000, uitval_pct=10.0), m2=883.2)
        self.assertAlmostEqual(t["stelen_m2"], 45000 / 883.2)
        self.assertIsNone(vak(regel(6, 1, 1, "2026-08-03", oogst="2026-09-22", aantal_planten=50000))["stelen_m2"])


class TestSamenvatting(unittest.TestCase):
    def vakken(self):
        return [
            vak(regel(1, 1, 1, "2026-08-03", oogst="2026-09-22", lengte_eind=80.0, beoordeling=8, wortel="Goed"),
                m2=900.0),
            vak(regel(2, 3, 5, "2026-08-04", oogst="2026-09-20", lengte_eind=70.0, beoordeling=6, wortel="Matig")),
            vak(regel(3, 3, 6, "2026-08-05"), prognose=date(2026, 9, 30)),
        ]

    def test_gewogen_naar_m2_en_totaal(self):
        u = tv.tabelwaarden(self.vakken(), [("Tuin 1", 1), ("Tuin 3", 3)])
        w, n = u["waarden"], u["n"]
        self.assertAlmostEqual(w["Totaal"]["lengte"], (80 * 900 + 70 * 500) / 1400)
        self.assertEqual((w["Tuin 3"]["aantal"], n["Tuin 3"]["aantal"]), (2, 1))   # 2 vakken, 1 afgerond
        self.assertEqual(w["Totaal"]["stek_matig"], 1)
        self.assertEqual(w["Totaal"]["plantdatum"], "3–5 aug")
        self.assertEqual(u["bron"]["lengte"], frozenset({"Tuin 1", "Tuin 3"}))

    def test_lopend_vak_telt_mee_voor_klimaat_niet_voor_resultaat(self):
        u = tv.tabelwaarden(self.vakken(), [("Tuin 1", 1), ("Tuin 3", 3)])
        self.assertEqual((u["n"]["Tuin 3"]["temp"], u["verwacht"]["Tuin 3"]["temp"]), (2, 2))
        self.assertEqual(u["n"]["Tuin 3"]["lengte"], 1)
        self.assertEqual(u["verwacht"]["Tuin 3"]["lengte"], 1)            # alleen afgeronde vakken verwacht
        self.assertIn("temp", u["markering"]["Tuin 3"])                    # ⏳: lopend vak telt mee
        self.assertIn("teeltduur", u["markering"]["Tuin 3"])
        self.assertNotIn("temp", u["markering"]["Tuin 1"])

    def test_onvolledige_data_en_uitleg(self):
        u = tv.tabelwaarden([vak(regel(7, 1, 2, "2026-09-14"))], [("Tuin 1", 1), ("Tuin 3", 3)])
        self.assertEqual(u["ontbreekt"]["Tuin 1"]["lengte"], "Nog geen afgeronde vakken")
        self.assertEqual(u["ontbreekt"]["Tuin 3"]["temp"], "Geen vakken in deze teelt")

    def test_teeltdag(self):
        vakken = self.vakken()
        self.assertEqual(tv.teeltdag(vakken, GISTEREN), (GISTEREN - date(2026, 8, 3)).days)
        self.assertIsNone(tv.teeltdag(vakken[:2], GISTEREN))                # alles afgerond

    def test_afwijking_van_gemiddelde(self):
        afw = tv.afwijking_van_gemiddelde(self.vakken(), "lengte")
        gem = (80 * 900 + 70 * 500) / 1400
        self.assertAlmostEqual(afw[2], (70 - gem) / gem)
        self.assertNotIn(3, afw)


class TestPlantweken(unittest.TestCase):
    def test_standaard_en_vorig_jaar(self):
        vakken = [vak(regel(1, 3, 1, "2026-08-03", oogst="2026-09-22")), vak(regel(2, 3, 2, "2026-09-14"))]
        weken = tv.plantweken(vakken)
        self.assertEqual(weken[(2026, 32)], (1, 1))
        self.assertEqual(tv.standaard_plantweek(weken), (2026, 32))
        self.assertEqual(tv.vorig_jaar((2026, 53)), (2025, 52))
        self.assertEqual(tv.vorige_weken((2026, 2), 3), [(2025, 52), (2026, 1), (2026, 2)])

    def test_kort_bereik(self):
        self.assertEqual(tv.kort_bereik([date(2026, 8, 10)]), "10 aug")
        self.assertEqual(tv.kort_bereik([date(2026, 8, 28), date(2026, 9, 2)]), "28 aug – 2 sep")
        self.assertIsNone(tv.kort_bereik([None]))


if __name__ == "__main__":
    unittest.main()

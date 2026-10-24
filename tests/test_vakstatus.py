"""
Tests voor logic/vakstatus.py (verwachte lengte, ladder, kleur).

    python -m unittest discover -s tests -v
"""
import unittest
from datetime import date, timedelta

from logic import vakstatus as vs


def teelt(id_, tuin, start, half=None, lengte_half=None, oogst=None, lengte_eind=None, vak=1, **extra):
    """Teelt-dict zoals de app die doorgeeft; datums als date."""
    return {"id": id_, "tuin_id": tuin, "vaknummer": vak, "datum_teelt_start": start,
            "datum_half": half, "lengte_half": lengte_half, "datum_oogst": oogst,
            "lengte_eind": lengte_eind, **extra}


def referentie(id_, tuin, start, lengte_half=35.0, lengte_eind=70.0, half_na=30, duur=50):
    return teelt(id_, tuin, start, start + timedelta(days=half_na), lengte_half,
                 start + timedelta(days=duur), lengte_eind)


def plan_50_dagen(start):
    return 50 / 7, start + timedelta(days=50)


class TestInterpolatie(unittest.TestCase):
    def test_lineair_tussen_de_drie_punten(self):
        punten = [(0, 0.0), (30, 36.0), (50, 76.0)]
        self.assertEqual(vs.interpoleer(punten, 0), 0.0)
        self.assertAlmostEqual(vs.interpoleer(punten, 15), 18.0)
        self.assertAlmostEqual(vs.interpoleer(punten, 40), 56.0)
        self.assertEqual(vs.interpoleer(punten, 80), 76.0)  # na de oogst: eindlengte

    def test_kwantiel_zoals_numpy(self):
        self.assertEqual(vs.kwantiel([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(vs.kwantiel([10, 20, 30], 0.25), 15)

    def test_weekafstand_over_de_jaargrens(self):
        self.assertEqual(vs.weekafstand(52, 1), 1)
        self.assertEqual(vs.weekafstand(10, 14), 4)


class TestReferentieladder(unittest.TestCase):
    start = date(2026, 8, 3)  # ISO-week 32

    def test_eigen_tuin_als_er_genoeg_zijn(self):
        refs = [referentie(i, 3, self.start - timedelta(days=7 * (i % 3))) for i in range(1, 5)]
        gekozen, niveau = vs.kies_referenties(teelt(99, 3, self.start), refs)
        self.assertEqual(niveau, "eigen")
        self.assertEqual(len(gekozen), 4)

    def test_valt_terug_op_beide_tuinen(self):
        refs = [referentie(1, 3, self.start), referentie(2, 1, self.start), referentie(3, 1, self.start)]
        _, niveau = vs.kies_referenties(teelt(99, 3, self.start), refs)
        self.assertEqual(niveau, "beide")

    def test_valt_terug_op_breed_venster(self):
        refs = [referentie(i, 3, self.start - timedelta(weeks=4)) for i in range(1, 4)]
        _, niveau = vs.kies_referenties(teelt(99, 3, self.start), refs)
        self.assertEqual(niveau, "breed")

    def test_te_weinig_referenties_is_geen_referentie(self):
        refs = [referentie(1, 3, self.start), referentie(2, 3, self.start)]
        self.assertEqual(vs.kies_referenties(teelt(99, 3, self.start), refs), ([], None))

    def test_teelt_zelf_en_onvolledige_teelten_tellen_niet_mee(self):
        refs = [referentie(i, 3, self.start) for i in (1, 2)]
        refs.append(referentie(99, 3, self.start))                  # de teelt zelf
        refs.append(teelt(5, 3, self.start, oogst=self.start + timedelta(days=50), lengte_eind=70))  # geen meting
        self.assertEqual(vs.kies_referenties(teelt(99, 3, self.start), refs), ([], None))


class TestKleur(unittest.TestCase):
    def test_drempels(self):
        self.assertEqual(vs.bepaal_kleur(None, None), "grijs")
        self.assertEqual(vs.bepaal_kleur(-3, 1), "groen")
        self.assertEqual(vs.bepaal_kleur(-7, 2), "oranje")
        self.assertEqual(vs.bepaal_kleur(12, -4), "oranje")   # ruim vóór is oranje, niet rood
        self.assertEqual(vs.bepaal_kleur(-12, 4), "rood")
        self.assertEqual(vs.bepaal_kleur(-2, vs.OOGST_ROOD_DAGEN + 1), "rood")


class TestBeoordeling(unittest.TestCase):
    start = date(2026, 8, 3)
    vandaag = date(2026, 9, 10)  # 38 dagen oud

    def refs(self):
        # Allemaal 36 cm op dag 30 en 76 cm op dag 50: verwacht op dag 30 = 36 cm.
        return [referentie(i, 3, self.start - timedelta(weeks=1), lengte_half=36, lengte_eind=76)
                for i in range(1, 6)]

    def test_op_schema(self):
        t = teelt(99, 3, self.start, self.start + timedelta(days=30), 35.5)
        s = vs.beoordeel_teelt(t, self.refs(), self.vandaag, plan_50_dagen)
        self.assertEqual(s["leeftijd"], 38)
        self.assertAlmostEqual(s["verwacht"], 36)
        self.assertEqual(s["kleur"], "groen")
        self.assertEqual(s["plan"], self.start + timedelta(days=50))

    def test_achterstand_geeft_rood_en_latere_prognose(self):
        # 30 cm op dag 30; de mediaan haalt 30 cm op dag 25 → 5 dagen achter.
        t = teelt(99, 3, self.start, self.start + timedelta(days=30), 30)
        s = vs.beoordeel_teelt(t, self.refs(), self.vandaag, plan_50_dagen)
        self.assertAlmostEqual(s["afwijking_pct"], (30 / 36 - 1) * 100)
        self.assertEqual(s["kleur"], "rood")
        self.assertEqual(s["prognose_dagen"], 5)
        self.assertEqual(s["prognose"], s["plan"] + timedelta(days=5))

    def test_florgib_voor_het_planten_telt_niet_mee(self):
        t = teelt(99, 3, self.start, self.start - timedelta(days=6), 30)
        s = vs.beoordeel_teelt(t, self.refs(), self.vandaag, plan_50_dagen)
        self.assertIsNone(s["meting"])
        self.assertIsNone(s["prognose"])
        self.assertEqual(s["kleur"], "grijs")
        self.assertEqual(s["florgib_fout"], self.start - timedelta(days=6))

    def test_zonder_meting_grijs(self):
        s = vs.beoordeel_teelt(teelt(99, 3, self.start), self.refs(), self.vandaag, plan_50_dagen)
        self.assertEqual(s["kleur"], "grijs")
        self.assertIsNone(s["afwijking_pct"])


class TestDatums(unittest.TestCase):
    def test_alle_vormen_van_een_datum(self):
        from datetime import datetime

        import pandas as pd
        d = date(2026, 9, 26)
        for waarde in ("2026-09-26", "2026-09-26 00:00:00", "2026-09-26T10:15:00", d,
                       datetime(2026, 9, 26, 10, 15), pd.Timestamp("2026-09-26")):
            self.assertEqual(vs.als_datum(waarde), d, waarde)
        self.assertIsNone(vs.als_datum(None))
        self.assertIsNone(vs.als_datum(float("nan")))

    def test_niet_iso_valt_terug_op_strptime(self):
        self.assertEqual(vs.als_datum("2026-9-6"), date(2026, 9, 6))


class TestReferentiebasis(unittest.TestCase):
    """De vooraf uitgerekende basis moet precies hetzelfde geven als zonder."""
    start = date(2026, 8, 3)

    def kandidaten(self):
        refs = [referentie(i, 3 if i % 2 else 1, self.start - timedelta(weeks=i % 5), lengte_half=30 + i,
                           lengte_eind=70 + i) for i in range(1, 15)]
        refs.append(teelt(50, 3, self.start))                                        # lopend, geen referentie
        refs.append(teelt(51, 3, self.start, oogst=self.start + timedelta(days=50)))  # geen meting
        return refs

    def test_alleen_referenties_met_plantweek(self):
        basis = vs.referentiebasis(self.kandidaten())
        self.assertEqual(len(basis), 14)
        self.assertTrue(all(w == vs.plantweek(k["datum_teelt_start"]) for k, w in basis))

    def test_kies_referenties_gelijk_met_en_zonder_basis(self):
        kandidaten = self.kandidaten()
        basis = vs.referentiebasis(kandidaten)
        for t in (teelt(99, 3, self.start), teelt(99, 1, self.start), kandidaten[0]):  # ook een teelt uit de lijst
            self.assertEqual(vs.kies_referenties(t, kandidaten, basis), vs.kies_referenties(t, kandidaten))

    def test_beoordeling_gelijk_met_en_zonder_basis(self):
        kandidaten = self.kandidaten()
        t = teelt(99, 3, self.start, self.start + timedelta(days=30), 31)
        vandaag = self.start + timedelta(days=38)
        self.assertEqual(vs.beoordeel_teelt(t, kandidaten, vandaag, plan_50_dagen, vs.referentiebasis(kandidaten)),
                         vs.beoordeel_teelt(t, kandidaten, vandaag, plan_50_dagen))

    def test_groeicurve_gelijk_aan_verwachte_lengte_per_dag(self):
        refs = vs.kies_referenties(teelt(99, 3, self.start), self.kandidaten())[0]
        curve = vs.groeicurve(refs)
        self.assertEqual(len(curve), 51)
        for leeftijd, p25, mediaan, p75 in curve:
            self.assertEqual((mediaan, p25, p75), vs.verwachte_lengte(refs, leeftijd))


if __name__ == "__main__":
    unittest.main()

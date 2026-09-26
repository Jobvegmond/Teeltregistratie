"""
Tests voor logic/vakstatus.py (verwachte lengte, ladder, kleur, aandachtspunten).

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

    def test_zonder_meting_grijs(self):
        s = vs.beoordeel_teelt(teelt(99, 3, self.start), self.refs(), self.vandaag, plan_50_dagen)
        self.assertEqual(s["kleur"], "grijs")
        self.assertIsNone(s["afwijking_pct"])


class TestAandachtspunten(unittest.TestCase):
    vandaag = date(2026, 9, 24)  # donderdag, week 39

    def ideaal(self, licht):
        return 0.0072 * licht + 11.7

    def status(self, vak, kleur="groen", afwijking=None, prognose_dagen=None, leeftijd=40,
               plan=None, emmers=None, **teelt_extra):
        start = self.vandaag - timedelta(days=leeftijd)
        plan = plan or self.vandaag + timedelta(days=20)
        return {"teelt": teelt(vak, 3, start, vak=vak, emmers=emmers, **teelt_extra), "start": start,
                "leeftijd": leeftijd, "plantweek": start.isocalendar()[1], "plan": plan,
                "prognose": plan + timedelta(days=prognose_dagen) if prognose_dagen else None,
                "prognose_dagen": prognose_dagen, "afwijking_pct": afwijking, "kleur": kleur}

    def test_volgorde_en_teksten(self):
        statussen = [
            self.status(12, "oranje", 7),
            self.status(17, "rood", -12),
            self.status(9, plan=self.vandaag),                          # oogst deze week, geen emmers
            self.status(3, leeftijd=5, wortel="Matig"),
            self.status(4, leeftijd=5, wortel="Matig"),
        ]
        klimaat = {3: [(self.vandaag - timedelta(days=i), self.ideaal(800) + 1.5, 800) for i in range(7)]}
        water = {v: self.vandaag for v in (3, 4, 9, 12)}                # vak 17: nooit water gehad
        punten = vs.aandachtspunten(statussen, klimaat, water, self.vandaag, self.vandaag, self.ideaal)
        teksten = [p["tekst"] for p in punten]
        self.assertTrue(teksten[0].startswith("Vak 17: lengte −12 %"))
        self.assertTrue(teksten[1].startswith("Afd. 3: 7 van de laatste 7 dagen > 1 °C boven ideaal"))
        self.assertIn("Vak 17: 40 dagen geen watergift geregistreerd", teksten)
        self.assertIn("Vak 9: oogst verwacht deze week, nog geen oogst geregistreerd", teksten)
        self.assertIn("Stek wk 38: vak 3 en 4 wortel 'Matig'", teksten)
        self.assertTrue(teksten[-1].startswith("Vak 12: lengte +7 %"))

    def test_geen_dubbele_rode_regel_voor_lengte_en_prognose(self):
        punten = vs.aandachtspunten([self.status(17, "rood", -12, prognose_dagen=8)], {}, {17: self.vandaag},
                                    self.vandaag, self.vandaag, self.ideaal)
        self.assertEqual(len([p for p in punten if p["sleutel"] == 17]), 1)

    def test_water_telt_tot_de_laatste_dag_met_data(self):
        # Priva loopt 3 dagen achter: dan geen melding voor een vak dat 5 dagen voor die dag water kreeg.
        horizon = self.vandaag - timedelta(days=3)
        self.assertEqual(vs.dagen_zonder_water(date(2026, 8, 1), horizon - timedelta(days=5), horizon), 5)

    def test_maximaal_acht(self):
        statussen = [self.status(v, "oranje", 8) for v in range(1, 15)]
        water = {v: self.vandaag for v in range(1, 15)}
        self.assertEqual(len(vs.aandachtspunten(statussen, {}, water, self.vandaag, self.vandaag, self.ideaal)),
                         vs.MAX_AANDACHTSPUNTEN)


if __name__ == "__main__":
    unittest.main()

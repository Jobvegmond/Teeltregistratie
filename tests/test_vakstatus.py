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

    def test_florgib_voor_het_planten_telt_niet_mee(self):
        t = teelt(99, 3, self.start, self.start - timedelta(days=6), 30)
        s = vs.beoordeel_teelt(t, self.refs(), self.vandaag, plan_50_dagen)
        self.assertIsNone(s["meting"])
        self.assertIsNone(s["prognose"])
        self.assertEqual(s["kleur"], "grijs")
        self.assertEqual(s["florgib_fout"], self.start - timedelta(days=6))
        punten = vs.aandachtspunten([s], {}, None, self.vandaag)
        self.assertTrue(any("ligt vóór het planten" in p["tekst"] for p in punten))

    def test_zonder_meting_grijs(self):
        s = vs.beoordeel_teelt(teelt(99, 3, self.start), self.refs(), self.vandaag, plan_50_dagen)
        self.assertEqual(s["kleur"], "grijs")
        self.assertIsNone(s["afwijking_pct"])


class TestAandachtspunten(unittest.TestCase):
    vandaag = date(2026, 9, 24)  # donderdag, week 39

    def stook(self, c=0.0, begrensd=False, prognose_bij_c=None, oogstrijp=False, florgib_verwacht=None):
        return {"c": c, "begrensd": begrensd, "prognose_bij_c": prognose_bij_c, "oogstrijp": oogstrijp,
                "florgib_verwacht": florgib_verwacht}

    def status(self, vak, leeftijd=40, plan=None, emmers=None, florgib=None, stook=None, afdeling=3,
               **teelt_extra):
        start = self.vandaag - timedelta(days=leeftijd)
        plan = plan or self.vandaag + timedelta(days=20)
        t = teelt(vak, 3, start, vak=vak, emmers=emmers, **teelt_extra)
        t["afdeling"] = afdeling
        return {"teelt": t, "start": start, "leeftijd": leeftijd, "plantweek": start.isocalendar()[1],
                "plan": plan, "florgib": florgib, "florgib_fout": None, "stook": stook}

    def test_volgorde_en_teksten(self):
        plan = self.vandaag + timedelta(days=20)
        fg = self.vandaag - timedelta(days=5)
        statussen = [
            self.status(12, stook=self.stook(0.5), florgib=fg),
            self.status(13, stook=self.stook(0.5), florgib=fg),                 # zelfde uitkomst → één regel
            self.status(17, stook=self.stook(3.0, True, plan + timedelta(days=4)), florgib=fg),
            self.status(18, stook=self.stook(0.1), florgib=fg),                 # op koers: geen melding
            self.status(9, plan=self.vandaag - timedelta(days=2), stook=self.stook(None, oogstrijp=True),
                        florgib=fg),
            self.status(20, leeftijd=30, stook=self.stook(florgib_verwacht=self.vandaag - timedelta(days=6))),
            self.status(3, leeftijd=5, wortel="Matig"),
            self.status(4, leeftijd=5, wortel="Matig"),
        ]
        water = {v: self.vandaag for v in (3, 4, 20)}
        punten = vs.aandachtspunten(statussen, water, self.vandaag, self.vandaag)
        self.assertEqual([p["tekst"] for p in punten], [
            f"Vak 17: haalt plan {plan:%d-%m} niet, ook niet bij +3,0 °C (prog. {plan + timedelta(days=4):%d-%m})",
            f"Vak 12 en 13: +0,5 °C t.o.v. de lichtlijn voor plan {plan:%d-%m}",
            f"Vak 20: Florgib verwacht {self.vandaag - timedelta(days=6):%d-%m}, nog niet geregistreerd",
            f"Vak 9: volgens het model oogstrijp (plan {self.vandaag - timedelta(days=2):%d-%m}), "
            "nog geen oogst geregistreerd",
            "Stek wk 38: vak 3 en 4 wortel 'Matig'",
        ])

    def test_te_vroeg_en_negatieve_correctie(self):
        plan = self.vandaag + timedelta(days=10)
        statussen = [self.status(5, plan=plan, stook=self.stook(-2.0, True, plan - timedelta(days=3)), florgib=plan),
                     self.status(6, plan=plan, stook=self.stook(-0.4), florgib=plan, afdeling=4)]
        statussen.append(self.status(7, plan=plan, stook=self.stook(-2.0, True, plan - timedelta(days=2)),
                                     florgib=plan, afdeling=2))            # 2 dagen: binnen de marge
        teksten = [p["tekst"] for p in vs.aandachtspunten(statussen, {}, self.vandaag, self.vandaag)]
        self.assertEqual(teksten, [
            f"Vak 5: te vroeg, ook bij −2,0 °C (prog. {plan - timedelta(days=3):%d-%m}, plan {plan:%d-%m})",
            f"Vak 6: −0,4 °C t.o.v. de lichtlijn voor plan {plan:%d-%m}",
        ])

    def test_water_telt_tot_de_laatste_dag_met_data(self):
        # Priva loopt 3 dagen achter: dan geen melding voor een vak dat 5 dagen voor die dag water kreeg.
        horizon = self.vandaag - timedelta(days=3)
        self.assertEqual(vs.dagen_zonder_water(date(2026, 8, 1), horizon - timedelta(days=5), horizon), 5)

    def test_watergift_samengevoegd_per_datum_en_alleen_voor_de_florgib(self):
        sinds = self.vandaag - timedelta(days=10)
        statussen = [self.status(v, leeftijd=25) for v in (10, 11, 12, 13, 14, 17)]
        statussen.append(self.status(20, leeftijd=25))                                   # heeft wel water
        statussen.append(self.status(30, leeftijd=35, florgib=self.vandaag - timedelta(days=8)))  # na Florgib
        water = {v: sinds for v in (10, 11, 12, 13, 14, 17)}
        water[20] = self.vandaag
        punten = vs.watergift_meldingen(statussen, water, self.vandaag, self.vandaag)
        self.assertEqual([p["tekst"] for p in punten], [f"Vak 10–14 en 17: geen watergift sinds {sinds:%d-%m}"])

    def test_watergift_onder_de_drempel_geen_melding(self):
        water = {5: self.vandaag - timedelta(days=vs.WATER_DROOG_DAGEN - 1), 6: self.vandaag}
        statussen = [self.status(5, leeftijd=20), self.status(6, leeftijd=20)]
        self.assertEqual(vs.watergift_meldingen(statussen, water, self.vandaag, self.vandaag), [])

    def test_watergift_import_loopt_achter(self):
        horizon = self.vandaag - timedelta(days=5)
        punten = vs.watergift_meldingen([self.status(5, leeftijd=20)], {5: horizon}, horizon, self.vandaag)
        self.assertEqual([p["tekst"] for p in punten], [f"Watergift-import loopt achter (laatste data {horizon:%d-%m})"])

    def test_watergift_alle_vakken_tegelijk_is_de_import(self):
        oud = self.vandaag - timedelta(days=6)
        statussen = [self.status(v, leeftijd=20) for v in (1, 2, 3)]
        punten = vs.watergift_meldingen(statussen, {1: oud, 2: oud, 3: oud}, self.vandaag, self.vandaag)
        self.assertTrue(punten[0]["tekst"].startswith("Watergift-import loopt achter"))

    def test_vakken_tekst(self):
        self.assertEqual(vs.vakken_tekst([12]), "Vak 12")
        self.assertEqual(vs.vakken_tekst([3, 5, 7]), "Vak 3, 5 en 7")
        self.assertEqual(vs.vakken_tekst([14, 10, 11, 12, 13]), "Vak 10–14")
        self.assertEqual(vs.vakken_tekst([1, 2, 9]), "Vak 1, 2 en 9")

    def test_maximaal_acht(self):
        statussen = [self.status(v, stook=self.stook(0.3 + v / 10), afdeling=v, florgib=self.vandaag)
                     for v in range(1, 15)]
        punten = vs.aandachtspunten(statussen, {}, self.vandaag, self.vandaag)
        self.assertEqual(len(punten), vs.MAX_AANDACHTSPUNTEN)
        self.assertEqual(punten[0]["sleutel"], 14)                       # grootste |c| eerst


if __name__ == "__main__":
    unittest.main()

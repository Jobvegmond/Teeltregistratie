"""Tests voor logic/watervoorspelling.py: kenmerken per vak-dag, straling ijken, model, advies, tekst en terugtoets."""
import random
import re
import unittest
from datetime import date, timedelta

from logic import watervoorspelling as wv

D = date(2026, 10, 1)


def dag(n):
    return D + timedelta(days=n)


def rij(leeftijd=10, sinds=4, S=2000.0, S_vandaag=500.0, vorige=15.0, gift=0.0, vak=5, datum=None):
    datum = datum or dag(leeftijd)
    return {"vak": vak, "teelt": 1, "datum": datum, "leeftijd": leeftijd, "sinds": sinds,
            "vorige_dag": datum - timedelta(days=sinds) if sinds is not None else None,
            "vorige": vorige if sinds is not None else None, "S": S, "S_vandaag": S_vandaag, "in_oogst": False,
            "gift": gift}


def nep_historie(n=4000, zaad=1):
    """Vak-dagen waarop de teler water geeft zodra de straling sinds de vorige gift boven de 2.500 komt."""
    rnd = random.Random(zaad)
    uit = []
    for i in range(n):
        leeftijd = rnd.randint(4, 40)
        S = rnd.uniform(0, 5000)
        drempel = 2500 if leeftijd <= 28 else 99999
        uit.append(rij(leeftijd=leeftijd, sinds=rnd.randint(1, 9), S=S, S_vandaag=0.0,
                       gift=15.0 if S + rnd.gauss(0, 300) > drempel else 0.0, datum=dag(i // 40), vak=i % 40 + 1))
    return uit


class TestKenmerken(unittest.TestCase):
    def test_fasen(self):
        self.assertEqual([wv.fase(x) for x in (0, 3, 4, 7, 8, 14, 15, 28, 29, 90)], [0, 0, 1, 1, 2, 2, 3, 3, 4, 4])

    def test_giften_alleen_vanaf_minimum(self):
        rijen = [{"vaknummer": 3, "datum": dag(0), "liter_per_m2": 15.0},
                 {"vaknummer": 3, "datum": dag(1), "liter_per_m2": 0.0},
                 {"vaknummer": 4, "datum": dag(1), "liter_per_m2": 0.4},
                 {"vaknummer": 4, "datum": dag(2), "liter_per_m2": None}]
        self.assertEqual(wv.giften(rijen), {(3, dag(0)): 15.0})

    def test_straling_en_dagen_sinds_de_gift(self):
        teelten = [{"id": 7, "vak": 3, "start": dag(0), "eind": None}]
        gift = {(3, dag(2)): 15.0}
        straling = {dag(i): 100.0 * (i + 1) for i in range(10)}
        uit = {r["datum"]: r for r in wv.kenmerken(teelten, gift, straling, dag(0), dag(5))}
        self.assertEqual(len(uit), 6)
        self.assertIsNone(uit[dag(1)]["sinds"])                       # nog geen gift sinds het planten
        self.assertEqual(uit[dag(1)]["S"], 100.0)                      # straling van de plantdag
        self.assertEqual(uit[dag(2)]["gift"], 15.0)
        r = uit[dag(5)]
        self.assertEqual((r["leeftijd"], r["sinds"], r["vorige"], r["vorige_dag"]), (5, 3, 15.0, dag(2)))
        self.assertEqual(r["S"], 400.0 + 500.0)                        # dag 3 en 4; de giftdag zelf telt niet
        self.assertEqual(r["S_vandaag"], 600.0)                        # zonder verwachting: de meting van de dag

    def test_verwachting_voor_vandaag_en_dagen_zonder_meting(self):
        teelten = [{"id": 7, "vak": 3, "start": dag(0), "eind": None}]
        straling = {dag(0): 300.0}                                     # dag 1 nog niet gemeten
        r = wv.kenmerken(teelten, {}, straling, dag(2), dag(2), {dag(1): 250.0, dag(2): 400.0})[0]
        self.assertEqual((r["S"], r["S_vandaag"]), (550.0, 400.0))
        self.assertEqual(wv.straling_tot_nu(r), 950.0)

    def test_teelt_stopt_bij_afronden_en_bij_de_volgende_start(self):
        teelten = [{"id": 1, "vak": 3, "start": dag(0), "eind": None}, {"id": 2, "vak": 3, "start": dag(5), "eind": None},
                   {"id": 3, "vak": 4, "start": dag(0), "eind": dag(2)}]
        gift = {(3, dag(1)): 10.0}
        uit = wv.kenmerken(teelten, gift, {}, dag(0), dag(6))
        vak3 = {r["datum"]: r for r in uit if r["vak"] == 3}
        self.assertEqual(vak3[dag(4)]["teelt"], 1)
        self.assertEqual(vak3[dag(5)]["teelt"], 2)
        self.assertIsNone(vak3[dag(6)]["sinds"])                       # de gift van de vorige teelt telt niet
        self.assertEqual(max(r["datum"] for r in uit if r["vak"] == 4), dag(2))

    def test_in_de_oogst(self):
        teelten = [{"id": 1, "vak": 3, "start": dag(0), "eind": None}]
        uit = {r["datum"]: r for r in wv.kenmerken(teelten, {}, {}, dag(0), dag(4), eerste_emmer={1: dag(2)})}
        self.assertEqual([uit[dag(i)]["in_oogst"] for i in range(5)], [False, False, False, True, True])


class TestStraling(unittest.TestCase):
    def test_ijken_op_de_laatste_weken(self):
        om = {dag(i): 2.0 + (i % 7) for i in range(60)}
        gemeten = {d: 150 + 55 * mj for d, mj in om.items()}
        for i in range(30):                                            # oude dagen met een andere verhouding
            gemeten[dag(i)] = 100 + 80 * om[dag(i)]
        a, b = wv.ijk_straling(gemeten, om, dag(60))
        self.assertAlmostEqual(a, 150, places=3)
        self.assertAlmostEqual(b, 55, places=3)
        self.assertAlmostEqual(wv.omrekenen(4.0, (a, b)), 150 + 220)

    def test_te_weinig_dagen_standaard(self):
        self.assertEqual(wv.ijk_straling({dag(0): 500.0}, {dag(0): 6.0}, dag(1)), wv.IJK_STANDAARD)
        self.assertIsNone(wv.omrekenen(None, wv.IJK_STANDAARD))

    def test_verwachting_reeks_kijkt_alleen_terug(self):
        om = {dag(i): 5.0 for i in range(40)}
        om.update({dag(i): 3.0 + i % 5 for i in range(40)})
        gemeten = {d: 100 + 50 * mj for d, mj in om.items()}
        reeks = wv.verwachting_reeks(gemeten, om)
        self.assertEqual(reeks[dag(0)], wv.omrekenen(om[dag(0)], wv.IJK_STANDAARD))   # nog niets om op te ijken
        self.assertAlmostEqual(reeks[dag(35)], 100 + 50 * om[dag(35)], places=3)


class TestModel(unittest.TestCase):
    def test_kans_stijgt_met_de_straling(self):
        model = wv.train(nep_historie())
        laag, hoog = wv.kans(model, rij(S=500)), wv.kans(model, rij(S=4500))
        self.assertLess(laag, 0.1)
        self.assertGreater(hoog, 0.9)
        self.assertLess(wv.kans(model, rij(leeftijd=35, S=4500)), 0.05)      # na week 4 bijna nooit

    def test_fase_zonder_genoeg_rijen_gemiddelde(self):
        rijen = [rij(leeftijd=2, gift=g) for g in (5.0, 0.0, 5.0, 5.0)] + nep_historie(500)
        model = wv.train(rijen)
        self.assertEqual(model[0], {"kans": 0.75, "liter": 5.0})
        self.assertEqual(wv.kans(model, rij(leeftijd=1)), 0.75)

    def test_advies(self):
        self.assertEqual([wv.advies(p) for p in (0.8, 0.5, 0.3, 0.15, 0.1)],
                         ["water", "water", "twijfel", "twijfel", "niet nodig"])
        self.assertEqual(wv.advies(0.02, opmerking=True), "twijfel")

    def test_morgen(self):
        m = wv.morgen(rij(leeftijd=9, sinds=3, S=1000, S_vandaag=400), 300.0)
        self.assertEqual((m["leeftijd"], m["sinds"], m["S"], m["S_vandaag"], m["datum"]), (10, 4, 1400, 300.0, dag(10)))


class TestTekst(unittest.TestCase):
    def test_reden(self):
        k = rij(leeftijd=9, sinds=3, S=2300, S_vandaag=500, vorige=15.0, vak=27, datum=date(2026, 11, 5))
        self.assertEqual(wv.reden(k, 0.64), "Vak 27 · 9 dagen na planten · 2.800 J/cm² straling sinds de gift van "
                                            "ma 02-11 (15 l/m²) · kans 64 %")
        tekst = wv.reden(rij(sinds=None, leeftijd=1), 0.3, [(dag(1), "droge kop")], morgen_kans=0.7)
        self.assertIn("1 dag na planten · nog geen gift sinds het planten, 2.500 J/cm² straling", tekst)
        self.assertTrue(tekst.endswith("morgen waarschijnlijk wel · opmerking 02-10: droge kop"))
        self.assertEqual(wv.reden(k, 0.1, vandaag_gegeven=12.5),
                         "Vak 27 · 9 dagen na planten · vandaag al 12,5 l/m² gegeven")

    def test_vakken_tekst(self):
        self.assertEqual(wv.vakken_tekst([27, 25, 26, 30, 17, 18]), "17, 18, 25–27, 30")


class TestAdviezen(unittest.TestCase):
    def setUp(self):
        self.model = wv.train(nep_historie())
        vandaag = date(2026, 11, 5)
        self.rijen = [rij(vak=25, S=4000, datum=vandaag), rij(vak=26, S=4000, datum=vandaag),
                      rij(vak=17, S=1900, datum=vandaag, vorige=10), rij(vak=30, S=300, datum=vandaag),
                      rij(vak=31, S=4000, datum=vandaag)]

    def test_adviezen_en_feed(self):
        lijst = wv.adviezen(self.model, self.rijen, 400.0, opmerkingen={}, vandaag_gegeven={31: 15.0})
        self.assertEqual({a["vak"]: a["advies"] for a in lijst},
                         {17: "twijfel", 25: "water", 26: "water", 30: "niet nodig", 31: "gegeven"})
        items = wv.feed_items(lijst, date(2026, 11, 5), "Tuin 3")
        # Eén los item per planting, eerst water, dan twijfel; geen item voor niet nodig of gegeven.
        self.assertEqual([(i["id"], re.sub(r" · \d+ %$", "", i["title"]), i["soort"], i["vakken"]) for i in items],
                         [("water-tuin3-2026-11-05-25-26", "Water · vak 25–26", "water", [25, 26]),
                          ("water-tuin3-2026-11-05-17-17", "Twijfel · vak 17", "twijfel", [17])])
        # De titel eindigt op de kans van de planting, zoals in de note.
        for i, a in zip(items, (lijst[1], lijst[0])):
            self.assertTrue(i["title"].endswith(f" · {a['kans'] * 100:.0f} %"), i["title"])
            self.assertIn(f"kans {a['kans'] * 100:.0f} %", i["note"])
        self.assertTrue(all((i["date"], i["area"]) == ("2026-11-05", "werk") for i in items))
        self.assertTrue(items[0]["note"].startswith("Tuin 3 · 10 dagen na planten · "))
        self.assertIn("meestal ± 15 l/m²", items[0]["note"])

    def test_water_opmerking_maakt_twijfel(self):
        rijen = [rij(vak=30, S=300, datum=date(2026, 11, 5))]
        lijst = wv.adviezen(self.model, rijen, opmerkingen={1: [(date(2026, 11, 3), "droge plek")]})
        self.assertEqual(lijst[0]["advies"], "twijfel")
        self.assertIn("opmerking 03-11: droge plek", lijst[0]["reden"])
        oud = wv.adviezen(self.model, rijen, opmerkingen={1: [(date(2026, 10, 1), "droge plek")]})
        self.assertEqual(oud[0]["advies"], "niet nodig")

    def test_niets_te_doen_geen_item(self):
        lijst = wv.adviezen(self.model, [rij(vak=30, S=300, datum=date(2026, 11, 5))])
        self.assertEqual(wv.feed_items(lijst, date(2026, 11, 5), "Tuin 3"), [])


class TestPlantingen(unittest.TestCase):
    def test_plantweek_en_aaneengesloten(self):
        vandaag = date(2026, 11, 5)                                     # do, week 45
        rijen = [rij(vak=v, leeftijd=l, datum=vandaag) for v, l in
                 ((17, 17), (18, 16), (19, 15), (20, 15), (21, 14), (22, 10), (23, 9), (24, 8),
                  (25, 3), (26, 2), (27, 1), (28, 0), (30, 2), (31, 30))]
        self.assertEqual(wv.plantingen(rijen), {17: "17–21", 18: "17–21", 19: "17–21", 20: "17–21", 21: "17–21",
                                                22: "22–24", 23: "22–24", 24: "22–24", 25: "25–28", 26: "25–28",
                                                27: "25–28", 28: "25–28", 30: "30", 31: "31"})

    def test_advies_per_planting_met_gemiddelde_kans(self):
        model = wv.train(nep_historie())
        vandaag = date(2026, 11, 5)
        rijen = [rij(vak=17, S=4500, datum=vandaag), rij(vak=18, S=2700, datum=vandaag),
                 rij(vak=19, S=300, datum=vandaag)]
        lijst = wv.adviezen(model, rijen)
        self.assertEqual({a["planting"] for a in lijst}, {"17–19"})
        self.assertEqual(len({a["advies"] for a in lijst}), 1)          # één advies voor de hele planting
        gemiddeld = sum(a["kans_vak"] for a in lijst) / 3
        self.assertTrue(all(abs(a["kans"] - gemiddeld) < 1e-9 for a in lijst))
        self.assertEqual(lijst[0]["advies"], wv.advies(gemiddeld))
        self.assertEqual(len(wv.groepen(lijst)), 1)
        self.assertIn("per vak", wv.groepen(lijst)[0])

    def test_planting_dagen(self):
        d = date(2026, 11, 5)
        rijen = [rij(vak=1, leeftijd=10, datum=d, gift=15.0), rij(vak=2, leeftijd=10, datum=d, gift=0.0),
                 rij(vak=3, leeftijd=10, datum=d, gift=0.0), rij(vak=9, leeftijd=3, datum=d, gift=5.0)]
        uit = sorted(wv.planting_dagen(rijen, [0.9, 0.6, 0.3, 0.8]))
        self.assertEqual(len(uit), 2)
        self.assertAlmostEqual(uit[0][0], 0.6)                          # vak 1–3: gemiddelde kans
        self.assertFalse(uit[0][1])                                     # 1 van 3 vakken water: minder dan de helft
        self.assertEqual(uit[1][1:], (True, 3))


class TestTerugtoets(unittest.TestCase):
    def test_terugtoets_beter_dan_blind(self):
        rijen = nep_historie(6000)
        splits = dag(100)
        uit = wv.terugtoets(rijen, splits)
        self.assertEqual(uit["per_vak"]["dagen"], sum(r["datum"] >= splits for r in rijen))
        self.assertEqual(uit["per_vak"]["giften"], sum(r["datum"] >= splits and r["gift"] > 0 for r in rijen))
        self.assertLessEqual(uit["dagen"], uit["per_vak"]["dagen"])
        self.assertEqual(sum(v["aantal"] for v in uit["advies"].values()), uit["dagen"])
        self.assertGreater(uit["water_raak"], 2 * uit["blind_raak"])
        self.assertGreater(uit["juist"], uit["blind_juist"])
        self.assertGreater(uit["gevonden_water_twijfel"], 0.9)
        self.assertEqual(set(uit["fasen"]), {f[2] for f in wv.FASEN})

    def test_extra_rijen_alleen_voor_het_leren(self):
        rijen = nep_historie(2000)
        extra = nep_historie(2000, zaad=2)
        uit = wv.terugtoets(rijen, dag(25), extra)
        self.assertEqual(uit["per_vak"]["dagen"], sum(r["datum"] >= dag(25) for r in rijen))



class TestFlorgibEnStreef(unittest.TestCase):
    def test_streef_tussen_winter_en_zomer(self):
        self.assertEqual(wv.streef(5000), 75.0)
        self.assertEqual(wv.streef(60000), 150.0)
        self.assertAlmostEqual(wv.streef(24000), 112.5)

    def test_verloop(self):
        self.assertEqual(wv.verloop(0), 0.0)
        self.assertAlmostEqual(wv.verloop(0.5), 0.64)
        self.assertAlmostEqual(wv.verloop(0.375), (0.38 + 0.64) / 2)
        self.assertEqual(wv.verloop(2.0), 1.0)

    def test_florgib_schatting_alleen_wat_bij_het_planten_bekend_was(self):
        teelten = [{"id": 1, "start": date(2025, 11, 1), "florgib": date(2025, 12, 31)},     # 60 dagen
                   {"id": 2, "start": date(2025, 11, 10), "florgib": date(2026, 1, 9)},      # 60 dagen
                   {"id": 3, "start": date(2026, 6, 1), "florgib": date(2026, 6, 27)},       # zomer, 26 dagen
                   {"id": 4, "start": date(2026, 11, 5), "florgib": None},
                   {"id": 5, "start": date(2025, 11, 5), "florgib": None}]                   # nog niets bekend
        uit = wv.florgib_schattingen(teelten)
        self.assertEqual(uit[4], 60)                                    # rond dezelfde plantdatum, vorig jaar
        self.assertEqual(uit[5], wv.FLORGIB_STANDAARD)

    def test_kenmerken_florgib_en_streef(self):
        teelten = [{"id": 1, "vak": 5, "start": dag(0), "florgib": dag(20), "eind": None}]
        gift = {(5, dag(0)): 10.0, (5, dag(3)): 15.0}
        straling = {dag(i): 400.0 for i in range(40)}
        klimaat = {n: 400.0 for n in range(1, 366)}
        rijen = {r["leeftijd"]: r for r in wv.kenmerken(teelten, gift, straling, dag(0), dag(30), klimaat=klimaat,
                                                        florgib_dagen={1: 30})}
        r = rijen[10]
        self.assertEqual(r["gegeven"], 25.0)
        self.assertFalse(r["na_florgib"])
        self.assertEqual(r["florgib_dag"], 30)                          # vóór de Florgib: de schatting
        self.assertEqual(r["lichtsom"], 30 * 400.0)                     # 10 dagen gemeten + 20 gemiddeld
        self.assertAlmostEqual(r["streef"], wv.streef(12000))
        self.assertAlmostEqual(wv.achterstand(r), r["streef"] * wv.verloop(10 / 30) - 25.0)
        self.assertTrue(rijen[20]["na_florgib"])                        # vanaf de dag van de Florgib
        self.assertEqual(rijen[20]["florgib_dag"], 20)
        self.assertEqual(rijen[25]["florgib"], dag(20))
        zonder = wv.kenmerken(teelten, gift, straling, dag(10), dag(10))
        self.assertIsNone(zonder[0]["streef"])                          # zonder klimaat geen streef

    def test_na_florgib_geen_advies(self):
        model = wv.train(nep_historie())
        r = dict(rij(vak=5, S=4500, datum=date(2026, 11, 5)), na_florgib=True, florgib=date(2026, 11, 2))
        lijst = wv.adviezen(model, [r, rij(vak=6, S=4500, datum=date(2026, 11, 5))])
        self.assertEqual({a["vak"]: a["advies"] for a in lijst}, {5: "na florgib", 6: "water"})
        self.assertIn("Florgib op ma 02-11: daarna niet meer gieten", lijst[0]["reden"])
        self.assertEqual([i["vakken"] for i in wv.feed_items(lijst, date(2026, 11, 5), "Tuin 3")], [[6]])
        self.assertIn("niet meer gieten", wv.groepen([lijst[0]])[0])

    def test_streef_regels(self):
        def met_streef(r, gegeven, streefwater=80.0, florgib_dag=40):
            return dict(r, gegeven=gegeven, streef=streefwater, florgib_dag=florgib_dag)
        model = wv.train(nep_historie())
        d = date(2026, 11, 5)
        # Streefwater al gegeven: water wordt twijfel.
        lijst = wv.adviezen(model, [met_streef(rij(vak=5, S=4500, datum=d), gegeven=85.0)])
        self.assertEqual(lijst[0]["advies"], "twijfel")
        self.assertEqual(lijst[0]["streef_regel"], "streefwater al gegeven")
        self.assertIn("streefwater al gegeven, daarom twijfel", wv.groepen(lijst)[0])
        # Ver achter op het schema: niet nodig wordt twijfel.
        r = met_streef(rij(vak=5, leeftijd=20, S=300, datum=d), gegeven=10.0)
        self.assertGreaterEqual(wv.achterstand(r), wv.STREEF_ACHTER)
        lijst = wv.adviezen(model, [r])
        self.assertEqual((lijst[0]["advies"], lijst[0]["streef_regel"]),
                         ("twijfel", "ver achter op het schema naar het streefwater"))
        # Op schema: het advies van het model blijft.
        r = met_streef(rij(vak=5, leeftijd=20, S=300, datum=d), gegeven=80.0 * wv.verloop(0.5))
        lijst = wv.adviezen(model, [r])
        self.assertEqual((lijst[0]["advies"], lijst[0]["streef_regel"]), ("niet nodig", None))
        self.assertIn("op schema", lijst[0]["reden"])

    def test_klimatologie(self):
        straling = {date(2025, 1, 1) + timedelta(days=i): float(i % 365) for i in range(730)}
        k = wv.klimatologie(straling, venster=0)
        self.assertAlmostEqual(k[10], 9.0)
        self.assertEqual(len(k), 365)


class TestPrivaVerwachting(unittest.TestCase):
    def test_ijk_priva(self):
        gemeten = {dag(i): 0.8 * (300 + 10 * i) for i in range(20)}
        priva = {dag(i): 300.0 + 10 * i for i in range(20)}
        self.assertAlmostEqual(wv.ijk_priva(gemeten, priva, dag(20)), 0.8)
        self.assertIsNone(wv.ijk_priva(gemeten, priva, dag(3)))         # te weinig dagen

    def test_priva_bestanden(self):
        from datetime import datetime
        from integrations import priva_meteo as pm
        catalogus = ['"id";"adres";"naam"',
                     '"7";"/meteo[VP9508:1]/toestand/verwachting[1]/verwachteStralingssomBuitenVandaag";"x"',
                     '"8";"/meteo[VP9508:1]/toestand/verwachting[1]/verwachteStralingssomBuitenMorgen";"y"']
        self.assertEqual(pm.ids(catalogus, "VP9508"), ("7", "8"))
        self.assertIsNone(pm.ids(catalogus, "Matricaria25"))
        regels = ['{"t":"2026-11-10T12:00:00+01:00","v":{"7":500,"8":300}}',
                  '{"t":"2026-11-10T20:00:00+01:00","v":{"8":350}}',
                  '{"t":"2026-11-11T09:00:00+01:00","v":{"7":340,"8":600}}',
                  'kapot']
        punten = pm.lees_punten(regels, ("7", "8"))
        self.assertEqual(len(punten["8"]), 3)
        # 07:10 in november is vóór zonsopkomst: "morgen" is de dag die begint, voor de dag erna nog niets.
        self.assertEqual(pm.verwachting_op(punten["7"], punten["8"], datetime(2026, 11, 11, 7, 10)), (350, None))
        self.assertEqual(pm.verwachting_op(punten["7"], punten["8"], datetime(2026, 11, 11, 10, 0)), (340, 600))
        reeks, erna = pm.per_dag(punten["7"], punten["8"], date(2026, 11, 11), date(2026, 11, 11))
        self.assertEqual((reeks, erna), ({date(2026, 11, 11): 350}, None))


if __name__ == "__main__":
    unittest.main()

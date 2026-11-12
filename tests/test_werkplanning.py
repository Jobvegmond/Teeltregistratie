"""Tests voor logic/werkplanning.py: CXDS-blokken, Florgib met CXDS, planten met Rizolex en inregenen."""
import unittest
from datetime import date

from logic import werkplanning as wp

MA = date(2026, 10, 26)          # maandag van week 44 (zo 25 t/m za 31 oktober)


def teelt(vak, start, florgib=None, verwacht=None, prognose=None, emmers=0):
    return {"vak": vak, "start": start, "florgib": florgib, "florgib_verwacht": verwacht, "prognose": prognose,
            "emmers": emmers}


def titels(lijst):
    return [(t["datum"], t["titel"]) for t in lijst]


class TestWerkplanning(unittest.TestCase):
    def test_blok_per_planting_na_anderhalve_week(self):
        teelten = [teelt(v, date(2026, 9, 7), florgib=date(2026, 10, 7), prognose=date(2026, 11, 9))
                   for v in range(30, 35)]
        cxds = {v: date(2026, 10, 20) for v in range(30, 35)}
        uit = wp.taken(teelten, cxds, [], MA)
        self.assertEqual(titels(uit), [(date(2026, 10, 30), "CXDS-blok vak 30–34")])
        self.assertIn("plantweek 37", uit[0]["toelichting"])

    def test_florgib_apart_met_cxds_en_niet_in_het_blok(self):
        teelten = [teelt(3, date(2026, 9, 21), verwacht=date(2026, 10, 26)),
                   teelt(4, date(2026, 9, 21), verwacht=date(2026, 11, 20))]
        cxds = {3: date(2026, 10, 14), 4: date(2026, 10, 14)}
        uit = wp.taken(teelten, cxds, [], MA)
        # Het blok (gemiddeld 24-10, dus vandaag en "loopt achter") zonder vak 3: dat krijgt zijn CXDS bij de Florgib.
        self.assertEqual(titels(uit), [(MA, "Florgib + CXDS vak 3"), (MA, "CXDS-blok vak 4")])
        self.assertIn("loopt achter", uit[1]["toelichting"])

    def test_eerste_cxds_op_de_tweede_vrijdag_na_planten(self):
        teelten = [teelt(v, date(2026, 10, 20)) for v in (13, 14)]                # di 20-10 → vr 23-10, vr 30-10
        uit = wp.taken(teelten, {13: date(2026, 9, 14)}, [], MA)      # CXDS van de vorige teelt telt niet
        self.assertEqual(titels(uit), [(date(2026, 10, 30), "CXDS-blok vak 13–14")])
        self.assertIn("eerste CXDS", uit[0]["toelichting"])

    def test_eerste_cxds_datum(self):
        self.assertEqual(wp.eerste_cxds(date(2026, 11, 10)), date(2026, 11, 20))  # dinsdag
        self.assertEqual(wp.eerste_cxds(date(2026, 11, 9)), date(2026, 11, 20))   # maandag
        self.assertEqual(wp.eerste_cxds(date(2026, 11, 13)), date(2026, 11, 27))  # vrijdag telt niet mee
        self.assertEqual(wp.eerste_cxds(date(2026, 11, 14)), date(2026, 11, 27))  # zaterdag

    def test_geen_cxds_in_de_oogst_en_reeksen_aaneengesloten(self):
        teelten = [teelt(24, date(2026, 8, 27), emmers=30), teelt(25, date(2026, 8, 31), prognose=date(2026, 11, 4)),
                   teelt(7, date(2026, 9, 28)), teelt(9, date(2026, 9, 30))]
        cxds = {24: date(2026, 10, 18), 25: date(2026, 10, 18), 7: date(2026, 10, 19), 9: date(2026, 10, 19)}
        uit = wp.taken(teelten, cxds, [], MA)
        self.assertEqual(titels(uit), [(date(2026, 10, 29), "CXDS-blok vak 7"),
                                       (date(2026, 10, 29), "CXDS-blok vak 9")])

    def test_planten_met_rizolex_en_inregenen_op_vrijdag(self):
        concepten = [(22, MA), (23, date(2026, 10, 27)), (24, date(2026, 10, 27)), (25, date(2026, 10, 29))]
        uit = wp.taken([], {}, concepten, MA)
        self.assertEqual(titels(uit), [
            (MA, "Planten vak 22 + Rizolex"), (date(2026, 10, 27), "Planten vak 23–24 + Rizolex"),
            (date(2026, 10, 29), "Planten vak 25 + Rizolex"),
            (date(2026, 10, 30), "Inregenen nieuwe vakken 22–25")])

    def test_florgib_telt_als_cxds_en_waterteelt_overslaan(self):
        teelten = [teelt(3, date(2026, 9, 21), florgib=date(2026, 10, 26)), teelt(4, date(2026, 9, 21)),
                   teelt(1, date(2026, 9, 21))]
        cxds = {3: date(2026, 10, 14), 4: date(2026, 10, 14), 1: date(2026, 10, 14)}
        uit = wp.taken(teelten, cxds, [], MA)
        # Vak 3 had CXDS met de Florgib op 26-10 (nog niet in Agro4all): niet in het blok met vak 4. Vak 1 nooit.
        self.assertEqual(titels(uit), [(MA, "CXDS-blok vak 4")])

    def test_concept_van_eerder_deze_week_en_inregenen_met_geplante_vakken(self):
        di = date(2026, 10, 27)
        uit = wp.taken([], {}, [(22, MA), (23, di)], di, geplant=[(21, date(2026, 10, 25))])
        self.assertEqual(titels(uit), [(di, "Planten vak 22 + Rizolex"), (di, "Planten vak 23 + Rizolex"),
                                       (date(2026, 10, 30), "Inregenen nieuwe vakken 21–23")])
        self.assertIn("loopt achter", uit[0]["toelichting"])

    def test_niet_op_zondag(self):
        teelten = [teelt(2, date(2026, 9, 21), florgib=date(2026, 10, 22))]     # 22-10 + 1,5 week = zo 1-11
        self.assertEqual(titels(wp.taken(teelten, {}, [], MA, dagen=8)), [(date(2026, 11, 2), "CXDS-blok vak 2")])

    def test_niet_op_zaterdag(self):
        teelten = [teelt(2, date(2026, 9, 21))]
        cxds = {2: date(2026, 10, 21)}                                          # + 1,5 week = za 31-10
        self.assertEqual(titels(wp.taken(teelten, cxds, [], MA)), [(date(2026, 10, 30), "CXDS-blok vak 2")])
        # Is het al zaterdag, dan naar maandag.
        za = date(2026, 10, 31)
        self.assertEqual(titels(wp.taken(teelten, cxds, [], za, dagen=3)), [(date(2026, 11, 2), "CXDS-blok vak 2")])

    def test_florgib_niet_in_het_weekend(self):
        teelten = [teelt(3, date(2026, 9, 21), verwacht=date(2026, 10, 31))]    # za
        uit = wp.taken(teelten, {3: date(2026, 10, 28)}, [], MA)
        self.assertEqual(titels(uit), [(date(2026, 10, 30), "Florgib + CXDS vak 3")])

    def test_buiten_de_periode_niets(self):
        teelten = [teelt(30, date(2026, 9, 7))]
        self.assertEqual(wp.taken(teelten, {30: date(2026, 10, 30)}, [], MA, dagen=7), [])

    def test_laatste_cxds(self):
        regels = [{"vaknummer": 3, "datum": date(2026, 10, 14), "middel": "ConSecta"},
                  {"vaknummer": 3, "datum": date(2026, 10, 20), "middel": "XenTari"},          # geen CXDS
                  {"vaknummer": 4, "datum": date(2026, 10, 22), "middel": "D-6 Force"}]
        self.assertEqual(wp.laatste_cxds(regels), {3: date(2026, 10, 14), 4: date(2026, 10, 22)})

    def test_onkruid_drie_weken_na_de_plantweek(self):
        # Plantweek 42 (13–16), 43 (17–21) en 44 (22–24); vak 1 (waterteelt) in week 43 telt niet mee.
        teelten = ([teelt(v, date(2026, 10, 12)) for v in range(13, 17)] +
                   [teelt(v, date(2026, 10, 19)) for v in range(17, 22)] + [teelt(1, date(2026, 10, 20))] +
                   [teelt(v, date(2026, 10, 26)) for v in range(22, 25)])
        cxds = {t["vak"]: date(2026, 11, 12) for t in teelten}        # geen CXDS in de periode
        uit = [t for t in wp.taken(teelten, cxds, [], date(2026, 11, 12), onkruid=True) if t["soort"] == "onkruid"]
        # Do 12-11: de lopende week (ma 09-11, al voorbij) én de volgende week, elk tot en met de zondag.
        self.assertEqual([(t["datum"], t["tot"], t["titel"]) for t in uit],
                         [(date(2026, 11, 9), date(2026, 11, 15), "Onkruid controleren vak 17–21"),
                          (date(2026, 11, 16), date(2026, 11, 22), "Onkruid controleren vak 22–24")])
        self.assertIn("plantweek 43", uit[0]["toelichting"])
        # Zonder onkruid=True (de app, de meldingen, het dagrapport) geen onkruidtaken.
        self.assertFalse([t for t in wp.taken(teelten, cxds, [], date(2026, 11, 12)) if t["soort"] == "onkruid"])


if __name__ == "__main__":
    unittest.main()

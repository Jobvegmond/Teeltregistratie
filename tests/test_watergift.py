"""Tests voor logic/watergift.py en de adapter voor behandelingen."""
import unittest
from datetime import date

from integrations import behandelingen as beh
from logic import watergift as wg

WATERSYSTEMEN = {1: {1: None}, 3: {1: [1, 2, 3], 2: [4, 5]}}


class TestKoppeling(unittest.TestCase):
    def test_alle_vakken(self):
        self.assertEqual(wg.watersysteem_van_vak(WATERSYSTEMEN, 1, 17), 1)
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 1, 1, [3, 1, 2]), [1, 2, 3])

    def test_vakken_per_systeem(self):
        self.assertEqual(wg.watersysteem_van_vak(WATERSYSTEMEN, 3, 5), 2)
        self.assertIsNone(wg.watersysteem_van_vak(WATERSYSTEMEN, 3, 9))
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 3, 2, range(1, 40)), [4, 5])
        self.assertEqual(wg.vakken_van_watersysteem(WATERSYSTEMEN, 3, 7, range(1, 40)), [])


class NepDatabase:
    def __init__(self):
        self.middelen, self.behandelingen = {}, []

    def upsert_middel(self, middel, bron):
        return self.middelen.setdefault((bron, middel.code), len(self.middelen) + 1)

    def upsert_behandeling(self, behandeling, middel_id, bron):
        self.behandelingen.append((bron, behandeling.extern_id, middel_id))


class NepBron:
    naam = "test"

    def fetch_behandelingen(self, van, tot):
        m = beh.Middel("ENT", "Entonem", "biologie")
        return [beh.Behandeling(date(2026, 9, 28), 3, 12, m, extern_id="a"),
                beh.Behandeling(date(2026, 9, 28), 3, 13, m, extern_id="b")]


class TestBehandelingen(unittest.TestCase):
    def test_lege_bron_schrijft_niets(self):
        db = NepDatabase()
        self.assertEqual(beh.synchroniseer(beh.LegeBron(), date(2026, 9, 1), date(2026, 9, 30), database=db), 0)
        self.assertEqual((db.middelen, db.behandelingen), ({}, []))

    def test_bron_via_dezelfde_vorm(self):
        db = NepDatabase()
        self.assertEqual(beh.synchroniseer(NepBron(), date(2026, 9, 1), date(2026, 9, 30), database=db), 2)
        self.assertEqual(db.middelen, {("test", "ENT"): 1})
        self.assertEqual(db.behandelingen, [("test", "a", 1), ("test", "b", 1)])


if __name__ == "__main__":
    unittest.main()


class TestMatrixLogica(unittest.TestCase):
    TEELTEN = [{"start": date(2026, 8, 3), "florgib": date(2026, 8, 31), "oogst": date(2026, 9, 25),
                "eerste_emmer": date(2026, 9, 21), "code": "263205"},
               {"start": date(2026, 9, 28), "florgib": None, "oogst": None, "eerste_emmer": None, "code": "264005"}]
    VANDAAG = date(2026, 9, 30)

    def test_teelt_en_markering(self):
        self.assertEqual(wg.markering(wg.teelt_op_dag(self.TEELTEN, date(2026, 8, 3), self.VANDAAG),
                                      date(2026, 8, 3)), {"plant"})
        self.assertEqual(wg.markering(wg.teelt_op_dag(self.TEELTEN, date(2026, 8, 31), self.VANDAAG),
                                      date(2026, 8, 31)), {"florgib"})
        self.assertEqual(wg.markering(wg.teelt_op_dag(self.TEELTEN, date(2026, 9, 23), self.VANDAAG),
                                      date(2026, 9, 23)), {"oogst"})
        self.assertIsNone(wg.teelt_op_dag(self.TEELTEN, date(2026, 9, 26), self.VANDAAG))   # leeg tussen de teelten
        self.assertEqual(wg.lopende_teelt(self.TEELTEN, self.VANDAAG)["code"], "264005")

    def test_vooruitkijken_met_verwachte_oogst(self):
        teelten = wg.rondes([
            {"start": date(2026, 9, 28), "florgib": None, "oogst": None, "eerste_emmer": None,
             "verwacht_oogst": date(2026, 12, 4), "concept": False},
            {"start": date(2026, 12, 14), "florgib": None, "oogst": None, "eerste_emmer": None,
             "verwacht_oogst": date(2027, 2, 26), "concept": True}])
        lopend = wg.teelt_op_dag(teelten, date(2026, 11, 1), self.VANDAAG)
        self.assertEqual((lopend["ronde"], lopend["concept"]), (0, False))
        self.assertEqual(wg.markering(lopend, date(2026, 12, 4), self.VANDAAG), {"oogst_verwacht"})
        self.assertIsNone(wg.teelt_op_dag(teelten, date(2026, 12, 10), self.VANDAAG))   # tussen oogst en concept
        self.assertEqual(wg.teelt_op_dag(teelten, date(2027, 1, 5), self.VANDAAG)["ronde"], 1)
        self.assertEqual(wg.laatste_eind({5: teelten}), date(2026, 12, 4))
        self.assertEqual(wg.laatste_eind({5: teelten}, met_concepten=True), date(2027, 2, 26))

    def test_echte_teelt_gaat_voor_concept(self):
        teelten = wg.rondes([
            {"start": date(2026, 9, 25), "florgib": None, "oogst": None, "eerste_emmer": None,
             "verwacht_oogst": date(2026, 12, 1), "concept": True},
            {"start": date(2026, 9, 28), "florgib": None, "oogst": None, "eerste_emmer": None,
             "verwacht_oogst": date(2026, 12, 4), "concept": False}])
        self.assertFalse(wg.teelt_op_dag(teelten, date(2026, 10, 15), self.VANDAAG)["concept"])
        concept = [dict(teelten[0])]
        self.assertIsNone(wg.lopende_teelt(concept, self.VANDAAG))     # een concept is geen lopende teelt

    def test_oogst_loopt_tot_vandaag_bij_eerste_emmer(self):
        t = {"start": date(2026, 8, 3), "florgib": None, "oogst": None, "eerste_emmer": date(2026, 9, 28),
             "verwacht_oogst": date(2026, 9, 29)}
        self.assertEqual(wg.markering(t, date(2026, 9, 30), self.VANDAAG), {"oogst"})
        self.assertIs(wg.teelt_op_dag([t], date(2026, 9, 30), self.VANDAAG), t)     # loopt door t/m vandaag

    def test_watergift_som_per_teelt(self):
        gift = {date(2026, 9, 27): 5.0, date(2026, 9, 28): 3.0, date(2026, 9, 29): None, date(2026, 9, 30): 2.5}
        self.assertEqual(wg.totaal_sinds_planten(gift, date(2026, 9, 28), self.VANDAAG), 5.5)

    def test_samenvatting_leeg_vak_telt_niet_mee(self):
        gift = {(1, date(2026, 9, 28)): 4.0, (2, date(2026, 9, 28)): 0.0}
        bezet = lambda vak, dag: vak == 1                     # vak 2 staat leeg
        uit = wg.samenvatting(gift, [1, 2], {1: 550, 2: 550}, bezet, date(2026, 9, 28), date(2026, 9, 29))
        self.assertEqual((uit["gift_per_dag"], uit["giftdagen"], uit["laatste"]), (2.0, 1, date(2026, 9, 28)))

    def test_ec_meststoffen(self):
        self.assertEqual(wg.ec_meststoffen({"ec_gem": 1.41, "ec_aanvoer": 0.12}), 1.29)
        self.assertIsNone(wg.ec_meststoffen({"ec_gem": 1.41, "ec_aanvoer": None}))

    def test_band(self):
        self.assertEqual(wg.band_status(1.1, (1.2, 1.7)), "laag")
        self.assertEqual(wg.band_status(1.8, (1.2, 1.7)), "hoog")
        self.assertIsNone(wg.band_status(1.4, (1.2, 1.7)))
        self.assertIsNone(wg.band_status(None, (1.2, 1.7)))

    def test_periode_hele_weken(self):
        self.assertEqual(wg.periode(date(2026, 9, 28), 4), (date(2026, 9, 7), date(2026, 10, 4)))


class TestBehandelingenSubregel(unittest.TestCase):
    """De subregel met middelcodes staat er alleen als er behandelingen zijn."""

    def matrix(self, behandelingen):
        from ui import watergift_matrix as wm
        dagen = [date(2026, 9, 28), date(2026, 9, 29)]
        per_dag = wg.behandelingen_per_vak_dag(behandelingen)
        m = {"dagen": dagen, "vandaag": date(2026, 9, 30), "maximum": 5.0,
             "toon_behandelingen": wg.toon_behandelingen(behandelingen), "kwaliteit": [],
             "afdelingen": [{"naam": "Afd. 1", "vakken": [
                 {"vak": 3, "plantweek": "wk 35", "leeftijd": "30 d", "totaal": "40", "tip": "",
                  "cellen": [{"liter": 2.0, "bron": "priva", "markering": set(), "tip": ""}] * 2,
                  "behandelingen": [per_dag.get((3, d), []) for d in dagen]}]}]}
        return wm.bouw_html(m)

    def test_verborgen_bij_lege_tabel(self):
        self.assertNotIn('class="beh"', self.matrix([]))

    def test_zichtbaar_met_testdata(self):
        html = self.matrix([{"vaknummer": 3, "datum": "2026-09-29", "code": "ENT", "type": "biologie"}])
        self.assertIn('class="beh"', html)
        self.assertIn(">ENT</span>", html)

"""Tests voor logic/prognoselog.py en het dagelijks (idempotent) wegschrijven van het prognoselogboek."""
import re
import sqlite3
import unittest
from datetime import date, timedelta

import pandas as pd

import database
from logic import prognoselog as pl

VANDAAG = date(2026, 9, 29)
TEELTEN = pd.DataFrame([
    {"id": 1, "tuin_id": 3, "afdeling": 2, "vaknummer": 31, "code": "2631-31", "datum_half": None},
    {"id": 2, "tuin_id": 1, "afdeling": 1, "vaknummer": 5, "code": "2630-05", "datum_half": "2026-09-20"},
    {"id": 3, "tuin_id": 1, "afdeling": 1, "vaknummer": 6, "code": "2630-06", "datum_half": None},  # geen prognose
])


def stand(start, prognose, c=0.4):
    return {"start": start, "gedaan": 0.5, "plan": date(2026, 10, 30), "prognose": prognose,
            "c": c, "begrensd": False}


STOOK = {1: stand(date(2026, 8, 1), date(2026, 11, 2)), 2: stand(date(2026, 7, 20), date(2026, 10, 28), c=None)}
AFWIJKING = {(3, 2): 0.8}


def logregel(teelt_id, datum, prognose, plan=date(2026, 11, 10), fase="voor_florgib", tuin_id=3):
    return {"teelt_id": teelt_id, "tuin_id": tuin_id, "code": f"c{teelt_id}", "vaknummer": teelt_id,
            "datum": datum, "prognose_oogst": prognose, "plan_oogst": plan, "fase": fase}


class TestLogregels(unittest.TestCase):
    def test_een_regel_per_vak_met_prognose(self):
        regels = pl.logregels(TEELTEN, STOOK, AFWIJKING, VANDAAG, "m/n50")
        self.assertEqual([r["teelt_id"] for r in regels], [1, 2])
        eerste, tweede = regels
        self.assertEqual((eerste["leeftijd_d"], eerste["fase"], eerste["stooklijn"], eerste["stooklijn_bron"]),
                         (59, "voor_florgib", 0.8, "gerealiseerd_14d"))
        self.assertEqual((tweede["fase"], tweede["stooklijn"], tweede["stooklijn_bron"], tweede["correctie_c"]),
                         ("na_florgib", 0.0, "ingesteld", None))
        self.assertEqual(set(eerste), set(database.PROGNOSE_LOG_KOLOMMEN))


class TestIdempotentLog(unittest.TestCase):
    """De INSERT van database.py op een SQLite-kopie van de tabel: tweemaal loggen op één dag = één regel."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        ddl = database.PROGNOSE_LOG_TABEL.replace("SERIAL", "INTEGER").replace("now()", "CURRENT_TIMESTAMP")
        self.db.execute(ddl)
        self.insert = re.sub(r"%\((\w+)\)s", r":\1", database.PROGNOSE_LOG_INSERT)

    def schrijf(self, regels):
        nieuw = 0
        for r in regels:
            nieuw += self.db.execute(self.insert, {k: (str(v) if isinstance(v, date) else v)
                                                   for k, v in r.items()}).rowcount
        return nieuw

    def test_tweede_keer_op_dezelfde_dag_verandert_niets(self):
        regels = pl.logregels(TEELTEN, STOOK, AFWIJKING, VANDAAG, "m")
        self.assertEqual(self.schrijf(regels), 2)
        anders = [dict(r, prognose_oogst=r["prognose_oogst"] + timedelta(days=5)) for r in regels]
        self.assertEqual(self.schrijf(anders), 0)
        rijen = self.db.execute("SELECT teelt_id, prognose_oogst FROM prognose_log ORDER BY teelt_id").fetchall()
        self.assertEqual(rijen, [(1, "2026-11-02"), (2, "2026-10-28")])  # de eerste regel blijft

    def test_volgende_dag_komt_erbij(self):
        self.schrijf(pl.logregels(TEELTEN, STOOK, AFWIJKING, VANDAAG, "m"))
        self.assertEqual(self.schrijf(pl.logregels(TEELTEN, STOOK, AFWIJKING, VANDAAG + timedelta(days=1), "m")), 2)


class TestWerkelijkeOogst(unittest.TestCase):
    def test_helft_van_de_emmers(self):
        emmers = {"2026-11-05": 10, "2026-11-03": 20, "2026-11-04": 25, "2026-11-06": 5}
        # totaal 60: na 03-11 20, na 04-11 45 ≥ 30
        self.assertEqual(pl.werkelijke_oogst(emmers), (date(2026, 11, 3), date(2026, 11, 4)))

    def test_zonder_emmers_de_oogstdatum(self):
        self.assertEqual(pl.werkelijke_oogst({}, "2026-11-07"), (None, date(2026, 11, 7)))


class TestFoutberekening(unittest.TestCase):
    WERKELIJK = date(2026, 11, 10)

    def test_horizons_dichtstbij_binnen_marge(self):
        log = [logregel(1, self.WERKELIJK - timedelta(days=d), self.WERKELIJK) for d in (30, 25, 15, 13, 9)]
        uit = pl.horizonregels(log, self.WERKELIJK)
        # 28 d: alleen 30 ligt binnen ±2 (25 niet); 14 d: 15 en 13 even ver → de vroegste (15)
        self.assertEqual((self.WERKELIJK - uit[28]["datum"]).days, 30)
        self.assertEqual((self.WERKELIJK - uit[14]["datum"]).days, 15)
        self.assertEqual((self.WERKELIJK - uit[7]["datum"]).days, 9)
        self.assertNotIn(pl.FLORGIB, uit)

    def test_horizon_zonder_regel_binnen_marge_ontbreekt(self):
        log = [logregel(1, self.WERKELIJK - timedelta(days=20), self.WERKELIJK)]
        self.assertEqual(pl.horizonregels(log, self.WERKELIJK), {})

    def test_eerste_regel_na_florgib(self):
        log = [logregel(1, self.WERKELIJK - timedelta(days=d), self.WERKELIJK, fase=f)
               for d, f in ((40, "voor_florgib"), (35, "na_florgib"), (34, "na_florgib"))]
        self.assertEqual((self.WERKELIJK - pl.horizonregels(log, self.WERKELIJK)[pl.FLORGIB]["datum"]).days, 35)

    def test_fout_is_werkelijk_min_prognose_en_plan(self):
        log = [logregel(1, self.WERKELIJK - timedelta(days=14), date(2026, 11, 7), plan=date(2026, 11, 12))]
        rij, = pl.fouten(log, {1: (date(2026, 11, 8), self.WERKELIJK)})
        self.assertEqual((rij["horizon"], rij["fout_prognose"], rij["fout_plan"], rij["dagen_voor_oogst"]),
                         (14, 3, -2, 14))

    def test_niet_geoogst_telt_niet(self):
        log = [logregel(1, self.WERKELIJK - timedelta(days=14), self.WERKELIJK)]
        self.assertEqual(pl.fouten(log, {}), [])

    def test_kwaliteit_per_tuin_en_horizon(self):
        rijen = [{"tuin_id": 3, "horizon": 14, "fout_prognose": f} for f in (3, -1, 0, -4)]
        k = pl.kwaliteit(rijen, "fout_prognose")[(3, 14)]
        self.assertEqual((k["n"], k["gemiddeld"], k["mae"], k["binnen_pct"]), (4, -0.5, 2.0, 50.0))

    def test_grootste_missers(self):
        log = []
        for teelt_id, fout in ((1, 2), (2, -6), (3, 4)):
            log.append(logregel(teelt_id, self.WERKELIJK - timedelta(days=7), self.WERKELIJK - timedelta(days=fout)))
        oogsten = {i: (None, self.WERKELIJK) for i in (1, 2, 3)}
        missers = pl.grootste_missers(pl.fouten(log, oogsten), aantal=2)
        self.assertEqual([(m["teelt_id"], m["max_fout"]) for m in missers], [(2, -6), (3, 4)])
        self.assertEqual(pl.aantal_vakken(pl.fouten(log, oogsten)), 3)


if __name__ == "__main__":
    unittest.main()

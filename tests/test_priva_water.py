"""Tests voor integrations/priva_water.py (gift, beurten, EC/pH per dag) en het idempotent opslaan van EC/pH."""
import re
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone

import database
from integrations import priva_water as pw

UTC = timezone.utc


def t(dag, uur, minuut=0):
    """Lokale tijd (CEST, zoals LOKALE_OFFSET) → UTC-tijdstip."""
    return datetime(2026, 9, dag, uur, minuut, tzinfo=UTC) - pw.LOKALE_OFFSET


class TestGift(unittest.TestCase):
    def test_liters_en_beurten(self):
        reeks = [(t(28, 7), 100.0), (t(28, 7, 1), 100.5), (t(28, 7, 2), 101.0),     # beurt 1: 1,0
                 (t(28, 11), 101.0), (t(28, 11, 1), 101.7),                          # beurt 2: 0,7
                 (t(29, 9), 101.7), (t(29, 9, 1), 102.0)]                            # 29-09: beurt 1: 0,3
        uit = pw.gift_per_dag(reeks)
        self.assertEqual(uit[date(2026, 9, 28)], (1.7, 2))
        self.assertEqual(uit[date(2026, 9, 29)], (0.3, 1))

    def test_reset_telt_niet_en_dag_zonder_gift_is_nul(self):
        reeks = [(t(28, 6), 500.0), (t(28, 7), 0.0), (t(28, 8), 0.6), (t(29, 6), 0.6), (t(29, 18), 0.6)]
        uit = pw.gift_per_dag(reeks)
        self.assertEqual(uit[date(2026, 9, 28)], (0.6, 1))
        self.assertEqual(uit[date(2026, 9, 29)], (0.0, 0))


class TestKwaliteit(unittest.TestCase):
    def test_tijdgewogen_met_maximaal_gewicht(self):
        # 1,0 geldt 10 min (begrensd, want de volgende meting is pas na 2 uur), 2,0 geldt 5 min, 3,0 10 min.
        reeks = [(t(28, 8), 1.0), (t(28, 10), 2.0), (t(28, 10, 5), 3.0)]
        uit = pw.tijdgewogen_per_dag(reeks)[date(2026, 9, 28)]
        self.assertAlmostEqual(uit["gem"], (1 * 10 + 2 * 5 + 3 * 10) / 25)
        self.assertEqual((uit["min"], uit["max"], uit["n"]), (1.0, 3.0, 3))

    def test_recept_langst_actief_zonder_geen_recept(self):
        reeks = [(t(28, 6), 2.0), (t(28, 6, 5), pw.GEEN_RECEPT), (t(28, 7), 3.0), (t(28, 7, 2), 3.0)]
        self.assertEqual(pw.recept_per_dag(reeks), {date(2026, 9, 28): 3})

    def test_ingestelde_waarde_nul_telt_niet(self):
        reeksen = {"ec": [(t(28, 9), 1.5)], "ec_doel": [(t(28, 9), 1.6), (t(28, 9, 5), 0.0)],
                   "ph_doel": [(t(28, 9), 0.0)]}
        rij, = pw.kwaliteit_rijen(reeksen, 1, date(2026, 9, 28), date(2026, 9, 28))
        self.assertEqual((rij["ec_doel"], rij["ph_doel"]), (1.6, None))

    def test_ec_uitgangswater_zonder_nullen(self):
        reeksen = {"ec": [(t(28, 9), 1.41)], "ec_aanvoer": [(t(28, 9), 0.12), (t(28, 9, 5), 0.0)]}
        rij, = pw.kwaliteit_rijen(reeksen, 1, date(2026, 9, 28), date(2026, 9, 28))
        self.assertEqual(rij["ec_aanvoer"], 0.12)

    def test_kwaliteit_rijen_alleen_binnen_venster(self):
        reeksen = {"ec": [(t(27, 9), 1.4), (t(28, 9), 1.5)], "ph": [(t(28, 9), 6.0)], "recept": [(t(28, 8), 2.0)]}
        rijen = pw.kwaliteit_rijen(reeksen, 1, date(2026, 9, 28), date(2026, 9, 28))
        self.assertEqual(len(rijen), 1)
        self.assertIsNone(rijen[0]["ec_doel"])
        self.assertEqual((rijen[0]["ec_gem"], rijen[0]["ph_gem"], rijen[0]["recept"], rijen[0]["watersysteem"]),
                         (1.5, 6.0, 2, 1))


class NepClient:
    """Doet alsof hij Priva is: geeft een vaste payload terug op het ene verzoek."""
    device_id = "VP9508"
    vakken = (1, 2)

    def __init__(self, payload):
        self.payload, self.verzoeken = payload, 0

    def _venster(self, dagen_terug):
        return datetime(2026, 9, 26, tzinfo=UTC), datetime(2026, 9, 28, 23, 59, 59, tzinfo=UTC)

    def _data_call(self, begin, eind, datapoints, wat="data"):
        self.verzoeken += 1
        self.gevraagd = [d["variableId"] for d in datapoints]
        return self.payload


def meting(tijd, waarde):
    return {"timestampUtc": tijd.strftime("%Y-%m-%dT%H:%M:%SZ"), "value": str(waarde)}


class TestHaalWater(unittest.TestCase):
    def test_een_verzoek_voor_gift_en_ec_ph(self):
        payload = {"data": [
            {"datapoint": {"variableId": pw.kraan_variabele(2)},
             "measurements": [meting(t(28, 7), 10.0), meting(t(28, 7, 1), 10.8)]},
            {"datapoint": {"variableId": pw.watersysteem_variabele(1, pw.STAART_EC)},
             "measurements": [meting(t(28, 7), 1.5)]},
            {"datapoint": {"variableId": pw.watersysteem_variabele(1, pw.STAART_PH)},
             "measurements": [meting(t(28, 7), 5.9)]},
        ]}
        client = NepClient(payload)
        gift, kwaliteit = pw.haal_water_dagwaarden(client, 3)
        self.assertEqual(client.verzoeken, 1)
        self.assertIn(pw.kraan_variabele(1), client.gevraagd)
        self.assertIn(pw.watersysteem_variabele(1, pw.STAART_PH), client.gevraagd)
        self.assertEqual(gift, [{"vaknummer": 2, "datum": date(2026, 9, 28), "liter_per_m2": 0.8, "beurten": 1}])
        self.assertEqual((kwaliteit[0]["datum"], kwaliteit[0]["ec_gem"], kwaliteit[0]["ph_gem"]),
                         (date(2026, 9, 28), 1.5, 5.9))


class TestIdempotentOpslaan(unittest.TestCase):
    """De upsert van database.py op een SQLite-kopie: twee keer dezelfde dag ophalen = één regel, de laatste telt."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(database.WATER_KWALITEIT_TABEL.replace("SERIAL", "INTEGER").replace("now()", "CURRENT_TIMESTAMP"))
        self.sql = re.sub(r"%\((\w+)\)s", r":\1", database.WATER_KWALITEIT_UPSERT)

    def schrijf(self, rij):
        waarden = {k: rij.get(k) for k in database.WATER_KWALITEIT_KOLOMMEN}
        waarden.update(tuin_id=3, datum=str(rij["datum"]), bron="priva")
        self.db.execute(self.sql, waarden)

    def test_zelfde_dag_twee_keer(self):
        rij = {"watersysteem": 1, "datum": date(2026, 9, 28), "ec_gem": 1.4, "ph_gem": 6.0, "metingen": 50}
        self.schrijf(rij)
        self.schrijf(dict(rij, ec_gem=1.45, metingen=180))      # latere ophaling: volledigere dag
        rijen = self.db.execute("SELECT datum, ec_gem, metingen FROM water_kwaliteit_dag").fetchall()
        self.assertEqual(rijen, [("2026-09-28", 1.45, 180)])
        self.schrijf(dict(rij, datum=date(2026, 9, 29)))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM water_kwaliteit_dag").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()

"""Tests voor integrations/priva_water.py (gift, beurten, EC/pH per dag) en het idempotent opslaan van EC/pH."""
import re
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone

import database
from integrations import priva_water as pw

UTC = timezone.utc


def t(dag, uur, minuut=0, seconde=0):
    """Lokale tijd (CEST, zoals LOKALE_OFFSET) → UTC-tijdstip."""
    return datetime(2026, 9, dag, uur, minuut, seconde, tzinfo=UTC) - pw.LOKALE_OFFSET


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

    def test_terugsprong_na_reset_telt_niet(self):
        # Echt patroon uit Priva, tuin 3 vak 2, 06-10-26: tellers op nul, 26 s later nog één keer de oude
        # stand, daarna definitief nul en een gift van 13,2. Opgeslagen werd 595,9 (582,7 + 13,2).
        def o(uur, minuut, seconde=0):
            return datetime(2026, 10, 6, uur, minuut, seconde, tzinfo=UTC) - pw.LOKALE_OFFSET
        reeks = [(o(3, 56, 55), 582.7), (o(10, 48, 22), 0.0), (o(10, 48, 48), 582.7), (o(10, 54, 4), 0.0),
                 (o(14, 0), 0.0), (o(14, 0, 5), 6.0), (o(14, 0, 10), 13.2)]
        self.assertEqual(pw.gift_per_dag(reeks), {date(2026, 10, 6): (13.2, 1)})
        (start, eind, liter), = pw.beurten_uit(reeks)
        self.assertEqual((start, eind, round(liter, 1)), (o(14, 0), o(14, 0, 10), 13.2))
        # Een lage oude stand (onder MAX_TOENAME_PER_STAP) valt via de terugsprongregel weg.
        laag = [(o(3, 0), 12.0), (o(10, 48, 22), 0.0), (o(10, 48, 48), 12.0), (o(10, 54, 4), 0.0)]
        self.assertEqual(pw.gift_per_dag(laag), {date(2026, 10, 6): (0.0, 0)})

    def test_onmogelijk_grote_stap_telt_niet(self):
        reeks = [(t(28, 6), 10.0), (t(28, 7), 410.0), (t(28, 8), 410.0), (t(28, 8, 0, 5), 411.5)]
        self.assertEqual(pw.gift_per_dag(reeks), {date(2026, 9, 28): (1.5, 1)})


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


class TestPerGift(unittest.TestCase):
    """EC/pH per gietbeurt, zoals Priva ze in het kraanoverzicht toont (gemiddelde over de beurt)."""

    def test_beurten_uit_meterstand(self):
        # Priva logt tijdens een beurt elke ~5 s
        reeks = [(t(29, 16, 0), 10.0), (t(29, 16, 0, 5), 10.7), (t(29, 16, 0, 10), 12.0),    # beurt 1: 2,0
                 (t(29, 18, 0), 12.0), (t(29, 18, 0, 5), 12.5)]                              # beurt 2: 0,5
        beurten = pw.beurten_uit(reeks)
        self.assertEqual([(a, b, round(l, 2)) for a, b, l in beurten],
                         [(t(29, 16, 0), t(29, 16, 0, 10), 2.0), (t(29, 18, 0), t(29, 18, 0, 5), 0.5)])

    def test_beurt_begint_bij_de_wijziging_niet_bij_de_vorige_stand(self):
        # De vorige stand is 12 uur oud (Priva logt dan eens per 12 uur); de beurt zelf loopt 16:00–16:03.
        reeks = [(t(29, 4, 7), 55.0), (t(29, 16, 0, 30), 55.05), (t(29, 16, 1), 55.7), (t(29, 16, 3), 57.0)]
        (start, eind, liter), = pw.beurten_uit(reeks)
        self.assertEqual((start, eind, round(liter, 2)), (t(29, 16, 0, 25), t(29, 16, 3), 2.0))
        # ook de dag van de liters volgt de wijziging: een beurt net na middernacht hoort bij de nieuwe dag
        nacht = [(t(28, 22, 0), 10.0), (t(29, 0, 5), 10.1), (t(29, 0, 6), 11.0)]
        self.assertEqual(pw.gift_per_dag(nacht), {date(2026, 9, 29): (1.0, 1)})

    def test_gemiddelde_over_de_beurt(self):
        # Vóór de beurt 1,4; om 16:01 1,2 en om 16:02 1,5; beurt 16:00–16:03: (1×1,4 + 1×1,2 + 1×1,5) / 3
        ec = [(t(29, 15, 50), 1.4), (t(29, 16, 1), 1.2), (t(29, 16, 2), 1.5), (t(29, 16, 10), 1.0)]
        self.assertAlmostEqual(pw.gemiddelde_tussen(ec, t(29, 16, 0), t(29, 16, 3)), (1.4 + 1.2 + 1.5) / 3)
        self.assertIsNone(pw.gemiddelde_tussen([], t(29, 16, 0), t(29, 16, 3)))

    def test_beurt_rijen_en_weging_per_dag(self):
        meterstand = [(t(29, 8, 0), 0.0), (t(29, 8, 0, 5), 3.0), (t(29, 16, 0), 3.0), (t(29, 16, 0, 5), 4.0)]
        ec = [(t(29, 7, 0), 1.6), (t(29, 12, 0), 1.2)]           # ochtendbeurt 1,6, middagbeurt 1,2
        ph = [(t(29, 7, 0), 5.8)]
        flow = [(t(29, 8, 1), 22.0), (t(29, 16, 1), 20.0)]
        rijen = pw.beurt_rijen(7, meterstand, ec, ph, flow)
        self.assertEqual([(r["liter_per_m2"], r["ec"], r["ph"]) for r in rijen], [(3.0, 1.6, 5.8), (1.0, 1.2, 5.8)])
        # dag: gewogen naar de liters, dus dichter bij de grote ochtendbeurt
        self.assertAlmostEqual(pw.gewogen((r["ec"], r["liter_per_m2"]) for r in rijen), (3 * 1.6 + 1 * 1.2) / 4)


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
        gift, kwaliteit, beurten = pw.haal_water_dagwaarden(client, 3)
        self.assertEqual(client.verzoeken, 1)
        self.assertIn(pw.kraan_flow_variabele(1), client.gevraagd)
        self.assertEqual(len(beurten), 1)
        self.assertEqual((beurten[0]["vaknummer"], beurten[0]["ec"], beurten[0]["ph"]), (2, 1.5, 5.9))
        self.assertIn(pw.kraan_variabele(1), client.gevraagd)
        self.assertIn(pw.watersysteem_variabele(1, pw.STAART_PH), client.gevraagd)
        self.assertEqual(gift, [{"vaknummer": 2, "datum": date(2026, 9, 28), "liter_per_m2": 0.8, "beurten": 1,
                                 "ec": 1.5, "ph": 5.9}])
        self.assertEqual((kwaliteit[0]["ec_gift"], kwaliteit[0]["ph_gift"]), (1.5, 5.9))
        self.assertEqual((kwaliteit[0]["datum"], kwaliteit[0]["ec_gem"], kwaliteit[0]["ph_gem"]),
                         (date(2026, 9, 28), 1.5, 5.9))


class TestBeurtenOpslaan(unittest.TestCase):
    """De upsert van gietbeurten op een SQLite-kopie: dezelfde beurt twee keer ophalen = één regel."""

    def test_zelfde_beurt_twee_keer(self):
        db = sqlite3.connect(":memory:")
        db.execute(database.WATERGIFT_BEURT_TABEL.replace("SERIAL", "INTEGER"))
        sql = re.sub(r"%\((\w+)\)s", r":\1", database.WATERGIFT_BEURT_UPSERT)
        rij = {"tuin_id": 3, "vaknummer": 7, "start": "2026-09-29T14:00:30+00:00", "eind": "2026-09-29T14:03:25+00:00",
               "datum": "2026-09-29", "liter_per_m2": 2.0, "ec": 1.34, "ph": 6.07, "flow": 21.9, "bron": "priva"}
        db.execute(sql, rij)
        db.execute(sql, dict(rij, ec=1.35))
        self.assertEqual(db.execute("SELECT COUNT(*), MAX(ec) FROM watergift_beurt").fetchone(), (1, 1.35))
        db.close()


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

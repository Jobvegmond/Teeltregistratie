"""Tests voor logic/klimaat_dag.py: klimaat per dag (etmaal, dag, nacht, lichtsom) uit de Priva-bestanden."""
import json
import unittest
from datetime import date, datetime, timedelta

from logic import klimaat_dag as kd

LIGGING = (52.011, 4.535)     # Bleiswijk


def t(dag, uur, minuut=0):
    return datetime(2026, 10, dag, uur, minuut, tzinfo=kd.NL)


def minuten(van, tot, waarde):
    """Elke minuut van `van` tot `tot` dezelfde (temp, rv) in alle afdelingen; waarde(tijd) → (temp, rv)."""
    uit, tijd = [], van
    while tijd < tot:
        uit.append((tijd, {n: waarde(tijd) for n in kd.AFDELINGEN}))
        tijd += timedelta(minutes=1)
    return uit


class TestZon(unittest.TestCase):
    def test_zonsopkomst_en_ondergang_bleiswijk(self):
        # Ongeveer de tabelwaarden voor Rotterdam (± 2 min): 25-10 (wintertijd) 07:22 en 17:29, 21-06 05:20 en 22:06.
        for dag, verwacht in ((date(2026, 10, 25), (t(25, 7, 22), t(25, 17, 29))),
                              (date(2026, 6, 21), (datetime(2026, 6, 21, 5, 20, tzinfo=kd.NL),
                                                   datetime(2026, 6, 21, 22, 6, tzinfo=kd.NL)))):
            for gekregen, tabel in zip(kd.zon_op_onder(dag, LIGGING), verwacht):
                self.assertLess(abs(gekregen - tabel), timedelta(minutes=2), (dag, gekregen))
        self.assertEqual(kd.zon_op_onder(date(2026, 10, 25), LIGGING)[0].utcoffset(), timedelta(hours=1))


class TestInlezen(unittest.TestCase):
    def test_minuten_rv_nul_is_leeg(self):
        regels = [json.dumps({"t": "2026-10-27T10:00:30+01:00",
                              "v": {"afd1.klimaatOverzicht.gemetenKasTemperatuur": 16.2,
                                    "afd1.klimaatOverzicht.gemetenRelatieveLuchtvochtigheid": 0}}), '{"t": "2026-1']
        uit = kd.lees_minuten(regels)
        self.assertEqual(len(uit), 1)
        self.assertEqual(uit[0][1][1], (16.2, None))
        self.assertEqual(uit[0][1][2], (None, None))

    def test_stralings_ids_en_storing(self):
        catalogus = ['"id";"adres";"naam"', '"1890";"/afdeling[VP9508:1]/klimaatOverzicht/berekendeBinnenStraling";"x"',
                     '"1892";"/afdeling[VP9508:1]/klimaatOverzicht/berekendeGroeilichtStraling";"x"',
                     '"5734";"/afdeling[VP9508:2]/klimaatOverzicht/berekendeBinnenStraling";"x"']
        ids = kd.stralings_ids(catalogus, "VP9508")
        self.assertEqual(ids, {"1890": 1, "5734": 2})
        self.assertEqual(kd.stralings_ids(catalogus, "Matricaria25"), {})
        regels = [json.dumps({"t": "2026-10-27T00:00:00+01:00", "soort": "basis", "v": {"1890": 0, "5734": 0}}),
                  json.dumps({"t": "2026-10-27T09:00:00+01:00", "soort": "meting", "v": {"1890": 100}}),
                  json.dumps({"t": "2026-10-27T09:30:00+01:00", "soort": "storing", "v": {}})]
        punten, tijden = kd.lees_straling(regels, ids)
        self.assertEqual(punten[1], [(t(27, 0), 0.0), (t(27, 9), 100.0)])
        self.assertEqual(tijden, [t(27, 0), t(27, 9)])        # de storing telt niet als dekking


class TestGedekt(unittest.TestCase):
    def test_gat_en_lopend_venster(self):
        elke_10 = [t(27, 0) + timedelta(minutes=10 * i) for i in range(150)]     # tot 28-10 00:50
        self.assertTrue(kd.gedekt(elke_10, t(27, 0), t(28, 0)))
        self.assertFalse(kd.gedekt(elke_10, t(28, 0), t(29, 0)))                 # loopt nog
        gat = [x for x in elke_10 if not t(27, 10) < x < t(27, 11, 30)]          # 1,5 uur niets
        self.assertFalse(kd.gedekt(gat, t(27, 0), t(28, 0)))
        uur = [x for x in elke_10 if not t(27, 10) < x < t(27, 11)]              # een uur mag (wintertijd)
        self.assertTrue(kd.gedekt(uur, t(27, 0), t(28, 0)))


class TestDagwaarden(unittest.TestCase):
    def test_etmaal_dag_nacht_en_lichtsom(self):
        op, onder = kd.zon_op_onder(date(2026, 10, 27), LIGGING)
        # Overdag 20 °C en 80 %, 's nachts 14 °C en 95 %; tot de volgende ochtend 9 uur.
        data = minuten(t(27, 0), t(28, 9), lambda x: (20.0, 80.0) if op <= x < onder else (14.0, 95.0))
        # Straling 100 W/m² van 10 tot 14 uur (4 uur = 144 J/cm²), alleen afdeling 1.
        straling = {1: [(t(27, 0), 0.0), (t(27, 10), 100.0), (t(27, 14), 0.0)], 2: []}
        tijden = [x for x, _ in data]
        rijen = kd.dagwaarden(date(2026, 10, 27), LIGGING, data, straling, tijden)
        self.assertEqual([r["afdeling"] for r in rijen], [1, 2, 3, 4])
        r = rijen[0]
        self.assertEqual((r["gem_temperatuur_dag"], r["gem_rv_dag"]), (20.0, 80.0))
        self.assertEqual((r["gem_temperatuur_nacht"], r["gem_rv_nacht"]), (14.0, 95.0))
        dag_minuten = (onder - op).total_seconds() / 60
        self.assertAlmostEqual(r["gem_temperatuur"], round(14 + 6 * dag_minuten / 1440, 2), places=1)
        self.assertEqual(r["stralingssom_dag"], 144)
        self.assertIsNone(rijen[1]["stralingssom_dag"])                         # geen stralingspunten

    def test_nacht_nog_niet_compleet_en_etmaal_niet_af(self):
        data = minuten(t(27, 0), t(28, 6), lambda x: (15.0, 90.0))             # zon komt 28-10 pas om 7:27 op
        rijen = kd.dagwaarden(date(2026, 10, 27), LIGGING, data)
        self.assertIsNone(rijen[0]["gem_temperatuur_nacht"])
        self.assertEqual(rijen[0]["gem_temperatuur"], 15.0)
        self.assertIsNone(rijen[0]["stralingssom_dag"])                         # geen straling meegegeven
        self.assertEqual(kd.dagwaarden(date(2026, 10, 28), LIGGING, data), [])  # 28-10 loopt nog


if __name__ == "__main__":
    unittest.main()

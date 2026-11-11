"""Tests voor logic/priva_water_bestanden.py: gietbeurten en EC/pH per watersysteem uit de Priva-bestanden."""
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from integrations import priva_water as pw
from logic import priva_water_bestanden as pwb

UTC = timezone.utc
CET = timezone(timedelta(hours=1))
CATALOGUS_KOP = "scad;iaddr;scherm;schermnaam;index;omschrijving;eenheid;soort"


def t(uur, minuut, seconde=0, dag=9):
    """Een tijdstip op 9-11-2026 in Nederlandse wintertijd, als UTC (zoals lees_jsonl het teruggeeft)."""
    return datetime(2026, 11, dag, uur, minuut, seconde, tzinfo=CET).astimezone(UTC)


def regel(tijd, soort, waarden):
    return json.dumps({"t": tijd.astimezone(CET).isoformat(), "soort": soort, "v": waarden})


class TestCatalogus(unittest.TestCase):
    def test_v_nummers_per_regelaar_op_omschrijving(self):
        tuin3 = [CATALOGUS_KOP,
                 "M430.0N1R1.1V4;1:1:1;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS - recept;;meting",
                 "M430.0N1R1.1V6;1:1:2;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS - gem EC;mS/cm;meting",
                 "M430.0N1R1.1V8;1:1:3;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS - gem ECa;mS/cm;meting",
                 "M430.0N1R2.1V4;1:1:4;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS DOSERING - gem flow m3;"
                 "m3/uur;meting",
                 "M420.0N1R6.1V2;1:1:5;M420.0;HYDRO/OVERZICHT/DOSERING/ACTUEEL;1;WATSYS - ber EC;mS/cm;meting"]
        tuin1 = [CATALOGUS_KOP,
                 "M430.0N1R1.1V5;1:2:1;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS 1 - gem EC;mS/cm;meting",
                 "M430.0N1R1.1V6;1:2:2;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS 1 - gem pH;pH;meting",
                 "M430.0N1R1.2V3;1:2:3;M430.0;HYDRO/OVERZICHT/WATERSYSTEMEN/ACTUEEL;1;WATSYS 2 - recept;;meting",
                 "M420.0N1R6.1V3;1:2:4;M420.0;HYDRO/OVERZICHT/DOSERING/ACTUEEL;1;WATSYS 1 - ber pH;pH;meting"]
        self.assertEqual(pwb.systeem_punten(tuin3), {
            (1, "recept"): "M430.0N1R1.1V4", (1, "ec"): "M430.0N1R1.1V6", (1, "ec_aanvoer"): "M430.0N1R1.1V8",
            (1, "ec_doel"): "M420.0N1R6.1V2"})
        self.assertEqual(pwb.systeem_punten(tuin1), {
            (1, "ec"): "M430.0N1R1.1V5", (1, "ph"): "M430.0N1R1.1V6", (2, "recept"): "M430.0N1R1.2V3",
            (1, "ph_doel"): "M420.0N1R6.1V3"})


class TestLezen(unittest.TestCase):
    def test_utc_tijdzones_storing_en_halve_regel(self):
        regels = [regel(t(0, 0, 3), "basis", {"A": 1.3, "B": "RUST", "C": 9}),
                  regel(t(13, 20), "meting", {"A": 1.4}),
                  regel(t(14, 0), "storing", {"A": 9.9}),
                  '{"t":"2026-11-09T16:00:00+01:00","soort":"meting","v":{"A":']
        tijdzones = {}
        uit = pwb.lees_jsonl(regels, {"A", "B"}, tijdzones)
        self.assertEqual(uit, {"A": [(t(0, 0, 3), 1.3), (t(13, 20), 1.4)], "B": [(t(0, 0, 3), "RUST")]})
        self.assertEqual(uit["A"][0][0].tzinfo, UTC)
        self.assertEqual(pwb.tijdzone_op(tijdzones, t(12, 0)), CET)

    def test_samenvoegen_en_getallen(self):
        a = {"A": [(t(23, 0, dag=8), 1.0), (t(0, 0, 3), 1.0)]}
        b = {"A": [(t(0, 0, 3), 1.0), (t(1, 0), "????"), (t(2, 0), 1.1)]}
        self.assertEqual(pwb.getallen(pwb.voeg_samen(a, b)["A"]),
                         [(t(23, 0, dag=8), 1.0), (t(0, 0, 3), 1.0), (t(2, 0), 1.1)])


def beurt_kraan_29():
    """De echte beurt van tuin 3, kraan 29, op 9-11-2026 (API: 16:50:00–16:52:26, 1,50 l/m², flow 21,70)."""
    return {
        "M414.0N2R1.29V5": [(t(0, 0, 3), 4812.215), (t(16, 51, 19), 4812.964), (t(16, 52, 39), 4813.718)],
        "M414.0N2R1.29V3": [(t(0, 0, 3), "8:54"), (t(16, 51, 19), "16:50")],
        "M411.0N1R1.29V1": [(t(0, 0, 3), "RUST"), (t(16, 50, 9), "GIET"), (t(16, 52, 39), "RUST")],
        "M412.0N2R1.29V3": [(t(0, 0, 3), 0), (t(16, 51, 19), 324.2), (t(16, 52, 39), 822.4)],
        "M412.0N2R1.29V6": [(t(0, 0, 3), None), (t(16, 51, 19), 21.32), (t(16, 52, 39), 21.53)],
        "M412.0N2R1.29V1": [(t(0, 0, 3), None), (t(16, 51, 19), 1.2), (t(16, 52, 39), 1.4)],
        "M412.0N2R1.29V2": [(t(0, 0, 3), None), (t(16, 51, 19), 6.6), (t(16, 52, 39), 6.5)],
    }


class TestBeurten(unittest.TestCase):
    def test_echte_beurt_kraan_29(self):
        ec = [(t(0, 0, 3), 1.3), (t(16, 52, 19), 1.6)]
        ph = [(t(0, 0, 3), 6.6), (t(16, 50, 59), 6.5), (t(16, 52, 19), 6.3)]
        rijen = pwb.beurten_van_kraan(29, beurt_kraan_29(), ec, ph, {t(0, 0, 3): CET})
        self.assertEqual(len(rijen), 1)
        b = rijen[0]
        self.assertEqual(b["start"], t(16, 50))            # de begintijd die Priva zelf noteert (M414 V3)
        self.assertEqual(b["eind"], t(16, 52, 39))
        self.assertEqual(b["datum"], date(2026, 11, 9))
        self.assertEqual(b["liter_per_m2"], 1.5)
        self.assertEqual(b["flow"], 21.53)                 # eerste beurt van de dag: de flow van "kraan vandaag"
        self.assertAlmostEqual(b["ec"], (139 * 1.3 + 20 * 1.6) / 159, places=3)
        self.assertEqual(b["vaknummer"], 29)

    def test_start_valt_terug_op_giet_als_de_klok_van_de_regelaar_afwijkt(self):
        # De regelaar op zomertijd: "17:50" ligt een uur na de gemeten toename en telt niet.
        reeksen = beurt_kraan_29()
        reeksen["M414.0N2R1.29V3"] = [(t(0, 0, 3), "8:54"), (t(16, 51, 19), "17:50")]
        b = pwb.beurten_van_kraan(29, reeksen, [], [], {t(0, 0, 3): CET})[0]
        self.assertEqual(b["start"], t(16, 50, 9))
        self.assertEqual(b["ec"], 1.4)                     # zonder watersysteem: het cijfer van de kraan

    def test_ec_van_de_kraan_bij_een_sprong_bij_de_start(self):
        ec = [(t(0, 0, 3), 0.8), (t(16, 52, 19), 1.6)]     # watersysteem ≈ 0,9, kraan zegt 1,4
        b = pwb.beurten_van_kraan(29, beurt_kraan_29(), ec, [], {t(0, 0, 3): CET})[0]
        self.assertEqual(b["ec"], 1.4)

    def test_flow_en_ec_van_een_tweede_beurt(self):
        liters = [(t(8, 0), 1000.0), (t(14, 0), 2000.0)]
        flows = [(t(8, 0), 20.0), (t(14, 0), 25.0)]          # draaitijd 50 → 80 (l per m³/u)
        self.assertAlmostEqual(pwb.beurt_flow(liters, flows, t(13, 55), t(13, 59)), 1000 / 30)
        ec = [(t(8, 0), 1.5), (t(14, 0), 1.6)]
        self.assertAlmostEqual(pwb.beurt_uit_dagcijfer(liters, ec, t(13, 55), t(13, 59)), 1.7)
        # Na de dagwissel (teller weer bij 0) is het gewoon het cijfer na de beurt.
        nieuw = [(t(8, 0), 1000.0), (t(23, 1), 0.0), (t(23, 30), 300.0)]
        self.assertEqual(pwb.beurt_flow(nieuw, [(t(23, 30), 22.0)], t(23, 28), t(23, 29)), 22.0)


class TestDagwaarden(unittest.TestCase):
    def test_gift_kwaliteit_en_beurten_zoals_de_api(self):
        reeksen = beurt_kraan_29()
        reeksen.update({
            "EC": [(t(0, 0, 3), 1.3), (t(16, 52, 19), 1.6)],
            "PH": [(t(0, 0, 3), 6.6), (t(16, 52, 19), 6.3)],
            "REC": [(t(0, 0, 3), "????"), (t(16, 50, 59), 2), (t(16, 53, 40), "????")],
        })
        punten = {(1, "ec"): "EC", (1, "ph"): "PH", (1, "recept"): "REC"}
        gift, kwaliteit, beurten = pwb.water_dagwaarden(reeksen, punten, {29}, 1, date(2026, 11, 9),
                                                        date(2026, 11, 9), {t(0, 0, 3): CET})
        self.assertEqual([(g["vaknummer"], g["liter_per_m2"], g["beurten"]) for g in gift], [(29, 1.5, 1)])
        self.assertEqual(len(beurten), 1)
        self.assertEqual(len(kwaliteit), 1)
        self.assertEqual(kwaliteit[0]["recept"], 2)          # '????' = geen recept, telt niet als recept
        self.assertEqual(kwaliteit[0]["ec_gift"], beurten[0]["ec"])
        self.assertEqual(set(kwaliteit[0]) - {"ec_gift", "ph_gift"},
                         set(pw.kwaliteit_rijen({"ec": reeksen["EC"]}, 1, date(2026, 11, 9),
                                                date(2026, 11, 9))[0]))

    def test_benodigde_sleutels(self):
        sleutels = pwb.benodigde_sleutels({(1, "ec"): "EC", (2, "ec"): "EC2"}, {3}, 1)
        self.assertIn("EC", sleutels)
        self.assertNotIn("EC2", sleutels)
        self.assertTrue({"M411.0N1R1.3V1", "M414.0N1R1.3V5", "M414.0N2R1.3V5", "M412.0N1R1.3V6"} <= sleutels)


if __name__ == "__main__":
    unittest.main()

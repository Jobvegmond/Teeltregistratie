"""Tests voor logic/plaagherkenning.py en fotobeoordeling.py (klaarzetten en verwerken, zonder database)."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import fotobeoordeling as fb
from logic import plaagherkenning as ph

UITSLAG = {
    "fototype": "gewas", "fotokwaliteit": "goed", "kwaliteit_tip": "",
    "bevindingen": [
        {"naam": "trips", "soort": "plaag", "zekerheid": "waarschijnlijk", "aantal": "± 5", "stadium": "larven",
         "kenmerken": "zilverige vlekjes"},
        {"naam": "roofmijt", "soort": "nuttig", "zekerheid": "mogelijk", "aantal": "2", "stadium": "",
         "kenmerken": "peervormig, snel"},
    ],
    "samenvatting": "Trips op het blad.", "advies": "Controleer de onderkant van het blad.",
}


def foto(breed, hoog):
    uit = io.BytesIO()
    Image.new("RGB", (breed, hoog), (40, 120, 40)).save(uit, format="PNG")
    return uit.getvalue()


class TestVoorbereiden(unittest.TestCase):
    def test_groot_wordt_verkleind_tot_jpeg(self):
        beeld = Image.open(io.BytesIO(ph.voorbereiden(foto(5000, 3000))))
        self.assertEqual(beeld.format, "JPEG")
        self.assertEqual(max(beeld.size), ph.MAX_PIXELS)

    def test_klein_blijft_even_groot(self):
        self.assertEqual(Image.open(io.BytesIO(ph.voorbereiden(foto(800, 600)))).size, (800, 600))

    def test_geen_afbeelding(self):
        with self.assertRaises(ph.FotoFout):
            ph.voorbereiden(b"geen foto")


class TestControleer(unittest.TestCase):
    def test_goed(self):
        self.assertEqual(ph.controleer(UITSLAG), [])
        self.assertEqual(ph.controleer({**UITSLAG, "bevindingen": []}), [])

    def test_fouten(self):
        fout = copy.deepcopy(UITSLAG)
        del fout["advies"]
        fout["fototype"] = "blad"
        fout["extra"] = 1
        fout["bevindingen"][0]["zekerheid"] = "heel zeker"
        del fout["bevindingen"][1]["kenmerken"]
        tekst = " | ".join(ph.controleer(fout))
        for stuk in ("'advies' ontbreekt", "'fototype'", "onbekend veld 'extra'", "bevinding 1: 'zekerheid'",
                     "bevinding 2: 'kenmerken'"):
            self.assertIn(stuk, tekst)
        self.assertEqual(ph.controleer([]), ["de uitslag is geen JSON-object"])

    def test_opdracht_bevat_schema(self):
        tekst = ph.opdracht()
        self.assertIn("trips", tekst)
        self.assertIn('"bevindingen"', tekst)


class TestTekst(unittest.TestCase):
    def test_kort(self):
        self.assertEqual(ph.kort(UITSLAG), "trips (waarschijnlijk), roofmijt (nuttig)")
        self.assertEqual(ph.kort({"bevindingen": []}), "niets gevonden")

    def test_opmerking(self):
        tekst = ph.opmerking_tekst(UITSLAG)
        self.assertTrue(tekst.startswith("Fotoherkenning: trips (waarschijnlijk), roofmijt (nuttig)."))
        self.assertIn("- trips: waarschijnlijk · ± 5; larven", tekst)
        self.assertIn("- roofmijt: mogelijk · 2", tekst)
        self.assertIn("Advies: Controleer", tekst)


class NepDatabase:
    def __init__(self, fotos):
        self.fotos = {f["id"]: f for f in fotos}
        self.opmerkingen = []

    def maak_foto_tabel(self):
        pass

    def get_fotos(self, status=None, met_foto=True):
        return [f for f in self.fotos.values() if status is None or f["status"] == status]

    def zet_foto_uitslag(self, foto_id, uitslag):
        f = self.fotos.get(foto_id)
        if not f or f["status"] != "wacht":
            return None
        f.update(status="klaar", uitslag=uitslag)
        return f

    def voeg_opmerking_toe(self, teelt_ids, datum, categorie, tekst, gebruiker=None):
        self.opmerkingen.append((teelt_ids, datum, categorie, tekst, gebruiker))

    def ruim_fotos_op(self, dagen):
        return 0


def nep_foto(foto_id, teelt_ids=(), status="wacht"):
    return {"id": foto_id, "teelt_ids": list(teelt_ids), "vakken": ", ".join("12" for _ in teelt_ids),
            "datum": "2026-11-13", "gebruiker": "job", "status": status}


class TestFotobeoordeling(unittest.TestCase):
    def setUp(self):
        self.map = tempfile.TemporaryDirectory()
        self.werk = Path(self.map.name) / "werk"
        self.nas = Path(self.map.name) / "nas" / "fotos"
        self.werk.mkdir()
        self.nas.parent.mkdir()

    def tearDown(self):
        self.map.cleanup()

    def schrijf(self, naam, inhoud):
        (self.werk / naam).write_text(json.dumps(inhoud), encoding="utf-8")

    def test_klaarzetten_alleen_goede_uitslagen(self):
        self.schrijf("wachtrij.json", [{"id": 1}, {"id": 2}, {"id": 3}])
        self.schrijf("1.json", UITSLAG)
        self.schrijf("2.json", {"fototype": "gewas"})                  # onvolledig; 3 ontbreekt
        args = SimpleNamespace(map=str(self.werk), naar=str(self.nas))
        self.assertEqual(fb.klaarzetten(args), 2)
        self.assertEqual([p.name for p in self.nas.iterdir()], ["uitslag-1.json"])

    def test_klaarzetten_zonder_nas(self):
        self.schrijf("wachtrij.json", [])
        args = SimpleNamespace(map=str(self.werk), naar=str(Path(self.map.name) / "weg" / "fotos"))
        self.assertEqual(fb.klaarzetten(args), 1)

    def test_verwerk_zet_uitslag_en_opmerking_eenmalig(self):
        self.nas.mkdir()
        for foto_id in (1, 2, 3):
            (self.nas / f"uitslag-{foto_id}.json").write_text(json.dumps(UITSLAG), encoding="utf-8")
        db = NepDatabase([nep_foto(1, [501]), nep_foto(2), nep_foto(3, [502], status="klaar")])
        args = SimpleNamespace(uitslagen=str(self.nas), droog=False)
        self.assertEqual(fb.verwerk(args, db=db), 2)
        self.assertEqual(db.fotos[1]["status"], "klaar")
        self.assertEqual(len(db.opmerkingen), 1)                      # foto 2 heeft geen vak, 3 was al klaar
        ids, datum, categorie, tekst, gebruiker = db.opmerkingen[0]
        self.assertEqual((ids, datum, categorie, gebruiker), ([501], "2026-11-13", "Ziekte/plagen", "job"))
        self.assertTrue(tekst.startswith("Fotoherkenning: trips"))
        self.assertEqual(fb.verwerk(args, db=db), 0)                  # het uur erna: niets nieuws

    def test_verwerk_droog_schrijft_niets(self):
        self.nas.mkdir()
        (self.nas / "uitslag-1.json").write_text(json.dumps(UITSLAG), encoding="utf-8")
        db = NepDatabase([nep_foto(1, [501])])
        fb.verwerk(SimpleNamespace(uitslagen=str(self.nas), droog=True), db=db)
        self.assertEqual(db.fotos[1]["status"], "wacht")
        self.assertEqual(db.opmerkingen, [])

    def test_argumenten_van_priva_bestanden(self):
        args = fb.lees_argumenten(["--doel", "productie", "--map", "/agro4all", "--droog"])
        self.assertEqual((args.actie, args.doel), ("verwerk", "productie"))


if __name__ == "__main__":
    unittest.main()

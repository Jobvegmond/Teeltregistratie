"""Tests voor logic/plaagherkenning.py: foto voorbereiden, antwoord lezen, opmerkingtekst (zonder echte API)."""
import io
import json
import unittest
from types import SimpleNamespace

from PIL import Image

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


def antwoord(tekst, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="thinking", thinking=""),
                                                      SimpleNamespace(type="text", text=tekst)])


class NepClient:
    def __init__(self, resultaat):
        self.verzoeken = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._resultaat = resultaat

    def _create(self, **kwargs):
        self.verzoeken.append(kwargs)
        return self._resultaat


def foto(breed, hoog, formaat="PNG"):
    uit = io.BytesIO()
    Image.new("RGB", (breed, hoog), (40, 120, 40)).save(uit, format=formaat)
    return uit.getvalue()


class TestVoorbereiden(unittest.TestCase):
    def test_groot_wordt_verkleind_tot_jpeg(self):
        jpeg = ph.voorbereiden(foto(5000, 3000))
        beeld = Image.open(io.BytesIO(jpeg))
        self.assertEqual(beeld.format, "JPEG")
        self.assertEqual(max(beeld.size), ph.MAX_PIXELS)
        self.assertLessEqual(len(jpeg), ph.MAX_BYTES)

    def test_klein_blijft_even_groot(self):
        beeld = Image.open(io.BytesIO(ph.voorbereiden(foto(800, 600))))
        self.assertEqual(beeld.size, (800, 600))

    def test_geen_afbeelding(self):
        with self.assertRaises(ph.AnalyseFout):
            ph.voorbereiden(b"geen foto")


class TestAnalyse(unittest.TestCase):
    def test_verzoek_en_uitslag(self):
        client = NepClient(antwoord(json.dumps(UITSLAG)))
        uit = ph.analyseer(b"jpeg", "onderkant blad, vak 12", client=client)
        self.assertEqual(uit["bevindingen"][0]["naam"], "trips")
        verzoek = client.verzoeken[0]
        self.assertEqual(verzoek["model"], "claude-opus-5-5")
        self.assertEqual(verzoek["output_config"]["format"]["schema"], ph.SCHEMA)
        inhoud = verzoek["messages"][0]["content"]
        self.assertEqual(inhoud[0]["source"]["media_type"], "image/jpeg")
        self.assertIn("vak 12", inhoud[1]["text"])

    def test_weigering(self):
        with self.assertRaises(ph.AnalyseFout):
            ph.lees_antwoord(antwoord("", stop="refusal"))

    def test_afgebroken(self):
        with self.assertRaises(ph.AnalyseFout):
            ph.lees_antwoord(antwoord('{"fototype": "ge', stop="max_tokens"))

    def test_schema_strikt(self):
        self.assertFalse(ph.SCHEMA["additionalProperties"])
        self.assertEqual(set(ph.SCHEMA["required"]), set(ph.SCHEMA["properties"]))
        bevinding = ph.SCHEMA["properties"]["bevindingen"]["items"]
        self.assertEqual(set(bevinding["required"]), set(bevinding["properties"]))


class TestTekst(unittest.TestCase):
    def test_kort(self):
        self.assertEqual(ph.kort(UITSLAG), "trips (waarschijnlijk), roofmijt (nuttig)")
        self.assertEqual(ph.kort({"bevindingen": []}), "niets gevonden")

    def test_opmerking(self):
        tekst = ph.opmerking_tekst([("IMG_1.jpg", UITSLAG)])
        self.assertTrue(tekst.startswith("Fotoherkenning: trips (waarschijnlijk), roofmijt (nuttig)."))
        self.assertIn("- trips: waarschijnlijk · ± 5; larven", tekst)
        self.assertIn("Advies: Controleer", tekst)
        twee = ph.opmerking_tekst([("a.jpg", UITSLAG), ("b.jpg", {"bevindingen": [], "advies": ""})])
        self.assertIn("Foto b.jpg: niets gevonden.", twee)


if __name__ == "__main__":
    unittest.main()

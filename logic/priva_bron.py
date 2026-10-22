"""
Waar de Priva-bestanden van een tuin op de NAS staan (config.PRIVA_BESTANDEN) en de controle dat ze van de
goede regelaar zijn. Gebruikt door priva_klimaat.py, priva_watergift.py en priva_pulsmeters.py.

Tuin 3 (VP9508): `bron live` (minuutbestanden) en `bron historie` (dagbestanden, uurhistorie).
Tuin 1 (Matricaria25): `bron historie/Tuin 1/live` en `bron historie/Tuin 1/historie`.
Tests in tests/test_priva_bron.py.
"""
import json
from pathlib import Path

from config import PRIVA_BESTANDEN


def instellingen(tuin_nummer):
    """De instellingen van een tuin uit config.PRIVA_BESTANDEN, of een ValueError als die er niet zijn."""
    if tuin_nummer not in PRIVA_BESTANDEN:
        raise ValueError(f"geen Priva-bestanden ingesteld voor tuin {tuin_nummer} (config.PRIVA_BESTANDEN)")
    return PRIVA_BESTANDEN[tuin_nummer]


def mappen(map_, tuin_nummer):
    """(live, historie): de map met de minuutbestanden en die met de dagbestanden van een tuin."""
    bron = instellingen(tuin_nummer)
    return Path(map_) / bron["live"], Path(map_) / bron["historie"]


def regelaar_in(tekst):
    """De regelaar ("pcu") uit laatste.json of water-actueel.json, of None als die er niet in staat."""
    try:
        return json.loads(tekst).get("pcu")
    except (ValueError, AttributeError):
        return None


def controleer_regelaar(live, tuin_nummer):
    """
    None als de bestanden in `live` van de regelaar van deze tuin zijn, anders een foutmelding. Zo komen
    de gegevens van de ene tuin nooit bij de andere terecht. Kijkt in laatste.json en water-actueel.json;
    staat de regelaar in geen van beide, dan geldt de map zoals ingesteld.
    """
    verwacht = instellingen(tuin_nummer)["pcu"]
    for naam in ("laatste.json", "water-actueel.json"):
        pad = Path(live) / naam
        if pad.exists():
            gevonden = regelaar_in(pad.read_text(encoding="utf-8"))
            if gevonden and gevonden != verwacht:
                return (f"{pad} is van regelaar {gevonden}, niet van {verwacht} (tuin {tuin_nummer}); "
                        "controleer config.PRIVA_BESTANDEN")
    return None

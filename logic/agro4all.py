"""
Behandelingen (gewasbescherming, biologie, voeding) uit Agro4all, per vak.

Agro4all registreert een bespuiting of inzet als één registratie op een tuin ("Tuin 1", "Tuin 3") met de
vakken (secties) waarop hij is uitgevoerd en de middelen erin. De export (agro4all_import.py leest hem) heeft
per registratie: id, activiteit (CROP_PROTECTION / BIO / FERTILIZER), tuin, start/eind/datum (epoch), methode,
mix, vakken en producten (naam, id, categorie, toelating, rol, hoeveelheid, eenheid, doel).

behandelingen() maakt daar per vak per middel een regel van. Registraties op de hele tuin (zonder vakken, of
op alle vakken van de tuin) vallen weg: die zeggen niets over één teelt. De hoeveelheid is die van de hele
registratie (bijv. 900 ml in 100 l, verdeeld over 4 vakken).

Alleen rekenwerk; tests in tests/test_agro4all.py.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

BRON = "agro4all"
NL = ZoneInfo("Europe/Amsterdam")
# Soort per middel: voeding (meststof), biologie (biostimulant of natuurlijke vijand) of gewasbescherming.
VOEDING_CATEGORIEEN = {"FERTILIZER"}
BIOLOGIE_CATEGORIEEN = {"BIOSTIMULANT", "BENEFICIAL_ORGANISM", "BIO_ADDITIVE", "MACRO_ORGANISM"}


def soort(activiteit, categorie):
    """'voeding', 'biologie' of 'gewasbescherming' voor een middel in een registratie."""
    if categorie in VOEDING_CATEGORIEEN or (activiteit == "FERTILIZER" and not categorie):
        return "voeding"
    if activiteit == "BIO" or categorie in BIOLOGIE_CATEGORIEEN:
        return "biologie"
    return "gewasbescherming"


def datum(registratie):
    """De dag (Nederlandse tijd) waarop de registratie is uitgevoerd: de start, anders de datum."""
    tijd = registratie.get("start") or registratie.get("datum")
    return datetime.fromtimestamp(tijd, NL).date() if tijd else None


def _getal_tekst(waarde):
    return f"{waarde:g}".replace(".", ",")


def behandelingen(export, vakken_per_tuin):
    """
    (middelen, regels) voor database.vervang_behandelingen. vakken_per_tuin: {tuinnummer: aantal vakken}; een
    registratie op al die vakken (of op geen enkel vak) telt niet mee. Middel-code = het Agro4all-product-id.
    """
    middelen, regels = {}, []
    for r in export.get("registraties", []):
        vakken = sorted(set(r.get("vakken") or []))
        dag = datum(r)
        if not vakken or dag is None or len(vakken) >= vakken_per_tuin.get(r.get("tuin"), 10 ** 6):
            continue
        mix = r.get("mix") or {}
        mix_tekst = f"{_getal_tekst(mix['hoeveelheid'])} {mix.get('eenheid') or ''}".strip() \
            if mix.get("hoeveelheid") is not None else None
        for i, p in enumerate(r.get("producten") or []):
            code = p.get("id") or p["naam"]
            middelen.setdefault(code, {"code": code, "naam": p["naam"], "type": soort(r.get("activiteit"),
                                                                                       p.get("categorie")),
                                       "werkzaam": None, "eenheid": p.get("eenheid"),
                                       "doel": p.get("doel")})
            for vak in vakken:
                regels.append({
                    "tuin_nummer": r["tuin"], "vaknummer": int(vak), "datum": dag, "middel_code": code,
                    "dosering": p.get("hoeveelheid"), "eenheid": p.get("eenheid"), "methode": r.get("methode"),
                    "opmerking": "toevoeging" if p.get("rol") == "toevoeging" else None,
                    "extern_id": f"{r['id']}:{vak}:{i}", "registratie": r["id"], "doel": p.get("doel"),
                    "mix": mix_tekst, "aantal_vakken": len(vakken),
                })
    return list(middelen.values()), regels


def overgeslagen(export, vakken_per_tuin):
    """(hele tuin, zonder vakken): aantallen registraties die niet per vak zijn (voor het log)."""
    hele, zonder = 0, 0
    for r in export.get("registraties", []):
        vakken = set(r.get("vakken") or [])
        if not vakken:
            zonder += 1
        elif len(vakken) >= vakken_per_tuin.get(r.get("tuin"), 10 ** 6):
            hele += 1
    return hele, zonder

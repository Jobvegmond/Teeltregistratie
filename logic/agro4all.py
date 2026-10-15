"""
Behandelingen (gewasbescherming, biologie, voeding) uit Agro4all, per vak.

Agro4all registreert een bespuiting of inzet als één registratie op een tuin ("Tuin 1", "Tuin 3") met de
vakken (secties) waarop hij is uitgevoerd en de middelen erin. De export (agro4all_import.py leest hem) heeft
per registratie: id, activiteit (CROP_PROTECTION / BIO / FERTILIZER), tuin, start/eind/datum (epoch), methode,
mix, vakken en producten (naam, id, categorie, toelating, rol, hoeveelheid, eenheid, doel).

behandelingen() maakt daar per vak per middel een regel van. Registraties op de hele tuin (zonder vakken, of
op alle vakken van de tuin) vallen weg: die zeggen niets over één teelt. Agro4all registreert het totaal van
de registratie; dat wordt naar rato van de m² over de vakken verdeeld (bijv. 3600 ml in 400 l over vier
vakken van 540 m² = 900 ml in 100 l per vak). Het totaal blijft erbij (dosering_totaal, mix_totaal).

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


def aandelen(vakken, vak_m2):
    """{vak: deel van het totaal} naar rato van de m² (vak_m2: {vak: m²}); zonder m² gelijk verdeeld."""
    m2 = {v: vak_m2.get(v) or 0 for v in vakken}
    totaal = sum(m2.values())
    return {v: (m2[v] / totaal if totaal else 1 / len(vakken)) for v in vakken}


def _rond(waarde):
    """Een aandeel netjes: vanaf 100 hele getallen (ml, g, stuks), daaronder twee decimalen."""
    if waarde is None:
        return None
    return float(round(waarde)) if abs(waarde) >= 100 else round(waarde, 2)


def behandelingen(export, vakken_per_tuin, vak_m2=None):
    """
    (middelen, regels) voor database.vervang_behandelingen. vakken_per_tuin: {tuinnummer: aantal vakken}; een
    registratie op al die vakken (of op geen enkel vak) telt niet mee. vak_m2: {(tuinnummer, vak): m²} voor de
    verdeling naar rato (zonder: gelijk). Middel-code = het Agro4all-product-id.
    """
    vak_m2 = vak_m2 or {}
    middelen, regels = {}, []
    for r in export.get("registraties", []):
        vakken = sorted(set(r.get("vakken") or []))
        dag = datum(r)
        if not vakken or dag is None or len(vakken) >= vakken_per_tuin.get(r.get("tuin"), 10 ** 6):
            continue
        mix = r.get("mix") or {}
        deel = aandelen(vakken, {v: vak_m2.get((r["tuin"], v)) for v in vakken})

        def mix_tekst(factor):
            if mix.get("hoeveelheid") is None:
                return None
            return f"{_getal_tekst(round(mix['hoeveelheid'] * factor, 1))} {mix.get('eenheid') or ''}".strip()
        for i, p in enumerate(r.get("producten") or []):
            code = p.get("id") or p["naam"]
            middelen.setdefault(code, {"code": code, "naam": p["naam"], "type": soort(r.get("activiteit"),
                                                                                       p.get("categorie")),
                                       "werkzaam": None, "eenheid": p.get("eenheid"),
                                       "doel": p.get("doel")})
            totaal = p.get("hoeveelheid")
            for vak in vakken:
                regels.append({
                    "tuin_nummer": r["tuin"], "vaknummer": int(vak), "datum": dag, "middel_code": code,
                    "dosering": _rond(totaal * deel[vak]) if totaal is not None else None,
                    "dosering_totaal": totaal, "eenheid": p.get("eenheid"), "methode": r.get("methode"),
                    "opmerking": "toevoeging" if p.get("rol") == "toevoeging" else None,
                    "extern_id": f"{r['id']}:{vak}:{i}", "registratie": r["id"], "doel": p.get("doel"),
                    "mix": mix_tekst(deel[vak]), "mix_totaal": mix_tekst(1), "aantal_vakken": len(vakken),
                })
    return list(middelen.values()), regels


def _nummer(naam):
    """Het getal in een naam ("Tuin 3" → 3, "Vak 12" → 12), of None."""
    cijfers = "".join(c if c.isdigit() else " " for c in naam or "").split()
    return int(cijfers[0]) if cijfers else None


def _plaagnaam(plaag):
    """De Nederlandse naam van een plaag, anders de eerste naam."""
    namen = (plaag or {}).get("names") or []
    return next((n["name"] for n in namen if n.get("language") == "nl"), namen[0]["name"] if namen else None)


def export_uit_api(velden, registraties, secties_per_registratie, methodes, opgehaald):
    """
    De export (zie bovenaan) uit wat integrations.agro4all.ophalen() teruggeeft: de velden met hun secties,
    de registraties zoals Agro4all ze geeft, per registratie-id de sectie-ids waarop hij staat, en
    toepassingswijze-id → naam.
    """
    sectie_vak = {s["id"]: _nummer(s["name"]) for v in velden for s in v.get("sections", [])}
    uit = []
    for r in registraties:
        moment = r.get("performedAt") or {}
        producten = []
        for sleutel, rol in (("appliedProducts", "product"), ("appliedAdditives", "toevoeging")):
            for toegepast in r.get(sleutel) or []:
                product, dosering = toegepast["product"], toegepast.get("dosage") or {}
                producten.append({"naam": product["name"], "id": product["id"],
                                  "categorie": product.get("productCategory"),
                                  "toelating": (product.get("registrationNumber") or {}).get("nl"), "rol": rol,
                                  "hoeveelheid": dosering.get("amount"), "eenheid": dosering.get("unit"),
                                  "doel": _plaagnaam(toegepast.get("pest"))})
        mix = r.get("mix")
        uit.append({
            "id": r["id"], "activiteit": r.get("activityType"), "tuin": _nummer((r.get("organizationField") or {})
                                                                               .get("name")),
            "start": moment.get("startTime"), "eind": moment.get("endTime"), "datum": moment.get("date"),
            "methode": methodes.get(r.get("applicationMannerId")),
            "mix": {"hoeveelheid": mix["amount"], "eenheid": mix["unit"]} if mix else None,
            "vakken": sorted({sectie_vak[s] for s in secties_per_registratie.get(r["id"], ()) if s in sectie_vak}),
            "producten": producten,
        })
    return {"opgehaald": opgehaald, "bron": BRON, "registraties": uit}


def moment(registratie):
    """Het tijdstip (epoch) van een registratie: de start, anders de datum; 0 als er geen is."""
    return registratie.get("start") or registratie.get("datum") or 0


def samenvoegen(oud, nieuw, van, opgehaald):
    """
    De export bijwerken met een deelexport vanaf `van` (epoch): alle registraties van vóór `van` uit de oude
    export blijven, alles vanaf `van` komt uit de nieuwe (wat daar niet meer in staat, is in Agro4all
    verwijderd). Een registratie die in beide staat (bijv. van datum veranderd) telt één keer: de nieuwe.
    """
    nieuwe = list((nieuw or {}).get("registraties", []))
    ids = {r["id"] for r in nieuwe}
    behouden = [r for r in (oud or {}).get("registraties", []) if moment(r) < van and r["id"] not in ids]
    alle = sorted(behouden + nieuwe, key=lambda r: (moment(r), r["id"]))
    return {"opgehaald": opgehaald, "bron": BRON, "registraties": alle}


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

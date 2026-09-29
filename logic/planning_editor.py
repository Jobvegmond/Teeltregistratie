"""
De concept-planningen als één bewerkbare tabel (Planning): welke wijzigingen
er in één keer doorgevoerd moeten worden. Alleen rekenwerk; de app voert ze
uit met de databasefuncties. Tests in tests/test_planning_editor.py.

Per concept (op id): startdatum, aantal planten, ✅ bevestigen, 🗑️ verwijderen.
- ✅ én 🗑️ aangevinkt: tegenstrijdig, er gebeurt niets met dat concept;
- 🗑️: verwijderen (een gewijzigde datum telt dan niet);
- een andere startdatum: wijzigen (vóór het bevestigen, zodat het vak op de
  nieuwe datum start);
- ✅: bevestigen met het aantal planten uit de tabel.
Een ander aantal planten zonder ✅ wordt niet bewaard: dat getal is alleen de
voorinvulling voor het bevestigen.
"""


def wijzigingen(origineel, bewerkt):
    """
    origineel / bewerkt: {id: {"start": date, "planten": int|None, "bevestigen": bool, "verwijderen": bool}}.
    Geeft {"gewijzigd": [(id, start)], "bevestigd": [(id, planten)], "verwijderd": [id],
    "conflict": [id]} in de volgorde van de ids.
    """
    uit = {"gewijzigd": [], "bevestigd": [], "verwijderd": [], "conflict": []}
    for id_, nieuw in bewerkt.items():
        oud = origineel.get(id_)
        if oud is None:
            continue
        if nieuw.get("bevestigen") and nieuw.get("verwijderen"):
            uit["conflict"].append(id_)
            continue
        if nieuw.get("verwijderen"):
            uit["verwijderd"].append(id_)
            continue
        if nieuw.get("start") and nieuw["start"] != oud["start"]:
            uit["gewijzigd"].append((id_, nieuw["start"]))
        if nieuw.get("bevestigen"):
            planten = nieuw.get("planten")
            uit["bevestigd"].append((id_, int(planten) if planten else None))
    return uit


def samenvatting(w):
    """"2 gewijzigd, 1 bevestigd, 0 verwijderd" (plus de conflicten als die er zijn)."""
    tekst = f"{len(w['gewijzigd'])} gewijzigd, {len(w['bevestigd'])} bevestigd, {len(w['verwijderd'])} verwijderd"
    if w["conflict"]:
        tekst += f"; {len(w['conflict'])} overgeslagen (zowel ✅ als 🗑️ aangevinkt)"
    return tekst


def heeft_wijzigingen(w):
    return any(w[k] for k in ("gewijzigd", "bevestigd", "verwijderd", "conflict"))

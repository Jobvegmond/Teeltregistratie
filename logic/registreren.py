"""
Rekenwerk voor het tabblad Registreren: de lopende vakken van een tuin (met wat er al is en wat het teeltmodel
verwacht), de waarde per vak bij het opslaan (een eigen waarde in de tabel, anders de waarde voor alle
aangevinkte vakken), wat er nog te doen is en de laatste registraties uit het wijzigingenlog.
Geen Streamlit; tests in tests/test_registreren.py.
"""
import re
from datetime import timedelta

from logic.vakstatus import als_datum


def _getal(waarde):
    """Een ingevulde waarde, of None bij leeg, NaN of 0 (0 betekent bij deze velden: niet ingevuld). Tekst
    (bijv. de rijpheid "1-3") blijft tekst."""
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, str):
        return waarde.strip() or None
    return float(waarde) or None


def lopende_vakken(teelten, tuin_id, vandaag, stook=None):
    """
    De lopende teelten van één tuin (geplant, nog niet afgerond), op plantdatum en vak, als dicts met:
    id, vak, afdeling, code, plantweek (ISO), geplant, florgib (datum), lengte_half, lengte_eind,
    planten, emmers, uitval (%), florgib_verwacht en prognose (uit `stook`, het teeltmodel).
    `teelten`: records zoals get_vakstatus_data()["teelten"].
    """
    stook = stook or {}
    uit = []
    for t in teelten:
        start = als_datum(t["datum_teelt_start"])
        if t["tuin_id"] != tuin_id or not start or start > vandaag or als_datum(t["datum_oogst"]):
            continue
        u = stook.get(int(t["id"])) or {}
        planten, emmers = _getal(t.get("aantal_planten")), _getal(t.get("emmers")) or 0
        uit.append({
            "id": int(t["id"]), "vak": int(t["vaknummer"]), "afdeling": t.get("afdeling"), "code": t.get("code"),
            "plantweek": start.isocalendar()[1], "geplant": start, "florgib": als_datum(t.get("datum_half")),
            "lengte_half": _getal(t.get("lengte_half")), "lengte_eind": _getal(t.get("lengte_eind")),
            "planten": planten, "emmers": emmers,
            "uitval": (planten - emmers * 100) / planten * 100 if planten and emmers else None,
            "florgib_verwacht": u.get("florgib_verwacht"), "prognose": u.get("prognose")})
    return sorted(uit, key=lambda r: (r["geplant"], r["vak"]))


def te_registreren(regels, velden, gemeen):
    """
    De vakken die meedoen bij het opslaan, als [(id, vak, {veld: waarde})]. Een vak doet mee als het is
    aangevinkt ("Kies") of als er in zijn regel een waarde is ingevuld. Per veld telt de eigen waarde in de
    regel; is die leeg, dan de waarde voor alle aangevinkte vakken (`gemeen`, {veld: waarde}).
    `regels`: dicts met "id", "vak", "Kies" en de velden (zoals de tabel ze teruggeeft).
    """
    uit = []
    for r in regels:
        eigen = {v: _getal(r.get(v)) for v in velden}
        if not r.get("Kies") and not any(w is not None for w in eigen.values()):
            continue
        uit.append((int(r["id"]), int(r["vak"]),
                    {v: eigen[v] if eigen[v] is not None else _getal(gemeen.get(v)) for v in velden}))
    return uit


def zonder(registraties, veld):
    """De vakken (nummers) waarvoor `veld` na het aanvullen nog leeg is."""
    return [vak for _id, vak, waarden in registraties if waarden.get(veld) is None]


def nog_te_doen(soort, vakken, vandaag, vooruit=3):
    """
    Wat er nu (of binnen `vooruit` dagen) te registreren is, als [(vak, tekst)], het dringendste eerst:
    - "florgib": vakken zonder Florgib waarvan het teeltmodel de Florgib verwacht;
    - "emmers": vakken in de oogst (al emmers) of met een prognose-oogst;
    - "lengte": vakken in de oogst zonder oogstlengte.
    """
    grens = vandaag + timedelta(days=vooruit)
    if soort == "florgib":
        rijen = sorted((r for r in vakken if r["lengte_half"] is None and r["florgib_verwacht"]
                        and r["florgib_verwacht"] <= grens), key=lambda r: (r["florgib_verwacht"], r["vak"]))
        return [(r["vak"], f"verwacht {r['florgib_verwacht']:%d-%m}" + _dagen(r["florgib_verwacht"], vandaag))
                for r in rijen]
    if soort == "emmers":
        bezig = sorted((r for r in vakken if r["emmers"]), key=lambda r: r["vak"])
        verwacht = sorted((r for r in vakken if not r["emmers"] and r["prognose"] and r["prognose"] <= grens),
                          key=lambda r: (r["prognose"], r["vak"]))
        return ([(r["vak"], f"in de oogst, {r['emmers']:g} emmers") for r in bezig]
                + [(r["vak"], f"prognose {r['prognose']:%d-%m}" + _dagen(r["prognose"], vandaag)) for r in verwacht])
    if soort == "lengte":
        return [(r["vak"], f"in de oogst ({r['emmers']:g} emmers), nog geen lengte")
                for r in sorted(vakken, key=lambda r: r["vak"]) if r["emmers"] and r["lengte_eind"] is None]
    return []


def _dagen(dag, vandaag):
    verschil = (dag - vandaag).days
    if verschil == 0:
        return " (vandaag)"
    return f" (over {verschil} d)" if verschil > 0 else f" ({-verschil} d over tijd)"


# Welke logregels bij welke soort registratie horen (omschrijving of entiteit in het wijzigingenlog).
_LOG = {
    "florgib": lambda actie, entiteit, tekst: tekst.startswith("Florgib lengte"),
    "emmers": lambda actie, entiteit, tekst: entiteit == "oogstregistratie" and actie == "aangemaakt"
    or tekst.startswith("Vak afgerond"),
    "lengte": lambda actie, entiteit, tekst: tekst.startswith("Oogstgegevens geregistreerd"),
    "opmerking": lambda actie, entiteit, tekst: entiteit == "opmerking" and actie == "aangemaakt",
}


def laatste_registraties(log, soort, vak_van, limiet=8):
    """
    De laatste registraties van één soort in deze tuin, nieuwste eerst, als dicts: tijdstip, gebruiker, vak,
    omschrijving. `log`: rijen (tijdstip, gebruiker, actie, entiteit, entiteit_id, omschrijving);
    `vak_van`: {teelt_id: vak} van de tuin (een emmerregel noemt de teelt in de omschrijving).
    """
    past = _LOG.get(soort)
    uit = []
    for tijdstip, gebruiker, actie, entiteit, entiteit_id, tekst in log:
        tekst = tekst or ""
        if not past or not past(actie, entiteit, tekst):
            continue
        teelt = re.search(r"voor teelt (\d+)", tekst) if entiteit == "oogstregistratie" else None
        try:                                   # entiteit_id staat als tekst in het log
            teelt_id = int(teelt.group(1)) if teelt else int(entiteit_id)
        except (TypeError, ValueError):
            continue
        if teelt_id not in vak_van:
            continue
        uit.append({"tijdstip": tijdstip, "gebruiker": gebruiker, "vak": vak_van[teelt_id],
                    "omschrijving": re.sub(r" voor teelt \d+", "", tekst)})
        if len(uit) == limiet:
            break
    return uit

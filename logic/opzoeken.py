"""
Opzoeken: een teelt (alle vakken uit één plantweek) of één vak met alle
informatie die er is. Alleen rekenwerk: zoeken op code of vaknummer, de
periode per vak, rijen uit dag-tabellen bij het juiste vak zoeken en de
samenvatting. Ophalen in database.get_opzoek_gegevens, tekenen in app.py.
Tests in tests/test_opzoeken.py.
"""
from datetime import date


def _d(waarde):
    if waarde is None or waarde != waarde or waarde == "":   # NaN != NaN
        return None
    if hasattr(waarde, "year"):
        return waarde.date() if hasattr(waarde, "date") else waarde
    return date.fromisoformat(str(waarde)[:10])


def zoek(vakken, tekst):
    """
    Het vak bij een zoektekst: een teeltcode (exact) of een vaknummer (de laatst
    geplante teelt in dat vak). `vakken`: dicts met id, tuin_id, vak, code, start.
    Geeft (vak of None, melding of None); een vaknummer dat in meer tuinen
    voorkomt geeft een melding in plaats van een vak.
    """
    tekst = (tekst or "").strip()
    if not tekst:
        return None, None
    op_code = [v for v in vakken if str(v.get("code") or "") == tekst]
    if op_code:
        return op_code[0], None
    if tekst.isdigit() and len(tekst) <= 2:
        in_vak = [v for v in vakken if int(v["vak"]) == int(tekst)]
        if len({v["tuin_id"] for v in in_vak}) > 1:
            return None, f"Vak {tekst} bestaat in beide tuinen: kies bovenaan Tuin 1 of Tuin 3, of zoek op de code."
        if in_vak:
            return max(in_vak, key=lambda v: _d(v["start"])), None
    return None, f"Geen vak gevonden bij '{tekst}'. Zoek op een teeltcode (bijv. 2634301) of een vaknummer."


def perioden(vakken, vandaag):
    """{teelt_id: (tuin_id, vak, afdeling, start, eind)}: van planten tot de oogst, of tot vandaag als het nog loopt."""
    uit = {}
    for v in vakken:
        start = _d(v["start"])
        eind = _d(v.get("oogstdatum")) or vandaag
        uit[int(v["id"])] = (v["tuin_id"], int(v["vak"]), v.get("afdeling"), start, max(eind, start))
    return uit


def bij_vak(rijen, perioden_, codes):
    """
    Rijen van een tabel per vak per dag (tuin_id, vak, datum) die binnen de
    periode van één van de vakken vallen, met de code van dat vak erbij.
    """
    uit = []
    for r in rijen:
        dag = _d(r["datum"])
        for teelt_id, (tuin_id, vak, _afd, start, eind) in perioden_.items():
            if r["tuin_id"] == tuin_id and int(r["vak"]) == vak and start <= dag <= eind:
                uit.append({**r, "code": codes.get(teelt_id)})
                break
    return uit


def bij_afdeling(rijen, perioden_):
    """Rijen per afdeling per dag (tuin_id, afdeling, datum) binnen de periode van een vak in die afdeling."""
    vensters = {}
    for tuin_id, _vak, afd, start, eind in perioden_.values():
        if afd is not None:
            vensters.setdefault((tuin_id, int(afd)), []).append((start, eind))
    return [r for r in rijen
            if any(s <= _d(r["datum"]) <= e for s, e in vensters.get((r["tuin_id"], int(r["afdeling"])), []))]


def bij_tuin(rijen, perioden_):
    """Rijen per tuin per dag (tuin_id, datum) binnen de periode van een van de vakken in die tuin."""
    vensters = {}
    for tuin_id, _vak, _afd, start, eind in perioden_.values():
        vensters.setdefault(tuin_id, []).append((start, eind))
    return [r for r in rijen if any(s <= _d(r["datum"]) <= e for s, e in vensters.get(r["tuin_id"], []))]


def samenvatting(vakken, emmers):
    """
    Kengetallen van een groep vakken (één vak of een hele teelt): aantal, lopend,
    plantdatum (eerste/laatste), rassen, planten, emmers, stelen, uitval en de
    eerste/laatste Florgib en oogst. `emmers`: rijen met teelt_id en emmers.
    """
    starts = [_d(v["start"]) for v in vakken]
    oogsten = [_d(v.get("oogstdatum")) for v in vakken if _d(v.get("oogstdatum"))]
    florgibs = [_d(v.get("florgib")) for v in vakken if _d(v.get("florgib"))]
    planten = [v.get("planten") for v in vakken if v.get("planten") == v.get("planten") and v.get("planten")]
    ids = {int(v["id"]) for v in vakken}
    n_emmers = sum(float(e["emmers"] or 0) for e in emmers if int(e["teelt_id"]) in ids)
    # Uitval alleen over de vakken die klaar zijn en een plantaantal hebben.
    klaar = [v for v in vakken if _d(v.get("oogstdatum")) and v.get("planten") == v.get("planten") and v.get("planten")]
    klaar_ids = {int(v["id"]) for v in klaar}
    klaar_planten = sum(float(v["planten"]) for v in klaar)
    klaar_emmers = sum(float(e["emmers"] or 0) for e in emmers if int(e["teelt_id"]) in klaar_ids)
    return {
        "vakken": len(vakken), "lopend": len(vakken) - len(oogsten),
        "eerste_start": min(starts) if starts else None, "laatste_start": max(starts) if starts else None,
        "rassen": sorted({v.get("ras") or "Cameron" for v in vakken}),
        "planten": sum(float(p) for p in planten) if planten else None,
        "emmers": n_emmers, "stelen": n_emmers * 100,
        "uitval": (klaar_planten - klaar_emmers * 100) / klaar_planten * 100 if klaar_planten and klaar_emmers else None,
        "eerste_florgib": min(florgibs) if florgibs else None, "laatste_florgib": max(florgibs) if florgibs else None,
        "eerste_oogst": min(oogsten) if oogsten else None, "laatste_oogst": max(oogsten) if oogsten else None,
    }

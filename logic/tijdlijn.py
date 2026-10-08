"""
Tijdlijn per vak (proef): de vakkenmatrix en de strokenplanning in één beeld.

Per vak de stukken op de tijdlijn: afgeronde teelten, de lopende teelt (tot
vandaag in de statuskleur van de vakkenmatrix, daarna licht tot de prognose),
bevestigde teelten die nog moeten beginnen en concepten. Daarnaast de
overlap met de vorige ronde in een vak en het aantal vakken dat per week
geoogst wordt. Alleen rekenwerk; tekenen gebeurt in app.py.
"""
from datetime import date, timedelta

from logic import weken as wg


def _datum(waarde):
    """date uit een date of 'YYYY-MM-DD'; None bij leeg."""
    if waarde is None or waarde != waarde or waarde == "":   # NaN != NaN
        return None
    if hasattr(waarde, "year"):
        return waarde.date() if hasattr(waarde, "date") else waarde
    return date.fromisoformat(str(waarde)[:10])


def stukken(teelten, statussen, concepten, vandaag, plan_van):
    """
    De stukken van één tuin op de tijdlijn, als dicts met: vak, soort, start, eind
    (en per soort extra velden). Soorten:
      afgerond  — start → oogst
      lopend    — start → vandaag, met `klasse` (statuskleur), `teelt_id`
      prognose  — vandaag → prognose (of plan) van een lopende teelt
      gepland   — bevestigde teelt die nog moet beginnen: start → plan
      concept   — concept-planning: start → verwachte oogst, met `concept_id`
    `teelten`: records van één tuin; `statussen`: {vak: status} van de lopende
    teelten (zoals _nu_tuin); `concepten`: (id, vak, start, duur, eind, notitie);
    `plan_van(start)` = de plan-oogstdatum.
    """
    uit = []
    lopende_ids = {int(s["teelt"]["id"]) for s in statussen.values()}
    for t in teelten:
        start, oogst = _datum(t["datum_teelt_start"]), _datum(t["datum_oogst"])
        basis = {"vak": int(t["vaknummer"]), "teelt_id": int(t["id"]), "code": t.get("code"), "ras": t.get("ras")}
        if oogst:
            uit.append({**basis, "soort": "afgerond", "start": start, "eind": oogst})
        elif start > vandaag:
            uit.append({**basis, "soort": "gepland", "start": start, "eind": plan_van(start) or start + timedelta(weeks=8)})
        elif int(t["id"]) not in lopende_ids:
            # Lopend, maar niet de jongste teelt in het vak (een oudere die nooit is afgesloten).
            uit.append({**basis, "soort": "afgerond", "start": start, "eind": vandaag, "open": True})
    for s in statussen.values():
        t = s["teelt"]
        basis = {"vak": int(t["vaknummer"]), "teelt_id": int(t["id"]), "code": t.get("code"), "ras": t.get("ras"),
                 "klasse": s["klasse"]}
        uit.append({**basis, "soort": "lopend", "start": s["start"], "eind": vandaag})
        einde = s.get("prognose") or s.get("plan")
        if einde and einde > vandaag:
            uit.append({**basis, "soort": "prognose", "start": vandaag, "eind": einde})
    for concept_id, vak, start, _duur, eind, _notitie in concepten:
        start = _datum(start)
        eind = _datum(eind) or start + timedelta(weeks=8)
        uit.append({"vak": int(vak), "soort": "concept", "concept_id": int(concept_id), "start": start, "eind": eind})
    uit.sort(key=lambda r: (r["vak"], r["start"]))
    return uit


def _rondes(stukken_lijst):
    """{vak: [(start, eind, concept_id)]}: elke teelt of concept één ronde; een lopende teelt tot zijn prognose."""
    rondes = {}
    for s in stukken_lijst:
        if s["soort"] == "prognose":
            continue
        eind = s["eind"]
        if s["soort"] == "lopend":
            eind = max([eind] + [p["eind"] for p in stukken_lijst
                                 if p["soort"] == "prognose" and p.get("teelt_id") == s.get("teelt_id")])
        rondes.setdefault(s["vak"], []).append((s["start"], eind, s.get("concept_id")))
    return rondes


def overlap(stukken_lijst):
    """
    De dagen waarop een teelt of concept begint vóór de vorige ronde in dat vak
    klaar is: [{vak, start, eind}]. De lopende teelt telt met zijn prognose mee.
    """
    uit = []
    for vak, lijst in _rondes(stukken_lijst).items():
        eerdere = []
        for start, eind, _ in sorted(lijst, key=lambda r: r[:2]):
            later = [e for e in eerdere if start < e]
            if later:
                uit.append({"vak": vak, "start": start, "eind": min(eind, max(later))})
            eerdere.append(eind)
    return uit


def overlappend(stukken_lijst, vak, start, eind, behalve_concept=None):
    """
    De rondes in het vak die overlappen met een nieuwe of verschoven planting
    van `start` tot `eind`: [(begin, eind)], op begin. Een ronde die eerder
    begint loopt dan nog na `start`; een latere begint al vóór `eind`. Het
    concept zelf (`behalve_concept`) telt niet mee.
    """
    return sorted((begin, einde) for begin, einde, concept_id in _rondes(stukken_lijst).get(vak, [])
                  if begin < eind and einde > start
                  and (behalve_concept is None or concept_id != behalve_concept))


def oogst_per_week(stukken_lijst, statussen, van, tot):
    """
    {zondag van de week: aantal vakken} met een (verwachte) oogst in [van, tot]:
    afgeronde teelten op hun oogstdag, lopende op de prognose (anders plan),
    geplande en concepten op hun plan-oogst.
    """
    dagen = [s["eind"] for s in stukken_lijst if s["soort"] in ("afgerond", "gepland", "concept") and not s.get("open")]
    for s in statussen.values():
        dagen.append(s.get("prognose") or s.get("plan"))
    uit = {}
    for d in dagen:
        if d and van <= d <= tot:
            zo = wg.week_begin(d)
            uit[zo] = uit.get(zo, 0) + 1
    return uit

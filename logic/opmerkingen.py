"""
Opmerkingen per vak zoeken en filteren (pagina Opmerkingen, Teeltvergelijking
en Tuin vergelijking). Alleen rekenwerk; tests in tests/test_opmerkingen.py.

Een opmerking is een dict uit database.get_alle_opmerkingen(): id, teelt_id,
datum, categorie, tekst, gebruiker, tuin_id, afdeling, vaknummer, code, start.
"""
from datetime import date, datetime


def _datum(waarde):
    if waarde is None or waarde != waarde:
        return None
    if isinstance(waarde, datetime):
        return waarde.date()
    if isinstance(waarde, date):
        return waarde
    return datetime.strptime(str(waarde)[:10], "%Y-%m-%d").date()


def teelt_van(opmerking):
    """De teelt (plantweek) van het vak: (isojaar, week)."""
    jaar, week, _ = _datum(opmerking["start"]).isocalendar()
    return jaar, week


def filter_opmerkingen(opmerkingen, tuinen=None, teelten=None, vakken=None, van=None, tot=None,
                       categorieen=None, zoek=None, teelt_ids=None):
    """
    De opmerkingen die aan alle opgegeven filters voldoen (None of leeg = geen filter),
    op datum van oud naar nieuw:
    - tuinen: tuin_ids; teelten: plantweken (isojaar, week); vakken: vaknummers;
    - van/tot: datum van de opmerking, beide inclusief;
    - categorieen; zoek: stukje tekst in de opmerking of de code (hoofdletters maken niet uit);
    - teelt_ids: alleen deze vakken (teelt-ids).
    """
    zoek = (zoek or "").strip().lower()
    uit = []
    for o in opmerkingen:
        d = _datum(o["datum"])
        if tuinen and o["tuin_id"] not in tuinen:
            continue
        if teelten and teelt_van(o) not in teelten:
            continue
        if vakken and o["vaknummer"] not in vakken:
            continue
        if van and d < van or tot and d > tot:
            continue
        if categorieen and o["categorie"] not in categorieen:
            continue
        if teelt_ids is not None and o["teelt_id"] not in teelt_ids:
            continue
        if zoek and zoek not in (o["tekst"] or "").lower() and zoek not in (o["code"] or "").lower():
            continue
        uit.append(o)
    return sorted(uit, key=lambda o: (_datum(o["datum"]), o["tuin_id"], o["vaknummer"], o["id"]))

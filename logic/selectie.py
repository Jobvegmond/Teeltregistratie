"""
Een vak of teelt kiezen met losse keuzevelden (tuin, vak, week, jaar) in plaats
van één lange lijst. Elk veld toont alleen wat bij de eerdere keuzes bestaat.
Alleen rekenwerk; tests in tests/test_selectie.py.

Een item is een dict met tuin_id, vak, jaar en week (en verder wat de
aanroeper nodig heeft, bijv. id).
"""


def _past(item, tuin=None, vak=None, week=None, jaar=None):
    return ((tuin is None or item["tuin_id"] == tuin) and (vak is None or item["vak"] == vak)
            and (week is None or item["week"] == week) and (jaar is None or item["jaar"] == jaar))


def vakken(items, tuin=None):
    """Vaknummers (laag naar hoog) in de gekozen tuin."""
    return sorted({i["vak"] for i in items if _past(i, tuin) and i["vak"] is not None})


def weken(items, tuin=None, vak=None):
    """Plantweken (laag naar hoog) bij de gekozen tuin en het gekozen vak."""
    return sorted({i["week"] for i in items if _past(i, tuin, vak)})


def jaren(items, week, tuin=None, vak=None):
    """Jaren (laag naar hoog) waarin de gekozen week bij tuin en vak voorkomt."""
    return sorted({i["jaar"] for i in items if _past(i, tuin, vak, week)})


def laatste(items, tuin=None, vak=None):
    """Het meest recente item (op jaar en week) bij tuin en vak, of None."""
    kandidaten = [i for i in items if _past(i, tuin, vak)]
    return max(kandidaten, key=lambda i: (i["jaar"], i["week"])) if kandidaten else None


def gekozen(items, tuin=None, vak=None, week=None, jaar=None):
    """De items die bij alle keuzes passen."""
    return [i for i in items if _past(i, tuin, vak, week, jaar)]


def geldig(waarde, opties, standaard):
    """`waarde` als die tussen de opties staat, anders `standaard`."""
    return waarde if waarde in opties else standaard

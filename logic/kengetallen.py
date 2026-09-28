"""
Vergelijkingstabel op "Beide tuinen": wat per kengetal "beter" is, hoe een
verschil gekleurd wordt, welke tuin per regel de beste is en wanneer het
totaal van beide tuinen met een eerdere periode te vergelijken is. Alleen
rekenwerk; tests in tests/test_kengetallen.py.
"""

# +1 = hoger is beter, −1 = lager is beter. Wat hier niet staat is neutraal
# (grijs, geen beste tuin): teeltduur, klimaat, lengtefactor, bezetting.
RICHTING = {"stelen": 1, "stelen_m2": 1, "gewicht": 1, "lengte": 1,
            "uitval": -1, "water": -1, "warmte": -1, "gas": -1}


def verschil_klasse(verschil, richting, decimalen=0):
    """"beter", "slechter" of "neutraal" (ook bij een afgerond verschil van 0); "leeg" zonder verschil."""
    if verschil is None:
        return "leeg"
    if not richting or round(verschil, decimalen) == 0:
        return "neutraal"
    return "beter" if verschil * richting > 0 else "slechter"


def beste(waarden, richting, decimalen=0):
    """
    waarden: {naam: waarde of None}. De naam met de beste waarde, als er
    minstens twee waarden zijn, "beter" gedefinieerd is en er na afronden
    precies één de beste is; anders None.
    """
    if not richting:
        return None
    bekend = {naam: round(w, decimalen) for naam, w in waarden.items() if w is not None}
    if len(bekend) < 2:
        return None
    top = max(bekend.values()) if richting > 0 else min(bekend.values())
    winnaars = [naam for naam, w in bekend.items() if w == top]
    return winnaars[0] if len(winnaars) == 1 else None


def bijdragers(per_tuin, sleutel):
    """De tuinen (namen) met een waarde voor dit kengetal: {naam: samenvatting} → frozenset."""
    return frozenset(naam for naam, s in per_tuin.items() if s.get(sleutel) is not None)


def totaal_vergelijkbaar(nu_per_tuin, toen_per_tuin, sleutel, tuin_ok):
    """
    Is het totaal van dit kengetal te vergelijken met de eerdere periode? Alleen
    als precies dezelfde tuinen er toen en nu aan bijdragen, en elke tuin zelf
    vergelijkbaar is (tuin_ok[naam]). Anders zou bijv. beide tuinen nu tegen
    alleen tuin 3 vorig jaar staan.
    """
    nu = bijdragers(nu_per_tuin, sleutel)
    return bool(nu) and nu == bijdragers(toen_per_tuin, sleutel) and all(tuin_ok.get(n) for n in nu)

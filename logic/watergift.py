"""
Watergift per vak en EC/pH per watersysteem: koppelen en samenvatten voor de
pagina Watergift. Alleen rekenwerk; tests in tests/test_watergift.py.
"""


def watersysteem_van_vak(watersystemen, tuin_nummer, vak):
    """Het watersysteem dat dit vak water geeft (config.WATERSYSTEMEN), of None."""
    for systeem, vakken in sorted(watersystemen.get(tuin_nummer, {}).items()):
        if vakken is None or vak in vakken:
            return systeem
    return None


def vakken_van_watersysteem(watersystemen, tuin_nummer, systeem, alle_vakken):
    """De vakken (laag naar hoog) die water krijgen van dit watersysteem; `alle_vakken` = de vakken van de tuin."""
    vakken = watersystemen.get(tuin_nummer, {}).get(systeem, ())
    if vakken is None:
        return sorted(alle_vakken)
    return sorted(v for v in vakken if v in set(alle_vakken))

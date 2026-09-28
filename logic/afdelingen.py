"""Afdelingen in teeltvolgorde (per tuin ingesteld in config.AFDELING_VOLGORDE)."""
from config import AFDELING_VOLGORDE


def sorteer_afdelingen(afdelingen, tuin_nummer):
    """
    De afdelingen in de teeltvolgorde van deze tuin. Afdelingen die niet in de
    instelling staan komen er in oplopende volgorde achter; dubbele vallen weg.
    """
    volgorde = AFDELING_VOLGORDE.get(tuin_nummer, ())
    positie = {afd: i for i, afd in enumerate(volgorde)}
    uniek = {int(a) for a in afdelingen if a is not None and a == a}
    return sorted(uniek, key=lambda a: (positie.get(a, len(volgorde)), a))

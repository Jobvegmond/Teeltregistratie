"""
De lichtlijn: de etmaaltemperatuur waarop gestookt wordt bij een gegeven
lichtsom binnen. Eén centrale functie; de getallen staan in config.py.

    T_ideaal = LICHTLIJN_BASIS + LICHTLIJN_FACTOR × lichtsom binnen (J/cm² per dag)

Boven de lichtlijn stoken versnelt de teelt (maar kost gewicht), eronder
vertraagt hij. De afwijking T − T_ideaal is daarom de maat voor de stooklijn.
Werkt op een getal, een numpy-array en een pandas-Series.
"""
from config import LICHTLIJN_BASIS, LICHTLIJN_FACTOR


def t_ideaal(lichtsom_binnen):
    """Ideale etmaaltemperatuur (°C) bij de lichtsom binnen van die dag (J/cm² per dag)."""
    if lichtsom_binnen is None:
        return None
    return LICHTLIJN_BASIS + LICHTLIJN_FACTOR * lichtsom_binnen


def afwijking(etmaaltemperatuur, lichtsom_binnen):
    """Afwijking van de lichtlijn in °C: positief = warmer gestookt dan de lichtlijn."""
    if etmaaltemperatuur is None or lichtsom_binnen is None:
        return None
    return etmaaltemperatuur - t_ideaal(lichtsom_binnen)


def formule_tekst():
    """De formule als tekst voor schermen en rapporten, in Nederlandse notatie."""
    from utils.format import fmt_kort
    return f"{fmt_kort(LICHTLIJN_BASIS, 1)} + {fmt_kort(LICHTLIJN_FACTOR, 4)} × lichtsom binnen"

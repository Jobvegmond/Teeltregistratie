"""
Behandelingen (gewasbescherming, biologie, voeding) uit een externe bron.

Nu nog niet gekoppeld: de enige bron is LegeBron, die niets teruggeeft. Een
latere API wordt één nieuwe klasse met dezelfde vorm als BehandelingBron
(basis.py) en een regel in BRONNEN; de pagina Watergift en de database hoeven
dan niet te veranderen:
- de pagina leest alleen de tabellen `middel` en `behandeling`;
- synchroniseer() zet wat een bron teruggeeft in die tabellen, op
  (bron, extern_id) voor behandelingen en (bron, code) voor middelen, dus
  opnieuw ophalen maakt geen dubbele regels.
"""
from integrations.behandelingen.basis import Behandeling, BehandelingBron, Middel
from integrations.behandelingen.leeg import LegeBron

BRONNEN = {"leeg": LegeBron}


def synchroniseer(bron, van, tot, database=None):
    """Haalt de behandelingen van..tot op bij `bron` en zet ze in de database. Geeft het aantal regels."""
    if database is None:
        import database
    behandelingen = bron.fetch_behandelingen(van, tot)
    for b in behandelingen:
        middel_id = database.upsert_middel(b.middel, bron=bron.naam)
        database.upsert_behandeling(b, middel_id, bron=bron.naam)
    return len(behandelingen)


__all__ = ["Behandeling", "BehandelingBron", "BRONNEN", "LegeBron", "Middel", "synchroniseer"]

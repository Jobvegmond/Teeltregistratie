"""De vaste vorm van een behandeling en van een bron die behandelingen levert."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol

TYPES = ("gewasbescherming", "biologie", "voeding")


@dataclass(frozen=True)
class Middel:
    code: str                       # korte code in de matrix, bijv. "ENT" of "AMB"
    naam: str
    type: str                       # een van TYPES
    doel: str | None = None         # bijv. "trips", "meeldauw"
    werkzaam: str | None = None     # werkzame stof of organisme
    eenheid: str | None = None      # standaard doseringseenheid, bijv. "ml/100 l" of "stuks/m²"


@dataclass(frozen=True)
class Behandeling:
    datum: date
    tuin_nummer: int
    vaknummer: int
    middel: Middel
    dosering: float | None = None
    eenheid: str | None = None
    methode: str | None = None      # bijv. "spuiten", "strooien", "druppel"
    opmerking: str | None = None
    extern_id: str | None = None    # uniek binnen de bron; voorkomt dubbele regels bij opnieuw ophalen


class BehandelingBron(Protocol):
    naam: str

    def fetch_behandelingen(self, van: date, tot: date) -> list[Behandeling]:
        """Alle behandelingen met een datum van..tot (beide inclusief)."""
        ...

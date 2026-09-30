"""Bron zonder behandelingen: de plek waar later de echte API komt."""
from integrations.behandelingen.basis import Behandeling


class LegeBron:
    naam = "leeg"

    def fetch_behandelingen(self, van, tot) -> list[Behandeling]:
        return []

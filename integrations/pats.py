"""
Koppeling met PATS (pats-c.com): vangplaattellingen van de Trap-Eyes en insectentellingen van de PATS-C.

API v2 (OpenAPI: <server>/api/v2/openapi.yaml, docs: <server>/api/v2/docs). Inloggen met de gewone PATS-
gebruikersnaam en -wachtwoord (PATS_USER en PATS_PASSW in .env / .env.taak); dat geeft een toegangstoken van
2 uur. Wij gebruiken alleen de leesfuncties (sections, spots, detection_classes, counts); de API kan ook
apparaten verplaatsen en sections stoppen, dat doen we nooit.

Versie 2 staat sinds oktober 2026 op de testserver (beta.pats-c.com) en komt daarna op pats-c.com.
"""
import os

import requests

SERVERS = {"beta": "https://beta.pats-c.com", "productie": "https://pats-c.com"}
TIMEOUT = 60


class PatsFout(RuntimeError):
    pass


def standaard_server():
    """De server: PATS_SERVER uit de omgeving, anders config.PATS_SERVER ("beta" of "productie")."""
    from config import PATS_SERVER
    return os.environ.get("PATS_SERVER") or PATS_SERVER


def inloggegevens():
    """(gebruiker, wachtwoord) uit de omgeving, of None als ze er niet (allebei) zijn."""
    gebruiker, wachtwoord = os.environ.get("PATS_USER"), os.environ.get("PATS_PASSW")
    return (gebruiker, wachtwoord) if gebruiker and wachtwoord else None


class Pats:
    """Minimale client voor de leesfuncties van API v2."""

    def __init__(self, gebruiker, wachtwoord, server=None):
        server = server or standaard_server()
        self.basis = SERVERS.get(server, server).rstrip("/")
        r = requests.post(f"{self.basis}/token", data={"username": gebruiker, "password": wachtwoord},
                          timeout=TIMEOUT)
        if not r.ok:
            raise PatsFout(f"inloggen op {self.basis}: HTTP {r.status_code} {_melding(r)}")
        self.token = r.json()["access_token"]

    def _get(self, pad, **params):
        r = requests.get(f"{self.basis}/api/v2/{pad}", params=params, timeout=TIMEOUT,
                         headers={"Authorization": f"Bearer {self.token}"})
        if not r.ok:
            raise PatsFout(f"{pad}: HTTP {r.status_code} {_melding(r)}")
        return r.json()

    def sections(self):
        return self._get("sections")["sections"]

    def spots(self, section_id):
        return self._get("spots", section_id=section_id)

    def detection_classes(self):
        return self._get("detection_classes")

    def counts(self, section_id, van, tot, bin_mode="D"):
        """Tellingen per dag: {"trapeye": [...], "c": [...]}. van/tot als date; PATS-C-dagen lopen van 12 tot 12 uur."""
        return self._get("counts", section_id=section_id, start_date=f"{van:%Y%m%d}", end_date=f"{tot:%Y%m%d}",
                         bin_mode=bin_mode)


def _melding(r):
    try:
        return r.json().get("message", "")[:200]
    except ValueError:
        return r.text[:200]

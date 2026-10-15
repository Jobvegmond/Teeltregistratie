"""
Koppeling met Agro4all: de registraties met hun vakken ophalen.

Agro4all heeft geen losse REST-API; de gegevens zijn bereikbaar via hun MCP-server
(https://api-nl.agro4all.com/mcp, dezelfde die Claude gebruikt). Daarvoor is een toegangstoken nodig van een
machine-gebruiker (bij Agro4all aan te vragen: een service user met een personal access token). Zet die als
AGRO4ALL_PAT in .env.taak; dan haalt agro4all_import.py elk uur zelf op. Zonder token leest agro4all_import.py
de export die de geplande Claude-taak op de NAS zet (agro4all_samenvoegen.py).

De apparaat-login (device code) staat Agro4all voor de connector-client niet toe (getest 15-10-26).
"""
import json
import os

import requests

MCP = "https://api-nl.agro4all.com/mcp"
TIMEOUT = 60


class Agro4allFout(RuntimeError):
    pass


def toegang():
    """Het toegangstoken (AGRO4ALL_PAT), of None als er geen is."""
    return os.environ.get("AGRO4ALL_PAT") or None


class Mcp:
    """Minimale MCP-client over HTTP (JSON-RPC; het antwoord als JSON of als server-sent event)."""

    def __init__(self, access_token):
        self.kop = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"}
        self.volgnummer = 0
        antwoord = self._post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "vemteelt", "version": "1"}})
        self.protocol = antwoord.get("protocolVersion")
        self._post("notifications/initialized", None, melding=True)

    def _post(self, methode, params, melding=False):
        bericht = {"jsonrpc": "2.0", "method": methode}
        if params is not None:
            bericht["params"] = params
        if not melding:
            self.volgnummer += 1
            bericht["id"] = self.volgnummer
        r = requests.post(MCP, json=bericht, headers=self.kop, timeout=TIMEOUT)
        if "Mcp-Session-Id" in r.headers:
            self.kop["Mcp-Session-Id"] = r.headers["Mcp-Session-Id"]
        if melding:
            return None
        if not r.ok:
            raise Agro4allFout(f"{methode}: HTTP {r.status_code} {r.text[:200]}")
        antwoord = _lees_antwoord(r)
        if "error" in antwoord:
            raise Agro4allFout(f"{methode}: {antwoord['error']}")
        return antwoord.get("result", {})

    def tool(self, naam, **argumenten):
        """Roept een tool aan en geeft het JSON-antwoord (de tekst van het resultaat, ingelezen)."""
        resultaat = self._post("tools/call", {"name": naam, "arguments": argumenten})
        if resultaat.get("isError"):
            raise Agro4allFout(f"{naam}: {resultaat.get('content')}")
        if resultaat.get("structuredContent") is not None:
            return resultaat["structuredContent"]
        tekst = "".join(c.get("text", "") for c in resultaat.get("content", []) if c.get("type") == "text")
        return json.loads(tekst)


def _lees_antwoord(r):
    if r.headers.get("Content-Type", "").startswith("text/event-stream"):
        for regel in r.text.splitlines():
            if regel.startswith("data:"):
                data = json.loads(regel[5:].strip())
                if "result" in data or "error" in data:
                    return data
        raise Agro4allFout("Geen antwoord in de event-stream")
    return r.json()


def alle(mcp, tool, **argumenten):
    """Alle items van een lijst-tool, pagina voor pagina (limit 100)."""
    items, offset = [], 0
    while True:
        antwoord = mcp.tool(tool, limit=100, offset=offset, **argumenten)
        data = antwoord.get("data", [])
        items += data
        totaal = (antwoord.get("pagination") or {}).get("total", len(items))
        offset += len(data)
        if not data or offset >= totaal:
            return items


def ophalen(token, melding=print):
    """
    (velden, registraties, vakken_per_registratie, methodes) uit Agro4all: de velden met secties, alle
    uitgevoerde registraties, per registratie-id de set (tuin, vak) uit een vraag per sectie, en de
    toepassingswijzen (id → naam).
    """
    mcp = Mcp(token)
    velden = mcp.tool("list_fields", limit=100)["data"]
    filters = dict(types=["REGISTRATION"], stages=["FINAL"], language="nl")
    registraties = alle(mcp, "list_registrations", sort=["date"], **filters)
    vakken = {}
    for veld in velden:
        for sectie in veld.get("sections", []):
            for r in alle(mcp, "list_registrations", **{"filter.sectionIds": [sectie["id"]]}, **filters):
                vakken.setdefault(r["id"], set()).add(sectie["id"])
    methodes = {}
    for activiteit in ("CROP_PROTECTION", "BIO", "FERTILIZER"):
        for m in mcp.tool("list_application_manners", activityType=activiteit, language="nl").get("items", []):
            methodes[m["id"]] = m.get("name")
    melding(f"Agro4all: {len(registraties)} registraties, {sum(len(v.get('sections', [])) for v in velden)} vakken")
    return velden, registraties, vakken, methodes

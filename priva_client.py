"""
Priva Horticulture API-client — haalt etmaalklimaat op uit Priva ONE.

Wordt gebruikt door database.importeer_klimaat_uit_priva() om de dagelijkse
klimaatcijfers (etmaaltemperatuur, RV, stralingssom) per kasafdeling op te
halen, als vervanger van de handmatige klimaatcomputer-CSV.

Config via omgevingsvariabelen (lokaal via .env, op Render via Environment
Variables):
    PRIVA_CLIENT_ID       (verplicht)
    PRIVA_CLIENT_SECRET   (verplicht)
    PRIVA_SITE_ID         (optioneel, standaard = tuin 3)
    PRIVA_DEVICE_ID       (optioneel, standaard = VP9508)

Los te testen:
    python priva_client.py            -- haalt de laatste dagen op en print ze
"""

import os
from datetime import datetime, timedelta, timezone

import requests

AUTH_URL = "https://auth.priva.com/connect/token"
BASE_URL = "https://horti-api.priva.com"
API_VERSION = "2.0"
SCOPES = "priva.hortiapi-data-access priva.data-services priva.metadatastore"

# Standaard: tuin 3 (Alb. vt Hartweg 20). Tuin 1 is nog niet gedeeld in Priva
# Access Control; zodra dat wel zo is kan die site-id hier of via env erbij.
STANDAARD_SITE_ID = "eb6c5c08-00e1-4fb2-9b3e-2f755a69405d"
STANDAARD_DEVICE_ID = "VP9508"

# Onze kasafdelingen 1-4 komen overeen met Priva-compartiment 1-4 (5 negeren,
# net als bij de CSV-import). De variableId van een afdelingsdatapoint heeft de
# vorm 00000002-000<afd>-0000-0000-<staart>.
AFDELINGEN = (1, 2, 3, 4)

# Staarten van de datapoints die we per afdeling ophalen:
STAART_ETMAALTEMP = "000000000e30"   # Temp24hour.PrevActual24hT  — gerealiseerde etmaaltemp vorige 24u (1 waarde/dag @ 10:00 UTC), °C
STAART_STRALINGSSOM = "000000007dba"  # Temp24hour.PrevRadSumInside — stralingssom binnen vorige 24u (1 waarde/dag), J/cm²
STAART_RV_MOMENT = "000000000d5a"     # KASL_REF.ATR_GEM_KAS_RV     — gem. kas-RV momentwaarde (~1/min); zelf daggemiddelde

# Gratis Priva-abonnement: max 5 dagen historie, en endTime moet vóór
# middernacht UTC van vandaag liggen (alleen afgeronde dagen). We houden marge.
MAX_DAGEN_TERUG = 4

# De etmaalwaarde met tijdstempel op dag D (10:00 UTC) hoort bij kalenderdag
# D + OFFSET. 0 = zelfde datum als het tijdstempel. Verifieer dit één keer tegen
# een overlappende klimaatcomputer-CSV-dag en pas zo nodig aan (-1 of +1).
ETMAAL_DATUM_OFFSET_DAGEN = 0


class PrivaConfiguratieFout(RuntimeError):
    """Er ontbreken Priva-credentials in de omgeving."""


class PrivaHortiClient:
    def __init__(self, client_id=None, client_secret=None, site_id=None, device_id=None):
        self.client_id = client_id or os.environ.get("PRIVA_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("PRIVA_CLIENT_SECRET")
        self.site_id = site_id or os.environ.get("PRIVA_SITE_ID") or STANDAARD_SITE_ID
        self.device_id = device_id or os.environ.get("PRIVA_DEVICE_ID") or STANDAARD_DEVICE_ID
        if not self.client_id or not self.client_secret:
            raise PrivaConfiguratieFout(
                "PRIVA_CLIENT_ID en PRIVA_CLIENT_SECRET ontbreken in de omgeving."
            )
        self._token = None
        self._verloopt = datetime.now(timezone.utc)

    # -- interne helpers -------------------------------------------------

    def _headers(self):
        if self._token is None or datetime.now(timezone.utc) >= self._verloopt:
            self._authenticeer()
        return {
            "Authorization": f"Bearer {self._token}",
            "x-api-version": API_VERSION,
            "Content-Type": "application/json",
        }

    def _authenticeer(self):
        resp = requests.post(
            AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPES,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Priva-authenticatie mislukt ({resp.status_code}): {resp.text}")
        payload = resp.json()
        self._token = payload["access_token"]
        self._verloopt = datetime.now(timezone.utc) + timedelta(
            seconds=payload.get("expires_in", 3600) - 60
        )

    def _variable_id(self, afdeling, staart):
        return f"00000002-000{afdeling}-0000-0000-{staart}"

    # -- publieke API --------------------------------------------------

    def haal_etmaal_dagwaarden(self, dagen_terug=MAX_DAGEN_TERUG):
        """
        Haalt in één API-call de etmaalklimaatcijfers op voor de laatste
        `dagen_terug` afgeronde dagen, voor afdeling 1 t/m 4.

        Geeft een lijst dicts terug, gesorteerd op (datum, afdeling):
            {"afdeling": 1, "datum": date(2026, 9, 6),
             "gem_temperatuur": 17.78, "gem_rv": 82.1, "stralingssom_dag": 1584.0}

        Een dag/afdeling verschijnt alleen als er minstens één van de drie
        waarden voor is. Ontbrekende waarden zijn None; bij een volgende
        ophaalronde worden ze via de upsert alsnog aangevuld.
        """
        dagen_terug = max(1, min(int(dagen_terug), MAX_DAGEN_TERUG))

        nu = datetime.now(timezone.utc)
        middernacht = nu.replace(hour=0, minute=0, second=0, microsecond=0)
        eind = middernacht - timedelta(seconds=1)
        begin = middernacht - timedelta(days=dagen_terug)

        datapoints = []
        for afd in AFDELINGEN:
            for staart in (STAART_ETMAALTEMP, STAART_STRALINGSSOM, STAART_RV_MOMENT):
                datapoints.append({
                    "deviceGroupId": "none",
                    "deviceId": self.device_id,
                    "variableId": self._variable_id(afd, staart),
                })

        body = {
            "startTime": begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": eind.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timeType": "sensortime",
            "datapoints": datapoints,
        }

        resp = requests.post(
            f"{BASE_URL}/api/sites/{self.site_id}/data",
            headers=self._headers(),
            json=body,
            timeout=120,
        )
        if not resp.ok:
            raise RuntimeError(f"Priva data-call mislukt ({resp.status_code}): {resp.text[:500]}")

        return self._verwerk_payload(resp.json())

    # -- payload -> dagwaarden ----------------------------------------

    def _verwerk_payload(self, payload):
        # variableId-staart -> {afdeling: ...}
        staart_naar_afd = {}
        for afd in AFDELINGEN:
            for staart in (STAART_ETMAALTEMP, STAART_STRALINGSSOM, STAART_RV_MOMENT):
                staart_naar_afd[self._variable_id(afd, staart).lower()] = (afd, staart)

        # (afdeling, datum) -> {"temp":..., "straling":..., "rv_som":..., "rv_n":...}
        emmers = {}

        for entry in payload.get("data", []):
            dp = entry.get("datapoint", {})
            vid = (dp.get("variableId") or dp.get("id") or "").lower()
            paar = staart_naar_afd.get(vid)
            if not paar:
                continue
            afd, staart = paar

            for meting in entry.get("measurements", []):
                ruwe = meting.get("value")
                if ruwe is None or ruwe == "":
                    continue
                try:
                    waarde = float(ruwe)
                except (TypeError, ValueError):
                    continue
                ts = datetime.fromisoformat(meting["timestampUtc"].replace("Z", "+00:00"))

                if staart in (STAART_ETMAALTEMP, STAART_STRALINGSSOM):
                    datum = (ts + timedelta(days=ETMAAL_DATUM_OFFSET_DAGEN)).date()
                    bak = emmers.setdefault((afd, datum), {})
                    sleutel = "temp" if staart == STAART_ETMAALTEMP else "straling"
                    bak[sleutel] = waarde
                else:  # RV-momentwaarde: daggemiddelde zelf berekenen (UTC-dag)
                    datum = ts.date()
                    bak = emmers.setdefault((afd, datum), {})
                    bak["rv_som"] = bak.get("rv_som", 0.0) + waarde
                    bak["rv_n"] = bak.get("rv_n", 0) + 1

        resultaat = []
        for (afd, datum), bak in emmers.items():
            gem_rv = bak["rv_som"] / bak["rv_n"] if bak.get("rv_n") else None
            temp = bak.get("temp")
            straling = bak.get("straling")
            if temp is None and straling is None and gem_rv is None:
                continue
            resultaat.append({
                "afdeling": afd,
                "datum": datum,
                "gem_temperatuur": round(temp, 2) if temp is not None else None,
                "gem_rv": round(gem_rv, 1) if gem_rv is not None else None,
                "stralingssom_dag": round(straling, 1) if straling is not None else None,
            })

        resultaat.sort(key=lambda r: (r["datum"], r["afdeling"]))
        return resultaat


def _cli():
    try:
        from database import _laad_dotenv  # zelfde .env-lader als de rest
        _laad_dotenv()
    except Exception:
        pass
    client = PrivaHortiClient()
    for rij in client.haal_etmaal_dagwaarden():
        print(
            f"{rij['datum']}  afd {rij['afdeling']}  "
            f"T={rij['gem_temperatuur']}  RV={rij['gem_rv']}  straling={rij['stralingssom_dag']}"
        )


if __name__ == "__main__":
    _cli()

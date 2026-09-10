"""
Priva Horticulture API-client — haalt etmaalklimaat op uit Priva ONE.

Wordt gebruikt door database.importeer_klimaat_uit_priva() om de dagelijkse
klimaatcijfers per kasafdeling op te halen, als vervanger van de handmatige
klimaatcomputer-CSV. De waarden zijn 1-op-1 vergeleken met een CSV-export
(7-8 sept 2026) en komen overeen.

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
# Access Control; zodra dat wel zo is kan die site-id via PRIVA_SITE_ID erbij.
STANDAARD_SITE_ID = "eb6c5c08-00e1-4fb2-9b3e-2f755a69405d"
STANDAARD_DEVICE_ID = "VP9508"

# Onze kasafdelingen 1-4 = Priva-compartiment 1-4 (5 negeren, net als bij de
# CSV-import). De variableId van een afdelingsdatapoint heeft de vorm
# 00000002-000<afd>-0000-0000-<staart>.
AFDELINGEN = (1, 2, 3, 4)

# Priva heeft een aggregatie-familie die 1-op-1 matcht met de CSV-labels:
#   staart ...0003.... = "aggregation Average 24hr"  (etmaal)     <-> Ave_24h_Comp*
#   staart ...0001.... = "aggregation Average Day"   (dag)        <-> Ave_Day_Comp*
#   staart ...0002.... = "aggregation Average Night" (nacht)      <-> Ave_Night_Comp*
# Deze komen als 1 waarde/dag terug, tijdstempel op de daggrens (00:00 UTC); de
# datum van het tijdstempel is de dag waar de waarde bij hoort (geverifieerd
# tegen de CSV). De Night-waarde van de laatste dag ontbreekt tot de nacht om
# is — die blijft dan leeg en wordt de volgende ophaalronde aangevuld.
STAART_TEMP_24H = "000030000d5b"    # KASL_REF.ATR_GEM_KAS_TEMP - Average 24hr
STAART_TEMP_DAG = "000010000d5b"    #                             Average Day
STAART_TEMP_NACHT = "000020000d5b"  #                             Average Night
STAART_RV_24H = "000030000d5a"      # KASL_REF.ATR_GEM_KAS_RV   - Average 24hr
STAART_RV_DAG = "000010000d5a"      #                             Average Day
STAART_RV_NACHT = "000020000d5a"    #                             Average Night

# De stralingssom-aggregaties (Sum Day/Night/24hr) bestaan wél in de metadata
# maar geven geen timeseries terug via de API. Daarom halen we de berekende
# afdelingsstraling als momentwaarde op (W/m², ~1 waarde/min) en integreren die
# zelf per kalenderdag tot J/cm². Getest: komt op ±1 J/cm² overeen met de
# CSV-kolommen Sum_Day_CalculatedRadiation + Sum_Night_CalculatedRadiation.
STAART_STRALING_MOMENT = "000000000ce1"  # AFD_SOM.BER_AFD_STRAL - momentwaarde W/m²

AGGREGATIE_STAARTEN = {
    STAART_TEMP_24H: "temp",
    STAART_TEMP_DAG: "temp_dag",
    STAART_TEMP_NACHT: "temp_nacht",
    STAART_RV_24H: "rv",
    STAART_RV_DAG: "rv_dag",
    STAART_RV_NACHT: "rv_nacht",
}

# Watergift wordt per vak (Priva "Valve" 1-39 = ons vaknummer 1-39) bijgehouden
# als oplopende meterstand `KRAAN.VERBRUIKM2` (liter/m²). De variableId heeft de
# vorm 000001c2-<vak in hex, 4 cijfers>-0000-0000-<staart>. De daggift is het
# verschil van de meterstand over de dag; Priva logt tijdens een gietbeurt elke
# ~5 s, dus de toename valt vrijwel volledig binnen de juiste kalenderdag.
VAKKEN = tuple(range(1, 40))
STAART_WATER_METERSTAND = "000000003461"  # KRAAN.VERBRUIKM2 - liter/m² (cumulatief)

# Grote negatieve sprong in de meterstand = reset; die increment overslaan.
WATER_RESET_DREMPEL = -1.0

# Priva geeft UTC-tijdstempels. Voor het per-kalenderdag optellen van straling
# en watergift gebruiken we een vaste offset van +2 uur (CEST). De 1-uurs
# onnauwkeurigheid rond de zomer-/wintertijdgrens valt in uren zonder straling
# of gietbeurt en heeft dus geen effect op een dagtotaal.
LOKALE_OFFSET = timedelta(hours=2)

# Gratis Priva-abonnement: max 5 dagen historie, en endTime moet vóór
# middernacht UTC van vandaag liggen (alleen afgeronde dagen). Marge houden.
MAX_DAGEN_TERUG = 4


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

    def _venster(self, dagen_terug):
        """(begin, eind) UTC: de laatste `dagen_terug` volledig afgeronde dagen."""
        dagen_terug = max(1, min(int(dagen_terug), MAX_DAGEN_TERUG))
        middernacht = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return middernacht - timedelta(days=dagen_terug), middernacht - timedelta(seconds=1)

    def _data_call(self, begin, eind, datapoints, wat="data"):
        resp = requests.post(
            f"{BASE_URL}/api/sites/{self.site_id}/data",
            headers=self._headers(),
            json={
                "startTime": begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endTime": eind.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timeType": "sensortime",
                "datapoints": datapoints,
            },
            timeout=120,
        )
        if not resp.ok:
            raise RuntimeError(f"Priva {wat}-call mislukt ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    # -- publieke API --------------------------------------------------

    def haal_etmaal_dagwaarden(self, dagen_terug=MAX_DAGEN_TERUG):
        """
        Haalt in één API-call de etmaalklimaatcijfers op voor de laatste
        `dagen_terug` afgeronde dagen, voor afdeling 1 t/m 4.

        Geeft een lijst dicts terug, gesorteerd op (datum, afdeling):
            {"afdeling": 1, "datum": date(2026, 9, 7),
             "gem_temperatuur": 20.71, "gem_temperatuur_dag": 23.60,
             "gem_temperatuur_nacht": 18.46, "gem_rv": 82.99,
             "gem_rv_dag": 77.07, "gem_rv_nacht": 89.49,
             "stralingssom_dag": 1032.0}

        Ontbrekende waarden zijn None; bij een volgende ophaalronde worden ze
        via de upsert alsnog aangevuld.
        """
        begin, eind = self._venster(dagen_terug)
        datapoints = [
            {"deviceGroupId": "none", "deviceId": self.device_id,
             "variableId": self._variable_id(afd, staart)}
            for afd in AFDELINGEN
            for staart in list(AGGREGATIE_STAARTEN) + [STAART_STRALING_MOMENT]
        ]
        return self._verwerk_payload(self._data_call(begin, eind, datapoints, "klimaat"))

    # -- payload -> dagwaarden ----------------------------------------

    def _verwerk_payload(self, payload):
        # variableId (lowercase) -> (afdeling, staart)
        vid_index = {}
        for afd in AFDELINGEN:
            for staart in list(AGGREGATIE_STAARTEN) + [STAART_STRALING_MOMENT]:
                vid_index[self._variable_id(afd, staart).lower()] = (afd, staart)

        # (afdeling, datum) -> {"temp":..., "rv_dag":..., "straling":..., ...}
        emmers = {}
        # (afdeling) -> gesorteerde lijst (timestamp, W/m²) voor de straling
        straling_reeks = {afd: [] for afd in AFDELINGEN}

        for entry in payload.get("data", []):
            dp = entry.get("datapoint", {})
            vid = (dp.get("variableId") or dp.get("id") or "").lower()
            paar = vid_index.get(vid)
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

                if staart == STAART_STRALING_MOMENT:
                    straling_reeks[afd].append((ts, waarde))
                else:
                    veld = AGGREGATIE_STAARTEN[staart]
                    emmers.setdefault((afd, ts.date()), {})[veld] = waarde

        # straling per kalenderdag integreren (trapezium, W/m²·s -> J/cm²)
        for afd, reeks in straling_reeks.items():
            reeks.sort()
            for i in range(len(reeks) - 1):
                t0, v0 = reeks[i]
                t1, v1 = reeks[i + 1]
                dt = (t1 - t0).total_seconds()
                if dt <= 0 or dt > 3600:  # nachtelijk gat overslaan (straling ~0)
                    continue
                datum = (t0 + LOKALE_OFFSET).date()
                bak = emmers.setdefault((afd, datum), {})
                bak["straling"] = bak.get("straling", 0.0) + (v0 + v1) / 2 * dt / 10000.0

        resultaat = []
        for (afd, datum), bak in emmers.items():
            if not any(v is not None for v in bak.values()):
                continue
            resultaat.append({
                "afdeling": afd,
                "datum": datum,
                "gem_temperatuur": _rond(bak.get("temp"), 2),
                "gem_temperatuur_dag": _rond(bak.get("temp_dag"), 2),
                "gem_temperatuur_nacht": _rond(bak.get("temp_nacht"), 2),
                "gem_rv": _rond(bak.get("rv"), 1),
                "gem_rv_dag": _rond(bak.get("rv_dag"), 1),
                "gem_rv_nacht": _rond(bak.get("rv_nacht"), 1),
                "stralingssom_dag": _rond(bak.get("straling"), 0),
            })

        resultaat.sort(key=lambda r: (r["datum"], r["afdeling"]))
        return resultaat

    # -- watergift per vak --------------------------------------------

    def haal_watergift_dagwaarden(self, dagen_terug=MAX_DAGEN_TERUG):
        """
        Haalt in één API-call de daggift (liter/m²) per vak (1-39) op voor de
        laatste afgeronde dagen, uit de oplopende meterstand KRAAN.VERBRUIKM2.

        Geeft een lijst dicts terug, gesorteerd op (datum, vaknummer):
            {"vaknummer": 25, "datum": date(2026, 9, 6), "liter_per_m2": 14.0}

        De oudste dag van het venster wordt weggelaten: daarvoor ontbreekt een
        meterstand van vóór middernacht, dus die zou te laag uitvallen.
        """
        begin, eind = self._venster(dagen_terug)
        oudste_volledige_dag = (begin + LOKALE_OFFSET).date() + timedelta(days=1)
        datapoints = [
            {"deviceGroupId": "none", "deviceId": self.device_id,
             "variableId": f"000001c2-{vak:04x}-0000-0000-{STAART_WATER_METERSTAND}"}
            for vak in VAKKEN
        ]
        payload = self._data_call(begin, eind, datapoints, "watergift")

        resultaat = []
        for entry in payload.get("data", []):
            dp = entry.get("datapoint", {})
            vid = dp.get("variableId") or dp.get("id") or ""
            try:
                vak = int(vid.split("-")[1], 16)
            except (IndexError, ValueError):
                continue

            reeks = []
            for meting in entry.get("measurements", []):
                ruwe = meting.get("value")
                if ruwe is None or ruwe == "":
                    continue
                try:
                    reeks.append((
                        datetime.fromisoformat(meting["timestampUtc"].replace("Z", "+00:00")),
                        float(ruwe),
                    ))
                except (TypeError, ValueError):
                    continue
            reeks.sort()

            per_dag = {}
            for (t0, v0), (t1, v1) in zip(reeks, reeks[1:]):
                toename = v1 - v0
                if toename < WATER_RESET_DREMPEL:
                    continue
                datum = (t0 + LOKALE_OFFSET).date()
                per_dag[datum] = per_dag.get(datum, 0.0) + max(0.0, toename)

            for datum, liter in per_dag.items():
                if datum < oudste_volledige_dag:
                    continue
                resultaat.append({
                    "vaknummer": vak,
                    "datum": datum,
                    "liter_per_m2": round(liter, 1),
                })

        resultaat.sort(key=lambda r: (r["datum"], r["vaknummer"]))
        return resultaat


def _rond(waarde, decimalen):
    if waarde is None:
        return None
    return round(waarde, decimalen) if decimalen else round(waarde)


def _cli():
    try:
        from database import _laad_dotenv  # zelfde .env-lader als de rest
        _laad_dotenv()
    except Exception:
        pass
    client = PrivaHortiClient()
    print("--- etmaalklimaat ---")
    for rij in client.haal_etmaal_dagwaarden():
        print(
            f"{rij['datum']}  afd {rij['afdeling']}  "
            f"T={rij['gem_temperatuur']} (d {rij['gem_temperatuur_dag']} / n {rij['gem_temperatuur_nacht']})  "
            f"RV={rij['gem_rv']} (d {rij['gem_rv_dag']} / n {rij['gem_rv_nacht']})  "
            f"straling={rij['stralingssom_dag']}"
        )
    print("--- watergift (liter/m² per vak) ---")
    for rij in client.haal_watergift_dagwaarden():
        if rij["liter_per_m2"]:
            print(f"{rij['datum']}  vak {rij['vaknummer']:2}  {rij['liter_per_m2']}")


if __name__ == "__main__":
    _cli()

"""
Stralingsverwachting van Open-Meteo (open-meteo.com: gratis, geen sleutel) voor de kwekerij in Bleiswijk:
kortegolfstraling per dag in MJ/m² (shortwave_radiation_sum), in de Europe/Amsterdam-tijd. Alleen lezen; er gaat
niets anders mee dan de vaste coördinaten en de datums.

- verwachting(): de laatste `dagen_terug` dagen en de komende `dagen_vooruit` dagen uit de gewone verwachting
  (voor het ijken op de Priva-stralingssom en de verwachting voor vandaag en morgen).
- historie(): de opgeslagen verwachtingen over een periode (historical-forecast-api), voor de terugtoets: zo
  goed als wat het advies die ochtend had kunnen weten.
"""
from datetime import date

import requests

BREEDTE, LENGTE = 52.01, 4.53          # Bleiswijk
VERWACHTING = "https://api.open-meteo.com/v1/forecast"
HISTORIE = "https://historical-forecast-api.open-meteo.com/v1/forecast"
TIMEOUT = 30


def _dagen(url, extra):
    params = {"latitude": BREEDTE, "longitude": LENGTE, "daily": "shortwave_radiation_sum",
              "timezone": "Europe/Amsterdam", **extra}
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    dagelijks = r.json()["daily"]
    return {date.fromisoformat(d): s for d, s in zip(dagelijks["time"], dagelijks["shortwave_radiation_sum"])
            if s is not None}


def verwachting(dagen_terug=40, dagen_vooruit=2):
    """{datum: MJ/m²} voor de laatste dagen en de komende dagen (vandaag telt bij dagen_vooruit)."""
    return _dagen(VERWACHTING, {"past_days": dagen_terug, "forecast_days": dagen_vooruit})


def historie(van, tot):
    """{datum: MJ/m²} van van t/m tot uit de opgeslagen verwachtingen."""
    return _dagen(HISTORIE, {"start_date": str(van), "end_date": str(tot)})

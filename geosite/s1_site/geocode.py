"""Convert a US ZIP code to a census tract GEOID via the Census Geocoder API.

Uses the free Census Bureau geocoding service — no API key required.
API docs: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html
"""

import requests

_CENSUS_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/address"
    "?street=&city=&state=&zip={zip}"
    "&benchmark=Public_AR_Census2020"
    "&vintage=Census2020_Census2020"
    "&layers=10"
    "&format=json"
)


def zip_to_geoid(zip_code: str) -> str:
    """Return the 11-digit census tract GEOID for a given ZIP code.

    Uses the first matching census tract when a ZIP spans multiple tracts.
    Raises ValueError if the ZIP code returns no census tracts.
    """
    url = _CENSUS_URL.format(zip=zip_code.strip())
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ValueError(f"Census geocoding service unavailable: {exc}") from exc

    tracts = (
        resp.json()
        .get("result", {})
        .get("geographies", {})
        .get("Census Tracts", [])
    )
    if not tracts:
        raise ValueError(f"No census tract found for ZIP code '{zip_code}'")

    return tracts[0]["GEOID"]

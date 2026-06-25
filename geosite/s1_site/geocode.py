"""Convert a US ZIP code to a census tract GEOID.

Two-step approach (both services are free, no API key required):
  1. ZIP → (lat, lon)  via api.zippopotam.us
  2. (lat, lon) → GEOID via Census Bureau coordinates geocoder

Why two steps: the Census address geocoder requires a street address;
ZIP-only lookups return 0 matches. The coordinates endpoint works reliably
with centroid coordinates derived from the ZIP.
"""

import requests

_ZIPPOPOTAM_URL = "https://api.zippopotam.us/us/{zip}"

_CENSUS_COORDS_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    "?x={lon}&y={lat}"
    "&benchmark=Public_AR_Current"
    "&vintage=Current_Current"
    "&layers=Census+Tracts"
    "&format=json"
)


def zip_to_geoid(zip_code: str) -> str:
    """Return the 11-digit census tract GEOID for a US ZIP code.

    Raises ValueError for unknown ZIP codes or service unavailability.
    """
    lat, lon = _zip_to_coords(zip_code)
    return _coords_to_geoid(lat, lon, zip_code)


def _zip_to_coords(zip_code: str) -> tuple[str, str]:
    """Return (latitude, longitude) strings for a ZIP code centroid."""
    url = _ZIPPOPOTAM_URL.format(zip=zip_code.strip())
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            raise ValueError(f"ZIP code '{zip_code}' not recognised")
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ValueError(f"ZIP lookup service unavailable: {exc}") from exc

    places = resp.json().get("places", [])
    if not places:
        raise ValueError(f"No location data for ZIP code '{zip_code}'")
    return places[0]["latitude"], places[0]["longitude"]


def _coords_to_geoid(lat: str, lon: str, zip_code: str) -> str:
    """Return the 11-digit census tract GEOID for a lat/lon point."""
    url = _CENSUS_COORDS_URL.format(lat=lat, lon=lon)
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

"""s1_site: site and soil thermal property lookup.

Public API
----------
get_site_data(zip_code) -> SiteData
    Geocode a ZIP code to a census tract, then look up pre-computed soil
    properties from data/public/thermal_by_tract.csv.
"""

from geosite.s1_site.geocode import zip_to_geoid
from geosite.s1_site.lookup import lookup_by_geoid
from geosite.models import SiteData


def get_site_data(zip_code: str) -> SiteData:
    """Return soil thermal properties and climate zone for a ZIP code.

    Geocodes the ZIP to a census tract GEOID, then looks up pre-computed
    Côté-Konrad (2005) derived thermal properties from data/public/.

    Parameters
    ----------
    zip_code : US ZIP code as a string, e.g. "60601"

    Returns
    -------
    SiteData with data_available=True when SSURGO data exists for the tract,
    data_available=False when the tract has no soil data (shows as blank on map).
    """
    geoid = zip_to_geoid(zip_code)
    return lookup_by_geoid(geoid)

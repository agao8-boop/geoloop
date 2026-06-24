"""s2_simulation: building energy loads for GSHP borefield sizing.

Public API
----------
get_loads(building_type, climate_zone) -> LoadPulses
    Look up pre-computed ASHRAE three-pulse ground loads from
    data/public/prototype_loads.json (fast path — no EnergyPlus required).

    When the user provides building parameter overrides, a future plan
    (Plan B) will trigger a real-time EnergyPlus simulation instead.
"""

from geosite.s2_simulation.lookup import lookup_prototype_loads
from geosite.models import LoadPulses


def get_loads(building_type: str, climate_zone: str) -> LoadPulses:
    """Return three-pulse ground loads for a DOE prototype building in a climate zone.

    Parameters
    ----------
    building_type : DOE prototype key, e.g. "small_office", "medium_office"
    climate_zone  : ASHRAE climate zone, e.g. "5A", "3B", "2A"

    Returns
    -------
    LoadPulses with sign convention: negative=heating, positive=cooling.
    """
    return lookup_prototype_loads(building_type, climate_zone)

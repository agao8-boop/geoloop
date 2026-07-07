"""s2_simulation: building energy loads for GSHP borefield sizing.

Public API
----------
get_loads(building_type, climate_zone, floor_area_m2=None) -> LoadPulses
    Look up pre-computed ASHRAE three-pulse ground loads from
    data/public/prototype_loads.json (fast path — no EnergyPlus required).

    If floor_area_m2 is provided and the JSON contains normalized W/m² values
    (populated by scripts/precompute_loads.py), loads are scaled to the user's
    floor area.  Otherwise returns values at the DOE prototype reference area.
"""

from geosite.s2_simulation.lookup import lookup_prototype_loads
from geosite.models import LoadPulses


def get_loads(
    building_type: str,
    climate_zone: str,
    floor_area_m2: float | None = None,
    envelope_factor: float = 1.0,
) -> LoadPulses:
    """Return three-pulse ground loads for a DOE prototype building.

    Parameters
    ----------
    building_type   : DOE prototype key, e.g. "small_office", "medium_office"
    climate_zone    : ASHRAE climate zone, e.g. "5A", "3B", "2A"
    floor_area_m2   : user building floor area [m²].  If None, returns values
                      at the prototype reference area.
    envelope_factor : building-design load multiplier (WWR × envelope ×
                      glazing, from s2_simulation.envelope). 1.0 = prototype
                      baseline; placeholder until calibrated values land.

    Returns
    -------
    LoadPulses with sign convention: negative=heating, positive=cooling.
    """
    loads = lookup_prototype_loads(building_type, climate_zone,
                                   target_area_m2=floor_area_m2)
    if envelope_factor == 1.0:
        return loads

    def _s(v: float) -> float:
        return v * envelope_factor if v == v else float("nan")

    return LoadPulses(
        q_h=_s(loads.q_h),
        q_m=_s(loads.q_m),
        q_y=_s(loads.q_y),
        q_h_heat=_s(loads.q_h_heat),
        q_m_heat=_s(loads.q_m_heat),
        q_h_cool=_s(loads.q_h_cool),
        q_m_cool=_s(loads.q_m_cool),
    )

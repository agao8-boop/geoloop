"""s2_simulation: building energy loads for GSHP borefield sizing.

Public API
----------
get_loads(building_type, climate_zone, floor_area_m2=None,
          heat_factor=1.0, cool_factor=1.0) -> LoadPulses
    Look up pre-computed ASHRAE three-pulse ground loads from
    data/public/prototype_loads.json (fast path — no EnergyPlus required).

    heat_factor scales q_h_heat, q_m_heat (heating pulses only).
    cool_factor scales q_h_cool, q_m_cool (cooling pulses only).
    Combined q_h / q_m / q_y use max(heat_factor, cool_factor) — conservative.
"""

from geosite.s2_simulation.lookup import lookup_prototype_loads
from geosite.models import LoadPulses


def get_loads(
    building_type: str,
    climate_zone: str,
    floor_area_m2: float | None = None,
    heat_factor: float = 1.0,
    cool_factor: float = 1.0,
    envelope_factor: float | None = None,  # legacy shim: overrides both if set
) -> LoadPulses:
    """Return three-pulse ground loads for a DOE prototype building.

    Parameters
    ----------
    building_type : DOE prototype key, e.g. "small_office", "medium_office"
    climate_zone  : ASHRAE climate zone, e.g. "5A", "3B", "2A"
    floor_area_m2 : user building floor area [m²].  If None, returns values
                    at the prototype reference area.
    heat_factor   : multiplier applied to q_h_heat, q_m_heat (heating pulses).
    cool_factor   : multiplier applied to q_h_cool, q_m_cool (cooling pulses).
    envelope_factor : DEPRECATED — legacy single-scalar shim; sets both
                      heat_factor and cool_factor if provided.

    Returns
    -------
    LoadPulses with sign convention: negative=heating, positive=cooling.
    """
    if envelope_factor is not None:
        heat_factor = cool_factor = envelope_factor

    try:
        loads = lookup_prototype_loads(building_type, climate_zone,
                                       target_area_m2=floor_area_m2)
    except KeyError as exc:
        if "Climate zone" not in str(exc):
            raise
        # climate_zone not pre-computed for this building type; derive from hourly profile
        from geosite.s6_strategy.load_profile import load_hourly_profile, _HOURLY_FALLBACK
        from geosite.s3_loads.compute import compute_pulses_from_ground
        from geosite.s4_sizing.footprint import PROTOTYPE_AREAS_M2
        profile = load_hourly_profile(building_type, climate_zone)
        # Profile is stored at the proxy building type's scale; normalize to target type.
        proxy_type = _HOURLY_FALLBACK.get(building_type, building_type)
        target_area = float(floor_area_m2 or PROTOTYPE_AREAS_M2.get(building_type, 1.0))
        proxy_area = float(PROTOTYPE_AREAS_M2.get(proxy_type, 1.0))
        scale = target_area / proxy_area
        if scale != 1.0:
            profile = [v * scale for v in profile]
        loads = compute_pulses_from_ground(profile)
    if heat_factor == 1.0 and cool_factor == 1.0:
        return loads

    combined = max(heat_factor, cool_factor)

    def _h(v: float) -> float:
        return v * heat_factor if v == v else float("nan")

    def _c(v: float) -> float:
        return v * cool_factor if v == v else float("nan")

    def _x(v: float) -> float:
        return v * combined if v == v else float("nan")

    return LoadPulses(
        q_h=_x(loads.q_h),
        q_m=_x(loads.q_m),
        q_y=_x(loads.q_y),
        q_h_heat=_h(loads.q_h_heat),
        q_m_heat=_h(loads.q_m_heat),
        q_h_cool=_c(loads.q_h_cool),
        q_m_cool=_c(loads.q_m_cool),
    )

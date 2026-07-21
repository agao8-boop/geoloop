"""Climate-aware, heat/cool-split envelope load factors.

For a given (climate_zone, building_type, wwr, glazing, infiltration),
returns (heat_factor, cool_factor) looked up from pre-computed EnergyPlus
parametric study results in data/envelope_study/results/.

Variant → JSON key mapping
--------------------------
  wwr:         low→wwr_10pct  medium→wwr_20pct(=1.0)  high→wwr_70pct
  glazing:     triple→glaz_triple_low_e  double→glaz_double_low_e
               double_legacy→glaz_double_pane  single→glaz_single_pane
  infiltration: high→infil_tight  standard→infil_standard  low→infil_leaky

Fall-backs
----------
  unknown building type → medium_office data
  unknown climate zone  → denver (5B) data
"""

import functools
import json
import pathlib

_RESULTS_DIR = pathlib.Path(__file__).parents[2] / "data" / "envelope_study" / "results"

# ASHRAE climate zone → city key used in JSON filenames
_ZONE_TO_CITY: dict[str, str] = {
    "1A": "miami",   "2A": "tampa",     "2B": "tucson",
    "3A": "atlanta", "3B": "el_paso",   "3C": "san_diego",
    "4A": "new_york","4B": "albuquerque","4C": "seattle",
    "5A": "buffalo", "5B": "denver",    "5C": "port_angeles",
    "6A": "rochester","6B": "great_falls",
    "7":  "international_falls", "8": "fairbanks",
}
_FALLBACK_CITY = "denver"
_FALLBACK_TYPE = "medium_office"

# Maps legacy UI/prototype_loads keys → sensitivity JSON filename keys
_ENVELOPE_TYPE_ALIAS: dict[str, str] = {
    "standalone_retail":     "retail_standalone",
    "primary_school":        "school_primary",
    "secondary_school":      "school_secondary",
    "outpatient_healthcare": "outpatient",
    "small_hotel":           "hotel_small",
    "large_hotel":           "hotel_large",
    "midrise_apartment":     "apartment_midrise",
    "highrise_apartment":    "apartment_highrise",
    # new types (no alias needed — keys already match sensitivity filenames)
    "retail_stripmall":    "retail_stripmall",
    "restaurant_fastfood": "restaurant_fastfood",
    "restaurant_sitdown":  "restaurant_sitdown",
}

# UI option → JSON variant key
_WWR_KEY: dict[str, str] = {
    "low":    "wwr_10pct",
    "medium": "wwr_20pct",
    "high":   "wwr_70pct",
}
_GLAZING_KEY: dict[str, str] = {
    "triple":        "glaz_triple_low_e",
    "double":        "glaz_double_low_e",       # code-min low-E (post-2000)
    "double_legacy": "glaz_double_pane",         # pre-2000 clear double-pane
    "single":        "glaz_single_pane",
}
_INFIL_KEY: dict[str, str] = {
    "high":     "infil_tight",
    "standard": "infil_standard",
    "low":      "infil_leaky",
}

WWR_OPTIONS      = frozenset(_WWR_KEY)
GLAZING_OPTIONS  = frozenset(_GLAZING_KEY)
ENVELOPE_OPTIONS = frozenset(_INFIL_KEY)    # "envelope" in UI = infiltration/insulation tier

# Legacy aliases kept for callers that imported the old names
WWR_FACTORS     = {k: 1.0 for k in WWR_OPTIONS}      # ponytail: dummy values, real data from JSON
ENVELOPE_FACTORS = {k: 1.0 for k in ENVELOPE_OPTIONS}
GLAZING_FACTORS  = {k: 1.0 for k in GLAZING_OPTIONS}


@functools.lru_cache(maxsize=128)
def _load_multipliers(building_type: str, city: str) -> dict:
    """Return the 'multipliers' sub-dict from the study JSON; fall back gracefully."""
    bt_resolved = _ENVELOPE_TYPE_ALIAS.get(building_type, building_type)
    for bt in (bt_resolved, _FALLBACK_TYPE):
        for ct in (city, _FALLBACK_CITY):
            p = _RESULTS_DIR / f"multipliers_{bt}_{ct}.json"
            if not p.exists():
                # legacy naming without building-type prefix
                p = _RESULTS_DIR / f"multipliers_{ct}.json"
            if p.exists():
                try:
                    data = json.loads(p.read_text())
                    mults = data.get("multipliers", {})
                    if mults:
                        return mults
                except Exception:
                    pass
    return {}


def get_envelope_factors(
    climate_zone: str,
    building_type: str,
    wwr: str = "medium",
    glazing: str = "double",
    infiltration: str = "standard",
) -> tuple[float, float]:
    """Return (heat_factor, cool_factor) for the given envelope selections.

    Factors multiply prototype loads: 1.0 = prototype baseline.
    heat_factor → applied to q_h_heat, q_m_heat.
    cool_factor → applied to q_h_cool, q_m_cool.
    Combined q_h / q_m / q_y use max(heat_factor, cool_factor) — conservative.
    """
    city  = _ZONE_TO_CITY.get(climate_zone, _FALLBACK_CITY)
    mults = _load_multipliers(building_type, city)

    heat = cool = 1.0
    for key_map, selection in (
        (_WWR_KEY, wwr),
        (_GLAZING_KEY, glazing),
        (_INFIL_KEY, infiltration),
    ):
        variant_key = key_map.get(selection)
        if not variant_key or variant_key not in mults:
            continue
        v = mults[variant_key]
        heat *= v.get("peak_heat", 1.0)
        cool *= v.get("peak_cool", 1.0)

    return heat, cool


def compute_envelope_factor(
    wwr: str = "medium",
    envelope: str = "standard",
    glazing: str = "double",
    climate_zone: str = "5B",
    building_type: str = "medium_office",
) -> float:
    """Legacy single-scalar shim — returns max(heat, cool) for backwards compat."""
    h, c = get_envelope_factors(climate_zone, building_type, wwr, glazing, envelope)
    return max(h, c)

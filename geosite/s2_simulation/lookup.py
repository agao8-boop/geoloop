"""Look up pre-computed annual ground loads for DOE prototype buildings.

Reads data/public/prototype_loads.json, keyed by building_type → climate_zone.
Values represent ASHRAE three-pulse ground loads (Philippe et al. 2010 convention).
Sign convention: negative = heating-dominant, positive = cooling-dominant.

These values are pre-computed from EnergyPlus runs for DOE Commercial Prototype
Building Models (Deru et al. 2011) in Ideal Air Loads mode. The developer pipeline
(scripts/precompute_loads.py) generates the JSON; this module only reads it.
"""

import json
import pathlib
from geosite.models import LoadPulses

_DEFAULT_JSON = pathlib.Path(__file__).parents[2] / "data/public/prototype_loads.json"


def lookup_prototype_loads(
    building_type: str,
    climate_zone: str,
    loads_json: pathlib.Path = _DEFAULT_JSON,
) -> LoadPulses:
    """Return three-pulse ground loads for a building type and climate zone.

    Raises KeyError with a descriptive message if the combination is not in the table.
    """
    with open(loads_json) as f:
        table = json.load(f)

    if building_type not in table:
        raise KeyError(
            f"'{building_type}' not in prototype loads table. "
            f"Available: {[k for k in table if not k.startswith('_')]}"
        )

    building_table = table[building_type]
    if climate_zone not in building_table:
        raise KeyError(
            f"Climate zone '{climate_zone}' not found for '{building_type}'. "
            f"Available zones: {list(building_table.keys())}"
        )

    entry = building_table[climate_zone]
    return LoadPulses(
        q_h=float(entry["q_h"]),
        q_m=float(entry["q_m"]),
        q_y=float(entry["q_y"]),
    )

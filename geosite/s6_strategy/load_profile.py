import json
import pathlib

import numpy as np

_DEFAULT_HOURLY_JSON = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "data" / "public" / "prototype_loads_hourly.json"
)

_CACHE: dict = {}

# Map building types without hourly profiles to a similar available type.
# As of 2026-07-23: 15/16 types have real 8760h data; only midrise_apartment
# still uses a proxy until its EnergyPlus runs complete.
_HOURLY_FALLBACK: dict[str, str] = {
    "midrise_apartment": "medium_office",
}


def _load_json(hourly_json_path) -> dict:
    path = str(hourly_json_path)
    if path not in _CACHE:
        _CACHE[path] = json.loads(pathlib.Path(hourly_json_path).read_text())
    return _CACHE[path]


def load_hourly_profile(
    building_type: str,
    climate_zone: str,
    hourly_json_path=_DEFAULT_HOURLY_JSON,
) -> list:
    """Return 8760h ground load array (W) for given building type and climate zone.

    Falls back to a similar building type when no hourly data exists yet.
    Raises KeyError only when climate_zone is not found.
    """
    data = _load_json(hourly_json_path)
    bt = building_type if building_type in data else _HOURLY_FALLBACK.get(building_type)
    if bt is None or bt not in data:
        raise KeyError(building_type)
    bt_data = data[bt]
    if climate_zone not in bt_data:
        raise KeyError(climate_zone)
    return [float(v) for v in bt_data[climate_zone]]


def scale_profile(profile: list, scale_factor: float) -> list:
    """Multiply every hourly value by scale_factor. Used for floor area and year adjustments."""
    return (np.asarray(profile, dtype=float) * scale_factor).tolist()

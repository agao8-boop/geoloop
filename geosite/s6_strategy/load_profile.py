import json
import pathlib

_DEFAULT_HOURLY_JSON = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "data" / "public" / "prototype_loads_hourly.json"
)

_CACHE: dict = {}


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

    Raises KeyError if building_type or climate_zone is not found.
    """
    data = _load_json(hourly_json_path)
    if building_type not in data:
        raise KeyError(building_type)
    bt_data = data[building_type]
    if climate_zone not in bt_data:
        raise KeyError(climate_zone)
    return [float(v) for v in bt_data[climate_zone]]


def scale_profile(profile: list, scale_factor: float) -> list:
    """Multiply every hourly value by scale_factor. Used for floor area and year adjustments."""
    return [v * scale_factor for v in profile]

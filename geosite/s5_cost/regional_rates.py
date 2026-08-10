import json
import pathlib

_RATES_FILE = pathlib.Path(__file__).parents[2] / "data" / "public" / "drilling_rates_by_state.json"
_rates_cache: dict | None = None

_STATE_TO_DIV = {
    "CT": "NE_div", "ME": "NE_div", "MA": "NE_div", "NH": "NE_div", "RI": "NE_div", "VT": "NE_div",
    "NJ": "MA_div", "NY": "MA_div", "PA": "MA_div",
    "IL": "ENC_div", "IN": "ENC_div", "MI": "ENC_div", "OH": "ENC_div", "WI": "ENC_div",
    "IA": "WNC_div", "KS": "WNC_div", "MN": "WNC_div", "MO": "WNC_div",
    "NE": "WNC_div", "ND": "WNC_div", "SD": "WNC_div",
    "DE": "SA_div", "DC": "SA_div", "FL": "SA_div", "GA": "SA_div",
    "MD": "SA_div", "NC": "SA_div", "SC": "SA_div", "VA": "SA_div", "WV": "SA_div",
    "AL": "ESC_div", "KY": "ESC_div", "MS": "ESC_div", "TN": "ESC_div",
    "AR": "WSC_div", "LA": "WSC_div", "OK": "WSC_div", "TX": "WSC_div",
    "AZ": "Mtn_div", "CO": "Mtn_div", "ID": "Mtn_div", "MT": "Mtn_div",
    "NV": "Mtn_div", "NM": "Mtn_div", "UT": "Mtn_div", "WY": "Mtn_div",
    "AK": "Pac_div", "CA": "Pac_div", "HI": "Pac_div", "OR": "Pac_div", "WA": "Pac_div",
}


def _load() -> dict:
    global _rates_cache
    if _rates_cache is None:
        _rates_cache = json.loads(_RATES_FILE.read_text())
    return _rates_cache


def get_region_used(state: str | None) -> str:
    table = _load()
    if state and state.upper() in table:
        return state.upper()
    div = _STATE_TO_DIV.get((state or "").upper())
    if div and div in table:
        return div
    return "US"


def get_rates(state: str | None) -> dict:
    return _load()[get_region_used(state)]

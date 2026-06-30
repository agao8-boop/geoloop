"""Look up deep-borehole thermal properties by census tract GEOID.

Primary source: data/public/deep_thermal_by_county.csv
  County-level k [W/m·K], α [m²/day], T_g [°C] at 100 m borehole midpoint.
  Produced by scripts/collect_deep_thermal.py.
  Methods: SMU IDW (Blackwell & Richards 2004) or
           SGMC → Clauser & Huenges (1995) median k.

Fallback: data/public/thermal_by_tract.csv
  Tract-level SSURGO shallow soil properties (0–2 m).
  NOTE: Only valid for horizontal closed-loop systems — NOT for vertical
  boreholes. Used only when deep_thermal_by_county.csv is not yet generated.

County FIPS is derived from the census tract GEOID (first 5 characters).
"""

import pathlib
import pandas as pd
from geosite.models import SiteData

_DATA = pathlib.Path(__file__).parents[2] / "data" / "public"
_DEEP_COUNTY_CSV  = _DATA / "deep_thermal_by_county.csv"
_SHALLOW_TRACT_CSV = _DATA / "thermal_by_tract.csv"
_CLIMATE_CSV      = _DATA / "climate_by_tract.csv"

# Cache DataFrames in module-level variables (loaded once per process)
_deep_df:    pd.DataFrame | None = None
_shallow_df: pd.DataFrame | None = None
_climate_df: pd.DataFrame | None = None


def _load_deep() -> pd.DataFrame | None:
    global _deep_df
    if _deep_df is None and _DEEP_COUNTY_CSV.exists():
        _deep_df = pd.read_csv(_DEEP_COUNTY_CSV, dtype={"county_fips": str})
        _deep_df["county_fips"] = _deep_df["county_fips"].str.zfill(5)
    return _deep_df


def _load_shallow() -> pd.DataFrame:
    global _shallow_df
    if _shallow_df is None:
        _shallow_df = pd.read_csv(_SHALLOW_TRACT_CSV, dtype={"geoid": str})
    return _shallow_df


def _load_climate() -> pd.DataFrame:
    global _climate_df
    if _climate_df is None:
        _climate_df = pd.read_csv(_CLIMATE_CSV, dtype={"geoid": str})
    return _climate_df


def lookup_by_geoid(
    geoid: str,
    thermal_csv: pathlib.Path = _SHALLOW_TRACT_CSV,
    climate_csv: pathlib.Path = _CLIMATE_CSV,
    deep_csv: pathlib.Path | None = _DEEP_COUNTY_CSV,
) -> SiteData:
    """Return SiteData for a census tract GEOID.

    Looks up k, α, T_g from the deep-borehole county dataset first
    (data/public/deep_thermal_by_county.csv). Falls back to the
    SSURGO shallow tract dataset if the deep dataset is unavailable.

    Parameters
    ----------
    geoid : 11-digit census tract GEOID, e.g. "17031320101"
    thermal_csv : SSURGO shallow tract CSV (fallback)
    climate_csv : climate zone by tract GEOID
    deep_csv : county-level deep thermal CSV; pass None to skip (for unit tests)
    """
    climate = pd.read_csv(climate_csv, dtype={"geoid": str})
    c_row = climate[climate["geoid"] == geoid]
    climate_zone = str(c_row.iloc[0]["climate_zone"]) if not c_row.empty else ""

    county_fips = geoid[:5].zfill(5)

    # ── Primary: deep borehole county dataset ────────────────────────────
    if deep_csv is not None and deep_csv.exists():
        deep = pd.read_csv(deep_csv, dtype={"county_fips": str})
        deep["county_fips"] = deep["county_fips"].str.zfill(5)
        d_row = deep[deep["county_fips"] == county_fips]
        if not d_row.empty:
            d = d_row.iloc[0]
            k     = float(d["k_wmpk"])     if pd.notna(d["k_wmpk"])     else float("nan")
            alpha = float(d["alpha_m2day"]) if pd.notna(d["alpha_m2day"]) else float("nan")
            T_g   = float(d["T_g_C"])      if pd.notna(d["T_g_C"])      else float("nan")
            if not (pd.isna(k) or pd.isna(alpha) or pd.isna(T_g)):
                state_abbrev = str(d["state_abbrev"]) if "state_abbrev" in d.index and pd.notna(d["state_abbrev"]) else ""
                return SiteData(
                    geoid=geoid,
                    k=k,
                    alpha=alpha,
                    T_g=T_g,
                    climate_zone=climate_zone,
                    data_available=True,
                    state_abbrev=state_abbrev,
                )

    # ── Fallback: shallow SSURGO tract dataset ───────────────────────────
    thermal = pd.read_csv(thermal_csv, dtype={"geoid": str})
    t_row = thermal[thermal["geoid"] == geoid]
    if t_row.empty or c_row.empty:
        return SiteData(
            geoid=geoid,
            k=float("nan"),
            alpha=float("nan"),
            T_g=float("nan"),
            climate_zone=climate_zone,
            data_available=False,
        )

    t = t_row.iloc[0]
    return SiteData(
        geoid=geoid,
        k=float(t["k_wmpk"]),
        alpha=float(t["alpha_m2day"]),
        T_g=float(t["T_g_C"]),
        climate_zone=climate_zone,
        data_available=bool(t["data_available"]),
    )

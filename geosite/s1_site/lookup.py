"""Look up pre-computed soil thermal properties by census tract GEOID.

Reads data/public/thermal_by_tract.csv and data/public/climate_by_tract.csv.
These files are populated by the developer data pipeline (scripts/).
Returns SiteData with data_available=False when no SSURGO data exists for a tract.
"""

import pathlib
import pandas as pd
from geosite.models import SiteData

_DEFAULT_THERMAL = pathlib.Path(__file__).parents[2] / "data/public/thermal_by_tract.csv"
_DEFAULT_CLIMATE = pathlib.Path(__file__).parents[2] / "data/public/climate_by_tract.csv"


def lookup_by_geoid(
    geoid: str,
    thermal_csv: pathlib.Path = _DEFAULT_THERMAL,
    climate_csv: pathlib.Path = _DEFAULT_CLIMATE,
) -> SiteData:
    """Return SiteData for a census tract GEOID.

    When the GEOID is not in the CSV (no SSURGO coverage), returns a SiteData
    with data_available=False and NaN for numeric fields.
    """
    thermal = pd.read_csv(thermal_csv, dtype={"geoid": str})
    climate = pd.read_csv(climate_csv, dtype={"geoid": str})

    t_row = thermal[thermal["geoid"] == geoid]
    c_row = climate[climate["geoid"] == geoid]

    if t_row.empty or c_row.empty:
        return SiteData(
            geoid=geoid,
            k=float("nan"),
            alpha=float("nan"),
            T_g=float("nan"),
            climate_zone="",
            data_available=False,
        )

    t = t_row.iloc[0]
    return SiteData(
        geoid=geoid,
        k=float(t["k_wmpk"]),
        alpha=float(t["alpha_m2day"]),
        T_g=float(t["T_g_C"]),
        climate_zone=str(c_row.iloc[0]["climate_zone"]),
        data_available=bool(t["data_available"]),
    )

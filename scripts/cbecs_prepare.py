#!/usr/bin/env python3
"""Prepare CBECS 2018 office microdata for model training.

Input:  data/cbecs/cbecs2018_public.csv   (downloaded from EIA)
Output: data/cbecs/cbecs_office_clean.csv  (filtered, feature-engineered)

Run from geosite_advisor/:
    python scripts/cbecs_prepare.py
"""

import pathlib
import numpy as np
import pandas as pd

SRC = pathlib.Path("data/cbecs/cbecs2018_public.csv")
DST = pathlib.Path("data/cbecs/cbecs_office_clean.csv")

# CBECS YRCONC codes → numeric midpoint year
YRCONC_YEAR = {2: 1940, 3: 1952, 4: 1965, 5: 1975, 6: 1985, 7: 1995, 8: 2006, 9: 2015}


def main():
    df = pd.read_csv(SRC, low_memory=False)
    print(f"Loaded {len(df):,} rows from {SRC}")

    # Keep office buildings only (PBA=2: office/professional)
    df = df[df["PBA"] == 2].copy()
    print(f"After PBA=2 filter: {len(df):,}")

    # Require positive floor area and both heat/cool loads
    df = df[(df["SQFT"] > 0) & (df["MFHTBTU"] > 0) & (df["MFCLBTU"] > 0)].copy()
    print(f"After load filter (SQFT>0, MFHTBTU>0, MFCLBTU>0): {len(df):,}")

    # Drop extreme outliers (top 1% EUI — likely data errors)
    df["ht_eui"] = df["MFHTBTU"] / df["SQFT"]   # kBtu/ft²
    df["cl_eui"] = df["MFCLBTU"] / df["SQFT"]   # kBtu/ft²
    p99_ht = df["ht_eui"].quantile(0.99)
    p99_cl = df["cl_eui"].quantile(0.99)
    df = df[(df["ht_eui"] <= p99_ht) & (df["cl_eui"] <= p99_cl)].copy()
    print(f"After top-1% EUI outlier removal: {len(df):,}")

    # Features
    df["log_sqft"]   = np.log1p(df["SQFT"])
    df["yr_mid"]     = df["YRCONC"].map(YRCONC_YEAR).fillna(1990).astype(float)
    df["log_hdd65"]  = np.log1p(df["HDD65"].fillna(3000))
    df["log_cdd65"]  = np.log1p(df["CDD65"].fillna(1500))
    df["wlcns"]      = df["WLCNS"].fillna(1).astype(int)

    # Log targets (less sensitive to outliers, easier to model)
    df["log_ht_eui"] = np.log1p(df["ht_eui"])
    df["log_cl_eui"] = np.log1p(df["cl_eui"])

    keep = [
        "SQFT", "log_sqft", "yr_mid", "HDD65", "log_hdd65",
        "CDD65", "log_cdd65", "wlcns", "CENDIV", "FINALWT",
        "ht_eui", "cl_eui", "log_ht_eui", "log_cl_eui",
    ]
    out = df[keep].dropna(subset=["log_ht_eui", "log_cl_eui"])

    DST.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(DST, index=False)
    print(f"Saved {len(out):,} rows → {DST}")
    print(f"  Heat EUI [kBtu/ft²]: mean={out['ht_eui'].mean():.1f}, "
          f"median={out['ht_eui'].median():.1f}, p99={p99_ht:.1f}")
    print(f"  Cool EUI [kBtu/ft²]: mean={out['cl_eui'].mean():.1f}, "
          f"median={out['cl_eui'].median():.1f}, p99={p99_cl:.1f}")


if __name__ == "__main__":
    main()

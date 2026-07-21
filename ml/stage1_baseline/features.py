"""
ml/stage1_baseline/features.py
═══════════════════════════════════════════════════════════════════════════
Feature engineering pipeline for Stage 1 MLP.

Loads per-county data from various sources and merges into a single
feature matrix: data/ml/features_all.csv

Run from project root:
    python ml/stage1_baseline/features.py

Requires (in data/ml/):
    sgmc_by_county.csv          — rock class (from collect_sgmc.py)
    smuheatflow_clean.csv       — training labels (from collect_smuheatflow.py)

Optional (improves accuracy when available):
    prism_temp_by_county.csv    — mean annual temperature
    gravity_by_county.csv       — Bouguer gravity anomaly
═══════════════════════════════════════════════════════════════════════════
"""

import csv
import math
import pathlib

import numpy as np
import pandas as pd

ROOT    = pathlib.Path(__file__).parent.parent.parent
ML_DIR  = ROOT / "data" / "ml"
OUT_DIR = ROOT / "data" / "ml"

# ── Rock class encoding ───────────────────────────────────────────────────
# Based on USGS SGMC simplified lithology classes
# k_literature = median thermal conductivity from Clauser & Huenges (1995)
ROCK_CLASS = {
    0:  ("water_ice",          0.6),
    1:  ("alluvial_glacial",   1.8),
    2:  ("clay_shale",         1.5),
    3:  ("limestone_carbonate",2.5),
    4:  ("sandstone",          2.8),
    5:  ("granite_felsic",     3.2),
    6:  ("basalt_mafic",       1.8),
    7:  ("metamorphic",        2.6),
    8:  ("coal_organic",       0.3),
    9:  ("undifferentiated",   2.0),
}

COUNTY_CENTROID_CSV = ROOT / "data" / "research" / "subsurface" / "horizontal_shallow_thermal_by_county.csv"


def load_county_centroids() -> pd.DataFrame:
    """Load lat/lon centroids from SSURGO county list."""
    df = pd.read_csv(COUNTY_CENTROID_CSV, dtype={"county_fips": str})
    df = df[["county_fips", "lat_approx", "state_abbrev"]].copy()
    df.columns = ["county_fips", "lat", "state_abbrev"]
    # Approximate lon from state centroids (rough proxy; SGMC join will use actual lat/lon)
    return df


def load_sgmc(path: pathlib.Path) -> pd.DataFrame:
    """Load USGS SGMC rock class by county."""
    if not path.exists():
        print(f"WARNING: SGMC file not found at {path}. Rock class feature will be missing.")
        return pd.DataFrame(columns=["county_fips", "rock_class_id", "rock_class_name", "k_rock_lit"])
    df = pd.read_csv(path, dtype={"county_fips": str})
    if "rock_class_id" not in df.columns:
        df["rock_class_id"] = 9
    df["k_rock_lit"] = df["rock_class_id"].map(lambda i: ROCK_CLASS.get(int(i), (None, 2.0))[1])
    return df[["county_fips", "rock_class_id", "k_rock_lit"]]


def load_prism_temp(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["county_fips", "mean_annual_temp_c"])
    return pd.read_csv(path, dtype={"county_fips": str})[["county_fips", "mean_annual_temp_c"]]


def load_gravity(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["county_fips", "bouguer_anomaly_mgal"])
    return pd.read_csv(path, dtype={"county_fips": str})[["county_fips", "bouguer_anomaly_mgal"]]


def build_feature_matrix() -> pd.DataFrame:
    """Merge all feature sources into one county-level feature matrix."""
    base    = load_county_centroids()
    sgmc    = load_sgmc(ML_DIR / "sgmc_by_county.csv")
    prism   = load_prism_temp(ML_DIR / "prism_temp_by_county.csv")
    gravity = load_gravity(ML_DIR / "gravity_by_county.csv")

    df = base.merge(sgmc,    on="county_fips", how="left")
    df = df.merge(prism,     on="county_fips", how="left")
    df = df.merge(gravity,   on="county_fips", how="left")

    # Fill missing with reasonable defaults
    df["rock_class_id"]    = df["rock_class_id"].fillna(9).astype(int)
    df["k_rock_lit"]       = df["k_rock_lit"].fillna(2.0)
    df["mean_annual_temp_c"] = df["mean_annual_temp_c"].fillna(12.0)   # national avg
    df["bouguer_anomaly_mgal"] = df["bouguer_anomaly_mgal"].fillna(0.0)

    return df


def load_training_labels() -> pd.DataFrame:
    """Load SMU heat flow labels, spatial join to counties by nearest centroid."""
    smu_path = ML_DIR / "smuheatflow_clean.csv"
    if not smu_path.exists():
        print(f"WARNING: SMU data not found at {smu_path}")
        return pd.DataFrame(columns=["lat", "lon", "k_wmpk", "T_g_150m_C"])
    df = pd.read_csv(smu_path)
    df = df.dropna(subset=["k_wmpk"])
    return df


FEATURE_COLS = ["lat", "rock_class_id", "k_rock_lit", "mean_annual_temp_c", "bouguer_anomaly_mgal"]
# lon is omitted — rock class already encodes most of the EW geology variation


def get_feature_matrix() -> pd.DataFrame:
    """Return the feature matrix, building it if needed."""
    feat_path = ML_DIR / "features_all.csv"
    if feat_path.exists():
        return pd.read_csv(feat_path, dtype={"county_fips": str})
    df = build_feature_matrix()
    df.to_csv(feat_path, index=False)
    print(f"Feature matrix saved → {feat_path} ({len(df)} rows)")
    return df


if __name__ == "__main__":
    df = build_feature_matrix()
    out = ML_DIR / "features_all.csv"
    df.to_csv(out, index=False)
    print(f"Built feature matrix: {len(df)} counties")
    print(df[FEATURE_COLS].describe())

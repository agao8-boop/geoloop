"""
ml/stage1_baseline/predict.py
═══════════════════════════════════════════════════════════════════════════
Inference for the Stage 1 MLP — given a county FIPS code (or lat/lon),
return predicted k, T_g, α.

This module is imported by the Flask API (app.py) to serve ML predictions.
It falls back to the static CSV (data/public/ml_thermal_by_county.csv)
if the models are not trained yet, and further falls back to the SSURGO
horizontal data as a last resort.

Usage (standalone):
    python ml/stage1_baseline/predict.py --fips 17031
    python ml/stage1_baseline/predict.py --lat 41.8 --state IL
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import pathlib
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

PRED_CSV  = ROOT / "data" / "public"  / "ml_thermal_by_county.csv"
FALLBACK_CSV = ROOT / "data" / "research" / "subsurface" / "horizontal_shallow_thermal_by_county.csv"

_cache: Optional[dict] = None


def _load_predictions() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    import csv

    # Try ML predictions first
    if PRED_CSV.exists():
        with open(PRED_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
        _cache = {r["county_fips"]: r for r in rows}
        return _cache

    # Fallback to SSURGO horizontal data
    if FALLBACK_CSV.exists():
        with open(FALLBACK_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
        _cache = {}
        for r in rows:
            fips = r.get("county_fips", "")
            if fips:
                _cache[fips] = {
                    "county_fips": fips,
                    "k_wmpk":      r.get("k_wmpk", "1.5"),
                    "T_g_C":       r.get("T_g_C", "12.0"),
                    "alpha_m2day": r.get("alpha_m2day", "0.07"),
                    "stage":       "0_fallback_ssurgo",
                }
        return _cache

    return {}


def predict_by_fips(county_fips: str) -> dict:
    """Return thermal predictions for a county FIPS code."""
    fips = str(county_fips).zfill(5)
    data = _load_predictions()

    if fips in data:
        row = data[fips]
        return {
            "county_fips":  fips,
            "k_wmpk":       float(row.get("k_wmpk") or 1.5),
            "T_g_C":        float(row.get("T_g_C")  or 12.0),
            "alpha_m2day":  float(row.get("alpha_m2day") or 0.07),
            "stage":        row.get("stage", 1),
            "source":       "ml_stage1" if PRED_CSV.exists() else "ssurgo_fallback",
        }

    # No data for this county — return national average with flag
    return {
        "county_fips":  fips,
        "k_wmpk":       1.5,
        "T_g_C":        12.0,
        "alpha_m2day":  0.07,
        "stage":        "national_avg",
        "source":       "fallback",
        "warning":      "No county data available. Using national average. Accuracy low.",
    }


def predict_from_features(features: dict) -> dict:
    """
    Online inference from raw features using the trained MLP model.
    Used for real-time prediction when county FIPS is known but CSV is stale.
    """
    import numpy as np

    try:
        from ml.stage1_baseline.model import derive_alpha, load_models
        from ml.stage1_baseline.features import FEATURE_COLS
        k_model, tg_model = load_models()
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLS]])
        k  = float(k_model.predict(X)[0])
        tg = float(tg_model.predict(X)[0])
        rc = int(features.get("rock_class_id", 9))
        alpha = derive_alpha(k, rc)
        return {
            "k_wmpk":      round(k, 3),
            "T_g_C":       round(tg, 2),
            "alpha_m2day": round(alpha, 6),
            "stage":       1,
            "source":      "ml_stage1_realtime",
        }
    except FileNotFoundError:
        return predict_by_fips(features.get("county_fips", "00000"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fips",  help="5-digit county FIPS code")
    parser.add_argument("--lat",   type=float, help="Latitude")
    parser.add_argument("--state", help="State abbreviation")
    args = parser.parse_args()

    if args.fips:
        result = predict_by_fips(args.fips)
        print(result)
    elif args.lat and args.state:
        print(f"TODO: nearest-county lookup for lat={args.lat} state={args.state}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

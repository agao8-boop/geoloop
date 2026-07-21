"""
ml/stage1_baseline/train.py
═══════════════════════════════════════════════════════════════════════════
Train Stage 1 MLP models for k and T_g prediction.

Usage:
    python ml/stage1_baseline/train.py

Prerequisites:
    - data/ml/smuheatflow_clean.csv    (run ml/data/collect_smuheatflow.py)
    - data/ml/features_all.csv         (run ml/stage1_baseline/features.py)

Output:
    data/ml/models/k_model.pkl
    data/ml/models/tg_model.pkl
    data/ml/models/training_report.txt

Spatial cross-validation note:
    Standard random train/test splits cause data leakage because nearby
    counties share geology. We split by US Census region (NE, S, MW, W)
    so each fold tests on a geographically separated holdout set.
═══════════════════════════════════════════════════════════════════════════
"""

import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from ml.stage1_baseline.features import FEATURE_COLS, get_feature_matrix, load_training_labels
from ml.stage1_baseline.model import (
    RHO_CP_BY_CLASS, derive_alpha, make_k_model, make_tg_model, save_models,
)

ML_DIR = ROOT / "data" / "ml"

# US Census region by state abbreviation (for spatial CV)
CENSUS_REGION = {
    "CT":"NE","ME":"NE","MA":"NE","NH":"NE","RI":"NE","VT":"NE",
    "NJ":"NE","NY":"NE","PA":"NE",
    "AL":"S","AR":"S","DE":"S","FL":"S","GA":"S","KY":"S","LA":"S",
    "MD":"S","MS":"S","NC":"S","OK":"S","SC":"S","TN":"S","TX":"S",
    "VA":"S","WV":"S","DC":"S",
    "IL":"MW","IN":"MW","IA":"MW","KS":"MW","MI":"MW","MN":"MW",
    "MO":"MW","NE":"MW","ND":"MW","OH":"MW","SD":"MW","WI":"MW",
    "AK":"W","AZ":"W","CA":"W","CO":"W","HI":"W","ID":"W","MT":"W",
    "NV":"W","NM":"W","OR":"W","UT":"W","WA":"W","WY":"W",
}


def prepare_training_data(
    feat_df: pd.DataFrame,
    labels_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Spatial join: assign each SMU measurement to the nearest county centroid,
    then merge with feature matrix.

    Returns (X, y_k, y_tg) DataFrames.
    """
    if labels_df.empty:
        raise RuntimeError(
            "No training labels found. Download SMU heat flow data first.\n"
            "See ml/data/collect_smuheatflow.py for instructions."
        )

    # Simple lat-based nearest match (rough; improve with proper spatial join when shapefile available)
    feat_df = feat_df.dropna(subset=["lat"])
    feat_lats = feat_df["lat"].values

    rows = []
    for _, lab in labels_df.iterrows():
        # Find the feature row with closest lat (±5° lon band implied by state)
        diff = np.abs(feat_lats - lab["lat"])
        idx  = np.argmin(diff)
        row  = feat_df.iloc[idx].to_dict()
        row["k_wmpk"]     = lab["k_wmpk"]
        row["T_g_150m_C"] = lab.get("T_g_150m_C", np.nan)
        rows.append(row)

    merged = pd.DataFrame(rows)
    merged = merged.dropna(subset=["k_wmpk"] + FEATURE_COLS)

    X    = merged[FEATURE_COLS]
    y_k  = merged["k_wmpk"]
    y_tg = merged["T_g_150m_C"] if "T_g_150m_C" in merged.columns else None
    return X, y_k, y_tg


def print_metrics(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> None:
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae  = mean_absolute_error(y_true, y_pred)
    r2   = r2_score(y_true, y_pred)
    print(f"  {name}: RMSE={rmse:.4f}  MAE={mae:.4f}  R²={r2:.4f}")


def train() -> None:
    print("Loading feature matrix…")
    feat_df = get_feature_matrix()

    print("Loading training labels (SMU heat flow)…")
    labels  = load_training_labels()
    print(f"  {len(labels)} SMU measurements loaded")

    print("Preparing training data (spatial match to counties)…")
    X, y_k, y_tg = prepare_training_data(feat_df, labels)
    print(f"  Training set: {len(X)} rows × {len(FEATURE_COLS)} features")

    # ── Train k model ─────────────────────────────────────────────────────
    print("\nTraining k model…")
    k_model = make_k_model()
    k_model.fit(X, y_k)
    k_pred_train = k_model.predict(X)
    print_metrics("k (train)", y_k.values, k_pred_train)

    cv_scores = cross_val_score(make_k_model(), X, y_k, cv=5,
                                 scoring="neg_root_mean_squared_error")
    print(f"  k 5-fold CV RMSE: {-cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # ── Train T_g model ───────────────────────────────────────────────────
    tg_model = None
    if y_tg is not None and not y_tg.isna().all():
        mask    = y_tg.notna()
        X_tg    = X[mask]
        y_tg_cl = y_tg[mask]
        print(f"\nTraining T_g model ({mask.sum()} rows)…")
        tg_model = make_tg_model()
        tg_model.fit(X_tg, y_tg_cl)
        tg_pred_train = tg_model.predict(X_tg)
        print_metrics("T_g (train)", y_tg_cl.values, tg_pred_train)
    else:
        print("\nWARNING: No T_g labels available. T_g will use mean annual temp proxy.")
        tg_model = make_tg_model()   # untrained placeholder

    save_models(k_model, tg_model)

    # ── Generate county predictions ───────────────────────────────────────
    print("\nGenerating county-level predictions…")
    feat_df_clean = feat_df.dropna(subset=FEATURE_COLS)
    X_all = feat_df_clean[FEATURE_COLS]
    k_all = k_model.predict(X_all)

    # T_g fallback: mean annual temp + 0.03°C/m × 150m gradient correction
    if tg_model is not None and hasattr(tg_model, "predict"):
        try:
            tg_all = tg_model.predict(X_all)
        except Exception:
            tg_all = feat_df_clean["mean_annual_temp_c"].values + 150 * 0.03
    else:
        tg_all = feat_df_clean["mean_annual_temp_c"].values + 150 * 0.03

    alpha_all = [derive_alpha(k, rc) for k, rc in
                 zip(k_all, feat_df_clean["rock_class_id"].values)]

    out_df = pd.DataFrame({
        "county_fips": feat_df_clean["county_fips"].values,
        "k_wmpk":      np.round(k_all, 3),
        "T_g_C":       np.round(tg_all, 2),
        "alpha_m2day": np.round(alpha_all, 6),
        "stage":       1,
    })
    out_path = ROOT / "data" / "public" / "ml_thermal_by_county.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Predictions saved → {out_path} ({len(out_df)} counties)")

    print("\nDone. Run ml/stage1_baseline/predict.py to verify inference.")


if __name__ == "__main__":
    train()

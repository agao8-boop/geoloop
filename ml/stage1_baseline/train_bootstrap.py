"""
ml/stage1_baseline/train_bootstrap.py
═══════════════════════════════════════════════════════════════════════════
Train Stage 1 MLP on bootstrap training data (shallow-soil proxy estimates).

Run when SMU heat flow database is NOT yet available.
When SMU data IS available, run train.py instead (higher accuracy labels).

Usage:
    python ml/stage1_baseline/train_bootstrap.py

Output:
    data/ml/models/k_model.pkl
    data/ml/models/tg_model.pkl
    data/public/ml_thermal_by_county.csv   ← plugs into the sizing tool
═══════════════════════════════════════════════════════════════════════════
"""

import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from sklearn.model_selection import KFold, cross_val_predict

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from ml.stage1_baseline.model import (
    derive_alpha, make_k_model, make_tg_model, save_models,
)

TRAIN_CSV = ROOT / "data" / "ml" / "bootstrap_training.csv"
OUT_CSV   = ROOT / "data" / "public" / "ml_thermal_by_county.csv"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

# ── Feature columns ────────────────────────────────────────────────────────
# These match what predict.py will supply at inference time
FEATURE_COLS = ["lat", "rock_class_id", "sand_pct", "clay_pct", "n_porosity", "mean_annual_temp_C"]
TARGET_K  = "k_deep_est"
TARGET_TG = "T_g_150m_est"


def print_metrics(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> None:
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae  = mean_absolute_error(y_true, y_pred)
    r2   = r2_score(y_true, y_pred)
    print(f"  {name:12s} RMSE={rmse:.4f}  MAE={mae:.4f}  R²={r2:.4f}")


def main() -> None:
    print("Loading bootstrap training data…")
    df = pd.read_csv(TRAIN_CSV, dtype={"county_fips": str, "rock_class_id": int})
    df = df.dropna(subset=FEATURE_COLS + [TARGET_K, TARGET_TG])
    print(f"  {len(df)} training rows × {len(FEATURE_COLS)} features")
    print(f"  k_deep range:   {df[TARGET_K].min():.2f} – {df[TARGET_K].max():.2f} W/m·K")
    print(f"  T_g_150m range: {df[TARGET_TG].min():.1f} – {df[TARGET_TG].max():.1f} °C")

    X    = df[FEATURE_COLS].values
    y_k  = df[TARGET_K].values
    y_tg = df[TARGET_TG].values

    # ── Train k model ──────────────────────────────────────────────────────
    print("\nTraining k model (MLP)…")
    k_model = make_k_model()
    k_model.fit(X, y_k)

    # 5-fold cross-validation (spatial: shuffle=True since we lack geographic split)
    cv_k = KFold(n_splits=5, shuffle=True, random_state=42)
    k_cv_pred = cross_val_predict(make_k_model(), X, y_k, cv=cv_k)
    print("  Train set:")
    print_metrics("k", y_k, k_model.predict(X))
    print("  5-fold CV:")
    print_metrics("k_cv", y_k, k_cv_pred)

    # ── Train T_g model ────────────────────────────────────────────────────
    print("\nTraining T_g model (MLP)…")
    tg_model = make_tg_model()
    tg_model.fit(X, y_tg)

    cv_tg = KFold(n_splits=5, shuffle=True, random_state=42)
    tg_cv_pred = cross_val_predict(make_tg_model(), X, y_tg, cv=cv_tg)
    print("  Train set:")
    print_metrics("T_g", y_tg, tg_model.predict(X))
    print("  5-fold CV:")
    print_metrics("T_g_cv", y_tg, tg_cv_pred)

    # ── Save models ────────────────────────────────────────────────────────
    save_models(k_model, tg_model)

    # ── Generate county predictions ────────────────────────────────────────
    print("\nGenerating county-level predictions for all 3,193 counties…")
    k_pred  = k_model.predict(X)
    tg_pred = tg_model.predict(X)

    alpha_pred = [
        derive_alpha(float(k), int(rc))
        for k, rc in zip(k_pred, df["rock_class_id"].values)
    ]

    out_df = pd.DataFrame({
        "county_fips":  df["county_fips"].values,
        "state_abbrev": df["state_abbrev"].values,
        "k_wmpk":       np.round(k_pred, 3),
        "T_g_C":        np.round(tg_pred, 2),
        "alpha_m2day":  np.round(alpha_pred, 6),
        "rock_class":   df["rock_class_id"].values,
        "stage":        "1_bootstrap",
        "data_quality": "shallow_proxy",
    })
    out_df.to_csv(OUT_CSV, index=False)
    print(f"Predictions saved → {OUT_CSV} ({len(out_df)} counties)")

    # ── Summary stats ──────────────────────────────────────────────────────
    print("\n── Prediction summary ──────────────────────────────────────────")
    print(f"  k:        mean={np.mean(k_pred):.2f}  std={np.std(k_pred):.2f}  "
          f"[{np.min(k_pred):.2f}, {np.max(k_pred):.2f}] W/m·K")
    print(f"  T_g_150m: mean={np.mean(tg_pred):.1f}  std={np.std(tg_pred):.1f}  "
          f"[{np.min(tg_pred):.1f}, {np.max(tg_pred):.1f}] °C")
    print(f"  alpha:    mean={np.mean(alpha_pred):.5f} m²/day")
    print("\nDone. Stage 1 bootstrap model is live.")
    print("To improve: download SMU heat flow CSV → run ml/data/collect_smuheatflow.py → run train.py")


if __name__ == "__main__":
    main()

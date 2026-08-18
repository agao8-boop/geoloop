#!/usr/bin/env python3
"""Train KNN + XGBoost models on CBECS office EUI data.

Input:  data/cbecs/cbecs_office_clean.csv   (from cbecs_prepare.py)
Output: data/cbecs/models/heat_knn.pkl
        data/cbecs/models/heat_xgb.pkl
        data/cbecs/models/cool_knn.pkl
        data/cbecs/models/cool_xgb.pkl

Run from geosite_advisor/:
    python scripts/cbecs_train.py
"""

import pathlib
import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_percentage_error, r2_score
from xgboost import XGBRegressor

SRC    = pathlib.Path("data/cbecs/cbecs_office_clean.csv")
OUTDIR = pathlib.Path("data/cbecs/models")

FEATURES = ["log_sqft", "yr_mid", "log_hdd65", "log_cdd65", "wlcns"]


def _eval(name: str, y_true, y_pred):
    r2   = r2_score(y_true, y_pred)
    mape = mean_absolute_percentage_error(np.expm1(y_true), np.expm1(y_pred))
    print(f"  {name}: R²={r2:.3f}  MAPE={100*mape:.1f}%")


def train_and_save(df: pd.DataFrame, log_target: str, label: str):
    X = df[FEATURES].values
    y = df[log_target].values

    X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.2, random_state=42)

    knn = Pipeline([
        ("scaler", StandardScaler()),
        ("knn",   KNeighborsRegressor(n_neighbors=10, weights="distance")),
    ])
    knn.fit(X_tr, y_tr)
    _eval(f"{label}/knn  val", y_va, knn.predict(X_va))

    xgb = XGBRegressor(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        objective="reg:squarederror", random_state=42, verbosity=0,
    )
    xgb.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    _eval(f"{label}/xgb  val", y_va, xgb.predict(X_va))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for model, fname in [(knn, f"{label}_knn.pkl"), (xgb, f"{label}_xgb.pkl")]:
        with open(OUTDIR / fname, "wb") as f:
            pickle.dump(model, f)
        print(f"  Saved → {OUTDIR / fname}")


def main():
    df = pd.read_csv(SRC)
    print(f"Loaded {len(df):,} rows from {SRC}")

    print("\n--- Heating EUI model ---")
    train_and_save(df, "log_ht_eui", "heat")

    print("\n--- Cooling EUI model ---")
    train_and_save(df, "log_cl_eui", "cool")

    print("\nDone.")


if __name__ == "__main__":
    main()

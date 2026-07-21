"""
ml/stage1_baseline/model.py
═══════════════════════════════════════════════════════════════════════════
Stage 1 MLP model definition using scikit-learn.

Two separate regressors:
  - k_model   → predicts thermal conductivity k [W/m·K]
  - Tg_model  → predicts ground temperature T_g [°C] at 150m depth

α (thermal diffusivity) is derived from k and volumetric heat capacity ρCp,
where ρCp is looked up by rock class.

Models are saved as .pkl files to data/ml/models/ after training.
═══════════════════════════════════════════════════════════════════════════
"""

import pathlib
import pickle

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT      = pathlib.Path(__file__).parent.parent.parent
MODEL_DIR = ROOT / "data" / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ── Volumetric heat capacity ρCp by rock class [MJ/m³·K] ─────────────────
# From ASHRAE 2019 Handbook; used to derive α = k / ρCp
RHO_CP_BY_CLASS = {
    0:  0.6 * 4.18,  # water
    1:  2.1,         # alluvial/glacial
    2:  2.4,         # clay/shale
    3:  2.2,         # limestone
    4:  2.1,         # sandstone
    5:  2.1,         # granite
    6:  2.3,         # basalt
    7:  2.5,         # metamorphic
    8:  1.5,         # coal
    9:  2.1,         # undifferentiated
}


def make_k_model() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("mlp", MLPRegressor(
            hidden_layer_sizes=(128, 64, 32),
            activation="relu",
            solver="adam",
            max_iter=2000,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=30,
            random_state=42,
            verbose=False,
        )),
    ])


def make_tg_model() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("mlp", MLPRegressor(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",
            max_iter=2000,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=30,
            random_state=42,
            verbose=False,
        )),
    ])


def derive_alpha(k: float, rock_class: int) -> float:
    """Compute thermal diffusivity α [m²/day] from k and ρCp."""
    rho_cp_mj = RHO_CP_BY_CLASS.get(int(rock_class), 2.1)  # MJ/m³·K
    rho_cp_wm = rho_cp_mj * 1e6                              # J/m³·K = W·s/m³·K
    alpha_m2s  = k / rho_cp_wm                               # m²/s
    return alpha_m2s * 86400                                  # → m²/day


def save_models(k_model: Pipeline, tg_model: Pipeline) -> None:
    with open(MODEL_DIR / "k_model.pkl", "wb") as f:
        pickle.dump(k_model, f)
    with open(MODEL_DIR / "tg_model.pkl", "wb") as f:
        pickle.dump(tg_model, f)
    print(f"Models saved to {MODEL_DIR}/")


def load_models() -> tuple[Pipeline, Pipeline]:
    k_path  = MODEL_DIR / "k_model.pkl"
    tg_path = MODEL_DIR / "tg_model.pkl"
    if not k_path.exists() or not tg_path.exists():
        raise FileNotFoundError(
            f"Trained models not found in {MODEL_DIR}/. "
            "Run ml/stage1_baseline/train.py first."
        )
    with open(k_path, "rb")  as f: k_model  = pickle.load(f)
    with open(tg_path, "rb") as f: tg_model = pickle.load(f)
    return k_model, tg_model

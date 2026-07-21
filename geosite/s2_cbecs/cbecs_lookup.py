"""CBECS-based load prediction for GSHP borefield sizing.

Predicts annual heating/cooling EUI from CBECS 2018 office survey data,
then converts to ASHRAE three-pulse loads by scaling DOE prototype loads.

Requires trained models in data/cbecs/models/ (run scripts/cbecs_train.py).

Public API
----------
predict_loads(floor_area_m2, hdd65, cdd65, year_built, climate_zone,
              wlcns=1, building_type='medium_office') → LoadPulses
models_available() → bool
"""

import json
import math
import pathlib
import pickle
from functools import lru_cache
from typing import Optional

import numpy as np

from geosite.models import LoadPulses
from geosite.s2_simulation.lookup import lookup_prototype_loads

_ROOT   = pathlib.Path(__file__).parents[2]
_MODELS = _ROOT / "data" / "cbecs" / "models"
_PROTO  = _ROOT / "data" / "public" / "prototype_loads.json"

FEATURES = ["log_sqft", "yr_mid", "log_hdd65", "log_cdd65", "wlcns"]
_KBTU_TO_KWH = 0.293071   # 1 kBtu = 0.293071 kWh
_FT2_PER_M2  = 10.7639


@lru_cache(maxsize=1)
def _load_models() -> Optional[dict]:
    fnames = ["heat_knn.pkl", "heat_xgb.pkl", "cool_knn.pkl", "cool_xgb.pkl"]
    if not all((_MODELS / fn).exists() for fn in fnames):
        return None
    models = {}
    for fn in fnames:
        key = fn.replace(".pkl", "").replace("_", "/", 1)  # e.g. "heat/knn"
        with open(_MODELS / fn, "rb") as f:
            models[key] = pickle.load(f)
    return models


@lru_cache(maxsize=1)
def _proto_ann_kwh(building_type: str = "medium_office") -> dict:
    """Return {climate_zone: (ann_heat_kWh, ann_cool_kWh)} from prototype JSON."""
    data = json.loads(_PROTO.read_text())
    bt   = data.get(building_type, {})
    out  = {}
    for cz, entry in bt.items():
        if cz.startswith("_"):
            continue
        out[cz] = (float(entry.get("ann_heat_kWh", 0) or 0),
                   float(entry.get("ann_cool_kWh", 0) or 0))
    return out


def _predict_eui(models, log_sqft, yr_mid, log_hdd65, log_cdd65, wlcns):
    """Return (heat_eui_kBtu_ft2, cool_eui_kBtu_ft2) as KNN+XGB ensemble."""
    x = np.array([[log_sqft, yr_mid, log_hdd65, log_cdd65, wlcns]])
    ht = 0.5 * (models["heat/knn"].predict(x)[0] + models["heat/xgb"].predict(x)[0])
    cl = 0.5 * (models["cool/knn"].predict(x)[0] + models["cool/xgb"].predict(x)[0])
    return math.expm1(max(ht, 0)), math.expm1(max(cl, 0))


def models_available() -> bool:
    return _load_models() is not None


def predict_loads(
    floor_area_m2: float,
    hdd65: float,
    cdd65: float,
    year_built: int,
    climate_zone: str,
    wlcns: int = 1,
    building_type: str = "medium_office",
) -> LoadPulses:
    """Predict ASHRAE three-pulse ground loads using CBECS EUI models.

    Scales DOE prototype loads by the ratio (CBECS predicted annual kWh /
    prototype annual kWh). Sign convention matches prototype — inherited from
    lookup_prototype_loads.

    Raises RuntimeError if models haven't been trained.
    """
    models = _load_models()
    if models is None:
        raise RuntimeError(
            "CBECS models not found in data/cbecs/models/. Run:\n"
            "  python scripts/cbecs_prepare.py && python scripts/cbecs_train.py"
        )

    # --- Predict EUI from CBECS model ---
    floor_ft2 = floor_area_m2 * _FT2_PER_M2
    x = [
        math.log1p(floor_ft2),
        float(max(1930, min(2025, year_built))),
        math.log1p(max(0.0, hdd65)),
        math.log1p(max(0.0, cdd65)),
        int(wlcns),
    ]
    ht_eui, cl_eui = _predict_eui(models, *x)

    # --- Convert EUI → annual kWh ---
    pred_heat_kWh = ht_eui * floor_ft2 * _KBTU_TO_KWH
    pred_cool_kWh = cl_eui * floor_ft2 * _KBTU_TO_KWH

    # --- Look up prototype loads for this climate zone ---
    proto = lookup_prototype_loads(building_type, climate_zone,
                                   target_area_m2=floor_area_m2)
    ann   = _proto_ann_kwh(building_type)

    if climate_zone not in ann:
        # Climate zone not in table — return prototype unscaled
        return proto

    proto_heat_kWh, proto_cool_kWh = ann[climate_zone]

    # --- Scale prototype three-pulse loads ---
    # Determine dominant mode from prototype annual kWh.
    # Scale dominant-mode loads by ratio of predicted to prototype annual energy.
    # Non-dominant mode is also scaled independently.
    heat_scale = pred_heat_kWh / proto_heat_kWh if proto_heat_kWh > 0 else 1.0
    cool_scale = pred_cool_kWh / proto_cool_kWh if proto_cool_kWh > 0 else 1.0

    # Both-mode peaks scale independently
    q_h_heat = (proto.q_h_heat * heat_scale) if proto.q_h_heat == proto.q_h_heat else proto.q_h_heat
    q_m_heat = (proto.q_m_heat * heat_scale) if proto.q_m_heat == proto.q_m_heat else proto.q_m_heat
    q_h_cool = (proto.q_h_cool * cool_scale) if proto.q_h_cool == proto.q_h_cool else proto.q_h_cool
    q_m_cool = (proto.q_m_cool * cool_scale) if proto.q_m_cool == proto.q_m_cool else proto.q_m_cool

    # For the single worst-case pulses (q_h, q_m, q_y), scale by the
    # dominant-mode scale factor.  Dominant mode = larger annual energy.
    if proto_heat_kWh >= proto_cool_kWh:
        dom_scale = heat_scale
    else:
        dom_scale = cool_scale

    return LoadPulses(
        q_h=proto.q_h * dom_scale,
        q_m=proto.q_m * dom_scale,
        q_y=proto.q_y * dom_scale,
        q_h_heat=q_h_heat,
        q_m_heat=q_m_heat,
        q_h_cool=q_h_cool,
        q_m_cool=q_m_cool,
    )

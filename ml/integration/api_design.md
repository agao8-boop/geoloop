# ML Integration — Flask API Design

## Current API Endpoints (Research Data)

| Endpoint | Data | Use |
|----------|------|-----|
| `GET /api/county_thermal` | SSURGO horizontal (0–2m) | Horizontal closed-loop screening |
| `GET /api/openloop_wells` | WQP groundwater wells | Open-loop screening |

## Planned ML Endpoints (Stage 1)

### `GET /api/ml/thermal?fips=17031`
Returns ML-predicted thermal properties for a county.

```json
{
  "county_fips": "17031",
  "k_wmpk": 2.14,
  "T_g_C": 11.8,
  "alpha_m2day": 0.0821,
  "stage": 1,
  "source": "ml_stage1",
  "model_version": "1.0.0",
  "confidence": "medium"
}
```

**Fallback chain:**
1. `data/public/ml_thermal_by_county.csv` (Stage 1 MLP predictions, if trained)
2. `data/research/subsurface/horizontal_shallow_thermal_by_county.csv` (SSURGO proxy)
3. National average (k=1.5, T_g=12.0) with warning flag

This is implemented in `ml/stage1_baseline/predict.py:predict_by_fips()`.

### `GET /api/ml/thermal?lat=41.87&lon=-87.63`
Returns predictions for the nearest county given coordinates.
Used in the s1_site pipeline step when geocoding returns lat/lon before FIPS lookup.

## Integration with Sizing Pipeline

The s1_site pipeline stage calls:
```python
from ml.stage1_baseline.predict import predict_by_fips
result = predict_by_fips(county_fips)
k     = result["k_wmpk"]      # W/m·K → into s4_sizing (Philippe eq.)
T_g   = result["T_g_C"]       # °C   → into s4_sizing as ground temp
alpha = result["alpha_m2day"]  # m²/day → into s4_sizing for transient term
```

## Dev Dashboard Display (Stage 1)

The dev dashboard `GET /dev` should show:
- Current ML stage active (1, 2, or 3)
- Training data count (how many SMU + TRT points)
- Cross-validation RMSE for k and T_g
- County-level k prediction map (replaces SSURGO map for vertical system)
- Feature importance bar chart (which input mattered most)
- Comparison scatter: ML predicted k vs. nearest TRT measurement

## User Tool Display

User sees (in the result card):
- "Subsurface data: estimated from geological survey data"  ← not "AI" language
- The actual k value and derived borehole length L
- Confidence indicator: high/medium/low based on data density in region

User does NOT see: which stage, which model, training set details.

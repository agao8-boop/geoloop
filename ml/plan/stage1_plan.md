# Stage 1 — Baseline MLP Plan
**Goal:** Working county-level k, T_g, α predictions in the tool as fast as possible.
**Motto:** Solid but not perfect. The method is refinable; get it into the pipeline first.

---

## What We're Predicting

| Output | Symbol | Unit | Why it matters |
|--------|--------|------|----------------|
| Thermal conductivity | k | W/m·K | Primary driver of borehole length L in Philippe eq. |
| Ground temperature | T_g | °C | Baseline heat pump works against |
| Thermal diffusivity | α | m²/day | Transient g-function response |

For Stage 1, **T_g** is the easiest (well-correlated with mean annual climate + depth correction).
**k** is the hardest (depends on rock mineralogy; most important to get right).
**α** is derived: α = k / (ρCp), and ρCp can be estimated from rock class.

## Input Features

| Feature | Source | Format | Notes |
|---------|--------|--------|-------|
| Latitude | — | float | Geographic proxy for climate + geology province |
| Longitude | — | float | " |
| Elevation [m] | USGS 3DEP (via API) | float | Proxy for topographic setting |
| Rock class | USGS SGMC | int (0–9) | Most important predictor of k |
| Mean annual temperature [°C] | NOAA PRISM | float | Primary T_g driver at shallow depth |
| Bouguer gravity anomaly [mGal] | USGS | float | Proxy for crustal density → rock type |
| Magnetic anomaly [nT] | USGS | float | Igneous/metamorphic indicator |
| Sediment thickness [km] | USGS | float | Depth to bedrock |

**Rock class encoding** (from USGS SGMC simplified):
0=water/ice, 1=alluvial/glacial, 2=clay/shale, 3=limestone/carbonate,
4=sandstone/siltstone, 5=granite/felsic, 6=basalt/mafic, 7=metamorphic,
8=coal/organic, 9=mixed/undifferentiated

## Training Data

### Primary: SMU Geothermal Heat Flow Database
- **What:** ~35,000 US borehole heat flow measurements with latitude, longitude,
  temperature gradient [°C/km], and often thermal conductivity k of rock samples
- **Access:** Downloadable CSV from SMU Geothermal Lab website; see data/collect_smuheatflow.py
- **Derived from:** q = k × (dT/dz)  →  if both q and dT/dz are known, solve for k
  If only dT/dz known: k estimated from rock class literature value → T_g = T_surface + dT/dz × depth
- **Target from this source:** T_g directly; k indirectly

### Secondary: Published Thermal Response Test (TRT) Database
- **What:** Short-duration (48–72h) borehole heating tests that directly measure in-situ k
  Gives the ground truth k values we need most
- **Available sources:**
  - Oregon IGSHPA TRT database (~80 PNW sites)
  - Minnesota GSHP program reported TRT values (~60 sites)
  - Published academic papers (Spitler & Gehlin 2015 global TRT database = ~500 values)
  - ASHRAE Handbook of HVAC Applications Appendix (rock type k table — for validation)
- **Expected total:** ~300–800 US TRT measurements after literature mining
- **Target from this source:** k directly (best quality labels)

### Derived Target: α
- α = k / (ρCp)
- ρCp by rock class (literature): granite 2.1 MJ/m³·K, limestone 2.2, sandstone 2.1,
  shale 2.4, clay 2.6, glacial till 2.1 MJ/m³·K
- So α follows directly from predicted k + rock class assignment

## Model Architecture

**scikit-learn MLPRegressor** — chosen for Stage 1 because:
- No GPU needed; trains in seconds on our ~500 point dataset
- Built into existing venv (sklearn already installed)
- Easy cross-validation with sklearn API
- Good enough for 8 tabular features; CNNs are overkill at this stage

```python
MLPRegressor(
    hidden_layer_sizes=(128, 64, 32),
    activation='relu',
    max_iter=1000,
    early_stopping=True,
    validation_fraction=0.15,
    random_state=42,
)
```

Multi-output: train separate models for k and T_g (cleaner than multi-output).
α derived from k prediction (not separately trained).

## Validation Strategy

- **Leave-one-out cross-validation** on county level (not random split, to avoid
  spatial leakage where nearby counties are correlated)
- **Metrics:** RMSE, MAE, R² for k and T_g
- **Baseline to beat:** Constant prediction = dataset mean (k≈1.5, T_g≈12°C)
- **Acceptable error for tool use:** k within ±0.3 W/m·K (~20%), T_g within ±2°C

## What "Into the Tool" Looks Like

After training, `predict.py` produces a county-level CSV:
  `data/public/ml_thermal_by_county.csv` (columns: county_fips, k, T_g, alpha, confidence)

The existing `s1_site/lookup.py` reads this instead of `thermal_by_tract.csv`.
Upgrade path: census-tract level when Stage 2 CNN is ready.

## Timeline Estimate

| Task | Effort |
|------|--------|
| Download + clean SMU heat flow data | 1–2 days |
| Spatial join with USGS SGMC rock classes | 1 day |
| Feature engineering + normalize | 0.5 days |
| Train MLP + cross-validate | 0.5 days |
| Generate prediction CSV + plug into tool | 0.5 days |
| **Total** | **~4 days** |

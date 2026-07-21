# GeoSite Advisor — Machine Learning Pipeline

## Purpose

Replace the lookup-table approach to subsurface thermal properties with a
neural network that can estimate **k [W/m·K]**, **α [m²/day]**, and **T_g [°C]**
at any US location from publicly available geological and geophysical observables.

This directly enables the vertical closed-loop sizing pipeline (s1_site → s4_sizing)
to work for any location without requiring a local Thermal Response Test.

## Why a Neural Network?

The SSURGO data (0–2 m) cannot serve vertical boreholes (30–150 m).
At borehole depth, thermal properties are determined by **bedrock lithology**,
not surface soil — and the relationship between observable surface proxies
(geology maps, gravity, magnetic anomalies, elevation) and subsurface thermal
properties is non-linear and spatially correlated. A neural network can learn
this mapping from sparse direct measurements.

This matches the proposal's stated goal: "use neural networks for more precise
calculation of subsurface conditions."

## Three-Stage Plan

```
Stage 1 — Baseline MLP (NOW)
  Input:  lat, lon, elevation, USGS rock class, mean annual temp, gravity
  Output: k, T_g, α  (county-level)
  Train:  SMU heat flow database + published TRT values (~500–1000 points)
  Goal:   Prove the approach works; get into the tool quickly.
  File:   ml/stage1_baseline/

Stage 2 — CNN on Geospatial Rasters (NEXT)
  Input:  N×N patch from stacked raster layers (geology, gravity, magnetics, DEM)
  Output: k, T_g, α  (higher spatial resolution)
  Train:  Same + additional borehole temperature logs (NOAA/USGS)
  Goal:   Capture spatial context; outperform Stage 1 near geologic boundaries.
  File:   ml/stage2_cnn/  (TODO)

Stage 3 — Physics-Informed NN (THESIS CONTRIBUTION)
  Input:  Same rasters + physics constraint (heat equation ∇·(k∇T) = Q)
  Output: Physically consistent T(x,y,z) and k(x,y,z) fields
  Train:  Full dataset + heat flow measurements as physics boundary conditions
  Goal:   Extrapolate to depth without direct measurement; publishable contribution.
  File:   ml/stage3_pinn/  (TODO)
```

## Integration with the Tool

```
User inputs ZIP → geocode → county FIPS
→ ml/stage1_baseline/predict.py → k, α, T_g
→ s4_sizing (Philippe et al.) → borehole length L

Dev dashboard: show which stage is active, prediction confidence intervals,
               feature importance map, and comparison to any nearby TRT data.
```

## Folder Structure

```
ml/
├── README.md                    ← this file
├── plan/
│   ├── stage1_plan.md           ← Stage 1 detailed execution plan
│   ├── architecture_decision.md ← Why MLP first; comparison of all options
│   └── future_stages.md        ← CNN and PINN roadmap
├── data/
│   ├── sources.md               ← Data catalogue with access instructions
│   ├── collect_smuheatflow.py   ← Download SMU Geothermal Heat Flow database
│   ├── collect_sgmc.py          ← USGS State Geologic Map → county rock class
│   └── README.md                ← What goes in data/ml/ (gitignored)
├── stage1_baseline/
│   ├── features.py              ← Feature engineering pipeline
│   ├── model.py                 ← MLP definition (scikit-learn)
│   ├── train.py                 ← Training + cross-validation
│   ├── evaluate.py              ← Metrics and error analysis
│   └── predict.py               ← Inference for Flask integration
└── integration/
    ├── api_design.md            ← Flask endpoint design
    └── ux_notes.md              ← User-facing and dev-facing UX
```

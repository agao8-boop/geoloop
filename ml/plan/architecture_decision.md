# Architecture Decision — Why MLP First

## The Problem Frame

We want to predict: k(lat, lon), T_g(lat, lon), α(lat, lon) for any US county.

We have: sparse direct measurements (~300–800 TRT tests + ~35,000 heat flow points)
         + nationally complete observable covariates (geology maps, gravity, climate)

This is a **spatial interpolation + regression** problem with rich covariates.

## Options Evaluated

### 1. Rule-Based Lookup (Current State)
**How:** Assign k by rock class from literature table (e.g., granite → 3.0 W/m·K)
**Pros:** Zero training data needed; fully interpretable; fast
**Cons:** Ignores porosity, saturation, mineralogy variation within class; error ±1.5 W/m·K
**Verdict:** Good baseline. Stage 1 must beat this.

### 2. MLP on Tabular Features ✅ STAGE 1
**How:** Vector of 8 features → 3-layer dense network → k, T_g
**Pros:** Simple; fast to train; works well with 500–1000 points; sklearn already installed
**Cons:** No spatial context; treats each county independently
**Expected improvement over lookup:** ±0.3–0.5 W/m·K for k (within-class variation captured)
**Verdict:** Build first. Ship into the tool. Set the bar.

### 3. Gradient Boosting (XGBoost/LightGBM) — Alternative Baseline
**How:** Same tabular features as MLP but tree-based
**Pros:** Often outperforms MLPs on tabular data; handles feature interactions naturally
**Cons:** Slightly harder to explain to non-ML audience than a neural network
**Verdict:** Run this in parallel with MLP as a sanity check. Use whichever wins.

### 4. CNN on Geospatial Rasters — STAGE 2
**How:** N×N patch around each target point from stacked rasters (10–20 channels)
**Pros:** Captures spatial context (rock units change at faults → nearby context matters)
**Cons:** Requires raster alignment at consistent CRS/resolution; more data engineering
**Expected improvement:** 10–20% lower RMSE than MLP near geologic transitions
**Literature:** Reichstein et al. (2019) Nature; several recent geothermal ML papers
**Verdict:** After Stage 1 is in the tool and we have the raster pipeline.

### 5. Graph Neural Network (County Spatial Graph) — Alternative Stage 2
**How:** Counties as nodes; spatial adjacency + geologic similarity as edges
**Pros:** Explicitly encodes spatial autocorrelation (Tobler's Law)
**Cons:** Less established in geothermal literature; complex graph construction
**Verdict:** Interesting but not as natural as CNN for this problem. Lower priority.

### 6. Physics-Informed Neural Network (PINN) — STAGE 3 / THESIS
**How:** NN predicts T(x,y,z) and k(x,y,z); loss = data fit + PDE residual ∇·(k∇T)=Q
**Pros:** Physically consistent; can extrapolate to unmeasured depths; highest novelty
**Cons:** Complex to formulate; requires understanding of forward heat problem
**Reference:** Raissi et al. (2019) J. Computational Physics — landmark PINN paper (10k+ citations)
**Verdict:** Stage 3. This is the publishable contribution for the thesis.

### 7. Neural Kriging (Deep Kriging)
**How:** Replace variogram in geostatistical kriging with learned neural covariance
**Pros:** Natural uncertainty quantification (prediction intervals, not just point estimates)
**Cons:** Less intuitive; less code support
**Verdict:** Worth adding uncertainty quantification ON TOP of Stage 1 MLP later.
           Use bootstrapping as a simpler first approximation.

## Decision

```
Stage 1: MLP (tabular, sklearn) — fast, solid, gets into the tool
Stage 1b: XGBoost comparison — run in parallel, use whichever is better
Stage 2: CNN (raster, PyTorch) — when spatial context improves accuracy
Stage 3: PINN (PyTorch + physics) — thesis contribution
```

## Why This Sequence Makes Sense

The user said: "We should [not spend] too much time on this stage, what we want is
solid but maybe somehow not very precise data for supporting and make sure it works,
and then we could always refine the method in the future."

MLP gets us into the tool with real ML-derived predictions in ~4 days.
The tool then works end-to-end. Every subsequent stage improves the number inside
the same pipeline without requiring architecture changes.

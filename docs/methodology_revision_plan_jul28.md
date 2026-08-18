# GeoSite Advisor — Methodology Revision Plan
**Date:** 2026-07-28
**Author:** Prepared by Claude Code after overnight research
**Status:** PLANNING ONLY — no code changed. All 33 items require discussion before implementation.

---

## How to Use This Document

Each theme maps directly to the numbered TODOs in `memory/todos_methodology_gaps.md`.
For each item: current behavior → what is wrong → what it should be → step-by-step revision path.
Items marked **DISCUSS FIRST** require explicit professor sign-off before any code change.
Items marked **NOT STARTED** can begin implementation once the plan below is agreed.

---

## Theme A — Input Definitions (items 1–4)

### Item 1 — ZIP code vs street address

**Current:** UI geocodes street address → lat/lon via Nominatim.
**Problem:** All downstream data (`deep_thermal_by_county.csv`, DOE prototype climate zones) is county-level. Street-level geocoding implies false precision.
**Correct behavior:** Accept ZIP code only. Resolve ZIP → county FIPS via a static ZIP-to-county lookup table (Census ZCTA crosswalk, free, 40 KB CSV). Then use county FIPS as the join key for all data.

**Revision steps:**
1. Download Census ZCTA-to-county crosswalk (2020 delineations, CSV).
2. Add `data/public/zip_to_county_fips.csv` with columns: `zip5`, `county_fips`, `county_name`, `state`.
3. In `s1_site/geocoder.py`: replace Nominatim call with ZIP lookup → FIPS. Return `{fips, county_name, state, lat_centroid, lon_centroid}` (centroid from county shapefile or pre-computed lookup).
4. Update UI: change address field to "ZIP Code (5 digits)". Add validation: must be 5 numeric digits.
5. Update all downstream calls that currently pass `lat/lon` to pass `county_fips` instead where possible.
6. Centroid lat/lon still needed for USGS API call; county centroid is sufficient.

**Impact:** Removes false precision, eliminates Nominatim dependency, faster lookups.

---

### Item 2 — WWR as numeric range

**Current:** WWR is selected as a category (e.g., "low / medium / high") with a hidden scalar.
**Problem:** The parameter is physically a percentage (0–100%), not a category. ASHRAE 90.1 defines window-to-wall ratio as a fraction. Users need to know what value they are selecting.

**Correct behavior:** UI shows labeled numeric ranges (e.g., "20–40%"). The calculation uses the **midpoint** of the selected range (e.g., 30%). The envelope multiplier lookup key remains the same category name for backward compatibility with `envelope_multipliers_all.csv`.

**Revision steps:**
1. In `s2_simulation/envelope.py` or equivalent: define range bands, e.g.:
   ```
   WWR_BANDS = {
     "wwr_low":    (0.10, 0.20, "10–20%"),
     "wwr_medium": (0.20, 0.40, "20–40%"),
     "wwr_high":   (0.40, 0.60, "40–60%"),
     ...
   }
   ```
2. UI: render dropdown/radio with display label "20–40% (midpoint 30%)".
3. The multiplier lookup key does not change — only the display label and documentation.
4. Update methodology docs and the input spreadsheet to show range boundaries.

---

### Item 3 — Glazing and infiltration as labeled ranges with ASHRAE values

**Current:** Glazing (U-factor) and infiltration (ACH) are selected as categories without showing the user the actual values.
**Problem:** A building owner cannot evaluate "good vs bad" without seeing the physical units.

**Correct behavior:** Each option shows its ASHRAE 90.1 Table-sourced range. Example for glazing:
- "Single-pane (U ≥ 3.5 W/m²K)"
- "Double low-e (U = 1.8–2.8 W/m²K)"
- "Triple low-e (U = 0.8–1.2 W/m²K)"

**Revision steps:**
1. Audit `data/reference/` for the ASHRAE 90.1 prescriptive envelope tables already referenced.
2. Extract U-value ranges per climate zone (or use national averages for a screening tool).
3. Define similar bands for ACH: natural infiltration typical range 0.5–2.0 ACH; tight construction 0.1–0.5 ACH; leaky 2.0–5.0 ACH.
4. Update UI dropdown labels to include the physical range.
5. Update input spreadsheet.

---

### Item 4 — "Unknown" option for all three envelope parameters

**Current:** All three parameters require a selection — no fallback for users who don't know.
**Problem:** A building owner evaluating GSHP feasibility may not know the glazing U-value.

**Correct behavior:** "Unknown" option for WWR, glazing, infiltration. When "Unknown" is selected, the multiplier for that parameter is set to **1.0** (i.e., no adjustment from prototype baseline — benchmark midpoint).

**Revision steps:**
1. Add `"unknown"` key to each parameter's band dictionary with `midpoint=None` and `multiplier=1.0`.
2. In `s2_simulation/envelope.py`: if `param == "unknown"`, skip multiplier lookup, use 1.0.
3. UI: add "Unknown / use default" as the last option in each dropdown.
4. Report/output: note which parameters were unknown so the user knows where uncertainty lies.

---

## Theme B — Subsurface Thermal Model (items 5–6)

> **STOP: Both items in this theme require detailed professor discussion before any implementation.**
> The open question is documented separately in `memory/open_question_subsurface.md`.

### Item 5 — Two overlapping k-lookup methods

**Current situation:**
- **Method A** (primary): IDW interpolation of SMU deep-borehole database → county-average k and α at 100 m depth. Source: `deep_thermal_by_county.csv`.
- **Method B** (present in code): SGMC rock class → Clauser & Huenges (1995) k_min/k_max ranges. This k_min/k_max is computed but never used in sizing.

**Problem:** The two methods produce different k values for the same location and the hierarchy is undefined. Method A is an empirical average; Method B is a lithology-based range. They answer different physical questions.

**Discussion questions before any change:**
1. Should Method B (SGMC-derived k_min/k_max) replace Method A when SMU county data is available? Or only when SMU data is missing?
2. Or should Method B define an uncertainty band around Method A's point estimate?
3. Should the SGMC range feed into best/base/worst cost scenarios as a proxy for thermal risk?

**What NOT to change yet:** Do not modify the k-lookup hierarchy until the professor specifies the intended role of each method.

---

### Item 6 — Layered subsurface (clay/sand overburden over hard rock)

**Current:** Single scalar k used for the entire borehole depth.
**Problem:** Real boreholes penetrate multiple geologic layers. A uniform k assumption underestimates effective conductivity when a high-k granite layer is reached below a low-k clay overburden, or overestimates when the reverse is true.

**Physically correct approach:** Effective k for a series thermal circuit:
```
k_eff = (H_total) / (H_1/k_1 + H_2/k_2 + ... + H_n/k_n)
```
where H_i is the thickness and k_i is the conductivity of layer i.

**This is a significant data problem.** Layer thicknesses and lithology sequence are site-specific and require borehole logs or a regional geology database. No such database is integrated.

**Discussion questions:**
1. Is SGMC polygon depth sufficient to estimate overburden thickness?
2. What is the professor's expectation — single-k acceptable for V1, layered k for V2?
3. If single-k stays, should there be a displayed uncertainty bound (k_min/k_max from SGMC)?

**Do not implement any layered model until there is an explicit, detailed implementation plan signed off by the professor.**

---

## Theme C — HVAC Simulation Model (item 7)

> **DISCUSS FIRST — deferred per professor. Do not change.**

### Item 7 — IdealLoadsAirSystem vs WSHP+DOAS

**Current:** EnergyPlus simulations use `IdealLoadsAirSystem` — a perfect load-matching system that reports space sensible + latent loads with no system inefficiency.
**What WSHP+DOAS gives:** Water-source heat pump terminal units (the actual GSHP terminal equipment) + Dedicated Outdoor Air System. This gives plant loads including heat pump compressor work, pump energy, and ventilation conditioning loads.

**The gap (Erik Coldrup, Jul 15):** IdealLoads gives space loads only. WSHP+DOAS gives space loads + HVAC plant loads. The difference is roughly 10% (more in humid climates with high ventilation loads).

**Position:** Deferred by professor. Keep flagged. If Erik's feedback changes post-full-tool review, scope a separate EnergyPlus run set with WSHP+DOAS system type for the same 16 prototype buildings.

**If COP correction is applied (see Theme E item 14):** The gap partially closes because IdealLoads space loads × COP factor approximates the ground exchange load. This is worth quantifying explicitly.

---

## Theme D — Multiplier Sequence & Climate Coverage (items 8, 11)

### Item 8 — Fix multiplier application order (DISCUSS FIRST)

**Current (wrong) sequence:**
```
1. Get prototype load pulses: q_h_base, q_m_base, q_y_base (from prototype_loads.json)
2. Get envelope multipliers: m_wwr, m_glaz, m_inf
3. Apply: q_h = q_h_base × m_wwr × m_glaz × m_inf
           q_m = q_m_base × ...
           q_y = q_y_base × ...
```

**Why this is wrong:** The three pulses (q_h, q_m, q_y) are extracted from the 8760h hourly profile by different aggregation operations (peak-hour, peak-monthly-average, annual-average). Applying multiplicative factors to the pre-extracted scalars implicitly assumes the multiplier scales all hours uniformly — which is only true if the envelope change affects every hour proportionally. In reality, envelope changes affect heating and cooling hours differently (e.g., better insulation reduces heating load but may increase cooling load on certain days due to solar gain dynamics).

**Correct sequence:**
```
1. Get prototype 8760h hourly profile: Q_heat[8760], Q_cool[8760]
2. Apply envelope multipliers to the hourly arrays:
   Q_heat_adj[h] = Q_heat[h] × m_heat_envelope
   Q_cool_adj[h] = Q_cool[h] × m_cool_envelope
3. Extract pulses from the modified hourly arrays using compute_pulses():
   q_h, q_m, q_y = compute_pulses(Q_heat_adj, Q_cool_adj)
```

**Discussion question:** The current multiplier table (`envelope_multipliers_all.csv`) has one multiplier per variant — it does not separate heating-hours multiplier from cooling-hours multiplier. Does the EnergyPlus study output separate heating/cooling multipliers, or a combined total HVAC load multiplier?

If combined: applying a single multiplier to both Q_heat and Q_cool arrays is the correct intermediate step.
If separate: need to read heating multiplier for Q_heat[h] and cooling multiplier for Q_cool[h] separately before extracting pulses.

**Steps once agreed:**
1. Confirm multiplier structure in `envelope_multipliers_all.csv` (check column names for heat/cool separation).
2. In `s3_loads/compute.py`: change `apply_multipliers()` to take hourly arrays, not scalar pulses.
3. Re-run the cross-validation example (Chicago medium office) and confirm q_h, q_m, q_y match the spreadsheet before and after.

---

### Item 11 — Expand from 4 cities to 16 ASHRAE climate zones

**Current:** Envelope multipliers computed for Denver (5B), Buffalo (6A), Atlanta (3A), Miami (1A) only.
**Problem:** 16 ASHRAE climate zones. A building in Portland (zone 4C, marine) or Phoenix (zone 2B, hot-dry) uses the wrong climate zone's multipliers.

**16 ASHRAE representative cities:**
| Zone | City | TMY3 file |
|------|------|-----------|
| 1A | Miami, FL | USA_FL_Miami |
| 2A | Houston, TX | USA_TX_Houston |
| 2B | Phoenix, AZ | USA_AZ_Phoenix |
| 3A | Atlanta, GA | USA_GA_Atlanta |
| 3B | El Paso, TX | USA_TX_El.Paso |
| 3C | San Francisco, CA | USA_CA_San.Francisco |
| 4A | Baltimore, MD | USA_MD_Baltimore |
| 4B | Albuquerque, NM | USA_NM_Albuquerque |
| 4C | Seattle, WA | USA_WA_Seattle |
| 5A | Chicago, IL | USA_IL_Chicago |
| 5B | Denver, CO | USA_CO_Denver |
| 6A | Minneapolis, MN | USA_MN_Minneapolis |
| 6B | Helena, MT | USA_MT_Helena |
| 7 | Duluth, MN | USA_MN_Duluth |
| 8 | Fairbanks, AK | USA_AK_Fairbanks |
| (3B-coast) | Los Angeles, CA | USA_CA_Los.Angeles |

**Steps:**
1. For each of the 12 missing climate zones, identify the DOE prototype IDF that already exists in `data/doe_prototypes/` (most already have Albuquerque, Seattle, etc. files — check).
2. Run the existing envelope sensitivity script on each new city.
3. Append results to `envelope_multipliers_all.csv`.
4. Update climate-zone-to-city mapping in `s2_simulation/` to include all 16 cities.

---

## Theme E — Three-Pulse Derivation (items 9, 10, 12, 14)

### Item 9 — Cross-check q_h, q_m, q_y definitions against Philippe et al. (2010)

**Philippe et al. (2010) definitions (from paper reconstruction):**
- **q_y:** Net average annual ground load [W/m²]. Positive = cooling dominant (net heat injection to ground). Negative = heating dominant (net heat extraction).
  ```
  q_y = (1/8760) × Σ[h=1 to 8760] q_ground[h]
  ```
- **q_m:** Peak monthly average ground load during the **dominant-mode month** [W/m²]. Computed as the one-month average that has the highest magnitude on the dominant side.
- **q_h:** Peak 6-hour ground load [W/m²]. The single worst-case 6-hour average during the year on the dominant side.

**Current code in `s3_loads/compute.py`:**
```python
q_y = ground.mean()          # net annual — CORRECT
q_h = ground.min()           # peak hour (heating dominant) — CORRECT for hourly; may need 6h average
q_m = monthly_avg.min()      # net monthly average — POTENTIALLY WRONG (should be one-sided)
```

**Issue with q_m:** Net monthly average cancels heating and cooling hours within the same month. The paper uses the one-sided dominant-mode monthly average (zero out non-dominant hours, then compute monthly average).

**Issue with q_h:** The paper specifies a 6-hour pulse, not a single-hour peak. The peak 6-hour average will be slightly lower than the single-hour peak — this is a conservative correction. For most building types the difference is small (< 5%), but it should be correct.

**Cross-check steps:**
1. Print the Philippe (2010) spreadsheet cell formulas for q_h, q_m, q_y.
2. Find the closest equivalent cells in the Python code.
3. For a numeric example: run `compute_pulses()` on a known 8760h profile and compare output to hand-calculated values from the spreadsheet.

---

### Item 10 — Area scaling: total conditioned floor area vs footprint

**Current:** Load intensity (W/m²) × total_conditioned_area from prototype metadata → q in Watts.
**Question:** The prototype loads in `prototype_loads.json` are already in absolute W (total building load), not per-m² intensity. The scaling is: `q_building = q_proto × (actual_area / proto_area)`.

**Correct interpretation:** `actual_area` = total conditioned floor area across all floors (e.g., a 4-story office: 4 × footprint). This is what the user inputs as "building area." The ground footprint is NOT the right area — the borefield is sized for the total HVAC load regardless of building shape.

**Verify:**
1. In `get_loads()`: confirm the area ratio uses `building_area_m2 / proto_area_m2` where both are total conditioned areas.
2. The prototype reference areas are in `prototype_metadata` — confirm these are total conditioned areas (not footprints).
3. Document this explicitly in the methodology.

---

### Item 12 — q_m: one-sided vs net monthly average (DISCUSS FIRST)

**This is the highest-impact unresolved definition question.**

**The two options:**

**Option A (current `compute_pulses()`):** Net monthly average
```python
q_m = monthly_averages_of_ground.min()   # min = most negative = peak heating month
```
For a heating-dominant building in January: heating hours give negative values, but some cooling hours also exist (e.g., mild days). The net monthly average is LESS negative than the one-sided heating average. This underestimates the heating pulse.

**Option B (current `extract_one_sided_pulses()`):** One-sided monthly average
```python
heating_only = np.where(ground < 0, ground, 0.0)
q_m = monthly_averages_of_heating_only.min()
```
This zeroes out all cooling hours before taking the monthly average. Result is a more negative (larger magnitude) q_m. This produces longer borefield sizing (conservative).

**Physical justification for Option B:** During any given month, the ground actually experiences alternating extraction and injection. The long-term 1-month pulse in the Philippe model represents the worst-case sustained load, which should be characterized by the dominant-mode hours only. The non-dominant hours provide some thermal recovery, which Philippe accounts for through the R_m resistance term (not through reducing q_m).

**Recommendation: Option B (one-sided).** But this requires explicit confirmation against the Philippe spreadsheet before changing `compute_pulses()`.

---

### Item 14 — Building load vs ground load: COP correction (DISCUSS FIRST)

**This is the largest hidden quantitative error in the current code.**

**Building load vs ground load:**
- Building heating load: Q_heat [W] — heat delivered to the space by the heat pump.
- Ground heat extraction: Q_ground_extraction [W] — heat removed from the ground.
  Relationship: Q_ground_extraction = Q_heat × (COP_h - 1)/COP_h

For COP_h = 3.5 (typical GSHP heating):
```
Q_ground_extraction = Q_heat × (3.5 - 1)/3.5 = Q_heat × 0.714
```
So ground extraction is **71.4%** of building heating load. Current code uses 100% → overestimates by 40%.

- Building cooling load: Q_cool [W] — heat removed from the space by the heat pump.
- Ground heat rejection: Q_ground_rejection [W] — heat injected into the ground.
  Relationship: Q_ground_rejection = Q_cool × (COP_c + 1)/COP_c

For COP_c = 4.5 (typical GSHP cooling):
```
Q_ground_rejection = Q_cool × (4.5 + 1)/4.5 = Q_cool × 1.222
```
So ground rejection is **122.2%** of building cooling load. Current code uses 100% → underestimates by 18%.

**Net effect on sizing:**
- Heating-dominant buildings: L_h is overestimated by ~40%. Borefield is too long.
- Cooling-dominant buildings: L_c is underestimated by ~18%. Borefield may be too short.

**Default COP values to use (ASHRAE GSHP standards):**
- COP_h = 3.5 (conservative ground-source heat pump heating COP at design conditions)
- COP_c = 4.5 (conservative GSHP cooling COP at design conditions)

These become user-overridable advanced parameters.

**Revision steps:**
1. Add `COP_h` and `COP_c` to `ADVANCED_DEFAULTS` in `s4_sizing/defaults.py`.
2. In `s3_loads/compute.py` `compute_pulses()`: apply conversion before computing ground profile:
   ```python
   # Convert building loads to ground exchange loads
   q_ground[h] = q_cool[h] × (COP_c + 1)/COP_c  - q_heat[h] × (COP_h - 1)/COP_h
   ```
   (sign convention: positive = cooling/injection, negative = heating/extraction)
3. Verify that q_y, q_m, q_h are then extracted from the corrected ground profile.
4. Update the sizing formula cross-check (item 19) with the corrected values.

**COP note:** The Philippe (2010) spreadsheet may or may not apply this correction internally — this must be checked before implementing. If the spreadsheet inputs are already ground loads, then the correction belongs in the Python conversion from EnergyPlus outputs. If the spreadsheet inputs are building loads, the spreadsheet handles it internally.

---

## Theme F — Dominant/Non-Dominant Load & Hybrid Logic (items 13, 27, 29)

### Item 13 — Three-part disambiguation (DISCUSS FIRST)

**Part a — "Dominant" refers to which side?**
In Philippe (2010): the sizing formula is applied twice — once for heating, once for cooling. The dominant mode produces the **longer** borefield length. That longer length is the design length.

- Heating dominant: L_h > L_c → use L_h. The borefield is sized for winter peak.
- Cooling dominant: L_c > L_h → use L_c. The borefield is sized for summer peak.

"Dominant" means: the side that gives the larger L. This has nothing to do with which side has more total energy volume.

**Part b — How does the ASHRAE spreadsheet determine dominant?**
Philippe spreadsheet computes L_h and L_c independently (separate formula invocations with appropriately signed inputs). The larger L is the design length. The code must replicate this exactly — compute both, pick the max.

**Current code behavior:** `heating_dominant = q_heat.sum() >= q_cool.sum()`. This uses total energy volume, not borefield length. This is WRONG. It should size both and compare L values.

**Part c — Peaker for non-dominant load**
Two distinct physical purposes for a peaker:
1. **Peak shaving the dominant load** (what M2 LDC does): Cut the top X% of peak-dominant-hours → smaller borefield → capital cost savings.
2. **Supplementing the non-dominant load for thermal balance** (long-term ground temperature management): If a heating-dominant building has a much smaller cooling load, the ground slowly cools over years (net heat extraction). A supplemental cooling tower (or other heat rejector) injects heat to maintain ground temperature. This is a separate, longer-timescale concern.

These two purposes require completely different calculations. The current code conflates them. The plan:
- M2 LDC = peak shaving dominant load → keep, refine
- Thermal balance supplement = long-term GSHP performance issue → flag as V2 feature, not implemented in V1

---

### Item 27 — Dominant mode check via borefield length (DISCUSS FIRST)

**Current:** Dominant mode determined by `q_heat.sum() >= q_cool.sum()` (energy volume).
**Correct:** Compute L_h and L_c from the sizing formula; pick whichever is larger.

This means the sizing function must run twice with opposite sign conventions, not once. The `T_in_HP` defaults already differ by mode (5°C heating, 40.2°C cooling), which is correct — those are the design entering water temperatures for the heat pump.

**Implementation plan:**
1. In `s4_sizing/ashrae_sizing.py`: expose a `mode` parameter (`"heating"` or `"cooling"`).
2. Call `size_borefield(mode="heating")` and `size_borefield(mode="cooling")`.
3. `dominant_mode = "heating" if L_h >= L_c else "cooling"`.
4. Pass dominant_mode to s6_strategy for LDC application.

---

### Item 29 — Remove Method 1 (hours-based LDC) from all code paths

**Current:** M1 still exists in `s6_strategy/ldc.py` even though only M2 is reported.
**Action:** Delete M1 code paths entirely. This is a simple deletion, not a redesign.

**Steps:**
1. In `ldc.py`: remove `_hours_based_cutoff()` function and all references.
2. In `strategy.py`: remove M1 call, keep only M2.
3. In tests: remove M1-specific test cases.
4. Confirm no API endpoint returns M1 data.

---

## Theme G — Sizing Formula Cross-Check (items 15–19)

### Item 15 — Physical meaning of resistance terms

The Philippe (2010) sizing formula is:
```
L = (q_y × R_y + q_m × R_m + q_h × (R_h + Rb)) / (T_m - T_g - Tp)
```

**Resistance terms:**
- **Rb** [m·K/W]: Borehole resistance. Thermal resistance from fluid to borehole wall. Components:
  - R_convection: fluid-to-pipe inner wall (depends on Re, Pr → Nusselt → h → R_conv)
  - R_pipe_wall: pipe wall conduction (depends on pipe k, OD, ID)
  - R_grout: grout layer conduction (depends on grout k, borehole radius, pipe OD)

- **R_h** [m·K/W]: Formation thermal resistance for 6-hour pulse. Derived from g-function evaluated at 6h timescale. Accounts for heat spreading in the surrounding rock over 6 hours. Short timescale → small radius of influence → R_h is small.

- **R_m** [m·K/W]: Formation resistance for 1-month pulse. g-function at 1-month → medium radius of influence → R_m > R_h.

- **R_y** [m·K/W]: Formation resistance for 10-year pulse. g-function at 10 years → large radius of influence, accounts for long-term ground temperature change from cumulative load.

**g-function timescales in the polynomial fit:**
The 10-term polynomial from Philippe uses: t_6h = 6×3600s, t_1m = 2.628×10^6s, t_10y = 3.154×10^8s, with inputs α (thermal diffusivity) and r_bore (borehole radius).

---

### Item 16 — Cell-by-cell cross-validation (DISCUSS FIRST, then item 19 executes)

**The validation protocol:**
1. Choose: Chicago, IL (zone 5A), medium office, default envelope.
2. Run Philippe (2010) spreadsheet (`data/reference/philippe_2010_sizing.xlsx`) manually with those inputs.
3. Run Python `size_borefield()` with identical inputs.
4. Print every intermediate value side by side.

**Intermediate values to compare:**
- Rb [m·K/W]
- α [m²/s], r_bore [m]
- F6H, F1M, F10Y (g-function evaluations)
- R_h, R_m, R_y [m·K/W]
- q_h, q_m, q_y [W/m]
- T_g [°C], T_m [°C]
- Tp (temperature penalty after iteration) [°C]
- L_h, L_c [m]

Any discrepancy > 1% in an intermediate value requires root-cause investigation before proceeding.

---

### Item 17 — G-function sensitivity to α

**G-function form (Philippe 2010, 10-term polynomial):**
The g-function evaluates heat spreading as a function of dimensionless time τ = α·t / r_bore².

At 6-hour timescale: τ_6h = α × 6×3600 / r_bore²

For α = 1e-6 m²/s (typical rock) and r_bore = 0.06m:
τ_6h = 1e-6 × 21600 / 0.0036 = 0.006

Sensitivity: ∂R_h/∂α is nonzero but small at short timescales (heat has not spread far).
At 10-year timescale: τ_10y = 1e-6 × 3.154e8 / 0.0036 = 87.6 → R_y is much more sensitive to α.

**Quantify:** A ±10% change in α propagates to R_y through the g-function polynomial. Should be computed numerically (evaluate g at α and α×1.1, compare). This bounds the uncertainty from subsurface characterization.

---

### Item 18 — T_in_HP physical meaning

**T_in_HP is the heat pump Entering Water Temperature (EWT):**
- Heating mode EWT = minimum ground-loop fluid temperature the heat pump can accept before lockout. Default: 5°C (ASHRAE 90.1 recommendation for vertical GSHP systems).
- Cooling mode EWT = maximum ground-loop fluid temperature before lockout. Default: 40.2°C (=105°F, DOE reference for ground-source systems).

**Physical chain:**
```
Ground temperature T_g
  → Heat exchange in borehole → ground loop fluid T_fluid
  → Heat pump EWT = T_in_HP (design constraint)
  → Heat pump COP (depends on EWT)
  → Building conditioning
```

The sizing formula ensures the fluid temperature never violates T_in_HP at design peak conditions. This is why T_m (mean fluid temperature) uses T_in_HP as a reference:
- Heating: T_m = (T_in_HP_heat + T_in_HP_heat + ΔT_fluid)/2 — the fluid temperature is near minimum at design peak.
- Cooling: T_m = (T_in_HP_cool + T_in_HP_cool - ΔT_fluid)/2 — the fluid temperature is near maximum at design peak.

**Document this clearly** in the methodology for professor review.

---

### Item 19 — Systematic comparison table (NOT STARTED — execute first)

This is the most concrete actionable item in Theme G. Can be implemented without professor input.

**Output:** A Markdown table comparing Python vs Excel at every step for Chicago medium office.

**Script plan (`scripts/validate_sizing.py`):**
```python
# Inputs (to be set identically in both Python and Excel)
inputs = {
    "building_type": "medium_office",
    "area_m2": 4982.0,  # DOE prototype total conditioned area
    "climate_zone": "5A",
    "k": 2.1,           # W/(m·K) — Illinois typical
    "alpha": 1.1e-6,    # m²/s
    "T_g": 11.5,        # °C — undisturbed ground temperature Chicago
    "T_in_HP_heat": 5.0,
    "T_in_HP_cool": 40.2,
    "COP_h": 3.5,
    "COP_c": 4.5,
    "rbore": 0.0762,    # m (3-inch borehole)
    "NB": 16,
    "B": 6.0,           # m borehole spacing
}
# Run sizing, print every intermediate value
```

---

## Theme H — NB Optimization Algorithm (items 20–23)

### Item 20 — Two NB options: manual vs optimized (DISCUSS FIRST)

**Agreed design (both options must coexist):**
- **Option A (manual):** User enters NB. System computes H = L/NB, checks H in [H_min, H_max], reports cost.
- **Option B (auto-optimize):** System iterates NB from a starting point to minimize total cost.

No code change until item 22's algorithm spec is agreed.

---

### Item 21 — Depth range defaults (NOT STARTED)

**Agreed values:**
- H_min = 125 m (do not recommend shallower — industry standard minimum for thermal performance)
- H_max = TBD (discuss: drill-rig capability, permitting, economics — typically 300–450 m in US)
- Default target depth = 150 m

**Update in `s4_sizing/defaults.py`:**
```python
H_MIN_M = 125.0   # minimum borehole depth, meters
H_MAX_M = 400.0   # maximum borehole depth, meters (pending discussion)
H_DEFAULT_M = 150.0
```

---

### Item 22 — NB optimization algorithm spec (NOT STARTED — implement after item 20 agreed)

**Full algorithm:**

```
Given: L (total borefield length from sizing formula)
       building_footprint (width W × depth D)
       spacing B (default 6m)
       H_min, H_max (depth constraints)

Option A (manual NB):
  H = L / NB
  if H < H_min: warn "too shallow, increase NB"
  if H > H_max: warn "too deep, reduce NB"
  cost = compute_cost(NB, H, ...)
  return {NB, H, cost}

Option B (optimize):
  Step 1: Compute NB range
    NB_min = floor(short_edge / B) + 1
    NB_max = corner_aware_perimeter_algorithm(W, D, B)   # TBD, see note

  Step 2: Find starting NB
    NB_start = floor((NB_min + NB_max) / 2)
    H_start = L / NB_start
    if H_start < H_min:
      # NB_start is too large (too many shallow boreholes)
      # iterate NB_start -= 1 until H >= H_min
    elif H_start > H_max:
      # NB_start is too small (too few deep boreholes)
      # iterate NB_start += 1 until H <= H_max

  Step 3: Cost minimization
    best = (NB_start, compute_cost(NB_start, L/NB_start))
    for delta in [1, -1, 2, -2, 3, -3, ...]:
      NB_try = NB_start + delta
      if NB_try < NB_min or NB_try > NB_max: continue
      H_try = L / NB_try
      if H_try < H_min or H_try > H_max: continue
      cost_try = compute_cost(NB_try, H_try)
      if cost_try < best[1]:
        best = (NB_try, cost_try)

    return {NB: best[0], H: L/best[0], cost: best[1]}
```

**NB_max algorithm (corner-aware perimeter):**
The current formula `floor(perimeter / spacing)` overcounts corners. For a rectangle W×D with spacing B:
- Long side: floor(W/B) + 1 boreholes (including both ends)
- Short side: floor(D/B) + 1 boreholes (including both ends)
- Corner boreholes are shared → total = 2×(floor(W/B) + floor(D/B))
This is still approximate; the correct value requires knowing whether fractional spacings are allowed and how corners are allocated. This needs a dedicated algorithm and validation for edge cases.

**NB_min fix:**
Current: `ceil(short_edge / spacing)` → gives 3 for 18m/6m.
Correct: `floor(short_edge / spacing) + 1` → gives 4 for 18m/6m (both ends count).
Only differs when edge length is exact multiple of spacing. Fix is a one-line change.

---

### Item 23 — H_max determination (DISCUSS FIRST)

Hold for professor discussion. Key considerations:
- Standard US geothermal drill rigs: capable to 300–600 m.
- Beyond ~400 m: formation stress increases, casing requirements change, cost per meter increases non-linearly.
- Permitting: some jurisdictions limit borehole depth.
- Practical default for a screening tool: H_max = 400 m pending discussion.

---

## Theme I — Cost Model & Stage Order (items 24–26, 30–31)

### Item 24 — Best/base/worst scenario driver (DISCUSS FIRST — but largely resolved)

**Current implementation (verified from `estimator.py`):**
The three cost scenarios are driven by `rock_frac` — the fraction of the borehole drilled through rock vs soil:
```python
_SCENARIOS = {"best": 0.00, "base": 0.30, "worst": 0.70}
```
- Best: 0% rock (all soft soil) → lower $/ft drilling rate
- Base: 30% rock → blended rate
- Worst: 70% rock → mostly hard rock drilling rate

**Is this valid?** Yes. Until a borehole is drilled, the exact geology is unknown. `rock_frac` is the dominant cost uncertainty for vertical GSHP. The SGMC rock class provides a prior estimate; actual value is revealed during drilling.

**For site-specific estimates:** `estimator.py` already derives `rock_frac` from SGMC rock class (sedimentary → low fraction, igneous/metamorphic → high fraction) with ±0.15 spread for best/worst. This is a reasonable approach.

**No change needed** to the scenario driver mechanism. Document and confirm with professor.

---

### Item 25 — Audit fixed vs variable line items (DISCUSS FIRST — but can be audited)

**From `s5_cost/line_items.py` (9 items):**
| Line item | Type | Notes |
|-----------|------|-------|
| Mobilization | Fixed (per project) | Does not scale with L or NB |
| Drilling (soil) | Variable ($/linear-ft) | Scales with total L × (1 - rock_frac) |
| Drilling (rock) | Variable ($/linear-ft) | Scales with total L × rock_frac |
| Well casing | Variable ($/ft) | Scales with L (top casing section) |
| Sand bag | Variable ($/bag) | Scales with volume |
| Grout bag | Variable ($/bag) | Scales with volume |
| U-tube pipe | Variable ($/linear-ft) | Scales with 2 × H × NB |
| Horizontal pipe | Variable (scales with NB and B) | Header pipe between boreholes |
| Horizontal trench | Fixed (per project) or variable by length | Trench from header to building |

**Header pipe cost:** `horiz_pipe ~ (NB-1) × B × rate + distance_to_building × rate`. This is why cost minimization is NOT identical to L minimization — L says nothing about header length, which scales with NB × spacing independently.

**Document the formula for each line item** explicitly in methodology for professor review.

---

### Item 26 — Fix stage order: S4 → S6 → S5 → S7 (NOT STARTED — implement this)

**Current wrong order:**
```
S4: size borefield → L_before
S5: cost uses L_before → cost_before (WRONG — L hasn't been modified by strategy yet)
S6: strategy → L_after (may be shorter if peak-shaving applied)
S7: report uses L_before cost
```

**Correct order:**
```
S4: size borefield → L_before
S6: strategy → L_after, peaker_capacity, peaker_cost
S5: cost uses L_after → cost_after (CORRECT)
S7: report uses cost_after, shows savings from strategy
```

**Implementation steps:**
1. In `app.py` (or wherever pipeline orchestration happens): swap S5 and S6 calls.
2. Ensure S5 receives `L_after` (not `L_before`) as input.
3. Ensure S7 report shows the full story: L_before → strategy applied → L_after → cost.
4. Update all related tests that assert on pipeline output order.
5. Confirm the API response schema correctly reflects L_before, L_after, and which cost is reported.

This is a concrete, executable fix with no physics ambiguity. Priority: **HIGH**.

---

### Item 30 — Peaker equipment cost (DISCUSS FIRST)

**Missing:** When M2 strategy recommends a peak-shaving boiler or electric resistance heater (heating dominant) or chiller (cooling dominant), the capital cost of that peaker is not included in the total GSHP system cost.

**Data needed:** A $/kW lookup table by capacity range. Example structure:
```
Peaker type           | Capacity range | $/kW
Electric resistance   | 10–100 kW      | $50–80/kW
Electric resistance   | 100–500 kW     | $30–50/kW
Gas boiler            | 50–500 kW      | $80–150/kW
Air-cooled chiller    | 50–200 kW      | $200–400/kW
```
Source: RSMeans MEP cost data, ASHRAE HVAC Applications, or published DOE reports.

**Steps once data is sourced:**
1. Add lookup table to `s5_cost/`.
2. After strategy determines peaker capacity (kW), add `peaker_cost = capacity × $/kW`.
3. Include in total GSHP system cost and report.

---

### Item 31 — Regional conventional system cost (DISCUSS FIRST)

**Current:** Conventional system cost = $35/sqft (US average).
**Problem:** Regional variation is large. California commercial HVAC averages $45–60/sqft; Midwest averages $28–38/sqft.

**Data needed:** Regional multiplier table by census region or state. RSMeans City Cost Indexes (CCI) provide this. The CCI can multiply the national $35/sqft baseline.

**Defer to V2** unless professor requests this for the Jul 28 presentation. The $35/sqft placeholder is clearly labeled and does not affect the sizing calculations.

---

## Theme J — Recommendation Score (items 32–33)

### Item 32 — CAPEX/OPEX comparison needs regional rates (DISCUSS FIRST)

**Current:** Payback period calculation uses national average electricity and gas rates.
**Problem:** Energy prices vary 3× across US states (residential electricity: 9 ¢/kWh Hawaii → 28 ¢/kWh). GSHP economics depend strongly on the local electricity/gas rate ratio.

**Data source:** EIA State Energy Data System (SEDS) — annual average electricity and gas prices by state. Free download as CSV.

**Steps:**
1. Add `data/public/eia_energy_rates_by_state.csv` with: state, avg_electricity_cents_per_kwh, avg_gas_dollars_per_therm (commercial rates).
2. Look up rates by state (derived from ZIP code in step 1 above).
3. Use state-specific rates in payback calculation.

**Defer full implementation** until after core sizing fixes (Themes E–H) are complete.

---

### Item 33 — Recommendation score redesign (DISCUSS FIRST)

**Current five factors:**
- F1: Climate zone suitability (0–35 pts) — duplicates load profile information
- F2: Ground thermal properties (0–20 pts)
- F3: Payback period (0–20 pts)
- F4: Building size/load intensity (0–15 pts)
- F5: Annual load balance (0–10 pts)

**Problem:** F1 (climate zone) is not independent of the sizing result — a building in zone 1A (Miami, cooling-dominant) will already show a large cooling borefield, so the "climate zone flag" is redundant information. F4 (building size) is also captured by the sizing already.

**Proposed redesign (defer until Themes E–H are correct):**
- **F1 — Borefield feasibility**: Does the site have adequate land area for the computed borefield? (NB × spacing × spacing vs available site area)
- **F2 — Thermal resource quality**: k vs national median — is the ground thermal conductivity above average?
- **F3 — Economic payback**: CAPEX GSHP / annual OPEX savings vs conventional system (uses regional rates from item 32)
- **F4 — Load balance risk**: |L_h - L_c| / max(L_h, L_c) — how unbalanced is the heating/cooling load? High imbalance → long-term ground temperature drift risk.
- **F5 — Subsurface data confidence**: How many SMU deep-borehole measurements contributed to the county k estimate? More data → higher confidence.

**Do not redesign until items 9, 12, 14, 27 are resolved** — those changes will change the sizing outputs that the score is based on.

---

## Summary Priority Matrix

| Priority | Item | Action | Prerequisite |
|----------|------|---------|-------------|
| HIGH | 26 | Fix stage order S4→S6→S5→S7 | None — implement now |
| HIGH | 29 | Remove M1 from all code paths | None — implement now |
| HIGH | 1 | ZIP code input, county FIPS lookup | None — implement now |
| HIGH | 4 | "Unknown" option for envelope params | None — implement now |
| HIGH | 19 | Cross-validation script (Python vs Excel) | None — run now |
| MEDIUM | 14 | COP correction for ground loads | Discuss first, check Philippe spreadsheet |
| MEDIUM | 12 | Fix q_m to one-sided (ldc.py path vs compute.py) | Discuss first, cross-check with 19 |
| MEDIUM | 27 | Dominant mode via L_h vs L_c comparison | Discuss first |
| MEDIUM | 22 | NB optimization algorithm | Discuss 20, 23 first |
| MEDIUM | 8 | Multiplier sequence fix | Discuss first, confirm multiplier structure |
| LOW | 2, 3 | Range display for WWR/glazing/infiltration | None — UI-only change |
| LOW | 11 | Expand to 16 climate zones | EnergyPlus runs needed |
| LOW | 21 | H_min/H_max defaults | Discuss 23 first |
| DEFER | 5, 6 | Layered subsurface model | Discuss thoroughly |
| DEFER | 7 | IdealLoads vs WSHP+DOAS | Professor deferred |
| DEFER | 31, 32, 33 | Regional rates, score redesign | After Themes E–H |

---

## Immediate Next Steps (can begin without professor input)

1. **Run cross-validation script** (item 19) — write `scripts/validate_sizing.py` against Chicago medium office
2. **Fix stage order** (item 26) — swap S5 and S6 in the orchestration layer
3. **Remove M1** (item 29) — delete `_hours_based_cutoff()` from `ldc.py`
4. **Add ZIP code input** (item 1) — download Census crosswalk, replace Nominatim
5. **Add "Unknown" option** (item 4) — one line per parameter

All other items wait for professor discussion.

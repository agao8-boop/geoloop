# GeoSite Advisor — Design Decision Log

---

## 2026-06-24 — s1_site: Soil Data Philosophy & Coverage Map

**Decision:** Soil data is fully automatic from location. Users are never asked to enter soil values. Where SSURGO data is unavailable, that location shows as blank on the coverage map — no fallback estimate, no placeholder. Neural network gap-filling is a planned future stage (post-MVP).
**Decided by:** User  

**What it means:**
- s1_site queries USGS SSURGO by lat/lon, applies Côté-Konrad (2005) to derive k and α
- The coverage map (one of the tool's research outputs) shows SSURGO data density: colored where data exists, blank where it does not
- ZIP codes are allocated to their parent city; SSURGO queries run at city centroid or point-in-polygon level
- User never sees soil numbers unless they explicitly look at the output panel — the subsurface is the tool's job, not theirs

**Research objective:** Establish a national map of soil thermal data coverage as a deliverable of this independent study. Blank areas on the map define the problem the neural network will solve in a later phase.

**Alternatives rejected:**
- Climate-zone fallback defaults: rejected — would misrepresent data gaps and undermine the coverage-map research goal
- Asking users to enter soil data: explicitly rejected — tool must be simple; building owners don't have soil boring reports at feasibility stage

---

## 2026-06-24 — Overall Data Architecture: Two Streams

**Decision:** All project data is organized into two strictly separated streams with a defined connection point.
**Decided by:** User

**Stream 1 — Developer/Research (private to researcher):**
- Census-tract level maps: above-ground (climate, weather, MAT, precipitation) and subsurface (soil properties, k, α, T_g, SSURGO coverage)
- Data collection scripts and provenance logs
- Coverage maps showing where data exists vs. is blank (the research output)
- Neural network training data and gap-filling results (future)
- Stored in `data/research/` — not served to public users

**Stream 2 — Public/Tool (user-facing):**
- Pre-computed lookup tables (CSV) of thermal properties by census tract
- Pre-computed building load lookup tables by prototype × climate zone
- Frontend fetches from these flat files; no heavy computation at runtime
- Stored in `data/public/` — served directly to the tool's Flask backend

**Connection point:** A pipeline script (run by developer, not users) reads Stream 1 data and exports the subset needed by Stream 2 into `data/public/`. This keeps the maps and raw data private while the tool stays lightweight.

**File structure intent:**
```
data/
├── research/               ← Developer only. Never exposed to users.
│   ├── subsurface/         # raw SSURGO pulls, Côté-Konrad results, coverage GeoJSON
│   ├── above_ground/       # EPW stats, precipitation, MAT by census tract
│   └── collection_logs/    # provenance: when/where data was fetched
└── public/                 # Tool-facing. Flat and fast.
    ├── thermal_by_tract.csv        # census_tract_geoid → k, alpha, T_g (NaN where no data)
    ├── climate_by_tract.csv        # census_tract_geoid → climate_zone, nearest_epw
    └── prototype_loads.json        # building_type × climate_zone → q_h, q_m, q_y
```

---

## 2026-06-24 — Spatial Unit: Census Tract for All Maps

**Decision:** Census tract (US Census TIGER/Line GEOID) is the common spatial unit for both maps (above-ground and subsurface). All data — SSURGO soil properties, precipitation, MAT, climate zone — are aggregated or interpolated to census tract centroids.
**Decided by:** User

**Why census tract:**
- Consistent, official US geographic unit (~74,000 tracts nationally, ~4,000 people each)
- Small enough to show meaningful spatial variation; large enough to have stable public data
- Enables a single consistent map for both above-ground and subsurface layers

**Two maps:**
- **Subsurface map:** census tract → k [W/m·K], α [m²/day], SSURGO coverage (colored where computed, blank where no SSURGO data) — this is the research deliverable
- **Above-ground map:** census tract → ASHRAE climate zone, mean annual air temperature (MAT), annual precipitation, nearest EPW station — supports both s1 (T_g) and s2 (prototype selection)

---

## 2026-06-24 — s1_site: Thermal Conductivity Calculation Method

**Decision:** Use Côté & Konrad (2005) as the single method for computing k and α from USGS SSURGO soil properties.  
**Decided by:** User (confirmed from reference spreadsheet `390geothermal_calc.xlsx` → `prelim` sheet)

**What it means:**
- USGS provides: texture class (sand/silt/clay %), dry bulk density ρ_d, particle fractions
- USGS SSURGO provides: texture class (sand/silt/clay %), dry bulk density ρ_d
- Côté-Konrad maps those to: k [W/m·K] and α [m²/day]
- Use original paper (eq. 28) formula directly: k_dry = χ × 10^(−η×n) — NEGATIVE exponent confirmed
- Parameter sets from paper (Table confirmed against Kersten 1949 data):
  - Gravels/coarse sands: χ=1.70, η=1.80, κ=4.50
  - Medium/fine sands: χ=0.75, η=1.20, κ=3.55
  - Silts/clays: χ=0.75, η=1.20, κ=1.90
  - Peat/organic: χ=0.30, η=0.87, κ=0.60
- The three-column averaging in 390geothermal_calc.xlsx prelim sheet represents unknown soil type scenarios — for implementation, use the original paper equations directly without this averaging
- S_r estimation method: PENDING — under research (see open question in design-log)

---

## 2026-06-24 — Data Storage Format

**Decision:** All data — whether batch-collected or computed — is stored as CSV. No SQLite or other database.
**Decided by:** User

**Two-tier CSV rule:**

| Data type | Example | Format | Why |
|---|---|---|---|
| Fixed batch data collected once | Côté-Konrad χ/η/κ parameters, USGS DS-801 quartz points, gfunction polynomial coefficients | CSV | Written once, never changes, fastest to dump from source |
| Computed / adjustable data | `thermal_by_tract.csv` (k, α, T_g per census tract), `prototype_loads.json` | CSV with clear readable column headers | Mentor needs to open and verify in Excel; methodology must be traceable |

**Specific files and their format:**

| File | Location | Format | Columns |
|---|---|---|---|
| Côté-Konrad soil type parameters | `data/research/subsurface/cote_konrad_params.csv` | CSV | soil_class, chi, eta, kappa_unfrozen, kappa_frozen, notes |
| USGS DS-801 quartz data | `data/research/subsurface/usgs_quartz_points.csv` | CSV | lat, lon, state, quartz_fraction, source_sample_id |
| Census tract thermal properties | `data/research/subsurface/thermal_by_tract.csv` | CSV | geoid, k_wmpk, alpha_m2day, T_g_C, S_r_used, soil_class, data_source, notes |
| Census tract climate | `data/research/above_ground/climate_by_tract.csv` | CSV | geoid, ashrae_climate_zone, mat_c, precip_mm_yr, nearest_epw_station |
| Public thermal lookup | `data/public/thermal_by_tract.csv` | CSV | geoid, k_wmpk, alpha_m2day, T_g_C (NaN where no data) |
| Prototype loads | `data/public/prototype_loads.json` | JSON | building_type → climate_zone → {q_h, q_m, q_y} |

**Rationale:** CSV opens directly in Excel, Numbers, and Google Sheets without any software installation. Mentor can review intermediate values. For ~74,000 census tracts, a CSV is under 10 MB — no database needed at this scale.

---

## 2026-06-24 — s1_site: Location Input Dual-Mode

**Decision:** Support two location input modes: (A) ZIP code → city → precise lat/lon for full s1 soil pipeline; (B) ASHRAE climate zone → building prototype selection only (no soil data — s1 shows blank).  
**Decided by:** User

**What it means:**
- Mode A (ZIP): feeds both s1 (soil, T_g, EPW) and s2 (climate zone → prototype selection)
- Mode B (Climate Zone): feeds only s2; s1 shows "No soil data available for climate zone selection"
- The map always shows SSURGO coverage regardless of which mode the user picks

---

> **Purpose:** Record every significant design or architectural decision made during development.  
> This log feeds directly into the weekly progress slide decks.  
> Format: newest decisions at the top. Each entry records what was decided, who decided it, why, and what alternatives were rejected.

---

## 2026-06-24 — Simulation Engine Approach (s2_simulation)

**Decision:** Option C — Hybrid: pre-computed lookup + real-time EnergyPlus  
**Decided by:** User  

**What it means:**
- If user provides only the minimum inputs (building type + location) → serve results instantly from a pre-computed lookup table of all 128 prototype × climate-zone combinations.
- If the user changes any parameter in the extended override box → trigger a real-time EnergyPlus simulation. A visible notice will read: *"Real-time calculation with EnergyPlus — this may take approximately X seconds."*

**Alternatives rejected:**
- **Option A (always real-time):** Too slow for the common case; requires EnergyPlus installed for every user.
- **Option B (always pre-computed):** Can't honour custom overrides; inaccurate for non-standard buildings.

---

## 2026-06-24 — Building Input UI Design (s2_simulation front-end)

**Decision:** Prototype-select + collapsible override box  
**Decided by:** User  

**What it means:**
- Primary, minimal input: building type (dropdown from 16 DOE commercial prototype types) + location (cascading dropdowns: State → City → ZIP code).
- The UI clearly states: *"Building type matches DOE Commercial Prototype Building Models (ASHRAE 90.1-2019)."*
- An "Advanced / Extended" collapsible section shows all numerical defaults for the selected prototype. Every field has a **↺ Reset to default** button.
- Floor area, WWR, envelope R-values, LPD, EPD, occupancy, and setpoints are all overridable.

**Alternatives rejected:**
- **Full parametric (build IDF from scratch):** Too complex for building-owner users; EnergyPlus expertise required.
- **Prototype only, no overrides:** Can't account for buildings that differ from the prototype (e.g., recently re-enveloped buildings).

---

## 2026-06-24 — Building Input Approach (overall strategy)

**Decision:** Option C — Prototype + Overrides (C.Scale-style UX)  
**Decided by:** User  

**What it means:**
- Use DOE/NREL pre-built prototype IDF files as the starting point.
- eppy patches only the fields the user overrides; everything else stays at the validated prototype defaults.
- This mirrors how C.Scale handles building inputs: ask for high-level descriptors, fill in the rest from standards.

**Alternatives rejected:**
- **Option A (prototype-select only):** No customization; inadequate for real buildings.
- **Option B (full parametric):** High user burden; error-prone without EnergyPlus expertise.

---

## 2026-06-23 — s4_sizing Baseline Implementation

**Decision:** Implement Philippe et al. (2010) ASHRAE three-pulse sizing equation in Python as the ground-truth baseline.  
**Decided by:** User  

**What it means:**
- `geosite/s4_sizing/ashrae_sizing.py` implements `size_borefield()` and `borehole_resistance()`.
- Polynomial coefficients extracted from `philippe_2010_sizing.xls` and `390geothermal_calc.xlsx`.
- Validation: Python outputs match both reference spreadsheets for identical inputs.
- All future pipeline stages (s1–s3) must produce outputs that plug directly into `size_borefield()`.

---

## 2026-06-23 — MVP Scope: Vertical Closed-Loop Only

**Decision:** V1 covers only vertical closed-loop GSHP systems.  
**Decided by:** Project definition (CLAUDE.md)  

**What it means:**
- Horizontal loop, open-loop, and pond/lake systems are out of scope for V1.
- Sizing equation (Philippe et al.) is valid only for vertical borehole arrays.

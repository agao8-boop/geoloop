# s5 Cost Estimation — Design Spec
**Date:** 2026-06-30  
**Stage:** s5 of GeoSite Advisor pipeline  
**Status:** Approved for implementation

---

## 1. Purpose

Translate Philippe et al. (2010) borefield sizing output (L, NB, H, B) into a regional cost estimate using the 9 line-item breakdown from the project reference spreadsheet (`data/reference/390geothermal_calc.xlsx`). Produces a composite $/ft metric, a best/base/worst cost range, and a contractor comparison. Visualized as a US state choropleth on the dev dashboard.

---

## 2. Module Structure

```
geosite/s5_cost/
    __init__.py          # public API: estimate_cost(L, NB, B, site) → CostResult
    line_items.py        # 9 line item definitions + quantity calculators
    regional_rates.py    # state-level rate table loader + Census division fallbacks
    estimator.py         # orchestrates line items × rates → CostResult ×3 scenarios

data/public/
    drilling_rates_by_state.json   # rate table (version-controlled)
```

No new Flask blueprint — cost endpoint lives in `app.py` alongside existing routes.

---

## 3. The 9 Line Items

These mirror the reference spreadsheet exactly (both "Close-loop h - s" best and "Close-loop h - c" worst tabs). All formulas verified against spreadsheet cell values.

| # | Item | Quantity formula | Default rate | Unit |
|---|---|---|---|---|
| 1 | Mobilization | 1 flat | $1,000 | /project |
| 2 | Drilling — soil | `NB × H_rounded_ft × (1 - rock_frac)` | $30 | /LF |
| 3 | Drilling — rock | `NB × H_rounded_ft × rock_frac` | $100 | /LF |
| 4 | Well casing | 0 (default) | $20 | /LF |
| 5 | Sand (bentonite bags) | `grout_bags_total × 8` | $10 | /50lb bag |
| 6 | Grout (CETCO High TC bags) | `ceil(grout_vol_L_per_borehole / 161) × NB` | $20 | /50lb bag |
| 7 | U-tube HDPE pipe | `NB × H_rounded_ft` (both legs, $2/LF covers both) | $2 | /LF |
| 8 | Horizontal header pipe | `2 × horiz_trench_ft` | $1 | /LF |
| 9 | Horizontal trench | `(NB - 1) × B_ft + distance_to_house_ft` | $5 | /LF |

**Derived quantities (all verified against spreadsheet):**
- `H_exact_m = L_m / NB` (exact depth per borehole from sizing output)
- `H_rounded_ft = ceil(H_exact_m × 3.28084 / 10) × 10` (round up to nearest 10 ft)
- `B_ft = B_m × 3.28084`
- `distance_to_house_ft = 100` (default; user-overridable)
- `horiz_trench_ft = (NB - 1) × B_ft + distance_to_house_ft`
- `horiz_pipe_ft = 2 × horiz_trench_ft`
- `grout_vol_m3_per_borehole = π × H_exact_m × (r_bore² - r_pext²/2)` (spreadsheet formula using r_pext = 0.0167 m, r_bore = 0.0762 m)
- `grout_vol_L_per_borehole = grout_vol_m3_per_borehole × 1000`
- `grout_bags_per_borehole = ceil(grout_vol_L_per_borehole / 161)` (161 L yield per CETCO batch)
- `grout_bags_total = grout_bags_per_borehole × NB`
- `sand_bags_total = grout_bags_per_borehole × 8 × NB` (8 × 50lb sand bags per CETCO batch = 180 kg ÷ 22.68 kg/bag → 7.94 → 8)
- Well casing defaults to 0 LF (spreadsheet also shows 0 for both sand/clay scenarios — only needed for unstable formations)

**Note:** The CETCO grout mix formula is fixed regardless of formation type. Sand (item 5) is the bentonite aggregate that goes INTO the grout mix, not a separate fill layer. The grout_vol formula (`r_bore² - r_pext²/2`) is derived from the spreadsheet and differs from standard physics (which would use `r_bore² - 2×r_pext²`); use the spreadsheet formula to reproduce exact results.

---

## 4. Scenario Modeling

Scenarios vary `rock_frac` only — this is the only parameter s5 controls. The borefield size (L, NB, H) is fixed from s4. All grout/sand quantities are geometry-driven (same across scenarios). The cost difference between scenarios comes entirely from the rock drilling split.

| Scenario | rock_frac | Interpretation |
|---|---|---|
| best | 0.0 | All soft soil/clay, no bedrock encountered |
| base | 0.30 | Typical — 30% of borehole depth in rock |
| worst | 0.70 | Mostly hard rock (granite, basalt) |

If the site's `rock_class_name` (from SGMC via deep thermal) is available, `rock_frac` is set from a lookup:
- igneous or metamorphic → rock_frac = 0.90
- sedimentary → rock_frac = 0.40  
- unconsolidated → rock_frac = 0.05
- unknown/null → use the three scenario defaults above

---

## 5. Regional Rate Table

**File:** `data/public/drilling_rates_by_state.json`

**Schema:**
```json
{
  "US": {
    "drilling_soil": 30, "drilling_rock": 100, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2,
    "horiz_pipe": 1, "horiz_trench": 5, "mobilization": 1000,
    "source": "390geothermal_calc.xlsx baseline", "year": 2024
  },
  "CA": {
    "drilling_soil": 45, "drilling_rock": 130, "well_casing": 25,
    "sand_bag": 12, "grout_bag": 22, "utube_pipe": 2.5,
    "horiz_pipe": 1.5, "horiz_trench": 7, "mobilization": 1500,
    "source": "NREL GeoVision 2019 + RSMeans 2024", "year": 2024
  },
  ...
}
```

**Census division keys** (fallback between state and "US"):  
`"NE_div"`, `"MA_div"`, `"ENC_div"`, `"WNC_div"`, `"SA_div"`, `"ESC_div"`, `"WSC_div"`, `"Mtn_div"`, `"Pac_div"`

**Lookup order:** `state` → `division` → `"US"`. Always resolves.

**V1 data sources:**
- ~15 high-data states (CA, TX, NY, FL, IL, PA, OH, GA, CO, WA, AZ, MN, MI, NC, VA): NREL GeoVision 2019 Appendix C, IGSHPA 2020 member survey, RSMeans 2024 Mechanical
- Remaining states: Census division average from populated states
- All entries carry `source` and `year` metadata for transparency and future refresh

---

## 6. CostResult Dataclass

```python
@dataclass
class CostResult:
    total_usd: float
    cost_per_ft: float        # total_usd / L_ft — headline metric
    L_ft: float
    NB: int
    breakdown: list[dict]     # [{name, qty, unit, rate, cost_usd}, ...]
    region_used: str          # "CA", "ENC_div", or "US"
    soil_frac: float
    rock_frac: float
    scenario: str             # "best" | "base" | "worst"
```

---

## 7. API Endpoint

```
POST /api/cost
Content-Type: application/json

Request body:
{
  "L": 1234,           # total borefield length in meters (from s4)
  "NB": 16,            # number of boreholes
  "B": 6.0,            # borehole spacing in meters
  "H": 77,             # depth per borehole in meters (= L / NB)
  "state": "IL",       # 2-letter state abbreviation (from site geocode)
  "rock_class": null,  # optional SGMC rock class name or null
  # NOTE: state_abbrev must be added to /calculate/smart response — currently
  # the site dict returns k/alpha/T_g/climate_zone but not state. Implementation
  # must also expose state_abbrev in the s1 SiteData model and the smart endpoint.

  # Optional overrides (if user has contractor-specific data):
  "soil_frac_override": null,    # float 0.0–1.0
  "rates_override": null         # dict matching rate table schema
}

Response:
{
  "best":  { ...CostResult },
  "base":  { ...CostResult },
  "worst": { ...CostResult },
  "headline_per_ft": <base.cost_per_ft>,
  "region_used": "IL" | "ENC_div" | "US"
}
```

`/calculate/smart` is not modified — cost is a separate POST so the sizing endpoint stays clean and independent.

---

## 8. UI Changes

### Main tool (`/`)

After sizing results appear, a collapsible "Cost Estimate" section renders:

1. **Three-column scenario card** (Best / Base / Worst):
   - Headline: `$X/ft` composite
   - Subline: `Total: $XXX,XXX` and `Depth: X ft/borehole`

2. **Line-item breakdown table** for the selected scenario:
   - Columns: Item | Quantity | Unit | Rate | Subtotal
   - Subtotals sum to Total

3. **Contractor comparison strip**:
   - "Your project (IL): $42/ft | National avg: $36/ft | Best case: $29/ft | Worst case: $51/ft"

4. **Attribution line**: "Rates: NREL GeoVision 2019 + RSMeans 2024 (IL)"

### Dev dashboard (`/dev`) — new Section 5

- **Leaflet choropleth**: 50 states colored by base-scenario $/ft
- Representative project for comparison: NB=16, B=6m, H=77m, 500 m² small office, base formation
- Color scale: 5 quantile buckets, $25–$60/ft range
- **Click tooltip**: state name, $/ft for all 3 scenarios, data source tag
- **Rate data table** below map: all 50 states with their drilling_soil, drilling_rock rates and source

---

## 9. Data Flow

```
ZIP → s1 → state_abbrev, rock_class_name (from deep_thermal_by_county.csv)
         → s4 → L (m), H (m), NB, B (m)
                     ↓
              POST /api/cost
                     ↓
              s5.estimate_cost()
                ├─ regional_rates.get(state_abbrev) → rates dict
                ├─ line_items.calc_quantities(L_ft, H_ft, NB, B_ft, r_bore, r_pipe)
                └─ for each scenario (best/base/worst):
                       apply soil_frac, grout_frac → line item costs
                       sum → total_usd
                       cost_per_ft = total_usd / L_ft
                       → CostResult
```

---

## 10. Tests

`tests/test_s5_cost.py`:

| Test | What it verifies |
|---|---|
| `test_national_defaults_match_spreadsheet_best` | base/best ≈ $36/ft for 32 bores × 230 ft (spreadsheet best tab) |
| `test_national_defaults_match_spreadsheet_worst` | worst ≈ $36/ft for 32 bores × 380 ft (spreadsheet worst tab) |
| `test_state_override_used_when_available` | CA rates override national default |
| `test_census_division_fallback` | state with no specific data → division average |
| `test_national_fallback` | division-less state → "US" default |
| `test_rock_fraction_affects_cost` | higher rock_frac → higher total cost |
| `test_utube_pipe_is_double_footage` | U-tube qty = L_ft × 2 |
| `test_api_cost_endpoint_returns_three_scenarios` | POST /api/cost returns 200 with best/base/worst |
| `test_cost_per_ft_formula` | cost_per_ft = total_usd / L_ft (identity check) |

---

## 11. Validation Against Reference Spreadsheet

Exact values extracted from spreadsheet cells (openpyxl, data_only=True):

| Tab | NB | H_exact_m | H_rounded_ft | Drill LF | Sand bags | Grout bags | Horiz trench ft | Total cost | $/ft |
|---|---|---|---|---|---|---|---|---|---|
| Close-loop h - s (best, 0% rock) | 32 | 68.9477 | 230 | 7,360 | 2,048 | 256 | 1,116.26 | $269,933.79 | $36.69 |
| Close-loop h - c (worst, 0% rock) | 32 | 114.4545 | 380 | 12,160 | 3,328 | 416 | 1,116.26 | $439,533.79 | $36.60 |

Common inputs: B = 6.7 m = 21.98 ft, distance_to_house = 435 ft, r_bore = 0.0762 m, r_pext = 0.0167 m, rock_frac = 0 (all soil), well_casing = 0.

The estimator must reproduce total cost within ±0.5% when supplied with these identical inputs and national default rates.

---

## 12. Expandability Notes

- Adding a new state: add one entry to `drilling_rates_by_state.json` with source/year — no code change
- Adding a new line item: extend the `LINE_ITEMS` list in `line_items.py` and the rate table schema
- Future: integrate RS Means API or IGSHPA live feed to refresh rates automatically
- Future (s6): cost model feeds into hybrid boiler peak-shaving economics ($/peak-kW avoided)

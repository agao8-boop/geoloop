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

These mirror the reference spreadsheet exactly (both "Close-loop h - s" best and "Close-loop h - c" worst tabs).

| # | Item | Quantity formula | Default rate | Unit |
|---|---|---|---|---|
| 1 | Mobilization | 1 flat | $1,000 | /project |
| 2 | Drilling — soil | `L_ft × soil_frac` | $30 | /LF |
| 3 | Drilling — rock | `L_ft × rock_frac` | $100 | /LF |
| 4 | Well casing | `L_ft` | $20 | /LF |
| 5 | Sand (bentonite bags) | `annulus_vol_ft3 × sand_fill_frac / bag_vol_ft3` | $10 | /50lb bag |
| 6 | Grout (CETCO High TC bags) | `annulus_vol_ft3 × grout_fill_frac / bag_vol_ft3` | $20 | /50lb bag |
| 7 | U-tube HDPE pipe | `L_ft × 2` (two legs per borehole) | $2 | /LF |
| 8 | Horizontal header pipe | `NB × B_ft` | $1 | /LF |
| 9 | Horizontal trench | same as header LF | $5 | /LF |

**Derived quantities:**
- `L_ft = L_meters × 3.28084`
- `B_ft = B_meters × 3.28084`
- `H_ft = H_meters × 3.28084` (depth per borehole = L / NB)
- `annulus_vol_ft3 = π × (r_bore_ft² - r_pipe_ext_ft²) × H_ft × NB`
  - `r_bore = 0.06 m` (default), `r_pipe_ext = 0.0167 m` (default, outer radius of U-tube)
  - `sand_bag_vol_ft3 = 0.80` (50 lb bag of dry bentonite sand at loose fill density ~62 lb/ft³)
  - `grout_bag_vol_ft3 = 0.50` (50 lb bag of CETCO High TC at mixed density ~100 lb/ft³)
- `soil_frac + rock_frac = 1.0`
- `sand_fill_frac + grout_fill_frac = 1.0`

---

## 4. Scenario Modeling

Three passes, returning all three so the UI can display a range:

| Scenario | soil_frac | rock_frac | sand_fill_frac | grout_fill_frac | Interpretation |
|---|---|---|---|---|---|
| best | 0.80 | 0.20 | 0.80 | 0.20 | Mostly sand, shallow water table |
| base | 0.60 | 0.40 | 0.50 | 0.50 | Mixed formation |
| worst | 0.20 | 0.80 | 0.20 | 0.80 | Mostly clay/rock, grouted to surface |

If the site's `rock_class_name` (from SGMC via deep thermal) is available, `rock_frac` is set from a lookup table (igneous/metamorphic → 0.90, sedimentary → 0.40, etc.) and the scenario range narrows around that value. If not available, use the three defaults above.

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

The spreadsheet gives two anchor points for regression tests:

| Tab | Formation | Boreholes | Depth | Total LF | Total cost | $/ft |
|---|---|---|---|---|---|---|
| Close-loop h - s (best) | 80% sand | 32 | 230 ft | 7,360 LF | $269,934 | ~$36.7 |
| Close-loop h - c (worst) | 80% clay | 32 | 380 ft | 12,160 LF | $439,534 | ~$36.2 |

The estimator must reproduce these within ±2% when supplied with identical inputs and national default rates.

---

## 12. Expandability Notes

- Adding a new state: add one entry to `drilling_rates_by_state.json` with source/year — no code change
- Adding a new line item: extend the `LINE_ITEMS` list in `line_items.py` and the rate table schema
- Future: integrate RS Means API or IGSHPA live feed to refresh rates automatically
- Future (s6): cost model feeds into hybrid boiler peak-shaving economics ($/peak-kW avoided)

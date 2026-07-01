# s6 Strategy — Hybrid GSHP Design Spec

**Date:** 2026-06-30  
**Stage:** s6 of GeoSite Advisor pipeline  
**Status:** Approved for implementation

---

## 1. Purpose

Every project runs a **mandatory** hybrid GSHP analysis. A supplemental peaker (electric heater or chiller) is always sized alongside the borefield. The output is:

- Load Duration Curve with cutoff
- Peaker capacity (kW) and type
- Trimmed borefield length (after peaker offloads peaks)
- Before/after comparison (L, H, cost)
- Two visualizations: annual load profile and load duration curve

---

## 2. Imbalance Detection — Paper's Method (Philippe et al. 2010)

**Step 1:** Extract heating-only and cooling-only three-pulse values from the 8760h profile.

From `data/public/prototype_loads_hourly.json` (extracted from EnergyPlus cache):
- Ground load sign convention: `positive = cooling (heat injection), negative = heating (heat extraction)`

```
heating_hours = [h for h in ground_load_8760 if h < 0]
cooling_hours = [h for h in ground_load_8760 if h > 0]

# Three-pulse for each side (SIGNED, each side separately)
q_h_heat = min(ground_load_8760)         # most negative hour (heating peak)
q_m_heat = min(monthly_averages)         # most negative monthly avg
q_y_heat = mean(heating_hours)           # annual heating avg (negative)

q_h_cool = max(ground_load_8760)         # most positive hour (cooling peak)
q_m_cool = max(monthly_averages)         # most positive monthly avg
q_y_cool = mean(cooling_hours)           # annual cooling avg (positive)
```

**Step 2:** Run sizing separately for each side → L_h, L_c

This matches the spreadsheet structure: `Close-loop h` tab sizes heating-only, `Close-loop c` tabs sizes cooling-only.

**Step 3:** Compute imbalance ratio

```
imbalance_ratio = max(L_h, L_c) / min(L_h, L_c)
dominant_mode   = "heating" if L_h > L_c else "cooling"
```

From the reference project (`prelim` tab): NB_heating=32, NB_cooling=20 → ratio=1.60.  
Spreadsheet treats this as a clear heating-dominant case without an explicit numeric threshold.

**Proposed threshold:** `imbalance_ratio > 1.25` → Case 1 (imbalanced).  
⚠️ **Verify against paper text.** The paper compares L_h vs L_c but does not state an explicit threshold in the spreadsheet. This 1.25 value is proposed as a conservative default and must be confirmed.

User-configurable parameter: `imbalance_threshold` (default: 1.25).

---

## 3. Load Duration Curve (LDC) — Both Cases

**Inputs:** Full 8760h ground load array (W)

**Algorithm:**
```python
sorted_by_magnitude = sorted(ground_load_8760, key=abs, reverse=True)
cutoff_idx   = int(8760 * ldc_cutoff_pct / 100)         # default 10%
cutoff_W     = abs(sorted_by_magnitude[cutoff_idx])      # threshold value
```

**Output:**
- `cutoff_W`: the load level the borefield must handle (new q_h)
- Any hour with `|load| > cutoff_W` → handled by peaker

**Re-derive trimmed three-pulse values:**
```python
trimmed_load = [min(max(h, -cutoff_W), cutoff_W) for h in ground_load_8760]

q_h_trimmed = max(abs(h) for h in trimmed_load)                     # = cutoff_W
q_m_trimmed = max peak monthly avg across trimmed_load months
q_y_trimmed = mean(trimmed_load)                                     # ≈ original q_y
```

**User parameter:** `ldc_cutoff_pct` (default: 10%, range 1–40%).

---

## 4. Case 1 — Imbalanced Load (imbalance_ratio > threshold)

The borefield cannot efficiently serve both sides without long-term ground temperature drift.

**Approach:**
1. Apply LDC cutoff to the **dominant side's peak loads** specifically.  
   All non-dominant hours are passed to the borefield unchanged.
2. The peaker is a **single-type unit** matching the dominant side:
   - Heating-dominant (L_h > L_c) → **electric heater**
   - Cooling-dominant (L_c > L_h) → **chiller**
3. Peaker capacity = `max |load| in the dominant-side hours above cutoff_W`.
4. Borefield is re-sized using the trimmed three-pulse values.

**Peaker sizing (proposed, verify against paper):**
```
peaker_kW = max(|h| for h in ground_load_8760 if |h| > cutoff_W and h * sign_dominant > 0) / 1000
```

This is the instantaneous peak demand that the peaker must supply.  
⚠️ The paper may define peaker sizing differently (e.g., based on rated capacity with a safety factor, or annual energy to calculate run hours). Flag for verification before detailed engineering.

---

## 5. Case 2 — Balanced Load (imbalance_ratio ≤ threshold)

Loads are approximately balanced; ground temperature drift is minimal. A peaker still reduces capital cost by clipping the rarest, largest loads.

**Approach:**
1. Apply LDC cutoff symmetrically to **both heating and cooling peaks**.
2. Separate capacities computed for each side:
   - Heating peaker (electric heater): `max |heat load above cutoff|`
   - Cooling peaker (chiller): `max |cool load above cutoff|`
3. Report as single "combined supplemental unit": `peaker_kW = max(heat_kW, cool_kW)`.  
   Default equipment: one **electric heater** + one **chiller** at equal capacity.
4. Borefield re-sized using trimmed three-pulse values (same formula as Case 1).

**Peaker sizing:** Same instantaneous peak formula as Case 1, applied to each side independently.

---

## 6. Peaker Equipment — Default Naming

| Case | Dominant | Peaker label |
|---|---|---|
| Case 1 | Heating | Electric heater |
| Case 1 | Cooling | Chiller |
| Case 2 | Balanced | Electric heater + Chiller (reported as one unit at max capacity) |

Future: extend equipment options (gas boiler, cooling tower, DOAS, thermal storage) based on user-provided site constraints and economics. See `docs/future/s6_optimization_notes.md`.

---

## 7. Data Architecture

### New preprocessing script: `scripts/extract_hourly_loads.py`

Reads all 48 cached EnergyPlus CSVs from `data/energyplus_cache/work/{bt}_{cz}/ep_output/eplusout.csv`.
Computes ground load per hour: `ground_load[h] = sum(cool_J[h]) / 3600 - sum(heat_J[h]) / 3600` (W).
Writes `data/public/prototype_loads_hourly.json`:

```json
{
  "_note": "Hourly ground loads in W. Positive = cooling (heat injection). Negative = heating (extraction).",
  "small_office": {
    "5A": [8760 floats],
    "3B": [...],
    "2A": [...]
  },
  "medium_office": { ... },
  "large_office": { ... }
}
```

Size: ~2.5 MB uncompressed, ~300 KB gzip. Served via `GET /api/loads/hourly`.

### Scaling: floor_area_m2 and year_built

If user overrides floor area, scale hourly profile proportionally:
```python
hourly_scaled = [h * (floor_area_m2 / prototype_area_m2) * year_factor for h in hourly_raw]
```

---

## 8. Module Structure

```
geosite/s6_strategy/
    __init__.py           # public API: run_strategy() → StrategyResult
    load_profile.py       # load 8760h array, apply scaling
    ldc.py                # LDC cutoff, trimming, re-derive three-pulse values
    peaker.py             # Case 1 and Case 2 peaker sizing
    strategy.py           # orchestration: detect case → LDC → peaker → re-size → cost
    models.py             # StrategyResult dataclass
```

### StrategyResult

```python
@dataclass
class StrategyResult:
    # Case detection
    case: int                        # 1 or 2
    imbalance_ratio: float           # L_h / L_c or L_c / L_h
    dominant_mode: str               # "heating" | "cooling" | "balanced"
    L_h: float                       # borefield length, heating-only sizing (m)
    L_c: float                       # borefield length, cooling-only sizing (m)

    # LDC
    ldc_cutoff_pct: float            # x% used
    cutoff_W: float                  # ground load threshold (W)

    # Peaker
    peaker_kW: float                 # supplemental unit capacity
    peaker_type: str                 # "electric_heater" | "chiller" | "electric_heater+chiller"
    peaker_heat_kW: float            # Case 2 only: heating-side peaker kW
    peaker_cool_kW: float            # Case 2 only: cooling-side peaker kW

    # Three-pulse — before and after
    q_h_before: float
    q_m_before: float
    q_y_before: float
    q_h_trimmed: float
    q_m_trimmed: float
    q_y_trimmed: float

    # Sizing — before and after
    L_before: float                  # borefield without peaker (dominant sizing, m)
    H_before: float
    L_after: float                   # borefield with trimmed load (m)
    H_after: float

    # Cost — before and after (CostResult from s5)
    cost_before: dict
    cost_after: dict

    # Profiles (for visualization)
    hourly_profile: list[float]      # original 8760h ground load (W)
    hourly_trimmed: list[float]      # trimmed 8760h profile (W) — borefield sees this
```

---

## 9. API Endpoint

```
POST /api/strategy
{
  "building_type":       "medium_office",
  "climate_zone":        "5A",
  "NB":                  16,
  "B":                   6.0,
  "state":               "IL",
  "floor_area_m2":       null,
  "year_built":          2020,
  "ldc_cutoff_pct":      10,              # optional, default 10
  "imbalance_threshold": 1.25             # optional, default 1.25
}
```

Response: full `StrategyResult` as JSON. `hourly_profile` and `hourly_trimmed` returned as arrays (8760 elements each).

The `POST /calculate/smart` and `POST /api/cost` flows remain unchanged. Strategy is a separate optional call.

---

## 10. Visualizations

All charts use **Chart.js** (CDN, no build step).

### Chart A — Annual Hourly Ground Load Profile

- X: hour of year (0–8760)
- Y: ground load W
- Two colors: heating hours (negative, blue) vs cooling hours (positive, red)
- Horizontal dashed line at ±cutoff_W
- Shaded region outside cutoff = peaker zone
- Shown in both user tool (compact, 180px) and dev tool (360px)

### Chart B — Load Duration Curve (dev tool only)

- X: rank (sorted hour, 1=largest, 8760=smallest)
- Y: |ground load| W
- Vertical line at cutoff_idx (x% of 8760)
- Shaded region left of line = peaker zone
- Area right of line = borefield zone

### Chart C — Before/After Comparison (both tools, different detail)

- Two side-by-side bar clusters: Without Peaker / With Peaker
- Bars: L (m), H (m), cost ($)
- Peaker capacity callout
- User tool: simplified, just the numbers + one-sentence summary
- Dev tool: full chart + all intermediate values table

---

## 11. UI Changes

### index.html — s6 section (after s5 cost)

After s5 cost section renders, auto-trigger strategy call.
Show:
- One-line summary: *"Hybrid system reduces borefield from 1,696 m → 980 m (−42%) with a 35 kW [electric heater / chiller]."*
- Compact Chart A (annual profile with cutoff line, 180px height)
- Three callout cards: Without Peaker | With Peaker | Peaker Unit

### dev.html — s6 trace step (after s5 cost step in pipeline trace)

Show:
- Case detection (Case 1/2, ratio, dominant side)
- LDC parameters used
- Chart A (full, 360px)
- Chart B (LDC curve, dev only, 300px)
- Chart C (before/after bars)
- Full StrategyResult table (all fields)

---

## 12. Tests

`tests/test_s6_strategy.py`:

| Test | What it verifies |
|---|---|
| `test_ldc_cutoff_10pct` | 10% cutoff on known profile yields correct cutoff_W |
| `test_trimmed_q_h_equals_cutoff` | q_h_trimmed = cutoff_W exactly |
| `test_case1_detected_for_large_ratio` | L_h/L_c > 1.25 → Case 1 |
| `test_case2_detected_for_balanced` | L_h/L_c ≤ 1.25 → Case 2 |
| `test_peaker_type_electric_heater_for_heating_dominant` | L_h > L_c → "electric_heater" |
| `test_peaker_type_chiller_for_cooling_dominant` | L_c > L_h → "chiller" |
| `test_l_after_less_than_l_before` | trimming always reduces borefield |
| `test_floor_area_scaling` | hourly profile scales linearly with area |
| `test_api_strategy_endpoint` | POST /api/strategy returns full StrategyResult |

---

## 13. Open Items / Verification Needed

1. **Imbalance threshold 1.25:** Paper does not state an explicit value — proposed from engineering judgment. Verify against Philippe et al. (2010) full text or Kavanaugh & Rafferty (2014).

2. **Peaker sizing method:** Currently proposed as instantaneous peak demand of trimmed hours. Paper may specify sizing with a safety factor or rated-load method. Verify before detailed engineering handoff.

3. **Case 2 combined peaker:** Reporting as `max(heat_kW, cool_kW)` is conservative. Real design would have separate units or a reversible heat pump. Acceptable for V1 as a conservative bound.

4. **See also:** `docs/future/s6_optimization_notes.md` for the optimal cutoff question.

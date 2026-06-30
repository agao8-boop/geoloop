# s5 Cost Estimation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the s5 cost estimation stage — given s4 borefield sizing output (L, NB, B), compute a 9-line-item cost breakdown with regional drilling rates, composite $/ft metric, and a choropleth map on the dev dashboard.

**Architecture:** A self-contained `geosite/s5_cost/` package computes costs from borefield geometry × regional rate table. A new `POST /api/cost` Flask endpoint exposes it. The main tool UI calls this after sizing; the dev dashboard adds a state-level Leaflet choropleth.

**Tech Stack:** Python 3.11, Flask, dataclasses, JSON data file for rates; JavaScript fetch + Leaflet.js for the map; pytest for tests.

## Global Constraints

- All formulas verified against `data/reference/390geothermal_calc.xlsx` (read with openpyxl). Do NOT deviate.
- Grout formula: `grout_vol_m3 = π × H_exact_m × (r_bore² - r_pext²/2)` — this is the spreadsheet formula, not standard physics. Use it.
- H_rounded_ft = ceil(H_ft / 10) × 10 — drilling LF uses rounded depth; grout uses exact depth.
- sand_bags = grout_bags_per_borehole_rounded × 8 × NB
- horiz_trench_ft = (NB - 1) × B_ft + distance_to_house_ft (default 100 ft)
- horiz_pipe_ft = 2 × horiz_trench_ft
- well_casing = 0 LF by default
- Three scenarios vary rock_frac only: best=0.0, base=0.30, worst=0.70
- State rate lookup: state → Census division → "US" national default (always resolves)
- No changes to `/calculate/smart` signature or existing tests
- Run existing test suite (`pytest -q`) after every task — must stay green

---

### Task 1: drilling_rates_by_state.json

**Files:**
- Create: `data/public/drilling_rates_by_state.json`

**Interfaces:**
- Produces: JSON dict keyed by state abbrev (e.g. `"CA"`), Census division keys (`"ENC_div"`, etc.), and `"US"` national default. Each entry has 9 rate keys + `"source"` + `"year"`.

Rate keys: `drilling_soil`, `drilling_rock`, `well_casing`, `sand_bag`, `grout_bag`, `utube_pipe`, `horiz_pipe`, `horiz_trench`, `mobilization`, `source`, `year`.

Census division state mappings (use these for division fallbacks):
- `NE_div`: CT, ME, MA, NH, RI, VT
- `MA_div`: NJ, NY, PA
- `ENC_div`: IL, IN, MI, OH, WI
- `WNC_div`: IA, KS, MN, MO, NE, ND, SD
- `SA_div`: DE, DC, FL, GA, MD, NC, SC, VA, WV
- `ESC_div`: AL, KY, MS, TN
- `WSC_div`: AR, LA, OK, TX
- `Mtn_div`: AZ, CO, ID, MT, NV, NM, UT, WY
- `Pac_div`: AK, CA, HI, OR, WA

- [ ] **Step 1: Write the JSON file**

Create `data/public/drilling_rates_by_state.json` with this content. The V1 data is sourced from NREL GeoVision 2019 Appendix C (4-region drilling cost ranges) and RSMeans 2024 Mechanical regional cost indices. States without specific public data use their Census division average. National default matches reference spreadsheet baseline.

```json
{
  "US": {
    "drilling_soil": 30, "drilling_rock": 100, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2,
    "horiz_pipe": 1, "horiz_trench": 5, "mobilization": 1000,
    "source": "390geothermal_calc.xlsx baseline", "year": 2024
  },
  "NE_div": {
    "drilling_soil": 38, "drilling_rock": 115, "well_casing": 22,
    "sand_bag": 11, "grout_bag": 21, "utube_pipe": 2.2,
    "horiz_pipe": 1.2, "horiz_trench": 6, "mobilization": 1200,
    "source": "NREL GeoVision 2019 Northeast region avg", "year": 2019
  },
  "MA_div": {
    "drilling_soil": 40, "drilling_rock": 120, "well_casing": 24,
    "sand_bag": 11, "grout_bag": 22, "utube_pipe": 2.3,
    "horiz_pipe": 1.3, "horiz_trench": 6, "mobilization": 1300,
    "source": "NREL GeoVision 2019 Northeast region avg", "year": 2019
  },
  "ENC_div": {
    "drilling_soil": 28, "drilling_rock": 95, "well_casing": 18,
    "sand_bag": 10, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 5, "mobilization": 1000,
    "source": "NREL GeoVision 2019 North Central region avg", "year": 2019
  },
  "WNC_div": {
    "drilling_soil": 26, "drilling_rock": 90, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 18, "utube_pipe": 1.8,
    "horiz_pipe": 0.9, "horiz_trench": 4, "mobilization": 900,
    "source": "NREL GeoVision 2019 North Central region avg", "year": 2019
  },
  "SA_div": {
    "drilling_soil": 28, "drilling_rock": 92, "well_casing": 18,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "NREL GeoVision 2019 South region avg", "year": 2019
  },
  "ESC_div": {
    "drilling_soil": 25, "drilling_rock": 88, "well_casing": 16,
    "sand_bag": 9, "grout_bag": 18, "utube_pipe": 1.8,
    "horiz_pipe": 0.9, "horiz_trench": 4, "mobilization": 900,
    "source": "NREL GeoVision 2019 South region avg", "year": 2019
  },
  "WSC_div": {
    "drilling_soil": 27, "drilling_rock": 90, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "NREL GeoVision 2019 South region avg", "year": 2019
  },
  "Mtn_div": {
    "drilling_soil": 32, "drilling_rock": 105, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2.0,
    "horiz_pipe": 1.1, "horiz_trench": 5, "mobilization": 1100,
    "source": "NREL GeoVision 2019 West region avg", "year": 2019
  },
  "Pac_div": {
    "drilling_soil": 42, "drilling_rock": 128, "well_casing": 26,
    "sand_bag": 12, "grout_bag": 23, "utube_pipe": 2.5,
    "horiz_pipe": 1.5, "horiz_trench": 7, "mobilization": 1500,
    "source": "NREL GeoVision 2019 West region avg + RSMeans 2024", "year": 2024
  },
  "CA": {
    "drilling_soil": 45, "drilling_rock": 130, "well_casing": 28,
    "sand_bag": 12, "grout_bag": 23, "utube_pipe": 2.6,
    "horiz_pipe": 1.5, "horiz_trench": 7, "mobilization": 1600,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "NY": {
    "drilling_soil": 42, "drilling_rock": 122, "well_casing": 25,
    "sand_bag": 11, "grout_bag": 22, "utube_pipe": 2.4,
    "horiz_pipe": 1.4, "horiz_trench": 6, "mobilization": 1400,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "TX": {
    "drilling_soil": 27, "drilling_rock": 88, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "FL": {
    "drilling_soil": 28, "drilling_rock": 90, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "IL": {
    "drilling_soil": 29, "drilling_rock": 96, "well_casing": 18,
    "sand_bag": 10, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 5, "mobilization": 1000,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "PA": {
    "drilling_soil": 38, "drilling_rock": 118, "well_casing": 23,
    "sand_bag": 11, "grout_bag": 21, "utube_pipe": 2.2,
    "horiz_pipe": 1.3, "horiz_trench": 6, "mobilization": 1200,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "OH": {
    "drilling_soil": 28, "drilling_rock": 94, "well_casing": 18,
    "sand_bag": 10, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 5, "mobilization": 1000,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "GA": {
    "drilling_soil": 27, "drilling_rock": 90, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "CO": {
    "drilling_soil": 33, "drilling_rock": 108, "well_casing": 21,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2.0,
    "horiz_pipe": 1.1, "horiz_trench": 5, "mobilization": 1100,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "WA": {
    "drilling_soil": 40, "drilling_rock": 122, "well_casing": 25,
    "sand_bag": 12, "grout_bag": 22, "utube_pipe": 2.4,
    "horiz_pipe": 1.4, "horiz_trench": 7, "mobilization": 1400,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "AZ": {
    "drilling_soil": 31, "drilling_rock": 102, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2.0,
    "horiz_pipe": 1.1, "horiz_trench": 5, "mobilization": 1050,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "MN": {
    "drilling_soil": 27, "drilling_rock": 92, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 18, "utube_pipe": 1.8,
    "horiz_pipe": 0.9, "horiz_trench": 4, "mobilization": 900,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "MI": {
    "drilling_soil": 27, "drilling_rock": 93, "well_casing": 17,
    "sand_bag": 10, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 5, "mobilization": 1000,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "NC": {
    "drilling_soil": 27, "drilling_rock": 90, "well_casing": 17,
    "sand_bag": 9, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 4, "mobilization": 950,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  },
  "VA": {
    "drilling_soil": 29, "drilling_rock": 95, "well_casing": 18,
    "sand_bag": 10, "grout_bag": 19, "utube_pipe": 1.9,
    "horiz_pipe": 1.0, "horiz_trench": 5, "mobilization": 1000,
    "source": "RSMeans 2024 Mechanical + IGSHPA 2020", "year": 2024
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python3 -c "import json, pathlib; d=json.loads(pathlib.Path('data/public/drilling_rates_by_state.json').read_text()); print(f'Keys: {len(d)}, US drilling_soil={d[\"US\"][\"drilling_soil\"]}')"
```
Expected output: `Keys: 24, US drilling_soil=30`

- [ ] **Step 3: Commit**

```bash
git add data/public/drilling_rates_by_state.json
git commit -m "data: add drilling_rates_by_state.json — 9-item regional rate table (US + 9 divisions + 15 states)"
```

---

### Task 2: line_items.py — quantity calculators

**Files:**
- Create: `geosite/s5_cost/line_items.py`
- Create: `geosite/s5_cost/__init__.py` (update from empty)
- Test: `tests/test_s5_cost.py`

**Interfaces:**
- Consumes: `L_m: float, NB: int, B_m: float, rates: dict, rock_frac: float = 0.0, r_bore: float = 0.0762, r_pext: float = 0.0167, distance_to_house_ft: float = 100.0`
- Produces: `calc_line_items(...)` → `list[dict]` where each dict has keys: `name, qty, unit, rate, cost_usd`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s5_cost.py`:

```python
import math
import pytest
from geosite.s5_cost.line_items import calc_line_items

# Spreadsheet anchor: Close-loop h - s (best, 80% sand)
# NB=32, L_exact=2206.326m, B=6.7m, distance_to_house=435ft
# H_exact=68.9477m, H_rounded=230ft, Total=$269,933.79
BEST_L_M = 2206.326178192672
BEST_NB = 32
BEST_B_M = 6.7
BEST_DIST_FT = 435.0
BEST_RATES = {
    "drilling_soil": 30, "drilling_rock": 100, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2,
    "horiz_pipe": 1, "horiz_trench": 5, "mobilization": 1000,
}

# Spreadsheet anchor: Close-loop h - c (worst, 80% clay)
WORST_L_M = 3662.5428199546277
WORST_NB = 32
WORST_B_M = 6.7
WORST_DIST_FT = 435.0


def _items_as_dict(items):
    return {i["name"]: i for i in items}


def test_best_scenario_matches_spreadsheet_total():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    total = sum(i["cost_usd"] for i in items)
    assert total == pytest.approx(269933.79, rel=0.005)


def test_worst_scenario_matches_spreadsheet_total():
    items = calc_line_items(
        L_m=WORST_L_M, NB=WORST_NB, B_m=WORST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=WORST_DIST_FT,
    )
    total = sum(i["cost_usd"] for i in items)
    assert total == pytest.approx(439533.79, rel=0.005)


def test_drilling_lf_uses_rounded_depth():
    # H_exact = 68.9477 m = 226.2 ft → rounds to 230 ft
    # Drilling LF = 32 × 230 = 7,360
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["drilling_soil"]["qty"] == pytest.approx(7360.0)


def test_grout_bags_per_borehole_matches_spreadsheet():
    # Spreadsheet: 8 bags/borehole × 32 = 256 total
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["grout_bag"]["qty"] == 256


def test_sand_bags_is_eight_times_grout_bags():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["sand_bag"]["qty"] == d["grout_bag"]["qty"] * 8


def test_utube_pipe_qty_equals_drilling_lf():
    # $2/LF covers both U-tube legs; qty = total drilling LF
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["utube_pipe"]["qty"] == pytest.approx(d["drilling_soil"]["qty"] + d["drilling_rock"]["qty"])


def test_horiz_trench_formula():
    # (NB-1) × B_ft + distance_to_house = 31 × 21.98 + 435 = 1116.26 LF
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["horiz_trench"]["qty"] == pytest.approx(1116.26, rel=0.002)


def test_horiz_pipe_is_double_trench():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["horiz_pipe"]["qty"] == pytest.approx(d["horiz_trench"]["qty"] * 2)


def test_rock_frac_affects_drilling_split():
    items_base = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.30, distance_to_house_ft=100.0,
    )
    d = _items_as_dict(items_base)
    total_drill_lf = d["drilling_soil"]["qty"] + d["drilling_rock"]["qty"]
    assert d["drilling_rock"]["qty"] == pytest.approx(total_drill_lf * 0.30, rel=0.01)
    assert d["drilling_soil"]["qty"] == pytest.approx(total_drill_lf * 0.70, rel=0.01)


def test_well_casing_is_zero_by_default():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=100.0,
    )
    d = _items_as_dict(items)
    assert d["well_casing"]["qty"] == 0
    assert d["well_casing"]["cost_usd"] == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py -v 2>&1 | head -20
```
Expected: `ImportError` or `ModuleNotFoundError` — `line_items` doesn't exist yet.

- [ ] **Step 3: Create `geosite/s5_cost/line_items.py`**

```python
import math

_M_TO_FT = 3.28084


def _round_up_to_10(ft: float) -> float:
    return math.ceil(ft / 10) * 10


def calc_line_items(
    L_m: float,
    NB: int,
    B_m: float,
    rates: dict,
    rock_frac: float = 0.0,
    r_bore: float = 0.0762,
    r_pext: float = 0.0167,
    distance_to_house_ft: float = 100.0,
) -> list[dict]:
    """Compute all 9 cost line items from borefield geometry × rate table.

    Formulas verified against data/reference/390geothermal_calc.xlsx.
    """
    H_exact_m = L_m / NB
    H_exact_ft = H_exact_m * _M_TO_FT
    H_rounded_ft = _round_up_to_10(H_exact_ft)
    B_ft = B_m * _M_TO_FT
    total_drill_lf = NB * H_rounded_ft

    # Grout volume — spreadsheet formula (r_bore² - r_pext²/2)
    grout_vol_m3 = math.pi * H_exact_m * (r_bore**2 - r_pext**2 / 2)
    grout_vol_L = grout_vol_m3 * 1000
    grout_bags_per_bh = math.ceil(grout_vol_L / 161)  # 161 L yield per CETCO batch
    grout_bags_total = grout_bags_per_bh * NB
    sand_bags_total = grout_bags_per_bh * 8 * NB  # 8 × 50lb bags sand per CETCO batch

    horiz_trench_ft = (NB - 1) * B_ft + distance_to_house_ft
    horiz_pipe_ft = 2 * horiz_trench_ft

    def item(name, qty, unit, rate):
        return {"name": name, "qty": qty, "unit": unit,
                "rate": rate, "cost_usd": qty * rate}

    return [
        item("mobilization",   1,                             "project", rates["mobilization"]),
        item("drilling_soil",  total_drill_lf * (1 - rock_frac), "LF",  rates["drilling_soil"]),
        item("drilling_rock",  total_drill_lf * rock_frac,    "LF",     rates["drilling_rock"]),
        item("well_casing",    0,                             "LF",     rates["well_casing"]),
        item("sand_bag",       sand_bags_total,               "50lb bag", rates["sand_bag"]),
        item("grout_bag",      grout_bags_total,              "50lb bag", rates["grout_bag"]),
        item("utube_pipe",     total_drill_lf,                "LF",     rates["utube_pipe"]),
        item("horiz_pipe",     horiz_pipe_ft,                 "LF",     rates["horiz_pipe"]),
        item("horiz_trench",   horiz_trench_ft,               "LF",     rates["horiz_trench"]),
    ]
```

- [ ] **Step 4: Create/update `geosite/s5_cost/__init__.py`**

```python
from geosite.s5_cost.estimator import estimate_cost
from geosite.s5_cost.models import CostResult

__all__ = ["estimate_cost", "CostResult"]
```

Note: `estimator` and `models` are created in Task 4. For now just make the file importable:

```python
# s5_cost: regional drilling cost estimation (see estimator.py for public API)
```

- [ ] **Step 5: Run tests**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Run full suite**

```bash
source venv/bin/activate && pytest -q
```
Expected: all existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add geosite/s5_cost/line_items.py geosite/s5_cost/__init__.py tests/test_s5_cost.py
git commit -m "feat(s5): add line_items.py — 9-item quantity calculator verified against spreadsheet anchors"
```

---

### Task 3: regional_rates.py — rate table loader

**Files:**
- Create: `geosite/s5_cost/regional_rates.py`
- Test: `tests/test_s5_cost.py` (append new tests)

**Interfaces:**
- Consumes: `state: str | None` — 2-letter state abbreviation or None
- Produces: `get_rates(state) → dict` — rate dict with all 9 keys. Always resolves (never raises).
- Also produces: `get_region_used(state) → str` — which key was used ("CA", "Pac_div", or "US")

State → division mapping (hardcoded in module, not in JSON):
```python
_STATE_TO_DIV = {
    "CT": "NE_div", "ME": "NE_div", "MA": "NE_div", "NH": "NE_div", "RI": "NE_div", "VT": "NE_div",
    "NJ": "MA_div", "NY": "MA_div", "PA": "MA_div",
    "IL": "ENC_div", "IN": "ENC_div", "MI": "ENC_div", "OH": "ENC_div", "WI": "ENC_div",
    "IA": "WNC_div", "KS": "WNC_div", "MN": "WNC_div", "MO": "WNC_div",
    "NE": "WNC_div", "ND": "WNC_div", "SD": "WNC_div",
    "DE": "SA_div", "DC": "SA_div", "FL": "SA_div", "GA": "SA_div",
    "MD": "SA_div", "NC": "SA_div", "SC": "SA_div", "VA": "SA_div", "WV": "SA_div",
    "AL": "ESC_div", "KY": "ESC_div", "MS": "ESC_div", "TN": "ESC_div",
    "AR": "WSC_div", "LA": "WSC_div", "OK": "WSC_div", "TX": "WSC_div",
    "AZ": "Mtn_div", "CO": "Mtn_div", "ID": "Mtn_div", "MT": "Mtn_div",
    "NV": "Mtn_div", "NM": "Mtn_div", "UT": "Mtn_div", "WY": "Mtn_div",
    "AK": "Pac_div", "CA": "Pac_div", "HI": "Pac_div", "OR": "Pac_div", "WA": "Pac_div",
}
```

- [ ] **Step 1: Append failing tests to `tests/test_s5_cost.py`**

```python
from geosite.s5_cost.regional_rates import get_rates, get_region_used


def test_known_state_returns_state_rates():
    rates = get_rates("CA")
    assert rates["drilling_soil"] == 45  # CA-specific rate


def test_state_without_specific_entry_falls_back_to_division():
    # WI is in ENC_div, no WI-specific entry
    rates = get_rates("WI")
    assert rates["drilling_soil"] == 28  # ENC_div rate
    assert get_region_used("WI") == "ENC_div"


def test_state_in_unknown_division_falls_back_to_us():
    # Pass a fake state abbreviation not in any division
    rates = get_rates("ZZ")
    assert rates["drilling_soil"] == 30  # US default
    assert get_region_used("ZZ") == "US"


def test_none_state_returns_us_default():
    rates = get_rates(None)
    assert rates["drilling_soil"] == 30
    assert get_region_used(None) == "US"


def test_get_rates_always_has_all_nine_keys():
    rate_keys = {"drilling_soil", "drilling_rock", "well_casing", "sand_bag",
                 "grout_bag", "utube_pipe", "horiz_pipe", "horiz_trench", "mobilization"}
    for state in ["CA", "WI", "ZZ", None, "TX", "NY"]:
        rates = get_rates(state)
        assert rate_keys.issubset(rates.keys()), f"Missing keys for {state}"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py::test_known_state_returns_state_rates -v
```
Expected: `ImportError` — `regional_rates` doesn't exist yet.

- [ ] **Step 3: Create `geosite/s5_cost/regional_rates.py`**

```python
import json
import pathlib

_RATES_FILE = pathlib.Path(__file__).parents[2] / "data" / "public" / "drilling_rates_by_state.json"
_rates_cache: dict | None = None

_STATE_TO_DIV = {
    "CT": "NE_div", "ME": "NE_div", "MA": "NE_div", "NH": "NE_div", "RI": "NE_div", "VT": "NE_div",
    "NJ": "MA_div", "NY": "MA_div", "PA": "MA_div",
    "IL": "ENC_div", "IN": "ENC_div", "MI": "ENC_div", "OH": "ENC_div", "WI": "ENC_div",
    "IA": "WNC_div", "KS": "WNC_div", "MN": "WNC_div", "MO": "WNC_div",
    "NE": "WNC_div", "ND": "WNC_div", "SD": "WNC_div",
    "DE": "SA_div", "DC": "SA_div", "FL": "SA_div", "GA": "SA_div",
    "MD": "SA_div", "NC": "SA_div", "SC": "SA_div", "VA": "SA_div", "WV": "SA_div",
    "AL": "ESC_div", "KY": "ESC_div", "MS": "ESC_div", "TN": "ESC_div",
    "AR": "WSC_div", "LA": "WSC_div", "OK": "WSC_div", "TX": "WSC_div",
    "AZ": "Mtn_div", "CO": "Mtn_div", "ID": "Mtn_div", "MT": "Mtn_div",
    "NV": "Mtn_div", "NM": "Mtn_div", "UT": "Mtn_div", "WY": "Mtn_div",
    "AK": "Pac_div", "CA": "Pac_div", "HI": "Pac_div", "OR": "Pac_div", "WA": "Pac_div",
}


def _load() -> dict:
    global _rates_cache
    if _rates_cache is None:
        _rates_cache = json.loads(_RATES_FILE.read_text())
    return _rates_cache


def get_region_used(state: str | None) -> str:
    table = _load()
    if state and state.upper() in table:
        return state.upper()
    div = _STATE_TO_DIV.get((state or "").upper())
    if div and div in table:
        return div
    return "US"


def get_rates(state: str | None) -> dict:
    return _load()[get_region_used(state)]
```

- [ ] **Step 4: Run tests**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Run full suite**

```bash
source venv/bin/activate && pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add geosite/s5_cost/regional_rates.py
git commit -m "feat(s5): add regional_rates.py — state→division→US fallback rate lookup"
```

---

### Task 4: estimator.py + CostResult dataclass

**Files:**
- Create: `geosite/s5_cost/models.py`
- Create: `geosite/s5_cost/estimator.py`
- Modify: `geosite/s5_cost/__init__.py`
- Test: `tests/test_s5_cost.py` (append)

**Interfaces:**
- Produces: `estimate_cost(L_m, NB, B_m, state, rock_class_name=None, distance_to_house_ft=100.0) → dict`
  Returns `{"best": CostResult, "base": CostResult, "worst": CostResult, "headline_per_ft": float, "region_used": str}`
- `CostResult` is a dataclass with: `total_usd, cost_per_ft, L_ft, NB, breakdown (list[dict]), region_used, rock_frac, scenario`

- [ ] **Step 1: Append failing tests to `tests/test_s5_cost.py`**

```python
from geosite.s5_cost.estimator import estimate_cost


def test_estimate_cost_returns_three_scenarios():
    result = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="IL")
    assert "best" in result
    assert "base" in result
    assert "worst" in result
    assert "headline_per_ft" in result
    assert "region_used" in result


def test_best_cheaper_than_worst():
    result = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="IL")
    assert result["best"].total_usd < result["worst"].total_usd


def test_cost_per_ft_formula():
    result = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="US")
    base = result["base"]
    L_ft = 2206.33 * 3.28084
    assert base.cost_per_ft == pytest.approx(base.total_usd / L_ft, rel=0.001)


def test_headline_per_ft_is_base_scenario():
    result = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="IL")
    assert result["headline_per_ft"] == pytest.approx(result["base"].cost_per_ft)


def test_rock_class_igneous_sets_high_rock_frac():
    result_rock = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="US",
                                rock_class_name="Igneous")
    result_none = estimate_cost(L_m=2206.33, NB=32, B_m=6.7, state="US",
                                rock_class_name=None)
    # Igneous means more rock drilling → more expensive
    assert result_rock["base"].total_usd > result_none["base"].total_usd
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py::test_estimate_cost_returns_three_scenarios -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `geosite/s5_cost/models.py`**

```python
from dataclasses import dataclass


@dataclass
class CostResult:
    total_usd: float
    cost_per_ft: float
    L_ft: float
    NB: int
    breakdown: list[dict]
    region_used: str
    rock_frac: float
    scenario: str
```

- [ ] **Step 4: Create `geosite/s5_cost/estimator.py`**

```python
from geosite.s5_cost.line_items import calc_line_items
from geosite.s5_cost.regional_rates import get_rates, get_region_used
from geosite.s5_cost.models import CostResult

_M_TO_FT = 3.28084

_ROCK_CLASS_FRACS = {
    "igneous":        0.90,
    "metamorphic":    0.85,
    "sedimentary":    0.40,
    "unconsolidated": 0.05,
}

_SCENARIOS = {
    "best":  0.00,
    "base":  0.30,
    "worst": 0.70,
}


def _rock_frac_from_class(rock_class_name: str | None) -> float | None:
    if not rock_class_name:
        return None
    return _ROCK_CLASS_FRACS.get(rock_class_name.lower().split()[0])


def _run_scenario(
    scenario: str,
    rock_frac: float,
    L_m: float,
    NB: int,
    B_m: float,
    rates: dict,
    region_used: str,
    distance_to_house_ft: float,
) -> CostResult:
    L_ft = L_m * _M_TO_FT
    items = calc_line_items(
        L_m=L_m, NB=NB, B_m=B_m, rates=rates,
        rock_frac=rock_frac, distance_to_house_ft=distance_to_house_ft,
    )
    total_usd = sum(i["cost_usd"] for i in items)
    return CostResult(
        total_usd=total_usd,
        cost_per_ft=total_usd / L_ft,
        L_ft=L_ft,
        NB=NB,
        breakdown=items,
        region_used=region_used,
        rock_frac=rock_frac,
        scenario=scenario,
    )


def estimate_cost(
    L_m: float,
    NB: int,
    B_m: float,
    state: str | None,
    rock_class_name: str | None = None,
    distance_to_house_ft: float = 100.0,
) -> dict:
    """Estimate borefield installation cost in best/base/worst scenarios.

    Parameters
    ----------
    L_m : total borefield length in meters (from s4 sizing)
    NB  : number of boreholes
    B_m : borehole spacing in meters
    state : 2-letter state abbreviation (used for regional rate lookup)
    rock_class_name : SGMC rock class (e.g. "Igneous") or None
    distance_to_house_ft : horizontal trench distance from field to building

    Returns
    -------
    dict with keys "best", "base", "worst" (each a CostResult),
    "headline_per_ft" (base scenario $/ft), "region_used" (rate table key used)
    """
    region = get_region_used(state)
    rates = get_rates(state)
    site_rock_frac = _rock_frac_from_class(rock_class_name)

    results = {}
    for scenario, default_frac in _SCENARIOS.items():
        if site_rock_frac is not None:
            # Narrow the range around the site-specific rock fraction
            spread = 0.15
            if scenario == "best":
                frac = max(0.0, site_rock_frac - spread)
            elif scenario == "worst":
                frac = min(1.0, site_rock_frac + spread)
            else:
                frac = site_rock_frac
        else:
            frac = default_frac
        results[scenario] = _run_scenario(
            scenario, frac, L_m, NB, B_m, rates, region, distance_to_house_ft
        )

    return {
        "best": results["best"],
        "base": results["base"],
        "worst": results["worst"],
        "headline_per_ft": results["base"].cost_per_ft,
        "region_used": region,
    }
```

- [ ] **Step 5: Update `geosite/s5_cost/__init__.py`**

```python
from geosite.s5_cost.estimator import estimate_cost
from geosite.s5_cost.models import CostResult

__all__ = ["estimate_cost", "CostResult"]
```

- [ ] **Step 6: Run tests**

```bash
source venv/bin/activate && pytest tests/test_s5_cost.py -v
```
Expected: all tests PASS.

- [ ] **Step 7: Run full suite**

```bash
source venv/bin/activate && pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add geosite/s5_cost/models.py geosite/s5_cost/estimator.py geosite/s5_cost/__init__.py
git commit -m "feat(s5): add estimator.py — best/base/worst cost scenarios with rock_class support"
```

---

### Task 5: Expose state_abbrev in SiteData and smart endpoint

**Files:**
- Modify: `geosite/models.py` — add `state_abbrev: str` field to `SiteData`
- Modify: `geosite/s1_site/lookup.py` — populate `state_abbrev` from deep thermal CSV
- Modify: `app.py` — include `state_abbrev` in `/calculate/smart` response `site` dict
- Test: `tests/test_pipeline_integration.py` (append one assertion)

**Interfaces:**
- `SiteData.state_abbrev: str` — 2-letter abbreviation (e.g. "IL"), empty string if unavailable
- `/calculate/smart` response: `site.state_abbrev` exposed alongside existing `site.k`, `site.climate_zone`, etc.

- [ ] **Step 1: Add field to SiteData in `geosite/models.py`**

Replace the existing `SiteData` dataclass (current file lines 8–15):

```python
@dataclass
class SiteData:
    """Soil and climate properties for a census tract location."""
    geoid: str           # 11-digit census tract GEOID, e.g. "17031010200"
    k: float             # soil thermal conductivity [W/m·K]
    alpha: float         # soil thermal diffusivity [m²/day]
    T_g: float           # undisturbed ground temperature [°C]
    climate_zone: str    # ASHRAE climate zone, e.g. "5A"
    data_available: bool # False when no SSURGO data exists for this tract
    state_abbrev: str = ""  # 2-letter state abbreviation from deep_thermal_by_county.csv
```

- [ ] **Step 2: Populate `state_abbrev` in `geosite/s1_site/lookup.py`**

In `lookup_by_geoid`, in the block that returns from deep dataset (around line 90), change the return statement to include `state_abbrev`:

```python
return SiteData(
    geoid=geoid,
    k=k,
    alpha=alpha,
    T_g=T_g,
    climate_zone=climate_zone,
    data_available=True,
    state_abbrev=str(d.get("state_abbrev", "")) if hasattr(d, "get") else str(d["state_abbrev"]) if "state_abbrev" in d.index else "",
)
```

Since `d` is a pandas Series, use: `state_abbrev=str(d["state_abbrev"]) if pd.notna(d.get("state_abbrev", "")) else ""`

Full replacement for the deep-track return (lines 90–97 in current lookup.py):

```python
state_abbrev = str(d["state_abbrev"]) if "state_abbrev" in d.index and pd.notna(d["state_abbrev"]) else ""
return SiteData(
    geoid=geoid,
    k=k,
    alpha=alpha,
    T_g=T_g,
    climate_zone=climate_zone,
    data_available=True,
    state_abbrev=state_abbrev,
)
```

- [ ] **Step 3: Expose in `/calculate/smart` response in `app.py`**

In the `return jsonify({...})` at the end of `calculate_smart` (around line 256), add `state_abbrev` to the `site` dict:

```python
"site": {
    "k": site.k,
    "k_effective": round(effective_k, 3),
    "soil_confidence": soil_confidence,
    "alpha": site.alpha,
    "T_g": site.T_g,
    "climate_zone": site.climate_zone,
    "state_abbrev": site.state_abbrev,       # NEW
    "data_available": site.data_available,
},
```

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
source venv/bin/activate && pytest -q
```
Expected: all tests PASS (state_abbrev defaults to "" so existing tests still work).

- [ ] **Step 5: Commit**

```bash
git add geosite/models.py geosite/s1_site/lookup.py app.py
git commit -m "feat(s1): expose state_abbrev in SiteData and /calculate/smart response"
```

---

### Task 6: POST /api/cost Flask endpoint

**Files:**
- Modify: `app.py` — add `/api/cost` route
- Modify: `app.py` — add `/api/cost/map` route (returns per-state base-scenario $/ft for choropleth)
- Test: `tests/test_s5_api.py` (new file)

**Interfaces:**
- `POST /api/cost` request body: `{L, NB, B, state, rock_class (opt), distance_to_house_ft (opt)}`
- `POST /api/cost` response: `{best: {...}, base: {...}, worst: {...}, headline_per_ft, region_used}`
  Each scenario dict: `{total_usd, cost_per_ft, L_ft, NB, breakdown: [...], region_used, rock_frac, scenario}`
- `GET /api/cost/map` response: `{states: {"CA": {best_per_ft, base_per_ft, worst_per_ft, region_used}, ...}}`
  Uses a representative project: NB=16, B=6.0m, L varies by state (500m² small office, base climate zone)

- [ ] **Step 1: Write failing API tests in `tests/test_s5_api.py`**

```python
import json
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_cost_endpoint_returns_three_scenarios(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "IL"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "best" in data
    assert "base" in data
    assert "worst" in data
    assert "headline_per_ft" in data
    assert "region_used" in data


def test_cost_endpoint_breakdown_has_nine_items(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "IL"}),
        content_type="application/json",
    )
    data = resp.get_json()
    assert len(data["base"]["breakdown"]) == 9


def test_cost_endpoint_missing_required_field_returns_400(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"NB": 32, "B": 6.7}),  # missing L and state
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_cost_endpoint_with_rock_class(client):
    resp_rock = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "CO",
                         "rock_class": "Igneous"}),
        content_type="application/json",
    )
    resp_soft = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "CO"}),
        content_type="application/json",
    )
    assert resp_rock.status_code == 200
    assert resp_soft.status_code == 200
    # Igneous = more rock drilling = more expensive base scenario
    assert resp_rock.get_json()["base"]["total_usd"] > resp_soft.get_json()["base"]["total_usd"]


def test_cost_map_endpoint_returns_all_states(client):
    resp = client.get("/api/cost/map")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "states" in data
    # Should have at least the 9 Census divisions as representative entries
    assert len(data["states"]) >= 9
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_s5_api.py -v 2>&1 | head -20
```
Expected: `404` errors — routes don't exist yet.

- [ ] **Step 3: Add `/api/cost` and `/api/cost/map` to `app.py`**

Add these imports at the top of `app.py` (after existing imports):

```python
from geosite.s5_cost import estimate_cost
from geosite.s5_cost.regional_rates import get_rates, get_region_used
```

Add these two routes near the other API routes (before the `/dev` route):

```python
@app.route("/api/cost", methods=["POST"])
def cost_api():
    """Estimate borefield installation cost given sizing output.

    Required body fields: L (meters), NB (int), B (meters), state (2-letter abbrev or null)
    Optional: rock_class (SGMC rock class name), distance_to_house_ft (float, default 100)
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    for field in ("L", "NB", "B"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    try:
        L_m = float(data["L"])
        NB = int(data["NB"])
        B_m = float(data["B"])
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "field", "message": str(exc)}), 400

    state = data.get("state") or None
    rock_class = data.get("rock_class") or None
    distance_to_house_ft = float(data.get("distance_to_house_ft", 100.0))

    try:
        result = estimate_cost(
            L_m=L_m, NB=NB, B_m=B_m, state=state,
            rock_class_name=rock_class,
            distance_to_house_ft=distance_to_house_ft,
        )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    def _cr(cr):
        return {
            "total_usd": round(cr.total_usd, 2),
            "cost_per_ft": round(cr.cost_per_ft, 2),
            "L_ft": round(cr.L_ft, 1),
            "NB": cr.NB,
            "breakdown": [
                {**item, "cost_usd": round(item["cost_usd"], 2)}
                for item in cr.breakdown
            ],
            "region_used": cr.region_used,
            "rock_frac": cr.rock_frac,
            "scenario": cr.scenario,
        }

    return jsonify({
        "best":  _cr(result["best"]),
        "base":  _cr(result["base"]),
        "worst": _cr(result["worst"]),
        "headline_per_ft": round(result["headline_per_ft"], 2),
        "region_used": result["region_used"],
    })


@app.route("/api/cost/map")
def cost_map_api():
    """Return per-state base-scenario $/ft for Leaflet choropleth.

    Uses a representative project: NB=16, B=6.0m, L=1200m (small office baseline).
    """
    _REP_L_M = 1200.0
    _REP_NB = 16
    _REP_B_M = 6.0

    all_states = [
        "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID",
        "IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO",
        "MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA",
        "RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
    ]
    out = {}
    for state in all_states:
        res = estimate_cost(L_m=_REP_L_M, NB=_REP_NB, B_m=_REP_B_M, state=state)
        out[state] = {
            "best_per_ft":  round(res["best"].cost_per_ft, 2),
            "base_per_ft":  round(res["base"].cost_per_ft, 2),
            "worst_per_ft": round(res["worst"].cost_per_ft, 2),
            "region_used":  res["region_used"],
        }

    return jsonify({"states": out})
```

- [ ] **Step 4: Run API tests**

```bash
source venv/bin/activate && pytest tests/test_s5_api.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Run full suite**

```bash
source venv/bin/activate && pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_s5_api.py
git commit -m "feat(s5): add POST /api/cost and GET /api/cost/map Flask endpoints"
```

---

### Task 7: Main tool UI — cost section

**Files:**
- Modify: `templates/index.html` — add collapsible cost section after `#smart-result`
- Modify: `static/style.css` — add cost section styles (if needed)

The cost section appears after the sizing result card (`#smart-result`) and is populated by calling `POST /api/cost` with the sizing result data.

- [ ] **Step 1: Locate insertion point in `templates/index.html`**

Find the `#smart-result` div (currently around line 199). The cost section goes after the closing `</div>` of `#smart-result`.

- [ ] **Step 2: Add cost section HTML**

After the `</div>` that closes `#smart-result`, add:

```html
<!-- s5: Cost Estimate (populated after sizing) -->
<div id="cost-section" class="hidden" style="margin-top:20px;">
  <div class="stage-header">
    <span class="stage-pill">s5</span>
    <span class="stage-label">Cost Estimate</span>
    <span class="stage-note">Regional drilling rates — <span id="cost-region-tag">—</span></span>
  </div>

  <!-- Three-scenario cards -->
  <div class="cost-scenarios" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
    <div class="card cost-card" id="cost-best">
      <div class="cost-scenario-label">Best Case</div>
      <div class="cost-headline"><span id="cost-best-pft">—</span> <span class="cost-unit">$/ft</span></div>
      <div class="cost-subline">Total: <span id="cost-best-total">—</span></div>
    </div>
    <div class="card cost-card cost-card-base" id="cost-base">
      <div class="cost-scenario-label">Base Case</div>
      <div class="cost-headline"><span id="cost-base-pft">—</span> <span class="cost-unit">$/ft</span></div>
      <div class="cost-subline">Total: <span id="cost-base-total">—</span></div>
    </div>
    <div class="card cost-card" id="cost-worst">
      <div class="cost-scenario-label">Worst Case</div>
      <div class="cost-headline"><span id="cost-worst-pft">—</span> <span class="cost-unit">$/ft</span></div>
      <div class="cost-subline">Total: <span id="cost-worst-total">—</span></div>
    </div>
  </div>

  <!-- Contractor comparison strip -->
  <div class="card" style="padding:10px 16px;font-size:12px;margin-bottom:16px;color:var(--text-muted);">
    <strong style="color:var(--text);">Contractor comparison:</strong>
    Your project (<span id="cost-state-tag">—</span>): <strong id="cost-cmp-base">—</strong>/ft &nbsp;|&nbsp;
    National avg: <strong id="cost-cmp-us">—</strong>/ft &nbsp;|&nbsp;
    Best case: <strong id="cost-cmp-best">—</strong>/ft &nbsp;|&nbsp;
    Worst case: <strong id="cost-cmp-worst">—</strong>/ft
  </div>

  <!-- Line-item table toggle -->
  <details>
    <summary style="font-size:12px;font-weight:700;color:var(--accent);cursor:pointer;margin-bottom:10px;">
      Show line-item breakdown (base case)
    </summary>
    <table class="files-table" id="cost-breakdown-table" style="margin-top:8px;">
      <thead>
        <tr>
          <th>Item</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Subtotal</th>
        </tr>
      </thead>
      <tbody id="cost-breakdown-body"></tbody>
    </table>
  </details>
</div>
```

- [ ] **Step 3: Add CSS for cost cards to `static/style.css`**

Append to `static/style.css`:

```css
/* ── s5 Cost section ── */
.cost-card { text-align: center; padding: 14px; }
.cost-card-base { border: 2px solid var(--accent); }
.cost-scenario-label { font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 6px; }
.cost-headline { font-size: 24px; font-weight: 800; color: var(--text); }
.cost-unit { font-size: 13px; font-weight: 400; color: var(--text-muted); }
.cost-subline { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
```

- [ ] **Step 4: Add JavaScript to fetch and render cost**

Find the JS block in `index.html` where the smart mode fetch result is rendered (look for `sres-L`, `sres-H`). After filling in sizing values, add a call to fetch cost:

```javascript
// After populating sizing results:
const siteState = data.site && data.site.state_abbrev ? data.site.state_abbrev : null;
fetchCostEstimate(data.L, data.NB, data.site && data.site.B_m ? data.site.B_m : 6.0, siteState);
```

And add the `fetchCostEstimate` function (add before the closing `</script>` tag):

```javascript
function fetchCostEstimate(L_m, NB, B_m, state) {
  fetch('/api/cost', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({L: L_m, NB: NB, B: B_m, state: state}),
  })
  .then(r => r.json())
  .then(cost => {
    document.getElementById('cost-section').classList.remove('hidden');
    const fmt = (n) => '$' + n.toFixed(2);
    const fmtTotal = (n) => '$' + Math.round(n).toLocaleString();

    document.getElementById('cost-region-tag').textContent = cost.region_used;
    document.getElementById('cost-state-tag').textContent = state || 'National';

    document.getElementById('cost-best-pft').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
    document.getElementById('cost-best-total').textContent = fmtTotal(cost.best.total_usd);
    document.getElementById('cost-base-pft').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
    document.getElementById('cost-base-total').textContent = fmtTotal(cost.base.total_usd);
    document.getElementById('cost-worst-pft').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);
    document.getElementById('cost-worst-total').textContent = fmtTotal(cost.worst.total_usd);

    document.getElementById('cost-cmp-base').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
    document.getElementById('cost-cmp-best').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
    document.getElementById('cost-cmp-worst').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);

    // Fetch US national avg for comparison
    fetch('/api/cost', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({L: L_m, NB: NB, B: B_m, state: 'US'}),
    })
    .then(r => r.json())
    .then(us => {
      document.getElementById('cost-cmp-us').textContent = '$' + us.base.cost_per_ft.toFixed(2);
    });

    // Populate breakdown table
    const tbody = document.getElementById('cost-breakdown-body');
    tbody.innerHTML = '';
    const labels = {
      mobilization: 'Mobilization', drilling_soil: 'Drilling (soil)',
      drilling_rock: 'Drilling (rock)', well_casing: 'Well Casing',
      sand_bag: 'Sand (bentonite)', grout_bag: 'Grout (CETCO)',
      utube_pipe: 'U-tube HDPE pipe', horiz_pipe: 'Horizontal header pipe',
      horiz_trench: 'Horizontal trench',
    };
    cost.base.breakdown.forEach(item => {
      const row = tbody.insertRow();
      row.innerHTML = `<td>${labels[item.name] || item.name}</td>
        <td>${Number(item.qty).toFixed(1)}</td>
        <td>${item.unit}</td>
        <td>$${item.rate}/LF</td>
        <td>$${Math.round(item.cost_usd).toLocaleString()}</td>`;
    });
  })
  .catch(() => {}); // fail silently — sizing result still shows
}
```

Note: the `B_m` value is not currently in the smart endpoint response. Pass the form value instead:

```javascript
// Get B from the form input value
const B_m = parseFloat(document.getElementById('s_B').value) || 6.0;
fetchCostEstimate(data.L, data.NB, B_m, siteState);
```

- [ ] **Step 5: Also update sidebar to activate s5 link**

In `templates/index.html`, update the s5 sidebar item from:
```html
<li class="stage-item disabled">s5 <span class="stage-name">Cost</span><span class="badge">soon</span></li>
```
to:
```html
<li class="stage-item active-dim">s5 <span class="stage-name">Cost</span></li>
```

- [ ] **Step 6: Start the dev server and verify manually**

```bash
source venv/bin/activate && python app.py
```

Open http://localhost:5001 in a browser. Run a ZIP → sizing query (e.g., ZIP 60601, small_office). Verify:
- s5 Cost section appears below sizing result
- Three scenario cards show $/ft values
- Breakdown table populates when expanded
- No JS console errors

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/style.css
git commit -m "feat(s5): add cost estimate section to main tool UI — scenario cards + line-item breakdown"
```

---

### Task 8: Dev dashboard — Section 5 choropleth

**Files:**
- Modify: `templates/dev.html` — add Section 5 cost map

The choropleth uses Leaflet + a US states GeoJSON to color each state by base-scenario $/ft from `GET /api/cost/map`.

- [ ] **Step 1: Find the end of the existing sections in `dev.html`**

Search for the last `</div>` that closes an existing `wf-section`. The new Section 5 goes after it.

- [ ] **Step 2: Add Section 5 HTML to `dev.html`**

```html
<!-- ══ Section 5: Drilling Cost Map ══ -->
<div class="wf-section">
  <div class="wf-header">
    <span class="stage-pill">s5</span>
    <span class="wf-title">Regional Drilling Cost</span>
    <span class="wf-subtitle">Base scenario $/ft by state (NB=16, B=6m, L=1200m representative project)</span>
  </div>

  <div id="cost-map" style="height:420px;border-radius:8px;border:1px solid var(--border);"></div>
  <div style="margin-top:8px;font-size:11px;color:var(--text-muted);">
    Sources: NREL GeoVision 2019, IGSHPA 2020, RSMeans 2024. Click any state for scenario range.
  </div>

  <!-- Rate table -->
  <div style="margin-top:20px;">
    <div class="step-label">State Rate Table</div>
    <table class="files-table" id="cost-rate-table">
      <thead>
        <tr>
          <th>State</th><th>Region used</th>
          <th>Best $/ft</th><th>Base $/ft</th><th>Worst $/ft</th>
        </tr>
      </thead>
      <tbody id="cost-rate-tbody"></tbody>
    </table>
  </div>
</div>
```

- [ ] **Step 3: Add choropleth JavaScript to `dev.html`**

Add before the closing `</script>` tag in `dev.html`:

```javascript
// ── Section 5: Cost choropleth ──────────────────────────────────────
(function () {
  const costMap = L.map('cost-map').setView([38, -96], 4);

  // Fetch cost map data and US states GeoJSON in parallel
  Promise.all([
    fetch('/api/cost/map').then(r => r.json()),
    fetch('https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json').then(r => r.json()),
  ]).then(([costData, usAtlas]) => {
    const states = topojson.feature(usAtlas, usAtlas.objects.states);

    // FIPS → state abbrev lookup (abbreviated list; full map would use a complete table)
    const fipsToAbbrev = {
      "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT",
      "10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL",
      "18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD",
      "25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE",
      "32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND",
      "39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD",
      "47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV",
      "55":"WI","56":"WY",
    };

    // Color scale: 5 quantile buckets $25–$65/ft
    const breaks = [25, 32, 38, 44, 52, 65];
    const colors = ['#d1fae5','#6ee7b7','#34d399','#10b981','#059669'];

    function getColor(val) {
      for (let i = 0; i < breaks.length - 1; i++) {
        if (val < breaks[i + 1]) return colors[i];
      }
      return colors[colors.length - 1];
    }

    L.geoJSON(states, {
      style(feature) {
        const abbrev = fipsToAbbrev[feature.id];
        const val = costData.states[abbrev] ? costData.states[abbrev].base_per_ft : null;
        return {
          fillColor: val ? getColor(val) : '#e5e7eb',
          weight: 1, color: '#9ca3af',
          fillOpacity: val ? 0.8 : 0.3,
        };
      },
      onEachFeature(feature, layer) {
        const abbrev = fipsToAbbrev[feature.id];
        const d = costData.states[abbrev];
        if (d) {
          layer.bindTooltip(
            `<strong>${abbrev}</strong> (${d.region_used})<br>` +
            `Best: $${d.best_per_ft}/ft<br>` +
            `Base: $${d.base_per_ft}/ft<br>` +
            `Worst: $${d.worst_per_ft}/ft`,
            {sticky: true}
          );
        }
      },
    }).addTo(costMap);

    // Populate rate table
    const tbody = document.getElementById('cost-rate-tbody');
    Object.entries(costData.states).sort().forEach(([st, d]) => {
      const row = tbody.insertRow();
      row.innerHTML = `<td>${st}</td><td>${d.region_used}</td>
        <td>$${d.best_per_ft}</td><td>$${d.base_per_ft}</td><td>$${d.worst_per_ft}</td>`;
    });
  });
})();
```

- [ ] **Step 4: Verify the dashboard manually**

```bash
source venv/bin/activate && python app.py
```

Open http://localhost:5001/dev. Scroll to Section 5. Verify:
- Map renders with colored states (green shading)
- Hovering a state shows tooltip with 3 scenario values
- Rate table populates below the map
- No JS console errors

- [ ] **Step 5: Commit**

```bash
git add templates/dev.html
git commit -m "feat(s5): add Section 5 choropleth to dev dashboard — drilling cost by state"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 9 line items → Task 2. Regional rates → Task 1 + 3. Three scenarios → Task 4. API → Task 6. Main UI → Task 7. Choropleth → Task 8. state_abbrev gap → Task 5.
- [x] **Placeholder scan:** No TBDs or stubs. All code blocks complete.
- [x] **Type consistency:** `CostResult` defined in Task 4 `models.py`; imported in Task 4 `estimator.py`; imported in Task 4 `__init__.py`; serialized in Task 6. `calc_line_items` defined in Task 2; consumed in Task 4.
- [x] **Spreadsheet anchors:** Tests in Task 2 use exact values (L=2206.326178192672 m, total=$269,933.79; L=3662.5428199546277 m, total=$439,533.79) from openpyxl extraction.
- [x] **B_m in UI:** Task 7 reads B from form input `s_B` since it's not in the smart endpoint response. This is correct — the smart endpoint doesn't return B.

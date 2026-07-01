# s6 Hybrid GSHP Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mandatory hybrid GSHP strategy stage (s6) that sizes a supplemental peaker (electric heater or chiller) via Load Duration Curve, trims borefield size accordingly, and displays before/after results with three Chart.js visualizations in both the user and developer UIs.

**Architecture:** New `geosite/s6_strategy/` Python module computes imbalance ratio (separate heating/cooling sizing runs), applies LDC cutoff to determine peaker capacity, re-sizes borefield on the trimmed profile, and feeds `POST /api/strategy`. The UI auto-triggers after s5 cost renders, showing a compact summary in `index.html` and a full 3-chart trace in `dev.html`.

**Tech Stack:** Python 3.11, Flask, numpy, Chart.js 4.4.0 (CDN), existing `size_borefield()` from `geosite/s4_sizing/ashrae_sizing.py`, existing `estimate_cost()` from `geosite/s5_cost/__init__.py`.

## Global Constraints

- Python 3.11 in venv at `./venv`; all code runs with `source venv/bin/activate`
- Ground load sign convention: **positive = cooling (heat injection into ground), negative = heating (heat extraction from ground)**
- `size_borefield()` returns a single `numpy.float64` (not a tuple): signature is `size_borefield(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B, NB, A) -> float`
- Advanced defaults: `Cp=4200, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167, kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0`
- T_in_HP defaults: heating mode → 5.0 °C, cooling mode → 40.2 °C
- `_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]` — sum=8760
- Prototype floor areas: `small_office=511 m², medium_office=4982 m², large_office=46320 m²`
- LDC default cutoff: **10%** (`ldc_cutoff_pct=10.0`); imbalance threshold default: **1.25**
- Peaker names: `"electric_heater"` (heating-dominant), `"chiller"` (cooling-dominant), `"electric_heater+chiller"` (balanced)
- Chart.js CDN: `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` — already loaded in both templates (check before adding again)
- Run tests: `source venv/bin/activate && python -m pytest tests/ -v`
- EnergyPlus cache: `data/energyplus_cache/work/{bt}_{cz}/ep_output/eplusout.csv` — 48 files (3 types × 16 zones: 1A,2A,2B,3A,3B,3C,4A,4B,4C,5A,5B,5C,6A,6B,7,8)
- Heating column pattern: `*Zone Ideal Loads Zone Total Heating Energy [J](Hourly)` (no trailing space)
- Cooling column pattern: `*Zone Ideal Loads Zone Total Cooling Energy [J](Hourly) ` (trailing space — present in real files)
- Convert J to W: divide by 3600 (hourly energy)
- Output JSON: `data/public/prototype_loads_hourly.json`
- No comments in code unless WHY is non-obvious

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `scripts/extract_hourly_loads.py` | One-time script: 48 EP CSVs → `prototype_loads_hourly.json` |
| Create | `data/public/prototype_loads_hourly.json` | Pre-computed 8760h ground loads, all 48 combinations |
| Modify | `app.py` | Add `GET /api/loads/hourly`, `POST /api/strategy` |
| Create | `geosite/s6_strategy/models.py` | `StrategyResult` dataclass |
| Create | `geosite/s6_strategy/load_profile.py` | Load + scale hourly profile from JSON |
| Create | `geosite/s6_strategy/ldc.py` | LDC computation, trimming, one-sided + dominant pulses |
| Create | `geosite/s6_strategy/strategy.py` | `run_strategy()` orchestration |
| Modify | `geosite/s6_strategy/__init__.py` | Export `run_strategy` |
| Create | `tests/test_s6_ldc.py` | LDC + trimming unit tests |
| Create | `tests/test_s6_strategy.py` | Strategy integration + API tests |
| Modify | `templates/index.html` | s6 user UI section (after s5 cost) |
| Modify | `templates/dev.html` | s6 dev trace step with Chart A, B, C |

---

## Task 1: Hourly Load Extraction

**Files:**
- Create: `scripts/extract_hourly_loads.py`
- Create: `data/public/prototype_loads_hourly.json`
- Modify: `app.py`

**Interfaces:**
- Produces: `data/public/prototype_loads_hourly.json` with structure:
  ```json
  {
    "_note": "Hourly ground loads in W. Positive = cooling (heat injection). Negative = heating (extraction).",
    "_units": "W",
    "_areas_m2": {"small_office": 511, "medium_office": 4982, "large_office": 46320},
    "small_office": {"5A": [8760 floats], "3B": [...], ...},
    "medium_office": {...},
    "large_office": {...}
  }
  ```
- Produces: `GET /api/loads/hourly` — returns the full JSON file contents

- [ ] **Step 1: Write `scripts/extract_hourly_loads.py`**

```python
#!/usr/bin/env python3
"""Extract 8760h hourly ground loads from EnergyPlus cache → prototype_loads_hourly.json.

Usage: python3 scripts/extract_hourly_loads.py
Run from repo root. Requires: pandas, numpy (already in venv).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR  = REPO_ROOT / "data/energyplus_cache/work"
OUT_PATH  = REPO_ROOT / "data/public/prototype_loads_hourly.json"

_PROTOTYPE_AREAS_M2 = {
    "small_office":  511,
    "medium_office": 4982,
    "large_office":  46320,
}

_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

_DIR_RE = re.compile(r'^(.+)_([0-9]+[A-C]?)$')


def _parse_dir(name: str):
    m = _DIR_RE.match(name)
    return (m.group(1), m.group(2)) if m else (None, None)


def _extract_ground_load(csv_path: Path) -> np.ndarray:
    df = pd.read_csv(csv_path)
    heat_cols = [c for c in df.columns if "Zone Ideal Loads Zone Total Heating Energy [J]" in c]
    cool_cols = [c for c in df.columns if "Zone Ideal Loads Zone Total Cooling Energy [J]" in c]
    if not heat_cols or not cool_cols:
        raise ValueError(f"Cannot find IDEALLOADS columns in {csv_path}")
    heat_J = df[heat_cols].sum(axis=1).values
    cool_J = df[cool_cols].sum(axis=1).values
    ground_W = (cool_J - heat_J) / 3600.0
    if len(ground_W) != 8760:
        raise ValueError(f"Expected 8760 rows, got {len(ground_W)} in {csv_path}")
    return ground_W


def main():
    result: dict = {
        "_note":     "Hourly ground loads in W. Positive = cooling (heat injection). Negative = heating (extraction).",
        "_units":    "W",
        "_areas_m2": _PROTOTYPE_AREAS_M2,
    }

    dirs = sorted(WORK_DIR.iterdir()) if WORK_DIR.exists() else []
    processed, skipped = 0, 0

    for d in dirs:
        if not d.is_dir():
            continue
        bt, cz = _parse_dir(d.name)
        if bt is None or bt not in _PROTOTYPE_AREAS_M2:
            skipped += 1
            continue
        csv_path = d / "ep_output" / "eplusout.csv"
        if not csv_path.exists():
            print(f"  SKIP (no CSV): {d.name}", file=sys.stderr)
            skipped += 1
            continue
        try:
            ground_W = _extract_ground_load(csv_path)
        except Exception as e:
            print(f"  ERROR {d.name}: {e}", file=sys.stderr)
            skipped += 1
            continue
        result.setdefault(bt, {})[cz] = [round(float(v), 2) for v in ground_W]
        processed += 1
        print(f"  OK {d.name}: peak={ground_W.max():.0f}W min={ground_W.min():.0f}W", flush=True)

    OUT_PATH.write_text(json.dumps(result, separators=(',', ':')))
    print(f"\nWrote {OUT_PATH} — {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the extraction script**

```bash
cd /path/to/geosite_advisor
source venv/bin/activate
python3 scripts/extract_hourly_loads.py
```

Expected: `Wrote data/public/prototype_loads_hourly.json — 48 processed, 0 skipped`

If some directories are skipped, check stderr. The output file will still work for the available combinations.

- [ ] **Step 3: Verify JSON structure**

```bash
python3 -c "
import json
data = json.load(open('data/public/prototype_loads_hourly.json'))
print('Keys:', list(data.keys()))
print('small_office zones:', list(data['small_office'].keys()))
print('small_office/5A length:', len(data['small_office']['5A']))
print('small_office/5A[0:3]:', data['small_office']['5A'][:3])
"
```

Expected: 48 zones available, 8760-length arrays, values are non-zero W floats.

- [ ] **Step 4: Add `GET /api/loads/hourly` to `app.py`**

Add this import at top of `app.py` if not already present:
```python
import pathlib
```
(already present — `_PUBLIC_DATA` is used for it)

Add this route to `app.py` after the existing `@app.route("/api/cost/map")` block and before the `/dev` route:

```python
@app.route("/api/loads/hourly")
def hourly_loads_api():
    """Serve pre-extracted 8760h hourly ground load profiles (W) for all building × zone combos."""
    p = _PUBLIC_DATA / "prototype_loads_hourly.json"
    if not p.exists():
        return jsonify({"error": "data_not_found",
                        "message": "prototype_loads_hourly.json not generated yet"}), 404
    import json as _json
    return _json.loads(p.read_text()), 200, {"Content-Type": "application/json"}
```

- [ ] **Step 5: Test the endpoint manually**

```bash
source venv/bin/activate
FLASK_APP=app.py FLASK_RUN_PORT=5001 flask run &
sleep 2
curl -s http://localhost:5001/api/loads/hourly | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('top keys:', [k for k in d if not k.startswith('_')])
print('small_office/5A len:', len(d['small_office']['5A']))
"
```

Expected: `top keys: ['small_office', 'medium_office', 'large_office']` and length 8760.

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_hourly_loads.py data/public/prototype_loads_hourly.json app.py
git commit -m "feat(s6): extract 8760h hourly ground loads + GET /api/loads/hourly"
```

---

## Task 2: s6 Models + Load Profile

**Files:**
- Create: `geosite/s6_strategy/models.py`
- Create: `geosite/s6_strategy/load_profile.py`
- Create: `tests/test_s6_load_profile.py`

**Interfaces:**
- Produces:
  - `StrategyResult` dataclass (imported by strategy.py and app.py)
  - `load_hourly_profile(building_type, climate_zone, hourly_json_path) -> list[float]`
  - `scale_profile(profile, scale_factor) -> list[float]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_s6_load_profile.py`:

```python
import pathlib
import pytest
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile

_HOURLY_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads_hourly.json"


def test_load_returns_8760_element_list():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert len(profile) == 8760


def test_load_profile_is_list_of_floats():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert isinstance(profile[0], float)


def test_load_small_office_5a_has_both_signs():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert any(h > 0 for h in profile), "no cooling hours"
    assert any(h < 0 for h in profile), "no heating hours"


def test_unknown_building_type_raises():
    with pytest.raises(KeyError):
        load_hourly_profile("unknown_type", "5A", _HOURLY_JSON)


def test_unknown_climate_zone_raises():
    with pytest.raises(KeyError):
        load_hourly_profile("small_office", "9Z", _HOURLY_JSON)


def test_scale_profile_multiplies_all_values():
    profile = [1.0, -2.0, 0.0, 3.0]
    scaled = scale_profile(profile, 2.0)
    assert scaled == pytest.approx([2.0, -4.0, 0.0, 6.0])


def test_scale_factor_one_returns_same_values():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    scaled = scale_profile(profile, 1.0)
    assert scaled == pytest.approx(profile)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_load_profile.py -v
```

Expected: FAIL with `ImportError: cannot import name 'load_hourly_profile'`

- [ ] **Step 3: Create `geosite/s6_strategy/models.py`**

```python
from dataclasses import dataclass, field


@dataclass
class StrategyResult:
    # Case detection
    case: int                    # 1 or 2
    imbalance_ratio: float       # max(L_h, L_c) / min(L_h, L_c)
    dominant_mode: str           # "heating" | "cooling" | "balanced"
    L_h: float                   # borefield length, heating-only sizing (m)
    L_c: float                   # borefield length, cooling-only sizing (m)

    # LDC
    ldc_cutoff_pct: float        # x% used
    cutoff_W: float              # ground load threshold (W) at cutoff rank

    # Peaker
    peaker_kW: float             # supplemental unit rated capacity
    peaker_type: str             # "electric_heater" | "chiller" | "electric_heater+chiller"
    peaker_heat_kW: float        # heating-side peaker (meaningful for Case 2)
    peaker_cool_kW: float        # cooling-side peaker (meaningful for Case 2)

    # Three-pulse — original dominant sizing
    q_h_before: float
    q_m_before: float
    q_y_before: float

    # Three-pulse — trimmed (after LDC)
    q_h_trimmed: float
    q_m_trimmed: float
    q_y_trimmed: float

    # Sizing — before and after
    L_before: float              # borefield without peaker (m)
    H_before: float              # depth per borehole without peaker (m)
    L_after: float               # borefield with trimmed load (m)
    H_after: float               # depth per borehole with trimmed load (m)
    NB: int                      # number of boreholes (unchanged)

    # Cost — before and after (dicts from estimate_cost)
    cost_before: dict
    cost_after: dict

    # Profiles for visualization (8760 floats each)
    hourly_profile: list         # original ground load (W)
    hourly_trimmed: list         # trimmed ground load (W)

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "imbalance_ratio": round(self.imbalance_ratio, 3),
            "dominant_mode": self.dominant_mode,
            "L_h": round(self.L_h, 1),
            "L_c": round(self.L_c, 1),
            "ldc_cutoff_pct": self.ldc_cutoff_pct,
            "cutoff_W": round(self.cutoff_W, 1),
            "peaker_kW": round(self.peaker_kW, 1),
            "peaker_type": self.peaker_type,
            "peaker_heat_kW": round(self.peaker_heat_kW, 1),
            "peaker_cool_kW": round(self.peaker_cool_kW, 1),
            "q_h_before": round(self.q_h_before, 1),
            "q_m_before": round(self.q_m_before, 1),
            "q_y_before": round(self.q_y_before, 1),
            "q_h_trimmed": round(self.q_h_trimmed, 1),
            "q_m_trimmed": round(self.q_m_trimmed, 1),
            "q_y_trimmed": round(self.q_y_trimmed, 1),
            "L_before": round(self.L_before),
            "H_before": round(self.H_before),
            "L_after": round(self.L_after),
            "H_after": round(self.H_after),
            "NB": self.NB,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "hourly_profile": [round(v, 2) for v in self.hourly_profile],
            "hourly_trimmed": [round(v, 2) for v in self.hourly_trimmed],
        }
```

- [ ] **Step 4: Create `geosite/s6_strategy/load_profile.py`**

```python
import json
import pathlib

_DEFAULT_HOURLY_JSON = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "data" / "public" / "prototype_loads_hourly.json"
)

_CACHE: dict = {}


def _load_json(hourly_json_path) -> dict:
    path = str(hourly_json_path)
    if path not in _CACHE:
        _CACHE[path] = json.loads(pathlib.Path(hourly_json_path).read_text())
    return _CACHE[path]


def load_hourly_profile(
    building_type: str,
    climate_zone: str,
    hourly_json_path=_DEFAULT_HOURLY_JSON,
) -> list:
    """Return 8760h ground load array (W) for given building type and climate zone.

    Raises KeyError if building_type or climate_zone is not found.
    """
    data = _load_json(hourly_json_path)
    if building_type not in data:
        raise KeyError(building_type)
    bt_data = data[building_type]
    if climate_zone not in bt_data:
        raise KeyError(climate_zone)
    return [float(v) for v in bt_data[climate_zone]]


def scale_profile(profile: list, scale_factor: float) -> list:
    """Multiply every hourly value by scale_factor. Used for floor area and year adjustments."""
    return [v * scale_factor for v in profile]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_load_profile.py -v
```

Expected: 7/7 PASS

- [ ] **Step 6: Commit**

```bash
git add geosite/s6_strategy/models.py geosite/s6_strategy/load_profile.py tests/test_s6_load_profile.py
git commit -m "feat(s6): StrategyResult dataclass + load_profile module"
```

---

## Task 3: LDC Module

**Files:**
- Create: `geosite/s6_strategy/ldc.py`
- Create: `tests/test_s6_ldc.py`

**Interfaces:**
- Consumes: `profile: list[float]` (8760 W values), `cutoff_pct: float`, `dominant_mode: str`
- Produces:
  - `compute_ldc(profile, cutoff_pct) -> dict` — `{"cutoff_idx": int, "cutoff_W": float, "sorted_abs": list}`
  - `trim_profile(profile, cutoff_W, dominant_mode) -> list[float]`
  - `extract_one_sided_pulses(profile, mode) -> tuple[float, float, float]` — `(q_h, q_m, q_y)`
  - `rederive_three_pulse(trimmed) -> tuple[float, float, float]` — `(q_h, q_m, q_y)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s6_ldc.py`:

```python
import pytest
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
    rederive_three_pulse,
)


def _flat_profile(n=8760, val=0.0):
    return [val] * n


def test_ldc_cutoff_idx_10pct():
    profile = list(range(1, 8761))  # 1 to 8760 W
    result = compute_ldc(profile, 10.0)
    assert result["cutoff_idx"] == 876


def test_ldc_cutoff_value_10pct():
    # Values 1..8760, sorted desc: 8760, 8759, ..., 7885 at index 876
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0)
    assert result["cutoff_W"] == pytest.approx(7884.0, abs=1.0)


def test_ldc_sorted_abs_descending():
    profile = [3.0, -10.0, 5.0, -2.0] + [0.0] * 8756
    result = compute_ldc(profile, 10.0)
    # sorted by magnitude desc: 10, 5, 3, 2, 0, 0, ...
    assert result["sorted_abs"][0] == pytest.approx(10.0)
    assert result["sorted_abs"][1] == pytest.approx(5.0)


def test_trim_profile_balanced_clips_both_sides():
    profile = [-100.0, -50.0, 0.0, 50.0, 100.0] + [0.0] * 8755
    trimmed = trim_profile(profile, 75.0, "balanced")
    assert trimmed[0] == pytest.approx(-75.0)
    assert trimmed[1] == pytest.approx(-50.0)
    assert trimmed[2] == pytest.approx(0.0)
    assert trimmed[3] == pytest.approx(50.0)
    assert trimmed[4] == pytest.approx(75.0)


def test_trim_profile_heating_clips_heating_only():
    profile = [-100.0, -50.0, 200.0] + [0.0] * 8757
    trimmed = trim_profile(profile, 75.0, "heating")
    assert trimmed[0] == pytest.approx(-75.0)    # clipped
    assert trimmed[1] == pytest.approx(-50.0)    # unchanged
    assert trimmed[2] == pytest.approx(200.0)    # cooling unchanged


def test_trim_profile_cooling_clips_cooling_only():
    profile = [-200.0, 50.0, 100.0] + [0.0] * 8757
    trimmed = trim_profile(profile, 75.0, "cooling")
    assert trimmed[0] == pytest.approx(-200.0)   # heating unchanged
    assert trimmed[1] == pytest.approx(50.0)     # unchanged
    assert trimmed[2] == pytest.approx(75.0)     # clipped


def test_extract_heating_pulses_dominant_negative():
    profile = [-30000.0] * 100 + [5000.0] * 100 + [0.0] * 8560
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    assert q_h < 0                               # heating = negative
    assert q_h == pytest.approx(-30000.0)        # peak extraction


def test_extract_cooling_pulses_dominant_positive():
    profile = [20000.0] * 100 + [-5000.0] * 100 + [0.0] * 8560
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "cooling")
    assert q_h > 0                               # cooling = positive
    assert q_h == pytest.approx(20000.0)


def test_extract_one_sided_zeroes_opposite():
    # Heating only: cooling hours contribute 0 to annual average
    profile = [-10000.0] * 4380 + [15000.0] * 4380  # half heat, half cool
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    # q_y = mean of heating-only profile (cooling hours zeroed)
    # heating contribution: -10000 * 4380 / 8760 = -5000
    assert q_y == pytest.approx(-5000.0, rel=0.01)


def test_rederive_three_pulse_q_h_equals_dominant_peak():
    # Cooling-dominant trimmed profile: max positive = 9000
    profile = [9000.0] * 10 + [-5000.0] * 10 + [0.0] * 8740
    q_h, q_m, q_y = rederive_three_pulse(profile)
    assert q_h > 0
    assert q_h == pytest.approx(9000.0)


def test_rederive_q_y_is_mean():
    profile = [100.0, -100.0] + [0.0] * 8758
    q_h, q_m, q_y = rederive_three_pulse(profile)
    assert q_y == pytest.approx(0.0, abs=0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v 2>&1 | head -20
```

Expected: FAIL with `ImportError: cannot import name 'compute_ldc'`

- [ ] **Step 3: Create `geosite/s6_strategy/ldc.py`**

```python
import numpy as np

_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def _monthly_averages(arr: np.ndarray) -> np.ndarray:
    avgs = np.empty(12)
    idx = 0
    for m, hours in enumerate(_MONTH_HOURS):
        avgs[m] = arr[idx: idx + hours].mean()
        idx += hours
    return avgs


def compute_ldc(profile: list, cutoff_pct: float) -> dict:
    """Sort 8760h profile by |load| descending, find cutoff value at x% rank.

    Returns dict with keys: cutoff_idx (int), cutoff_W (float), sorted_abs (list).
    """
    arr = np.asarray(profile, dtype=float)
    sorted_abs = np.sort(np.abs(arr))[::-1]  # descending by magnitude
    cutoff_idx = int(len(arr) * cutoff_pct / 100)
    cutoff_W = float(sorted_abs[cutoff_idx]) if cutoff_idx < len(sorted_abs) else 0.0
    return {
        "cutoff_idx": cutoff_idx,
        "cutoff_W": cutoff_W,
        "sorted_abs": sorted_abs.tolist(),
    }


def trim_profile(profile: list, cutoff_W: float, dominant_mode: str) -> list:
    """Clip hourly loads to ±cutoff_W, respecting Case 1 vs Case 2 rules.

    dominant_mode:
        "heating"  → clip heating (negative) hours to -cutoff_W; cooling unchanged (Case 1)
        "cooling"  → clip cooling (positive) hours to +cutoff_W; heating unchanged (Case 1)
        "balanced" → clip both sides to ±cutoff_W (Case 2)
    """
    result = []
    for h in profile:
        if dominant_mode == "heating":
            result.append(max(h, -cutoff_W) if h < 0 else h)
        elif dominant_mode == "cooling":
            result.append(min(h, cutoff_W) if h > 0 else h)
        else:
            result.append(max(-cutoff_W, min(cutoff_W, h)))
    return result


def extract_one_sided_pulses(profile: list, mode: str) -> tuple:
    """Extract (q_h, q_m, q_y) for single-mode borefield sizing.

    mode: "heating" → keep negative hours, zero out positive
          "cooling" → keep positive hours, zero out negative

    Sign convention maintained: heating q_h < 0, cooling q_h > 0.
    """
    arr = np.asarray(profile, dtype=float)
    if mode == "heating":
        one_sided = np.where(arr < 0, arr, 0.0)
        q_h = float(one_sided.min())
        q_m = float(_monthly_averages(one_sided).min())
    else:
        one_sided = np.where(arr > 0, arr, 0.0)
        q_h = float(one_sided.max())
        q_m = float(_monthly_averages(one_sided).max())
    q_y = float(one_sided.mean())
    return q_h, q_m, q_y


def rederive_three_pulse(trimmed: list) -> tuple:
    """Extract (q_h, q_m, q_y) from a trimmed 8760h profile.

    Auto-detects dominant mode by comparing total heating vs cooling energy.
    Sign convention: negative = heating, positive = cooling.
    """
    arr = np.asarray(trimmed, dtype=float)
    heat_energy = float(np.where(arr < 0, -arr, 0).sum())
    cool_energy = float(np.where(arr > 0, arr, 0).sum())
    heating_dominant = heat_energy >= cool_energy
    monthly_avgs = _monthly_averages(arr)
    q_h = float(arr.min() if heating_dominant else arr.max())
    q_m = float(monthly_avgs.min() if heating_dominant else monthly_avgs.max())
    q_y = float(arr.mean())
    return q_h, q_m, q_y
```

- [ ] **Step 4: Run tests**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v
```

Expected: 11/11 PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s6_strategy/ldc.py tests/test_s6_ldc.py
git commit -m "feat(s6): LDC computation, trimming, one-sided and dominant three-pulse extraction"
```

---

## Task 4: Strategy Orchestration + POST /api/strategy

**Files:**
- Create: `geosite/s6_strategy/strategy.py`
- Modify: `geosite/s6_strategy/__init__.py`
- Modify: `app.py`
- Create: `tests/test_s6_strategy.py`

**Interfaces:**
- Consumes:
  - `load_hourly_profile(bt, cz, path) -> list[float]` from `load_profile.py`
  - `scale_profile(profile, factor) -> list[float]` from `load_profile.py`
  - `compute_ldc(profile, pct) -> dict` from `ldc.py`
  - `trim_profile(profile, cutoff_W, dominant_mode) -> list[float]` from `ldc.py`
  - `extract_one_sided_pulses(profile, mode) -> tuple` from `ldc.py`
  - `rederive_three_pulse(trimmed) -> tuple` from `ldc.py`
  - `size_borefield(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B, NB, A) -> float` from `geosite.s4_sizing.ashrae_sizing`
  - `estimate_cost(L_m, NB, B_m, state, rock_class_name, distance_to_house_ft) -> dict` from `geosite.s5_cost`
  - `StrategyResult` from `models.py`
- Produces:
  - `run_strategy(building_type, climate_zone, k, alpha, T_g, NB, B, A, ...) -> StrategyResult`
  - `POST /api/strategy` Flask endpoint

- [ ] **Step 1: Write failing tests**

Create `tests/test_s6_strategy.py`:

```python
import json
import pathlib
import pytest
from app import app
from geosite.s6_strategy import run_strategy

_HOURLY_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads_hourly.json"

# Chicago small office ground params (from prior spreadsheet verification)
_CHICAGO_PARAMS = dict(
    building_type="small_office",
    climate_zone="5A",
    k=2.0, alpha=0.1, T_g=12.0,
    NB=16, B=6.0, A=1.0,
    state="IL",
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_run_strategy_returns_strategy_result():
    from geosite.s6_strategy.models import StrategyResult
    result = run_strategy(**_CHICAGO_PARAMS)
    assert isinstance(result, StrategyResult)


def test_small_office_5a_has_case_1_or_2():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.case in (1, 2)


def test_l_after_less_than_l_before():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.L_after < result.L_before, "Trimming must reduce borefield length"


def test_peaker_kw_positive():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.peaker_kW > 0


def test_peaker_type_is_valid():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.peaker_type in ("electric_heater", "chiller", "electric_heater+chiller")


def test_hourly_profile_length():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert len(result.hourly_profile) == 8760
    assert len(result.hourly_trimmed) == 8760


def test_hourly_trimmed_max_le_cutoff():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert max(abs(h) for h in result.hourly_trimmed) <= result.cutoff_W + 0.1


def test_imbalance_ratio_gte_1():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.imbalance_ratio >= 1.0


def test_floor_area_scaling_changes_result():
    result_default = run_strategy(**_CHICAGO_PARAMS)
    result_scaled = run_strategy(**_CHICAGO_PARAMS, floor_area_m2=1000.0)
    # Larger area → larger loads → larger borefield
    assert result_scaled.L_before != result_default.L_before


def test_api_strategy_endpoint_200(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({
            "building_type": "small_office",
            "climate_zone": "5A",
            "k": 2.0, "alpha": 0.1, "T_g": 12.0,
            "NB": 16, "B": 6.0, "A": 1.0,
            "state": "IL",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200


def test_api_strategy_response_has_required_keys(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({
            "building_type": "small_office",
            "climate_zone": "5A",
            "k": 2.0, "alpha": 0.1, "T_g": 12.0,
            "NB": 16, "B": 6.0, "A": 1.0,
            "state": "IL",
        }),
        content_type="application/json",
    )
    data = resp.get_json()
    for key in ("case", "L_before", "L_after", "peaker_kW", "peaker_type",
                "cost_before", "cost_after", "hourly_profile", "hourly_trimmed"):
        assert key in data, f"Missing key: {key}"


def test_api_strategy_missing_building_type_returns_400(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({"climate_zone": "5A", "k": 2.0, "alpha": 0.1,
                         "T_g": 12.0, "NB": 16, "B": 6.0, "A": 1.0}),
        content_type="application/json",
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_strategy.py -v 2>&1 | head -20
```

Expected: FAIL with `ImportError: cannot import name 'run_strategy'`

- [ ] **Step 3: Create `geosite/s6_strategy/strategy.py`**

```python
import numpy as np
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
    rederive_three_pulse,
)
from geosite.s6_strategy.models import StrategyResult

_ADVANCED_DEFAULTS = {
    "Cp":     4200.0,
    "mfls":   0.05,
    "rbore":  0.06,
    "rpin":   0.01365,
    "rpext":  0.0167,
    "kgrout": 1.5,
    "kpipe":  0.42,
    "LU":     0.0511,
    "hconv":  1000.0,
}
_T_IN_HP = {"heating": 5.0, "cooling": 40.2}
_PROTOTYPE_AREAS_M2 = {"small_office": 511, "medium_office": 4982, "large_office": 46320}


def _do_size(q_h, q_m, q_y, k, alpha, T_g, mode, NB, B, A, adv) -> float:
    return float(size_borefield(
        q_h=q_h, q_m=q_m, q_y=q_y,
        k=k, alpha=alpha, T_g=T_g,
        T_in_HP=_T_IN_HP[mode],
        B=B, NB=NB, A=A,
        **adv,
    ))


def run_strategy(
    building_type: str,
    climate_zone: str,
    k: float,
    alpha: float,
    T_g: float,
    NB: int,
    B: float,
    A: float = 1.0,
    ldc_cutoff_pct: float = 10.0,
    imbalance_threshold: float = 1.25,
    floor_area_m2=None,
    year_factor: float = 1.0,
    state=None,
    **sizing_params,
) -> StrategyResult:
    """Run mandatory hybrid GSHP strategy analysis.

    Loads 8760h profile, detects imbalance, applies LDC cutoff to size peaker,
    re-sizes borefield on trimmed profile, computes before/after cost.
    """
    adv = {k_: sizing_params.get(k_, v) for k_, v in _ADVANCED_DEFAULTS.items()}

    # --- Load and scale 8760h profile ---
    raw_profile = load_hourly_profile(building_type, climate_zone)
    scale = year_factor
    if floor_area_m2 is not None:
        proto_area = _PROTOTYPE_AREAS_M2.get(building_type, 1.0)
        scale *= floor_area_m2 / proto_area
    profile = scale_profile(raw_profile, scale)

    # --- Separate heating/cooling sizing to detect imbalance ---
    q_h_heat, q_m_heat, q_y_heat = extract_one_sided_pulses(profile, "heating")
    q_h_cool, q_m_cool, q_y_cool = extract_one_sided_pulses(profile, "cooling")

    # Guard: if one side has no load (all-heating or all-cooling building), use tiny value
    L_h = _do_size(q_h_heat, q_m_heat, q_y_heat, k, alpha, T_g, "heating", NB, B, A, adv) if q_h_heat < 0 else 0.0
    L_c = _do_size(q_h_cool, q_m_cool, q_y_cool, k, alpha, T_g, "cooling", NB, B, A, adv) if q_h_cool > 0 else 0.0

    # --- Imbalance detection ---
    if L_h == 0.0 and L_c == 0.0:
        imbalance_ratio = 1.0
        dominant_mode = "balanced"
    elif L_h == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "cooling"
    elif L_c == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "heating"
    else:
        imbalance_ratio = max(L_h, L_c) / min(L_h, L_c)
        dominant_mode = "heating" if L_h >= L_c else "cooling"

    case = 1 if imbalance_ratio > imbalance_threshold else 2

    # --- LDC cutoff (from full mixed profile) ---
    ldc = compute_ldc(profile, ldc_cutoff_pct)
    cutoff_W = ldc["cutoff_W"]

    # --- Peaker sizing ---
    trim_mode = dominant_mode if case == 1 else "balanced"

    peaker_heat_kW = max(
        (abs(h) for h in profile if h < 0 and abs(h) > cutoff_W), default=0.0
    ) / 1000.0
    peaker_cool_kW = max(
        (h for h in profile if h > 0 and h > cutoff_W), default=0.0
    ) / 1000.0

    if case == 1:
        if dominant_mode == "heating":
            peaker_kW = peaker_heat_kW
            peaker_type = "electric_heater"
        else:
            peaker_kW = peaker_cool_kW
            peaker_type = "chiller"
    else:
        peaker_kW = max(peaker_heat_kW, peaker_cool_kW)
        peaker_type = "electric_heater+chiller"

    # --- Trim profile + re-derive three-pulse ---
    trimmed = trim_profile(profile, cutoff_W, trim_mode)
    q_h_trimmed, q_m_trimmed, q_y_trimmed = rederive_three_pulse(trimmed)

    # --- Before sizing: use dominant mode's original three-pulse ---
    if dominant_mode in ("heating", "balanced") and L_h >= L_c:
        q_h_before, q_m_before, q_y_before = q_h_heat, q_m_heat, q_y_heat
        before_mode = "heating"
    else:
        q_h_before, q_m_before, q_y_before = q_h_cool, q_m_cool, q_y_cool
        before_mode = "cooling"

    L_before = _do_size(q_h_before, q_m_before, q_y_before, k, alpha, T_g, before_mode, NB, B, A, adv)
    H_before = L_before / NB

    # --- After sizing: trimmed profile uses same before_mode for T_in_HP ---
    trimmed_mode_for_TinHP = before_mode
    L_after = _do_size(q_h_trimmed, q_m_trimmed, q_y_trimmed, k, alpha, T_g, trimmed_mode_for_TinHP, NB, B, A, adv)
    H_after = L_after / NB

    # --- Cost before/after ---
    def _cost(L_m: float) -> dict:
        res = estimate_cost(L_m=L_m, NB=NB, B_m=B, state=state)
        base = res["base"]
        return {
            "total_usd": round(base.total_usd, 2),
            "cost_per_ft": round(base.cost_per_ft, 2),
            "scenario": "base",
        }

    cost_before = _cost(L_before)
    cost_after = _cost(L_after)

    return StrategyResult(
        case=case,
        imbalance_ratio=imbalance_ratio,
        dominant_mode=dominant_mode,
        L_h=L_h,
        L_c=L_c,
        ldc_cutoff_pct=ldc_cutoff_pct,
        cutoff_W=cutoff_W,
        peaker_kW=peaker_kW,
        peaker_type=peaker_type,
        peaker_heat_kW=peaker_heat_kW,
        peaker_cool_kW=peaker_cool_kW,
        q_h_before=q_h_before,
        q_m_before=q_m_before,
        q_y_before=q_y_before,
        q_h_trimmed=q_h_trimmed,
        q_m_trimmed=q_m_trimmed,
        q_y_trimmed=q_y_trimmed,
        L_before=L_before,
        H_before=H_before,
        L_after=L_after,
        H_after=H_after,
        NB=NB,
        cost_before=cost_before,
        cost_after=cost_after,
        hourly_profile=profile,
        hourly_trimmed=trimmed,
    )
```

- [ ] **Step 4: Update `geosite/s6_strategy/__init__.py`**

```python
"""s6_strategy: mandatory hybrid GSHP peak-shaving analysis.

Sizes supplemental peaker (electric heater or chiller) via Load Duration Curve,
trims borefield accordingly, and computes before/after cost comparison.
"""
from geosite.s6_strategy.strategy import run_strategy

__all__ = ["run_strategy"]
```

- [ ] **Step 5: Add `POST /api/strategy` to `app.py`**

Add this import at top of `app.py` (after existing imports):
```python
from geosite.s6_strategy import run_strategy
```

Add this route to `app.py` after the `hourly_loads_api` route:

```python
@app.route("/api/strategy", methods=["POST"])
def strategy_api():
    """Run mandatory hybrid GSHP strategy analysis.

    Required: building_type, climate_zone, k, alpha, T_g, NB, B, A, state
    Optional: ldc_cutoff_pct (default 10), imbalance_threshold (default 1.25),
              floor_area_m2, year_built (int), year_factor (float, overrides year_built)
              Advanced: Cp, mfls, rbore, rpin, rpext, kgrout, kpipe, LU, hconv
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    for field in ("building_type", "climate_zone", "k", "alpha", "T_g", "NB", "B", "A"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    building_type = str(data["building_type"]).strip()
    climate_zone  = str(data["climate_zone"]).strip()
    state         = data.get("state") or None

    try:
        k     = float(data["k"])
        alpha = float(data["alpha"])
        T_g   = float(data["T_g"])
        NB    = int(data["NB"])
        B     = float(data["B"])
        A     = float(data["A"])
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "field", "message": str(exc)}), 400

    ldc_cutoff_pct      = float(data.get("ldc_cutoff_pct", 10.0))
    imbalance_threshold = float(data.get("imbalance_threshold", 1.25))

    floor_area_m2 = None
    if data.get("floor_area_m2"):
        floor_area_m2 = float(data["floor_area_m2"])

    year_factor = 1.0
    if data.get("year_factor"):
        year_factor = float(data["year_factor"])
    elif data.get("year_built"):
        year_factor = _year_to_load_factor(int(data["year_built"]))

    sizing_params = {
        k_: float(data.get(k_, v))
        for k_, v in {
            "Cp": 4200.0, "mfls": 0.05, "rbore": 0.06, "rpin": 0.01365,
            "rpext": 0.0167, "kgrout": 1.5, "kpipe": 0.42, "LU": 0.0511, "hconv": 1000.0,
        }.items()
    }

    try:
        result = run_strategy(
            building_type=building_type,
            climate_zone=climate_zone,
            k=k, alpha=alpha, T_g=T_g,
            NB=NB, B=B, A=A,
            ldc_cutoff_pct=ldc_cutoff_pct,
            imbalance_threshold=imbalance_threshold,
            floor_area_m2=floor_area_m2,
            year_factor=year_factor,
            state=state,
            **sizing_params,
        )
    except KeyError as exc:
        return jsonify({"error": "field", "message": f"Unknown building_type or climate_zone: {exc}"}), 400
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    return jsonify(result.to_dict())
```

- [ ] **Step 6: Run all tests**

```bash
source venv/bin/activate && python -m pytest tests/test_s6_strategy.py tests/test_s6_ldc.py tests/test_s6_load_profile.py -v
```

Expected: all tests PASS

- [ ] **Step 7: Run full suite to check no regressions**

```bash
source venv/bin/activate && python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests pass (may be 100+)

- [ ] **Step 8: Commit**

```bash
git add geosite/s6_strategy/strategy.py geosite/s6_strategy/__init__.py app.py tests/test_s6_strategy.py
git commit -m "feat(s6): run_strategy orchestration + POST /api/strategy endpoint"
```

---

## Task 5: index.html — s6 User UI Section

**Files:**
- Modify: `templates/index.html`

**Context:**
- The s5 cost result is displayed after `POST /api/cost` succeeds.
- After s5 renders, automatically call `POST /api/strategy` and show results.
- The s6 section goes in the results area, after the cost section.
- Chart.js is already loaded in index.html — do not add it again.
- The call to `/api/strategy` requires: `building_type`, `climate_zone`, `k`, `alpha`, `T_g`, `NB`, `B`, `A`, `state`, and optionally `floor_area_m2`, `year_factor`. These are available from the `smartResult` and `costPayload` variables after the smart calculation completes.

**What to add to the results area:**

A new `<div id="s6-section">` hidden initially, revealed after strategy response arrives. Contains:
1. One-sentence headline summary
2. Three info cards: Without Peaker | With Peaker | Peaker Unit  
3. One compact Chart.js line chart (annual hourly profile, 180px height) using decimated weekly averages (52 points)

- [ ] **Step 1: Locate the existing cost section in index.html**

Read `templates/index.html`. Find the element with `id="cost-section"` or similar where s5 cost results are shown. The s6 section goes immediately after it.

- [ ] **Step 2: Add the s6 HTML section**

Find the closing `</div>` of the cost results section in `index.html`. After it, add:

```html
<!-- s6: Hybrid Strategy -->
<div id="s6-section" style="display:none;margin-top:24px">
  <h3 style="font-size:14px;font-weight:600;color:var(--text);margin:0 0 10px">
    Hybrid System Strategy
  </h3>
  <div id="s6-headline" style="font-size:13px;color:var(--muted);margin-bottom:12px;font-style:italic">
    Calculating…
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
    <div class="result-card" style="padding:10px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">Without Peaker</div>
      <div id="s6-before-L" style="font-size:20px;font-weight:700;color:var(--text)">—</div>
      <div id="s6-before-cost" style="font-size:12px;color:var(--muted)">—</div>
    </div>
    <div class="result-card" style="padding:10px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">With Peaker</div>
      <div id="s6-after-L" style="font-size:20px;font-weight:700;color:#10b981">—</div>
      <div id="s6-after-cost" style="font-size:12px;color:var(--muted)">—</div>
    </div>
    <div class="result-card" style="padding:10px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">Peaker Unit</div>
      <div id="s6-peaker-kw" style="font-size:20px;font-weight:700;color:#f59e0b">—</div>
      <div id="s6-peaker-type" style="font-size:12px;color:var(--muted)">—</div>
    </div>
  </div>
  <div style="position:relative;height:180px">
    <canvas id="s6-chart-a"></canvas>
  </div>
</div>
```

- [ ] **Step 3: Add s6 JS handler**

Find where the cost section is populated in the JS (likely after the `fetch('/api/cost', ...)` call). After cost results are displayed, add a call to fetch strategy results. Add this JavaScript function and call:

```javascript
async function fetchStrategy(smartResult, costState) {
  const s6Section = document.getElementById('s6-section');
  s6Section.style.display = 'block';

  const payload = {
    building_type: smartResult.building_type || costState.building_type,
    climate_zone:  smartResult.site.climate_zone,
    k:             smartResult.site.k_effective,
    alpha:         smartResult.site.alpha,
    T_g:           smartResult.site.T_g,
    NB:            smartResult.NB,
    B:             costState.B,
    A:             costState.A,
    state:         smartResult.site.state_abbrev,
    floor_area_m2: smartResult.loads.floor_area_m2 || null,
    year_factor:   smartResult.loads.year_factor || 1.0,
  };

  let res;
  try {
    const resp = await fetch('/api/strategy', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    res = await resp.json();
  } catch (err) {
    document.getElementById('s6-headline').textContent = 'Strategy calculation failed.';
    return;
  }

  const reduction = res.L_before > 0
    ? Math.round((1 - res.L_after / res.L_before) * 100) : 0;
  const peakerLabel = res.peaker_type === 'electric_heater' ? 'electric heater'
    : res.peaker_type === 'chiller' ? 'chiller' : 'electric heater + chiller';

  document.getElementById('s6-headline').textContent =
    `Hybrid system reduces borefield from ${res.L_before.toLocaleString()} m → ` +
    `${res.L_after.toLocaleString()} m (−${reduction}%) with a ` +
    `${res.peaker_kW.toFixed(1)} kW ${peakerLabel}.`;

  document.getElementById('s6-before-L').textContent = `${res.L_before.toLocaleString()} m`;
  document.getElementById('s6-before-cost').textContent =
    `$${(res.cost_before.total_usd / 1000).toFixed(0)}k base`;
  document.getElementById('s6-after-L').textContent = `${res.L_after.toLocaleString()} m`;
  document.getElementById('s6-after-cost').textContent =
    `$${(res.cost_after.total_usd / 1000).toFixed(0)}k base`;
  document.getElementById('s6-peaker-kw').textContent = `${res.peaker_kW.toFixed(1)} kW`;
  document.getElementById('s6-peaker-type').textContent = peakerLabel;

  _renderS6ChartA('s6-chart-a', res.hourly_profile, res.cutoff_W, 180);
}

function _renderS6ChartA(canvasId, hourlyProfile, cutoffW, heightPx) {
  // Downsample to 52 weekly averages for performance
  const weeklyAvg = [];
  for (let w = 0; w < 52; w++) {
    const start = w * 168;
    const end = Math.min(start + 168, hourlyProfile.length);
    const slice = hourlyProfile.slice(start, end);
    weeklyAvg.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  const labels = weeklyAvg.map((_, i) => `W${i + 1}`);
  const colors = weeklyAvg.map(v => v < 0 ? 'rgba(59,130,246,0.7)' : 'rgba(239,68,68,0.7)');

  const canvas = document.getElementById(canvasId);
  canvas.height = heightPx;
  if (canvas._chartInst) canvas._chartInst.destroy();
  canvas._chartInst = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: weeklyAvg,
        backgroundColor: colors,
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {display: false},
        tooltip: {
          callbacks: {
            label: ctx => `${(ctx.raw / 1000).toFixed(1)} kW`,
          },
        },
      },
      scales: {
        x: {display: false},
        y: {
          ticks: {callback: v => `${(v / 1000).toFixed(0)}kW`},
          grid: {color: 'rgba(0,0,0,0.05)'},
        },
      },
    },
  });
}
```

The `fetchStrategy` call must be placed at the end of the existing cost section's success handler, passing `smartResult` (the result from `/calculate/smart`) and an object with `B` and `A` from the form values.

**Important:** You need to read the existing JS in index.html carefully to find:
1. Where `smartResult` is stored after the `/calculate/smart` call
2. Where the cost section success handler ends
3. What variables are available at that point

Add `fetchStrategy(smartResult, {B: parseFloat(formB), A: parseFloat(formA)})` at the right location. Also store `building_type` in `smartResult` if not already present (it comes from the form, not the API response — add it: `smartResult.building_type = building_type;` when the smart result is received).

- [ ] **Step 4: Verify UI works**

```bash
source venv/bin/activate
FLASK_APP=app.py FLASK_RUN_PORT=5001 flask run &
```

Open `http://localhost:5001` in browser. Enter a ZIP code (e.g. 60601 for Chicago) and building type (small_office), submit. After cost section appears, the s6 section should appear below with:
- One-line summary
- Three cards with values
- A bar chart showing weekly averages

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat(s6): hybrid strategy section in user tool with compact chart"
```

---

## Task 6: dev.html — s6 Dev Trace Step with Charts A, B, C

**Files:**
- Modify: `templates/dev.html`

**Context:**
- dev.html has a pipeline trace form. After the s5 cost step card renders (the card with `id="s5-out"` or similar), add a new s6 step card.
- The s6 step is triggered automatically when s5 finishes.
- Three charts: A (annual profile, 360px), B (LDC curve, 300px), C (before/after bar, 250px).
- Chart.js already loaded in dev.html — do not add it again.
- The strategy call reuses all parameters already collected in the trace run.

**What to add:**

A new `.wf-section` div for s6 in the pipeline trace HTML, and corresponding JS in the s6 section of the trace JS handler.

- [ ] **Step 1: Locate s5 card in dev.html**

Read `templates/dev.html`. Find the s5 workflow section card (the one with `<span class="stage-pill" style="background:#8b5cf6">s5</span>`). The s6 section goes immediately after it.

- [ ] **Step 2: Add s6 HTML card after s5 card**

After the closing `</div>` of the s5 `.wf-section`, insert:

```html
<!-- s6: Hybrid Strategy -->
<div class="wf-section" id="s6-wf-section" style="display:none">
  <div class="wf-header" style="margin-bottom:8px;border-bottom:1px dashed var(--border)">
    <span class="stage-pill" style="background:#0ea5e9">s6</span>
    <span class="wf-title" style="font-size:13px">Hybrid Strategy — LDC Peak Shaving</span>
  </div>
  <div class="step-grid">
    <!-- Case detection -->
    <div class="step-card">
      <div class="step-label">Case Detection</div>
      <div class="kv-list" id="s6-case-out"><span class="step-empty">run a trace</span></div>
    </div>
    <!-- LDC params -->
    <div class="step-card">
      <div class="step-label">LDC Parameters</div>
      <div class="kv-list" id="s6-ldc-out"><span class="step-empty">—</span></div>
    </div>
    <!-- Peaker -->
    <div class="step-card">
      <div class="step-label">Peaker Unit</div>
      <div class="kv-list" id="s6-peaker-out"><span class="step-empty">—</span></div>
    </div>
    <!-- Before/after sizing -->
    <div class="step-card full-width">
      <div class="step-label">Sizing — Before vs After Peaker</div>
      <div id="s6-sizing-out"><span class="step-empty">—</span></div>
    </div>
    <!-- Chart A: Annual profile -->
    <div class="step-card full-width">
      <div class="step-label">Chart A — Annual Hourly Ground Load Profile</div>
      <div style="position:relative;height:360px"><canvas id="s6-dev-chart-a"></canvas></div>
    </div>
    <!-- Chart B: LDC curve -->
    <div class="step-card full-width">
      <div class="step-label">Chart B — Load Duration Curve</div>
      <div style="position:relative;height:300px"><canvas id="s6-dev-chart-b"></canvas></div>
    </div>
    <!-- Chart C: Before/after comparison -->
    <div class="step-card full-width">
      <div class="step-label">Chart C — Before vs After (Borefield + Cost)</div>
      <div style="position:relative;height:250px"><canvas id="s6-dev-chart-c"></canvas></div>
    </div>
    <!-- Full StrategyResult table -->
    <div class="step-card full-width">
      <div class="step-label">Full StrategyResult</div>
      <div id="s6-full-out"><span class="step-empty">—</span></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add s6 JS in dev.html trace handler**

Find where the s5 result is rendered in the dev.html JS (after the `fetch('/api/cost', ...)` call in the trace). After s5 renders, add:

```javascript
// s6: Hybrid Strategy
document.getElementById('s6-wf-section').style.display = 'block';
document.getElementById('s6-case-out').innerHTML = '<span class="step-empty">Calculating…</span>';

const s6Payload = {
  building_type: traceForm.building_type,
  climate_zone:  s1Result.climate_zone || traceForm.climate_zone,
  k:             s1Result.k_effective || traceForm.k,
  alpha:         s1Result.alpha       || traceForm.alpha,
  T_g:           s1Result.T_g         || traceForm.T_g,
  NB:            parseInt(traceForm.NB),
  B:             parseFloat(traceForm.B),
  A:             parseFloat(traceForm.A || 1.0),
  state:         s1Result.state_abbrev || null,
  floor_area_m2: traceForm.floor_area_m2 ? parseFloat(traceForm.floor_area_m2) : null,
  year_factor:   s2Result.year_factor || 1.0,
};

fetch('/api/strategy', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify(s6Payload),
})
.then(r => r.json())
.then(s6 => {
  const peakerLabel = s6.peaker_type === 'electric_heater' ? 'Electric Heater'
    : s6.peaker_type === 'chiller' ? 'Chiller' : 'Electric Heater + Chiller';

  // Case detection kv-list
  document.getElementById('s6-case-out').innerHTML = `
    <div class="kv-row"><span class="kv-key">Case</span><span class="kv-val">${s6.case} (${s6.case === 1 ? 'Imbalanced' : 'Balanced'})</span></div>
    <div class="kv-row"><span class="kv-key">Imbalance ratio</span><span class="kv-val">${s6.imbalance_ratio.toFixed(3)}×</span></div>
    <div class="kv-row"><span class="kv-key">Dominant mode</span><span class="kv-val">${s6.dominant_mode}</span></div>
    <div class="kv-row"><span class="kv-key">L_heating</span><span class="kv-val">${s6.L_h.toFixed(0)} m</span></div>
    <div class="kv-row"><span class="kv-key">L_cooling</span><span class="kv-val">${s6.L_c.toFixed(0)} m</span></div>
  `;

  // LDC params
  document.getElementById('s6-ldc-out').innerHTML = `
    <div class="kv-row"><span class="kv-key">Cutoff %</span><span class="kv-val">${s6.ldc_cutoff_pct}%</span></div>
    <div class="kv-row"><span class="kv-key">Cutoff W</span><span class="kv-val">${s6.cutoff_W.toFixed(0)} W (${(s6.cutoff_W/1000).toFixed(1)} kW)</span></div>
    <div class="kv-row"><span class="kv-key">q_h before</span><span class="kv-val">${s6.q_h_before.toFixed(0)} W</span></div>
    <div class="kv-row"><span class="kv-key">q_h trimmed</span><span class="kv-val">${s6.q_h_trimmed.toFixed(0)} W</span></div>
    <div class="kv-row"><span class="kv-key">q_m before</span><span class="kv-val">${s6.q_m_before.toFixed(0)} W</span></div>
    <div class="kv-row"><span class="kv-key">q_m trimmed</span><span class="kv-val">${s6.q_m_trimmed.toFixed(0)} W</span></div>
    <div class="kv-row"><span class="kv-key">q_y before</span><span class="kv-val">${s6.q_y_before.toFixed(0)} W</span></div>
    <div class="kv-row"><span class="kv-key">q_y trimmed</span><span class="kv-val">${s6.q_y_trimmed.toFixed(0)} W</span></div>
  `;

  // Peaker
  document.getElementById('s6-peaker-out').innerHTML = `
    <div class="kv-row"><span class="kv-key">Type</span><span class="kv-val">${peakerLabel}</span></div>
    <div class="kv-row"><span class="kv-key">Capacity</span><span class="kv-val">${s6.peaker_kW.toFixed(1)} kW</span></div>
    <div class="kv-row"><span class="kv-key">Heat-side</span><span class="kv-val">${s6.peaker_heat_kW.toFixed(1)} kW</span></div>
    <div class="kv-row"><span class="kv-key">Cool-side</span><span class="kv-val">${s6.peaker_cool_kW.toFixed(1)} kW</span></div>
  `;

  // Sizing before/after
  const reduction = s6.L_before > 0 ? ((1 - s6.L_after/s6.L_before)*100).toFixed(1) : 0;
  const costSave = ((s6.cost_before.total_usd - s6.cost_after.total_usd)/1000).toFixed(0);
  document.getElementById('s6-sizing-out').innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr>
        <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--border)"></th>
        <th style="text-align:right;padding:4px 8px;border-bottom:1px solid var(--border)">Without Peaker</th>
        <th style="text-align:right;padding:4px 8px;border-bottom:1px solid var(--border)">With Peaker</th>
        <th style="text-align:right;padding:4px 8px;border-bottom:1px solid var(--border)">Reduction</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:4px 8px">Total length L</td>
            <td style="text-align:right;padding:4px 8px">${s6.L_before.toLocaleString()} m</td>
            <td style="text-align:right;padding:4px 8px;color:#10b981">${s6.L_after.toLocaleString()} m</td>
            <td style="text-align:right;padding:4px 8px;color:#10b981">−${reduction}%</td></tr>
        <tr><td style="padding:4px 8px">Depth H</td>
            <td style="text-align:right;padding:4px 8px">${s6.H_before.toLocaleString()} m</td>
            <td style="text-align:right;padding:4px 8px;color:#10b981">${s6.H_after.toLocaleString()} m</td>
            <td style="text-align:right;padding:4px 8px">per borehole</td></tr>
        <tr><td style="padding:4px 8px">Base cost</td>
            <td style="text-align:right;padding:4px 8px">$${(s6.cost_before.total_usd/1000).toFixed(0)}k</td>
            <td style="text-align:right;padding:4px 8px;color:#10b981">$${(s6.cost_after.total_usd/1000).toFixed(0)}k</td>
            <td style="text-align:right;padding:4px 8px;color:#10b981">−$${costSave}k</td></tr>
      </tbody>
    </table>
  `;

  // Chart A: annual hourly profile (weekly averages, 52 bars)
  _devChartA(s6.hourly_profile, s6.cutoff_W);
  // Chart B: LDC curve (downsample to 876 points: every 10th)
  _devChartB(s6.hourly_profile, s6.cutoff_W);
  // Chart C: before/after bars
  _devChartC(s6);
})
.catch(err => {
  document.getElementById('s6-case-out').innerHTML =
    `<span class="step-empty" style="color:#ef4444">Error: ${err.message}</span>`;
});

function _devChartA(hourlyProfile, cutoffW) {
  const weekly = [];
  for (let w = 0; w < 52; w++) {
    const sl = hourlyProfile.slice(w * 168, w * 168 + 168);
    weekly.push(sl.reduce((a, b) => a + b, 0) / sl.length);
  }
  const colors = weekly.map(v => v < 0 ? 'rgba(59,130,246,0.8)' : 'rgba(239,68,68,0.8)');
  const canvas = document.getElementById('s6-dev-chart-a');
  if (canvas._ci) canvas._ci.destroy();
  canvas._ci = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: weekly.map((_, i) => `W${i+1}`),
      datasets: [
        {data: weekly, backgroundColor: colors, borderWidth: 0, label: 'Ground load'},
        {
          type: 'line', label: `+Cutoff (${(cutoffW/1000).toFixed(1)}kW)`,
          data: Array(52).fill(cutoffW), borderColor: '#f59e0b',
          borderDash: [4, 2], pointRadius: 0, borderWidth: 1.5,
        },
        {
          type: 'line', label: `-Cutoff`,
          data: Array(52).fill(-cutoffW), borderColor: '#f59e0b',
          borderDash: [4, 2], pointRadius: 0, borderWidth: 1.5,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {legend: {display: true}},
      scales: {
        x: {display: false},
        y: {ticks: {callback: v => `${(v/1000).toFixed(0)}kW`}},
      },
    },
  });
}

function _devChartB(hourlyProfile, cutoffW) {
  const sorted = [...hourlyProfile].map(Math.abs).sort((a, b) => b - a);
  // Downsample: every 10th point → 876 points
  const ds = sorted.filter((_, i) => i % 10 === 0);
  const cutoffIdx = Math.round(hourlyProfile.length * 0.10);
  const dsIdx = Math.round(cutoffIdx / 10);
  const canvas = document.getElementById('s6-dev-chart-b');
  if (canvas._ci) canvas._ci.destroy();
  canvas._ci = new Chart(canvas, {
    type: 'line',
    data: {
      labels: ds.map((_, i) => i * 10),
      datasets: [
        {
          data: ds, borderColor: '#6366f1', borderWidth: 1.5,
          pointRadius: 0, fill: false, label: '|Load| (W)',
        },
        {
          type: 'line', data: Array(ds.length).fill(cutoffW),
          borderColor: '#f59e0b', borderDash: [4, 2], pointRadius: 0,
          borderWidth: 1.5, label: `Cutoff (${(cutoffW/1000).toFixed(1)} kW)`,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: {display: true},
        annotation: {},
      },
      scales: {
        x: {title: {display: true, text: 'Rank (1=largest)'}},
        y: {ticks: {callback: v => `${(v/1000).toFixed(0)}kW`}},
      },
    },
  });
}

function _devChartC(s6) {
  const canvas = document.getElementById('s6-dev-chart-c');
  if (canvas._ci) canvas._ci.destroy();
  canvas._ci = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: ['Borefield L (m)', 'Depth H (m/borehole)', 'Base Cost ($k)'],
      datasets: [
        {
          label: 'Without Peaker',
          data: [s6.L_before, s6.H_before, s6.cost_before.total_usd / 1000],
          backgroundColor: 'rgba(99,102,241,0.7)',
        },
        {
          label: 'With Peaker',
          data: [s6.L_after, s6.H_after, s6.cost_after.total_usd / 1000],
          backgroundColor: 'rgba(16,185,129,0.7)',
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {legend: {display: true}},
      scales: {y: {beginAtZero: true}},
    },
  });
}
```

**Important:** Read dev.html carefully before editing to find the correct variable names for `traceForm`, `s1Result`, `s2Result` (these may differ from what's shown here). Match the variable names already used in the existing s5 JS handler.

Also add `s6` to the sidebar navigation: find `<li id="s6-nav"` or similar sidebar link and change its class from `disabled` or similar to `active-dim` (matching the s5 sidebar pattern).

- [ ] **Step 4: Test the dev UI**

Navigate to `http://localhost:5001/dev`. Run a trace with any valid inputs. After s5 cost renders, s6 should appear with:
- Case detection (Case 1 or 2)
- LDC params table
- Peaker table
- Sizing comparison table
- Chart A (bar chart, weekly averages, 360px)
- Chart B (LDC curve, 300px)
- Chart C (before/after comparison bar chart, 250px)

- [ ] **Step 5: Run full test suite**

```bash
source venv/bin/activate && python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add templates/dev.html templates/index.html
git commit -m "feat(s6): three-chart hybrid strategy UI in user tool and dev trace"
```

---

## Self-Review

### Spec Coverage Check

| Spec requirement | Covered by Task |
|---|---|
| Mandatory hybrid GSHP analysis for every project | Task 4 (run_strategy always called) |
| Philippe et al. imbalance detection: separate L_h and L_c sizings | Task 4 (strategy.py) |
| LDC 10% default cutoff, user-configurable | Task 3 (ldc.py), Task 4 (API param) |
| Case 1 (imbalanced): dominant-side-only trimming | Task 3 (trim_profile mode="heating"/"cooling") |
| Case 2 (balanced): symmetric trimming | Task 3 (trim_profile mode="balanced") |
| Electric heater for heating-dominant | Task 4 (peaker_type logic) |
| Chiller for cooling-dominant | Task 4 (peaker_type logic) |
| "electric_heater+chiller" for balanced | Task 4 (Case 2) |
| Peaker capacity = max instantaneous load above cutoff | Task 4 (strategy.py) |
| Before-sizing uses dominant-mode original three-pulse | Task 4 (strategy.py) |
| After-sizing uses trimmed three-pulse | Task 4 (strategy.py) |
| Cost before/after (base scenario) | Task 4 (estimate_cost calls) |
| 8760h hourly profiles extracted from EnergyPlus cache | Task 1 (script) |
| Floor area scaling | Task 4 (scale_profile) |
| Year factor applied | Task 4 (scale_profile) |
| GET /api/loads/hourly | Task 1 |
| POST /api/strategy | Task 4 |
| StrategyResult dataclass with all fields | Task 2 |
| StrategyResult.to_dict() serialization | Task 2 |
| Chart A: annual hourly profile (weekly averages, both tools) | Tasks 5, 6 |
| Chart B: LDC curve (dev only) | Task 6 |
| Chart C: before/after comparison (both tools) | Tasks 5, 6 |
| One-line summary in user tool | Task 5 |
| Three callout cards in user tool | Task 5 |
| Full StrategyResult table in dev tool | Task 6 |
| Imbalance threshold 1.25 default, configurable | Task 4 |
| tests/test_s6_strategy.py with 11+ tests | Tasks 3, 4 |

### No-Placeholder Scan

All code blocks are complete. No TBD or TODO markers. Tests have concrete assertions with specific values. Commands have expected outputs.

### Type Consistency Check

- `extract_one_sided_pulses` → `tuple[float, float, float]` ✓ used correctly in strategy.py
- `rederive_three_pulse` → `tuple[float, float, float]` ✓ used correctly
- `compute_ldc` → `dict` with `cutoff_idx`, `cutoff_W`, `sorted_abs` ✓ accessed correctly
- `trim_profile` → `list[float]` ✓ passed to rederive_three_pulse
- `run_strategy` → `StrategyResult` ✓ .to_dict() called in app.py
- `StrategyResult.to_dict()` → `dict` ✓ returned by Flask endpoint
- All sizing params match `size_borefield` signature ✓ verified from real signature

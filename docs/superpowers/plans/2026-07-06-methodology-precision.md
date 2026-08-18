# Methodology & Precision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sizing pipeline match standard engineering practice: report kWh (not just hours) coverage for the hybrid strategy, size by target borehole depth instead of fixed borehole count, support ASHRAE-style 99.6% design-peak extraction, and fix the q_y sign-convention inconsistency between s3 and s6.

**Architecture:** All physics changes live in `geosite/s6_strategy/ldc.py` (coverage metrics, peak exclusion, net q_y) and `geosite/s4_sizing/ashrae_sizing.py` (a new depth-primary wrapper `size_borefield_for_depth` that iterates NB = ceil(L/H_target) to a fixed point, since NB feeds the Tp interaction correction). `run_strategy` and the two Flask endpoints gain `H_target`/`ignore_top_pct` parameters with full backward compatibility: passing an explicit `NB` preserves today's fixed-count behavior, so every existing test keeps passing.

**Tech Stack:** Python 3.11 (venv at `./venv`), Flask, numpy, pytest; vanilla JS frontend (`static/main.js`, `templates/index.html`).

## Global Constraints

- Run tests with: `source venv/bin/activate && python -m pytest tests/ -v` (from repo root `/Users/agao/Downloads/CEE299/geosite_advisor`)
- Ground load sign convention: **positive = cooling (heat injection into ground), negative = heating (heat extraction from ground)**
- Do NOT modify `borehole_resistance`, `_g_poly`, `_peak_correction`, or the fixed-NB `size_borefield` iteration in `geosite/s4_sizing/ashrae_sizing.py` — they are validated against the Philippe et al. (2010) reference spreadsheet (`data/reference/philippe_2010_sizing.xlsx`) and must keep producing identical outputs
- `size_borefield()` signature: `size_borefield(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B=None, NB=None, A=1.0, tol=1.0, max_iter=200) -> float`
- Advanced defaults (verbatim, used in 3 places): `Cp=4200.0, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167, kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0`
- T_in_HP defaults: heating mode 5.0 °C, cooling mode 40.2 °C
- New defaults introduced by this plan: `H_target=125.0` m (valid API range 30–300), `ignore_top_pct=0.0` % (valid API range 0–5; ASHRAE 99.6% ≈ 0.4)
- LDC default cutoff stays `ldc_cutoff_pct=10.0`; imbalance threshold stays 1.25
- Reference data for integration tests — Denver Medium Office 5B at prototype scale: max cooling +419.2 kW, min heating −172.8 kW, annual avg +21.7 kW, `cutoff_W` ≈ 122.4 kW at 10%, worst cooling month avg ≈ +89.0 kW (June)
- Backward compatibility: any call that passes an explicit `NB` (Python or HTTP) must behave exactly as before this plan (same L, same H = L/NB, same cost)
- Each hourly profile value is W over one hour, so summing W over the 8760 array yields Wh directly
- No comments in code unless the WHY is non-obvious

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `geosite/constants.py` | Shared `MONTH_HOURS` list (currently duplicated in s3 and s6) |
| Modify | `geosite/s6_strategy/ldc.py` | Energy coverage metrics, net q_y, `ignore_top_pct` |
| Modify | `geosite/s3_loads/compute.py` | Import `MONTH_HOURS` from constants |
| Modify | `geosite/s4_sizing/ashrae_sizing.py` | Add `size_borefield_for_depth()` (new function only) |
| Modify | `geosite/s6_strategy/strategy.py` | Depth-primary mode, coverage fields, per-scenario NB |
| Modify | `geosite/s6_strategy/models.py` | New `StrategyResult` fields + `to_dict` keys |
| Modify | `app.py` | `H_target`/`ignore_top_pct` on `/api/strategy`; depth mode on `/calculate/smart` |
| Modify | `templates/index.html`, `static/main.js` | Depth input replaces borehole-count input; coverage display |
| Create | `tests/test_s4_depth_sizing.py`, `tests/test_s6_precision.py` | New behavior |
| Modify | `tests/test_s6_ldc.py` | Coverage metrics, net q_y, peak exclusion |

**Audit results baked into this plan (from reading the current code):**
1. `extract_one_sided_pulses` computes q_y from the one-sided profile (opposite-sign hours zeroed), but `compute_pulses` in s3 and the two-pass sizing in `/calculate/smart` both use the **net** annual mean. The annual pulse models long-term ground heat buildup, which physically nets injection against extraction — s6 currently over-states depletion and over-sizes L. Task 2 fixes this.
2. Peaker sizing with **max** excess is correct and stays: the peaker's rated capacity must meet the worst instantaneous shortfall or the building has unmet load at design conditions; mean/percentile excess would undersize the unit. Units verified: profile in W, `cutoff_W` in W, `/ 1000.0` yields kW correctly. Task 5 documents this in the docstring and Task 5's tests pin it against the Denver reference numbers. What max-sizing lacks is an economics signal, so Task 1 adds peaker annual kWh alongside.
3. `_MONTH_HOURS` in both `ldc.py` and `compute.py` sums to 8760 with correct non-leap month boundaries (Jan=744 … Dec=744) and EnergyPlus output starts Jan 1 hour 1 — boundaries are correct, but the list is duplicated (drift risk). Task 2 consolidates it.
4. The naive spec formula `sum(sorted_abs[cutoff_idx:]) / sum(sorted_abs)` under-counts GSHP energy: after trimming, the GSHP still carries `cutoff_W` during every peak hour (trim clips, it does not zero). The correct GSHP share is `sum(min(|q(h)|, cutoff_W)) / sum(|q(h)|)`, equivalently `1 − excess/total`. Task 1 implements the correct form.

---

## Task 1: LDC Energy Coverage Metrics

**Files:**
- Modify: `geosite/s6_strategy/ldc.py` (function `compute_ldc`, currently lines 15–25)
- Test: `tests/test_s6_ldc.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `compute_ldc(profile: list, cutoff_pct: float) -> dict` with three NEW keys used by Task 5: `"gshp_energy_pct"` (float, 0–100), `"gshp_hours_pct"` (float, 0–100), `"peaker_energy_Wh"` (float, ≥ 0). Existing keys `"cutoff_idx"`, `"cutoff_W"`, `"sorted_abs"` unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s6_ldc.py`:

```python
def test_ldc_energy_coverage_small_profile():
    # sorted desc: 100, 50, 50, 50; 25% cutoff -> idx=1, cutoff_W=50
    # GSHP covers min(|q|, 50) each hour = 50+50+50+50 = 200 of 250 total
    profile = [100.0, 50.0, 50.0, 50.0]
    result = compute_ldc(profile, 25.0)
    assert result["gshp_energy_pct"] == pytest.approx(80.0)
    assert result["gshp_hours_pct"] == pytest.approx(75.0)
    assert result["peaker_energy_Wh"] == pytest.approx(50.0)


def test_ldc_energy_coverage_triangle_profile():
    # 1..8760 W: cutoff_idx=876, cutoff_W=7884
    # excess = sum(8760..7885) - 876*7884 = 7290510 - 6906384 = 384126
    # total = 8760*8761/2 = 38373180 -> coverage = 98.999%
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0)
    assert result["gshp_energy_pct"] == pytest.approx(99.0, abs=0.05)
    assert result["gshp_hours_pct"] == pytest.approx(90.0)
    assert result["peaker_energy_Wh"] == pytest.approx(384126.0, rel=1e-6)


def test_ldc_energy_coverage_zero_profile_is_100pct():
    result = compute_ldc([0.0] * 8760, 10.0)
    assert result["gshp_energy_pct"] == 100.0
    assert result["peaker_energy_Wh"] == 0.0


def test_ldc_energy_coverage_zero_cutoff_pct_is_100pct():
    # cutoff_pct=0 -> cutoff at the absolute max -> no excess, no peaker
    result = compute_ldc(list(range(1, 8761)), 0.0)
    assert result["gshp_energy_pct"] == 100.0
    assert result["gshp_hours_pct"] == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v -k energy_coverage`
Expected: 4 FAILs with `KeyError: 'gshp_energy_pct'`

- [ ] **Step 3: Implement `compute_ldc` energy metrics**

Replace the `compute_ldc` function in `geosite/s6_strategy/ldc.py` with:

```python
def compute_ldc(profile: list, cutoff_pct: float) -> dict:
    """Sort profile by |load| descending, return cutoff at x% rank plus coverage metrics.

    GSHP energy share counts min(|q(h)|, cutoff_W) every hour: after LDC
    trimming the GSHP still carries the base load during peak hours, so the
    peaker only supplies the excess above the cutoff.
    """
    arr = np.asarray(profile, dtype=float)
    n = len(arr)
    sorted_abs = np.sort(np.abs(arr))[::-1]
    cutoff_idx = int(n * cutoff_pct / 100)
    cutoff_W = float(sorted_abs[cutoff_idx]) if cutoff_idx < n else 0.0

    total_Wh = float(sorted_abs.sum())
    excess_Wh = float((sorted_abs[:cutoff_idx] - cutoff_W).sum()) if cutoff_idx > 0 else 0.0
    gshp_energy_pct = 100.0 * (1.0 - excess_Wh / total_Wh) if total_Wh > 0 else 100.0
    gshp_hours_pct = 100.0 * (n - cutoff_idx) / n if n > 0 else 100.0

    return {
        "cutoff_idx": cutoff_idx,
        "cutoff_W": cutoff_W,
        "sorted_abs": sorted_abs.tolist(),
        "gshp_energy_pct": gshp_energy_pct,
        "gshp_hours_pct": gshp_hours_pct,
        "peaker_energy_Wh": excess_Wh,
    }
```

- [ ] **Step 4: Run the full LDC test file**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v`
Expected: all PASS (existing cutoff tests plus the 4 new ones)

- [ ] **Step 5: Commit**

```bash
git add geosite/s6_strategy/ldc.py tests/test_s6_ldc.py
git commit -m "feat(s6): add GSHP energy/hours coverage metrics to LDC"
```

---

## Task 2: Net Annual Pulse q_y + Shared MONTH_HOURS Constant

**Files:**
- Create: `geosite/constants.py`
- Modify: `geosite/s6_strategy/ldc.py` (top of file + `extract_one_sided_pulses`, currently lines 41–53)
- Modify: `geosite/s3_loads/compute.py` (lines 14–15)
- Test: `tests/test_s6_ldc.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `geosite.constants.MONTH_HOURS: list[int]` (12 entries, sums to 8760). `extract_one_sided_pulses(profile, mode)` keeps its signature but q_y is now the NET mean of the full profile (Task 3 adds a third parameter; Task 5 relies on this net-q_y behavior).

**Why:** q_y is the 10-year annual pulse in the Philippe equation — it models net ground heat buildup. `compute_pulses` (s3) and `/calculate/smart` two-pass sizing already use the net mean; only s6 zeroes the opposite side first, inflating |q_y| and over-sizing L. This task aligns s6 with the validated s3 path.

- [ ] **Step 1: Update the existing test that pins the old behavior, and add the new one**

In `tests/test_s6_ldc.py`, DELETE this test:

```python
def test_extract_one_sided_zeroes_opposite():
    # Heating only: cooling hours contribute 0 to annual average
    profile = [-10000.0] * 4380 + [15000.0] * 4380  # half heat, half cool
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    # q_y = mean of heating-only profile (cooling hours zeroed)
    # heating contribution: -10000 * 4380 / 8760 = -5000
    assert q_y == pytest.approx(-5000.0, rel=0.01)
```

and ADD in its place:

```python
def test_extract_q_y_is_net_annual_mean():
    # q_y models net ground heat buildup: (-10000*4380 + 15000*4380)/8760 = +2500
    profile = [-10000.0] * 4380 + [15000.0] * 4380
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    assert q_y == pytest.approx(2500.0, rel=0.01)
    assert q_h == pytest.approx(-10000.0)


def test_extract_q_y_identical_for_both_modes():
    profile = [-10000.0] * 4380 + [15000.0] * 4380
    _, _, q_y_heat = extract_one_sided_pulses(profile, "heating")
    _, _, q_y_cool = extract_one_sided_pulses(profile, "cooling")
    assert q_y_heat == pytest.approx(q_y_cool)


def test_month_hours_constant_sums_to_8760():
    from geosite.constants import MONTH_HOURS
    assert len(MONTH_HOURS) == 12
    assert sum(MONTH_HOURS) == 8760
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v -k "net_annual or both_modes or month_hours"`
Expected: FAIL — `q_y == -5000` (not 2500) and `ModuleNotFoundError: No module named 'geosite.constants'`

- [ ] **Step 3: Create the shared constant**

Create `geosite/constants.py`:

```python
"""Shared constants for the geosite pipeline."""

# Hours per calendar month, non-leap year, Jan..Dec. Sums to 8760.
MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
```

- [ ] **Step 4: Use the constant and switch q_y to net mean**

In `geosite/s6_strategy/ldc.py`, replace:

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
```

with:

```python
import numpy as np

from geosite.constants import MONTH_HOURS


def _monthly_averages(arr: np.ndarray) -> np.ndarray:
    avgs = np.empty(12)
    idx = 0
    for m, hours in enumerate(MONTH_HOURS):
        avgs[m] = arr[idx: idx + hours].mean()
        idx += hours
    return avgs
```

and replace `extract_one_sided_pulses` with:

```python
def extract_one_sided_pulses(profile: list, mode: str) -> tuple:
    """Extract (q_h, q_m, q_y) for one-mode sizing.

    q_h and q_m come from the one-sided profile (opposite-sign hours zeroed):
    'heating' keeps negative hours (q_h < 0), 'cooling' keeps positive (q_h > 0).
    q_y is the NET annual mean of the full profile: the annual pulse models
    long-term ground heat buildup, which nets injection against extraction.
    This matches compute_pulses() in s3 and the /calculate/smart two-pass path.
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
    q_y = float(arr.mean())
    return q_h, q_m, q_y
```

In `geosite/s3_loads/compute.py`, replace:

```python
# Approximate hours per month for a non-leap year
_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
```

with:

```python
from geosite.constants import MONTH_HOURS as _MONTH_HOURS
```

(keep the `_MONTH_HOURS` alias — `compute.py` uses that name in `_monthly_averages` at the bottom of the file).

- [ ] **Step 5: Run the whole suite (this change shifts s6 L values — all s6 tests are qualitative and must still pass)**

Run: `source venv/bin/activate && python -m pytest tests/ -v`
Expected: all PASS. If `tests/test_s6_strategy.py::test_l_after_less_than_l_before` fails, the trim/extract wiring is wrong — do not loosen the test.

- [ ] **Step 6: Commit**

```bash
git add geosite/constants.py geosite/s6_strategy/ldc.py geosite/s3_loads/compute.py tests/test_s6_ldc.py
git commit -m "fix(s6): use net annual mean for q_y; share MONTH_HOURS constant"
```

---

## Task 3: ASHRAE-Style Peak-Hour Exclusion (`ignore_top_pct`)

**Files:**
- Modify: `geosite/s6_strategy/ldc.py` (`extract_one_sided_pulses` from Task 2)
- Test: `tests/test_s6_ldc.py`

**Interfaces:**
- Consumes: Task 2's `extract_one_sided_pulses`
- Produces: `extract_one_sided_pulses(profile: list, mode: str, ignore_top_pct: float = 0.0) -> tuple[float, float, float]`. With `ignore_top_pct=0.0` the output is bit-identical to Task 2. Task 5 passes this parameter through `run_strategy`.

**Concept:** ASHRAE design conditions use the 99.6% annual percentile rather than the absolute extreme. `ignore_top_pct=0.4` means q_h is the magnitude exceeded in only the top 0.4% of hours (~35 h), so one freak hour cannot over-size the borefield. Only q_h is affected; q_m and q_y are averages and stay untouched. The peaker (Task 5) still covers the true extreme.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s6_ldc.py`:

```python
def test_ignore_top_pct_default_zero_is_unchanged():
    profile = [-50000.0] * 5 + [-20000.0] * 100 + [0.0] * 8655
    assert extract_one_sided_pulses(profile, "heating") == \
        extract_one_sided_pulses(profile, "heating", 0.0)


def test_ignore_top_pct_skips_extreme_heating_hours():
    # 5 freak hours at -50 kW, design load -20 kW
    # 0.1% of 8760 = 8.76 -> round -> 9 hours ignored -> q_h = -20000
    profile = [-50000.0] * 5 + [-20000.0] * 100 + [0.0] * 8655
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating", 0.1)
    assert q_h == pytest.approx(-20000.0)


def test_ignore_top_pct_skips_extreme_cooling_hours():
    profile = [60000.0] * 5 + [25000.0] * 100 + [0.0] * 8655
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "cooling", 0.1)
    assert q_h == pytest.approx(25000.0)


def test_ignore_top_pct_leaves_q_m_and_q_y_unchanged():
    profile = [-50000.0] * 5 + [-20000.0] * 100 + [0.0] * 8655
    _, q_m0, q_y0 = extract_one_sided_pulses(profile, "heating", 0.0)
    _, q_m1, q_y1 = extract_one_sided_pulses(profile, "heating", 0.4)
    assert q_m1 == pytest.approx(q_m0)
    assert q_y1 == pytest.approx(q_y0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v -k ignore_top`
Expected: FAIL with `TypeError: extract_one_sided_pulses() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Implement the parameter**

Replace `extract_one_sided_pulses` in `geosite/s6_strategy/ldc.py` with:

```python
def extract_one_sided_pulses(profile: list, mode: str,
                             ignore_top_pct: float = 0.0) -> tuple:
    """Extract (q_h, q_m, q_y) for one-mode sizing.

    q_h and q_m come from the one-sided profile (opposite-sign hours zeroed):
    'heating' keeps negative hours (q_h < 0), 'cooling' keeps positive (q_h > 0).
    q_y is the NET annual mean of the full profile: the annual pulse models
    long-term ground heat buildup, which nets injection against extraction.

    ignore_top_pct: ASHRAE-style design percentile. 0.4 means q_h is the
    magnitude exceeded in only the top 0.4% of hours (~35 h/yr), so a single
    extreme hour cannot govern the borefield. Affects q_h only.
    """
    arr = np.asarray(profile, dtype=float)
    n_ignore = int(round(arr.size * ignore_top_pct / 100.0))
    n_ignore = min(n_ignore, arr.size - 1)
    if mode == "heating":
        one_sided = np.where(arr < 0, arr, 0.0)
        q_h = float(np.sort(one_sided)[n_ignore])
        q_m = float(_monthly_averages(one_sided).min())
    else:
        one_sided = np.where(arr > 0, arr, 0.0)
        q_h = float(np.sort(one_sided)[::-1][n_ignore])
        q_m = float(_monthly_averages(one_sided).max())
    q_y = float(arr.mean())
    return q_h, q_m, q_y
```

(`np.sort` ascending puts the most-negative heating hours first, so index `n_ignore` is the (n_ignore+1)-th worst extraction hour; the reversed sort does the same for cooling.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_ldc.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s6_strategy/ldc.py tests/test_s6_ldc.py
git commit -m "feat(s6): ASHRAE-style ignore_top_pct peak-hour exclusion"
```

---

## Task 4: Depth-Primary Sizing (`size_borefield_for_depth`)

**Files:**
- Modify: `geosite/s4_sizing/ashrae_sizing.py` (append new function only; do not touch existing functions)
- Test: `tests/test_s4_depth_sizing.py` (create)

**Interfaces:**
- Consumes: existing `size_borefield(...)` (signature in Global Constraints)
- Produces: `size_borefield_for_depth(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B, A=1.0, H_target=125.0, tol=1.0, max_nb_iter=25) -> tuple[float, int, float]` returning `(L, NB, H)`. Task 5 and Task 6 call this.

**Why iterate:** NB is an input to the Tp inter-borehole interaction polynomial, so you cannot just divide once. The loop finds the joint fixed point: guess NB from the interaction-free L₀, re-size with that NB, recompute `NB = ceil(L / H_target)`, repeat until NB stabilizes (2–4 iterations in practice). At the fixed point `NB = ceil(L / H_target)` guarantees `H = L/NB ≤ H_target`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s4_depth_sizing.py`:

```python
"""Depth-primary sizing: NB derived from target borehole depth.

XLS_D inputs are the philippe_2010_sizing.xls bh_sizing column D cooling
case, which gives L0 = 151.657 m without borefield interaction.
"""

import math
import pytest

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

XLS_D = dict(
    q_h=12_000.0, q_m=6_000.0, q_y=1_500.0,
    k=2.0, alpha=0.086, T_g=15.0,
    Cp=4_200.0, mfls=0.05, T_in_HP=40.2,
    rbore=0.06, rpin=0.01365, rpext=0.0167,
    kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0,
)


def test_depth_sizing_small_load_two_boreholes():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=125.0)
    assert NB == 2
    assert H == pytest.approx(L / NB)
    assert H <= 125.0
    assert 140 < L < 180


def test_depth_sizing_single_borehole_when_target_exceeds_L0():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=200.0)
    assert NB == 1
    assert 140 < L < 180
    assert H <= 200.0


def test_depth_sizing_large_load_fixed_point_invariant():
    big = dict(XLS_D, q_h=1_200_000.0, q_m=600_000.0, q_y=150_000.0)
    L, NB, H = size_borefield_for_depth(**big, B=6.1, A=1.0, H_target=125.0)
    assert NB == math.ceil(L / 125.0)
    assert H <= 125.0
    assert NB > 50


def test_depth_sizing_consistent_with_fixed_nb():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=125.0)
    L_fixed = float(size_borefield(**XLS_D, B=6.1, NB=NB, A=1.0))
    assert L == pytest.approx(L_fixed, abs=1.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_depth_sizing.py -v`
Expected: FAIL with `ImportError: cannot import name 'size_borefield_for_depth'`

- [ ] **Step 3: Implement the function**

Append to `geosite/s4_sizing/ashrae_sizing.py`:

```python
def size_borefield_for_depth(
    q_h: float,
    q_m: float,
    q_y: float,
    k: float,
    alpha: float,
    T_g: float,
    Cp: float,
    mfls: float,
    T_in_HP: float,
    rbore: float,
    rpin: float,
    rpext: float,
    kgrout: float,
    kpipe: float,
    LU: float,
    hconv: float,
    B: float,
    A: float = 1.0,
    H_target: float = 125.0,
    tol: float = 1.0,
    max_nb_iter: int = 25,
) -> tuple[float, int, float]:
    """Depth-primary borefield sizing: derive NB from a target borehole depth.

    Standard industry practice fixes the borehole depth (drill-rig capability,
    typically 100-150 m) and derives the borehole count. Because NB feeds the
    Tp interaction correction, L and NB are iterated to a joint fixed point:
        NB = ceil(L / H_target)  with  L = size_borefield(..., NB=NB).

    Returns
    -------
    (L, NB, H) : total length [m], borehole count, actual depth per hole [m].
                 At the fixed point H <= H_target by construction.
                 A non-positive L (non-binding fluid-temperature constraint)
                 returns (L, 1, L) without iterating.
    """
    common = dict(
        q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g,
        Cp=Cp, mfls=mfls, T_in_HP=T_in_HP, rbore=rbore, rpin=rpin,
        rpext=rpext, kgrout=kgrout, kpipe=kpipe, LU=LU, hconv=hconv,
        tol=tol,
    )
    L = float(size_borefield(**common))
    if L <= 0:
        return L, 1, L

    NB = max(1, math.ceil(L / H_target))
    seen: set[int] = set()
    for _ in range(max_nb_iter):
        L = float(size_borefield(**common, B=B, NB=NB, A=A))
        if L <= 0:
            return L, 1, L
        NB_new = max(1, math.ceil(L / H_target))
        if NB_new == NB:
            break
        if NB_new in seen:
            # ceil() can 2-cycle near a boundary; more boreholes = shallower,
            # conservative side of the target depth
            NB = max(NB, NB_new)
            L = float(size_borefield(**common, B=B, NB=NB, A=A))
            break
        seen.add(NB)
        NB = NB_new
    return L, NB, L / NB
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_depth_sizing.py tests/test_s4_sizing.py -v`
Expected: all PASS (including the untouched spreadsheet-parity tests)

- [ ] **Step 5: Commit**

```bash
git add geosite/s4_sizing/ashrae_sizing.py tests/test_s4_depth_sizing.py
git commit -m "feat(s4): depth-primary sizing (H_target -> NB fixed point)"
```

---

## Task 5: Strategy Orchestration — Depth Mode, Coverage, Per-Scenario NB

**Files:**
- Modify: `geosite/s6_strategy/models.py` (full rewrite below)
- Modify: `geosite/s6_strategy/strategy.py` (full rewrite below)
- Test: `tests/test_s6_precision.py` (create)

**Interfaces:**
- Consumes: `size_borefield_for_depth` (Task 4), `compute_ldc` coverage keys (Task 1), `extract_one_sided_pulses(profile, mode, ignore_top_pct)` (Task 3)
- Produces: `run_strategy(building_type, climate_zone, k, alpha, T_g, B, NB=None, H_target=125.0, A=1.0, ldc_cutoff_pct=10.0, ignore_top_pct=0.0, imbalance_threshold=1.25, floor_area_m2=None, year_factor=1.0, state=None, **sizing_params) -> StrategyResult`. Note `NB` moved after `B` and is now optional — all existing callers (app.py, tests) pass keywords, so this is safe. New `StrategyResult` fields consumed by Task 6/7: `NB_before: int`, `NB_after: int`, `H_target: float | None`, `ignore_top_pct: float`, `gshp_energy_pct: float`, `gshp_hours_pct: float`, `peaker_annual_kWh: float`. Field `NB` is kept and equals `NB_before` for backward compatibility (dev.html reads it).

**Peaker audit (documented conclusion, do not change the formula):** rated capacity = max hourly excess above `cutoff_W`, computed from the FULL profile even when `ignore_top_pct > 0` — the hours excluded from borefield sizing are exactly the hours the peaker must cover. Units: W − W → /1000.0 → kW. Correct.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s6_precision.py`:

```python
"""Precision-upgrade integration tests: depth-primary mode, coverage metrics,
ignore_top_pct, and peaker unit consistency.

Denver Medium Office 5B reference values (prototype scale):
max cooling +419.2 kW, min heating -172.8 kW, cutoff_W ~122.4 kW at 10%.
"""

import math
import pytest
from geosite.s6_strategy import run_strategy

_DENVER = dict(
    building_type="medium_office",
    climate_zone="5B",
    k=2.0, alpha=0.1, T_g=12.0,
    B=6.0, A=1.0,
    state="CO",
)

_CHICAGO_FIXED_NB = dict(
    building_type="small_office",
    climate_zone="5A",
    k=2.0, alpha=0.1, T_g=12.0,
    NB=16, B=6.0, A=1.0,
    state="IL",
)


@pytest.fixture(scope="module")
def denver():
    return run_strategy(**_DENVER)


def test_depth_mode_derives_borehole_counts(denver):
    assert denver.NB_before >= 1
    assert denver.NB_after >= 1
    assert denver.NB_after <= denver.NB_before
    assert denver.NB == denver.NB_before


def test_depth_mode_respects_target_depth(denver):
    assert denver.H_target == 125.0
    assert denver.H_before <= 125.0 + 1e-6
    assert denver.H_after <= 125.0 + 1e-6
    assert denver.NB_before == math.ceil(denver.L_before / 125.0)


def test_denver_cutoff_matches_reference(denver):
    assert denver.cutoff_W == pytest.approx(122_400.0, rel=0.02)


def test_denver_peaker_kw_units_consistent(denver):
    # Cooling-dominant: peaker = (max cooling W - cutoff W)/1000 kW
    # Reference: (419200 - 122400)/1000 = 296.8 kW
    assert denver.peaker_cool_kW == pytest.approx(296.8, rel=0.05)
    max_cool_W = max(h for h in denver.hourly_profile)
    expected_kW = (max_cool_W - denver.cutoff_W) / 1000.0
    assert denver.peaker_cool_kW == pytest.approx(expected_kW, rel=1e-9)


def test_denver_hours_coverage_is_90pct(denver):
    assert denver.gshp_hours_pct == pytest.approx(90.0, abs=0.01)


def test_denver_energy_coverage_exceeds_hours_coverage(denver):
    assert denver.gshp_hours_pct < denver.gshp_energy_pct < 100.0
    assert denver.peaker_annual_kWh > 0


def test_ignore_top_pct_shrinks_borefield():
    base = run_strategy(**_DENVER)
    trimmed = run_strategy(**_DENVER, ignore_top_pct=0.4)
    assert abs(trimmed.q_h_before) <= abs(base.q_h_before)
    assert trimmed.L_before <= base.L_before
    # Peaker still sized from the full profile extreme
    assert trimmed.peaker_kW == pytest.approx(base.peaker_kW, rel=1e-9)


def test_fixed_nb_mode_is_backward_compatible():
    r = run_strategy(**_CHICAGO_FIXED_NB)
    assert r.NB_before == 16
    assert r.NB_after == 16
    assert r.H_target is None
    assert r.H_before == pytest.approx(r.L_before / 16)


def test_to_dict_has_new_keys():
    d = run_strategy(**_CHICAGO_FIXED_NB).to_dict()
    for key in ("gshp_energy_pct", "gshp_hours_pct", "peaker_annual_kWh",
                "NB_before", "NB_after", "H_target", "ignore_top_pct"):
        assert key in d, f"Missing key: {key}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_precision.py -v`
Expected: FAIL — `run_strategy() missing 1 required positional argument: 'NB'` and/or `TypeError` on new keywords

- [ ] **Step 3: Rewrite `geosite/s6_strategy/models.py`**

Replace the entire file with:

```python
from dataclasses import dataclass


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
    gshp_energy_pct: float       # % of annual ground-load energy served by GSHP
    gshp_hours_pct: float        # % of hours the GSHP serves without the peaker
    peaker_annual_kWh: float     # annual ground-side energy supplied by peaker

    # Peaker
    peaker_kW: float             # supplemental unit rated capacity (max excess)
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
    NB_before: int               # borehole count without peaker
    L_after: float               # borefield with trimmed load (m)
    H_after: float               # depth per borehole with trimmed load (m)
    NB_after: int                # borehole count with trimmed load
    NB: int                      # = NB_before (backward compatibility)
    H_target: float | None       # target depth in depth-primary mode; None if NB was fixed
    ignore_top_pct: float        # ASHRAE-style peak exclusion used for q_h

    # Cost — before and after (dicts from estimate_cost)
    cost_before: dict
    cost_after: dict

    # Profiles for visualization (8760 floats each)
    hourly_profile: list         # original ground load (W)
    hourly_trimmed: list         # trimmed ground load (W)

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "imbalance_ratio": round(min(self.imbalance_ratio, 9999.0), 3),
            "dominant_mode": self.dominant_mode,
            "L_h": round(self.L_h, 1),
            "L_c": round(self.L_c, 1),
            "ldc_cutoff_pct": self.ldc_cutoff_pct,
            "cutoff_W": round(self.cutoff_W, 1),
            "gshp_energy_pct": round(self.gshp_energy_pct, 1),
            "gshp_hours_pct": round(self.gshp_hours_pct, 1),
            "peaker_annual_kWh": round(self.peaker_annual_kWh, 1),
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
            "NB_before": self.NB_before,
            "L_after": round(self.L_after),
            "H_after": round(self.H_after),
            "NB_after": self.NB_after,
            "NB": self.NB,
            "H_target": self.H_target,
            "ignore_top_pct": self.ignore_top_pct,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "hourly_profile": [round(v, 2) for v in self.hourly_profile],
            "hourly_trimmed": [round(v, 2) for v in self.hourly_trimmed],
        }
```

- [ ] **Step 4: Rewrite `geosite/s6_strategy/strategy.py`**

Replace the entire file with:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
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


def run_strategy(
    building_type: str,
    climate_zone: str,
    k: float,
    alpha: float,
    T_g: float,
    B: float,
    NB: int | None = None,
    H_target: float = 125.0,
    A: float = 1.0,
    ldc_cutoff_pct: float = 10.0,
    ignore_top_pct: float = 0.0,
    imbalance_threshold: float = 1.25,
    floor_area_m2=None,
    year_factor: float = 1.0,
    state=None,
    **sizing_params,
) -> StrategyResult:
    """Run mandatory hybrid GSHP strategy analysis.

    Sizing mode: NB=None (default) is depth-primary — the borehole count is
    derived as ceil(L / H_target) per scenario, so the before/after cases can
    have different counts. Passing an explicit NB preserves the legacy
    fixed-count behavior (H = L / NB) exactly.

    Peaker rated capacity is the MAX hourly excess above the LDC cutoff, not
    the mean: the peaker must meet the worst instantaneous shortfall or the
    building has unmet load at design conditions. It is computed from the
    FULL profile even when ignore_top_pct > 0 — the hours excluded from
    borefield sizing are exactly the hours the peaker must cover. The annual
    peaker energy (kWh) is reported separately for economics.
    """
    adv = {k_: sizing_params.get(k_, v) for k_, v in _ADVANCED_DEFAULTS.items()}

    def _sized(q_h, q_m, q_y, mode):
        """Return (L, NB, H) for one three-pulse scenario."""
        common = dict(q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g,
                      T_in_HP=_T_IN_HP[mode], **adv)
        if NB is not None:
            L = float(size_borefield(**common, B=B, NB=NB, A=A))
            return L, NB, L / NB
        return size_borefield_for_depth(**common, B=B, A=A, H_target=H_target)

    # --- Load and scale 8760h profile ---
    raw_profile = load_hourly_profile(building_type, climate_zone)
    scale = year_factor
    if floor_area_m2 is not None:
        proto_area = _PROTOTYPE_AREAS_M2.get(building_type, 1.0)
        scale *= floor_area_m2 / proto_area
    profile = scale_profile(raw_profile, scale)

    # --- Separate heating/cooling sizing to detect imbalance ---
    q_h_heat, q_m_heat, q_y_heat = extract_one_sided_pulses(profile, "heating", ignore_top_pct)
    q_h_cool, q_m_cool, q_y_cool = extract_one_sided_pulses(profile, "cooling", ignore_top_pct)

    L_h = _sized(q_h_heat, q_m_heat, q_y_heat, "heating")[0] if q_h_heat < 0 else 0.0
    L_c = _sized(q_h_cool, q_m_cool, q_y_cool, "cooling")[0] if q_h_cool > 0 else 0.0

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

    trim_mode = dominant_mode if case == 1 else "balanced"

    # --- Peaker sizing: max excess above cutoff, full profile, W -> kW ---
    peaker_heat_kW = max(
        (abs(h) - cutoff_W for h in profile if h < 0 and abs(h) > cutoff_W), default=0.0
    ) / 1000.0
    peaker_cool_kW = max(
        (h - cutoff_W for h in profile if h > 0 and h > cutoff_W), default=0.0
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

    # --- Before sizing: use dominant mode's original three-pulse ---
    if dominant_mode in ("heating", "balanced") and L_h >= L_c:
        q_h_before, q_m_before, q_y_before = q_h_heat, q_m_heat, q_y_heat
        before_mode = "heating"
    else:
        q_h_before, q_m_before, q_y_before = q_h_cool, q_m_cool, q_y_cool
        before_mode = "cooling"

    L_before, NB_before, H_before = _sized(q_h_before, q_m_before, q_y_before, before_mode)

    # --- Trim profile + re-derive three-pulse (pinned to before_mode) ---
    trimmed = trim_profile(profile, cutoff_W, trim_mode)
    q_h_trimmed, q_m_trimmed, q_y_trimmed = extract_one_sided_pulses(trimmed, before_mode, ignore_top_pct)

    L_after, NB_after, H_after = _sized(q_h_trimmed, q_m_trimmed, q_y_trimmed, before_mode)

    # --- Cost before/after (each scenario uses its own borehole count) ---
    def _cost(L_m: float, nb: int) -> dict:
        res = estimate_cost(L_m=L_m, NB=nb, B_m=B, state=state)
        base = res["base"]
        return {
            "total_usd": round(base.total_usd, 2),
            "cost_per_ft": round(base.cost_per_ft, 2),
            "scenario": "base",
        }

    cost_before = _cost(L_before, NB_before)
    cost_after = _cost(L_after, NB_after)

    return StrategyResult(
        case=case,
        imbalance_ratio=imbalance_ratio,
        dominant_mode=dominant_mode,
        L_h=L_h,
        L_c=L_c,
        ldc_cutoff_pct=ldc_cutoff_pct,
        cutoff_W=cutoff_W,
        gshp_energy_pct=ldc["gshp_energy_pct"],
        gshp_hours_pct=ldc["gshp_hours_pct"],
        peaker_annual_kWh=ldc["peaker_energy_Wh"] / 1000.0,
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
        NB_before=NB_before,
        L_after=L_after,
        H_after=H_after,
        NB_after=NB_after,
        NB=NB_before,
        H_target=None if NB is not None else H_target,
        ignore_top_pct=ignore_top_pct,
        cost_before=cost_before,
        cost_after=cost_after,
        hourly_profile=profile,
        hourly_trimmed=trimmed,
    )
```

- [ ] **Step 5: Run the new tests and the existing s6 suite**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_precision.py tests/test_s6_strategy.py tests/test_s6_ldc.py -v`
Expected: all PASS. `tests/test_s6_strategy.py` passes `NB=16` via `_CHICAGO_PARAMS`, exercising the legacy path unchanged.

- [ ] **Step 6: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add geosite/s6_strategy/strategy.py geosite/s6_strategy/models.py tests/test_s6_precision.py
git commit -m "feat(s6): depth-primary strategy with coverage metrics and per-scenario NB"
```

---

## Task 6: API Wiring — `/api/strategy` and `/calculate/smart`

**Files:**
- Modify: `app.py` (`strategy_api` at ~line 618; `calculate_smart` at ~line 132; imports at line 10)
- Test: `tests/test_api_depth.py` (create)

**Interfaces:**
- Consumes: `run_strategy` (Task 5 signature), `size_borefield_for_depth` (Task 4)
- Produces:
  - `POST /api/strategy` — `NB` becomes optional; new optional body fields `H_target` (float, default 125.0, valid 30–300) and `ignore_top_pct` (float, default 0.0, valid 0–5). Response gains keys `NB_before`, `NB_after`, `H_target`, `ignore_top_pct`, `gshp_energy_pct`, `gshp_hours_pct`, `peaker_annual_kWh` (all from `to_dict`).
  - `POST /calculate/smart` — `NB` becomes optional; new optional `H_target` (same default/range). When `NB` omitted, response `NB` is the derived count of the governing pass and response gains `"H_target": 125.0`; when `NB` supplied, behavior is byte-identical to today and `"H_target"` is `null`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_depth.py`:

```python
"""API tests for depth-primary sizing and precision parameters."""

import json
from unittest.mock import patch, MagicMock
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_geocode_mocks(geoid: str) -> list[MagicMock]:
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None
    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    tract_resp.raise_for_status.return_value = None
    return [zip_resp, tract_resp]


_STRATEGY_BASE = {
    "building_type": "small_office",
    "climate_zone": "5A",
    "k": 2.0, "alpha": 0.1, "T_g": 12.0,
    "B": 6.0, "A": 1.0,
    "state": "IL",
}


def test_strategy_without_nb_uses_depth_mode(client):
    resp = client.post("/api/strategy", data=json.dumps(_STRATEGY_BASE),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["H_target"] == 125.0
    assert data["NB_before"] >= 1
    assert data["H_before"] <= 125
    assert "gshp_energy_pct" in data


def test_strategy_with_nb_stays_legacy(client):
    body = dict(_STRATEGY_BASE, NB=16)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["NB_before"] == 16
    assert data["NB_after"] == 16
    assert data["H_target"] is None


def test_strategy_rejects_out_of_range_h_target(client):
    body = dict(_STRATEGY_BASE, H_target=1000)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400


def test_strategy_rejects_out_of_range_ignore_top_pct(client):
    body = dict(_STRATEGY_BASE, ignore_top_pct=50)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400


def test_strategy_accepts_ignore_top_pct(client):
    body = dict(_STRATEGY_BASE, ignore_top_pct=0.4)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json()["ignore_top_pct"] == 0.4


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_without_nb_derives_count(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601",
            "building_type": "small_office",
            "B": 6.0,
            "A": 1.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["NB"] >= 1
    assert data["H"] <= 125
    assert data["H_target"] == 125.0


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_with_nb_stays_legacy(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601",
            "building_type": "small_office",
            "NB": 16, "B": 6.0, "A": 1.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["NB"] == 16
    assert data["H_target"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_api_depth.py -v`
Expected: FAILs — `/api/strategy` without NB returns 400 (`'NB' is required`); `/calculate/smart` without NB returns 400; `H_target` key missing.

- [ ] **Step 3: Update the import in `app.py`**

Replace line 10:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
```

with:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth
```

- [ ] **Step 4: Update `strategy_api` in `app.py`**

In `strategy_api`, replace this block:

```python
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
```

with:

```python
    for field in ("building_type", "climate_zone", "k", "alpha", "T_g", "B", "A"):
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
        B     = float(data["B"])
        A     = float(data["A"])
        NB    = None
        if "NB" in data and str(data["NB"]).strip() != "":
            NB = int(data["NB"])
        H_target = float(data.get("H_target", 125.0))
        ignore_top_pct = float(data.get("ignore_top_pct", 0.0))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "field", "message": str(exc)}), 400

    if not (30.0 <= H_target <= 300.0):
        return jsonify({"error": "field", "field": "H_target",
                        "message": "H_target must be between 30 and 300 m"}), 400
    if not (0.0 <= ignore_top_pct <= 5.0):
        return jsonify({"error": "field", "field": "ignore_top_pct",
                        "message": "ignore_top_pct must be between 0 and 5 %"}), 400

    ldc_cutoff_pct      = float(data.get("ldc_cutoff_pct", 10.0))
    imbalance_threshold = float(data.get("imbalance_threshold", 1.25))
```

and update the `run_strategy(...)` call in the same function from:

```python
        result = run_strategy(
            building_type=building_type,
            climate_zone=climate_zone,
            k=k, alpha=alpha, T_g=T_g,
            NB=NB, B=B, A=A,
            ldc_cutoff_pct=ldc_cutoff_pct,
```

to:

```python
        result = run_strategy(
            building_type=building_type,
            climate_zone=climate_zone,
            k=k, alpha=alpha, T_g=T_g,
            NB=NB, B=B, A=A,
            H_target=H_target,
            ignore_top_pct=ignore_top_pct,
            ldc_cutoff_pct=ldc_cutoff_pct,
```

(rest of the call unchanged).

- [ ] **Step 5: Update `calculate_smart` in `app.py`**

5a. Replace the required-fields block:

```python
    # --- validate required fields ---
    required = {"zip_code": str, "building_type": str,
                "NB": int, "B": float, "A": float}
    for field, _ in required.items():
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    zip_code = str(data["zip_code"]).strip()
    building_type = str(data["building_type"]).strip()
    NB = int(data["NB"])
    B = float(data["B"])
    A = float(data["A"])
```

with:

```python
    # --- validate required fields ---
    for field in ("zip_code", "building_type", "B", "A"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    zip_code = str(data["zip_code"]).strip()
    building_type = str(data["building_type"]).strip()
    B = float(data["B"])
    A = float(data["A"])

    # NB fixed-count mode is legacy; depth-primary (H_target) is the default
    NB = None
    if "NB" in data and str(data["NB"]).strip() != "":
        try:
            NB = int(data["NB"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "NB",
                            "message": "NB must be an integer"}), 400
    try:
        H_target = float(data.get("H_target", 125.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_target",
                        "message": "H_target must be a number"}), 400
    if not (30.0 <= H_target <= 300.0):
        return jsonify({"error": "field", "field": "H_target",
                        "message": "H_target must be between 30 and 300 m"}), 400
```

5b. Replace the NB validation:

```python
    if NB < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "NB must be >= 1"}), 400
    if A < 1:
```

with:

```python
    if NB is not None and NB < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "NB must be >= 1"}), 400
    if A < 1:
```

5c. Replace the two-pass sizing block (from `try:` after the `_has_both` line through `return jsonify({"error": "calculation", ...}), 500`):

```python
    try:
        if _has_both:
            T_heat = float(data.get("T_in_HP_heat", _T_IN_HP_DEFAULTS["heating"]))
            T_cool = float(data.get("T_in_HP_cool", _T_IN_HP_DEFAULTS["cooling"]))
            if NB is not None:
                L_heat = size_borefield(
                    q_h=loads.q_h_heat, q_m=loads.q_m_heat, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_heat, B=B, NB=NB, A=A, **params,
                )
                L_cool = size_borefield(
                    q_h=loads.q_h_cool, q_m=loads.q_m_cool, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_cool, B=B, NB=NB, A=A, **params,
                )
                governing = "heating" if L_heat >= L_cool else "cooling"
                L = max(L_heat, L_cool)
                NB_out, H = NB, max(L_heat, L_cool) / NB
            else:
                L_heat, NB_h, H_h = size_borefield_for_depth(
                    q_h=loads.q_h_heat, q_m=loads.q_m_heat, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_heat, B=B, A=A, H_target=H_target, **params,
                )
                L_cool, NB_c, H_c = size_borefield_for_depth(
                    q_h=loads.q_h_cool, q_m=loads.q_m_cool, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_cool, B=B, A=A, H_target=H_target, **params,
                )
                governing = "heating" if L_heat >= L_cool else "cooling"
                L, NB_out, H = ((L_heat, NB_h, H_h) if governing == "heating"
                                else (L_cool, NB_c, H_c))
        else:
            T_in_HP = float(data.get("T_in_HP", _T_IN_HP_DEFAULTS[mode]))
            L_heat = None
            L_cool = None
            governing = mode
            if NB is not None:
                L = size_borefield(
                    q_h=loads.q_h, q_m=loads.q_m, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_in_HP, B=B, NB=NB, A=A, **params,
                )
                NB_out, H = NB, L / NB
            else:
                L, NB_out, H = size_borefield_for_depth(
                    q_h=loads.q_h, q_m=loads.q_m, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    T_in_HP=T_in_HP, B=B, A=A, H_target=H_target, **params,
                )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500
```

5d. Replace the response top-level keys:

```python
    return jsonify({
        "L": round(L),
        "H": round(L / NB),
        "NB": NB,
        "governing": governing,
```

with:

```python
    return jsonify({
        "L": round(L),
        "H": round(H),
        "NB": NB_out,
        "H_target": None if NB is not None else H_target,
        "governing": governing,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_api_depth.py tests/test_pipeline_integration.py tests/test_s5_api.py tests/test_s6_strategy.py -v`
Expected: all PASS (existing integration tests send `NB`, so they exercise the unchanged legacy path)

- [ ] **Step 7: Run the full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_api_depth.py
git commit -m "feat(api): H_target + ignore_top_pct on /api/strategy and /calculate/smart"
```

---

## Task 7: UI Wiring — Depth Input, Coverage Display, Peak-Exclusion Control

**Files:**
- Modify: `templates/index.html` (s4 geometry card ~lines 133–158; advanced details ~lines 161–179; s6 section ~lines 286–313)
- Modify: `static/main.js` (smart submit handler ~lines 87–252; `fetchStrategy` ~lines 486–543)

**Interfaces:**
- Consumes: Task 6's API contract (`H_target`, `ignore_top_pct`, response `NB`, `NB_before`, `NB_after`, `gshp_energy_pct`, `gshp_hours_pct`, `peaker_annual_kWh`)
- Produces: DOM ids used later by the UI-redesign plan: `s_H_target` (replaces `s_NB`), `s_ignore_top_pct`, `s6-coverage`. Manual Mode is untouched (it mirrors the reference spreadsheet, which is NB-based).

Note for the executor: the companion plan `2026-07-06-ui-redesign.md` restyles these same sections. This plan must be executed FIRST; keep the markup minimal here and do not add inline styling beyond what is shown.

- [ ] **Step 1: Replace the borehole-count input with a target-depth input**

In `templates/index.html`, replace:

```html
          <div class="field">
            <label for="s_NB">Number of boreholes</label>
            <div class="input-row">
              <input type="number" id="s_NB" name="s_NB" min="1" value="16">
              <span class="unit">—</span>
            </div>
            <span class="field-error" data-for="s_NB"></span>
          </div>
```

with:

```html
          <div class="field">
            <label for="s_H_target">Target borehole depth <span class="hint-inline">(typical 100–150 m — borehole count is derived)</span></label>
            <div class="input-row">
              <input type="number" id="s_H_target" name="s_H_target" min="30" max="300" step="1" value="125">
              <span class="unit">m</span>
            </div>
            <span class="field-error" data-for="s_H_target"></span>
          </div>
```

- [ ] **Step 2: Add the peak-exclusion control to Advanced overrides**

In `templates/index.html`, inside `<details class="advanced-details">`, after the `s_mfls` field's closing `</div>` (the one closing its `.field`), add:

```html
            <div class="field">
              <label for="s_ignore_top_pct">Ignore top design hours <span class="hint-inline">(ASHRAE 99.6% percentile — applies to hybrid strategy sizing)</span></label>
              <div class="input-row">
                <select id="s_ignore_top_pct" name="s_ignore_top_pct">
                  <option value="0" selected>0% — size to the absolute peak hour</option>
                  <option value="0.2">0.2% — ignore top ~18 hours</option>
                  <option value="0.4">0.4% — ignore top ~35 hours (ASHRAE 99.6%)</option>
                </select>
              </div>
            </div>
```

- [ ] **Step 3: Add the coverage line to the s6 section**

In `templates/index.html`, immediately after `<div style="position:relative;height:180px"><canvas id="s6-chart-a"></canvas></div>` (inside `#s6-section`), add:

```html
          <div id="s6-coverage" style="margin-top:10px;font-size:12px;color:var(--text-muted)"></div>
```

- [ ] **Step 4: Update `static/main.js` for the new inputs**

4a. In `clearSmartErrors()`, replace:

```js
    ['zip_code', 'building_type', 's_NB', 's_B', 's_A'].forEach(clearFieldError);
```

with:

```js
    ['zip_code', 'building_type', 's_H_target', 's_B', 's_A'].forEach(clearFieldError);
```

4b. In the smart submit handler, replace:

```js
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      NB:              parseFloat(document.getElementById('s_NB').value),
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      soil_confidence: document.getElementById('soil_confidence').value,
    };
```

with:

```js
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      H_target:        parseFloat(document.getElementById('s_H_target').value) || 125,
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      soil_confidence: document.getElementById('soil_confidence').value,
    };
```

4c. Replace the field remap:

```js
        const fieldMap = { NB: 's_NB', B: 's_B', A: 's_A' };
```

with:

```js
        const fieldMap = { H_target: 's_H_target', B: 's_B', A: 's_A' };
```

4d. In `fetchStrategy`, replace:

```js
    const payload = {
      building_type: smartRes.building_type,
      climate_zone:  smartRes.site.climate_zone,
      k:             smartRes.site.k_effective ?? smartRes.site.k,
      alpha:         smartRes.site.alpha,
      T_g:           smartRes.site.T_g,
      NB:            smartRes.NB,
      B:             costState.B,
      A:             costState.A,
      state:         smartRes.site.state_abbrev,
      floor_area_m2: smartRes.loads.floor_area_m2 || null,
      year_factor:   smartRes.loads.year_factor || 1.0,
    };
```

with:

```js
    const payload = {
      building_type:  smartRes.building_type,
      climate_zone:   smartRes.site.climate_zone,
      k:              smartRes.site.k_effective ?? smartRes.site.k,
      alpha:          smartRes.site.alpha,
      T_g:            smartRes.site.T_g,
      H_target:       parseFloat(document.getElementById('s_H_target').value) || 125,
      ignore_top_pct: parseFloat(document.getElementById('s_ignore_top_pct').value) || 0,
      B:              costState.B,
      A:              costState.A,
      state:          smartRes.site.state_abbrev,
      floor_area_m2:  smartRes.loads.floor_area_m2 || null,
      year_factor:    smartRes.loads.year_factor || 1.0,
    };
```

4e. Still in `fetchStrategy`, replace the before/after card population:

```js
    document.getElementById('s6-before-L').textContent = `${res.L_before.toLocaleString()} m`;
    document.getElementById('s6-before-cost').textContent =
      `$${(res.cost_before.total_usd / 1000).toFixed(0)}k base`;
    document.getElementById('s6-after-L').textContent = `${res.L_after.toLocaleString()} m`;
    document.getElementById('s6-after-cost').textContent =
      `$${(res.cost_after.total_usd / 1000).toFixed(0)}k base`;
```

with:

```js
    document.getElementById('s6-before-L').textContent = `${res.L_before.toLocaleString()} m`;
    document.getElementById('s6-before-cost').textContent =
      `$${(res.cost_before.total_usd / 1000).toFixed(0)}k base · ${res.NB_before} boreholes`;
    document.getElementById('s6-after-L').textContent = `${res.L_after.toLocaleString()} m`;
    document.getElementById('s6-after-cost').textContent =
      `$${(res.cost_after.total_usd / 1000).toFixed(0)}k base · ${res.NB_after} boreholes`;
```

4f. After the `_renderS6ChartA(...)` call at the end of `fetchStrategy`, add:

```js
    const cov = document.getElementById('s6-coverage');
    if (cov && res.gshp_energy_pct != null) {
      cov.textContent =
        `GSHP alone serves ${res.gshp_hours_pct.toFixed(1)}% of hours and ` +
        `${res.gshp_energy_pct.toFixed(1)}% of annual ground-load energy; ` +
        `the peaker supplies the remaining ${(100 - res.gshp_energy_pct).toFixed(1)}% ` +
        `(${Math.round(res.peaker_annual_kWh).toLocaleString()} kWh/yr).`;
    }
```

- [ ] **Step 5: Verify the backend contract end-to-end**

Run: `source venv/bin/activate && python -m pytest tests/ -v`
Expected: all PASS

Then start the app and hit the new endpoints:

```bash
source venv/bin/activate && flask --app app run --port 5000 &
sleep 2
curl -s -X POST http://127.0.0.1:5000/api/strategy \
  -H 'Content-Type: application/json' \
  -d '{"building_type":"medium_office","climate_zone":"5B","k":2.0,"alpha":0.1,"T_g":12.0,"B":6.0,"A":1.0,"H_target":125,"ignore_top_pct":0.4,"state":"CO"}' \
  | python -c "import json,sys; d=json.load(sys.stdin); print({k: d[k] for k in ('NB_before','NB_after','H_before','H_after','H_target','gshp_energy_pct','gshp_hours_pct','peaker_kW','peaker_annual_kWh','ignore_top_pct')})"
kill %1
```

Expected: printed dict with `H_before <= 125`, `NB_after <= NB_before`, `gshp_energy_pct` between 90 and 100, `ignore_top_pct: 0.4`.

- [ ] **Step 6: Manual browser check**

Run `source venv/bin/activate && flask --app app run --port 5000`, open `http://127.0.0.1:5000`, enter ZIP `60601` + Medium Office, click Calculate. Confirm: the geometry card shows "Target borehole depth" with 125; the result panel shows a derived borehole count; the s6 section shows the coverage sentence and per-scenario borehole counts. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/main.js
git commit -m "feat(ui): depth-first input, coverage display, peak-exclusion control"
```

---

## Self-Review Notes

- Spec coverage: (1) kWh coverage — Task 1 + surfaced in Tasks 5/6/7; (2) depth-primary input — Tasks 4/5/6/7; (3) peaker audit — documented in File Map audit + `run_strategy` docstring + pinned by `test_denver_peaker_kw_units_consistent`; (4) ASHRAE 99.6% — Tasks 3/5/6/7; (5) other issues — net q_y fix (Task 2), MONTH_HOURS dedup (Task 2), month boundaries verified correct (no change needed).
- Type consistency: `size_borefield_for_depth` returns `(float, int, float)` everywhere it is consumed (Tasks 5, 6); `extract_one_sided_pulses` third parameter is positional-compatible in every call site shown.
- Known intentional limitation: `ignore_top_pct` applies only to the strategy path (s6), because `/calculate/smart` reads pre-aggregated annual pulses from `prototype_loads.json` and has no hourly profile for most building types. The UI hint states this.

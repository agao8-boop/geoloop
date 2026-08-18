# Auto-NB Range from Building Footprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "user types NB or leaves it blank" approach with a geometry-driven borehole-count range derived from the building footprint: estimate the footprint from floor area ÷ DOE prototype floor count, bound NB between one line of boreholes along the short side (NB_min) and a full perimeter ring (NB_max), then pick the NB in that range that minimizes total drilled length L subject to a minimum-depth constraint H = L/NB ≥ H_min. `/calculate/smart` finally works with NB blank (today it returns 400 despite the UI saying "leave blank to auto-compute").

**Architecture:** A new pure-computation module `geosite/s4_sizing/footprint.py` owns the floor-count table, the full 12-type prototype-area table, `compute_nb_range()` (geometry only), and `find_optimal_nb()` (sweeps NB over the range calling the validated `size_borefield`). The depth-primary fixed-point `size_borefield_for_depth()` from the unexecuted methodology-precision plan is a **prerequisite** and is bundled here as Task 1 — `find_optimal_nb` uses it as the fallback when the load is too small for any footprint-range NB to reach H_min. `run_strategy` and `/calculate/smart` swap their rough one-pass NB estimates for the footprint search; passing an explicit `NB` (Python or HTTP) preserves today's fixed-count behavior exactly, so every existing test keeps passing.

**Tech Stack:** Python 3.11 (venv at `./venv`), Flask, numpy, pytest; vanilla JS frontend (`static/main.js`, `templates/index.html`).

## Global Constraints

- Run tests with: `source venv/bin/activate && python -m pytest tests/ -v` (from repo root `/Users/agao/Downloads/CEE299/geosite_advisor`). Baseline: 219 passing, 5 pre-existing failures (missing directories, unrelated) — do not fix or worsen those 5.
- Ground load sign convention: **positive = cooling (heat injection into ground), negative = heating (heat extraction from ground)**
- Do NOT modify `borehole_resistance`, `_g_poly`, `_peak_correction`, or the fixed-NB `size_borefield` iteration in `geosite/s4_sizing/ashrae_sizing.py` — validated against `data/reference/philippe_2010_sizing.xlsx` and must keep producing identical outputs
- `size_borefield()` signature (unchanged): `size_borefield(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B=None, NB=None, A=1.0, tol=1.0, max_iter=200) -> float`
- Advanced defaults (verbatim, already defined in `app.py` `_ADVANCED_DEFAULTS` and `strategy.py` `_ADVANCED_DEFAULTS`): `Cp=4200.0, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167, kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0`
- T_in_HP defaults: heating 5.0 °C, cooling 40.2 °C
- Footprint geometry constants: aspect ratio (long/short) fixed at **9.0** (`FOOTPRINT_ASPECT`); spacing defaults to 6.0 m and is the existing user-adjustable `s_B`/`B` value — the borefield spacing and the footprint-line spacing are the same number. The `A` parameter of the Tp polynomial stays an independent user input (its smart-mode default is already 9.0, deliberately matching the footprint aspect).
- `H_min` semantics: minimum acceptable depth per borehole inside the footprint search (default 125.0 m, valid API range 30–300). The depth-primary fallback (`size_borefield_for_depth`, ceil semantics, H ≤ target) is used only when NO footprint-range NB can satisfy H ≥ H_min — i.e. the load is small and fewer, deeper-than-target holes are impossible to avoid being shallow; in the fallback H may come out below H_min and callers surface that via `nb_opt < nb_min`.
- Backward compatibility: any call that passes an explicit `NB` (Python or HTTP) must behave exactly as before this plan (same L, same H = L/NB, same cost). Existing integration tests all pass `NB` and pin this.
- DOE prototype floor counts (bake verbatim into `BUILDING_FLOORS`): small_office 1, medium_office 3, large_office 12, standalone_retail 1, primary_school 1, secondary_school 2, hospital 5, outpatient_healthcare 3, small_hotel 4, large_hotel 6, warehouse 1, midrise_apartment 4
- DOE prototype areas m² (bake verbatim into `PROTOTYPE_AREAS_M2`): small_office 511, medium_office 4982, large_office 46320, standalone_retail 2294, primary_school 6871, secondary_school 19592, hospital 22422, outpatient_healthcare 3804, small_hotel 4014, large_hotel 11345, warehouse 4835, midrise_apartment 3135
- Physics rationale for the optimization (document in the `find_optimal_nb` docstring): L increases with NB because of the Tp inter-borehole interaction correction; H = L/NB decreases with NB. The minimum-L valid solution is therefore expected at the smallest valid NB, but the full range is swept anyway because the polynomial is not guaranteed monotone near the boundary. Worst case ≈ 77 candidates × ~23 Tp iterations — trivially fast.
- No comments in code unless the WHY is non-obvious

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `geosite/s4_sizing/ashrae_sizing.py` | Append `size_borefield_for_depth()` only (prerequisite, Task 1) |
| Create | `tests/test_s4_depth_sizing.py` | Fixed-point depth sizing behavior (Task 1) |
| Create | `geosite/s4_sizing/footprint.py` | `BUILDING_FLOORS`, `PROTOTYPE_AREAS_M2`, `compute_nb_range()`, `find_optimal_nb()` |
| Create | `tests/test_s4_footprint.py` | Geometry range math + optimizer invariants |
| Modify | `geosite/s6_strategy/strategy.py` | Replace rough 1-pass NB estimate with footprint search; full-table area fix |
| Modify | `geosite/s6_strategy/models.py` | `nb_min`/`nb_max` fields + `to_dict` keys |
| Modify | `app.py` | `/calculate/smart`: NB truly optional, `H_min` param, footprint wiring, new response keys |
| Create | `tests/test_api_footprint.py` | Smart endpoint with/without NB, range keys, validation |
| Modify | `templates/index.html` | s_NB moves to Advanced as an override; H_min relabel; NB-range display in result panel |
| Modify | `static/main.js` | Send `H_min`, populate range display, only forward user NB override to `/api/strategy` |
| Modify | `tests/test_ui_template.py` | Add `sres-NB-range` to `REQUIRED_IDS` |

**Audit results baked into this plan (from reading the current code):**
1. `/calculate/smart` lists `NB` in its `required` dict (app.py ~line 150) and returns 400 when it is blank — but `templates/index.html` labels `s_NB` "leave blank to auto-compute" and `static/main.js` omits `NB` when the field is empty. **Live bug:** blank NB in Smart Mode always errors. This plan fixes it.
2. `strategy.py` auto-computes NB with `NB = max(1, int(L_dom_ni / H_min))` plus one Tp refinement pass (lines 116–126) — a floor-division estimate, not a fixed point, and with no geometric grounding. Replaced by the footprint search.
3. `strategy.py` `_PROTOTYPE_AREAS_M2` has only 3 office types with `.get(building_type, 1.0)` — passing `floor_area_m2` for any of the other 9 building types silently scales the 8760h profile by `floor_area / 1.0` (thousands×). Task 4 fixes this by importing the full 12-type table from `footprint.py`.
4. `size_borefield_for_depth` does not exist (methodology-precision plan Task 4 was never executed). It is bundled here as Task 1 because `find_optimal_nb` needs it as the small-load fallback.
5. `templates/dev.html` trace runner always sends `NB: parseFloat(...)` which serializes to JSON `null` when blank; the new parse guard (`data.get("NB") not in (None, "")`) makes the dev trace's "auto" placeholder actually work with no dev.html change.

---

## Task 1: Prerequisite — Depth-Primary Fixed Point (`size_borefield_for_depth`)

> Lifted verbatim from the unexecuted `2026-07-06-methodology-precision.md` Task 4. If that plan has been executed by the time this one runs and the function already exists, verify the tests below pass and skip to Task 2.

**Files:**
- Modify: `geosite/s4_sizing/ashrae_sizing.py` (append new function only; do not touch existing functions)
- Test: `tests/test_s4_depth_sizing.py` (create)

**Interfaces:**
- Consumes: existing `size_borefield(...)`
- Produces: `size_borefield_for_depth(q_h, q_m, q_y, k, alpha, T_g, Cp, mfls, T_in_HP, rbore, rpin, rpext, kgrout, kpipe, LU, hconv, B, A=1.0, H_target=125.0, tol=1.0, max_nb_iter=25) -> tuple[float, int, float]` returning `(L, NB, H)`. Task 3's `find_optimal_nb` uses this as its fallback.

**Why iterate:** NB is an input to the Tp inter-borehole interaction polynomial, so you cannot just divide once. The loop finds the joint fixed point `NB = ceil(L / H_target)` with `L = size_borefield(..., NB=NB)` (2–4 iterations in practice). At the fixed point `H = L/NB ≤ H_target` by construction.

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

## Task 2: Footprint Geometry — `compute_nb_range`

**Files:**
- Create: `geosite/s4_sizing/footprint.py`
- Test: `tests/test_s4_footprint.py` (create)

**Interfaces:**
- Consumes: nothing (pure geometry)
- Produces: `BUILDING_FLOORS: dict[str, int]`, `PROTOTYPE_AREAS_M2: dict[str, float]`, `FOOTPRINT_ASPECT = 9.0`, and `compute_nb_range(floor_area_m2: float | None, building_type: str, spacing_m: float = 6.0) -> tuple[int, int, dict]` returning `(nb_min, nb_max, meta)`. Consumed by Tasks 3–5.

**Geometry (document in the docstring):** `footprint = floor_area / n_floors`; rectangular footprint at aspect 9 → `W = sqrt(footprint/9)`, `L = 9·W = 3·sqrt(footprint)`; `nb_min = ceil(W / spacing)` (one line along the SHORT side); `nb_max = floor(2·(L+W) / spacing)` (boreholes ringing the perimeter). `floor_area_m2=None` uses the DOE prototype area.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s4_footprint.py`:

```python
"""Footprint-driven NB range: geometry math and optimizer invariants."""

import math
import pytest

from geosite.s4_sizing.footprint import (
    BUILDING_FLOORS,
    PROTOTYPE_AREAS_M2,
    compute_nb_range,
)


def test_floor_table_covers_all_12_prototypes():
    assert set(BUILDING_FLOORS) == set(PROTOTYPE_AREAS_M2)
    assert len(BUILDING_FLOORS) == 12
    assert BUILDING_FLOORS["large_office"] == 12
    assert BUILDING_FLOORS["small_office"] == 1


def test_small_office_prototype_range():
    # footprint = 511/1; W = sqrt(511)/3 = 7.535 m; L = 3*sqrt(511) = 67.816 m
    # nb_min = ceil(7.535/6) = 2; perimeter = 150.70 m -> nb_max = floor(25.12) = 25
    nb_min, nb_max, meta = compute_nb_range(None, "small_office", spacing_m=6.0)
    assert nb_min == 2
    assert nb_max == 25
    assert meta["footprint_m2"] == pytest.approx(511.0)
    assert meta["n_floors"] == 1
    assert meta["width_m"] == pytest.approx(7.535, abs=0.01)
    assert meta["length_m"] == pytest.approx(9 * meta["width_m"])
    assert meta["prototype_area_used"] is True


def test_large_office_prototype_range():
    # footprint = 46320/12 = 3860; W = 20.710 m; L = 186.39 m
    # nb_min = ceil(20.710/6) = 4; perimeter = 414.19 m -> nb_max = 69
    nb_min, nb_max, meta = compute_nb_range(None, "large_office", spacing_m=6.0)
    assert nb_min == 4
    assert nb_max == 69
    assert meta["footprint_m2"] == pytest.approx(3860.0)


def test_medium_office_prototype_range():
    # footprint = 4982/3 = 1660.67; W = 13.584 m; nb_min = 3; nb_max = 45
    nb_min, nb_max, _ = compute_nb_range(None, "medium_office", spacing_m=6.0)
    assert (nb_min, nb_max) == (3, 45)


def test_user_area_overrides_prototype():
    # 1022 m2 small office: footprint 1022; W = 10.656 m -> nb_min 2;
    # L = 95.907; perimeter = 213.13 -> nb_max 35
    nb_min, nb_max, meta = compute_nb_range(1022.0, "small_office", spacing_m=6.0)
    assert (nb_min, nb_max) == (2, 35)
    assert meta["prototype_area_used"] is False


def test_tighter_spacing_expands_range():
    nb_min6, nb_max6, _ = compute_nb_range(None, "small_office", spacing_m=6.0)
    nb_min3, nb_max3, _ = compute_nb_range(None, "small_office", spacing_m=3.0)
    assert nb_min3 >= nb_min6
    assert nb_max3 > nb_max6
    assert (nb_min3, nb_max3) == (3, 50)


def test_nb_min_never_below_one_and_range_ordered():
    for bt in BUILDING_FLOORS:
        nb_min, nb_max, _ = compute_nb_range(None, bt, spacing_m=6.0)
        assert 1 <= nb_min <= nb_max


def test_unknown_building_type_raises():
    with pytest.raises(KeyError):
        compute_nb_range(None, "space_station")


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        compute_nb_range(-5.0, "small_office")
    with pytest.raises(ValueError):
        compute_nb_range(None, "small_office", spacing_m=0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_footprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geosite.s4_sizing.footprint'`

- [ ] **Step 3: Implement the module**

Create `geosite/s4_sizing/footprint.py`:

```python
"""Footprint-driven borehole count range.

The borefield is assumed to be placed in/around a rectangular building
footprint with aspect ratio 9 (long/short), the arrangement that maximizes
inter-borehole energy efficiency for a line-dominant field:
    footprint = floor_area / n_floors
    W = sqrt(footprint / 9),  L = 9 * W = 3 * sqrt(footprint)
    NB_min = one line of boreholes along the SHORT side  = ceil(W / spacing)
    NB_max = boreholes circling the full perimeter       = floor(2*(L+W) / spacing)

Floor counts are the DOE Commercial Prototype Building Models (90.1-2019)
story counts; areas are the prototype conditioned floor areas.
"""

import math

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

FOOTPRINT_ASPECT = 9.0

BUILDING_FLOORS = {
    "small_office":          1,
    "medium_office":         3,
    "large_office":          12,
    "standalone_retail":     1,
    "primary_school":        1,
    "secondary_school":      2,
    "hospital":              5,
    "outpatient_healthcare": 3,
    "small_hotel":           4,
    "large_hotel":           6,
    "warehouse":             1,
    "midrise_apartment":     4,
}

PROTOTYPE_AREAS_M2 = {
    "small_office":          511.0,
    "medium_office":         4982.0,
    "large_office":          46320.0,
    "standalone_retail":     2294.0,
    "primary_school":        6871.0,
    "secondary_school":      19592.0,
    "hospital":              22422.0,
    "outpatient_healthcare": 3804.0,
    "small_hotel":           4014.0,
    "large_hotel":           11345.0,
    "warehouse":             4835.0,
    "midrise_apartment":     3135.0,
}


def compute_nb_range(
    floor_area_m2: float | None,
    building_type: str,
    spacing_m: float = 6.0,
) -> tuple[int, int, dict]:
    """Return (nb_min, nb_max, meta) from the building footprint geometry.

    floor_area_m2=None uses the DOE prototype area for the building type.
    """
    if building_type not in BUILDING_FLOORS:
        raise KeyError(
            f"'{building_type}' not in footprint table. "
            f"Available: {sorted(BUILDING_FLOORS)}"
        )
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")

    prototype_area_used = floor_area_m2 is None
    area = PROTOTYPE_AREAS_M2[building_type] if prototype_area_used else float(floor_area_m2)
    if area <= 0:
        raise ValueError("floor_area_m2 must be positive")

    n_floors = BUILDING_FLOORS[building_type]
    footprint = area / n_floors
    width = math.sqrt(footprint / FOOTPRINT_ASPECT)
    length = FOOTPRINT_ASPECT * width
    perimeter = 2.0 * (length + width)

    nb_min = max(1, math.ceil(width / spacing_m))
    nb_max = max(nb_min, math.floor(perimeter / spacing_m))

    meta = {
        "footprint_m2": footprint,
        "n_floors": n_floors,
        "floor_area_m2": area,
        "width_m": width,
        "length_m": length,
        "perimeter_m": perimeter,
        "spacing_m": spacing_m,
        "aspect": FOOTPRINT_ASPECT,
        "prototype_area_used": prototype_area_used,
    }
    return nb_min, nb_max, meta
```

(`find_optimal_nb` is added in Task 3; the imports at the top are already in place for it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_footprint.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s4_sizing/footprint.py tests/test_s4_footprint.py
git commit -m "feat(s4): footprint-driven NB range from DOE floor counts"
```

---

## Task 3: NB Optimizer — `find_optimal_nb`

**Files:**
- Modify: `geosite/s4_sizing/footprint.py` (append)
- Test: `tests/test_s4_footprint.py` (append)

**Interfaces:**
- Consumes: `size_borefield` (fixed-NB, validated), `size_borefield_for_depth` (Task 1 fallback)
- Produces: `find_optimal_nb(nb_min, nb_max, q_h, q_m, q_y, k, alpha, T_g, H_min=125.0, B=6.0, A=1.0, **adv) -> tuple[int, float, float]` returning `(nb_opt, L_opt, H_opt)`. `**adv` carries `T_in_HP` plus the 9 advanced borehole/fluid parameters. Fallback is detectable by callers as `nb_opt < nb_min`. Consumed by Tasks 4–5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s4_footprint.py`:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import find_optimal_nb

_ADV = dict(
    Cp=4200.0, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167,
    kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0,
)
_GROUND = dict(k=2.0, alpha=0.086, T_g=15.0)
_BIG_COOL = dict(q_h=400_000.0, q_m=90_000.0, q_y=20_000.0, T_in_HP=40.2)
_SMALL_COOL = dict(q_h=12_000.0, q_m=6_000.0, q_y=1_500.0, T_in_HP=40.2)


def test_optimal_nb_within_range_and_meets_depth():
    nb, L, H = find_optimal_nb(4, 69, **_BIG_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert 4 <= nb <= 69
    assert H == pytest.approx(L / nb)
    assert H >= 125.0
    assert L > 0


def test_optimal_nb_minimizes_L_over_valid_range():
    nb, L, H = find_optimal_nb(4, 69, **_BIG_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    for cand in range(4, 70):
        L_c = float(size_borefield(**_BIG_COOL, **_GROUND, **_ADV,
                                   B=6.0, NB=cand, A=9.0))
        if L_c > 0 and L_c / cand >= 125.0:
            assert L <= L_c + 1e-9


def test_small_load_falls_back_to_depth_primary():
    # L0 ~ 152 m: even nb_min=2 gives H ~ 76 m < 125 -> no valid range NB
    nb, L, H = find_optimal_nb(2, 25, **_SMALL_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert nb < 2          # fallback signalled by nb_opt < nb_min
    assert nb >= 1
    assert L > 0
    assert H == pytest.approx(L / nb)


def test_nonbinding_constraint_returns_L0():
    # Strong ground, tiny injection at high T_in_HP -> L can be non-positive
    nb, L, H = find_optimal_nb(
        2, 25, q_h=100.0, q_m=50.0, q_y=-5_000.0, T_in_HP=40.2,
        **_GROUND, H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert nb == 1
    assert L <= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_footprint.py -v -k optimal_nb`
Expected: FAIL with `ImportError: cannot import name 'find_optimal_nb'`

- [ ] **Step 3: Implement the optimizer**

Append to `geosite/s4_sizing/footprint.py`:

```python
def find_optimal_nb(
    nb_min: int,
    nb_max: int,
    q_h: float,
    q_m: float,
    q_y: float,
    k: float,
    alpha: float,
    T_g: float,
    H_min: float = 125.0,
    B: float = 6.0,
    A: float = 1.0,
    **adv,
) -> tuple[int, float, float]:
    """Pick the NB in [nb_min, nb_max] that minimizes total drilled length L.

    Candidates must satisfy the minimum-depth constraint H = L/NB >= H_min
    (shallow holes waste mobilization cost and header pipe). L increases with
    NB via the Tp interaction correction and H decreases, so the minimum-L
    valid NB is expected at the low end — the full range is swept anyway
    because the Tp polynomial is not guaranteed monotone near the boundary.

    Fallback: when no range NB satisfies H >= H_min (small load), the field
    is smaller than one footprint line; depth-primary sizing with
    H_target=H_min decides NB instead (per the 2026-07-06 professor
    directive: depth is the primary input). Callers detect the fallback as
    nb_opt < nb_min. adv carries T_in_HP plus the 9 borehole/fluid params.

    Returns (nb_opt, L_opt, H_opt).
    """
    common = dict(q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g, **adv)

    L0 = float(size_borefield(**common))
    if L0 <= 0:
        return 1, L0, L0

    best = None
    for nb in range(nb_min, nb_max + 1):
        L = float(size_borefield(**common, B=B, NB=nb, A=A))
        if L <= 0:
            continue
        H = L / nb
        if H < H_min:
            continue
        if best is None or L < best[1]:
            best = (nb, L, H)
    if best is not None:
        return best

    L, nb, H = size_borefield_for_depth(**common, B=B, A=A, H_target=H_min)
    return nb, L, H
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s4_footprint.py tests/test_s4_depth_sizing.py tests/test_s4_sizing.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s4_sizing/footprint.py tests/test_s4_footprint.py
git commit -m "feat(s4): find_optimal_nb — minimum-L NB search with depth fallback"
```

---

## Task 4: Strategy Wiring — Footprint Search Replaces the Rough Estimate

**Files:**
- Modify: `geosite/s6_strategy/strategy.py`
- Modify: `geosite/s6_strategy/models.py`
- Test: `tests/test_s6_footprint.py` (create)

**Interfaces:**
- Consumes: `compute_nb_range`, `find_optimal_nb`, full `PROTOTYPE_AREAS_M2`
- Produces: `run_strategy` keeps its exact signature; when `NB=None` the borehole count now comes from the footprint search. `StrategyResult` gains `nb_min: int | None = None`, `nb_max: int | None = None` (None when NB was user-fixed) and `to_dict()` gains both keys. `/api/strategy` needs no change — it already treats NB as optional and forwards `H_min` (app.py line ~650/656).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s6_footprint.py`:

```python
"""Footprint-driven NB inside run_strategy."""

import pytest
from geosite.s6_strategy import run_strategy
from geosite.s4_sizing.footprint import compute_nb_range

_CHI = dict(
    building_type="small_office", climate_zone="5A",
    k=2.0, alpha=0.1, T_g=12.0, B=6.0, A=9.0, state="IL",
)


def test_auto_nb_comes_from_footprint_range():
    r = run_strategy(**_CHI)
    nb_min, nb_max, _ = compute_nb_range(None, "small_office", spacing_m=6.0)
    assert r.nb_min == nb_min
    assert r.nb_max == nb_max
    assert (nb_min <= r.NB <= nb_max) or r.NB < nb_min  # in-range or fallback
    assert r.NB >= 1


def test_explicit_nb_bypasses_footprint():
    r = run_strategy(**_CHI, NB=16)
    assert r.NB == 16
    assert r.nb_min is None
    assert r.nb_max is None
    assert r.H_before == pytest.approx(r.L_before / 16)


def test_to_dict_has_range_keys():
    d = run_strategy(**_CHI).to_dict()
    assert "nb_min" in d
    assert "nb_max" in d


def test_floor_area_scaling_uses_full_area_table():
    # hospital was missing from the old 3-entry table (scale blew up to
    # floor_area/1.0); at prototype area the scale must be ~1.0
    r_proto = run_strategy(**dict(_CHI, building_type="hospital"), NB=16)
    r_same = run_strategy(**dict(_CHI, building_type="hospital"), NB=16,
                          floor_area_m2=22422.0)
    assert r_same.L_before == pytest.approx(r_proto.L_before, rel=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_footprint.py -v`
Expected: FAIL — `AttributeError: 'StrategyResult' object has no attribute 'nb_min'` and the hospital area test fails on the huge mis-scale

- [ ] **Step 3: Add the fields to `geosite/s6_strategy/models.py`**

At the END of the `StrategyResult` dataclass field list (after `m2_H_after: float`), add:

```python
    # Footprint-derived NB range (None when NB was user-fixed)
    nb_min: int | None = None
    nb_max: int | None = None
```

In `to_dict()`, after the `"H_min": self.H_min,` line add:

```python
            "nb_min": self.nb_min,
            "nb_max": self.nb_max,
```

- [ ] **Step 4: Rewire `geosite/s6_strategy/strategy.py`**

4a. Replace the imports/constants at the top:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
```

with:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import (
    PROTOTYPE_AREAS_M2 as _PROTOTYPE_AREAS_M2,
    compute_nb_range,
    find_optimal_nb,
)
```

and DELETE the local 3-entry table line:

```python
_PROTOTYPE_AREAS_M2 = {"small_office": 511, "medium_office": 4982, "large_office": 46320}
```

4b. In `run_strategy`, the profile-scaling block currently reads `_PROTOTYPE_AREAS_M2.get(building_type, 1.0)`. Replace that line with:

```python
        proto_area = _PROTOTYPE_AREAS_M2.get(building_type, 1.0)
```

→

```python
        proto_area = _PROTOTYPE_AREAS_M2[building_type]
```

(KeyError here is correct — `load_hourly_profile` has already validated the type.)

4c. Replace the rough NB block:

```python
    # --- Compute NB from H_min (if not provided) ---
    if NB is None:
        L_dom_ni = max(L_h_ni, L_c_ni)
        NB = max(1, int(L_dom_ni / H_min))
        # One Tp-correction pass to refine NB
        if dominant_mode in ("heating", "balanced"):
            q_h_d, q_m_d, q_y_d, d_mode = q_h_heat, q_m_heat, q_y_heat, "heating"
        else:
            q_h_d, q_m_d, q_y_d, d_mode = q_h_cool, q_m_cool, q_y_cool, "cooling"
        L_corr = _do_size(q_h_d, q_m_d, q_y_d, k, alpha, T_g, d_mode, NB, B, A, adv)
        NB = max(1, int(L_corr / H_min))
```

with:

```python
    # --- Compute NB from the building footprint (if not provided) ---
    nb_min = nb_max = None
    if NB is None:
        nb_min, nb_max, _fp = compute_nb_range(floor_area_m2, building_type,
                                               spacing_m=B)
        if dominant_mode in ("heating", "balanced"):
            q_h_d, q_m_d, q_y_d, d_mode = q_h_heat, q_m_heat, q_y_heat, "heating"
        else:
            q_h_d, q_m_d, q_y_d, d_mode = q_h_cool, q_m_cool, q_y_cool, "cooling"
        NB, _, _ = find_optimal_nb(
            nb_min, nb_max, q_h=q_h_d, q_m=q_m_d, q_y=q_y_d,
            k=k, alpha=alpha, T_g=T_g, H_min=H_min, B=B, A=A,
            T_in_HP=_T_IN_HP[d_mode], **adv,
        )
```

4d. In the `StrategyResult(...)` constructor call at the bottom, after `H_min=H_min,` (in the "New fields" block), add:

```python
        nb_min=nb_min,
        nb_max=nb_max,
```

- [ ] **Step 5: Run the strategy suites**

Run: `source venv/bin/activate && python -m pytest tests/test_s6_footprint.py tests/test_s6_strategy.py tests/test_s6_ldc.py tests/test_s6_load_profile.py -v`
Expected: all PASS. Existing `test_s6_strategy.py` passes explicit `NB=16`, exercising the untouched legacy path.

- [ ] **Step 6: Commit**

```bash
git add geosite/s6_strategy/strategy.py geosite/s6_strategy/models.py tests/test_s6_footprint.py
git commit -m "feat(s6): footprint NB search in run_strategy; full prototype area table"
```

---

## Task 5: `/calculate/smart` — NB Truly Optional

**Files:**
- Modify: `app.py` (`calculate_smart`, ~lines 132–339; imports line 10)
- Test: `tests/test_api_footprint.py` (create)

**Interfaces:**
- Consumes: `compute_nb_range`, `find_optimal_nb`, `PROTOTYPE_AREAS_M2`
- Produces: `POST /calculate/smart` — required fields shrink to `zip_code, building_type, B, A`. Optional `NB` (legacy fixed-count, byte-identical behavior) and `H_min` (float, default 125.0, valid 30–300). Response gains top-level keys `nb_min`, `nb_max`, `H_min` (null in legacy mode), `footprint` (meta dict or null). `H` is now the derived depth of the governing pass.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_footprint.py`:

```python
"""API tests: footprint-driven NB on /calculate/smart."""

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


_BASE = {"zip_code": "60601", "building_type": "small_office", "B": 6.0, "A": 9.0}


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_without_nb_uses_footprint(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart", data=json.dumps(_BASE),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["nb_min"] == 2      # small_office prototype, spacing 6 m
    assert data["nb_max"] == 25
    assert data["H_min"] == 125.0
    assert data["NB"] >= 1
    assert data["footprint"]["n_floors"] == 1
    assert data["H"] == pytest.approx(data["L"] / data["NB"], abs=1.0)


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_with_nb_stays_legacy(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart", data=json.dumps(dict(_BASE, NB=16)),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["NB"] == 16
    assert data["nb_min"] is None
    assert data["nb_max"] is None
    assert data["H_min"] is None
    assert data["H"] == round(data["L"] / 16)


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_floor_area_changes_range(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, floor_area_m2=1022.0)),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert (data["nb_min"], data["nb_max"]) == (2, 35)


def test_smart_rejects_out_of_range_h_min(client):
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, H_min=1000)),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "H_min"


def test_smart_rejects_non_integer_nb(client):
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, NB="abc")),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "NB"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_api_footprint.py -v`
Expected: FAILs — omitting NB currently returns 400 `'NB' is required`

- [ ] **Step 3: Update the import in `app.py`**

Replace line 10:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
```

with:

```python
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import compute_nb_range, find_optimal_nb
```

- [ ] **Step 4: Make NB optional and parse H_min in `calculate_smart`**

Replace:

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

    # NB fixed-count mode is legacy; footprint-derived NB is the default.
    # data["NB"] may be JSON null (dev.html sends NaN -> null when blank).
    NB = None
    if data.get("NB") not in (None, ""):
        try:
            NB = int(data["NB"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "NB",
                            "message": "NB must be an integer"}), 400
    try:
        H_min = float(data.get("H_min", 125.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be a number"}), 400
    if not (30.0 <= H_min <= 300.0):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be between 30 and 300 m"}), 400
```

- [ ] **Step 5: Guard the NB range check**

Replace:

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

- [ ] **Step 6: Footprint range + optimizer in the sizing block**

Immediately BEFORE the `# --- s4: two-pass borefield sizing ---` comment, add:

```python
    nb_min = nb_max = None
    fp_meta = None
    if NB is None:
        try:
            nb_min, nb_max, fp_meta = compute_nb_range(
                floor_area_m2, building_type, spacing_m=B)
        except (KeyError, ValueError) as exc:
            return jsonify({"error": "field", "field": "building_type",
                            "message": str(exc)}), 400
```

Then replace the whole two-pass `try:` block (from `try:` after the `_has_both` line through `return jsonify({"error": "calculation", "message": str(exc)}), 500`):

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
                NB_out, H = NB, L / NB
            else:
                NB_h, L_heat, H_h = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=loads.q_h_heat, q_m=loads.q_m_heat, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_heat, **params,
                )
                NB_c, L_cool, H_c = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=loads.q_h_cool, q_m=loads.q_m_cool, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_cool, **params,
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
                NB_out, L, H = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=loads.q_h, q_m=loads.q_m, q_y=loads.q_y,
                    k=effective_k, alpha=site.alpha, T_g=site.T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_in_HP, **params,
                )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500
```

- [ ] **Step 7: Extend the response**

Replace:

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
        "nb_min": nb_min,
        "nb_max": nb_max,
        "H_min": None if NB is not None else H_min,
        "footprint": fp_meta,
        "governing": governing,
```

- [ ] **Step 8: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_api_footprint.py tests/test_pipeline_integration.py tests/test_s5_api.py -v`
Expected: all PASS (integration tests send `NB`, exercising the unchanged legacy path)

Then the full suite: `source venv/bin/activate && python -m pytest tests/ -v` — no new failures beyond the 5 pre-existing.

- [ ] **Step 9: Commit**

```bash
git add app.py tests/test_api_footprint.py
git commit -m "feat(api): footprint-derived NB range on /calculate/smart; NB optional"
```

---

## Task 6: UI — NB Override Moves to Advanced, Range Display in Results

**Files:**
- Modify: `templates/index.html` (s4 geometry card ~lines 135–172; advanced details ~lines 174–193; result panel ~lines 219–232)
- Modify: `static/main.js` (smart body ~lines 105–113, fieldMap ~line 146, result render ~lines 213–216, `fetchStrategy` payload ~lines 525–539)
- Modify: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 5's API contract (`nb_min`, `nb_max`, `H_min`, `NB`, `footprint`)
- Produces: DOM id `sres-NB-range` (added to `REQUIRED_IDS`); `s_NB` keeps its id (the `test_geometry_input_present` guard stays green) but moves into Advanced overrides as an explicit override; `s_H_min` stays in the geometry card with an accurate label.

- [ ] **Step 1: Add the new id to the regression suite**

In `tests/test_ui_template.py`, extend `REQUIRED_IDS` — after `"smart-result", "sres-L", "sres-H", "sres-NB",` add:

```python
    "sres-NB-range",
```

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: exactly 1 FAIL (the new id)

- [ ] **Step 2: Rework the geometry card in `templates/index.html`**

Replace:

```html
          <div class="field">
            <label for="s_NB">Number of boreholes <span class="hint-inline">— leave blank to auto-compute from min depth</span></label>
            <div class="input-row">
              <input type="number" id="s_NB" name="s_NB" min="1" placeholder="auto">
              <span class="unit">—</span>
            </div>
            <span class="field-error" data-for="s_NB"></span>
          </div>
          <div class="field">
            <label for="s_H_min">Min borehole depth <span class="hint-inline">— used when NB is auto-computed</span></label>
            <div class="input-row">
              <input type="number" id="s_H_min" name="s_H_min" step="1" min="50" value="125">
              <span class="unit">m</span>
            </div>
          </div>
```

with:

```html
          <div class="field">
            <label for="s_H_min">Minimum borehole depth <span class="hint-inline">— borehole count is derived from your building footprint; depths shallower than this are rejected</span></label>
            <div class="input-row">
              <input type="number" id="s_H_min" name="s_H_min" step="1" min="30" max="300" value="125">
              <span class="unit">m</span>
            </div>
            <span class="field-error" data-for="s_H_min"></span>
          </div>
```

- [ ] **Step 3: Move the NB override into Advanced overrides**

In `<details class="advanced-details">`, after the `s_mfls` field's closing `</div>` (the one closing its `.field`), add:

```html
            <div class="field">
              <label for="s_NB">Borehole count override <span class="hint-inline">(fixes NB and skips the footprint search)</span></label>
              <div class="input-row">
                <input type="number" id="s_NB" name="s_NB" min="1" placeholder="auto from footprint">
                <span class="unit">—</span>
              </div>
              <span class="field-error" data-for="s_NB"></span>
            </div>
```

- [ ] **Step 4: Add the range display to the result panel**

Replace:

```html
            <div class="stat">
              <span class="stat-label">Boreholes</span>
              <span class="stat-value"><span id="sres-NB">—</span></span>
            </div>
```

with:

```html
            <div class="stat">
              <span class="stat-label">Boreholes</span>
              <span class="stat-value"><span id="sres-NB">—</span></span>
              <span class="stat-sub" id="sres-NB-range"></span>
            </div>
```

- [ ] **Step 5: Update `static/main.js`**

5a. In the smart submit handler, replace:

```js
    const nbRaw = document.getElementById('s_NB').value.trim();
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      soil_confidence: document.getElementById('soil_confidence').value,
    };
    if (nbRaw !== '') body.NB = parseInt(nbRaw, 10);
```

with:

```js
    const nbRaw = document.getElementById('s_NB').value.trim();
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      B:               parseFloat(document.getElementById('s_B').value),
      A:               parseFloat(document.getElementById('s_A').value),
      H_min:           parseFloat(document.getElementById('s_H_min').value) || 125,
      soil_confidence: document.getElementById('soil_confidence').value,
    };
    if (nbRaw !== '') body.NB = parseInt(nbRaw, 10);
```

5b. Replace the field remap:

```js
        const fieldMap = { NB: 's_NB', B: 's_B', A: 's_A' };
```

with:

```js
        const fieldMap = { NB: 's_NB', B: 's_B', A: 's_A', H_min: 's_H_min' };
```

5c. After the headline stat population:

```js
    document.getElementById('sres-L').textContent  = fmtInt(result.L);
    document.getElementById('sres-H').textContent  = fmtInt(result.H);
    document.getElementById('sres-NB').textContent = fmtInt(result.NB);
```

add:

```js
    const nbRange = document.getElementById('sres-NB-range');
    if (result.nb_min != null && result.nb_max != null) {
      nbRange.textContent = result.NB < result.nb_min
        ? `below footprint range ${result.nb_min}–${result.nb_max} (small load — depth-primary fallback)`
        : `optimal within footprint range ${result.nb_min}–${result.nb_max}`;
    } else {
      nbRange.textContent = 'user override';
    }
```

5d. In the smart handler, replace the result attachment line:

```js
    result.building_type = body.building_type;
```

with:

```js
    result.building_type = body.building_type;
    result.NB_user = body.NB ?? null;
```

5e. In `fetchStrategy`, replace:

```js
    if (smartRes.NB) payload.NB = smartRes.NB;
```

with:

```js
    if (smartRes.NB_user) payload.NB = smartRes.NB_user;
```

(This fixes a latent inconsistency: today the smart response `NB` is always truthy, so `/api/strategy` was always forced into fixed-NB mode and its own auto-NB path never ran from the UI. Now only an explicit user override is forwarded, and s6 runs the same footprint search.)

- [ ] **Step 6: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS (including `test_geometry_input_present` — `s_NB` still exists)

- [ ] **Step 7: Manual browser check**

Run `source venv/bin/activate && flask --app app run --port 5000`, open `http://127.0.0.1:5000`:
1. ZIP `60601` + Small Office, NB override blank → result shows a derived NB with sub-line "optimal within footprint range 2–25"; s6 section renders.
2. Same inputs + floor area `1022` → range becomes 2–35.
3. Advanced → Borehole count override `16` → result NB = 16, sub-line "user override", values match pre-plan behavior.
4. `/dev` trace with NB blank ("auto") no longer errors.
Stop the server.

- [ ] **Step 8: Full suite + commit**

Run: `source venv/bin/activate && python -m pytest tests/ -v` — no new failures beyond the 5 pre-existing.

```bash
git add templates/index.html static/main.js tests/test_ui_template.py
git commit -m "feat(ui): footprint NB range display; NB becomes an advanced override"
```

---

## Self-Review Notes

- Spec coverage: (1) footprint from floors table — Task 2; (2) aspect-9 rectangle, W/L/perimeter formulas — Task 2; (3) spacing = existing `s_B` — Tasks 2/4/5 pass `spacing_m=B`; (4) NB_min/NB_max definitions — Task 2; (5) full-range minimum-L sweep with H ≥ H_min — Task 3; (6) outputs NB_opt/nb_min/nb_max/H/L in API + UI — Tasks 4–6; (7) `size_borefield_for_depth` prerequisite bundled as Task 1 and consumed as the Task 3 fallback.
- Backward compatibility: explicit NB short-circuits everything (strategy 4c, smart Step 6); all existing integration and s6 tests pass NB and stay byte-identical.
- Known intentional limitations: per-scenario NB (NB_before ≠ NB_after in s6) remains future work from the methodology-precision plan — this plan keeps one NB for before/after. `H` in the legacy smart path is still `L/NB` exactly as today. The footprint aspect (9) and the Tp `A` parameter remain independent inputs whose defaults coincide.
- Fallback semantics: `nb_opt < nb_min` signals the depth-primary fallback; surfaced in the UI sub-line and testable (`test_small_load_falls_back_to_depth_primary`).
- Sequencing: run BEFORE `2026-07-06-building-efficiency-params.md` (independent, but this plan edits the same app.py parse block; running this first keeps that plan's snippets accurate) and coordinate with the unexecuted `2026-07-06-methodology-precision.md` — its Task 4 is duplicated here as Task 1 (skip whichever runs second); its Task 7 (`s_H_target` replacing `s_NB`) is superseded by this plan's Task 6.

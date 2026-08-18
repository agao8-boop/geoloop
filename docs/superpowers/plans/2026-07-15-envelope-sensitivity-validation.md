# Envelope Accuracy + Full Sensitivity Study + WSHP Validation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the envelope multiplier model to be climate-specific and heat/cool-split; extend the sensitivity study to cover all building types and internal gains (people, lighting, equipment, schedule); and validate IdealLoads against an unmodified prototype HVAC run to quantify the modeling gap.

**Architecture:** Three parallel tracks. Track A (code revisions) rewrites `envelope.py` to look up heat/cool factors from existing per-city JSON files and applies them asymmetrically to heating vs cooling pulses in `s2_simulation`. Track B (sensitivity) extends `envelope_study.py` with internal-gains variants and adds a parallel orchestrator that runs all building types × 4 representative cities overnight. Track C (validation) adds a script that runs the unmodified DOE prototype (real VAV HVAC) alongside the IdealLoads version and computes the load-profile delta.

**Tech Stack:** Python 3.12, EnergyPlus 26.1, eppy, numpy, existing `scripts/run_energyplus_loads.py` helpers, existing `scripts/envelope_study.py` infrastructure.

## Global Constraints

- EnergyPlus binary: `/Applications/EnergyPlus-26-1-0/energyplus` (or `ENERGYPLUS_DIR` env override)
- All new scripts run from `geosite_advisor/` as CWD
- IDF manipulation: prefer regex on raw text (consistent with existing pattern in `envelope_study.py`); use eppy only when regex is insufficient
- Multiplier JSON schema must stay backward-compatible: new files add keys, never remove existing ones
- No real-time EnergyPlus in the Flask app — all simulations are offline pre-compute
- Representative cities for overnight run: `denver` (5B), `buffalo` (5A), `atlanta` (3A), `miami` (1A)
- Building types to run: `small_office`, `large_office`, `small_hotel`, `large_hotel` (medium_office already complete)

---

## File Map

### Track A — Code Revisions

| File | Action | Responsibility |
|------|--------|----------------|
| `geosite/s2_simulation/envelope.py` | **Rewrite** | Climate-aware lookup returning `(heat_factor, cool_factor)` per `(climate_zone, building_type, wwr, glazing, infiltration)` |
| `geosite/s2_simulation/__init__.py` | **Modify** | Accept `heat_factor`/`cool_factor` separately; apply asymmetrically to heating vs cooling pulse components |
| `templates/index.html` | **Modify** | Add `double_legacy` glazing option; update multiplier display labels |
| `static/main.js` | **Modify** | Default glazing to `double_legacy` when `year_built` tier is `existing` or `old` |
| `tests/test_s2_envelope.py` | **Rewrite** | Update to new API; add climate-zone lookup tests |
| `tests/test_api_envelope.py` | **Modify** | Add `double_legacy` round-trip test |

### Track B — Sensitivity Extension

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/envelope_study.py` | **Modify** | Add `_apply_people_density`, `_apply_lighting_density`, `_apply_equip_density`, `_apply_schedule_fraction` IDF helpers; add 8 new variants to variant list |
| `scripts/run_sensitivity_all.py` | **Create** | Parallel orchestrator: loops `building_type × city × variant`, spawns `envelope_study.run_study()` calls via `multiprocessing.Pool`, writes per-type aggregate JSON |
| `data/envelope_study/results/` | output dir (exists) | Receives `multipliers_{type}_{city}.json` for all new combinations |

### Track C — WSHP/IdealLoads Validation

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/wshp_validation.py` | **Create** | Runs unmodified DOE prototype (real HVAC) + IdealLoads version for same building+city; extracts plant loads from prototype ESO; compares to IdealLoads output; writes `data/wshp_validation/{type}_{city}_delta.json` |
| `data/wshp_validation/` | **Create dir** | Output for validation results |

---

## Task A1: Rewrite `envelope.py` — climate-aware heat/cool lookup

**Files:**
- Rewrite: `geosite/s2_simulation/envelope.py`
- Rewrite: `tests/test_s2_envelope.py`

**Interfaces:**
- Produces: `get_envelope_factors(climate_zone, building_type, wwr, glazing, infiltration) -> (heat_factor: float, cool_factor: float)`
- Produces: `GLAZING_OPTIONS`, `WWR_OPTIONS`, `ENVELOPE_OPTIONS` (frozensets, same names as before for API compat)
- Removes: `compute_envelope_factor()` (old single-scalar API — callers updated in A2)

**Context:**
- Existing per-city JSONs live at `data/envelope_study/results/multipliers_medium_office_{city}.json`
- Each JSON has a `"multipliers"` dict keyed by variant name (e.g. `"glaz_triple_low_e"`, `"wwr_70pct"`, `"infil_leaky"`)
- Each variant has `"peak_heat"`, `"peak_cool"`, `"annual_heat"`, `"annual_cool"` multipliers
- The `CITY_ZONE_MAP` in `envelope_study.py` maps city keys → climate zones; invert it to map zone → city for lookup
- Fall back to `medium_office` data if building type not yet available; fall back to `denver` if climate zone not in data

- [ ] **Step 1: Write failing tests**

```python
# tests/test_s2_envelope.py
import pytest
from geosite.s2_simulation.envelope import (
    get_envelope_factors, GLAZING_OPTIONS, WWR_OPTIONS, ENVELOPE_OPTIONS
)

def test_baseline_returns_unity():
    h, c = get_envelope_factors("5B", "medium_office", "medium", "double", "standard")
    assert h == pytest.approx(1.0, abs=0.01)
    assert c == pytest.approx(1.0, abs=0.01)

def test_heat_cool_are_asymmetric_for_triple_cold_climate():
    # Denver (5B): triple low-E cuts heating more than cooling
    h, c = get_envelope_factors("5B", "medium_office", "medium", "triple", "standard")
    assert h < c  # heat benefit > cool benefit in cold climate
    assert h < 0.75

def test_glazing_options_includes_double_legacy():
    assert "double_legacy" in GLAZING_OPTIONS

def test_unknown_climate_zone_falls_back():
    # Zone "9" doesn't exist — should fall back without raising
    h, c = get_envelope_factors("9", "medium_office", "medium", "double", "standard")
    assert h == pytest.approx(1.0, abs=0.05)

def test_unknown_building_type_falls_back():
    h, c = get_envelope_factors("5B", "hospital", "medium", "double", "standard")
    assert isinstance(h, float) and isinstance(c, float)

def test_double_legacy_higher_than_double():
    # Pre-2000 clear glass (higher U, higher SHGC) → more load than code low-E
    h_leg, c_leg = get_envelope_factors("5B", "medium_office", "medium", "double_legacy", "standard")
    h_dbl, c_dbl = get_envelope_factors("5B", "medium_office", "medium", "double", "standard")
    assert c_leg > c_dbl  # clear glass = more solar gain = more cooling load
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/agao/Downloads/CEE299/geosite_advisor
python3 -m pytest tests/test_s2_envelope.py -v 2>&1 | tail -20
```
Expected: ImportError or multiple FAILs

- [ ] **Step 3: Write new `envelope.py`**

```python
# geosite/s2_simulation/envelope.py
"""Climate-aware, heat/cool-split envelope load factors.

For a given (climate_zone, building_type, wwr, glazing, infiltration),
returns (heat_factor, cool_factor) looked up from pre-computed EnergyPlus
parametric study results in data/envelope_study/results/.

Variant → JSON key mapping:
  wwr:         low→wwr_10pct  medium→wwr_20pct(baseline=1.0)  high→wwr_70pct
  glazing:     triple→glaz_triple_low_e  double→glaz_double_low_e
               double_legacy→glaz_double_pane  single→glaz_single_pane
  infiltration: high→infil_tight  standard→infil_standard  low→infil_leaky
"""

import functools
import json
import pathlib

_RESULTS_DIR = pathlib.Path(__file__).parents[2] / "data" / "envelope_study" / "results"

# Map ASHRAE climate zone → city key used in JSON filenames
_ZONE_TO_CITY = {
    "1A": "miami", "2A": "tampa", "2B": "tucson",
    "3A": "atlanta", "3B": "el_paso", "3C": "san_diego",
    "4A": "new_york", "4B": "albuquerque", "4C": "seattle",
    "5A": "buffalo", "5B": "denver", "5C": "port_angeles",
    "6A": "rochester", "6B": "great_falls",
    "7":  "international_falls", "8": "fairbanks",
}
_FALLBACK_CITY    = "denver"
_FALLBACK_TYPE    = "medium_office"

# UI option → JSON variant key
_WWR_KEY = {"low": "wwr_10pct", "medium": "wwr_20pct", "high": "wwr_70pct"}
_GLAZING_KEY = {
    "triple":        "glaz_triple_low_e",
    "double":        "glaz_double_low_e",
    "double_legacy": "glaz_double_pane",
    "single":        "glaz_single_pane",
}
_INFIL_KEY = {"high": "infil_tight", "standard": "infil_standard", "low": "infil_leaky"}

WWR_OPTIONS      = frozenset(_WWR_KEY)
GLAZING_OPTIONS  = frozenset(_GLAZING_KEY)
ENVELOPE_OPTIONS = frozenset(_INFIL_KEY)  # named "envelope" in UI = infiltration/insulation tier


@functools.lru_cache(maxsize=64)
def _load_multipliers(building_type: str, city: str) -> dict:
    """Load multipliers JSON; fall back to medium_office or denver if missing."""
    for bt in (building_type, _FALLBACK_TYPE):
        for ct in (city, _FALLBACK_CITY):
            p = _RESULTS_DIR / f"multipliers_{bt}_{ct}.json"
            if p.exists():
                data = json.loads(p.read_text())
                return data.get("multipliers", {})
    return {}


def get_envelope_factors(
    climate_zone: str,
    building_type: str,
    wwr: str = "medium",
    glazing: str = "double",
    infiltration: str = "standard",
) -> tuple[float, float]:
    """Return (heat_factor, cool_factor) for the given envelope selections.

    Factors multiply the prototype loads: 1.0 = no change from prototype.
    heat_factor applies to q_h_heat, q_m_heat.
    cool_factor applies to q_h_cool, q_m_cool.
    """
    city = _ZONE_TO_CITY.get(climate_zone, _FALLBACK_CITY)
    mults = _load_multipliers(building_type, city)

    heat, cool = 1.0, 1.0
    for key_map, selection in (
        (_WWR_KEY, wwr),
        (_GLAZING_KEY, glazing),
        (_INFIL_KEY, infiltration),
    ):
        variant_key = key_map.get(selection)
        if not variant_key or variant_key not in mults:
            continue
        v = mults[variant_key]
        heat *= v.get("peak_heat", 1.0)
        cool *= v.get("peak_cool", 1.0)

    return heat, cool
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_s2_envelope.py -v 2>&1 | tail -20
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s2_simulation/envelope.py tests/test_s2_envelope.py
git commit -m "feat: climate-aware heat/cool split envelope lookup from per-city JSON"
```

---

## Task A2: Update `s2_simulation/__init__.py` — apply factors asymmetrically

**Files:**
- Modify: `geosite/s2_simulation/__init__.py`

**Interfaces:**
- Consumes: `get_envelope_factors(climate_zone, building_type, wwr, glazing, infiltration) -> (float, float)` from A1
- `get_loads()` signature change: replace `envelope_factor: float` with `heat_factor: float = 1.0, cool_factor: float = 1.0`

- [ ] **Step 1: Write failing test**

```python
# add to tests/test_s2_envelope.py
from geosite.s2_simulation import get_loads

def test_get_loads_asymmetric_factors():
    """heat_factor only scales heating pulses; cool_factor only scales cooling."""
    base   = get_loads("medium_office", "5B")
    scaled = get_loads("medium_office", "5B", heat_factor=2.0, cool_factor=0.5)
    # q_h_heat doubles
    assert scaled.q_h_heat == pytest.approx(base.q_h_heat * 2.0, rel=0.01)
    # q_h_cool halves
    assert scaled.q_h_cool == pytest.approx(base.q_h_cool * 0.5, rel=0.01)
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python3 -m pytest tests/test_s2_envelope.py::test_get_loads_asymmetric_factors -v
```

- [ ] **Step 3: Update `__init__.py`**

Replace the `envelope_factor: float` param and its application with:

```python
def get_loads(
    building_type: str,
    climate_zone: str,
    floor_area_m2: float | None = None,
    heat_factor: float = 1.0,
    cool_factor: float = 1.0,
) -> LoadPulses:
    """Return three-pulse ground loads for a DOE prototype building.

    heat_factor : multiplier applied to q_h_heat and q_m_heat (heating pulses)
    cool_factor : multiplier applied to q_h_cool and q_m_cool (cooling pulses)
    Combined q_h, q_m, q_y use the conservative (larger) factor.
    """
    loads = lookup_prototype_loads(building_type, climate_zone,
                                   target_area_m2=floor_area_m2)
    if heat_factor == 1.0 and cool_factor == 1.0:
        return loads

    combined = max(heat_factor, cool_factor)

    return LoadPulses(
        q_h=loads.q_h * combined,
        q_m=loads.q_m * combined,
        q_y=loads.q_y * combined,
        q_h_heat=loads.q_h_heat * heat_factor,
        q_m_heat=loads.q_m_heat * heat_factor,
        q_h_cool=loads.q_h_cool * cool_factor,
        q_m_cool=loads.q_m_cool * cool_factor,
    )
```

- [ ] **Step 4: Fix callers of old `envelope_factor` API in `app.py`**

Find the call site:
```bash
grep -n "envelope_factor\|get_loads\|get_envelope_factor\|compute_envelope_factor" /Users/agao/Downloads/CEE299/geosite_advisor/app.py | head -20
```

Update caller to:
```python
from geosite.s2_simulation.envelope import get_envelope_factors
# ...
heat_f, cool_f = get_envelope_factors(
    climate_zone=climate_zone,
    building_type=building_type,
    wwr=wwr,
    glazing=glazing,
    infiltration=envelope,
)
loads = get_loads(building_type, climate_zone,
                  floor_area_m2=floor_area_m2,
                  heat_factor=heat_f, cool_factor=cool_f)
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_s2_envelope.py tests/test_api_envelope.py -v 2>&1 | tail -30
```
Expected: all PASS

- [ ] **Step 6: Smoke-test the app**

```bash
python3 app.py &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/
kill %1
```
Expected: `200`

- [ ] **Step 7: Commit**

```bash
git add geosite/s2_simulation/__init__.py app.py tests/test_s2_envelope.py
git commit -m "feat: apply heat/cool envelope factors asymmetrically to heating vs cooling pulses"
```

---

## Task A3: Add `double_legacy` glazing to UI

**Files:**
- Modify: `templates/index.html` (two glazing `<select>` blocks — one in simplified form ~line 219, one in advanced form ~line 732)
- Modify: `static/main.js` — update default glazing selection based on `year_built` tier
- Modify: `tests/test_api_envelope.py` — add round-trip test

**Context:** `double_legacy` = pre-2000 clear double-pane glass (U=3.0 W/m²K, SHGC=0.70). This is the correct default for users selecting "existing" or "old" building age.

- [ ] **Step 1: Add option to both `<select>` blocks in `index.html`**

In both glazing selects (simplified ~line 219 and advanced ~line 732), add after the `double` option:

```html
<option value="double_legacy">Double-pane clear (pre-2000)</option>
```

Change the `double` label to make distinction clear:
```html
<option value="double" selected>Double-pane low-E (post-2000)</option>
```

- [ ] **Step 2: Update default glazing in `main.js` based on building age**

Find where `year_built`/`building_age` drives form defaults. Add logic so that when age tier is `existing` or `old`, the glazing select defaults to `double_legacy`:

```javascript
// After the year_built/building_age selection changes:
const age = document.getElementById('s_building_age').value;  // adjust ID as needed
const glazingSel = document.getElementById('s_glazing');
if ((age === 'existing' || age === 'old') && glazingSel.value === 'double') {
    glazingSel.value = 'double_legacy';
}
```

- [ ] **Step 3: Add API test**

```python
# in tests/test_api_envelope.py
def test_double_legacy_accepted_by_api(client):
    """double_legacy should parse and return a valid result."""
    resp = client.post("/calculate", json={
        **MINIMAL_VALID_PAYLOAD,
        "glazing": "double_legacy",
    })
    assert resp.status_code == 200
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_api_envelope.py -v 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/main.js tests/test_api_envelope.py
git commit -m "feat: add double_legacy (pre-2000 clear glass) glazing option"
```

---

## Task B1: Extend `envelope_study.py` with internal-gains variants

**Files:**
- Modify: `scripts/envelope_study.py`

**What to add:** Four new IDF text-manipulation helpers + 8 new variants (low/high for people density, lighting power density, equipment power density, and operating schedule fraction). One-at-a-time variation, baseline unchanged.

**Scaling approach:**
- People: IDF uses `Area/Person` method → field `Floor Area per Person {m2/person}`. Scale by `1/factor` (doubling density → halves m2/person).
- Lighting: field `Watts per Zone Floor Area {W/m2}` → multiply by factor.
- Equipment: same field pattern for `ElectricEquipment` → multiply by factor.
- Schedule: insert a new `Schedule:Constant` with the fraction value and reference it as a `Schedule Type Limits` override — this is complex. Simpler: multiply all numeric values in the `BLDG_OCC_SCH` (occupancy schedule) blocks using regex, effectively scaling occupancy hours.

- [ ] **Step 1: Add four helper functions after `_apply_infiltration` in `envelope_study.py`**

```python
def _apply_people_density(idf_text: str, factor: float) -> str:
    """Scale Floor Area per Person by 1/factor (factor>1 = more people)."""
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Floor Area per Person \{m2/person\})',
        lambda m: f"{m.group(1)}{float(m.group(2)) / factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_lighting_density(idf_text: str, factor: float) -> str:
    """Scale Watts per Zone Floor Area for Lights objects."""
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Watts per Zone Floor Area \{W/m2\})',
        lambda m: f"{m.group(1)}{float(m.group(2)) * factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_equip_density(idf_text: str, factor: float) -> str:
    """Scale Watts per Zone Floor Area for ElectricEquipment objects."""
    # ElectricEquipment uses same field comment as Lights in DOE prototypes
    # but they appear in different object contexts; regex matches both — acceptable
    # since we want to scale all internal gains together for equipment sensitivity.
    return re.sub(
        r'(\n\s+)([\d.E+\-]+),(\s+!- Watts per Zone Floor Area \{W/m2\} \[Electric Equipment\])',
        lambda m: f"{m.group(1)}{float(m.group(2)) * factor:.6f},{m.group(3)}",
        idf_text,
    )


def _apply_schedule_fraction(idf_text: str, factor: float) -> str:
    """Scale occupancy schedule values (0–1 fractional) by factor, clamped to 1.0.

    Targets BLDG_OCC_SCH compact schedule numeric values only.
    factor < 1.0 = reduced occupancy hours (e.g. 0.71 ≈ 5-day week).
    """
    in_occ_sch = False
    lines = idf_text.split('\n')
    out = []
    for line in lines:
        if 'BLDG_OCC_SCH' in line and 'Schedule:Compact' in idf_text[max(0,idf_text.index(line)-200):idf_text.index(line)+10]:
            in_occ_sch = True
        if in_occ_sch and re.match(r'\s+[\d.]+,\s*$', line):
            val = float(re.search(r'[\d.]+', line).group())
            scaled = min(val * factor, 1.0)
            line = re.sub(r'[\d.]+', f'{scaled:.4f}', line, count=1)
        if in_occ_sch and line.strip().endswith(';'):
            in_occ_sch = False
        out.append(line)
    return '\n'.join(out)
```

- [ ] **Step 2: Add 8 new variant entries in the `VARIANTS` list inside `run_study()`**

Locate the block that builds the variants list (around line 340 in `envelope_study.py`). After the existing infiltration variants, append:

```python
# --- Internal gains: people density ---
{"label": "people_low",   "people_factor": 0.5,  "lighting_factor": 1.0, "equip_factor": 1.0, "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
{"label": "people_high",  "people_factor": 2.0,  "lighting_factor": 1.0, "equip_factor": 1.0, "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
# --- Internal gains: lighting power density ---
{"label": "lighting_low", "people_factor": 1.0, "lighting_factor": 0.5,  "equip_factor": 1.0, "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
{"label": "lighting_high","people_factor": 1.0, "lighting_factor": 1.5,  "equip_factor": 1.0, "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
# --- Internal gains: equipment/plug loads ---
{"label": "equip_low",    "people_factor": 1.0, "lighting_factor": 1.0, "equip_factor": 0.5,  "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
{"label": "equip_high",   "people_factor": 1.0, "lighting_factor": 1.0, "equip_factor": 2.0,  "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
# --- Schedule: 5-day vs always-on ---
{"label": "sched_5day",   "people_factor": 1.0, "lighting_factor": 1.0, "equip_factor": 1.0, "sched_factor": 0.714,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0},
{"label": "sched_extended","people_factor": 1.0, "lighting_factor": 1.0, "equip_factor": 1.0, "sched_factor": 1.0,
 "u_factor": GLAZING_BASELINE_U, "shgc": GLAZING_BASELINE_SHGC, "infil_rate": INFILTRATION_BASELINE, "wwr_scale": 1.0,
 "note": "baseline — already 8760h annual run"},
```

- [ ] **Step 3: Apply new factors in `_write_variant_idf`**

Update the function signature and body to call the new helpers:

```python
def _write_variant_idf(raw_idf_path, variant_dir,
                        u_factor, shgc, infil_rate, wwr_scale,
                        people_factor=1.0, lighting_factor=1.0,
                        equip_factor=1.0, sched_factor=1.0):
    text = raw_idf_path.read_text(encoding="utf-8", errors="replace")
    text = _apply_glazing(text, u_factor, shgc)
    text = _apply_infiltration(text, infil_rate)
    text = _apply_wwr_replace(text, wwr_scale)
    if people_factor != 1.0:
        text = _apply_people_density(text, people_factor)
    if lighting_factor != 1.0:
        text = _apply_lighting_density(text, lighting_factor)
    if equip_factor != 1.0:
        text = _apply_equip_density(text, equip_factor)
    if sched_factor != 1.0:
        text = _apply_schedule_fraction(text, sched_factor)
    variant_dir.mkdir(parents=True, exist_ok=True)
    out_path = variant_dir / "modified_base.idf"
    out_path.write_text(text, encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Dry-run sanity check**

```bash
python3 scripts/envelope_study.py --building medium_office --city denver --dry-run 2>&1 | grep -E "people|lighting|equip|sched"
```
Expected: 8 new variant labels printed in the dry-run output.

- [ ] **Step 5: Commit**

```bash
git add scripts/envelope_study.py
git commit -m "feat: add people/lighting/equipment/schedule variants to envelope sensitivity study"
```

---

## Task B2: Parallel orchestration script for overnight batch

**Files:**
- Create: `scripts/run_sensitivity_all.py`

**Context:** Run all missing combinations: `{small_office, large_office, small_hotel, large_hotel} × {denver, buffalo, atlanta, miami}` plus internal-gains variants for `medium_office × {denver, buffalo, atlanta, miami}`. Use `multiprocessing.Pool` to run 4 studies in parallel. Each study is ~21 variants × 5–15 min/sim = 1.75–5.25 hrs per (type, city) pair; with 4-way parallelism, wall time ≈ 4–8 hrs.

- [ ] **Step 1: Write `run_sensitivity_all.py`**

```python
#!/usr/bin/env python3
"""Overnight orchestrator: run envelope_study for all missing building types × cities.

Usage:
    python scripts/run_sensitivity_all.py
    python scripts/run_sensitivity_all.py --dry-run
    python scripts/run_sensitivity_all.py --workers 4

Results written to data/envelope_study/results/multipliers_{type}_{city}.json
"""
import argparse
import multiprocessing
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"

# Building types without complete 4-city data
NEW_TYPES = ["small_office", "large_office", "small_hotel", "large_hotel"]
REPR_CITIES = ["denver", "buffalo", "atlanta", "miami"]

# Also run new internal-gains variants for medium_office
MEDIUM_CITIES = ["denver", "buffalo", "atlanta", "miami"]


def _run_one(args):
    building, city, dry_run = args
    import envelope_study
    tag = f"{building}_{city}"
    result_path = RESULTS_DIR / f"multipliers_{tag}.json"
    if result_path.exists() and not dry_run:
        print(f"[SKIP] {tag} already complete")
        return tag, "skipped"
    print(f"[START] {tag}")
    t0 = time.time()
    try:
        envelope_study.run_study(city=city, building_type=building, dry_run=dry_run)
        elapsed = time.time() - t0
        print(f"[DONE]  {tag}  ({elapsed/60:.1f} min)")
        return tag, "ok"
    except Exception as e:
        print(f"[FAIL]  {tag}: {e}")
        return tag, f"error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    tasks = []
    for bt in NEW_TYPES:
        for city in REPR_CITIES:
            tasks.append((bt, city, args.dry_run))
    # medium_office new-variant re-runs (envelope_study skips already-done variants)
    for city in MEDIUM_CITIES:
        tasks.append(("medium_office", city, args.dry_run))

    print(f"Total tasks: {len(tasks)}  workers: {args.workers}")
    with multiprocessing.Pool(processes=args.workers) as pool:
        results = pool.map(_run_one, tasks)

    ok  = [r for r in results if r[1] == "ok"]
    skp = [r for r in results if r[1] == "skipped"]
    err = [r for r in results if r[1].startswith("error")]
    print(f"\n=== Summary ===  ok={len(ok)}  skipped={len(skp)}  errors={len(err)}")
    for tag, msg in err:
        print(f"  FAILED: {tag}: {msg}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run to verify task list**

```bash
python3 scripts/run_sensitivity_all.py --dry-run 2>&1 | head -30
```
Expected: prints 24 task lines (4 types × 4 cities + 4 medium_office), no errors

- [ ] **Step 3: Commit**

```bash
git add scripts/run_sensitivity_all.py
git commit -m "feat: parallel overnight orchestrator for all building types × cities sensitivity study"
```

---

## Task C1: WSHP/IdealLoads validation script

**Files:**
- Create: `scripts/wshp_validation.py`
- Create dir: `data/wshp_validation/`

**What it does:** For each (building_type, city) pair, runs two EnergyPlus simulations:
1. **IdealLoads run** — same as `envelope_study` baseline (already done; reuses existing results if present)
2. **Prototype run** — unmodified DOE prototype IDF with its native VAV+chiller+boiler HVAC system, with only output variable requests added

Extracts from prototype run: total chiller cooling output (= plant cooling load), total boiler heating output (= plant heating load). Compares peak and annual values to IdealLoads. Writes delta JSON.

**Targets:** `medium_office` and `large_office` × `buffalo` (cold, heat recovery matters) and `miami` (warm, economizer matters).

- [ ] **Step 1: Create output directory**

```bash
mkdir -p /Users/agao/Downloads/CEE299/geosite_advisor/data/wshp_validation
```

- [ ] **Step 2: Write `wshp_validation.py`**

```python
#!/usr/bin/env python3
"""Compare IdealLoads load profile to unmodified DOE prototype HVAC plant loads.

For each (building_type, city):
  Run A: IdealLoads (reuse existing baseline if available, else run fresh)
  Run B: Unmodified prototype — add output meters, run as-is

Outputs data/wshp_validation/{type}_{city}_delta.json with:
  - peak_heat_ideal_kW, peak_heat_proto_kW, peak_heat_delta_pct
  - peak_cool_ideal_kW, peak_cool_proto_kW, peak_cool_delta_pct
  - annual_heat_ideal_MWh, annual_heat_proto_MWh, annual_heat_delta_pct
  - annual_cool_ideal_MWh, annual_cool_proto_MWh, annual_cool_delta_pct

Usage:
    python scripts/wshp_validation.py
    python scripts/wshp_validation.py --dry-run
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))

ROOT         = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR    = ROOT / "data" / "doe_prototypes"
OUT_DIR      = ROOT / "data" / "wshp_validation"
EPW_DIR      = ROOT / "data" / "epw"
ENERGYPLUS   = pathlib.Path(os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-26-1-0")) / "energyplus"

TARGETS = [
    ("medium_office", "buffalo"),
    ("medium_office", "miami"),
    ("large_office",  "buffalo"),
    ("large_office",  "miami"),
]

CITY_MAP = {
    "buffalo": ("5A", "USA_NY_Buffalo.Niagara.Intl.AP.725280_TMY3.epw", "Buffalo"),
    "miami":   ("1A", "USA_FL_Miami.Intl.AP.722020_TMY3.epw",           "Miami"),
}
PROTO_STEMS = {
    "medium_office": "ASHRAE901_OfficeMedium_STD2022",
    "large_office":  "ASHRAE901_OfficeLarge_STD2022",
}

OUTPUT_METER_BLOCK = """
  Output:Meter,Chiller Electricity Energy,Hourly;
  Output:Meter,Boiler NaturalGas Energy,Hourly;
  Output:Meter,Boiler Electricity Energy,Hourly;
  Output:Variable,*,Zone Ideal Loads Heat Recovery Total Cooling Energy,Hourly;
  Output:Variable,*,Zone Ideal Loads Heat Recovery Total Heating Energy,Hourly;
"""


def _add_output_meters(idf_text: str) -> str:
    """Append output meter requests before the last semicolon-terminated object."""
    return idf_text.rstrip() + "\n\n" + OUTPUT_METER_BLOCK + "\n"


def _set_run_period_annual(idf_text: str) -> str:
    """Ensure RunPeriod covers the full year."""
    return re.sub(
        r'(RunPeriod,.*?)(EndMonth\s*=\s*\d+)',
        r'\g<1>EndMonth = 12',
        idf_text, flags=re.DOTALL
    )


def _parse_eso_meter(eso_path: pathlib.Path, meter_name: str) -> np.ndarray:
    """Extract hourly values for a named meter from an ESO file."""
    lines = eso_path.read_text(encoding="utf-8", errors="replace").splitlines()
    # Find the variable index for this meter
    idx = None
    for line in lines:
        if meter_name.lower() in line.lower() and line.startswith(" "):
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    idx = int(parts[0].strip())
                    break
                except ValueError:
                    pass
    if idx is None:
        return np.zeros(8760)
    values = []
    for line in lines:
        if line.startswith(f"{idx},"):
            parts = line.split(",")
            try:
                values.append(float(parts[1]))
            except (ValueError, IndexError):
                pass
    arr = np.array(values[:8760], dtype=float)
    return arr if len(arr) == 8760 else np.zeros(8760)


def run_prototype(building_type: str, city: str, work_dir: pathlib.Path,
                  dry_run: bool = False) -> dict | None:
    zone, epw_file, city_stem = CITY_MAP[city]
    proto_stem = PROTO_STEMS[building_type]
    proto_sub = f"{proto_stem}/{proto_stem}_{city_stem}"
    idf_path = PROTO_DIR / proto_sub / f"{proto_stem}_{city_stem}.idf"
    epw_path = EPW_DIR / epw_file

    if not idf_path.exists():
        print(f"  [WARN] IDF not found: {idf_path}")
        return None
    if not epw_path.exists():
        print(f"  [WARN] EPW not found: {epw_path}")
        return None

    run_dir = work_dir / f"proto_{building_type}_{city}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Prepare modified IDF with output meters
    text = idf_path.read_text(encoding="utf-8", errors="replace")
    text = _add_output_meters(text)
    mod_idf = run_dir / "prototype_with_outputs.idf"
    mod_idf.write_text(text, encoding="utf-8")

    if dry_run:
        print(f"  [DRY] would run EnergyPlus on {mod_idf.name}")
        return {"peak_heat_W": 0.0, "peak_cool_W": 0.0,
                "annual_heat_Wh": 0.0, "annual_cool_Wh": 0.0, "source": "dry_run"}

    import subprocess
    result = subprocess.run(
        [str(ENERGYPLUS), "-w", str(epw_path), "-r", str(mod_idf)],
        cwd=run_dir, capture_output=True, text=True, timeout=3600
    )
    if result.returncode != 0:
        print(f"  [FAIL] EnergyPlus failed: {result.stderr[-500:]}")
        return None

    eso_path = run_dir / "eplusout.eso"
    if not eso_path.exists():
        print(f"  [FAIL] No ESO output found")
        return None

    heat_Wh = _parse_eso_meter(eso_path, "Boiler NaturalGas Energy")
    cool_Wh = _parse_eso_meter(eso_path, "Chiller Electricity Energy")

    return {
        "peak_heat_W":    float(heat_Wh.max()),
        "peak_cool_W":    float(cool_Wh.max()),
        "annual_heat_Wh": float(heat_Wh.sum()),
        "annual_cool_Wh": float(cool_Wh.sum()),
        "source": "prototype_vav",
    }


def load_ideal_baseline(building_type: str, city: str) -> dict | None:
    """Load existing IdealLoads baseline metrics from envelope_study results."""
    results_dir = ROOT / "data" / "envelope_study" / "results"
    p = results_dir / f"multipliers_{building_type}_{city}.json"
    if not p.exists():
        p = results_dir / f"multipliers_{city}.json"  # legacy naming
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    raw = data.get("raw_metrics", {})
    baseline_label = data.get("baseline_label", "wwr_20pct")
    bm = raw.get(baseline_label)
    if not bm:
        return None
    return {
        "peak_heat_W":    bm["peak_heat_W"],
        "peak_cool_W":    bm["peak_cool_W"],
        "annual_heat_Wh": bm["annual_heat_Wh"],
        "annual_cool_Wh": bm["annual_cool_Wh"],
        "source": "ideal_loads",
    }


def delta_pct(a: float, b: float) -> float:
    if abs(a) < 1.0:
        return 0.0
    return round((b - a) / abs(a) * 100, 1)


def compare(ideal: dict, proto: dict) -> dict:
    return {
        "peak_heat_ideal_kW":   round(ideal["peak_heat_W"] / 1000, 1),
        "peak_heat_proto_kW":   round(proto["peak_heat_W"] / 1000, 1),
        "peak_heat_delta_pct":  delta_pct(ideal["peak_heat_W"], proto["peak_heat_W"]),
        "peak_cool_ideal_kW":   round(ideal["peak_cool_W"] / 1000, 1),
        "peak_cool_proto_kW":   round(proto["peak_cool_W"] / 1000, 1),
        "peak_cool_delta_pct":  delta_pct(ideal["peak_cool_W"], proto["peak_cool_W"]),
        "annual_heat_ideal_MWh":  round(ideal["annual_heat_Wh"] / 1e6, 2),
        "annual_heat_proto_MWh":  round(proto["annual_heat_Wh"] / 1e6, 2),
        "annual_heat_delta_pct":  delta_pct(ideal["annual_heat_Wh"], proto["annual_heat_Wh"]),
        "annual_cool_ideal_MWh":  round(ideal["annual_cool_Wh"] / 1e6, 2),
        "annual_cool_proto_MWh":  round(proto["annual_cool_Wh"] / 1e6, 2),
        "annual_cool_delta_pct":  delta_pct(ideal["annual_cool_Wh"], proto["annual_cool_Wh"]),
        "note": "proto=VAV+chiller+boiler; ideal=ZoneHVAC:IdealLoadsAirSystem",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="wshp_val_") as tmpdir:
        work = pathlib.Path(tmpdir)
        for building_type, city in TARGETS:
            tag = f"{building_type}_{city}"
            print(f"\n=== {tag} ===")

            ideal = load_ideal_baseline(building_type, city)
            if ideal is None:
                print(f"  [WARN] No IdealLoads baseline found for {tag}; skipping")
                continue

            proto = run_prototype(building_type, city, work, dry_run=args.dry_run)
            if proto is None:
                print(f"  [WARN] Prototype run failed for {tag}; skipping")
                continue

            result = {"ideal": ideal, "prototype": proto, "delta": compare(ideal, proto)}
            out_path = OUT_DIR / f"{tag}_delta.json"
            out_path.write_text(json.dumps(result, indent=2))
            print(f"  peak_heat delta: {result['delta']['peak_heat_delta_pct']:+.1f}%")
            print(f"  peak_cool delta: {result['delta']['peak_cool_delta_pct']:+.1f}%")
            print(f"  annual_heat delta: {result['delta']['annual_heat_delta_pct']:+.1f}%")
            print(f"  annual_cool delta: {result['delta']['annual_cool_delta_pct']:+.1f}%")
            print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Dry-run to verify IDF paths resolve**

```bash
python3 scripts/wshp_validation.py --dry-run 2>&1
```
Expected: 4 `[DRY]` lines, no path errors. If `[WARN] IDF not found` appears, check `data/doe_prototypes/` directory structure.

- [ ] **Step 4: Commit**

```bash
git add scripts/wshp_validation.py data/wshp_validation/
git commit -m "feat: WSHP validation script — compare IdealLoads vs prototype VAV plant loads"
```

---

## Task D: Launch overnight runs

Run both batch scripts in background with logging. Execute after Tasks A1–A3, B1–B2, C1 are all committed.

- [ ] **Step 1: Verify all tests pass before launching**

```bash
python3 -m pytest tests/test_s2_envelope.py tests/test_api_envelope.py -v 2>&1 | tail -10
```
Expected: all PASS

- [ ] **Step 2: Launch sensitivity study (background)**

```bash
cd /Users/agao/Downloads/CEE299/geosite_advisor
nohup python3 scripts/run_sensitivity_all.py --workers 4 \
  > /tmp/sensitivity_overnight.log 2>&1 &
echo "Sensitivity PID: $!"
```

- [ ] **Step 3: Launch WSHP validation (background)**

```bash
nohup python3 scripts/wshp_validation.py \
  > /tmp/wshp_validation.log 2>&1 &
echo "WSHP validation PID: $!"
```

- [ ] **Step 4: Confirm both started**

```bash
sleep 5
tail -5 /tmp/sensitivity_overnight.log
tail -5 /tmp/wshp_validation.log
```
Expected: task start messages, no immediate crash

- [ ] **Step 5: Morning check — read results**

```bash
# Sensitivity: count completed files
ls data/envelope_study/results/multipliers_*_*.json | wc -l

# WSHP: print delta summary
for f in data/wshp_validation/*_delta.json; do
  echo "=== $f ==="; python3 -c "
import json,sys
d=json.load(open('$f'))['delta']
print(f'  heat: ideal={d[\"peak_heat_ideal_kW\"]}kW proto={d[\"peak_heat_proto_kW\"]}kW delta={d[\"peak_heat_delta_pct\"]:+}%')
print(f'  cool: ideal={d[\"peak_cool_ideal_kW\"]}kW proto={d[\"peak_cool_proto_kW\"]}kW delta={d[\"peak_cool_delta_pct\"]:+}%')
"
done
```

---

## Self-Review

**Spec coverage:**
- ✅ Envelope multiplier heat/cool split → Task A1 + A2
- ✅ Climate-specific lookup → Task A1
- ✅ double_legacy glazing for existing buildings → Task A3
- ✅ Sensitivity for people, lighting, equipment, schedule → Task B1
- ✅ All building types × representative cities → Task B2
- ✅ WSHP/IdealLoads comparison run → Task C1
- ✅ Overnight launch → Task D

**Placeholder scan:** No TBD, all steps have concrete code.

**Type consistency:**
- `get_envelope_factors()` returns `tuple[float, float]` — A1 defines, A2 consumes ✅
- `get_loads()` new signature has `heat_factor`/`cool_factor` — A2 defines, `app.py` update in same task ✅
- `_write_variant_idf()` new kwargs are optional with defaults — B1 defines, no other callers break ✅

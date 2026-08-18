# Building Efficiency Parameters (WWR, Envelope, Glazing) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the professor-requested building-design pull-downs — Window-Wall Ratio, envelope efficiency, and glazing type — as load modifiers wired end-to-end through the UI, both calculate endpoints, the strategy endpoint, and the dev dashboard. **All factors are 1.0 for now**: the actual multipliers arrive from the professor next week (input spreadsheet due 2026-07-13). This plan builds structure and wiring only; zero physics.

**Architecture:** These parameters are load modifiers — they scale the heating/cooling demand from the EnergyPlus prototype loads. A new module `geosite/s2_simulation/envelope.py` owns three factor tables and `compute_envelope_factor(wwr, envelope, glazing) -> float` (the product of the three; today always 1.0). The multiplier is applied in the s2 load lookup step: `get_loads(..., envelope_factor=...)` scales the returned `LoadPulses`, and `run_strategy(..., envelope_factor=...)` folds it into the 8760h profile scale (alongside `year_factor`), so s4 sizing and s6 strategy stay consistent. The manual `/calculate` endpoint multiplies the user's q_h/q_m/q_y directly. Because every factor is 1.0, every existing numeric test result is unchanged — the suite pins that.

**Tech Stack:** Python 3.11 (venv at `./venv`), Flask, pytest; vanilla JS frontend (`static/main.js`, `templates/index.html`, `templates/dev.html`).

## Global Constraints

- Run tests with: `source venv/bin/activate && python -m pytest tests/ -v` (from repo root). Baseline: 219 passing, 5 pre-existing failures (missing directories, unrelated) — do not fix or worsen those 5.
- **No physics.** Every factor table entry is exactly `1.0` until the professor supplies calibrated values. Do not invent multipliers (see memory: Feedback — No Invented Methods). The ONLY code that will change when real values arrive is the three dicts in `envelope.py`.
- Option keys (exact strings, used in Python, HTML `value=`, and JS):
  - `wwr`: `"low"` (≤20%), `"medium"` (30–40%, default), `"high"` (≥50%)
  - `envelope`: `"high"` (high performance), `"standard"` (default), `"low"` (low performance)
  - `glazing`: `"triple"`, `"double"` (standard, default), `"single"`
- Combined factor: `envelope_factor = WWR_FACTORS[wwr] * ENVELOPE_FACTORS[envelope] * GLAZING_FACTORS[glazing]`
- API contract: the three fields are optional strings on `/calculate/smart` and `/calculate`; unknown values → 400 with `{"error": "field", "field": "<name>"}`. `/api/strategy` takes the pre-combined `envelope_factor` float (like `year_factor`), not the three strings.
- Backward compatibility: omitting all three fields must produce byte-identical responses to today (defaults → factor 1.0).
- NaN-safe scaling: `LoadPulses` cross-mode fields (`q_h_heat` etc.) may be NaN for stub entries; scale with the existing `v * f if v == v else nan` pattern.
- UI placement: a "Building Design" card between the s2 Building card and the s4 Borefield Geometry header in Smart Mode, labeled with the **s2** stage pill (these are building characteristics that affect the load simulation). Manual Mode gets the same three selects in the Basic tab.
- No comments in code unless the WHY is non-obvious. No emojis in UI.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `geosite/s2_simulation/envelope.py` | Factor tables + `compute_envelope_factor()` (all 1.0) |
| Create | `tests/test_s2_envelope.py` | Factor function behavior + option-set pins |
| Modify | `geosite/s2_simulation/__init__.py` | `get_loads(..., envelope_factor=1.0)` applies the scalar |
| Modify | `tests/test_s2_lookup.py` | Scaling identity at factor 1.0; factor ≠ 1.0 scales linearly |
| Modify | `geosite/s6_strategy/strategy.py` | `run_strategy(..., envelope_factor=1.0)` folds into profile scale |
| Modify | `app.py` | Parse/validate the three fields on `/calculate/smart` + `/calculate`; `envelope_factor` on `/api/strategy`; echo in responses |
| Create | `tests/test_api_envelope.py` | Endpoint validation + identity behavior |
| Modify | `templates/index.html` | "Building Design" card (smart) + selects in manual Basic tab |
| Modify | `templates/dev.html` | Three trace-row selects + s2 trace display |
| Modify | `static/main.js` | Include values in smart body, strategy payload, manual collect |
| Modify | `tests/test_ui_template.py` | New ids in `REQUIRED_IDS` |

**Current-state notes baked into this plan:**
1. `get_loads` (s2 `__init__.py`) is a thin wrapper over `lookup_prototype_loads`; the multiplier goes in the wrapper so `lookup.py` (which mirrors the JSON schema) stays untouched.
2. `app.py` already applies `year_factor` to `LoadPulses` with a NaN-safe `_scale` helper inside `calculate_smart` — the envelope factor is applied earlier, inside `get_loads`, so the two multipliers compose without touching that block.
3. `run_strategy` scales the 8760h profile by `scale = year_factor * (floor_area/proto_area)`; `envelope_factor` multiplies into the same `scale` so s6's before/after sizing sees the same loads as s4.
4. `main.js` `fetchStrategy` builds its payload from the smart response — the smart response must therefore echo `envelope_factor` under `loads` for the s6 call to forward it.
5. `templates/dev.html` trace runner (`#t-run`, ~line 1292) posts to `/calculate/smart` and renders `s2-in`; it gains three selects and two trace lines.

---

## Task 1: Factor Module — `envelope.py`

**Files:**
- Create: `geosite/s2_simulation/envelope.py`
- Test: `tests/test_s2_envelope.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `WWR_FACTORS`, `ENVELOPE_FACTORS`, `GLAZING_FACTORS` (dicts), `WWR_OPTIONS`/`ENVELOPE_OPTIONS`/`GLAZING_OPTIONS` (frozensets for endpoint validation), `compute_envelope_factor(wwr="medium", envelope="standard", glazing="double") -> float`. Raises `ValueError` naming the offending parameter on unknown keys. Consumed by Tasks 2–3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s2_envelope.py`:

```python
"""Building-design load modifiers. All factors are 1.0 until the professor
supplies calibrated values (input spreadsheet review, 2026-07-13)."""

import itertools
import pytest

from geosite.s2_simulation.envelope import (
    WWR_FACTORS,
    ENVELOPE_FACTORS,
    GLAZING_FACTORS,
    compute_envelope_factor,
)


def test_option_sets_pinned():
    assert set(WWR_FACTORS) == {"low", "medium", "high"}
    assert set(ENVELOPE_FACTORS) == {"high", "standard", "low"}
    assert set(GLAZING_FACTORS) == {"triple", "double", "single"}


def test_all_factors_are_neutral_for_now():
    for combo in itertools.product(WWR_FACTORS, ENVELOPE_FACTORS, GLAZING_FACTORS):
        assert compute_envelope_factor(*combo) == 1.0


def test_defaults_are_medium_standard_double():
    assert compute_envelope_factor() == 1.0
    assert compute_envelope_factor("medium", "standard", "double") == 1.0


def test_unknown_option_raises_with_param_name():
    with pytest.raises(ValueError, match="wwr"):
        compute_envelope_factor(wwr="huge")
    with pytest.raises(ValueError, match="envelope"):
        compute_envelope_factor(envelope="passivhaus")
    with pytest.raises(ValueError, match="glazing"):
        compute_envelope_factor(glazing="quad")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s2_envelope.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'geosite.s2_simulation.envelope'`

- [ ] **Step 3: Implement the module**

Create `geosite/s2_simulation/envelope.py`:

```python
"""Building-design load modifiers: WWR, envelope tightness, glazing type.

Structure-only placeholder: every factor is 1.0 until calibrated multipliers
arrive from the professor (input spreadsheet review, 2026-07-13). When they
do, ONLY the three dicts below change — no wiring code moves.

The combined factor scales the prototype heating/cooling loads (q_h, q_m,
q_y and the 8760h strategy profile) as a single scalar, the same mechanism
as the construction-year factor.
"""

WWR_FACTORS = {          # window-to-wall ratio
    "low":    1.0,       # <= 20%
    "medium": 1.0,       # 30-40% (DOE prototype baseline)
    "high":   1.0,       # >= 50%
}

ENVELOPE_FACTORS = {     # insulation + air sealing
    "high":     1.0,     # high performance
    "standard": 1.0,     # code baseline
    "low":      1.0,     # low performance / leaky
}

GLAZING_FACTORS = {      # glass quality
    "triple": 1.0,
    "double": 1.0,       # standard
    "single": 1.0,
}

WWR_OPTIONS = frozenset(WWR_FACTORS)
ENVELOPE_OPTIONS = frozenset(ENVELOPE_FACTORS)
GLAZING_OPTIONS = frozenset(GLAZING_FACTORS)


def compute_envelope_factor(
    wwr: str = "medium",
    envelope: str = "standard",
    glazing: str = "double",
) -> float:
    """Combined load multiplier for the selected building-design options."""
    if wwr not in WWR_FACTORS:
        raise ValueError(f"wwr must be one of {sorted(WWR_FACTORS)}, got '{wwr}'")
    if envelope not in ENVELOPE_FACTORS:
        raise ValueError(f"envelope must be one of {sorted(ENVELOPE_FACTORS)}, got '{envelope}'")
    if glazing not in GLAZING_FACTORS:
        raise ValueError(f"glazing must be one of {sorted(GLAZING_FACTORS)}, got '{glazing}'")
    return WWR_FACTORS[wwr] * ENVELOPE_FACTORS[envelope] * GLAZING_FACTORS[glazing]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s2_envelope.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s2_simulation/envelope.py tests/test_s2_envelope.py
git commit -m "feat(s2): envelope factor tables (WWR/envelope/glazing, all 1.0)"
```

---

## Task 2: Apply the Factor in `get_loads`

**Files:**
- Modify: `geosite/s2_simulation/__init__.py`
- Test: `tests/test_s2_lookup.py` (append)

**Interfaces:**
- Consumes: `lookup_prototype_loads` (unchanged), `LoadPulses`
- Produces: `get_loads(building_type, climate_zone, floor_area_m2=None, envelope_factor=1.0) -> LoadPulses` — every load field scaled by `envelope_factor`, NaN-safe. Default 1.0 → byte-identical to today. Consumed by Task 3 (`app.py`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s2_lookup.py`:

```python
def test_get_loads_envelope_factor_default_is_identity():
    from geosite.s2_simulation import get_loads
    base = get_loads("small_office", "5A")
    same = get_loads("small_office", "5A", envelope_factor=1.0)
    assert same.q_h == base.q_h
    assert same.q_m == base.q_m
    assert same.q_y == base.q_y


def test_get_loads_envelope_factor_scales_linearly():
    from geosite.s2_simulation import get_loads
    base = get_loads("small_office", "5A")
    x2 = get_loads("small_office", "5A", envelope_factor=2.0)
    assert x2.q_h == pytest.approx(2.0 * base.q_h)
    assert x2.q_m == pytest.approx(2.0 * base.q_m)
    assert x2.q_y == pytest.approx(2.0 * base.q_y)


def test_get_loads_envelope_factor_nan_safe():
    from geosite.s2_simulation import get_loads
    loads = get_loads("small_office", "5A", envelope_factor=2.0)
    # cross-mode fields either scale or stay NaN — never crash
    for v in (loads.q_h_heat, loads.q_h_cool):
        assert (v != v) or isinstance(v, float)
```

(Adjust the `pytest` import at the top of the file if not already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_s2_lookup.py -v -k envelope`
Expected: FAIL with `TypeError: get_loads() got an unexpected keyword argument 'envelope_factor'`

- [ ] **Step 3: Implement the scaling**

In `geosite/s2_simulation/__init__.py`, replace the `get_loads` function with:

```python
def get_loads(
    building_type: str,
    climate_zone: str,
    floor_area_m2: float | None = None,
    envelope_factor: float = 1.0,
) -> LoadPulses:
    """Return three-pulse ground loads for a DOE prototype building.

    Parameters
    ----------
    building_type   : DOE prototype key, e.g. "small_office", "medium_office"
    climate_zone    : ASHRAE climate zone, e.g. "5A", "3B", "2A"
    floor_area_m2   : user building floor area [m²].  If None, returns values
                      at the prototype reference area.
    envelope_factor : building-design load multiplier (WWR × envelope ×
                      glazing, from s2_simulation.envelope). 1.0 = prototype
                      baseline; placeholder until calibrated values land.

    Returns
    -------
    LoadPulses with sign convention: negative=heating, positive=cooling.
    """
    loads = lookup_prototype_loads(building_type, climate_zone,
                                   target_area_m2=floor_area_m2)
    if envelope_factor == 1.0:
        return loads

    def _s(v: float) -> float:
        return v * envelope_factor if v == v else float("nan")

    return LoadPulses(
        q_h=_s(loads.q_h),
        q_m=_s(loads.q_m),
        q_y=_s(loads.q_y),
        q_h_heat=_s(loads.q_h_heat),
        q_m_heat=_s(loads.q_m_heat),
        q_h_cool=_s(loads.q_h_cool),
        q_m_cool=_s(loads.q_m_cool),
    )
```

(Verify the `LoadPulses` field list against `geosite/models.py` before committing — the constructor call must name exactly the fields `app.py` names in its own re-scaling block at lines ~233–241.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_s2_lookup.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add geosite/s2_simulation/__init__.py tests/test_s2_lookup.py
git commit -m "feat(s2): get_loads accepts envelope_factor load multiplier"
```

---

## Task 3: API Wiring — Both Calculate Endpoints + Strategy

**Files:**
- Modify: `app.py` (`calculate` ~lines 27–78; `calculate_smart` ~lines 132–339; `strategy_api` ~lines 618–697)
- Modify: `geosite/s6_strategy/strategy.py` (`run_strategy` signature + scale line)
- Test: `tests/test_api_envelope.py` (create)

**Interfaces:**
- Consumes: `compute_envelope_factor`, option frozensets (Task 1); `get_loads(envelope_factor=...)` (Task 2)
- Produces:
  - `POST /calculate/smart` — optional `wwr`/`envelope`/`glazing` (defaults `"medium"`/`"standard"`/`"double"`); invalid value → 400 field error; response `loads` dict gains `"wwr"`, `"envelope"`, `"glazing"`, `"envelope_factor"`.
  - `POST /calculate` (manual) — same three optional fields; factor multiplies the parsed `q_h`/`q_m`/`q_y`; response gains `"envelope_factor"`.
  - `POST /api/strategy` — optional `envelope_factor` (float, default 1.0, valid 0 < f ≤ 10) folded into the profile scale.
  - `run_strategy(..., envelope_factor: float = 1.0, ...)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_envelope.py`:

```python
"""Endpoint wiring for building-design parameters (all factors 1.0)."""

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


_SMART = {"zip_code": "60601", "building_type": "small_office",
          "NB": 16, "B": 6.0, "A": 9.0}

_MANUAL = {
    "q_h": 12000, "q_m": 6000, "q_y": 1500,
    "k": 2.0, "alpha": 0.086, "T_g": 15.0,
    "Cp": 4200, "mfls": 0.05, "T_in_HP": 40.2,
    "rbore": 0.06, "rpin": 0.01365, "rpext": 0.0167,
    "kgrout": 1.5, "kpipe": 0.42, "LU": 0.0511, "hconv": 1000,
    "B": 6.1, "NB": 5, "A": 1.0,
}

_STRATEGY = {"building_type": "small_office", "climate_zone": "5A",
             "k": 2.0, "alpha": 0.1, "T_g": 12.0, "NB": 16, "B": 6.0,
             "A": 9.0, "state": "IL"}


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_accepts_design_fields_and_echoes_factor(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    body = dict(_SMART, wwr="high", envelope="low", glazing="single")
    resp = client.post("/calculate/smart", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    loads = resp.get_json()["loads"]
    assert loads["wwr"] == "high"
    assert loads["envelope"] == "low"
    assert loads["glazing"] == "single"
    assert loads["envelope_factor"] == 1.0


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_result_identical_with_and_without_fields(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    r1 = client.post("/calculate/smart", data=json.dumps(_SMART),
                     content_type="application/json").get_json()
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    body = dict(_SMART, wwr="low", envelope="high", glazing="triple")
    r2 = client.post("/calculate/smart", data=json.dumps(body),
                     content_type="application/json").get_json()
    assert r1["L"] == r2["L"]
    assert r1["H"] == r2["H"]


def test_smart_rejects_unknown_wwr(client):
    body = dict(_SMART, wwr="enormous")
    resp = client.post("/calculate/smart", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "wwr"


def test_manual_accepts_design_fields_identity(client):
    base = client.post("/calculate", data=json.dumps(_MANUAL),
                       content_type="application/json").get_json()
    body = dict(_MANUAL, wwr="high", envelope="low", glazing="single")
    resp = client.post("/calculate", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["L"] == base["L"]
    assert data["envelope_factor"] == 1.0


def test_manual_rejects_unknown_glazing(client):
    body = dict(_MANUAL, glazing="quintuple")
    resp = client.post("/calculate", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "glazing"


def test_strategy_accepts_envelope_factor(client):
    body = dict(_STRATEGY, envelope_factor=1.0)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()


def test_strategy_rejects_nonpositive_envelope_factor(client):
    body = dict(_STRATEGY, envelope_factor=0)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_api_envelope.py -v`
Expected: FAILs — `wwr` key missing from `loads`, unknown values return 200, `envelope_factor` key missing

- [ ] **Step 3: Shared parse helper + import in `app.py`**

3a. Add to the imports (after line 12 `from geosite.s2_simulation import get_loads`):

```python
from geosite.s2_simulation.envelope import (
    WWR_OPTIONS, ENVELOPE_OPTIONS, GLAZING_OPTIONS, compute_envelope_factor,
)
```

3b. Below `_T_IN_HP_DEFAULTS` (~line 93), add the helper both endpoints use:

```python
def _parse_design_fields(data):
    """Return (wwr, envelope, glazing, envelope_factor) or a Flask 400 tuple."""
    wwr      = str(data.get("wwr", "medium")).strip().lower()
    envelope = str(data.get("envelope", "standard")).strip().lower()
    glazing  = str(data.get("glazing", "double")).strip().lower()
    for field, value, options in (("wwr", wwr, WWR_OPTIONS),
                                  ("envelope", envelope, ENVELOPE_OPTIONS),
                                  ("glazing", glazing, GLAZING_OPTIONS)):
        if value not in options:
            return None, (jsonify({"error": "field", "field": field,
                                   "message": f"'{field}' must be one of {sorted(options)}"}), 400)
    return (wwr, envelope, glazing, compute_envelope_factor(wwr, envelope, glazing)), None
```

- [ ] **Step 4: Wire `/calculate/smart`**

4a. After the `soil_confidence` parsing block (ends `k_factor = _CONFIDENCE_K_FACTORS[soil_confidence]`), add:

```python
    design, err = _parse_design_fields(data)
    if err:
        return err
    wwr, envelope, glazing, envelope_factor = design
```

4b. Change the s2 call:

```python
        loads: LoadPulses = get_loads(building_type, site.climate_zone,
                                      floor_area_m2=floor_area_m2)
```

to:

```python
        loads: LoadPulses = get_loads(building_type, site.climate_zone,
                                      floor_area_m2=floor_area_m2,
                                      envelope_factor=envelope_factor)
```

4c. In the response `"loads"` dict, after `"floor_area_m2": floor_area_m2,` add:

```python
            "wwr": wwr,
            "envelope": envelope,
            "glazing": glazing,
            "envelope_factor": envelope_factor,
```

- [ ] **Step 5: Wire manual `/calculate`**

5a. In `calculate()`, immediately after the 19-field parse loop (before `# --- validate ranges ---`), add:

```python
    design, err = _parse_design_fields(data)
    if err:
        return err
    wwr, envelope, glazing, envelope_factor = design
    for f in ("q_h", "q_m", "q_y"):
        values[f] *= envelope_factor
```

5b. Extend the response:

```python
    return jsonify({"L": round(L), "H": round(L / values["NB"]), "NB": values["NB"]})
```

→

```python
    return jsonify({"L": round(L), "H": round(L / values["NB"]),
                    "NB": values["NB"], "envelope_factor": envelope_factor})
```

- [ ] **Step 6: Wire `/api/strategy` and `run_strategy`**

6a. In `strategy_api`, after the `year_factor` parsing block, add:

```python
    envelope_factor = 1.0
    if data.get("envelope_factor") not in (None, ""):
        try:
            envelope_factor = float(data["envelope_factor"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "envelope_factor",
                            "message": "envelope_factor must be a number"}), 400
    if not (0.0 < envelope_factor <= 10.0):
        return jsonify({"error": "field", "field": "envelope_factor",
                        "message": "envelope_factor must be in (0, 10]"}), 400
```

and add `envelope_factor=envelope_factor,` to the `run_strategy(...)` call (after `year_factor=year_factor,`).

6b. In `geosite/s6_strategy/strategy.py`, add the parameter to `run_strategy` (after `year_factor: float = 1.0,`):

```python
    envelope_factor: float = 1.0,
```

and change the scale line:

```python
    scale = year_factor
```

to:

```python
    scale = year_factor * envelope_factor
```

Also add one line to the docstring: `envelope_factor: building-design load multiplier (WWR x envelope x glazing); 1.0 until calibrated.`

- [ ] **Step 7: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_api_envelope.py tests/test_pipeline_integration.py tests/test_s5_api.py tests/test_s6_strategy.py -v`
Expected: all PASS (identity at factor 1.0 keeps every existing number unchanged)

Then full suite: `source venv/bin/activate && python -m pytest tests/ -v` — no new failures beyond the 5 pre-existing.

- [ ] **Step 8: Commit**

```bash
git add app.py geosite/s6_strategy/strategy.py tests/test_api_envelope.py
git commit -m "feat(api): wwr/envelope/glazing fields wired through both endpoints and strategy"
```

---

## Task 4: UI — Building Design Card (Smart + Manual)

**Files:**
- Modify: `templates/index.html`
- Modify: `static/main.js`
- Modify: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 3's API contract
- Produces: DOM ids `s_wwr`, `s_envelope`, `s_glazing` (smart) and `wwr`, `envelope`, `glazing` (manual), all added to `REQUIRED_IDS`; smart body and manual payload include the three values; `fetchStrategy` forwards `envelope_factor` from the smart response.

- [ ] **Step 1: Add the new ids to the regression suite**

In `tests/test_ui_template.py`, extend `REQUIRED_IDS` — after `"s_B", "s_A", "s_T_in_HP", "s_mfls",` add:

```python
    "s_wwr", "s_envelope", "s_glazing",
    "wwr", "envelope", "glazing",
```

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: exactly 6 FAILs (the new ids)

- [ ] **Step 2: Add the Smart Mode card**

In `templates/index.html`, between the s2 Building card's closing `</div>` (after the `year_built` field, line ~133) and the `<!-- s4: Borefield geometry (still user input) -->` comment, insert:

```html
        <!-- s2b: Building Design (efficiency multipliers — neutral until calibrated) -->
        <div class="stage-header">
          <span class="stage-pill">s2</span>
          <span class="stage-label">Building Design</span>
          <span class="stage-note">Efficiency multipliers pending calibration — all options currently neutral (×1.00)</span>
        </div>
        <div class="card">
          <div class="field">
            <label for="s_wwr">Window-Wall Ratio <span class="hint-inline">— share of wall area that is glass</span></label>
            <div class="input-row">
              <select id="s_wwr" name="s_wwr">
                <option value="low">Low (&le; 20%)</option>
                <option value="medium" selected>Medium (30&ndash;40%, prototype baseline)</option>
                <option value="high">High (&ge; 50%)</option>
              </select>
            </div>
            <span class="field-error" data-for="s_wwr"></span>
          </div>
          <div class="field">
            <label for="s_envelope">Envelope Efficiency <span class="hint-inline">— insulation and air sealing</span></label>
            <div class="input-row">
              <select id="s_envelope" name="s_envelope">
                <option value="high">High performance</option>
                <option value="standard" selected>Standard (code baseline)</option>
                <option value="low">Low performance</option>
              </select>
            </div>
            <span class="field-error" data-for="s_envelope"></span>
          </div>
          <div class="field">
            <label for="s_glazing">Glazing Type <span class="hint-inline">— glass quality</span></label>
            <div class="input-row">
              <select id="s_glazing" name="s_glazing">
                <option value="triple">Triple-pane</option>
                <option value="double" selected>Double-pane (standard)</option>
                <option value="single">Single-pane</option>
              </select>
            </div>
            <span class="field-error" data-for="s_glazing"></span>
          </div>
        </div>
```

- [ ] **Step 3: Add the Manual Mode card**

In `#tab-basic`, immediately after the "Ground Loads" card's closing `</div>`, insert:

```html
            <div class="card">
              <h2 class="card-title">Building Design</h2>
              <p class="hint">Load multipliers — all options currently neutral (&times;1.00) pending calibration.</p>
              <div class="field">
                <label for="wwr">Window-Wall Ratio</label>
                <div class="input-row">
                  <select id="wwr" name="wwr">
                    <option value="low">Low (&le; 20%)</option>
                    <option value="medium" selected>Medium (30&ndash;40%)</option>
                    <option value="high">High (&ge; 50%)</option>
                  </select>
                </div>
                <span class="field-error" data-for="wwr"></span>
              </div>
              <div class="field">
                <label for="envelope">Envelope Efficiency</label>
                <div class="input-row">
                  <select id="envelope" name="envelope">
                    <option value="high">High performance</option>
                    <option value="standard" selected>Standard</option>
                    <option value="low">Low performance</option>
                  </select>
                </div>
                <span class="field-error" data-for="envelope"></span>
              </div>
              <div class="field">
                <label for="glazing">Glazing Type</label>
                <div class="input-row">
                  <select id="glazing" name="glazing">
                    <option value="triple">Triple-pane</option>
                    <option value="double" selected>Double-pane (standard)</option>
                    <option value="single">Single-pane</option>
                  </select>
                </div>
                <span class="field-error" data-for="glazing"></span>
              </div>
            </div>
```

- [ ] **Step 4: Update `static/main.js`**

4a. In the smart submit handler, extend the body — after the `soil_confidence:` line inside the `body` object literal, add:

```js
      wwr:             document.getElementById('s_wwr').value,
      envelope:        document.getElementById('s_envelope').value,
      glazing:         document.getElementById('s_glazing').value,
```

4b. In `collectManualInputs`, extend the field list:

```js
      'B', 'NB', 'A',
```

→

```js
      'B', 'NB', 'A',
      'wwr', 'envelope', 'glazing',
```

(the generic `#sizing-form [name=...]` selector already picks up `<select>` elements).

4c. In `fetchStrategy`, add to the `payload` object literal (after `year_factor:`):

```js
      envelope_factor: smartRes.loads.envelope_factor || 1.0,
```

- [ ] **Step 5: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS

- [ ] **Step 6: Manual browser check**

Run `source venv/bin/activate && flask --app app run --port 5000`, open `http://127.0.0.1:5000`:
1. Smart Mode shows the Building Design card between Building and Borefield Geometry with three dropdowns defaulting to Medium / Standard / Double-pane.
2. ZIP `60601` + Small Office with any dropdown combination → identical L/H/NB to the defaults (factors are 1.0).
3. Manual Mode Basic tab shows the same three selects; Calculate returns the same L as before.
Stop the server.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/main.js tests/test_ui_template.py
git commit -m "feat(ui): building design dropdowns (WWR, envelope, glazing)"
```

---

## Task 5: Dev Dashboard Trace

**Files:**
- Modify: `templates/dev.html` (trace-row ~lines 233–256; `#t-run` handler ~lines 1292–1307; s2 trace render ~lines 1360–1367)

**Interfaces:**
- Consumes: Task 3's smart response (`loads.wwr` etc.)
- Produces: trace-row selects `t-wwr`, `t-envelope`, `t-glazing`; s2 input/output panels show the received values and the factor.

- [ ] **Step 1: Add the trace-row selects**

In `templates/dev.html`, after the Soil Confidence `trace-field` div (ends line ~251), add:

```html
          <div class="trace-field">
            <label>WWR</label>
            <select id="t-wwr">
              <option value="low">Low</option>
              <option value="medium" selected>Medium</option>
              <option value="high">High</option>
            </select>
          </div>
          <div class="trace-field">
            <label>Envelope</label>
            <select id="t-envelope">
              <option value="high">High perf</option>
              <option value="standard" selected>Standard</option>
              <option value="low">Low perf</option>
            </select>
          </div>
          <div class="trace-field">
            <label>Glazing</label>
            <select id="t-glazing">
              <option value="triple">Triple</option>
              <option value="double" selected>Double</option>
              <option value="single">Single</option>
            </select>
          </div>
```

- [ ] **Step 2: Send the values in the trace body**

In the `#t-run` handler, extend the `body` object — after the `soil_confidence:` line, add:

```js
      wwr:             document.getElementById('t-wwr').value,
      envelope:        document.getElementById('t-envelope').value,
      glazing:         document.getElementById('t-glazing').value,
```

- [ ] **Step 3: Show received values in the s2 trace**

In the s2 render block, replace:

```js
    document.getElementById('s2-in').innerHTML =
      kv('building_type',  body.building_type) +
      kv('climate_zone',   s.climate_zone) +
      kv('floor_area_m2',  floorNote) +
      kv('year_built',     yearNote) +
      kv('source',         'data/public/prototype_loads.json (EnergyPlus pre-computed)');
```

with:

```js
    document.getElementById('s2-in').innerHTML =
      kv('building_type',  body.building_type) +
      kv('climate_zone',   s.climate_zone) +
      kv('floor_area_m2',  floorNote) +
      kv('year_built',     yearNote) +
      kv('wwr / envelope / glazing', `${l.wwr ?? '—'} / ${l.envelope ?? '—'} / ${l.glazing ?? '—'}`) +
      kv('envelope_factor', l.envelope_factor != null ? `×${l.envelope_factor.toFixed(2)} (placeholder — awaiting calibration)` : '×1.00') +
      kv('source',         'data/public/prototype_loads.json (EnergyPlus pre-computed)');
```

- [ ] **Step 4: Verify**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v` (pins `/dev` still renders).
Then run the app, open `/dev`, run a trace with non-default dropdowns, confirm the s2 Input panel shows the three values and `×1.00`. Stop the server.

- [ ] **Step 5: Full suite + commit**

Run: `source venv/bin/activate && python -m pytest tests/ -v` — no new failures beyond the 5 pre-existing.

```bash
git add templates/dev.html
git commit -m "feat(dev): building design values in pipeline trace"
```

---

## Self-Review Notes

- Spec coverage: professor's four examples — WWR (Task 1 table + UI), envelope tightness (Task 1 table + UI), glass quality (Task 1 table + UI), borehole depth target (already an input, `s_H_min`; owned by the companion footprint plan, not duplicated here). All factors 1.0; the only future edit point is the three dicts in `envelope.py`.
- Scope discipline: no physics invented (memory rule: No Invented Methods). Identity tests pin that responses are byte-identical with and without the new fields.
- Consistency: the factor reaches s4 via `get_loads` and s6 via `run_strategy`'s profile scale, so sizing and strategy always see the same loads; `main.js` forwards `envelope_factor` from the smart response into the strategy payload.
- This plan feeds the 2026-07-13 input-spreadsheet deliverable: the three dropdowns + defaults are three of the ~10–15 inputs the professor asked to review.
- Sequencing: independent of `2026-07-06-nb-from-footprint.md`, but run AFTER it — both edit `calculate_smart` and `index.html`, and the footprint plan's snippets assume the pre-envelope file state. If run first instead, apply this plan's Step 4a (Task 3) insertion point relative to whatever the parse block looks like (it anchors on the `soil_confidence` block, which neither plan moves).

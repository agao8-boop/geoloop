# Staged Pipeline UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Smart Mode from a single-form-submit into a two-stage pipeline wizard. Stage 1 (ZIP + building inputs → "Analyze Site & Loads →") returns soil properties, ground loads, and the footprint-derived NB range. Only then does Stage 2 unlock (borefield geometry → "Size Borefield →"), which runs the NB optimizer and returns the sizing. **NB is never a user input** — it is always computed from footprint geometry + load iteration. The only exception is a deliberately buried "Expert: fix borehole count" toggle (2 clicks to reach, clearly labeled not-recommended). The dev tool gains the same stage separation with all intermediates exposed.

**Architecture:** Two new stateless endpoints, `/calculate/stage1` and `/calculate/stage2`, built by extracting the s1/s2 half and the s4 half of the existing `/calculate/smart` handler into shared helpers (`_resolve_site_and_loads`, `_run_sizing`). `/calculate/smart` keeps its exact request/response contract (dev tool and `tests/test_api_footprint.py` depend on it) by calling the same two helpers back-to-back. State between stages lives client-side in one module-level variable (`let stage1Result = null`) — Stage 2 echoes the Stage 1 numbers back to the server, so no session/cache is needed and a page refresh cleanly resets the wizard. No physics code changes: `footprint.py`, `ashrae_sizing.py`, `strategy.py` are called exactly as today, just from a reorganized surface.

**Tech Stack:** Flask (app.py), vanilla JS (no framework), plain CSS on the existing token system (`--accent: #0e7c5b` etc.), Jinja2 templates, pytest + Flask test client.

## Global Constraints

- **NB is ALWAYS auto-computed.** `compute_nb_range(floor_area_m2, building_type, spacing_m)` sets [nb_min, nb_max]; `find_optimal_nb(...)` sweeps it. The expert override lives behind a `<details>` + enable-checkbox (2 clicks) at the very bottom of Step 2, never as a normal field.
- **H_min (default 125 m, range 30–300 in the API, practitioner range 100–150) is the primary Stage 2 control** (professor directive 2026-07-06: "flip inputs — depth is primary, NB is the output").
- **Do not change `/calculate/smart`'s request or response shape.** `templates/dev.html` posts to it and `tests/test_api_footprint.py` pins it. Refactor its internals only.
- **Manual Mode is untouched.** No changes to `#panel-manual`, `/calculate`, or the manual JS handler.
- **No new Python physics.** Only `app.py` (routing/validation), templates, JS, CSS, and tests change.
- **Vanilla JS only.** Wizard state = module-level `stage1Result` variable + CSS class toggling. No React/Vue/Alpine, no build step.
- **Style consistency:** reuse `stage-header`, `stage-pill`, `card`, `stat-card`, `pipeline-panel`, `two-pass`, `callout` patterns and the existing tokens. New classes added: `wizard-step`, `step-locked`, `step-status`, `expert-toggle`.
- Editing ANY Step 1 input after Stage 1 has run must invalidate downstream state: re-lock Step 2, hide all result panels (`stage1-result`, `smart-result`, `cost-section`, `s6-section`).
- DOM ids that are REMOVED from index.html: `smart-btn`, `smart-error`, `pipeline-panel` (replaced by `stage1-btn`/`stage2-btn`, `stage1-error`/`stage2-error`, `stage1-result`). `tests/test_ui_template.py` `REQUIRED_IDS` must be updated in the same task that changes the markup.
- Run tests with: `source venv/bin/activate && python -m pytest tests/ -v` (full suite before every commit).
- No comments in code unless the WHY is non-obvious.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `app.py` | Extract `_resolve_site_and_loads` + `_run_sizing` helpers; add `/calculate/stage1`, `/calculate/stage2`; `/calculate/smart` re-implemented on the helpers with identical contract |
| Create | `tests/test_api_stage1.py` | Stage 1 endpoint contract |
| Create | `tests/test_api_stage2.py` | Stage 2 endpoint contract + stage1→stage2 chain parity with `/calculate/smart` |
| Modify | `templates/index.html` | Smart panel → two `wizard-step` sections; Stage-1 results panel with NB-range card; expert NB toggle; Step 2 locked by default |
| Modify | `static/style.css` | `wizard-step`, `step-locked`, `step-status`, `expert-toggle` classes |
| Modify | `static/main.js` | `stage1Result` state machine: `runStage1`, `renderStage1`, `runStage2`, `renderStage2`, `unlockStep2`, `lockStep2`, `invalidateStage1` |
| Modify | `templates/dev.html` | STAGE 1 / STAGE 2 band headers; new s4a "Footprint NB Range & Optimal NB" card; nb_source rendering |
| Modify | `tests/test_ui_template.py` | Update `REQUIRED_IDS`; add dev-dashboard id checks |

Current-state facts this plan builds on (verified by reading the code):

- `/calculate/smart` (app.py lines 158–428) already does everything: s1 `get_site_data`, s2 `get_loads` + year/envelope factors, `compute_nb_range`, two-pass `find_optimal_nb` / `size_borefield`, and returns `site`, `loads`, `nb_min`, `nb_max`, `footprint`, `H_min`, `governing`, `L_heat`, `L_cool`, `imbalance_m`, `solar_thermal_recommended`. The staged endpoints are a straight split of this handler.
- The `loads` payload of `/calculate/smart` includes `q_h_heat`/`q_h_cool` but NOT `q_m_heat`/`q_m_cool` — Stage 1's response must add those two so Stage 2 can run the two-pass sizing without re-simulating.
- `compute_nb_range` takes `spacing_m` (= B). B is a Stage 2 input, so Stage 1 reports the NB range at the default B = 6.0 m labeled as an estimate, and Stage 2 recomputes the range with the user's actual B before optimizing.
- `find_optimal_nb` falls back to `size_borefield_for_depth(H_target=H_min)` when no in-range NB satisfies H ≥ H_min; callers detect this as `nb_opt < nb_min`. The response gains an explicit `nb_source` field so the UI stops inferring this from a comparison.
- main.js currently has one `smartBtn` handler doing everything (lines 95–280), then `fetchCostEstimate` → `fetchStrategy` chained off the result. The chain survives; only its trigger moves to the end of `renderStage2`, and s6/strategy payload fields now come from `stage1Result` instead of the combined response.
- dev.html's Run Trace (`#t-run`, lines 1316–1597) posts once to `/calculate/smart` and fills `s1a/s1b/s2/s4/s5/s6` cards. It keeps that single call — the dev changes are presentation only (stage bands + one new card).

---

## Task 1: Staged API Endpoints (`/calculate/stage1`, `/calculate/stage2`)

**Files:**
- Modify: `app.py`
- Create: `tests/test_api_stage1.py`
- Create: `tests/test_api_stage2.py`

**Interfaces:**
- Produces: `_resolve_site_and_loads(data) -> (payload_dict | None, error_response | None)` and `_run_sizing(sizing_in) -> (result_dict | None, error_response | None)` module-level helpers in `app.py`; routes `POST /calculate/stage1`, `POST /calculate/stage2`.
- Consumes: `get_site_data`, `get_loads`, `compute_nb_range`, `find_optimal_nb`, `size_borefield`, `_parse_design_fields`, `_year_to_load_factor`, `_ADVANCED_DEFAULTS`, `_T_IN_HP_DEFAULTS` — all existing.
- Guarantee: `/calculate/smart` request/response unchanged (`tests/test_api_footprint.py` stays green untouched).

### Endpoint contracts (exact)

**`POST /calculate/stage1`**

Request body:

```json
{
  "zip_code": "60601",            // required, 5-digit string
  "building_type": "small_office",// required, key in BUILDING_FLOORS
  "floor_area_m2": 2000,          // optional; null/absent = DOE prototype area
  "year_built": 2005,             // optional int; 0 = new/planned; default 2020
  "soil_confidence": "low",       // optional; low|medium|high; default "low"
  "wwr": "medium", "envelope": "standard", "glazing": "double"  // optional
}
```

Success 200:

```json
{
  "site": { /* identical shape to /calculate/smart's "site" object:
              k, k_effective, soil_confidence, alpha, T_g, climate_zone,
              state_abbrev, data_available, rock_class, k_min, k_max,
              shallow_soil_class, k_shallow */ },
  "loads": { /* /calculate/smart's "loads" shape PLUS q_m_heat and q_m_cool
               (null when the per-mode split is unavailable):
               q_h, q_m, q_y, q_h_heat, q_m_heat, q_h_cool, q_m_cool,
               mode, year_built, year_factor, floor_area_m2,
               wwr, envelope, glazing, envelope_factor */ },
  "nb_estimate": {
    "nb_min": 2, "nb_max": 25,
    "spacing_m": 6.0,
    "footprint": { /* meta dict from compute_nb_range: footprint_m2, n_floors,
                     floor_area_m2, width_m, length_m, perimeter_m, spacing_m,
                     aspect, prototype_area_used */ },
    "note": "estimated at default 6.0 m spacing; recomputed in stage 2"
  }
}
```

Errors: same conventions as `/calculate/smart` — 400 `{"error":"field","field":...,"message":...}`, 422 `{"error":"geocode"| "no_site_data", ...}`. No sizing keys (`L`, `H`, `NB`) appear anywhere in this response.

**`POST /calculate/stage2`** (stateless — client echoes stage 1 outputs back)

Request body:

```json
{
  "building_type": "small_office",   // required (for nb-range recompute)
  "floor_area_m2": 2000,             // optional, same semantics as stage 1
  "site":  {"k_effective": 2.1, "alpha": 0.086, "T_g": 12.4},  // required; extra keys ignored
  "loads": {"q_h": -60000, "q_m": -25000, "q_y": -4000,
            "q_h_heat": -60000, "q_m_heat": -25000,
            "q_h_cool": 41000,  "q_m_cool": 17000},             // required; per-mode keys may be null
  "H_min": 125.0,                    // optional, default 125, validated 30–300
  "B": 6.0,                          // optional, default 6.0, must be > 0
  "A": 9.0,                          // optional, default 9.0, must be >= 1
  "NB": 24,                          // EXPERT OVERRIDE ONLY; omitted in normal flow
  "T_in_HP_heat": 5.0, "T_in_HP_cool": 40.2, "T_in_HP": null,   // optional
  "mfls": 0.05, "Cp": 4200, "rbore": 0.06                       // optional advanced, all _ADVANCED_DEFAULTS keys accepted
}
```

Success 200:

```json
{
  "L": 3120, "H": 130, "NB": 24,
  "nb_min": 2, "nb_max": 25,          // recomputed with the submitted B; null when NB override used
  "H_min": 125.0,                     // null when NB override used
  "footprint": { /* meta */ },        // null when NB override used
  "nb_source": "optimizer",           // "optimizer" | "depth_fallback" | "expert_override"
  "governing": "heating",
  "L_heat": 3120, "L_cool": 1840,     // null when single-pass
  "imbalance_m": 1280,
  "solar_thermal_recommended": true
}
```

`nb_source` values: `"expert_override"` when `NB` was in the request; `"depth_fallback"` when `find_optimal_nb` returned `nb_opt < nb_min`; `"optimizer"` otherwise.

Validation errors (400, `{"error":"field", "field":..., "message":...}`):
- `site` missing or `site.k_effective`/`site.alpha`/`site.T_g` missing/non-finite → field `"site"`, message `"Stage 1 result is missing or corrupt — run Analyze Site & Loads again"`.
- `loads` missing or `q_h`/`q_m`/`q_y` missing/non-finite → field `"loads"`, same guidance.
- `H_min` outside 30–300 → field `"H_min"` (same message as `/calculate/smart`).
- `A < 1` → field `"A"`; `B <= 0` → field `"B"`; `NB < 1` or non-integer → field `"NB"`.
- unknown `building_type` → field `"building_type"` (from `compute_nb_range`'s KeyError).

### Steps

- [ ] **Step 1: Write the Stage 1 tests (they fail — endpoint doesn't exist)**

Create `tests/test_api_stage1.py`. Reuse the geocode-mock pattern from `tests/test_api_footprint.py` (`_make_geocode_mocks`, `@patch("geosite.s1_site.geocode.requests.get")`, GEOID `"17031320101"`):

```python
"""API tests: /calculate/stage1 — site + loads + NB range, no sizing."""

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


_BASE = {"zip_code": "60601", "building_type": "small_office"}


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_returns_site_loads_and_nb_estimate(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1", data=json.dumps(_BASE),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert set(data) == {"site", "loads", "nb_estimate"}
    assert data["site"]["k_effective"] > 0
    for key in ("q_h", "q_m", "q_y", "q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"):
        assert key in data["loads"]
    est = data["nb_estimate"]
    assert est["nb_min"] == 2 and est["nb_max"] == 25   # small_office proto, B=6.0
    assert est["spacing_m"] == 6.0
    assert est["footprint"]["n_floors"] == 1


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_never_returns_sizing_keys(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1", data=json.dumps(_BASE),
                       content_type="application/json")
    data = resp.get_json()
    for forbidden in ("L", "H", "NB"):
        assert forbidden not in data


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_floor_area_scales_range(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1",
                       data=json.dumps(dict(_BASE, floor_area_m2=1022.0)),
                       content_type="application/json")
    est = resp.get_json()["nb_estimate"]
    assert (est["nb_min"], est["nb_max"]) == (2, 35)


def test_stage1_requires_zip_and_building_type(client):
    for missing in ("zip_code", "building_type"):
        body = dict(_BASE)
        del body[missing]
        resp = client.post("/calculate/stage1", data=json.dumps(body),
                           content_type="application/json")
        assert resp.status_code == 400
        assert resp.get_json()["field"] == missing
```

- [ ] **Step 2: Write the Stage 2 tests (they fail)**

Create `tests/test_api_stage2.py`. Stage 2 needs no geocode mock (stateless). Include the chain-parity test — it is the key regression:

```python
"""API tests: /calculate/stage2 — NB optimization from echoed stage-1 numbers."""

import json
from unittest.mock import patch, MagicMock
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


_SITE  = {"k_effective": 1.8, "alpha": 0.086, "T_g": 12.0}
_LOADS = {"q_h": -60000.0, "q_m": -25000.0, "q_y": -4000.0,
          "q_h_heat": -60000.0, "q_m_heat": -25000.0,
          "q_h_cool": 41000.0,  "q_m_cool": 17000.0}
_BASE  = {"building_type": "small_office", "site": _SITE, "loads": _LOADS}


def _post(client, body):
    return client.post("/calculate/stage2", data=json.dumps(body),
                       content_type="application/json")


def test_stage2_computes_nb_from_footprint(client):
    resp = _post(client, _BASE)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["nb_source"] in ("optimizer", "depth_fallback")
    assert data["NB"] >= 1
    assert data["nb_min"] == 2 and data["nb_max"] == 25
    assert data["H"] == pytest.approx(data["L"] / data["NB"], abs=1.0)


def test_stage2_spacing_changes_nb_range(client):
    resp = _post(client, dict(_BASE, B=3.0))
    data = resp.get_json()
    assert data["nb_max"] > 25          # tighter spacing fits more boreholes


def test_stage2_expert_override_fixes_nb(client):
    resp = _post(client, dict(_BASE, NB=16))
    data = resp.get_json()
    assert data["NB"] == 16
    assert data["nb_source"] == "expert_override"
    assert data["nb_min"] is None and data["nb_max"] is None


def test_stage2_single_pass_when_mode_split_null(client):
    loads = dict(_LOADS, q_h_heat=None, q_m_heat=None, q_h_cool=None, q_m_cool=None)
    resp = _post(client, dict(_BASE, loads=loads))
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["L_heat"] is None and data["L_cool"] is None
    assert data["governing"] == "heating"   # q_h < 0


def test_stage2_rejects_missing_stage1_echo(client):
    for missing in ("site", "loads"):
        body = {k: v for k, v in _BASE.items() if k != missing}
        resp = _post(client, body)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == missing


def test_stage2_rejects_out_of_range_h_min(client):
    resp = _post(client, dict(_BASE, H_min=1000))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "H_min"


def _make_geocode_mocks(geoid):
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None
    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    tract_resp.raise_for_status.return_value = None
    return [zip_resp, tract_resp]


@patch("geosite.s1_site.geocode.requests.get")
def test_stage_chain_matches_smart_endpoint(mock_get, client):
    """stage1 → stage2 must reproduce /calculate/smart exactly."""
    smart_body = {"zip_code": "60601", "building_type": "small_office",
                  "B": 6.0, "A": 9.0, "H_min": 125.0}

    mock_get.side_effect = _make_geocode_mocks("17031320101")
    smart = client.post("/calculate/smart", data=json.dumps(smart_body),
                        content_type="application/json").get_json()

    mock_get.side_effect = _make_geocode_mocks("17031320101")
    s1 = client.post("/calculate/stage1",
                     data=json.dumps({"zip_code": "60601",
                                      "building_type": "small_office"}),
                     content_type="application/json").get_json()
    s2 = _post(client, {"building_type": "small_office",
                        "site": s1["site"], "loads": s1["loads"],
                        "B": 6.0, "A": 9.0, "H_min": 125.0}).get_json()

    for key in ("L", "H", "NB", "governing", "L_heat", "L_cool",
                "nb_min", "nb_max", "imbalance_m", "solar_thermal_recommended"):
        assert s2[key] == smart[key], f"{key}: chain={s2[key]} smart={smart[key]}"
```

Run: `source venv/bin/activate && python -m pytest tests/test_api_stage1.py tests/test_api_stage2.py -v`
Expected: all FAIL with 404s (endpoints missing).

- [ ] **Step 3: Refactor `app.py` — extract the two halves of `calculate_smart`**

3a. Add `_resolve_site_and_loads(data)` above `calculate_smart`. Move into it, verbatim, the code currently at app.py lines ~181–307 minus the NB/B/A/H_min parsing: zip/building_type required-field checks, `floor_area_m2` + `year_built` + `soil_confidence` parsing, `_parse_design_fields`, `get_site_data` (+ geocode/no-data 422s), `get_loads`, year-factor scaling of the `LoadPulses`, dominant-mode detection, and the effective-k confidence logic. Return signature:

```python
def _resolve_site_and_loads(data):
    """Shared s1+s2 half of the pipeline. Returns (payload, None) or (None, error_response).

    payload = {
        "site": {...},          # exact dict /calculate/smart returns under "site"
        "loads": {...},         # smart's "loads" dict + q_m_heat/q_m_cool (NaN → None)
        "building_type": str,
        "floor_area_m2": float | None,
        "effective_k": float,   # unrounded, for sizing
        "loads_obj": LoadPulses # unrounded, for sizing
    }
    """
```

NaN-safe serialization for the four per-mode keys: `None if v != v else v`.

3b. Add `_run_sizing(...)` containing the code currently at lines ~309–397 (nb-range computation, two-pass vs single-pass branch, `find_optimal_nb`/`size_borefield` calls, imbalance metrics):

```python
def _run_sizing(*, q_pulses, effective_k, alpha, T_g, building_type,
                floor_area_m2, NB, H_min, B, A, params, data):
    """Shared s4 half. q_pulses = dict with q_h..q_m_cool (None allowed for mode split).
    Returns (result_dict, None) or (None, error_response).
    result_dict keys: L, H, NB, nb_min, nb_max, H_min, footprint, nb_source,
    governing, L_heat, L_cool, imbalance_m, solar_thermal_recommended.
    """
```

Inside, set `nb_source`:
- `"expert_override"` if `NB is not None` (and set `nb_min = nb_max = footprint = None`, `H_min` key to `None`, matching current smart behavior);
- else after `find_optimal_nb`, `"depth_fallback"` if the returned `NB < nb_min` else `"optimizer"` (for two-pass, judge by the governing pass's NB).

`T_in_HP` resolution (`T_in_HP_heat`/`T_in_HP_cool`/`T_in_HP` from `data` with `_T_IN_HP_DEFAULTS`) stays inside `_run_sizing`; the two-pass condition becomes "all four per-mode pulse values are not None" (equivalent to today's NaN check after serialization).

3c. Re-implement `calculate_smart` as: parse `B`/`A`/`NB`/`H_min` exactly as today (same error messages/order) → `_resolve_site_and_loads(data)` → `_run_sizing(...)` → merge and jsonify with the EXACT current top-level shape. Drop `nb_source` and the two extra loads keys from the smart response only if any existing test pins the exact key set — check first; `test_api_footprint.py` asserts specific keys, not the full set, so ADDING `nb_source` and `q_m_heat`/`q_m_cool` is safe and preferred (keep responses convergent). Verify with the test run.

3d. Add the two routes:

```python
@app.route("/calculate/stage1", methods=["POST"])
def calculate_stage1():
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400
    payload, err = _resolve_site_and_loads(data)
    if err:
        return err
    try:
        nb_min, nb_max, fp_meta = compute_nb_range(
            payload["floor_area_m2"], payload["building_type"], spacing_m=6.0)
    except (KeyError, ValueError) as exc:
        return jsonify({"error": "field", "field": "building_type",
                        "message": str(exc)}), 400
    return jsonify({
        "site": payload["site"],
        "loads": payload["loads"],
        "nb_estimate": {
            "nb_min": nb_min, "nb_max": nb_max, "spacing_m": 6.0,
            "footprint": fp_meta,
            "note": "estimated at default 6.0 m spacing; recomputed in stage 2",
        },
    })
```

`calculate_stage2`: validate per the contract table above (site/loads echo checks first, then H_min/B/A/NB), build `q_pulses` from `data["loads"]`, resolve `params = {k: float(data.get(k, v)) for k, v in _ADVANCED_DEFAULTS.items()}`, call `_run_sizing(...)`, jsonify the result dict directly. Use `math.isfinite` for the echo checks (reject NaN/inf/strings via try/except float()).

- [ ] **Step 4: Run all API tests**

Run: `source venv/bin/activate && python -m pytest tests/test_api_stage1.py tests/test_api_stage2.py tests/test_api_footprint.py tests/test_api_envelope.py tests/test_pipeline_integration.py -v`
Expected: all PASS. The footprint suite passing proves `/calculate/smart` is unbroken; the chain-parity test proves the split is lossless.

- [ ] **Step 5: Run the full suite, then commit**

```bash
source venv/bin/activate && python -m pytest tests/ -v
git add app.py tests/test_api_stage1.py tests/test_api_stage2.py
git commit -m "feat(api): staged /calculate/stage1 + /calculate/stage2 endpoints on shared pipeline helpers"
```

---

## Task 2: Wizard Markup + CSS (index.html, style.css)

**Files:**
- Modify: `templates/index.html` (Smart panel only, lines ~55–243)
- Modify: `static/style.css` (append new classes)
- Modify: `tests/test_ui_template.py` (`REQUIRED_IDS`)

**Interfaces:**
- Produces DOM ids consumed by Task 3 JS: `wizard-step1`, `stage1-btn`, `stage1-error`, `stage1-result`, `pipeline-s1` (kept), `pipeline-s2` (kept), `pipeline-nb` (new), `step1-status`, `wizard-step2`, `stage2-btn`, `stage2-error`, `step2-status`, `expert-nb-details`, `expert-nb-enable`, plus all existing input ids unchanged (`zip_code`, `soil_confidence`, `building_type`, `floor_area_m2`, `year_built`, `s_wwr`, `s_envelope`, `s_glazing`, `s_H_min`, `s_B`, `s_A`, `s_T_in_HP`, `s_mfls`, `s_NB`).
- Removes ids: `smart-btn`, `smart-error`, `pipeline-panel`.

- [ ] **Step 1: Update the id regression suite FIRST**

In `tests/test_ui_template.py` `REQUIRED_IDS`: remove `"smart-error"`, `"smart-btn"`, `"pipeline-panel"`; add:

```python
    "wizard-step1", "stage1-btn", "stage1-error", "stage1-result",
    "pipeline-nb", "step1-status",
    "wizard-step2", "stage2-btn", "stage2-error", "step2-status",
    "expert-nb-details", "expert-nb-enable",
```

Run the suite — expect exactly the new ids to FAIL.

- [ ] **Step 2: Restructure the Smart panel in `templates/index.html`**

Inside `<section id="panel-smart">`, wrap and reorder as follows (existing cards move verbatim unless noted):

```html
<!-- ── STEP 1: Site & Building Analysis ── -->
<div id="wizard-step1" class="wizard-step">
  <div class="stage-header">
    <span class="stage-pill">Step 1</span>
    <span class="stage-label">Site &amp; Building Analysis</span>
    <span class="step-status" id="step1-status"></span>
    <span class="stage-note">Everything the load model needs — no borefield inputs yet</span>
  </div>

  <!-- existing s1 stage-header + card (ZIP, soil_confidence)  : MOVE HERE UNCHANGED -->
  <!-- existing s2 stage-header + card (building_type, floor_area_m2, year_built) : UNCHANGED -->
  <!-- existing s2b stage-header + card (s_wwr, s_envelope, s_glazing) : UNCHANGED -->

  <div id="stage1-error" class="calc-error hidden"></div>
  <button type="button" id="stage1-btn" class="calc-btn">Analyze Site &amp; Loads &rarr;</button>

  <!-- Stage 1 results (hidden until success) -->
  <div id="stage1-result" class="pipeline-panel hidden">
    <div class="pipeline-step">
      <div class="pipeline-label">s1 — Site Data</div>
      <div class="pipeline-values" id="pipeline-s1">—</div>
    </div>
    <div class="pipeline-step">
      <div class="pipeline-label">s2–s3 — Ground Loads</div>
      <div class="pipeline-values" id="pipeline-s2">—</div>
    </div>
    <div class="pipeline-step">
      <div class="pipeline-label">Footprint — Borehole Capacity</div>
      <div class="pipeline-values" id="pipeline-nb">—</div>
    </div>
  </div>
</div>

<!-- ── STEP 2: Borefield Sizing (locked until Step 1 completes) ── -->
<div id="wizard-step2" class="wizard-step step-locked">
  <div class="stage-header">
    <span class="stage-pill">Step 2</span>
    <span class="stage-label">Borefield Sizing</span>
    <span class="step-status" id="step2-status">Complete Step 1 to unlock</span>
    <span class="stage-note">Borehole count is computed — you only set the geometry</span>
  </div>

  <!-- existing s4 borefield-geometry card (s_H_min, s_B, s_A) : MOVE HERE UNCHANGED,
       but change the s_H_min label to:
       "Minimum borehole depth — the primary sizing control; the optimizer picks the
        borehole count that hits this depth with the least total drilling" -->

  <!-- Advanced overrides: KEEP the details block but REMOVE the s_NB field from it.
       Only s_T_in_HP and s_mfls remain inside. -->

  <div id="stage2-error" class="calc-error hidden"></div>
  <button type="button" id="stage2-btn" class="calc-btn" disabled>Size Borefield &rarr;</button>

  <!-- Expert override — deliberately last, two clicks deep -->
  <details id="expert-nb-details" class="advanced-details expert-toggle">
    <summary>Expert: fix borehole count manually (not recommended)</summary>
    <div class="card" style="margin-top:12px">
      <div class="callout callout-warn">
        Fixing NB disables the footprint search and depth optimization. The tool exists
        to compute this number — only override it if you are validating against an
        external design.
      </div>
      <div class="field">
        <label>
          <input type="checkbox" id="expert-nb-enable"> Enable manual borehole count
        </label>
      </div>
      <div class="field">
        <label for="s_NB">Borehole count override</label>
        <div class="input-row">
          <input type="number" id="s_NB" name="s_NB" min="1" placeholder="auto from footprint" disabled>
          <span class="unit">—</span>
        </div>
        <span class="field-error" data-for="s_NB"></span>
      </div>
    </div>
  </details>
</div>

<!-- smart-result, cost-section, s6-section blocks: UNCHANGED, stay after wizard-step2 -->
```

Notes:
- `smart-result` stat label "Boreholes" becomes `Boreholes (auto-computed)`.
- Delete the old `smart-error` div, `smart-btn` button, and the old `pipeline-panel` block (its two inner ids move into `stage1-result` as shown).
- `s_NB` keeps its id/name (Task 3 JS and field-error mapping reuse them) but starts `disabled`.

- [ ] **Step 3: Append wizard classes to `static/style.css`**

```css
/* ── Staged wizard ── */
.wizard-step { margin-bottom: 8px; }

.wizard-step.step-locked {
  opacity: 0.45;
  pointer-events: none;
  user-select: none;
}

.step-status {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-faint);
  background: #eceff3;
  border-radius: 999px;
  padding: 2px 10px;
  white-space: nowrap;
}

.step-status.done {
  color: var(--accent);
  background: var(--accent-soft);
}

.expert-toggle { margin-top: 28px; }
.expert-toggle summary { font-size: 12px; color: var(--text-faint); }
.expert-toggle summary:hover { color: var(--warn); }
```

(`step-locked` uses `pointer-events: none` so nothing inside is clickable; the JS also sets `disabled` on `stage2-btn` for keyboard users.)

- [ ] **Step 4: Run tests**

`source venv/bin/activate && python -m pytest tests/test_ui_template.py -v` — all PASS.
Note: `static/main.js` still references the removed ids at this point, so the smart flow is broken in the browser until Task 3 lands. That is acceptable between commits within this plan; commit Tasks 2 and 3 back-to-back without deploying in between (or execute Tasks 2+3 before any manual verification).

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/style.css tests/test_ui_template.py
git commit -m "feat(ui): two-step wizard markup — step 2 locked, NB behind expert toggle"
```

---

## Task 3: JS State Machine (main.js)

**Files:**
- Modify: `static/main.js` (replace the smart-mode block, lines ~78–286; touch `fetchStrategy` payload source)

**Interfaces:**
- Consumes: Task 1 endpoints, Task 2 DOM ids.
- Produces: module-level `let stage1Result = null;` and functions `runStage1`, `renderStage1`, `runStage2`, `renderStage2`, `unlockStep2`, `lockStep2`, `invalidateStage1`, `collectStage1Body`, `collectStage2Body`.
- Keeps: `fetchCostEstimate(L, NB, B, state, smartRes)` and `fetchStrategy(smartRes, costState)` with minimal signature changes described below; Manual Mode block untouched; `fmtInt`/`fmtUSD`, vintage/proto-area hint helpers untouched.

- [ ] **Step 1: Replace the smart-mode section of `static/main.js`**

Delete the old `smartBtn` const/handler, `clearSmartErrors`, `showSmartError`, `resetSmartBtn`. Add:

```js
  // ── SMART MODE: staged wizard ─────────────────────────────────────────
  let stage1Result = null;

  const stage1Btn    = document.getElementById('stage1-btn');
  const stage2Btn    = document.getElementById('stage2-btn');
  const stage1Error  = document.getElementById('stage1-error');
  const stage2Error  = document.getElementById('stage2-error');
  const step1Status  = document.getElementById('step1-status');
  const step2Status  = document.getElementById('step2-status');
  const wizardStep2  = document.getElementById('wizard-step2');
  const stage1Panel  = document.getElementById('stage1-result');
  const smartResult  = document.getElementById('smart-result');

  const STAGE1_INPUT_IDS = ['zip_code', 'soil_confidence', 'building_type',
                            'floor_area_m2', 'year_built',
                            's_wwr', 's_envelope', 's_glazing'];

  function unlockStep2() {
    wizardStep2.classList.remove('step-locked');
    stage2Btn.disabled = false;
    step2Status.textContent = '';
    step1Status.textContent = 'Complete';
    step1Status.classList.add('done');
  }

  function lockStep2() {
    wizardStep2.classList.add('step-locked');
    stage2Btn.disabled = true;
    step2Status.textContent = 'Complete Step 1 to unlock';
    step1Status.textContent = '';
    step1Status.classList.remove('done');
  }

  function invalidateStage1() {
    if (stage1Result === null) return;
    stage1Result = null;
    lockStep2();
    stage1Panel.classList.add('hidden');
    smartResult.classList.add('hidden');
    document.getElementById('cost-section').classList.add('hidden');
    document.getElementById('s6-section').classList.add('hidden');
  }

  STAGE1_INPUT_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', invalidateStage1);
      el.addEventListener('change', invalidateStage1);
    }
  });
```

- [ ] **Step 2: Stage 1 fetch + render**

```js
  function collectStage1Body() {
    const body = {
      zip_code:        document.getElementById('zip_code').value.trim(),
      building_type:   document.getElementById('building_type').value,
      soil_confidence: document.getElementById('soil_confidence').value,
      wwr:             document.getElementById('s_wwr').value,
      envelope:        document.getElementById('s_envelope').value,
      glazing:         document.getElementById('s_glazing').value,
    };
    const floorArea = document.getElementById('floor_area_m2').value.trim();
    if (floorArea) body.floor_area_m2 = parseFloat(floorArea);
    const yearRaw = document.getElementById('year_built').value.trim();
    if (yearRaw !== '') body.year_built = parseInt(yearRaw, 10);
    return body;
  }

  async function runStage1() { ... }
  stage1Btn.addEventListener('click', runStage1);
```

`runStage1` behavior (mirror the old handler's ergonomics):
1. Clear `stage1Error` + field errors for `['zip_code', 'building_type', 'floor_area_m2', 'year_built']`; call `invalidateStage1()`.
2. Disable button, add `.loading`, text `'Analyzing…'`.
3. `fetch('/calculate/stage1', {method:'POST', ...})` with `collectStage1Body()`.
4. On `!response.ok`: field errors route through the existing `showFieldError` (no `s_`-prefix remap needed — stage 1 fields keep their names); banner errors to `stage1Error`. Reset button.
5. On success: `stage1Result = result;` → `renderStage1(result)` → `unlockStep2()` → reset button (text back to `'Analyze Site & Loads →'`) → `stage1Panel.scrollIntoView({behavior:'smooth', block:'nearest'})`.

`renderStage1(result)`: move the existing `pipeline-s1` and `pipeline-s2` innerHTML builders (k-line, k-range bar, rock/soil class line, load pulses, mode label, year/area notes) verbatim — they already read from `result.site` / `result.loads`. Then add the new capacity line:

```js
    const est = result.nb_estimate;
    const fp  = est.footprint;
    document.getElementById('pipeline-nb').innerHTML =
      `Footprint ${Math.round(fp.footprint_m2).toLocaleString()} m² ` +
      `(${Math.round(fp.length_m)} × ${Math.round(fp.width_m)} m, ${fp.n_floors} floor${fp.n_floors > 1 ? 's' : ''})<br>` +
      `<strong>${est.nb_min}–${est.nb_max} boreholes</strong> fit this footprint at ${est.spacing_m} m spacing<br>` +
      `<span style="font-size:11px;color:var(--text-muted)">Step 2 optimizes the count within this range — recomputed if you change spacing</span>`;
    stage1Panel.classList.remove('hidden');
```

- [ ] **Step 3: Stage 2 fetch + render**

```js
  function collectStage2Body() {
    const body = {
      building_type: stage1Result.loads ? document.getElementById('building_type').value : null,
      site:  stage1Result.site,
      loads: stage1Result.loads,
      H_min: parseFloat(document.getElementById('s_H_min').value) || 125,
      B:     parseFloat(document.getElementById('s_B').value) || 6.0,
      A:     parseFloat(document.getElementById('s_A').value) || 9.0,
    };
    body.building_type = document.getElementById('building_type').value;
    const floorArea = document.getElementById('floor_area_m2').value.trim();
    if (floorArea) body.floor_area_m2 = parseFloat(floorArea);
    const T_in_HP = document.getElementById('s_T_in_HP').value.trim();
    const mfls    = document.getElementById('s_mfls').value.trim();
    if (T_in_HP) body.T_in_HP = parseFloat(T_in_HP);
    if (mfls)    body.mfls    = parseFloat(mfls);
    if (document.getElementById('expert-nb-enable').checked) {
      const nbRaw = document.getElementById('s_NB').value.trim();
      if (nbRaw !== '') body.NB = parseInt(nbRaw, 10);
    }
    return body;
  }

  async function runStage2() { ... }
  stage2Btn.addEventListener('click', runStage2);
```

`runStage2` behavior:
1. Guard: `if (!stage1Result) return;`
2. Clear `stage2Error` + field errors for `['s_H_min', 's_B', 's_A', 's_NB']`; hide `smart-result`, `cost-section`, `s6-section`.
3. Button → disabled/loading/`'Sizing…'`.
4. POST `/calculate/stage2`. Error mapping: `{H_min:'s_H_min', B:'s_B', A:'s_A', NB:'s_NB', site:null, loads:null}` — `site`/`loads` errors go to the `stage2Error` banner with the server message (tells the user to re-run Step 1).
5. On success: `renderStage2(result)` → reset button (`'Size Borefield →'`).

`renderStage2(result)`: reuse the existing result-panel code (sres-L/H/NB, two-pass bars, imbalance, solar callout) verbatim, with the NB-range subtitle switched to `nb_source`:

```js
    const nbRange = document.getElementById('sres-NB-range');
    if (result.nb_source === 'expert_override') {
      nbRange.textContent = 'expert override — footprint optimization skipped';
    } else if (result.nb_source === 'depth_fallback') {
      nbRange.textContent =
        `small load — depth-primary sizing chose ${result.NB} (footprint fits ${result.nb_min}–${result.nb_max})`;
    } else {
      nbRange.textContent = `optimal within footprint range ${result.nb_min}–${result.nb_max}`;
    }
```

Then trigger the downstream chain exactly as today, sourcing site/loads from `stage1Result`:

```js
    const siteState = stage1Result.site.state_abbrev || null;
    const B_m = parseFloat(document.getElementById('s_B').value) || 6.0;
    const smartRes = {
      ...result,
      site:  stage1Result.site,
      loads: stage1Result.loads,
      building_type: document.getElementById('building_type').value,
      NB_user: result.nb_source === 'expert_override' ? result.NB : null,
    };
    fetchCostEstimate(result.L, result.NB, B_m, siteState, smartRes);
```

`fetchCostEstimate` and `fetchStrategy` need no signature changes — `smartRes` above has the same `.site`, `.loads`, `.building_type`, `.NB_user` fields they already read.

- [ ] **Step 4: Manual verification**

Run `source venv/bin/activate && flask --app app run --port 5000`, open `http://127.0.0.1:5000`, and verify the full state machine:
1. On load: Step 2 grayed out and unclickable, `stage2-btn` disabled, no result panels.
2. ZIP `60601` + Small Office → "Analyze Site & Loads →": Stage 1 panel appears with soil, loads, and "2–25 boreholes fit this footprint"; Step 1 chip says "Complete"; Step 2 unlocks.
3. "Size Borefield →": sizing result appears with "Boreholes (auto-computed)" and "optimal within footprint range 2–25" (or depth-fallback wording); cost + s6 sections follow.
4. Change Building Type → everything downstream hides, Step 2 re-locks.
5. Expert toggle: open details → check "Enable manual borehole count" → `s_NB` becomes editable → enter 16 → re-run Step 2 → NB shows 16 with "expert override" subtitle.
6. Manual Mode: unchanged, still calculates.
Stop the server.

Also add: `document.getElementById('expert-nb-enable').addEventListener('change', e => { document.getElementById('s_NB').disabled = !e.target.checked; if (!e.target.checked) document.getElementById('s_NB').value = ''; });`

- [ ] **Step 5: Run full tests, commit**

```bash
source venv/bin/activate && python -m pytest tests/ -v
git add static/main.js
git commit -m "feat(ui): staged wizard state machine — stage1Result gating, NB always computed"
```

---

## Task 4: Dev Tool Stage Separation (dev.html)

**Files:**
- Modify: `templates/dev.html` (trace section markup ~lines 363–560; trace runner JS ~lines 1316–1425)
- Modify: `tests/test_ui_template.py` (dev id checks)

**Interfaces:**
- Consumes: `/calculate/smart` unchanged (single call preserved — the smart response already carries `nb_min`, `nb_max`, `footprint`, `H_min`, and after Task 1 also `nb_source`).
- Produces: ids `s4a-in`, `s4a-out`; visual STAGE 1 / STAGE 2 band headers.

- [ ] **Step 1: Add stage band headers in the trace section**

Immediately BEFORE the `<!-- s1a: Geocoding -->` section, insert:

```html
<div class="wf-header" style="border-bottom:2px solid var(--accent);margin-top:4px">
  <span class="stage-pill" style="background:var(--accent)">STAGE 1</span>
  <span class="wf-title">Site &amp; Building Analysis</span>
  <span class="wf-subtitle">s1 geocode + soil → s2/s3 loads → footprint NB range · what the user tool returns from "Analyze Site &amp; Loads"</span>
</div>
```

Immediately BEFORE the `<!-- s4: Sizing -->` section, insert:

```html
<div class="wf-header" style="border-bottom:2px solid #10b981;margin-top:4px">
  <span class="stage-pill" style="background:#10b981">STAGE 2</span>
  <span class="wf-title">Borefield Sizing</span>
  <span class="wf-subtitle">NB optimization → three-pulse sizing → cost → strategy · what "Size Borefield" returns</span>
</div>
```

- [ ] **Step 2: Add the s4a card between the STAGE 2 band and the s4 section**

```html
<!-- s4a: Footprint NB Range & Optimal NB -->
<div class="wf-section">
  <div class="wf-header" style="margin-bottom:8px;border-bottom:1px dashed var(--border)">
    <span class="stage-pill" style="background:#10b981">s4a</span>
    <span class="wf-title" style="font-size:13px">Borehole Count — Footprint Range &amp; Optimizer</span>
  </div>
  <div class="step-grid">
    <div class="step-card">
      <div class="step-label">Inputs consumed</div>
      <div class="kv-list" id="s4a-in"><span class="step-empty">run a trace</span></div>
    </div>
    <div class="step-card">
      <div class="step-label">How it works</div>
      <div class="eq-block">footprint = floor_area / n_floors
W = sqrt(footprint / 9);  L = 9W
nb_min = ceil(W / B)      (short-side line)
nb_max = floor(2(L+W)/B)  (full perimeter)
sweep NB in [nb_min, nb_max]:
  L(NB) via three-pulse sizing
  keep NB minimizing L s.t. H=L/NB ≥ H_min
fallback: depth-primary, NB = ceil(L/H_min)</div>
    </div>
    <div class="step-card full-width">
      <div class="step-label">Output</div>
      <div class="kv-list" id="s4a-out"><span class="step-empty">—</span></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Render s4a in the `t-run` handler**

In the trace JS, after the `s2-out` block and before the `// s4 input/output` block, add:

```js
    // s4a: footprint NB range + optimizer outcome (stage boundary)
    const fp = result.footprint;
    document.getElementById('s4a-in').innerHTML =
      kv('building_type', body.building_type + '  (from STAGE 1)') +
      kv('floor_area_m2', l.floor_area_m2 ? `${l.floor_area_m2} m²` : 'DOE prototype default') +
      kv('B (spacing)',   `${body.B} m  (STAGE 2 input)`) +
      kv('H_min',         `${document.getElementById('t-hmin').value || 125} m  (STAGE 2 input — primary control)`);

    if (result.nb_min != null) {
      document.getElementById('s4a-out').innerHTML =
        kv('footprint',   `${Math.round(fp.footprint_m2).toLocaleString()} m²  (${Math.round(fp.length_m)} × ${Math.round(fp.width_m)} m, ${fp.n_floors} floors, aspect ${fp.aspect})`) +
        kv('nb_min',      `${result.nb_min}  (one line along short side)`) +
        kv('nb_max',      `${result.nb_max}  (full perimeter ring)`) +
        kv('NB chosen',   `${result.NB}`, 'ok') +
        kv('nb_source',   result.nb_source === 'depth_fallback'
              ? 'depth_fallback — no in-range NB satisfies H ≥ H_min; NB = ceil(L/H_min)'
              : 'optimizer — minimum total drill length with H ≥ H_min',
           result.nb_source === 'depth_fallback' ? 'warn' : 'ok');
    } else {
      document.getElementById('s4a-out').innerHTML =
        kv('nb_source', 'expert_override — NB fixed by dev input, footprint search skipped', 'warn') +
        kv('NB (fixed)', `${result.NB}`);
    }
```

Also update the `t-nb` field label in the trace header from `NB` to `NB (expert)` with title `"Leave blank — NB is computed. Fill only to force a fixed count."` — the field stays (dev tool legitimately exercises the override path).

In the existing `s4-in` block, annotate provenance: change the `kv('k_effective, α, T_g', ...)` line's suffix from `(from s1)` to `(from STAGE 1)`, the `q_h, q_m, q_y` suffix from `(from s2)` to `(from STAGE 1)`, and the `kv('NB, B, A', ...)` line to `kv('NB, B, A', \`${result.NB} (computed, s4a), ${body.B} m, ${body.A}\`)`.

- [ ] **Step 4: Pin the new dev ids in tests**

In `tests/test_ui_template.py` add:

```python
DEV_REQUIRED_IDS = ["t-run", "t-hmin", "t-nb", "s4a-in", "s4a-out",
                    "s1a-out", "s1b-out", "s2-out", "s4-out", "s5-out"]


@pytest.fixture(scope="module")
def dev_html():
    app.config["TESTING"] = True
    with app.test_client() as c:
        return c.get("/dev").get_data(as_text=True)


@pytest.mark.parametrize("el_id", DEV_REQUIRED_IDS)
def test_dev_contains_hook_id(dev_html, el_id):
    assert f'id="{el_id}"' in dev_html, f"dev.html hook id '{el_id}' missing"
```

- [ ] **Step 5: Verify and commit**

Run the app, open `/dev`, Run Trace with ZIP 60601 / Small Office / NB blank: STAGE 1 band precedes s1a/s1b/s2; STAGE 2 band precedes s4a/s4/s5/s6; s4a shows nb_min=2, nb_max=25, chosen NB, nb_source. Re-run with NB=16: s4a shows the expert_override warning. Stop the server.

```bash
source venv/bin/activate && python -m pytest tests/ -v
git add templates/dev.html tests/test_ui_template.py
git commit -m "feat(dev): stage-separated trace with s4a footprint/NB-optimizer card"
```

---

## Task 5: Final Verification Sweep

**Files:** none new — verification only.

- [ ] **Step 1: Full test suite**

`source venv/bin/activate && python -m pytest tests/ -v` — all PASS. Pay attention to `test_api_footprint.py` (smart contract), `test_stage_chain_matches_smart_endpoint` (split is lossless), `test_ui_template.py` (both templates).

- [ ] **Step 2: End-to-end browser pass**

One Smart Mode run start-to-finish (steps from Task 3 Step 4), one Manual Mode run, one `/dev` trace. Confirm: no console errors; NB never appears as an enabled input outside the expert toggle; refreshing the page resets to Step-1-only state.

- [ ] **Step 3: Grep for dead references**

`grep -n "smart-btn\|smart-error\|pipeline-panel" static/main.js templates/index.html tests/` — expect zero hits.

---

## Commit Plan (summary)

1. `feat(api): staged /calculate/stage1 + /calculate/stage2 endpoints on shared pipeline helpers` — app.py refactor + 2 new test files
2. `feat(ui): two-step wizard markup — step 2 locked, NB behind expert toggle` — index.html + style.css + REQUIRED_IDS update
3. `feat(ui): staged wizard state machine — stage1Result gating, NB always computed` — main.js
4. `feat(dev): stage-separated trace with s4a footprint/NB-optimizer card` — dev.html + dev id tests

Commits 2 and 3 must land together before any manual browser check (2 alone leaves main.js pointing at removed ids).

## Self-Review Notes

- **NB never user-set:** Stage 2 request omits NB entirely in the normal flow; the HTML input starts `disabled` and requires details-open + checkbox-check; the API treats `NB` strictly as an expert override and reports it via `nb_source`.
- **Statelessness over sessions:** Stage 2 echoes Stage 1 numbers back rather than using Flask sessions — no server-side cache to invalidate, refresh resets cleanly, and the dev tool / tests can hit stage 2 directly with synthetic loads (which `test_api_stage2.py` exploits).
- **Backward compat:** `/calculate/smart` is re-expressed on the same helpers with an identical contract, plus two additive keys (`nb_source`, `q_m_heat`/`q_m_cool` in loads) that no existing consumer breaks on; the chain-parity test locks the equivalence.
- **B-dependence of the NB range** is handled honestly: Stage 1 shows an estimate at 6.0 m labeled as such; Stage 2 recomputes with the submitted B before optimizing (guarded by `test_stage2_spacing_changes_nb_range`).
- **No new physics:** every computation call (`compute_nb_range`, `find_optimal_nb`, `size_borefield`, `size_borefield_for_depth`, `estimate_cost`, `run_strategy`) is invoked with the same arguments as today.
- **July 13 input spreadsheet:** the Stage 1 / Stage 2 input split in this plan (8 stage-1 inputs, 3 stage-2 inputs, 2 advanced, 1 expert) is the natural skeleton for the professor's ~10–15-input spreadsheet.

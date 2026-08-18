# Methodology, Smart-Mode Params, and s7 AI Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three coordinated upgrades. **(A)** Replace the fixed aspect-9 footprint assumption in NB estimation with building-type-specific aspect ratios and add a load-density cross-check, without touching the professor-validated minimize-L optimizer. **(B)** Audit every user-controllable parameter, loop the Manual-only parameters that a power user legitimately needs into Smart Mode's hidden Advanced block (including fixing the currently-dead `s_T_in_HP` field), and keep the Manual Advanced tab with a clarifying note. **(C)** Pivot s7 from "PDF export" to a fixed-structure in-page report — design summary, benefits & savings, cost comparison vs conventional HVAC — capped by an AI design review generated via the Claude API (critical *and* encouraging, with a mandatory pre-feasibility caveat).

**Architecture:** (A) is confined to `geosite/s4_sizing/footprint.py` plus the tests that pin NB-range values; the optimizer objective, sweep, and depth fallback are untouched. (B) is UI/JS only — `app.py`'s stage2 endpoint *already accepts* every `_ADVANCED_DEFAULTS` key and `T_in_HP_heat`/`T_in_HP_cool`, so the work is exposing inputs in `index.html`, wiring `collectStage2Body()` and the `fetchStrategy` payload, and one small app.py cleanup (deduplicate the inline defaults dict in `strategy_api`). (C) adds a new `geosite/s7_report/` module (deterministic report builder + Claude API caller), one new Flask route `POST /api/report`, and an s7 section in the UI that chains off `fetchStrategy` completion. The Claude call is non-streaming `client.messages.create` with a JSON-schema structured output, 30 s timeout, and graceful degradation (report renders without the AI section if the key is missing or the call fails).

**Tech Stack:** Python 3.11 / Flask, vanilla JS, Jinja2, pytest + Flask test client, `anthropic` Python SDK (new dependency), model `claude-haiku-4-5` for the report review.

---

## METHODOLOGY AUDIT — s1 → s6, reviewed by Claude Fable 5

This section is the critical review the user requested ("use model Fable 5 to review all steps of calculation"). It is organized MECE: each stage is audited for (i) what the code actually does, (ii) internal validity (is the math right given its own assumptions), (iii) external validity (are the assumptions right), and (iv) what is missing. Items marked **[FIX-in-this-plan]** are addressed by tasks below; items marked **[DEFER]** are documented gaps for the professor/backlog.

### s1 — Soil Thermal Properties

**What it does:** ZIP → lat/lon (zippopotam.us) → census tract GEOID (Census geocoder) → county FIPS → `deep_thermal_by_county.csv` (SMU IDW where ≥3 quality-A/B points within 200 km, else SGMC rock class → Clauser & Huenges 1995 median k); fallback to shallow SSURGO tract data; `soil_confidence` maps to k_min / k / min(k_max, 1.25k) when class bounds exist, else ×0.83 / ×1.00 / ×1.10.

- **Internal validity:** Sound. The two-track method is honest about provenance (`k_method` recorded), the deprecated ML endpoint is correctly quarantined, and the physics-grounded confidence adjustment (class bounds instead of arbitrary multipliers) is defensible — clamping "high" at min(k_max, 1.25k) prevents the optimism ceiling from exceeding the lithology.
- **External validity:** County-level k is a coarse spatial unit — a county can span granite and alluvium. Clauser & Huenges medians carry ±50% class-internal spread; the conservative default (k_min for "low" confidence) is the right posture for a pre-feasibility tool and matches the professor's 2026-06-29 directive.
- **Gaps:** (1) Coverage fraction of US counties in `deep_thermal_by_county.csv` is not surfaced anywhere — an unknown GEOID silently returns `data_available: False` and a 422; the UI message is correct but there is no coverage map/statistic. **[DEFER]** (2) T_g at 100 m midpoint ignores seasonal surface variation — correct for vertical bores below ~10 m, so this is fine *for this tool's scope*; document it. (3) Water table / saturation effects on k are ignored — saturated vs dry sand differs by 2–3×; the SGMC medians implicitly assume typical saturation. This is the single largest s1 uncertainty and should be named in the s7 AI-review prompt context. **[FIX-in-this-plan — surfaced in s7 report as a standing caveat]**

### s2 — Building Loads (pre-computed EnergyPlus)

**What it does:** `prototype_loads.json` (DOE prototypes, IdealLoads) → linear area scaling → × year_factor (ASHRAE 90.1 vintage breakpoints) → × envelope_factor (currently all 1.0).

- **Internal validity:** Linear area scaling was explicitly validated by the professor (2026-06-29). The vintage breakpoints are sourced (PNNL 90.1 savings analyses, CBECS) and interpolated continuously — reasonable.
- **External validity:** (1) IdealLoads means the "ground load" is really the *zone* load — no HVAC system efficiency, no duct losses, no fan heat. For borefield sizing the ground load should be zone load × (COP±1)/COP: heating extraction is ~75% of zone load at COP 4, cooling rejection is ~125%. Ignoring this **oversizes heating-dominant fields by ~1/3 and undersizes cooling-dominant fields by ~20%** — directionally conservative for heating climates, non-conservative for cooling climates. This is the most consequential known bias in the whole pipeline. **[DEFER — professor decision; flagged in s7 AI prompt]** (2) Envelope factors are structure-only placeholders (all ×1.00) pending the 2026-07-13 calibration — the UI already labels this honestly. (3) A user's real building may diverge from the DOE prototype in schedule/plug loads; area scaling cannot capture that. Acceptable for pre-feasibility; the s7 caveat covers it.

### s3 — Three-Pulse Extraction

**What it does:** 8760 h net ground profile (q_cool − q_heat, positive = injection) → q_h (extreme hour), q_m (extreme monthly mean), q_y (annual mean), plus both-mode peaks for two-pass sizing.

- **Sign convention check (the professor's specific ask):** Verified consistent end-to-end. `compute_pulses` and `extract_one_sided_pulses` produce negative = extraction; `size_borefield` computes `T_out = T_in_HP + q_h/(m_dot·Cp)` with `m_dot = mfls·|q_h|/1000` — negative q_h lowers T_m below T_in_HP, T_m − T_g goes negative, numerator (all q negative) goes negative, L positive. Cooling mirror-symmetric. The s6 ASHRAE cap is applied sign-correctly (`max(q_h_heat, −cap_W)` / `min(q_h_cool, cap_W)`). One subtlety: **q_y is the *net* annual mean in both single-pass and two-pass sizing** (both passes in `_run_sizing` share `q_y`) — that is the correct Philippe et al. treatment (long-term ground drift depends on net flux), but `extract_one_sided_pulses` in s6 computes a *one-sided* q_y (`one_sided.mean()`), which overstates annual imbalance per mode when both modes exist. The two paths therefore size slightly differently for the same building. **[DEFER — document; changing it alters s6 baselines and needs professor sign-off]**
- **Gaps:** Monthly bins use fixed non-leap month-hours (fine); latent vs sensible split ignored (IdealLoads gives total — fine at this fidelity); demand charges are an s6/s7 economics topic, not a load topic.

### s4 — Borefield Sizing (Philippe et al. 2010)

**What it does:** Rb analytical resistance, 10-term g-function polynomials (6h/1m/10y), fixed-point iteration on the Tp interaction polynomial, two-pass (heat/cool) governing-mode selection; NB from footprint geometry + minimize-L sweep; depth-primary fallback.

- **Internal validity:** The implementation is pinned to the reference spreadsheet (CLAUDE.md ground truth) and the convergence upgrade (tol=1.0 m vs Excel's 5 fixed passes) is documented with error bounds — good. Validity ranges (α 0.025–0.2, rbore 0.05–0.1) are enforced at the API for `/calculate` — **but stage2 and `/api/strategy` do NOT re-validate α or rbore ranges on user-supplied advanced overrides.** With Section B exposing these fields in Smart Mode, range validation must be added. **[FIX-in-this-plan — Task B2]**
- **External validity:** (1) The polynomial g-functions are fits valid inside the stated parameter box; vs a full numerical g-function (e.g. pygfunction) expect single-digit-% deviation for typical fields, growing for very large NB or tight B/H — acceptable for pre-feasibility, and worth a one-time benchmark against pygfunction as a backlog item. **[DEFER]** (2) Two-pass sizing (size each mode independently at its own T_in_HP, larger governs) is the standard practical approach; its known blind spot is that the non-governing mode's *beneficial* ground recharge is only captured through the shared net q_y, which the two-pass branch does use — correct. (3) Rb assumes a single U-tube, uniform grout; grout k uncertainty (±0.5 W/m·K between standard and thermally-enhanced) moves L by roughly 5–10% — exposing `kgrout` in Smart Mode (Section B) is the right mitigation.
- **NB range logic — the Section A subject, fully critiqued there.**

### s5 — Cost Estimation

**What it does:** Regional $/ft rates × footage, line items (mobilization, soil/rock drilling split, casing, grout, U-tube, header pipe, trench), rock-fraction scenarios narrowed ±0.15 around the SGMC class fraction.

- **Internal validity:** Better than the prompt's priors suggest — mobilization, header pipe, and trenching ARE line items (`line_items.py` / the UI breakdown table shows them). The rock-fraction narrowing around site lithology is a nice touch.
- **Gaps:** (1) No heat pump equipment or inside-the-building installation cost — the number shown is *borefield* cost, not *system* cost, and the UI does not say so loudly. (2) No conventional-system comparison and no lifecycle/operating cost. **[FIX-in-this-plan — s7 report adds both, clearly labeled as rough industry placeholders]** (3) Regional rates have a vintage; no inflation index. **[DEFER]**

### s6 — Hybrid Strategy (LDC Peak Shaving)

**What it does:** ASHRAE 99.6% cap (top 0.4% of hours flattened), two cutoff methods (M1 top-10%-hours, M2 top-10%-energy via bisection), trim → re-extract pulses → resize, peaker kW per side, cost before/after.

- **Internal validity:** The LDC math is clean (M2's monotone bisection is correct; capping applied before both cutoffs). Two verified inconsistencies: (a) `strategy.py` duplicates `_ADVANCED_DEFAULTS`/`_T_IN_HP` from `app.py` — drift risk **[FIX-in-this-plan — Task B2 consolidation]**; (b) the s6 pipeline computes its own NB via `find_optimal_nb` on *capped, one-sided* pulses while stage2 computes NB on *uncapped* pulses — the two panels can legitimately disagree on NB for the same inputs, and the UI does not explain why. `main.js` passes `NB` only for expert overrides. **[FIX-in-this-plan — pass stage2's computed NB into `/api/strategy` so s5/s6 describe the same field]** (c) `fetchStrategy` does not forward the user's advanced overrides (mfls, T_in_HP, pipe params) — s6 silently reverts to defaults after the user tuned stage2. **[FIX-in-this-plan — Task B1]**
- **Gaps:** (1) Peaker *energy* (kWh) is computed in `ldc.py` (`m1_peaker_energy_Wh`/`m2_peaker_energy_Wh`) but not surfaced in the UI — the professor's 2026-07-06 LDC-kWh metric ask. The s7 report surfaces it. **[FIX-in-this-plan — s7]** (2) No COP assumption anywhere, so "savings" are drilling-capex-only — the s7 operating-cost model adds explicit COP/efficiency constants. (3) Multi-year thermal drift beyond the 10-year Tp horizon, and demand-charge value of peak shaving: both real, both beyond pre-feasibility scope. **[DEFER — named in the s7 AI caveats]**

### Cross-cutting verdict

The pipeline's *engineering core* (s3 sign conventions, s4 spreadsheet parity, s6 LDC math) is trustworthy. The three largest honest uncertainties, in order: **(1)** zone-load-as-ground-load (no COP correction, ±20–35% directional bias by climate), **(2)** county-median k with unquantified in-county spread (mitigated by the conservative default), **(3)** the aspect-9 footprint fiction distorting the NB search space (fixed by Section A). Every s7 AI review must carry these three plus the pre-feasibility disclaimer.

---

## Global Constraints

- **Do not change the optimizer objective.** `find_optimal_nb`'s minimize-L sweep with H ≥ H_min and the depth-primary fallback are professor-validated (2026-07-06). Section A changes only the *bounds* fed into it.
- **No invented methods** (standing user rule): every new constant (aspect ratios, W/m extraction rates, $/kW conventional costs, COP values) must carry a source comment and, where it is a placeholder pending calibration, an explicit `# PLACEHOLDER — pending professor calibration` marker.
- **`/calculate/smart` and `/calculate` request/response contracts unchanged** (dev.html + `test_api_footprint.py` pin them). New response keys are additive only.
- **Claude API usage:** non-streaming `client.messages.create` on model `claude-haiku-4-5` (alias — do NOT append a date suffix), `max_tokens=1500`, `timeout=30.0` on the client, JSON-schema structured output via `output_config={"format": {...}}`. API key from `ANTHROPIC_API_KEY` env (python-dotenv already in requirements; load it in `app.py` if not already). Every failure path degrades gracefully — the report must render without the AI section.
- **Vanilla JS, existing CSS token system**, no build step.
- Run tests with: `source venv/bin/activate && python -m pytest tests/ -v` (full suite before every commit).
- No comments in code unless the WHY is non-obvious.

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `geosite/s4_sizing/footprint.py` | `BUILDING_ASPECT` table, per-type aspect in `compute_nb_range`, `load_implied_nb_range()` |
| Modify | `app.py` | Surface load-implied NB range + capacity warning in stage1/stage2; validate advanced-override ranges; `POST /api/report`; dedupe strategy defaults |
| Modify | `geosite/s6_strategy/strategy.py` | Import shared defaults instead of duplicating |
| Create | `geosite/s7_report/builder.py` | Deterministic report assembly + savings/cost-comparison math |
| Create | `geosite/s7_report/ai.py` | Claude API review call (schema, prompt, error handling) |
| Modify | `geosite/s7_report/__init__.py` | Public API: `build_report`, `generate_review` |
| Modify | `templates/index.html` | Smart Advanced block params; T_in_HP heat/cool split; Manual Advanced note; s7 section |
| Modify | `static/main.js` | New fields in `collectStage2Body()`; forward overrides + NB to `fetchStrategy`; s7 generate/render/copy |
| Modify | `static/style.css` | `ai-pill`, report section styles |
| Modify | `requirements.txt` | `anthropic` |
| Modify | `tests/test_s4_footprint.py`, `tests/test_api_stage1.py`, `tests/test_api_stage2.py`, `tests/test_s6_footprint.py`, `tests/test_api_footprint.py` | Re-pin NB ranges to per-type aspect values |
| Modify | `tests/test_ui_template.py` | New/changed DOM ids |
| Create | `tests/test_s7_report.py` | Builder math + AI call (mocked) |
| Create | `tests/test_api_report.py` | `/api/report` contract + degradation paths |

---

# SECTION A — NB Estimation: Critique and Rationalization

## A.0 MECE critique of the current logic (analysis — no code)

The current chain: `footprint = area/n_floors` → rectangle at fixed aspect 9 → `nb_min = ceil(W/B)` (one line on the short side) → `nb_max = floor(perimeter/B)` (full ring) → minimize-L sweep. Each assumption, judged:

1. **Fixed aspect 9 — INDEFENSIBLE as a *building* footprint.** No DOE prototype is remotely 9:1 (measured prototype aspect ratios run 1.3–3.0; see table below). The docstring justifies 9 as "the arrangement that maximizes inter-borehole efficiency for a line-dominant field" — but that is a property of the **borefield array** (already separately controlled by the user-facing array aspect `A`, default 9.0 in Smart Mode Step 2), not of the building. The code conflates two different aspect ratios. Consequences of the fiction: for a 1-floor small office (511 m²) it yields W=7.5 m / L=67.8 m — a bowling alley, not an office. Because a 9:1 rectangle of equal area has a *smaller* short side and a *larger* perimeter than the true shape, nb_min is understated (2 vs true ~4) and nb_max overstated (25 vs true ~15) — the sweep range is wrong at both ends, and every number shown to the user under "Footprint" (length × width) is physically false.
2. **`nb_min` = one line along the short side — keep the *rule*, fix the *input*.** As a lower bound it encodes "the field should at least span the building's narrow dimension," which is a sane minimum-disruption floor once W is realistic. With aspect 9 it degenerates (W→small→nb_min→1–2 for any small building). No rule change needed; the aspect fix repairs it.
3. **`nb_max` = full perimeter ring — acceptable upper bound, with two caveats.** (a) It presumes the entire perimeter is drillable — hospitals with courtyards, retail with parking-side utility corridors, and zero-lot-line urban sites violate this. A site-availability factor is the honest fix, but it is one more uncalibrated input; at pre-feasibility, an *upper bound* being optimistic is tolerable **as long as the UI labels it "up to … fit the perimeter"** (it does). (b) With realistic aspect, the perimeter shrinks, so nb_max tightens automatically — partially self-correcting. Keep the ring; do not add an availability input now. **[DEFER an `site_frac` input to the professor's Jul-13 input-spreadsheet review]**
4. **Optimizer objective (minimize total L s.t. H ≥ H_min) — KEEP UNCHANGED.** Minimum drilled length is a defensible proxy for minimum cost when cost ≈ rate × footage + per-hole fixed costs and H_min already suppresses the many-shallow-holes failure mode. It is professor-validated. What it does *not* capture — mobilization steps at NB thresholds, header-pipe cost growth with NB — is second-order at this fidelity and already priced downstream in s5.
5. **Geometry-only bounds ignore the load — the real structural gap.** Nothing checks whether the load *physically fits* the footprint: a 46,000 m² large office's ground load may need more bore-meters than any perimeter ring at 125 m can deliver, and today the optimizer just returns the least-bad in-range answer with no warning. Conversely a tiny load correctly triggers the depth fallback (handled, and the UI wording is correct). The fix is a **load-density cross-check** (industry rule of thumb: sustained peak extraction 15–70 W per bore-meter depending on soil, per VDI 4640 / IGSHPA guidance): compute the NB range the load itself implies at H_min and compare with the geometric range. Overlap → fine; load-implied minimum above geometric maximum → surface a "footprint capacity" warning steering the user to s6 hybrid, deeper H, or expert NB. **This check informs, it does not re-bound the optimizer** — keeping the professor-validated behavior intact.
6. **Boundary communication — mostly fine already.** `nb_source: depth_fallback` exists and `main.js` renders "small load — depth-primary sizing chose N". The missing piece is the *other* boundary (load too big for footprint), covered by the new warning.

### Per-building aspect ratios (from DOE Commercial Prototype scorecards)

Values below are footprint length/width from the published prototype drawings, rounded to one decimal. E-shaped schools use the effective bounding rectangle. **Implementer: verify each against the DOE prototype scorecard PDFs (energycodes.gov, 90.1-2019 set) before committing; adjust any that differ and note the source in the code comment.**

| building_type | aspect | basis |
|---|---|---|
| small_office | 1.5 | 27.7 × 18.5 m |
| medium_office | 1.5 | 49.9 × 33.3 m |
| large_office | 1.5 | 73.1 × 48.7 m |
| standalone_retail | 1.3 | 54.3 × 42.2 m |
| primary_school | 1.6 | E-shape bounding box |
| secondary_school | 1.6 | E-shape bounding box |
| hospital | 1.3 | 70.1 × 53.3 m |
| outpatient_healthcare | 1.4 | scorecard |
| small_hotel | 3.0 | 54.9 × 18.3 m |
| large_hotel | 3.0 | slab wing |
| warehouse | 2.2 | 100.6 × 45.7 m |
| midrise_apartment | 2.7 | 46.3 × 16.9 m |

## Task A1: Building-type aspect ratios in `footprint.py`

**Files:** Modify `geosite/s4_sizing/footprint.py`; modify `tests/test_s4_footprint.py`.

- [ ] **Step 1: Update the footprint tests first (they fail).** In `tests/test_s4_footprint.py`, re-pin small_office prototype expectations: area 511 m², 1 floor, aspect 1.5 → W = √(511/1.5) = 18.46 m, L = 27.69 m, perimeter 92.31 m → `nb_min = ceil(18.46/6) = 4`, `nb_max = floor(92.31/6) = 15`. Add a parametrized test asserting `meta["aspect"] == BUILDING_ASPECT[bt]` for every building type, and one asserting all aspects are in [1.0, 4.0] (guard against a typo reintroducing 9).
- [ ] **Step 2: Implement.** In `footprint.py`: add the `BUILDING_ASPECT` dict (with the scorecard-basis comment per row and the verify note); in `compute_nb_range` replace `FOOTPRINT_ASPECT` with `aspect = BUILDING_ASPECT[building_type]`; delete `FOOTPRINT_ASPECT` (grep the repo for other references — `dev.html`'s eq-block text mentions `sqrt(footprint/9)`; update that text to `sqrt(footprint/aspect[type])`). Update the module docstring: the building footprint aspect is now type-specific and is *distinct from* the borefield array aspect `A`.
- [ ] **Step 3: Re-pin the API tests.** `tests/test_api_stage1.py` (`nb_min == 2 and nb_max == 25` → `4`/`15`; the `floor_area_m2=1022` case: W = √(1022/1.5) = 26.1 → nb_min 5, perimeter 130.5 → nb_max 21), `tests/test_api_stage2.py` (same 4/15 pins; the `B=3.0` test's `> 25` assertion becomes `> 15`), `tests/test_api_footprint.py` and `tests/test_s6_footprint.py` — recompute any pinned nb values with the formula above for the building types they use. Run each file and fix pins until green.
- [ ] **Step 4: Full suite, commit.** `git commit -m "fix(s4): building-type footprint aspect ratios replace fixed aspect-9"`

## Task A2: Load-density cross-check

**Files:** Modify `geosite/s4_sizing/footprint.py`, `app.py`, `static/main.js`, `templates/index.html` (one hint line), tests.

- [ ] **Step 1: Tests first.** In `tests/test_s4_footprint.py` add tests for a new `load_implied_nb_range(q_h_W, H_min)`: `q_h = -60000, H_min = 125` → lo = ceil(60000/(70×125)) = 7, hi = ceil(60000/(15×125)) = 32; zero/positive-cooling load uses |q_h|; lo ≥ 1 always.
- [ ] **Step 2: Implement in `footprint.py`:**

```python
# Sustained peak extraction/rejection per bore-meter. Range spans VDI 4640
# Blatt 2 guideline values for poor soils (dry sediment, ~15 W/m) to
# favorable saturated rock with low run-hours (~70 W/m).
Q_PER_M_MIN = 15.0
Q_PER_M_MAX = 70.0

def load_implied_nb_range(q_h_W: float, H_min: float) -> tuple[int, int]:
    q = abs(q_h_W)
    lo = max(1, math.ceil(q / (Q_PER_M_MAX * H_min)))
    hi = max(lo, math.ceil(q / (Q_PER_M_MIN * H_min)))
    return lo, hi
```

- [ ] **Step 3: Surface it (additive keys only).** In `app.py` `calculate_stage1`: add to `nb_estimate` → `"nb_load_min"`, `"nb_load_max"` (from the governing |q_h| at default H_min=125), and `"capacity_warning": nb_load_min > nb_max` (bool). In `_run_sizing`: same three keys computed with the actual H_min/B, `None` under expert override. Do NOT feed these into `find_optimal_nb` — the optimizer bounds stay geometric.
- [ ] **Step 4: UI.** In `renderStage1` (`pipeline-nb` block) append a line: `Load check: this q_h needs roughly {nb_load_min}–{nb_load_max} boreholes at 125 m (15–70 W/m rule of thumb)`. When `capacity_warning` is true, render a `callout callout-warn`: "The peak load likely exceeds what the building perimeter can host — consider the s6 hybrid strategy, deeper boreholes, or off-footprint field area." Mirror the warning in `renderStage2` when stage2's recomputed flag is true.
- [ ] **Step 5: API tests.** Add stage1/stage2 assertions for the new keys (present, ints, warning bool). Full suite, commit: `git commit -m "feat(s4): load-density NB cross-check with footprint capacity warning"`

## Task A3: What deliberately does NOT change (record in code)

- [ ] Add a short comment block atop `find_optimal_nb` noting: objective (minimize L), H_min constraint, and depth fallback are professor-validated 2026-07-06 and must not change without sign-off; the load-density check is advisory only. No functional change; fold into the Task A2 commit if trivial.

---

# SECTION B — Parameter Audit: Smart Mode Advanced Block

## B.0 MECE parameter inventory (analysis)

| Parameter | Manual UI | Smart UI | Stage2 API accepts | Verdict |
|---|---|---|---|---|
| q_h, q_m, q_y | ✅ Basic | computed (s2) | echoed via `loads` | correct — never a Smart input |
| k, α, T_g | ✅ Basic | computed (s1) + soil_confidence | echoed via `site` | correct — soil_confidence is the Smart-mode knob |
| wwr / envelope / glazing | ✅ Basic | ✅ Step 1 | ✅ | already both |
| B (spacing) | ✅ | ✅ Step 2 | ✅ | already both |
| A (array aspect) | ✅ | ✅ Step 2 | ✅ | already both |
| NB | ✅ | expert toggle | ✅ | already both (correctly buried) |
| H_min | — | ✅ Step 2 (primary) | ✅ | Smart-only by design |
| **T_in_HP (single)** | ✅ | ⚠️ `s_T_in_HP` — **DEAD**: two-pass `_run_sizing` reads `T_in_HP_heat`/`T_in_HP_cool`, so the field the Smart UI sends is ignored on the normal path | ✅ (single-pass only) | **fix: split into heat/cool pair** |
| T_in_HP_heat / T_in_HP_cool | — | — | ✅ (silently) | **add to Smart hidden block** |
| mfls | ✅ Basic | ✅ hidden | ✅ | already both — but NOT forwarded to `/api/strategy` by main.js → **fix** |
| Cp | ✅ Advanced | — | ✅ | add (grouped, low prominence) — antifreeze mixes drop Cp ~10–15% |
| rbore | ✅ Advanced | — | ✅ | **add** — rig-dependent, varies per project |
| kgrout | ✅ Advanced | — | ✅ | **add** — standard vs thermally-enhanced grout is a real design choice (±5–10% on L) |
| rpin / rpext / LU | ✅ Advanced | — | ✅ | add — set by pipe SDR selection; legitimate power-user knob |
| hconv | ✅ Advanced | — | ✅ | add for completeness (flow-regime dependent), lowest prominence |
| soil_confidence, zip, building_type, floor_area, year_built | — | ✅ Step 1 | s1 path | Smart-only by design |
| ldc_cutoff_pct, ignore_top_pct, imbalance_threshold | — | — | strategy API only | **[DEFER]** — s6 tuning params, professor-owned; do not expose yet |

**Decisions:** (1) All 8 borehole/pipe params + Cp go into Smart Mode's existing Advanced `<details>` under a second sub-heading "Borehole & pipe construction" — empty inputs with the default as placeholder; blank = server default. Rationale: stage2 already accepts them, a validating engineer needs them to reproduce an external design, and hiding them behind the collapsed details keeps the smart path clean. (2) `s_T_in_HP` is replaced by `s_T_in_HP_heat` / `s_T_in_HP_cool` — this fixes the dead-field bug. (3) **Manual Advanced tab: KEEP.** After this change it fully overlaps Smart's hidden block, but Manual Mode is the researcher/validation surface and overlap is explicitly fine per the user. Add one hint line: *"Borehole & pipe physical constants — typically fixed by the drilling contractor and pipe SDR; leave at defaults unless you have contractor specs."*

## Task B1: Smart Mode hidden params + JS wiring

**Files:** Modify `templates/index.html`, `static/main.js`, `tests/test_ui_template.py`.

- [ ] **Step 1: ids test first.** In `tests/test_ui_template.py` `REQUIRED_IDS`: remove `s_T_in_HP`; add `s_T_in_HP_heat`, `s_T_in_HP_cool`, `s_Cp`, `s_rbore`, `s_rpin`, `s_rpext`, `s_kgrout`, `s_kpipe`, `s_LU`, `s_hconv`. Run — new ids fail.
- [ ] **Step 2: index.html.** In the Smart Advanced `<details>` (currently `s_T_in_HP` + `s_mfls`): replace the single T_in_HP field with two fields (labels "HP inlet temp — heating design (min EWT)" placeholder `5.0`, "HP inlet temp — cooling design (max EWT)" placeholder `40.2`); keep `s_mfls`; append a sub-heading `<h2 class="card-title">Borehole &amp; pipe construction</h2>` with the 8 fields, each `placeholder` = the `_ADVANCED_DEFAULTS` value, units matching the Manual Advanced tab. In the Manual Advanced tab card, add the contractor hint line from B.0. Value: all new Smart inputs start empty (blank → server default), consistent with `s_mfls`.
- [ ] **Step 3: main.js.** In `collectStage2Body()`: for each of `{T_in_HP_heat: 's_T_in_HP_heat', T_in_HP_cool: 's_T_in_HP_cool', Cp: 's_Cp', rbore: 's_rbore', rpin: 's_rpin', rpext: 's_rpext', kgrout: 's_kgrout', kpipe: 's_kpipe', LU: 's_LU', hconv: 's_hconv'}` send `parseFloat` when non-blank (same pattern as mfls); delete the `s_T_in_HP` read. Factor the map into a module-level `const SMART_ADV_FIELDS` and reuse it in `fetchStrategy`: extend the strategy `payload` with the same non-blank overrides **plus `mfls`** (currently dropped) so s6 sizes with the same physics as stage2. Also pass stage2's computed NB: in `renderStage2`, set `smartRes.NB_user = result.NB` when `nb_source === 'expert_override'` (unchanged) and additionally set `smartRes.NB_computed = result.NB`; in `fetchStrategy`, `payload.NB = smartRes.NB_user ?? smartRes.NB_computed ?? null` — s5 and s6 now describe the same borefield (audit finding s6-b).
- [ ] **Step 4: Manual verification.** Run the app; ZIP 60601 / Small Office → stage1 → open Advanced, set kgrout 2.0 and T_in_HP_heat 3.0 → stage2 → confirm L changes vs defaults and s6 headline uses the same NB as the sizing panel. Full suite, commit: `git commit -m "feat(ui): borehole/pipe + per-mode EWT params in Smart Advanced; forward overrides and NB to s6"`

## Task B2: Server-side validation + defaults dedupe

**Files:** Modify `app.py`, `geosite/s6_strategy/strategy.py`; modify `tests/test_api_stage2.py`.

- [ ] **Step 1: Tests first.** stage2 with `alpha`-carrying site is already validated; add: `rbore=0.2` in stage2 body → 400 field `rbore` "between 0.05 and 0.1 m"; `kgrout=0` → 400; `T_in_HP_heat="abc"` → 400 field `T_in_HP_heat`.
- [ ] **Step 2: app.py.** In the shared params-parsing spot (both `calculate_smart` and `calculate_stage2` do `params = {k: float(data.get(k, v)) ...}`): extract a `_parse_advanced_params(data)` helper that floats each key with a per-field 400 on ValueError, enforces `0.05 <= rbore <= 0.1` and positive kgrout/kpipe/Cp/hconv/mfls/LU/rpin/rpext plus `rpin < rpext < rbore` and `LU < 2*rbore`, and floats `T_in_HP`, `T_in_HP_heat`, `T_in_HP_cool` when present (else pass-through of defaults inside `_run_sizing` as today). Use it in `/calculate/smart`, `/calculate/stage2`, and `/api/strategy` (replacing `strategy_api`'s inline duplicate dict).
- [ ] **Step 3: strategy.py.** Replace its local `_ADVANCED_DEFAULTS`/`_T_IN_HP` copies with `from app import ...`? No — circular import; instead move the canonical dicts to `geosite/s4_sizing/defaults.py` (new tiny module: `ADVANCED_DEFAULTS`, `T_IN_HP_DEFAULTS`) and import from both `app.py` and `strategy.py`, keeping the old names as aliases in `app.py` (tests may reference `app._ADVANCED_DEFAULTS`; grep first).
- [ ] **Step 4:** Full suite, commit: `git commit -m "refactor(api): shared advanced-param defaults + range validation for overrides"`

---

# SECTION C — Stage 7: Fixed-Structure In-Page Report with AI Review

## C.0 Report structure (fixed)

Four sections, rendered in-page (no PDF), each pulling from data the browser already holds after stage1 → stage2 → cost → strategy:

1. **System Design** — from stage2 result + stage1: NB, H (m), total L (m + ft), spacing B, array aspect A, governing mode, two-pass L_heat/L_cool + imbalance, nb_source (optimizer / depth fallback / expert), footprint dims, soil k_eff / α / T_g / climate zone.
2. **Estimated Performance** — from s6: GSHP coverage (M1 & M2, % hours and % kWh), peaker size kW and type, **peaker energy kWh/yr** (finally surfacing `m*_peaker_energy_Wh` — professor's LDC-kWh ask), ASHRAE cap, dominant mode, thermal-imbalance / solar-thermal flag.
3. **Cost & Savings** — s5 best/base/worst borefield cost; **conventional comparison** computed server-side in `builder.py` from peak load + annual thermal energy with clearly-labeled placeholder constants (below); GSHP total system estimate = borefield + HP equipment; annual operating cost each; simple payback (guarded).
4. **AI Design Review** — Claude-generated: strengths / concerns / risks / next steps / one-line verdict, with the mandatory pre-feasibility caveat, rendered under a distinctive "AI Analysis" pill. If the call fails: a neutral note ("AI review unavailable — {reason}") and the other three sections stand alone.

**Economics constants** (all in `builder.py`, each `# PLACEHOLDER — rough US commercial averages, pending professor calibration`):
`ELEC_USD_PER_KWH = 0.13` (EIA commercial avg), `GAS_USD_PER_THERM = 1.20`, `KWH_PER_THERM = 29.3`, `BOILER_EFF = 0.85`, `CHILLER_COP = 3.0`, `GSHP_COP_HEAT = 4.0`, `GSHP_COP_COOL = 4.5`, `CONV_USD_PER_KW = (340.0, 500.0, 710.0)` (gas boiler + air-cooled chiller plant installed, ≈ $1.2–2.5k/ton), `HP_USD_PER_KW = 570.0` (GSHP water-to-air units installed, ≈ $2k/ton). Operating: `conv = heat_kWh/0.85/29.3×gas + cool_kWh/3.0×elec`; `gshp = heat_kWh/4.0×elec + cool_kWh/4.5×elec` (note in output that peaker energy is additional). Annual thermal kWh are computed client-side from the strategy `hourly_profile` (sum of negative hours → heat, positive → cool, ÷1000) and sent in the request — no server re-simulation.

**AI call design** (`ai.py`): model `claude-haiku-4-5`, non-streaming, `max_tokens=1500`, client constructed with `timeout=30.0`. Structured output:

```python
REVIEW_SCHEMA = {
  "type": "object",
  "properties": {
    "verdict": {"type": "string"},
    "strengths": {"type": "array", "items": {"type": "string"}},
    "concerns": {"type": "array", "items": {"type": "string"}},
    "risks": {"type": "array", "items": {"type": "string"}},
    "next_steps": {"type": "array", "items": {"type": "string"}},
  },
  "required": ["verdict", "strengths", "concerns", "risks", "next_steps"],
  "additionalProperties": False,
}
resp = client.messages.create(
    model="claude-haiku-4-5", max_tokens=1500,
    system=REVIEW_SYSTEM,
    output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
    messages=[{"role": "user", "content": json.dumps(review_input, sort_keys=True)}],
)
```

`REVIEW_SYSTEM` must instruct: (a) you are reviewing a *pre-feasibility* GSHP borefield estimate, not an engineering design — the caveat "this tool is a pre-feasibility estimator; a licensed engineer and a thermal response test are required before installation" MUST appear in `risks` or `next_steps`; (b) be critical AND encouraging — at least two genuine concerns and at least two genuine strengths; (c) use only the numbers provided, never invent site data; (d) specifically evaluate: depth-fallback or expert-override NB, thermal imbalance / solar flag, GSHP coverage below ~85% energy, payback above ~15 yr, capacity_warning, and the three standing pipeline caveats (no COP correction on ground loads, county-median soil k, footprint-model NB range). `review_input` = compact dict: building_type, floor_area, climate_zone, k_eff, NB, H, L, B, governing, imbalance_m, solar_flag, nb_source, capacity_warning, q_h_kW, coverage m1/m2 (%hrs, %kWh), peaker kW/kWh, cost range, conventional comparison, payback.

Error handling: catch `anthropic.APIStatusError`, `anthropic.APIConnectionError`, `anthropic.APITimeoutError` (and missing-key `anthropic.AuthenticationError`) → return `(None, "<reason string>")`. If `ANTHROPIC_API_KEY` is unset, short-circuit before constructing the client.

## Task C1: `geosite/s7_report` module

**Files:** Create `geosite/s7_report/builder.py`, `geosite/s7_report/ai.py`; modify `geosite/s7_report/__init__.py`; modify `requirements.txt`; create `tests/test_s7_report.py`.

- [ ] **Step 1: Tests first** (`tests/test_s7_report.py`): builder — given a synthetic payload (NB=15, H=130, L=1950, q_h=-60 kW, heat 120 MWh / cool 40 MWh thermal, base cost $80k), assert conventional capex = 60×500 = $30k mid, gshp capex = 80k + 60×570, operating costs match the formulas to 1 cent, payback = Δcapex/Δopex (and `None` when savings ≤ 0), and the output dict has exactly the four section keys + `inputs_echo`. AI — `@patch("geosite.s7_report.ai.anthropic.Anthropic")` returning a mock whose `messages.create` yields a response with `.content=[Mock(type="text", text=json.dumps(valid_review))]`; assert parse; second test: `messages.create` raises `anthropic.APIConnectionError` → `(None, reason)`; third: no env key (monkeypatch delenv) → `(None, "not configured")` without constructing the client.
- [ ] **Step 2: Implement** `builder.py` (constants + `build_report(data: dict) -> dict`, pure, no I/O) and `ai.py` (`generate_review(report: dict) -> tuple[dict | None, str | None]`) per C.0. `__init__.py` re-exports both. Add `anthropic` to `requirements.txt` and `pip install anthropic` in the venv. `import anthropic` at module top of `ai.py` only (keeps app importable if the wheel is missing? No — it's a hard dep now; requirements covers it).
- [ ] **Step 3:** Run the new tests, full suite, commit: `git commit -m "feat(s7): report builder with conventional-HVAC comparison + Claude review module"`

## Task C2: `POST /api/report` route

**Files:** Modify `app.py`; create `tests/test_api_report.py`.

- [ ] **Step 1: Tests first.** Contract: request body = `{design: {...stage2 result...}, site: {...}, loads: {...}, cost: {...}, strategy: {...}, annual_heat_kwh_th: float, annual_cool_kwh_th: float}`. With `geosite.s7_report.ai.generate_review` patched to return a canned review: 200 with keys `{report, ai_review, ai_error}` where `ai_review` is the canned dict and `ai_error` is None. With it patched to `(None, "timeout")`: still 200, `ai_review` None, `ai_error == "timeout"`. Missing `design` → 400 field `design`. Non-numeric annual kWh → 400.
- [ ] **Step 2: Implement** the route: validate presence/type of the seven top-level keys (dict/dict/dict/dict/dict/float/float — `cost` and `strategy` may be `None` with the corresponding report sections marked unavailable), call `build_report`, then `generate_review` (never let an AI exception 500 the route — wrap in try/except as a final guard), return `jsonify({"report": ..., "ai_review": ..., "ai_error": ...})`.
- [ ] **Step 3:** Full suite, commit: `git commit -m "feat(api): POST /api/report — structured s7 report with AI review"`

## Task C3: s7 UI

**Files:** Modify `templates/index.html`, `static/main.js`, `static/style.css`, `tests/test_ui_template.py`.

- [ ] **Step 1: ids test first.** Add to `REQUIRED_IDS`: `s7-section`, `s7-generate-btn`, `s7-error`, `s7-report`, `s7-design`, `s7-performance`, `s7-cost`, `s7-ai`, `s7-ai-badge`, `s7-copy-btn`.
- [ ] **Step 2: index.html.** Sidebar: change the s7 item from `disabled` + "soon" badge to `active-dim` (matching the other passive stages). After `#s6-section`, add a hidden `#s7-section`: stage-header (pill `s7`, label "Report", note "Fixed-structure summary — design, savings, cost comparison, AI review"), a `#s7-generate-btn` calc-btn ("Generate Report"), `#s7-error` banner, and `#s7-report` (hidden) containing four `card`s with the content ids above. The AI card's header carries `<span id="s7-ai-badge" class="ai-pill">AI Analysis — claude-haiku-4-5</span>` and a static caveat line: *"Automated review of a pre-feasibility estimate — not an engineering design."* Add `#s7-copy-btn` ("Copy report as text") at the bottom.
- [ ] **Step 3: main.js.** (a) In `fetchStrategy`, after successful render: store `window.__geositeLast = {stage1: stage1Result, stage2: lastStage2Result, cost: lastCostResult, strategy: res}` — introduce module-level `lastStage2Result` (set in `renderStage2`) and `lastCostResult` (set in `fetchCostEstimate`); unhide `#s7-section`. Add both to the `invalidateStage1` hide list. (b) `generateReport()`: compute `annual_heat_kwh_th = -sum(min(h,0))/1000`, `annual_cool_kwh_th = sum(max(h,0))/1000` over `strategy.hourly_profile`; POST `/api/report`; loading state on the button; render — design/performance/cost sections as label:value rows (reuse `stat`/`cost-note` classes), AI section as verdict paragraph + four titled `<ul>`s (strengths/concerns/risks/next steps); when `ai_error`, show the neutral note in `#s7-ai` instead. (c) Copy button: build a plain-text serialization (section headings, `label: value` lines, `- ` bullets — no HTML) and `navigator.clipboard.writeText`, flashing the button text to "Copied". 
- [ ] **Step 4: style.css.** `.ai-pill` (accent-soft background, accent text, radius 999px, 11px), minimal `#s7-report .report-row` spacing. Reuse existing tokens.
- [ ] **Step 5: Manual verification.** Full run 60601/Small Office through s6, Generate Report: all four sections populate (with a real `ANTHROPIC_API_KEY` in `.env` the AI card fills; with the key unset the card shows the unavailable note and everything else renders); copy button yields readable plain text; editing a Step-1 input hides s7. Full suite, commit: `git commit -m "feat(ui): s7 in-page report — generate, render, copy; AI analysis card"`

## Task C4: Final verification sweep

- [ ] Full suite: `source venv/bin/activate && python -m pytest tests/ -v` — all green.
- [ ] End-to-end browser pass: Smart Mode s1→s7 (once with key, once with `ANTHROPIC_API_KEY` unset), Manual Mode calculate, `/dev` trace (verify the s4a eq-block aspect text update from Task A1), no console errors.
- [ ] Greps: `grep -rn "FOOTPRINT_ASPECT" geosite tests templates` → 0 hits; `grep -n "s_T_in_HP\b" templates static tests` → only the `_heat`/`_cool` variants; `grep -rn "9.0.*aspect\|aspect.*9" geosite/s4_sizing/footprint.py` → only the array-aspect docstring distinction.

---

## Commit Plan (summary)

1. `fix(s4): building-type footprint aspect ratios replace fixed aspect-9` — footprint.py + 5 re-pinned test files + dev.html text
2. `feat(s4): load-density NB cross-check with footprint capacity warning` — footprint.py, app.py, main.js, index.html, tests
3. `feat(ui): borehole/pipe + per-mode EWT params in Smart Advanced; forward overrides and NB to s6` — index.html, main.js, test_ui_template.py
4. `refactor(api): shared advanced-param defaults + range validation for overrides` — app.py, strategy.py, new defaults.py, tests
5. `feat(s7): report builder with conventional-HVAC comparison + Claude review module` — geosite/s7_report/*, requirements.txt, tests
6. `feat(api): POST /api/report — structured s7 report with AI review` — app.py, tests
7. `feat(ui): s7 in-page report — generate, render, copy; AI analysis card` — index.html, main.js, style.css, tests

## Self-Review Notes

- **Optimizer untouched:** Section A changes bounds inputs (realistic aspect) and adds an advisory check; `find_optimal_nb`'s objective, sweep, H_min constraint, and depth fallback are byte-identical.
- **No invented methods:** every new constant carries a source or an explicit PLACEHOLDER marker; the aspect table instructs verification against DOE scorecards before commit; economics constants are flagged for the professor's calibration pass.
- **Dead-field bug fixed, not papered over:** `s_T_in_HP` was silently ignored on the two-pass path; the split into `s_T_in_HP_heat`/`s_T_in_HP_cool` makes the UI honest about what the sizing actually consumes.
- **s5/s6/stage2 coherence:** forwarding the user's overrides and the computed NB into `/api/strategy` removes two silent divergences found in the audit.
- **AI review degrades gracefully:** no key / timeout / API error → report still renders; the route never 500s on AI failure; the pre-feasibility caveat is enforced in the prompt AND duplicated as static UI text so it survives any model output.
- **Contract safety:** all API changes are additive keys or new endpoints; `/calculate/smart` and `/calculate` shapes unchanged; NB-range value re-pins are confined to tests that pinned aspect-9 artifacts.
- **Deferred (documented, not dropped):** site-availability fraction for nb_max; COP correction of ground loads; one-sided vs net q_y divergence between stage2 and s6; pygfunction benchmark; s6 tuning params exposure; coverage statistics for the soil CSV.

# UI Aesthetic Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the GeoSite Advisor web UI into a polished, professional engineering-SaaS look — Inter typography, a coherent token-based color system, stat-card results with comparison bars, a cost-range visualization, and full mobile responsiveness — without adding or removing any functionality.

**Architecture:** One design-system stylesheet (`static/style.css`, full rewrite) lands first with all component classes; subsequent tasks migrate `templates/index.html` section by section off its inline styles and onto those classes, with matching `static/main.js` render tweaks (no-emoji labels, comparison-bar widths, cost-range marker, loading states). A small pytest template-regression suite pins every DOM id that `main.js` depends on, so restructuring cannot silently break the JS.

**Tech Stack:** Plain CSS (no framework, no build step — per `frontend_design/design-notes.md`), vanilla JS, Jinja2 templates, Inter via Google Fonts, Chart.js 4.4.0 (already loaded from CDN), pytest + Flask test client.

## Global Constraints

- No new JS/CSS frameworks, no build step — plain CSS and vanilla JS only (project decision recorded in `frontend_design/design-notes.md`)
- `templates/dev.html` also links `/static/style.css` and uses these shared classes: `card`, `stage-pill`, `stage-label`, `files-table`, `result-card`, `sidebar`, `badge`, `hidden`. **Do not rename or delete any existing class** — restyle them in place and add new classes alongside
- Every DOM id referenced by `static/main.js` must survive unchanged (the Task 1 test suite enforces this): `btn-smart, btn-manual, panel-smart, panel-manual, zip_code, soil_confidence, building_type, floor_area_m2, year_built, proto-area-hint, year-factor-hint, s_B, s_A, s_T_in_HP, s_mfls, smart-error, smart-btn, pipeline-panel, pipeline-s1, pipeline-s2, smart-result, sres-L, sres-H, sres-NB, two-pass-block, sres-L-heat, sres-L-cool, sres-governing, sres-imbalance-line, sres-solar-line, cost-section, cost-region-tag, cost-state-tag, cost-best-pft, cost-best-total, cost-base-pft, cost-base-total, cost-worst-pft, cost-worst-total, cost-cmp-base, cost-cmp-us, cost-cmp-best, cost-cmp-worst, cost-breakdown-table, cost-breakdown-body, s6-section, s6-headline, s6-before-L, s6-before-cost, s6-after-L, s6-after-cost, s6-peaker-kw, s6-peaker-type, s6-chart-a, sizing-form, calc-error, calc-btn, result-panel, res-L, res-H, res-NB`
- Design tokens (exact values, defined once in Task 2 and used everywhere): background `#f6f8fa`, surface `#ffffff`, border `#e3e8ee`, ink `#16232f`, muted ink `#5b6b7b`, accent `#0e7c5b`, accent hover `#0a6448`, accent tint `#e6f4ee`, heating blue `#2563eb`, cooling red `#dc2626`, warning `#b45309`, sidebar `#0f1d29`
- Font: Inter (weights 400, 500, 600, 700, 800) from Google Fonts, falling back to `system-ui, -apple-system, "Segoe UI", sans-serif`
- Chart sign-color convention (keep): heating/negative = blue, cooling/positive = red, cutoff line = amber/warning
- No emojis anywhere in the UI (currently in two-pass block, solar warning, and pipeline s1 line — remove them)
- Mobile breakpoints: `900px` (sidebar collapses to top bar, grids stack) and `560px` (single-column everything)
- Run tests with: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v` (plus the full suite before each commit)
- **Sequencing with the companion plan:** `2026-07-06-methodology-precision.md` should be executed FIRST. Its Task 7 replaces the `s_NB` input with `s_H_target` and adds `s_ignore_top_pct` and `s6-coverage`. This plan's markup snippets assume those exist; if the precision plan has NOT run, keep the `s_NB` field markup where snippets show `s_H_target` and skip the `s6-coverage`/`s_ignore_top_pct` references — the Task 1 tests accept either variant
- No comments in code unless the WHY is non-obvious

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/test_ui_template.py` | Pins every JS-hook id; regression guard for all later tasks |
| Modify | `static/style.css` | Full rewrite: tokens, base, shell, all components (Task 2) |
| Modify | `templates/index.html` | Font links, sidebar/header markup, section-by-section de-inlining |
| Modify | `templates/references.html` | Font links only |
| Modify | `static/main.js` | Label/format polish, bar widths, cost range marker, loading states, hidden-class toggling |

Current-state findings this plan addresses (from reading the code):
- `index.html` has ~30 inline `style="..."` attributes (two-pass block, cost section, entire s6 section) — everything the redesign touches moves to classes
- `main.js` toggles `#s6-section` via `style.display` while everything else uses the `.hidden` class — unified to `.hidden`
- Emojis used as icons (two-pass, solar warning, rock/soil lines) — replaced with text labels and styled callouts
- No mobile layout at all (fixed 220px sidebar, `max-width:760px` main)
- Result values, cost totals, and headline numbers have inconsistent formatting (`toLocaleString` vs `toFixed` mixes) — one `fmtInt`/`fmtUSD` helper pair
- The s6 chart is squeezed into 180px with default Chart.js styling

---

## Task 1: Template Hook-Id Regression Suite

**Files:**
- Test: `tests/test_ui_template.py` (create)

**Interfaces:**
- Consumes: Flask `app` from `app.py`, `templates/index.html`
- Produces: a parametrized test over `REQUIRED_IDS` that every later task must keep green. Later tasks append ids to `REQUIRED_IDS` when they introduce new hooks (`bar-L-heat`, `bar-L-cool`, `cost-range-fill`, `cost-range-marker`, `cost-range-min`, `cost-range-max`, `cost-range-label`).

- [ ] **Step 1: Write the test file**

Create `tests/test_ui_template.py`:

```python
"""Regression guard: static/main.js queries these ids; index.html must keep them."""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


REQUIRED_IDS = [
    "btn-smart", "btn-manual", "panel-smart", "panel-manual",
    "zip_code", "soil_confidence", "building_type", "floor_area_m2",
    "year_built", "proto-area-hint", "year-factor-hint",
    "s_B", "s_A", "s_T_in_HP", "s_mfls",
    "smart-error", "smart-btn",
    "pipeline-panel", "pipeline-s1", "pipeline-s2",
    "smart-result", "sres-L", "sres-H", "sres-NB",
    "two-pass-block", "sres-L-heat", "sres-L-cool", "sres-governing",
    "sres-imbalance-line", "sres-solar-line",
    "cost-section", "cost-region-tag", "cost-state-tag",
    "cost-best-pft", "cost-best-total", "cost-base-pft", "cost-base-total",
    "cost-worst-pft", "cost-worst-total",
    "cost-cmp-base", "cost-cmp-us", "cost-cmp-best", "cost-cmp-worst",
    "cost-breakdown-table", "cost-breakdown-body",
    "s6-section", "s6-headline", "s6-before-L", "s6-before-cost",
    "s6-after-L", "s6-after-cost", "s6-peaker-kw", "s6-peaker-type",
    "s6-chart-a",
    "sizing-form", "calc-error", "calc-btn",
    "result-panel", "res-L", "res-H", "res-NB",
]


@pytest.fixture(scope="module")
def index_html():
    app.config["TESTING"] = True
    with app.test_client() as c:
        return c.get("/").get_data(as_text=True)


def test_index_renders(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("el_id", REQUIRED_IDS)
def test_index_contains_hook_id(index_html, el_id):
    assert f'id="{el_id}"' in index_html, f"main.js hook id '{el_id}' missing"


def test_geometry_input_present(index_html):
    # s_NB before the methodology-precision plan, s_H_target after
    assert 'id="s_H_target"' in index_html or 'id="s_NB"' in index_html


def test_references_renders(client):
    assert client.get("/references").status_code == 200


def test_dev_renders(client):
    assert client.get("/dev").status_code == 200
```

- [ ] **Step 2: Run the suite — it must pass against the CURRENT templates**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS (this suite documents the status quo; later tasks keep it green)

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_template.py
git commit -m "test(ui): template hook-id regression suite"
```

---

## Task 2: Design System Stylesheet + Inter Typography

**Files:**
- Modify: `static/style.css` (full replacement)
- Modify: `templates/index.html` (head, lines 3–8)
- Modify: `templates/references.html` (head, add font links after the stylesheet link)
- Test: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: nothing
- Produces: every class later tasks use — `stat-grid`, `stat`, `stat-label`, `stat-value`, `stat-unit`, `stat-sub`, `stat-accent`, `stat-warn`, `result-chip`, `two-pass`, `two-pass-title`, `two-pass-sub`, `two-pass-note`, `mode-bars`, `mode-bar-row`, `mode-bar-label`, `mode-bar-track`, `mode-bar-fill`, `mode-bar-heat`, `mode-bar-cool`, `mode-bar-value`, `callout`, `callout-warn`, `cost-grid`, `cost-range`, `cost-range-head`, `cost-range-title`, `cost-range-total`, `cost-range-track`, `cost-range-marker`, `cost-range-ends`, `cost-note`, `strategy-headline`, `strategy-coverage`, `chart-wrap`, `page-sub`, `sidebar-sub`, `calc-btn.loading`. All existing class names keep working (dev.html depends on them).

- [ ] **Step 1: Add font links to both templates**

In `templates/index.html`, replace:

```html
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GeoSite Advisor</title>
  <link rel="stylesheet" href="/static/style.css">
```

with:

```html
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GeoSite Advisor — Geothermal Borefield Sizing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
```

In `templates/references.html`, immediately BEFORE its `<link rel="stylesheet" href="/static/style.css">` line, add:

```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Replace `static/style.css` in full**

Replace the entire contents of `static/style.css` with:

```css
/* ════════════════════════════════════════════════════════════════
   GeoSite Advisor design system
   Tokens → base → shell → components → utilities → responsive
   dev.html shares this file: never remove an existing class.
   ════════════════════════════════════════════════════════════════ */

/* ── 1. Tokens ── */
:root {
  --font-sans: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif;

  --bg: #f6f8fa;
  --surface: #ffffff;
  --border: #e3e8ee;
  --border-strong: #cbd5e1;

  --text: #16232f;
  --text-muted: #5b6b7b;
  --text-faint: #8a99a8;
  --unit-color: #8a99a8;

  --accent: #0e7c5b;
  --accent-hover: #0a6448;
  --accent-active: #084f39;
  --accent-soft: #e6f4ee;

  --heat: #2563eb;
  --cool: #dc2626;
  --warn: #b45309;
  --warn-soft: #fef3c7;
  --warn-border: #fcd34d;
  --error-color: #b91c1c;
  --error-soft: #fee2e2;
  --error-border: #fca5a5;

  --sidebar-bg: #0f1d29;
  --sidebar-text: #9fb0bf;
  --sidebar-active-bg: rgba(14, 124, 91, 0.28);
  --sidebar-active-text: #ffffff;

  --result-bg: #f2faf6;
  --result-border: #bfe6d4;
  --tab-active: var(--accent);

  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 14px;
  --shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.05);
  --shadow: 0 1px 3px rgba(16, 24, 40, 0.07), 0 4px 14px rgba(16, 24, 40, 0.05);
}

/* ── 2. Reset + base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.45;
  color: var(--text);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* ── 3. Shell ── */
.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 232px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.sidebar-title {
  font-size: 15px;
  font-weight: 700;
  color: #ffffff;
  padding: 24px 20px 6px;
  letter-spacing: -0.01em;
}

.sidebar-sub {
  font-size: 11px;
  color: var(--sidebar-text);
  padding: 0 20px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  letter-spacing: 0.02em;
}

.sidebar-footer {
  margin-top: auto;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-link {
  font-size: 12px;
  color: var(--sidebar-text);
  text-decoration: none;
  opacity: 0.75;
}
.sidebar-link:hover { opacity: 1; color: #fff; }

.stage-list { list-style: none; padding: 12px 8px; }

.stage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  margin: 1px 0;
  font-size: 13px;
  color: var(--sidebar-text);
  cursor: default;
  border-radius: var(--radius-sm);
}

.stage-item.active {
  background: var(--sidebar-active-bg);
  color: var(--sidebar-active-text);
  font-weight: 600;
}

.stage-item.active-dim { color: rgba(159, 176, 191, 0.8); font-weight: 500; }

.stage-item.active a {
  color: var(--sidebar-active-text);
  text-decoration: none;
  display: flex;
  gap: 8px;
  align-items: center;
}

.stage-item.disabled { opacity: 0.4; }

.stage-name { flex: 1; }

.badge {
  font-size: 10px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.12);
  color: var(--sidebar-text);
  padding: 1px 7px;
  border-radius: 999px;
  letter-spacing: 0.03em;
}

.main {
  flex: 1;
  padding: 40px 44px 72px;
  max-width: 820px;
}

.page-title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-bottom: 4px;
  color: var(--text);
}

.page-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 26px;
}

/* ── 4. Mode toggle (segmented control) ── */
.mode-toggle {
  display: inline-flex;
  gap: 4px;
  margin-bottom: 28px;
  background: #eceff3;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px;
}

.mode-btn {
  padding: 8px 18px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-btn:hover { color: var(--text); }

.mode-btn.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}

.mode-badge {
  font-size: 10px;
  font-weight: 600;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 2px 7px;
  border-radius: 999px;
}

.mode-btn:not(.active) .mode-badge { background: #e0e5ea; color: var(--text-muted); }

/* ── 5. Stage headers ── */
.stage-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 28px 0 10px;
}

.stage-pill {
  font-size: 11px;
  font-weight: 700;
  background: var(--accent);
  color: #fff;
  padding: 2px 8px;
  border-radius: 5px;
  letter-spacing: 0.04em;
}

.stage-label { font-size: 14px; font-weight: 700; color: var(--text); }

.stage-note {
  font-size: 11px;
  color: var(--text-faint);
  margin-left: auto;
  font-style: normal;
}

/* ── 6. Cards + fields ── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.card-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.hint { font-size: 12px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.5; }
.hint-inline { font-size: 12px; font-weight: 400; color: var(--text-faint); }

.field { margin-bottom: 16px; }
.field:last-child { margin-bottom: 0; }

.field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--text);
}

.field label em {
  font-style: normal;
  font-weight: 400;
  color: var(--text-faint);
  font-size: 12px;
}

.field-hint { font-size: 12px; color: var(--text-faint); margin-top: 5px; display: block; }

.input-row { display: flex; align-items: center; gap: 10px; }

.input-row input,
.input-row select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text);
  background: var(--surface);
  transition: border-color 0.15s, box-shadow 0.15s;
  max-width: 240px;
}

.input-row select { max-width: 340px; }

.input-row input:focus,
.input-row select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(14, 124, 91, 0.14);
}

.input-row input.input-error { border-color: var(--error-color); }
.input-row input.input-error:focus { box-shadow: 0 0 0 3px rgba(185, 28, 28, 0.12); }

.unit { font-size: 12px; font-weight: 500; color: var(--unit-color); white-space: nowrap; }

.field-error {
  display: block;
  font-size: 12px;
  color: var(--error-color);
  margin-top: 4px;
  min-height: 16px;
}

/* ── 7. Advanced details ── */
.advanced-details { margin-bottom: 4px; }

.advanced-details summary {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  padding: 8px 0;
  user-select: none;
}

.advanced-details summary:hover { color: var(--accent); }

/* ── 8. Buttons ── */
.calc-btn {
  display: block;
  width: 100%;
  padding: 13px;
  margin-top: 22px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.01em;
  transition: background 0.15s, transform 0.05s;
  position: relative;
}

.calc-btn:hover { background: var(--accent-hover); }
.calc-btn:active { background: var(--accent-active); transform: translateY(1px); }
.calc-btn:disabled { background: #9ca3af; cursor: not-allowed; transform: none; }

.calc-btn.loading { padding-right: 40px; }
.calc-btn.loading::after {
  content: "";
  position: absolute;
  right: 16px;
  top: 50%;
  width: 15px;
  height: 15px;
  margin-top: -8px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: btn-spin 0.7s linear infinite;
}

@keyframes btn-spin { to { transform: rotate(360deg); } }

/* ── 9. Error banner ── */
.calc-error {
  margin-top: 12px;
  padding: 11px 14px;
  background: var(--error-soft);
  border: 1px solid var(--error-border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--error-color);
}

.calc-error.hidden { display: none; }

/* ── 10. Pipeline trace panel ── */
.pipeline-panel { margin-top: 16px; display: flex; gap: 12px; }

.pipeline-step {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}

.pipeline-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.pipeline-values { font-size: 13px; color: var(--text); line-height: 1.7; }

/* ── 11. Result panel + stat cards ── */
.result-panel {
  margin-top: 28px;
  background: var(--result-bg);
  border: 1px solid var(--result-border);
  border-radius: var(--radius-lg);
  padding: 22px 26px;
  box-shadow: var(--shadow-sm);
}

.result-panel.hidden { display: none; }

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 16px;
}

.result-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  margin-bottom: 0;
}

.result-chip {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--surface);
  border: 1px solid var(--result-border);
  border-radius: 999px;
  padding: 3px 12px;
  white-space: nowrap;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.stat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}

.stat-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.stat-value {
  display: block;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.stat-unit {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-faint);
  margin-left: 4px;
}

.stat-sub { display: block; font-size: 12px; color: var(--text-muted); margin-top: 5px; }

.stat-accent .stat-value { color: var(--accent); }
.stat-warn .stat-value { color: var(--warn); }

/* Legacy dev.html cards */
.result-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}

.result-grid { display: flex; flex-direction: column; gap: 12px; }

.result-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid var(--result-border);
  padding-bottom: 10px;
}

.result-item:last-child { border-bottom: none; padding-bottom: 0; }

.result-label { font-size: 13px; color: var(--text-muted); }

.result-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent-active);
  font-variant-numeric: tabular-nums;
}

/* ── 12. Two-pass comparison bars ── */
.two-pass {
  margin-top: 16px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.two-pass-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 10px; }
.two-pass-sub { font-weight: 400; font-size: 12px; color: var(--text-faint); }

.mode-bars { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }

.mode-bar-row {
  display: grid;
  grid-template-columns: 64px 1fr 96px;
  align-items: center;
  gap: 10px;
}

.mode-bar-label { font-size: 12px; font-weight: 500; color: var(--text-muted); }

.mode-bar-track {
  height: 10px;
  background: #eef1f4;
  border-radius: 999px;
  overflow: hidden;
}

.mode-bar-fill { height: 100%; border-radius: 999px; width: 0; transition: width 0.4s ease; }
.mode-bar-heat { background: var(--heat); }
.mode-bar-cool { background: var(--cool); }

.mode-bar-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.two-pass-note { font-size: 12px; color: var(--text-muted); line-height: 1.5; }

/* ── 13. Callouts ── */
.callout {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  line-height: 1.55;
}

.callout-warn {
  background: var(--warn-soft);
  border: 1px solid var(--warn-border);
  color: #7c4a03;
}

/* ── 14. Cost section ── */
.cost-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}

.cost-card { text-align: center; padding: 16px 14px; margin-bottom: 0; }
.cost-card-base { border: 2px solid var(--accent); }

.cost-scenario-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.cost-headline {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.cost-unit { font-size: 13px; font-weight: 400; color: var(--text-faint); }
.cost-subline { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

.cost-range { margin-bottom: 14px; }

.cost-range-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}

.cost-range-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.cost-range-total { font-size: 15px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }

.cost-range-track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, #34d399, #fbbf24, #f87171);
  opacity: 0.9;
}

.cost-range-marker {
  position: absolute;
  top: -4px;
  width: 4px;
  height: 18px;
  margin-left: -2px;
  background: var(--text);
  border-radius: 2px;
  box-shadow: 0 0 0 2px var(--surface);
}

.cost-range-ends {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.cost-note { padding: 10px 16px; font-size: 12px; color: var(--text-muted); margin-bottom: 16px; }

.breakdown-toggle {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  cursor: pointer;
  margin-bottom: 10px;
}

/* ── 15. Strategy section ── */
.strategy-headline {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 14px;
  line-height: 1.55;
}

.stat-grid-3 { grid-template-columns: repeat(3, 1fr); margin-bottom: 14px; }

.chart-wrap {
  position: relative;
  height: 220px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
}

.strategy-coverage {
  margin-top: 10px;
  padding: 10px 14px;
  background: var(--accent-soft);
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  color: var(--accent-active);
  line-height: 1.55;
}

.strategy-coverage:empty { display: none; }

/* ── 16. Tabs (manual mode) ── */
.tab-strip { display: flex; border-bottom: 2px solid var(--border); margin-bottom: 24px; }

.tab-btn {
  background: none;
  border: none;
  padding: 10px 20px;
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover { color: var(--text); }

.tab-btn.active { color: var(--tab-active); border-bottom-color: var(--tab-active); font-weight: 600; }

.tab-panel { display: block; }
.tab-panel.hidden { display: none; }

/* ── 17. Tables ── */
.files-table { width: 100%; border-collapse: collapse; font-size: 12px; }

.files-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  border-bottom: 2px solid var(--border);
}

.files-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  font-variant-numeric: tabular-nums;
}

.files-table tr:last-child td { border-bottom: none; }

/* ── 18. References page ── */
.ref-entry { padding: 12px 0; border-bottom: 1px solid var(--border); }
.ref-entry:last-child { border-bottom: none; }
.ref-authors { font-size: 12px; color: var(--text-muted); margin-bottom: 2px; }
.ref-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 3px; }
.ref-source { font-size: 12px; color: var(--text-muted); }
.ref-source a { color: var(--accent); }

/* ── 19. Utilities ── */
.hidden { display: none !important; }

/* ── 20. Responsive ── */
@media (max-width: 900px) {
  .layout { flex-direction: column; }

  .sidebar {
    width: 100%;
    height: auto;
    position: static;
    flex-direction: row;
    align-items: center;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .sidebar-title { padding: 14px 16px; white-space: nowrap; }
  .sidebar-sub { display: none; }
  .sidebar-footer { margin: 0 0 0 auto; padding: 14px 16px; border-top: none; white-space: nowrap; }

  .stage-list { display: flex; padding: 8px; }
  .stage-item { padding: 6px 10px; white-space: nowrap; }

  .main { padding: 24px 20px 56px; max-width: none; }

  .pipeline-panel { flex-direction: column; }
  .cost-grid { grid-template-columns: 1fr; }
  .stat-grid-3 { grid-template-columns: 1fr; }
}

@media (max-width: 560px) {
  .mode-toggle { display: flex; width: 100%; }
  .mode-btn { flex: 1; justify-content: center; }
  .input-row input, .input-row select { max-width: none; }
  .stage-note { display: none; }
  .stat-grid { grid-template-columns: 1fr 1fr; }
  .mode-bar-row { grid-template-columns: 56px 1fr 80px; }
}
```

- [ ] **Step 3: Run the template suite and full test suite**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py tests/ -v`
Expected: all PASS (only CSS + head links changed; no ids touched)

- [ ] **Step 4: Visual check**

Run `source venv/bin/activate && flask --app app run --port 5000`, open `http://127.0.0.1:5000`. Verify: Inter renders (inspect computed font-family on body), inputs show the green focus ring, the mode toggle looks like a segmented control, `/dev` and `/references` still render without layout breakage (old markup + new styles is expected to look slightly unpolished until Tasks 3–6). Stop the server.

- [ ] **Step 5: Commit**

```bash
git add static/style.css templates/index.html templates/references.html
git commit -m "feat(ui): design system stylesheet + Inter typography"
```

---

## Task 3: Sidebar, Header, and Mode Toggle Markup

**Files:**
- Modify: `templates/index.html` (sidebar block lines ~13–29; page title line ~33)
- Test: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 2 classes `sidebar-sub`, `page-sub`
- Produces: unchanged ids; new static markup only

- [ ] **Step 1: Update the sidebar block**

In `templates/index.html`, replace:

```html
    <aside class="sidebar">
      <div class="sidebar-title">GeoSite Advisor</div>
      <nav>
```

with:

```html
    <aside class="sidebar">
      <div>
        <div class="sidebar-title">GeoSite Advisor</div>
        <div class="sidebar-sub">Geothermal borefield feasibility</div>
      </div>
      <nav>
```

- [ ] **Step 2: Add a page subtitle under the title**

Replace:

```html
      <h1 class="page-title">Borefield Sizing</h1>
```

with:

```html
      <h1 class="page-title">Borefield Sizing</h1>
      <p class="page-sub">Vertical closed-loop ground-source heat pump sizing — ASHRAE three-pulse method (Philippe et&nbsp;al. 2010)</p>
```

- [ ] **Step 3: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS

- [ ] **Step 4: Visual check**

Run the app, confirm the sidebar shows the subtitle on desktop and collapses to a horizontal top bar below 900px wide (resize the window). Stop the server.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat(ui): refined sidebar, header, and mode toggle"
```

---

## Task 4: Results + Pipeline Sections (Stat Cards, Two-Pass Bars, No Emojis)

**Files:**
- Modify: `templates/index.html` (`#smart-result` block, lines ~200–231)
- Modify: `static/main.js` (smart result rendering ~lines 146–239; add format helpers)
- Test: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 2 classes `stat-grid`, `stat`, `result-head`, `result-chip`, `two-pass`, `mode-bar-*`, `callout callout-warn`
- Produces: new ids `bar-L-heat`, `bar-L-cool` (added to `REQUIRED_IDS`); JS helpers `fmtInt(n)` and `fmtUSD(n)` used by Tasks 5–6

- [ ] **Step 1: Add the new ids to the regression suite**

In `tests/test_ui_template.py`, extend `REQUIRED_IDS` — after the line `"sres-imbalance-line", "sres-solar-line",` add:

```python
    "bar-L-heat", "bar-L-cool",
```

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v -k "bar_L or bar-L"`
Expected: 2 FAILs (ids not yet in template). Note: pytest normalizes the parametrized id, so if `-k` matches nothing run the whole file and confirm exactly 2 failures.

- [ ] **Step 2: Replace the `#smart-result` block in `templates/index.html`**

Replace the entire block from `<div id="smart-result" class="result-panel hidden">` through its matching `</div>` (currently ending just before `<!-- s5: Cost Estimate ... -->`) with:

```html
        <div id="smart-result" class="result-panel hidden">
          <div class="result-head">
            <h2 class="result-title">Sizing Result</h2>
            <span class="result-chip">Governing: <span id="sres-governing">—</span></span>
          </div>
          <div class="stat-grid">
            <div class="stat">
              <span class="stat-label">Total borefield length</span>
              <span class="stat-value"><span id="sres-L">—</span><span class="stat-unit">m</span></span>
            </div>
            <div class="stat">
              <span class="stat-label">Borehole depth</span>
              <span class="stat-value"><span id="sres-H">—</span><span class="stat-unit">m</span></span>
            </div>
            <div class="stat">
              <span class="stat-label">Boreholes</span>
              <span class="stat-value"><span id="sres-NB">—</span></span>
            </div>
          </div>
          <div id="two-pass-block" class="two-pass hidden">
            <div class="two-pass-title">Two-pass sizing check
              <span class="two-pass-sub">— heating and cooling evaluated independently; the larger governs</span>
            </div>
            <div class="mode-bars">
              <div class="mode-bar-row">
                <span class="mode-bar-label">Heating</span>
                <div class="mode-bar-track"><div class="mode-bar-fill mode-bar-heat" id="bar-L-heat"></div></div>
                <span class="mode-bar-value"><span id="sres-L-heat">—</span> m</span>
              </div>
              <div class="mode-bar-row">
                <span class="mode-bar-label">Cooling</span>
                <div class="mode-bar-track"><div class="mode-bar-fill mode-bar-cool" id="bar-L-cool"></div></div>
                <span class="mode-bar-value"><span id="sres-L-cool">—</span> m</span>
              </div>
            </div>
            <div id="sres-imbalance-line" class="two-pass-note"></div>
            <div id="sres-solar-line" class="callout callout-warn hidden">
              <strong>Thermal depletion risk:</strong> annual heat extraction exceeds injection (q<sub>y</sub> &lt; 0).
              Ground temperature will decline over the 10-year design horizon. Consider a
              <strong>solar thermal supplement</strong> (flat-plate collectors feeding ground-loop preheat)
              to rebalance annual heat flux and reduce required borefield length.
            </div>
          </div>
        </div>
```

- [ ] **Step 3: Update `static/main.js` rendering**

3a. Immediately after the `SOIL_CLASS_LABELS` constant (after its closing `};`), add the shared formatters:

```js
  function fmtInt(n) {
    return n == null ? '—' : Math.round(n).toLocaleString('en-US');
  }

  function fmtUSD(n) {
    return n == null ? '—' : '$' + Math.round(n).toLocaleString('en-US');
  }
```

3b. Replace the two-pass rendering block:

```js
    // Two-pass sizing breakdown
    const twoPassBlock = document.getElementById('two-pass-block');
    if (result.L_heat != null && result.L_cool != null) {
      document.getElementById('sres-L-heat').textContent = result.L_heat.toLocaleString();
      document.getElementById('sres-L-cool').textContent = result.L_cool.toLocaleString();
      const govLabel = result.governing === 'heating' ? '🥶 Heating' : '🌡 Cooling';
      document.getElementById('sres-governing').textContent = govLabel;
```

with:

```js
    // Two-pass sizing breakdown
    const twoPassBlock = document.getElementById('two-pass-block');
    if (result.L_heat != null && result.L_cool != null) {
      document.getElementById('sres-L-heat').textContent = fmtInt(result.L_heat);
      document.getElementById('sres-L-cool').textContent = fmtInt(result.L_cool);
      const maxL = Math.max(result.L_heat, result.L_cool, 1);
      document.getElementById('bar-L-heat').style.width =
        `${Math.max(0, result.L_heat) / maxL * 100}%`;
      document.getElementById('bar-L-cool').style.width =
        `${Math.max(0, result.L_cool) / maxL * 100}%`;
      document.getElementById('sres-governing').textContent =
        result.governing === 'heating' ? 'Heating' : 'Cooling';
```

3c. Replace the rock/soil class line builder (remove emojis):

```js
    const classLine  = [
      rockLabel  ? `<span title="SGMC bedrock class at depth">🪨 ${rockLabel}</span>` : null,
      soilLabel  ? `<span title="SSURGO surface soil (0–2 m)">🌱 ${soilLabel}</span>` : null,
    ].filter(Boolean).join(' &nbsp;·&nbsp; ');
```

with:

```js
    const classLine  = [
      rockLabel  ? `<span title="SGMC bedrock class at depth">Bedrock: ${rockLabel}</span>` : null,
      soilLabel  ? `<span title="SSURGO surface soil (0–2 m)">Surface soil: ${soilLabel}</span>` : null,
    ].filter(Boolean).join(' &nbsp;·&nbsp; ');
```

3d. Replace the data-availability marker in the same handler:

```js
      (site.data_available ? '✓ Deep borehole data' : '⚠ No soil data') +
```

with:

```js
      (site.data_available ? 'Deep borehole data available' : 'No soil data — defaults used') +
```

3e. Replace the headline stat population:

```js
    document.getElementById('sres-L').textContent  = result.L?.toLocaleString();
    document.getElementById('sres-H').textContent  = result.H?.toLocaleString();
    document.getElementById('sres-NB').textContent = result.NB?.toLocaleString();
```

with:

```js
    document.getElementById('sres-L').textContent  = fmtInt(result.L);
    document.getElementById('sres-H').textContent  = fmtInt(result.H);
    document.getElementById('sres-NB').textContent = fmtInt(result.NB);
```

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS (including the two new bar ids)

- [ ] **Step 5: Visual check**

Run the app, submit ZIP `60601` + Small Office. Verify: three stat cards with big tabular numbers, governing chip in the panel header, two horizontal bars whose widths reflect L_heat vs L_cool, no emojis anywhere in the result panel. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html static/main.js tests/test_ui_template.py
git commit -m "feat(ui): stat-card results and two-pass comparison bars"
```

---

## Task 5: Cost Section (Range Bar + De-Inlined Markup)

**Files:**
- Modify: `templates/index.html` (`#cost-section` block, lines ~234–283)
- Modify: `static/main.js` (`fetchCostEstimate`, lines ~422–483)
- Test: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 2 classes `cost-grid`, `cost-range*`, `cost-note`, `breakdown-toggle`; Task 4 helpers `fmtInt`, `fmtUSD`
- Produces: new ids `cost-range-fill` is NOT used (gradient track instead) — new ids are `cost-range-marker`, `cost-range-min`, `cost-range-max`, `cost-range-label` (added to `REQUIRED_IDS`)

- [ ] **Step 1: Add the new ids to the regression suite**

In `tests/test_ui_template.py`, extend `REQUIRED_IDS` — after `"cost-breakdown-table", "cost-breakdown-body",` add:

```python
    "cost-range-marker", "cost-range-min", "cost-range-max", "cost-range-label",
```

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: exactly 4 FAILs (the new ids)

- [ ] **Step 2: Replace the `#cost-section` block in `templates/index.html`**

Replace the entire block from `<div id="cost-section" class="hidden" style="margin-top:20px;">` through its matching `</div>` (just before `<!-- s6: Hybrid Strategy -->`) with:

```html
        <div id="cost-section" class="hidden">
          <div class="stage-header">
            <span class="stage-pill">s5</span>
            <span class="stage-label">Cost Estimate</span>
            <span class="stage-note">Regional drilling rates — <span id="cost-region-tag">—</span></span>
          </div>

          <div class="card cost-range">
            <div class="cost-range-head">
              <span class="cost-range-title">Installed cost range</span>
              <span class="cost-range-total" id="cost-range-label">—</span>
            </div>
            <div class="cost-range-track">
              <div class="cost-range-marker" id="cost-range-marker"></div>
            </div>
            <div class="cost-range-ends">
              <span id="cost-range-min">—</span>
              <span id="cost-range-max">—</span>
            </div>
          </div>

          <div class="cost-grid">
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

          <div class="card cost-note">
            <strong style="color:var(--text);">Contractor comparison:</strong>
            Your project (<span id="cost-state-tag">—</span>): <strong id="cost-cmp-base">—</strong>/ft &nbsp;|&nbsp;
            National avg: <strong id="cost-cmp-us">—</strong>/ft &nbsp;|&nbsp;
            Best case: <strong id="cost-cmp-best">—</strong>/ft &nbsp;|&nbsp;
            Worst case: <strong id="cost-cmp-worst">—</strong>/ft
          </div>

          <details>
            <summary class="breakdown-toggle">Show line-item breakdown (base case)</summary>
            <table class="files-table" id="cost-breakdown-table">
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

- [ ] **Step 3: Update `fetchCostEstimate` in `static/main.js`**

Replace:

```js
    .then(cost => {
      document.getElementById('cost-section').classList.remove('hidden');
      const fmtTotal = (n) => '$' + Math.round(n).toLocaleString();

      document.getElementById('cost-region-tag').textContent = cost.region_used;
      document.getElementById('cost-state-tag').textContent = state || 'National';

      document.getElementById('cost-best-pft').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
      document.getElementById('cost-best-total').textContent = fmtTotal(cost.best.total_usd);
      document.getElementById('cost-base-pft').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
      document.getElementById('cost-base-total').textContent = fmtTotal(cost.base.total_usd);
      document.getElementById('cost-worst-pft').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);
      document.getElementById('cost-worst-total').textContent = fmtTotal(cost.worst.total_usd);
```

with:

```js
    .then(cost => {
      document.getElementById('cost-section').classList.remove('hidden');

      document.getElementById('cost-region-tag').textContent = cost.region_used;
      document.getElementById('cost-state-tag').textContent = state || 'National';

      document.getElementById('cost-best-pft').textContent  = '$' + cost.best.cost_per_ft.toFixed(2);
      document.getElementById('cost-best-total').textContent = fmtUSD(cost.best.total_usd);
      document.getElementById('cost-base-pft').textContent  = '$' + cost.base.cost_per_ft.toFixed(2);
      document.getElementById('cost-base-total').textContent = fmtUSD(cost.base.total_usd);
      document.getElementById('cost-worst-pft').textContent = '$' + cost.worst.cost_per_ft.toFixed(2);
      document.getElementById('cost-worst-total').textContent = fmtUSD(cost.worst.total_usd);

      const best = cost.best.total_usd, base = cost.base.total_usd, worst = cost.worst.total_usd;
      const span = Math.max(worst - best, 1);
      document.getElementById('cost-range-min').textContent = fmtUSD(best);
      document.getElementById('cost-range-max').textContent = fmtUSD(worst);
      document.getElementById('cost-range-label').textContent = fmtUSD(base) + ' expected';
      document.getElementById('cost-range-marker').style.left =
        `${Math.min(100, Math.max(0, (base - best) / span * 100))}%`;
```

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS

- [ ] **Step 5: Visual check**

Run the app, submit a smart calculation. Verify: gradient range bar with a dark marker positioned between the min/max labels, three scenario cards in a responsive grid (stacked below 900px), breakdown table opens from the styled toggle. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html static/main.js tests/test_ui_template.py
git commit -m "feat(ui): cost range visualization and cleaned cost section"
```

---

## Task 6: Strategy Section Restyle + Chart Polish

**Files:**
- Modify: `templates/index.html` (`#s6-section` block, lines ~286–313)
- Modify: `static/main.js` (`fetchStrategy` and `_renderS6ChartA`; the two `style.display` toggles)
- Test: `tests/test_ui_template.py`

**Interfaces:**
- Consumes: Task 2 classes `stat-grid-3`, `stat-accent`, `stat-warn`, `chart-wrap`, `strategy-headline`, `strategy-coverage`; Task 4 helpers `fmtInt`, `fmtUSD`
- Produces: `#s6-section` visibility now controlled by the `.hidden` class (not `style.display`); Chart.js styling uses the token colors

- [ ] **Step 1: Replace the `#s6-section` block in `templates/index.html`**

Replace the entire block from `<div id="s6-section" style="display:none;margin-top:24px">` through its matching closing `</div>` with (if the methodology-precision plan has not run, omit the `s6-coverage` div):

```html
        <div id="s6-section" class="hidden">
          <div class="stage-header">
            <span class="stage-pill">s6</span>
            <span class="stage-label">Hybrid System Strategy</span>
            <span class="stage-note">Load-duration-curve peak shaving</span>
          </div>
          <div id="s6-headline" class="strategy-headline">Calculating…</div>
          <div class="stat-grid stat-grid-3">
            <div class="stat">
              <span class="stat-label">Without peaker</span>
              <span class="stat-value" id="s6-before-L">—</span>
              <span class="stat-sub" id="s6-before-cost">—</span>
            </div>
            <div class="stat stat-accent">
              <span class="stat-label">With peaker</span>
              <span class="stat-value" id="s6-after-L">—</span>
              <span class="stat-sub" id="s6-after-cost">—</span>
            </div>
            <div class="stat stat-warn">
              <span class="stat-label">Peaker unit</span>
              <span class="stat-value" id="s6-peaker-kw">—</span>
              <span class="stat-sub" id="s6-peaker-type">—</span>
            </div>
          </div>
          <div class="chart-wrap">
            <canvas id="s6-chart-a"></canvas>
          </div>
          <div id="s6-coverage" class="strategy-coverage"></div>
        </div>
```

- [ ] **Step 2: Switch the visibility toggles in `static/main.js` to `.hidden`**

2a. In the smart submit handler, replace:

```js
    document.getElementById('s6-section').style.display = 'none';
```

with:

```js
    document.getElementById('s6-section').classList.add('hidden');
```

2b. In `fetchStrategy`, replace:

```js
    const s6Section = document.getElementById('s6-section');
    s6Section.style.display = 'block';
```

with:

```js
    const s6Section = document.getElementById('s6-section');
    s6Section.classList.remove('hidden');
```

- [ ] **Step 3: Polish the chart palette and headline in `static/main.js`**

3a. In `_renderS6ChartA`, replace:

```js
    const colors = ds.map(h =>
      h < 0 ? 'rgba(59,130,246,0.7)' : h > 0 ? 'rgba(239,68,68,0.7)' : 'transparent'
    );
```

with:

```js
    const colors = ds.map(h =>
      h < 0 ? 'rgba(37,99,235,0.65)' : h > 0 ? 'rgba(220,38,38,0.55)' : 'transparent'
    );
```

3b. In the same function, replace both cutoff dataset `borderColor: '#f59e0b',` occurrences with `borderColor: '#b45309',`.

3c. In the same options object, replace:

```js
        scales: {
          x: {display: false},
          y: {
            ticks: {callback: v => `${(v / 1000).toFixed(0)}kW`},
            grid: {color: 'rgba(0,0,0,0.05)'},
          },
        },
```

with:

```js
        scales: {
          x: {display: false},
          y: {
            ticks: {
              callback: v => `${(v / 1000).toFixed(0)} kW`,
              font: {family: "'Inter', sans-serif", size: 11},
              color: '#5b6b7b',
            },
            grid: {color: 'rgba(22,35,47,0.06)'},
          },
        },
```

3d. In `fetchStrategy`, replace the headline assembly:

```js
    document.getElementById('s6-headline').textContent =
      `Hybrid system reduces borefield from ${res.L_before.toLocaleString()} m → ` +
      `${res.L_after.toLocaleString()} m (−${reduction}%) with a ` +
      `${res.peaker_kW.toFixed(1)} kW ${peakerLabel}.`;
```

with:

```js
    document.getElementById('s6-headline').textContent =
      `A hybrid system reduces the borefield from ${fmtInt(res.L_before)} m to ` +
      `${fmtInt(res.L_after)} m (${reduction}% smaller) by adding a ` +
      `${res.peaker_kW.toFixed(1)} kW ${peakerLabel} for peak hours.`;
```

3e. Also in `fetchStrategy`, replace the last-height argument call:

```js
    _renderS6ChartA('s6-chart-a', res.hourly_profile, res.cutoff_W, res.dominant_mode, 180);
```

with:

```js
    _renderS6ChartA('s6-chart-a', res.hourly_profile, res.cutoff_W, res.dominant_mode, 220);
```

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_ui_template.py -v`
Expected: all PASS

- [ ] **Step 5: Visual check**

Run the app, submit a smart calculation, wait for s6. Verify: three stat cards (green "with peaker" value, amber peaker value), chart inside a bordered card at 220px with muted grid lines and Inter tick labels, coverage strip appears in a green tint (or is invisible when empty). Confirm the section hides again when a new calculation starts. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html static/main.js tests/test_ui_template.py
git commit -m "feat(ui): restyled hybrid strategy section and chart polish"
```

---

## Task 7: Loading States, Error Polish, Responsive Audit

**Files:**
- Modify: `static/main.js` (smart + manual submit handlers)
- Modify: `templates/index.html` (only if the audit in Step 3 finds a leftover inline style in a section this plan touched)
- Test: `tests/test_ui_template.py` + full suite

**Interfaces:**
- Consumes: Task 2 `.calc-btn.loading` spinner
- Produces: consistent async affordances on both calculate buttons

- [ ] **Step 1: Add the loading class to the smart button**

In `static/main.js`, in the smart submit handler, replace:

```js
    smartBtn.disabled = true;
    smartBtn.textContent = 'Calculating…';
```

with:

```js
    smartBtn.disabled = true;
    smartBtn.classList.add('loading');
    smartBtn.textContent = 'Calculating…';
```

and replace:

```js
  function resetSmartBtn() {
    smartBtn.disabled    = false;
    smartBtn.textContent = 'Calculate Borefield Size';
  }
```

with:

```js
  function resetSmartBtn() {
    smartBtn.disabled    = false;
    smartBtn.classList.remove('loading');
    smartBtn.textContent = 'Calculate Borefield Size';
  }
```

- [ ] **Step 2: Add the same affordance to the manual button**

In the manual `calc-btn` click handler, replace:

```js
  document.getElementById('calc-btn').addEventListener('click', async () => {
    clearManualErrors();
    document.getElementById('result-panel').classList.add('hidden');

    const data = collectManualInputs();
```

with:

```js
  document.getElementById('calc-btn').addEventListener('click', async () => {
    clearManualErrors();
    document.getElementById('result-panel').classList.add('hidden');
    const manualBtn = document.getElementById('calc-btn');
    manualBtn.disabled = true;
    manualBtn.classList.add('loading');

    const data = collectManualInputs();
```

and add the reset before EACH of the three exit points of that handler (after the network `catch` block's `showCalcError` line, after the `!response.ok` branch's error handling, and before the final `scrollIntoView` line), using:

```js
    manualBtn.disabled = false;
    manualBtn.classList.remove('loading');
```

Concretely, the end of the handler becomes:

```js
    } catch (err) {
      showCalcError('Network error: ' + err.message);
      manualBtn.disabled = false;
      manualBtn.classList.remove('loading');
      return;
    }

    if (!response.ok) {
      if (result.error === 'field') {
        showFieldError(result.field, result.message);
        if (advancedFields.includes(result.field)) {
          document.querySelector('[data-tab="advanced"]').click();
        } else {
          document.querySelector('[data-tab="basic"]').click();
        }
      } else {
        showCalcError(result.message || 'Calculation failed.');
      }
      manualBtn.disabled = false;
      manualBtn.classList.remove('loading');
      return;
    }

    manualBtn.disabled = false;
    manualBtn.classList.remove('loading');
    document.getElementById('res-L').textContent  = result.L.toLocaleString();
    document.getElementById('res-H').textContent  = result.H.toLocaleString();
    document.getElementById('res-NB').textContent = result.NB.toLocaleString();
    document.getElementById('result-panel').classList.remove('hidden');
    document.getElementById('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
```

- [ ] **Step 3: Responsive + inline-style audit**

Run `grep -n 'style="' templates/index.html`. Expected leftovers: only the small `field-hint` spans in the s1/s2 cards and the `cost-note` strong tag — these are acceptable. If any `style="` remains inside `#smart-result`, `#cost-section`, or `#s6-section`, move it to an existing class from Task 2.

Then run the app and verify at three widths (desktop ~1280px, tablet ~800px, phone ~400px): sidebar collapses to a scrollable top bar, stat grids stack, cost cards stack, chart stays legible, no horizontal scrolling of the page body.

- [ ] **Step 4: Run the full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add static/main.js templates/index.html
git commit -m "feat(ui): loading states, error polish, mobile responsiveness"
```

---

## Self-Review Notes

- Spec coverage: typography (Task 2 — Inter), color system (Task 2 tokens), visual hierarchy (Tasks 3–4 — page sub, stat cards, chips), input/output sections with smooth interactions (Tasks 3, 7 — segmented toggle, focus rings, spinner, bar/width transitions), mobile responsive (Tasks 2, 7), better data visualization (Task 4 two-pass bars, Task 5 cost range bar, Task 6 chart polish), professional feel (emoji removal, tabular numerals, consistent formatting). No invented features — every element restyles an existing one.
- Type consistency: `fmtInt`/`fmtUSD` defined in Task 4 and consumed in Tasks 5–6; `bar-L-heat`/`bar-L-cool` and cost-range ids are declared in the tasks that create them and added to `REQUIRED_IDS` in the same task.
- dev.html safety: no class was removed or renamed; `result-card`, `files-table`, `card`, `stage-pill`, `badge`, `sidebar` all remain styled.
- Dependency: run `2026-07-06-methodology-precision.md` first; fallback instructions included where its markup is referenced (Task 6 Step 1, Global Constraints).

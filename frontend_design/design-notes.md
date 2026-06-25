# GeoSite Advisor — Frontend Design Notes

> **How to use this file:**
> Whenever you have a frontend design idea — a reference site, a color palette, a layout concept, a UI pattern — tell Claude and it will be added here under the relevant section. This document is the living record of all design decisions and inspiration for both the user tool and the developer dashboard.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Server | Flask (Jinja2 templates) | Already in project; minimal overhead |
| Styling | Plain CSS (no framework) | Full control, no build step, lightweight |
| JavaScript | Vanilla JS (no framework) | No build step; adequate for this tool's complexity |
| Icons | None yet | To be added when needed |
| Fonts | System font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI"`) | Fast load, no external dependency |

---

## Two Interfaces

### User Tool (`/` and `/references`)

**Goal:** As simple as a calculator. Building owner enters ZIP + building type → gets a number. No soil data, no pipeline details, no methodology visible.

**Current design language:**
- Color: Dark sidebar (`#1e2a38`) + white content area + green accent (`#2e7d5e`)
- Typography: System sans-serif, 14px body, tight letter-spacing on labels
- Layout: Fixed 220px sidebar + scrollable main content, max-width 760px
- Cards: White panels with 1px border, 8px radius — one card per input group
- Two modes: **Smart Mode** (s1–s4 auto-pipeline, ZIP + building type) and **Manual Mode** (s4 only, all 19 parameters)
- Smart Mode shows a pipeline trace panel after calculation — but only the final k/α/T_g and q_h/q_m/q_y values, not the GEOID or data provenance

**Reference inspirations:**
- **C.Scale** (https://cscale.io): Minimal building carbon tool — good model for "enter a few things, get a result" UX without overwhelming the user
- General principle: ask only what the user actually knows (building type, ZIP) and auto-derive everything else

**Pages:**
- `/` — Main sizing tool (Smart Mode + Manual Mode toggle)
- `/references` — Clean citation list; no methodology detail

---

### Developer Dashboard (`/dev`)

**Goal:** Full pipeline visibility. Every intermediate value, data provenance, coverage status, and pipeline trace visible at a glance.

**Current design language:**
- Dark banner at top: "⚙ Developer Mode — Not visible to users"
- Same sidebar as user tool but with "Developer Dashboard" subtitle
- Pipeline trace output: monospace pre-formatted, shows GEOID, k, α, T_g, loads, result
- Data status chips: colored dots indicating fixture vs. real data
- Quick reference table: what users see vs. what developer keeps

**Key principle:** Developer dashboard shows everything the user tool hides. GEOID, SSURGO coverage flag, raw load values, data source labels, pipeline step outputs.

---

## Design Ideas Log

> Add new ideas here as they come up. Each entry should have a date, the idea, and which interface it applies to.

### 2026-06-25 — Initial setup
- **Two-mode toggle on main page**: Smart Mode (s1–s4, auto) vs Manual Mode (s4 only). The toggle buttons use a bordered card style with a green active state — clean and unambiguous.
- **Stage pills in form**: Small green `s1`, `s2`, `s4` pills before each form section — visual mapping to the pipeline stages without being technical.
- **Pipeline trace panel**: After a Smart Mode calculation, two small cards appear showing the derived site data and loads. Users see just enough to understand what the tool did without exposing the research data.
- **Advanced overrides as `<details>`**: Collapses by default; opens on click. Keeps the form clean for the common case.

---

## References & Inspiration

| Source | URL | What it's good for |
|---|---|---|
| C.Scale | https://cscale.io | Minimal building energy/carbon tool UX — model for "simple input, clean output" |
| ASHRAE design guidelines | Internal | Field label text and unit conventions |
| DOE EnergyPlus documentation | https://energyplus.net | Building type names and descriptions |

---

## Planned Improvements (add ideas here)

- [ ] Map view on the user tool showing the site location (after geocoding succeeds)
- [ ] Subsurface coverage map visible to developer at `/dev` — shows which census tracts have SSURGO data
- [ ] Above-ground climate map at `/dev` — EPW station coverage across the US
- [ ] Better building type descriptions in the dropdown (add floor area, use case)
- [ ] Mobile layout (currently desktop-only)

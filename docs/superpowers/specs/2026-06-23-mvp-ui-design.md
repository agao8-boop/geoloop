# GeoSite Advisor — MVP UI Design Spec
**Date:** 2026-06-23  
**Status:** Approved

---

## Purpose

Provide a browser-based interface so users can enter borefield sizing inputs, run the ASHRAE three-pulse calculation (`s4_sizing`), and read the results — without touching Python directly. The UI must also make the 7-stage pipeline visible and be structured so future stages and richer interactions slot in cleanly.

---

## File Layout

```
geosite_advisor/
├── app.py                    ← Flask app: GET / and POST /calculate
├── templates/
│   └── index.html            ← full page layout, sidebar, tab structure
└── static/
    ├── style.css             ← all styling (no inline styles in HTML)
    └── main.js               ← tab switching, form submit, result rendering
```

No additional dependencies beyond Flask (added to `requirements.txt`).

---

## Layout

Two-column layout. Left sidebar is fixed width (~220 px). Right main area is scrollable.

### Sidebar
- App name "GeoSite Advisor" at top
- Vertical list of all 7 stages:
  - s1 Site, s2 Simulation, s3 Loads, s4 Sizing, s5 Cost, s6 Strategy, s7 Report
- s4 Sizing: active state — highlighted, clickable (links to `#`)
- All others: dimmed, non-clickable, each shows a small "coming soon" badge
- No routing needed; single-page app

### Main Area
- Page heading: "Borefield Sizing — Stage 4"
- Two-tab strip: **Basic** | **Advanced**
- Form below tabs (fields change per active tab)
- Full-width **Calculate** button at bottom of form
- Result panel below button — hidden until calculation succeeds, then displayed in place

---

## Input Form

### Basic Tab — 11 fields in 3 groups

**Ground Loads**  
Sign convention note: *"Negative = heat extraction (heating mode). Positive = heat injection (cooling mode)."*

| Label | Parameter | Unit | No default |
|---|---|---|---|
| Peak hourly load | q_h | W | — |
| Peak monthly load | q_m | W | — |
| Annual average load | q_y | W | — |

**Ground Properties**

| Label | Parameter | Unit | No default |
|---|---|---|---|
| Thermal conductivity | k | W/m·K | — |
| Thermal diffusivity | α | m²/day | — |
| Undisturbed ground temp | T_g | °C | — |

**Borefield**

| Label | Parameter | Unit | No default |
|---|---|---|---|
| Borehole spacing | B | m | — |
| Number of boreholes | NB | — | — |
| Aspect ratio | A | — | — |
| HP inlet temperature | T_in_HP | °C | — |
| Flow rate | mfls | kg/s·kW | — |

### Advanced Tab — 8 fields, pre-filled with standard defaults

| Label | Parameter | Unit | Default |
|---|---|---|---|
| Borehole radius | rbore | m | 0.06 |
| Pipe inner radius | rpin | m | 0.01365 |
| Pipe outer radius | rpext | m | 0.0167 |
| Grout conductivity | kgrout | W/m·K | 1.5 |
| Pipe conductivity | kpipe | W/m·K | 0.42 |
| U-tube spacing | LU | m | 0.0511 |
| Convection coefficient | hconv | W/m²·K | 1000 |
| Fluid heat capacity | Cp | J/kg·K | 4200 |

---

## Backend

### Routes

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `index.html` |
| POST | `/calculate` | Accepts JSON body, returns JSON result |

### POST /calculate

**Request body:** all 19 input fields as a flat JSON object (field names match Python parameter names).

**Success response:**
```json
{
  "L": 1775,
  "H": 55,
  "NB": 32
}
```

**Error response:**
```json
{
  "error": "field",
  "field": "alpha",
  "message": "α must be between 0.025 and 0.2 m²/day"
}
```
or
```json
{
  "error": "calculation",
  "message": "<exception message>"
}
```

### Server-side validation
- All fields present and numeric
- α ∈ [0.025, 0.2] m²/day
- rbore ∈ [0.05, 0.1] m
- NB ≥ 1, A ≥ 1

---

## Frontend Behaviour (main.js)

1. Tab strip toggles `active` class; shows/hides tab content panels
2. On Calculate click: collect all field values from both tabs into one object, POST to `/calculate` as `application/json`
3. On success: un-hide result panel, populate L, H, NB values
4. On field error: show red message next to the offending field
5. On calculation error: show red banner below the Calculate button
6. All errors cleared on next Calculate click

---

## Result Panel

Displayed below the Calculate button after a successful run:

| Label | Value |
|---|---|
| Total borefield length L | `{L} m` |
| Borehole depth H | `{H} m` |
| Number of boreholes | `{NB}` |

---

## Styling (style.css)

- Clean sans-serif font (system font stack)
- Sidebar: dark background, white text, active stage highlighted in a muted accent colour
- Form: light background cards per group, label above input, unit shown as grey suffix
- Tabs: underline-style active indicator, no heavy borders
- Result panel: distinct background (light green tint or similar) to stand out from the form
- Error states: red border on invalid field, red text message below it
- No external CSS frameworks — plain CSS only

---

## Out of Scope (MVP)

- s1–s3 auto-populating inputs from USGS / EnergyPlus
- Saving / loading sessions
- PDF report generation (s7)
- Mobile layout
- Authentication

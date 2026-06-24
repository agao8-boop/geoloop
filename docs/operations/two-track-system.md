# GeoSite Advisor — Two-Track System: Developer vs. User

> **Who reads this:** Developer (researcher) only. This document explains the fundamental separation between what users see and what you control privately.

---

## The Core Idea

Everything in this project belongs to one of two tracks:

| | Developer Track | User Track |
|---|---|---|
| **What it is** | Your research, data, methodology, maps, decisions | The web app users interact with |
| **Who sees it** | You only | Anyone with the URL |
| **Examples** | SSURGO soil data, Côté-Konrad computations, coverage maps, citations, design decisions, slide decks, question log | Flask form, sizing result, references page |
| **Where it lives** | `data/research/`, `docs/`, `weekly_progress/`, `scripts/`, `notebooks/` | `app.py`, `templates/`, `static/`, `data/public/` |
| **On GitHub?** | ❌ Never — in `.gitignore` | ✅ Yes — public repo |
| **On deployed server?** | ❌ Never — excluded from deployment | ✅ Yes — served to users |

---

## The Bridge: `data/public/`

This folder is the only connection between the two tracks. You populate it privately; the app reads from it publicly.

```
data/research/  ──[scripts/export_public.py]──▶  data/public/  ──[Flask]──▶  User browser
  (your moat)          (you run this)             (the bridge)
```

**Files in `data/public/` that will be served:**

| File | Contents | Who populates it |
|---|---|---|
| `thermal_by_tract.csv` | census tract GEOID → k, alpha, T_g (NaN where no SSURGO data) | `scripts/compute_thermal.py` |
| `climate_by_tract.csv` | census tract GEOID → climate zone, MAT, nearest EPW | `scripts/collect_climate.py` |
| `prototype_loads.json` | building_type × climate_zone → q_h, q_m, q_y | `scripts/precompute_loads.py` |
| `references.json` | User-facing citation list (no methodology detail) | Maintained manually |

**Users can query these files through the Flask API. They cannot read the raw files, see directory listings, or access anything outside `data/public/`.**

---

## What Users See vs. What You Keep Private

| Topic | What users see | What you keep private |
|---|---|---|
| Soil thermal conductivity | "k = 1.83 W/m·K for this location" | Côté-Konrad equations, SSURGO data, S_r assumptions |
| Data coverage | Nothing (blank on their end if no data) | Subsurface coverage map showing gaps by census tract |
| References | A clean list: "Philippe et al. (2010)", "USGS SSURGO" | `docs/references/citations.md` with full methodology notes |
| Sizing algorithm | Output: "Total borefield length: 1,843 m" | `geosite/s4_sizing/ashrae_sizing.py` implementation |
| Building simulation | Output: q_h, q_m, q_y values | EnergyPlus IDF files, prototype selection logic, eppy patches |
| Your maps | Never shown | `data/research/maps/subsurface_coverage.geojson` |

---

## Security Notes

- Flask is configured to serve **only** files from `templates/` and `static/`. It does NOT serve `data/research/`, `docs/`, `scripts/`, or any other directory.
- The `data/public/` CSV files are read server-side by Python; they are never sent as raw downloads to the browser (only the computed result is returned as JSON).
- API keys (USGS, geocoding services) are stored in `.env` and loaded via `python-dotenv`. `.env` is in `.gitignore`.
- Never log or expose internal file paths, module names, or stack traces to the user. Flask's debug mode must be `False` in production.

---

## References Page (User-Facing)

Users see a References & Acknowledgements section in the tool. It is populated from `data/public/references.json`. This file lists:
- Paper citations (author, title, journal, year)
- Data sources (USGS, DOE, ASHRAE)
- Software acknowledgements (EnergyPlus, eppy)

It does **not** reveal:
- How those references are used in calculations
- Which equations or parameters come from which source
- Your private methodology or design decisions

---

## Maintenance Checklist

> See `docs/operations/maintenance.md` for when to re-run each pipeline step.

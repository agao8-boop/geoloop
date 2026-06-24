# GeoSite Advisor — Developer Maintenance Checklist

> **Who reads this:** Developer only. Tracks when the data pipeline needs to be re-run and what changed.
> When Claude (or you) makes a change that requires regenerating `data/public/` files, the task will be noted below under "Pending Re-Runs."

---

## Pipeline Steps & When to Re-Run

| Script (to be created) | Re-run when... | Output file |
|---|---|---|
| `scripts/collect_ssurgo.py` | Adding new census tracts, SSURGO API changes, expanding coverage | `data/research/subsurface/ssurgo_by_tract.csv` |
| `scripts/collect_quartz.py` | USGS DS-801 dataset updated, interpolation method changed | `data/research/subsurface/quartz_by_tract.csv` |
| `scripts/compute_thermal.py` | Côté-Konrad parameters updated, S_r method changed, new soil data | `data/research/subsurface/thermal_by_tract.csv` |
| `scripts/collect_climate.py` | EPW file library updated, climate zone mapping changed | `data/research/above_ground/climate_by_tract.csv` |
| `scripts/precompute_loads.py` | EnergyPlus prototype IDFs updated, new building types added, load calc method changed | `data/research/loads/prototype_loads.json` |
| `scripts/export_public.py` | After ANY of the above complete — copies research outputs to `data/public/` | All files under `data/public/` |

**After running `export_public.py`, redeploy the Flask app so users get updated data.**

---

## Pending Re-Runs

> Claude will add entries here when a code or methodology change requires a data pipeline re-run.
> Clear an entry once you have run the pipeline and redeployed.

*(None yet — pipeline scripts not yet created)*

---

## Deployment Checklist (for when the tool goes public)

Before pushing to GitHub and deploying:

- [ ] Verify `.gitignore` excludes `data/research/`, `weekly_progress/`, `docs/`, `scripts/`, `notebooks/`
- [ ] Verify `data/public/` CSV files are committed and up to date
- [ ] Set `FLASK_DEBUG=False` in production `.env`
- [ ] Confirm Flask has no routes that serve files from outside `templates/` and `static/`
- [ ] Confirm no internal paths, module names, or stack traces appear in API responses
- [ ] Set up environment variables on the server for any API keys (never hardcoded)
- [ ] Add `SECRET_KEY` to `.env` for Flask session security
- [ ] Test that `/` and `/calculate` work; test that direct access to `/data/research/` or `/docs/` returns 404

---

## Version Log

| Date | What changed | Pipeline step needed |
|---|---|---|
| 2026-06-24 | Initial project setup. No data collected yet. | All steps — pending |

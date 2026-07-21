# EnergyPlus Workflow for GeoSite Advisor

Concise reference for running EnergyPlus sensitivity studies in this project.
Updated: 2026-07-16.

## Setup

- **EnergyPlus**: `/Applications/EnergyPlus-22-1-0/energyplus`
- **Python**: system python3 (3.12), no venv required
- **IDF source**: `data/doe_prototypes/`
- **EPW source**: `data/epw/`
- **Results**: `data/envelope_study/results/multipliers_{building_type}_{city}.json`

Override EnergyPlus path: `export ENERGYPLUS_DIR=/path/to/EnergyPlus-XX-X-X`

## Available Building Types

Currently have local IDFs for:
- `small_office`  → `ASHRAE901_OfficeSmall_STD2022/`
- `medium_office` → `ASHRAE901_OfficeMedium_STD2022/`
- `large_office`  → `ASHRAE901_OfficeLarge_STD2022/`

City stem in filename matches `{proto_dir}/{proto_dir}_{CityName}.idf`
e.g. `ASHRAE901_OfficeMedium_STD2022/ASHRAE901_OfficeMedium_STD2022_Buffalo.idf`

## Running a Sensitivity Study

### Single city/type
```bash
python3 scripts/envelope_study.py --city denver --building-type medium_office
python3 scripts/envelope_study.py --city buffalo --building-type large_office
python3 scripts/envelope_study.py --dry-run   # verify paths without running EnergyPlus
```

### All building types × cities (overnight batch)
```bash
# 4 parallel workers; skips combos that already have results
nohup python3 scripts/run_sensitivity_all.py --workers 4 \
  > /tmp/sensitivity_overnight.log 2>&1 &
```

Skip logic: if `multipliers_{type}_{city}.json` already exists, that combo is skipped.
Delete the file to force a re-run.

## What each run produces

`data/envelope_study/results/multipliers_{type}_{city}.json`:
```json
{
  "building_type": "medium_office",
  "city": "buffalo",
  "climate_zone": "5A",
  "baseline_label": "wwr_20pct",
  "raw_metrics": {
    "wwr_20pct":        {"peak_heat_kW": 179.4, "peak_cool_kW": 159.1,
                         "annual_heat_MWh": 39.78, "annual_cool_MWh": 212.42},
    "glaz_triple_low_e": { ... },
    ...
  },
  "multipliers": {
    "wwr_20pct": {"peak_heat": 1.0, "peak_cool": 1.0, ...},
    ...
  }
}
```

Baseline = `wwr_20pct` (20% WWR, double low-E, standard infiltration, code-level internal gains).

## Parameter Variants

| Key | Category | What changes |
|---|---|---|
| `wwr_10/20/30/50/70/90pct` | Window-to-Wall Ratio | % of façade that is glazed |
| `glaz_double_low_e` | Glazing (baseline) | U=1.7 W/m²K, SHGC=0.25 |
| `glaz_double_pane` | Glazing | U=3.0, SHGC=0.70 (pre-2000 clear) |
| `glaz_single_pane` | Glazing | U=5.8, SHGC=0.86 (pre-1980) |
| `glaz_triple_low_e` | Glazing | U=0.8, SHGC=0.20 (post-2010) |
| `infil_standard` | Infiltration (baseline) | Code-level air leakage |
| `infil_leaky` | Infiltration | Older/poorly sealed building |
| `infil_tight` | Infiltration | New construction tight envelope |
| `people_low/high` | Occupancy | 0.5× / 2.0× baseline density |
| `lighting_low/high` | Lighting | 0.5× / 1.5× baseline W/m² |
| `equip_low/high` | Equipment | 0.5× / 2.0× baseline W/m² |
| `sched_5day` | Schedule | 5-day work week |
| `sched_extended` | Schedule | Extended operating hours (1.25×) |

## Adding a New Building Type

1. Place IDF files in `data/doe_prototypes/{proto_dir}/{proto_dir}_{City}.idf`
   - One IDF per city; city stems must match `CITY_META` in `envelope_study.py`
2. Add to `PROTO_MAP` in `scripts/envelope_study.py`:
   ```python
   "retail": ("ASHRAE901_Retail_STD2022", "Retail"),
   ```
3. Add to `BUILDING_TYPES` in `scripts/run_sensitivity_all.py`
4. Run: `python3 scripts/envelope_study.py --building-type retail --city denver --dry-run`
   to verify IDF/EPW paths resolve before launching the full batch.

## HVAC Validation (IdealLoads vs prototype)

```bash
nohup python3 scripts/wshp_validation.py > /tmp/wshp_validation.log 2>&1 &
```

Compares IdealLoads baseline (from sensitivity results) against unmodified DOE
prototype (VAV+chiller+boiler). Outputs `data/wshp_validation/{type}_{city}_delta.json`.

Key finding (Jul 16): IdealLoads **overpredicts cooling ~62%** (no economizer modeled)
and **underpredicts heating 46–105%** (no ventilation loss modeled). Next step is to
replace DOE prototype HVAC with WSHP+DOAS for a proper GSHP-equivalent reference.

## Exporting to CSV

```bash
python3 -c "
import csv, json, pathlib
# ... (see scripts/ or re-run the one-liner from the session)
"
# Output: data/envelope_study/results/sensitivity_study_results.csv
# Columns: building_type, city, climate_zone, category, variant,
#          variant_description, peak_heat_kW, peak_cool_kW,
#          annual_heat_MWh, annual_cool_MWh,
#          heat_multiplier_vs_baseline, cool_multiplier_vs_baseline
```

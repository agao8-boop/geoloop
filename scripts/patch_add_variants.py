#!/usr/bin/env python3
"""Patch existing result JSONs with new/synthetic variants and run glaz_double_pane.

Two actions:
1. Inject synthetic 1.0 baseline rows into every existing result JSON:
   - glaz_double_low_e  (double-pane low-E = current baseline, multiplier = 1.0)
   - infil_standard     (standard infiltration = current baseline, multiplier = 1.0)
   These don't need new simulations — they ARE the baseline run.

2. Run glaz_double_pane (U=3.0, SHGC=0.70, plain clear double pane) for all
   (building, city) combos that don't already have it, and append to existing JSON.

Usage:
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/patch_add_variants.py
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/patch_add_variants.py --dry-run
"""

import argparse
import json
import os
import pathlib
import sys
import time

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"
VARIANTS_DIR = ROOT / "data" / "envelope_study" / "variants"

ENERGYPLUS_DIR = pathlib.Path(
    os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-22-1-0")
)

# Plain clear double pane — no low-E coating; typical pre-2000 commercial building
DOUBLE_PANE_U    = 3.0
DOUBLE_PANE_SHGC = 0.70

BASELINE_U    = 2.06120838
BASELINE_SHGC = 0.378
BASELINE_WWR  = 0.20
BASELINE_INFIL = 0.000569572250459736

SYNTHETIC_ROWS = {
    "glaz_double_low_e": {
        "param": "glazing", "level": "double_low_e",
        "u_factor": BASELINE_U, "shgc": BASELINE_SHGC,
        "infil_rate": BASELINE_INFIL, "wwr_scale": BASELINE_WWR,
        "peak_heat": 1.0, "peak_cool": 1.0,
        "annual_heat": 1.0, "annual_cool": 1.0,
        "combined_peak": 1.0,
        "is_baseline_marker": True,
    },
    "infil_standard": {
        "param": "infiltration", "level": "standard",
        "u_factor": BASELINE_U, "shgc": BASELINE_SHGC,
        "infil_rate": BASELINE_INFIL, "wwr_scale": BASELINE_WWR,
        "peak_heat": 1.0, "peak_cool": 1.0,
        "annual_heat": 1.0, "annual_cool": 1.0,
        "combined_peak": 1.0,
        "is_baseline_marker": True,
    },
}


def inject_synthetic(jf: pathlib.Path) -> bool:
    """Add synthetic 1.0 rows to a result JSON if not already present. Returns True if changed."""
    d = json.loads(jf.read_text())
    mults = d.get("multipliers", {})
    changed = False
    for key, row in SYNTHETIC_ROWS.items():
        if key not in mults:
            mults[key] = row
            changed = True
            print(f"    + {key} (synthetic 1.0 baseline marker)")
    if changed:
        d["multipliers"] = mults
        jf.write_text(json.dumps(d, indent=2))
    return changed


def run_double_pane_variant(building: str, city: str, dry_run: bool) -> dict:
    """Run glaz_double_pane for one (building, city) and return metrics dict."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from run_energyplus_loads import (
        load_idf, get_zone_names, get_zone_air_nodes,
        remove_hvac_objects, add_ideal_loads_hvac, add_output_variables,
        set_run_period_annual, patch_v22_compat, patch_simulation_control,
        run_energyplus, parse_ideal_loads_output,
    )
    from envelope_study import (
        CITY_ZONE_MAP, _get_raw_idf, _write_variant_idf, _load_metrics, _multipliers,
        INFIL_BASELINE_RATE, GLAZING_BASELINE_U, GLAZING_BASELINE_SHGC, _BASELINE_WWR,
    )

    idd_path = ENERGYPLUS_DIR / "Energy+.idd"
    epw_name = CITY_ZONE_MAP[city][1]
    epw_path = ROOT / "data" / "epw" / epw_name
    raw_idf  = _get_raw_idf(building, city)

    tag        = f"{building}_{city}"
    label      = "glaz_double_pane"
    variant_dir = VARIANTS_DIR / tag / label
    ep_out_dir  = VARIANTS_DIR / tag / "ep_runs" / label

    if dry_run:
        print(f"  [DRY] {tag} / {label}  U={DOUBLE_PANE_U}  SHGC={DOUBLE_PANE_SHGC}")
        return {}

    mod_idf = _write_variant_idf(
        raw_idf, variant_dir,
        DOUBLE_PANE_U, DOUBLE_PANE_SHGC, INFIL_BASELINE_RATE, _BASELINE_WWR,
    )
    idf = load_idf(mod_idf, idd_path)
    zone_air_nodes = get_zone_air_nodes(idf)
    n_removed      = remove_hvac_objects(idf)
    zone_names     = get_zone_names(idf)
    add_ideal_loads_hvac(idf, zone_names, zone_air_nodes=zone_air_nodes)
    add_output_variables(idf, zone_names)
    set_run_period_annual(idf)
    patch_v22_compat(idf)
    patch_simulation_control(idf)

    sim_idf = variant_dir / "simulation_ready.idf"
    idf.save(str(sim_idf))
    _t = sim_idf.read_text()
    if "EnclosureAveraged" in _t:
        sim_idf.write_text(_t.replace("EnclosureAveraged", "ZoneAveraged"))
    print(f"    Prepared ({n_removed} HVAC objects removed, {len(zone_names)} zones)")

    run_energyplus(sim_idf, epw_path, ep_out_dir, energyplus_dir=ENERGYPLUS_DIR)
    q_heat, q_cool = parse_ideal_loads_output(ep_out_dir, zone_names)
    m = _load_metrics(q_heat, q_cool)
    print(f"    heat={m['peak_heat_W']/1000:.1f}kW  cool={m['peak_cool_W']/1000:.1f}kW"
          f"  ann_h={m['annual_heat_Wh']/1e6:.2f}MWh  ann_c={m['annual_cool_Wh']/1e6:.2f}MWh")

    # Clean up ep_runs to save disk
    import shutil
    if ep_out_dir.exists():
        shutil.rmtree(ep_out_dir)

    return m


def append_double_pane(jf: pathlib.Path, dry_run: bool) -> bool:
    """Run glaz_double_pane and append to result JSON. Returns True if work was done."""
    d = json.loads(jf.read_text())
    if "glaz_double_pane" in d.get("multipliers", {}):
        print(f"    already has glaz_double_pane — skip")
        return False

    building = d["building_type"]
    city     = d["city"]
    print(f"\n  [{building}/{city}] running glaz_double_pane ...")

    try:
        m = run_double_pane_variant(building, city, dry_run)
    except (Exception, SystemExit) as exc:
        print(f"  CRASH: {exc}")
        return False

    if dry_run:
        return False

    # Compute multipliers relative to baseline raw metrics
    baseline_lbl = d.get("baseline_label", "wwr_20pct")
    raw = d.get("raw_metrics", {}).get(baseline_lbl, {})
    baseline_m = {
        "peak_heat_W":    raw.get("peak_heat_kW",    0) * 1000,
        "peak_cool_W":    raw.get("peak_cool_kW",    0) * 1000,
        "annual_heat_Wh": raw.get("annual_heat_MWh", 0) * 1e6,
        "annual_cool_Wh": raw.get("annual_cool_MWh", 0) * 1e6,
    }

    from envelope_study import _multipliers
    mult = _multipliers(m, baseline_m)

    d["multipliers"]["glaz_double_pane"] = {
        "param": "glazing", "level": "double_pane",
        "u_factor": DOUBLE_PANE_U, "shgc": DOUBLE_PANE_SHGC,
        "infil_rate": BASELINE_INFIL, "wwr_scale": BASELINE_WWR,
        "peak_heat":    round(mult["peak_heat"],    4),
        "peak_cool":    round(mult["peak_cool"],    4),
        "annual_heat":  round(mult["annual_heat"],  4),
        "annual_cool":  round(mult["annual_cool"],  4),
        "combined_peak":round(mult["combined_peak"],4),
    }
    # Also add to raw_metrics for completeness
    d["raw_metrics"]["glaz_double_pane"] = {
        "peak_heat_kW":    round(m["peak_heat_W"]   / 1000, 2),
        "peak_cool_kW":    round(m["peak_cool_W"]   / 1000, 2),
        "annual_heat_MWh": round(m["annual_heat_Wh"] / 1e6, 3),
        "annual_cool_MWh": round(m["annual_cool_Wh"] / 1e6, 3),
    }
    jf.write_text(json.dumps(d, indent=2))
    print(f"    Appended glaz_double_pane → {jf.name}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    json_files = sorted(f for f in RESULTS_DIR.glob("multipliers_*_*.json")
                        if "_partial" not in f.name)
    print(f"Found {len(json_files)} result files.\n")

    # Phase 1: inject synthetic baseline rows (fast, no simulation)
    print("=== Phase 1: injecting synthetic baseline markers ===")
    for jf in json_files:
        print(f"  {jf.name}")
        inject_synthetic(jf)

    # Phase 2: run glaz_double_pane for every file that needs it
    print(f"\n=== Phase 2: running glaz_double_pane ({len(json_files)} combos) ===")
    t0 = time.time()
    done = 0
    for i, jf in enumerate(json_files):
        elapsed = time.time() - t0
        if done > 0:
            eta = elapsed / done * (len(json_files) - done)
            print(f"[{i+1}/{len(json_files)}]  ETA ≈ {eta/3600:.1f}h")
        else:
            print(f"[{i+1}/{len(json_files)}]")
        worked = append_double_pane(jf, args.dry_run)
        if worked:
            done += 1

    print(f"\nDone. {done} new glaz_double_pane simulations run.")


if __name__ == "__main__":
    main()

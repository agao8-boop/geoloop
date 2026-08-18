#!/usr/bin/env python3
"""
scripts/run_energyplus_wshp_all.py
───────────────────────────────────────────────────────────────────────────────
Run WSHP+DOAS EnergyPlus simulations for ALL DOE prototype building × city
combinations and generate prototype_loads_wshp.json.

This REPLACES the IdealLoads approach entirely. No COP correction is applied.
The ground loop source-side heat transfer rate is extracted directly from the
WSHP simulation — EnergyPlus computes the COP internally.

Pipeline:
  1. patch_idf_wshp_doas.py  →  data/wshp_idfs/{building}_{city}_wshp.idf
  2. This script:
       - Runs EnergyPlus -x on each patched IDF
       - Extracts 8760h "Water To Air Heat Pump Source Side Heat Transfer Rate"
         summed across all zones → building-level ground load profile
       - Computes q_h (peak 6h), q_m (peak month one-sided), q_y (annual net)
       - Writes data/public/prototype_loads_wshp.json

Output JSON schema (same as prototype_loads.json for drop-in replacement):
  {
    "{building_type}": {
      "_area_m2": float,
      "{climate_zone}": {
        "q_h": float,   # peak 6h ground load [W], + = injection (cooling), - = extraction (heating)
        "q_m": float,   # peak month one-sided ground load [W]
        "q_y": float,   # annual net ground load [W]
        "q_h_Wpm2": float,
        "q_m_Wpm2": float,
        "q_y_Wpm2": float,
        "peak_heat_ground_kW": float,
        "peak_cool_ground_kW": float,
        "ann_heat_ground_kWh": float,
        "ann_cool_ground_kWh": float,
        "city": str,
        "source": "WSHP+DOAS EnergyPlus"
      }
    }
  }

Usage:
    python scripts/run_energyplus_wshp_all.py           # run all
    python scripts/run_energyplus_wshp_all.py --resume  # skip already-done
    python scripts/run_energyplus_wshp_all.py --dry-run

Scope: 8 non-DHW building types × 16 climate cities = 128 runs
Excluded: hospital, hotel, restaurant, apartment (domestic hot water distorts ground load)
Estimated time: ~5-15 min per simulation × 128 runs ≈ 10-32 hours
Run overnight with --resume to recover from interruptions.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

import numpy as np

ROOT         = pathlib.Path(__file__).parent.parent
PROTO_DIR    = ROOT / "data" / "doe_prototypes"
WSHP_IDF_DIR = ROOT / "data" / "wshp_idfs"
EPW_DIR      = ROOT / "data" / "epw"
WORK_DIR     = ROOT / "data" / "wshp_runs"
OUT_JSON     = ROOT / "data" / "public" / "prototype_loads_wshp.json"
LOG_FILE     = ROOT / "data" / "wshp_runs" / "run_log.txt"

ENERGYPLUS = pathlib.Path(
    os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-22-1-0")
) / "energyplus"

# ── City → EPW file mapping ────────────────────────────────────────────────
CITY_EPW = {
    "Albuquerque":      "USA_NM_Albuquerque.Intl.Sunport.723650_TMY3.epw",
    "Atlanta":          "USA_GA_Atlanta-Hartsfield.Jackson.Intl.AP.722190_TMY3.epw",
    "Buffalo":          "USA_NY_Buffalo.Niagara.Intl.AP.725280_TMY3.epw",
    "Denver":           "USA_CO_Denver-Aurora-Buckley.AFB.724695_TMY3.epw",
    "ElPaso":           "USA_TX_El.Paso.Intl.AP.722700_TMY3.epw",
    "Fairbanks":        "USA_AK_Fairbanks.Intl.AP.702610_TMY3.epw",
    "GreatFalls":       "USA_MT_Great.Falls.Intl.AP.727750_TMY3.epw",
    "InternationalFalls":"USA_MN_International.Falls.Intl.AP.727470_TMY3.epw",
    "Miami":            "USA_FL_Miami.Intl.AP.722020_TMY3.epw",
    "NewYork":          "USA_NY_New.York-John.F.Kennedy.Intl.AP.744860_TMY3.epw",
    "PortAngeles":      "USA_WA_Port.Angeles-William.R.Fairchild.Intl.AP.727885_TMY3.epw",
    "Rochester":        "USA_MN_Rochester.Intl.AP.726440_TMY3.epw",
    "SanDiego":         "USA_CA_San.Deigo-Brown.Field.Muni.AP.722904_TMY3.epw",
    "Seattle":          "USA_WA_Seattle-Tacoma.Intl.AP.727930_TMY3.epw",
    "Tampa":            "USA_FL_Tampa-MacDill.AFB.747880_TMY3.epw",
    "Tucson":           "USA_AZ_Tucson-Davis-Monthan.AFB.722745_TMY3.epw",
}

# ── City → ASHRAE climate zone ─────────────────────────────────────────────
CITY_ZONE = {
    "Miami":             "1A",
    "Tampa":             "2A",
    "Tucson":            "2B",
    "Atlanta":           "3A",
    "ElPaso":            "3B",
    "SanDiego":          "3C",
    "NewYork":           "4A",
    "Albuquerque":       "4B",
    "PortAngeles":       "4C",
    "Buffalo":           "5A",
    "Denver":            "5B",
    "Seattle":           "5C",
    "Rochester":         "6A",
    "GreatFalls":        "6B",
    "InternationalFalls":"7",
    "Fairbanks":         "8",
}

# ── DOE prototype stem → GeoSite building type key ────────────────────────
# INCLUDED: office, school, retail, warehouse — no domestic hot water
# EXCLUDED: hospital, hotel, restaurant, apartment — DHW loads distort ground sizing
PROTO_STEM_MAP = {
    "ASHRAE901_OfficeLarge_STD2022":       ("large_office",       46320.0),
    "ASHRAE901_OfficeMedium_STD2022":      ("medium_office",       4982.0),
    "ASHRAE901_OfficeSmall_STD2022":       ("small_office",         511.0),
    "ASHRAE901_SchoolPrimary_STD2022":     ("primary_school",       6871.0),
    "ASHRAE901_SchoolSecondary_STD2022":   ("secondary_school",    19592.0),
    "ASHRAE901_RetailStandalone_STD2022":  ("standalone_retail",   2294.0),
    "ASHRAE901_RetailStripmall_STD2022":   ("retail_stripmall",    2090.0),
    "ASHRAE901_Warehouse_STD2022":         ("warehouse",           4835.0),
}


def _find_all_cases() -> list[dict]:
    """Enumerate all valid (building, city) cases with matching IDF + EPW."""
    cases = []
    for stem, (btype, area_m2) in PROTO_STEM_MAP.items():
        proto_dir = PROTO_DIR / stem
        if not proto_dir.exists():
            continue
        for city, epw_name in CITY_EPW.items():
            idf_src = proto_dir / f"{stem}_{city}.idf"
            epw_path = EPW_DIR / epw_name
            if not idf_src.exists() or not epw_path.exists():
                continue
            zone = CITY_ZONE.get(city, "unknown")
            cases.append({
                "stem": stem,
                "btype": btype,
                "area_m2": area_m2,
                "city": city,
                "zone": zone,
                "idf_src": idf_src,
                "epw_path": epw_path,
            })
    return cases


def _patch_if_needed(case: dict) -> pathlib.Path:
    """Patch IDF to WSHP+DOAS if not already done."""
    out_idf = WSHP_IDF_DIR / f"{case['btype']}_{case['city']}_wshp.idf"
    if not out_idf.exists():
        # Import and call patcher directly
        sys.path.insert(0, str(ROOT / "scripts"))
        import patch_idf_wshp_doas as patcher
        patcher.patch_idf_raw(case["idf_src"], out_idf)
    return out_idf


def _run_ep(idf_path: pathlib.Path, epw_path: pathlib.Path,
            run_dir: pathlib.Path, dry_run: bool) -> bool:
    run_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"      [DRY] energyplus -x {idf_path.name}")
        return True
    cmd = [str(ENERGYPLUS), "-x", "-w", str(epw_path), "-d", str(run_dir), str(idf_path)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    elapsed = time.time() - t0
    if r.returncode != 0:
        print(f"      [FAIL] rc={r.returncode}  {(r.stderr or r.stdout)[-200:]}")
        return False
    print(f"      Done {elapsed/60:.1f} min")
    return True


def _extract_ground_loads(run_dir: pathlib.Path) -> np.ndarray | None:
    """Extract 8760h ground load [W] from eplusout.eso. Returns None on failure.

    Parses the ESO binary dictionary directly — no ReadVarsESO dependency.

    Sign convention: positive = heat injected into ground (cooling dominant)
                     negative = heat extracted from ground (heating dominant)

    EP reports both source-side transfers as positive magnitudes:
        g[h] = sum(cooling_coil_source) - sum(heating_coil_source)
    """
    eso_path = run_dir / "eplusout.eso"
    if not eso_path.exists():
        return None

    clg_codes: set[int] = set()
    htg_codes: set[int] = set()
    in_dict = True
    hourly_data: dict[int, list[float]] = {}  # code → per-hour sums

    # Single-pass parse: dict section then data section
    with open(eso_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if in_dict:
                if line.startswith("End of Data Dictionary"):
                    in_dict = False
                    continue
                # Dictionary entry: {code},{n_vals},{key},{varname}[unit] !Freq
                parts = line.split(",", 3)
                if len(parts) < 3:
                    continue
                try:
                    code = int(parts[0].strip())
                except ValueError:
                    continue
                # ESO format: {code},{n_vals},{key_name},{var_name}[unit] !Freq
                varname = parts[3] if len(parts) > 3 else ""
                if "Cooling Coil Source Side Heat Transfer Rate" in varname:
                    clg_codes.add(code)
                    hourly_data.setdefault(code, [])
                elif "Heating Coil Source Side Heat Transfer Rate" in varname:
                    htg_codes.add(code)
                    hourly_data.setdefault(code, [])
            else:
                # Data row: {code},{val1},...
                parts = line.split(",")
                if not parts:
                    continue
                try:
                    code = int(parts[0].strip())
                except ValueError:
                    continue
                if code in hourly_data and len(parts) > 1:
                    try:
                        hourly_data[code].append(float(parts[1].strip()))
                    except ValueError:
                        pass

    if not clg_codes and not htg_codes:
        return None

    # Build 8760-element array: net ground load per hour
    n_hours = max(
        (len(v) for v in hourly_data.values() if v), default=0
    )
    if n_hours < 8760:
        return None

    result = np.zeros(n_hours, dtype=float)
    for code in clg_codes:
        vals = hourly_data.get(code, [])
        if vals:
            result[:len(vals)] += np.array(vals[:n_hours])
    for code in htg_codes:
        vals = hourly_data.get(code, [])
        if vals:
            result[:len(vals)] -= np.array(vals[:n_hours])

    return result[:8760]


def _compute_pulses(g: np.ndarray, area_m2: float) -> dict:
    """Compute q_h, q_m, q_y from 8760h ground load array [W].

    Follows Philippe et al. (2010) definitions:
      q_y  = annual mean of net ground load (positive = cooling dominant)
      q_m  = full-month net average of worst month (NOT one-sided; heating
             and cooling hours cancel within a month, per paper definition)
      q_h  = peak 6-hour rolling average (6h pulse duration per ASHRAE method)
    """
    from numpy.lib.stride_tricks import sliding_window_view

    q_y = float(g.mean())
    cool_dom = q_y >= 0

    # q_h: peak 6-hour rolling average on dominant side
    # ASHRAE method applies q_h as a 6-hour pulse; 6h avg avoids 1-hour anomalies.
    r6 = sliding_window_view(g, 6).mean(axis=1)
    q_h = float(r6.max()) if cool_dom else float(r6.min())

    # q_m: full-month NET average of worst month (Philippe 2010 definition).
    # Heating and cooling hours within a month cancel; ground sees only net flux.
    # (Prior implementation used dominant-mode-only, which overestimates q_m in
    #  shoulder months and diverges from s3_loads/compute.py — Task 12 fix.)
    month_h = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    monthly, start = [], 0
    for h in month_h:
        monthly.append(float(g[start:start + h].mean()))
        start += h
    q_m = max(monthly, key=abs)  # worst month by abs(net average)

    # Peak loads
    peak_cool_W = float(g.clip(min=0).max())
    peak_heat_W = float((-g).clip(min=0).max())
    ann_cool_Wh = float(g.clip(min=0).sum())
    ann_heat_Wh = float((-g).clip(min=0).sum())

    return {
        "q_h":               round(q_h, 1),
        "q_m":               round(q_m, 1),
        "q_y":               round(q_y, 1),
        "q_h_Wpm2":          round(q_h / area_m2, 4),
        "q_m_Wpm2":          round(q_m / area_m2, 4),
        "q_y_Wpm2":          round(q_y / area_m2, 4),
        "peak_cool_ground_kW": round(peak_cool_W / 1000, 2),
        "peak_heat_ground_kW": round(peak_heat_W / 1000, 2),
        "ann_cool_ground_kWh": round(ann_cool_Wh / 3600 / 1000, 1),
        "ann_heat_ground_kWh": round(ann_heat_Wh / 3600 / 1000, 1),
        "source": "WSHP+DOAS EnergyPlus",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume",  action="store_true",
                    help="Skip cases already present in output JSON")
    args = ap.parse_args()

    if not args.dry_run and not ENERGYPLUS.exists():
        sys.exit(f"EnergyPlus not found: {ENERGYPLUS}\n"
                 f"Set ENERGYPLUS_DIR env var.")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    WSHP_IDF_DIR.mkdir(parents=True, exist_ok=True)

    cases = _find_all_cases()
    print(f"Found {len(cases)} valid building × city combinations")

    # Load existing results for resume
    existing = {}
    if args.resume and OUT_JSON.exists():
        with open(OUT_JSON) as f:
            existing = json.load(f)
        done = sum(
            1 for bt in existing.values()
            for k, v in bt.items()
            if not k.startswith("_") and isinstance(v, dict)
        )
        print(f"Resume: {done} already done, skipping those")

    results = existing
    n_done = 0
    n_fail = 0

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a")

    for i, case in enumerate(cases):
        btype = case["btype"]
        city  = case["city"]
        zone  = case["zone"]
        tag   = f"{btype}/{city}({zone})"

        # Resume check
        if args.resume and results.get(btype, {}).get(zone):
            print(f"  [{i+1:3d}/{len(cases)}] SKIP {tag}")
            continue

        print(f"\n  [{i+1:3d}/{len(cases)}] {tag}")

        # Patch IDF
        try:
            wshp_idf = _patch_if_needed(case)
        except Exception as e:
            print(f"      [FAIL] patch: {e}")
            log.write(f"FAIL patch {tag}: {e}\n")
            n_fail += 1
            continue

        # Run EnergyPlus
        run_dir = WORK_DIR / f"{btype}_{city}"
        ok = _run_ep(wshp_idf, case["epw_path"], run_dir, args.dry_run)
        if not ok:
            log.write(f"FAIL ep {tag}\n")
            n_fail += 1
            continue

        if args.dry_run:
            n_done += 1
            continue

        # Extract ground loads
        g = _extract_ground_loads(run_dir)
        if g is None:
            print(f"      [FAIL] no source-side output in CSV")
            log.write(f"FAIL extract {tag}\n")
            n_fail += 1
            continue

        pulses = _compute_pulses(g, case["area_m2"])
        pulses["city"] = city

        # Store in results
        if btype not in results:
            results[btype] = {}
        results[btype]["_area_m2"] = case["area_m2"]
        results[btype][zone] = pulses

        # Save incrementally
        with open(OUT_JSON, "w") as f:
            json.dump(results, f, indent=2)

        n_done += 1
        log.write(
            f"OK {tag}  q_h={pulses['q_h_Wpm2']:.2f}  "
            f"q_m={pulses['q_m_Wpm2']:.2f}  q_y={pulses['q_y_Wpm2']:.2f} W/m²\n"
        )
        log.flush()

    log.close()

    print(f"\n{'='*60}")
    print(f"Complete: {n_done} succeeded, {n_fail} failed")
    print(f"Output: {OUT_JSON}")
    print(f"Log:    {LOG_FILE}")

    if not args.dry_run and OUT_JSON.exists():
        with open(OUT_JSON) as f:
            final = json.load(f)
        total_zones = sum(
            1 for bt in final.values()
            for k in bt if not k.startswith("_")
        )
        print(f"Total entries in JSON: {total_zones}")


if __name__ == "__main__":
    main()

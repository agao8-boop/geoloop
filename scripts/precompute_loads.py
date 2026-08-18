#!/usr/bin/env python3
"""
scripts/precompute_loads.py

Batch-simulate all building-type × climate-zone combinations and write
the results to data/public/prototype_loads.json.

This is the offline pipeline that populates the pre-computed load library
used by geosite/s2_simulation/lookup.py at serve time.  Run it once after
installing EnergyPlus and downloading the required IDF and EPW files.

HOW IT WORKS
------------
For each (building_type, climate_zone) pair:
  1. Load the DOE prototype IDF for that building type and climate zone.
  2. Replace its HVAC with ZoneHVAC:IdealLoadsAirSystem (via run_energyplus_loads.py).
  3. Run a full-year EnergyPlus simulation with the matching TMYx EPW.
  4. Aggregate the 8760h output into three-pulse ground loads (q_h, q_m, q_y)
     via geosite/s3_loads/compute.py.
  5. Store normalized values (W/m²) alongside absolute values (W) so the
     lookup can scale to arbitrary user floor areas at runtime.
  6. Write results into data/public/prototype_loads.json, preserving any
     existing entries (resume-safe: skips already-computed pairs).

FILE LAYOUT (set up before running)
-------------------------------------
data/
  energyplus_cache/
    idf/
      small_office_1A.idf       ← DOE prototype IDF, Chicago=5A, Houston=2A, etc.
      small_office_2A.idf          Filename convention: {type}_{zone}.idf
      ...                          Download from: energycodes.gov/prototype-building-models
      medium_office_5A.idf         Select: ASHRAE 90.1-2019 → building type → city
      large_office_5A.idf
    epw/
      1A.epw                    ← TMYx EPW, one per ASHRAE climate zone
      2A.epw                       Filename convention: {zone}.epw
      ...                          Download from: climate.onebuilding.org
      5A.epw                       Select: TMYx 2007-2021 for representative city
      8.epw

ASHRAE CLIMATE ZONES — Representative Cities (ASHRAE 90.1-2019 Table B-4)
---------------------------------------------------------------------------
  1A → Miami, FL          (hot-humid)
  2A → Houston, TX        (hot-humid)
  2B → Phoenix, AZ        (hot-dry)
  3A → Memphis, TN        (mixed-humid)
  3B → El Paso, TX        (mixed-dry)
  3C → San Francisco, CA  (marine)
  4A → Baltimore, MD      (mixed-humid)
  4B → Albuquerque, NM    (mixed-dry)
  4C → Seattle, WA        (marine)
  5A → Chicago, IL        (cold-humid)
  5B → Boulder, CO        (cold-dry)
  6A → Burlington, VT     (cold-humid)
  6B → Helena, MT         (cold-dry)
  7  → Duluth, MN         (very cold)
  8  → Fairbanks, AK      (subarctic)

DOE PROTOTYPE FLOOR AREAS (reference sizes)
-------------------------------------------
  small_office  :    511 m² /   5,502 sq ft
  medium_office :  4,982 m² /  53,628 sq ft
  large_office  : 46,320 m² / 498,588 sq ft
  Source: Deru et al. (2011) NREL/TP-5500-46861.

RUN-TIME SCALING
----------------
prototype_loads.json stores both absolute values (W, for the prototype area)
and normalized values (W/m²).  The lookup module scales by the user's
requested floor area:
    q_h_user = q_h_norm_Wpm2 × user_area_m2

USAGE
-----
  # Phase 1: simulate office types for the three core climate zones
  python scripts/precompute_loads.py --types small_office medium_office large_office \\
                                     --zones 5A 3B 2A

  # Phase 2: full sweep (15 zones × 3 types = 45 simulations, ~2–3 h)
  python scripts/precompute_loads.py --types small_office medium_office large_office

  # Force re-run even if already computed
  python scripts/precompute_loads.py --zones 5A --force

REFERENCES
----------
  Deru, M. et al. (2011). U.S. DOE commercial reference building models.
    NREL/TP-5500-46861. doi:10.2172/1000545
  DOE (2023). Commercial Prototype Building Models. energycodes.gov.
  EnergyPlus (2024). Input-Output Reference, v24.2. energyplus.net.
  Philippe, M. et al. (2010). ASHRAE Journal 52(7): 20–28.
"""

import argparse
import json
import os
import pathlib
import sys
import time

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

ROOT     = pathlib.Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "data" / "energyplus_cache" / "work"
OUT_JSON = ROOT / "data" / "public" / "prototype_loads.json"

# Import shared path resolution (data/doe_prototypes/ + data/epw/)
import energyplus_paths as _ep
from energyplus_paths import (
    CITY_TO_ZONE, ZONE_TO_CITIES, DOE_LABELS, ENERGYPLUS_DIR,
    find_idf, find_epw, inventory, print_inventory,
)

# ─────────────────────────────────────────────────────────────────────────────
# Climate zone metadata  (coordinates for JSON output)
# ─────────────────────────────────────────────────────────────────────────────
# Representative cities from the ASHRAE 90.1-2022 DOE STD2022 prototype set.
# Zone 5A is absent — no Chicago IDF in this download (add separately if needed).

# Official DOE ASHRAE 90.1-2022 representative cities for all 16 US climate zones.
# Source: DOE Commercial Prototype Building Models table, energycodes.gov
CLIMATE_ZONES: dict[str, dict] = {
    "1A": {"city": "Miami",             "state": "FL", "lat": 25.79,  "lon": -80.32,  "desc": "Very Hot Humid"},
    "2A": {"city": "Tampa",             "state": "FL", "lat": 27.97,  "lon": -82.53,  "desc": "Hot Humid"},
    "2B": {"city": "Tucson",            "state": "AZ", "lat": 32.23,  "lon": -110.96, "desc": "Hot Dry"},
    "3A": {"city": "Atlanta",           "state": "GA", "lat": 33.64,  "lon": -84.43,  "desc": "Warm Humid"},
    "3B": {"city": "El Paso",           "state": "TX", "lat": 31.81,  "lon": -106.38, "desc": "Warm Dry"},
    "3C": {"city": "San Diego",         "state": "CA", "lat": 32.73,  "lon": -117.19, "desc": "Warm Marine"},
    "4A": {"city": "New York",          "state": "NY", "lat": 40.64,  "lon": -73.78,  "desc": "Mixed Humid"},
    "4B": {"city": "Albuquerque",       "state": "NM", "lat": 35.04,  "lon": -106.62, "desc": "Mixed Dry"},
    "4C": {"city": "Seattle",           "state": "WA", "lat": 47.45,  "lon": -122.31, "desc": "Mixed Marine"},
    "5A": {"city": "Buffalo",           "state": "NY", "lat": 42.94,  "lon": -78.73,  "desc": "Cool Humid"},
    "5B": {"city": "Denver",            "state": "CO", "lat": 39.86,  "lon": -104.67, "desc": "Cool Dry"},
    "5C": {"city": "Port Angeles",      "state": "WA", "lat": 48.12,  "lon": -123.50, "desc": "Cool Marine"},
    "6A": {"city": "Rochester",         "state": "MN", "lat": 43.91,  "lon": -92.50,  "desc": "Cold Humid"},
    "6B": {"city": "Great Falls",       "state": "MT", "lat": 47.48,  "lon": -111.37, "desc": "Cold Dry"},
    "7":  {"city": "International Falls","state": "MN", "lat": 48.57,  "lon": -93.40,  "desc": "Very Cold"},
    "8":  {"city": "Fairbanks",         "state": "AK", "lat": 64.82,  "lon": -147.86, "desc": "Subarctic/Arctic"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Building type registry
# ─────────────────────────────────────────────────────────────────────────────

# Maps prototype_loads.json keys to reference floor areas.
# Source: Deru et al. (2011) NREL/TP-5500-46861, Table 3.
BUILDING_TYPES: dict[str, dict] = {
    "small_office":          {"area_m2": 511.2},
    "medium_office":         {"area_m2": 4982.2},
    "large_office":          {"area_m2": 46320.0},
    "standalone_retail":     {"area_m2": 2294.0},
    "primary_school":        {"area_m2": 6871.0},
    "secondary_school":      {"area_m2": 19592.0},
    "hospital":              {"area_m2": 22422.0},
    "outpatient_healthcare": {"area_m2": 3804.0},
    "small_hotel":           {"area_m2": 4014.0},
    "large_hotel":           {"area_m2": 11345.0},
    "warehouse":             {"area_m2": 4835.0},
    "midrise_apartment":     {"area_m2": 3135.0},
    "highrise_apartment":    {"area_m2": 16722.0},  # 180,000 ft² — NREL/TP-5500-46861
    "retail_stripmall":      {"area_m2": 2090.0},   # 22,500 ft²
    "restaurant_fastfood":   {"area_m2": 232.3},    # 2,500 ft² — confirmed from IDF volumes
    "restaurant_sitdown":    {"area_m2": 511.1},    # 5,500 ft² — confirmed from IDF volumes
}

# ─────────────────────────────────────────────────────────────────────────────
# Setup check
# ─────────────────────────────────────────────────────────────────────────────

def check_setup() -> bool:
    """Verify EnergyPlus 26-1-0 is installed."""
    idd = ENERGYPLUS_DIR / "Energy+.idd"
    if not ENERGYPLUS_DIR.exists() or not idd.exists():
        print(
            f"\nERROR: EnergyPlus not found at {ENERGYPLUS_DIR}\n"
            "Install EnergyPlus from: https://energyplus.net/downloads\n"
        )
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Simulation runner (calls run_energyplus_loads.py internals directly)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_one(
    building_type: str,
    zone: str,
    i_path: pathlib.Path,
    e_path: pathlib.Path,
    work_root: pathlib.Path,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Run one EnergyPlus simulation; return (q_heat_8760, q_cool_8760) or None on error.

    Imports prepare_idf, run_energyplus, and parse_ideal_loads_output directly
    from run_energyplus_loads.py to avoid subprocess overhead.
    """
    # Import helpers from run_energyplus_loads (same package, no subprocess)
    script_dir = pathlib.Path(__file__).parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    try:
        import run_energyplus_loads as ep
    except ImportError as exc:
        print(f"  ERROR importing run_energyplus_loads: {exc}")
        return None

    bt_info = BUILDING_TYPES[building_type]
    area_sqft = bt_info["area_m2"] / 0.092903   # prototype reference area exactly

    work_dir = work_root / f"{building_type}_{zone}"
    idd_path = ENERGYPLUS_DIR / "Energy+.idd"

    try:
        ready_idf, zone_names = ep.prepare_idf(
            src_idf_path=i_path,
            target_area_sqft=area_sqft,
            building_type=_to_doe_type(building_type),
            work_dir=work_dir,
            idd_path=idd_path,
        )
    except Exception as exc:
        print(f"  ERROR in prepare_idf: {exc}")
        return None

    ep_out_dir = work_dir / "ep_output"
    try:
        ep.run_energyplus(
            idf_path=ready_idf,
            epw_path=e_path,
            output_dir=ep_out_dir,
            energyplus_dir=ENERGYPLUS_DIR,
        )
    except SystemExit as exc:
        print(f"  ERROR running EnergyPlus: {exc}")
        return None

    try:
        q_heat, q_cool = ep.parse_ideal_loads_output(ep_out_dir, zone_names)
    except SystemExit as exc:
        print(f"  ERROR parsing output: {exc}")
        return None

    return q_heat, q_cool


def _to_doe_type(json_key: str) -> str:
    """Map prototype_loads.json key to DOE prototype building type string.

    run_energyplus_loads.py DOE_PROTOTYPES uses CamelCase keys.
    """
    mapping = {
        "small_office":   "SmallOffice",
        "medium_office":  "MediumOffice",
        "large_office":   "LargeOffice",
    }
    return mapping.get(json_key, json_key)


# ─────────────────────────────────────────────────────────────────────────────
# JSON update
# ─────────────────────────────────────────────────────────────────────────────

def load_existing_json() -> dict:
    """Load the current prototype_loads.json (creates a stub if not found)."""
    if OUT_JSON.exists():
        with open(OUT_JSON) as f:
            return json.load(f)
    return {
        "_note": "Pre-computed loads from EnergyPlus + ZoneHVAC:IdealLoadsAirSystem.",
        "_generated_by": "scripts/precompute_loads.py",
        "_units": "W (absolute) and W/m2 (normalized to prototype floor area)",
    }


def already_computed(data: dict, building_type: str, zone: str) -> bool:
    """Return True if real (non-fixture) values are already in the JSON."""
    entry = data.get(building_type, {}).get(zone, {})
    return bool(entry) and entry.get("computed", False)


def write_result(
    data: dict,
    building_type: str,
    zone: str,
    q_heat: np.ndarray,
    q_cool: np.ndarray,
) -> None:
    """Compute three-pulse loads and write them into the data dict."""
    # Import compute_pulses from geosite package
    root_src = ROOT
    if str(root_src) not in sys.path:
        sys.path.insert(0, str(root_src))
    from geosite.s3_loads.compute import compute_pulses

    pulses = compute_pulses(q_heat, q_cool)

    area_m2 = BUILDING_TYPES[building_type]["area_m2"]

    if building_type not in data:
        data[building_type] = {"_area_m2": area_m2}

    data[building_type][zone] = {
        # Absolute values at prototype reference area
        "q_h": round(pulses.q_h, 0),
        "q_m": round(pulses.q_m, 0),
        "q_y": round(pulses.q_y, 0),
        # Normalized per unit floor area (W/m²) for runtime scaling
        "q_h_Wpm2": round(pulses.q_h / area_m2, 2),
        "q_m_Wpm2": round(pulses.q_m / area_m2, 2),
        "q_y_Wpm2": round(pulses.q_y / area_m2, 4),
        # Diagnostic
        "peak_heat_kW": round(float(q_heat.max()) / 1000, 1),
        "peak_cool_kW": round(float(q_cool.max()) / 1000, 1),
        "ann_heat_kWh": round(float(q_heat.sum()) / 1000, 0),
        "ann_cool_kWh": round(float(q_cool.sum()) / 1000, 0),
        "computed": True,
        "epw_source": "TMYx 2007-2021 (climate.onebuilding.org)",
        "idf_source": "DOE Prototype Buildings, ASHRAE 90.1-2019 (energycodes.gov)",
    }

    # Write immediately so partial results are not lost on interruption
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch EnergyPlus precompute for prototype_loads.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--types", nargs="+",
        default=["small_office", "medium_office", "large_office"],
        choices=list(BUILDING_TYPES.keys()),
        help="Building types to simulate (default: three office types)",
    )
    p.add_argument(
        "--zones", nargs="+",
        default=list(CLIMATE_ZONES.keys()),
        choices=list(CLIMATE_ZONES.keys()),
        help="ASHRAE climate zones to simulate (default: all 15)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Re-run even if results already exist in prototype_loads.json",
    )
    p.add_argument(
        "--energyplus-dir", type=pathlib.Path, default=ENERGYPLUS_DIR,
        help=f"EnergyPlus installation directory (default: {ENERGYPLUS_DIR})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Allow overriding EnergyPlus install path at runtime
    if args.energyplus_dir != ENERGYPLUS_DIR:
        import energyplus_paths as _ep_mod
        _ep_mod.ENERGYPLUS_DIR = args.energyplus_dir

    if not check_setup():
        sys.exit(1)

    available, missing = inventory(args.types, args.zones)

    total_pairs = len(args.types) * len(args.zones)
    print(f"\nBuilding types : {args.types}")
    print(f"Climate zones  : {args.zones}")
    print(f"Pairs total    : {total_pairs}")
    print(f"Files found    : {len(available)}")
    print(f"Files missing  : {len(missing)}\n")

    if missing:
        print("MISSING FILE PAIRS (skipped):")
        for btype, zone, msgs in missing:
            cz = CLIMATE_ZONES.get(zone, {})
            print(f"  {btype} × {zone} ({cz.get('city','?')}, {cz.get('state','?')})")
            for m in msgs:
                print(m)
        print()

    if not available:
        print("No simulations to run — add IDF and EPW files and re-run.")
        sys.exit(0)

    data = load_existing_json()

    skipped  = 0
    computed = 0
    errors   = 0
    t_start  = time.time()

    for i, (btype, zone, i_path, e_path) in enumerate(available, 1):
        cz = CLIMATE_ZONES.get(zone, {})
        tag = f"{btype} × {zone} ({cz.get('city','?')})"

        if not args.force and already_computed(data, btype, zone):
            print(f"[{i}/{len(available)}] SKIP  {tag}  (already computed, use --force to re-run)")
            skipped += 1
            continue

        print(f"[{i}/{len(available)}] RUN   {tag}")
        t0 = time.time()

        result = simulate_one(btype, zone, i_path, e_path, WORK_DIR)
        if result is None:
            print(f"  FAILED — see error above\n")
            errors += 1
            continue

        q_heat, q_cool = result
        write_result(data, btype, zone, q_heat, q_cool)

        elapsed = time.time() - t0
        entry = data[btype][zone]
        print(
            f"  Done in {elapsed:.0f}s — "
            f"q_h={entry['q_h']/1000:.0f} kW  "
            f"q_m={entry['q_m']/1000:.0f} kW  "
            f"q_y={entry['q_y']/1000:.1f} kW  "
            f"peak_heat={entry['peak_heat_kW']:.0f} kW  "
            f"peak_cool={entry['peak_cool_kW']:.0f} kW\n"
        )
        computed += 1

    total_time = time.time() - t_start
    print("=" * 60)
    print(f"Done.  {computed} simulated, {skipped} skipped, {errors} errors.")
    print(f"Total time: {total_time/60:.1f} min")
    print(f"Output: {OUT_JSON}")

    if computed > 0:
        print("\nSummary of new results:")
        for btype in args.types:
            for zone in args.zones:
                if data.get(btype, {}).get(zone, {}).get("computed"):
                    e = data[btype][zone]
                    cz = CLIMATE_ZONES.get(zone, {})
                    print(
                        f"  {btype:20s} {zone:3s} {cz.get('city','?'):15s}  "
                        f"q_h={e['q_h']/1000:+7.0f} kW  "
                        f"q_y={e['q_y']/1000:+7.1f} kW"
                    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run envelope sensitivity study for the (building_type, city) pairs still missing.

small_office and medium_office already have all 16 cities.
The following 6 types have only 4 cities (atlanta, buffalo, denver, miami):
  large_office, retail_standalone, retail_stripmall,
  school_primary, school_secondary, warehouse

This script runs the 12 missing cities for each of those types.

Usage:
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_missing.py
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_missing.py --dry-run
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_missing.py --building large_office

After all runs complete, regenerate the aggregate CSV:
    python scripts/aggregate_envelope_results.py
"""
import argparse
import pathlib
import sys
import time

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"
sys.path.insert(0, str(ROOT / "scripts"))

from envelope_study import run_study, CITY_ZONE_MAP  # noqa: E402

# Building types that currently have only 4 cities
MISSING_BTYPES = [
    "large_office",
    "retail_standalone",
    "retail_stripmall",
    "school_primary",
    "school_secondary",
    "warehouse",
]

# Cities already done for all building types (skip these)
DONE_CITIES = {"atlanta", "buffalo", "denver", "miami"}

ALL_CITIES = list(CITY_ZONE_MAP.keys())  # 16 cities


def _is_done(btype: str, city: str) -> bool:
    return (RESULTS_DIR / f"multipliers_{btype}_{city}.json").exists()


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--building", choices=MISSING_BTYPES,
        help="Run only this building type (default: all 6)"
    )
    args = p.parse_args()

    buildings   = [args.building] if args.building else MISSING_BTYPES
    need_cities = [c for c in ALL_CITIES if c not in DONE_CITIES]

    pairs = [
        (b, c) for b in buildings for c in need_cities if not _is_done(b, c)
    ]

    if not pairs:
        print("All pairs already complete.")
        return

    print(f"Pairs to run: {len(pairs)}  ({len(buildings)} building types × {len(need_cities)} cities, minus already-done)")
    if args.dry_run:
        for b, c in pairs:
            print(f"  [DRY] {b}/{c}")
        return

    t0 = time.time()
    n_done = n_fail = 0
    for i, (btype, city) in enumerate(pairs):
        elapsed = time.time() - t0
        if n_done > 0:
            eta_h = elapsed / n_done * (len(pairs) - n_done) / 3600
            print(f"\n[{i+1}/{len(pairs)}] {btype}/{city}  ETA≈{eta_h:.1f}h")
        else:
            print(f"\n[{i+1}/{len(pairs)}] {btype}/{city}")
        try:
            run_study(city, btype, dry_run=False)
            n_done += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            n_fail += 1

    print(f"\nDone: {n_done}/{len(pairs)}  Failed: {n_fail}")
    print("Next: python scripts/aggregate_envelope_results.py")


if __name__ == "__main__":
    main()

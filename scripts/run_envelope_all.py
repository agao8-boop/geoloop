#!/usr/bin/env python3
"""Batch runner: envelope study for all climate zones × all three building types.

Run order: small_office → medium_office → large_office
If large_office crashes, all prior results are preserved and the CSV is written
immediately from whatever completed data exists.

Usage (from geosite_advisor/):
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_all.py
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_all.py --dry-run
    ENERGYPLUS_DIR=/Applications/EnergyPlus-22-1-0 python scripts/run_envelope_all.py --building small_office
"""

import argparse
import json
import os
import pathlib
import sys
import time

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from envelope_study import (
    CITY_ZONE_MAP, BUILDING_TYPE_MAP, run_study,
)
from aggregate_envelope_results import aggregate  # written below


# Run order: small and medium first, large last (crash risk)
BUILD_ORDER = ["small_office", "medium_office", "large_office"]

CITIES_ORDERED = [
    # Roughly hot→cold so results accumulate in a sensible reading order
    "miami", "tampa", "tucson", "atlanta", "el_paso", "san_diego",
    "new_york", "albuquerque", "seattle",
    "buffalo", "denver", "port_angeles",
    "rochester", "great_falls", "international_falls", "fairbanks",
]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--building", choices=list(BUILDING_TYPE_MAP.keys()),
                   help="Run only this building type (default: all)")
    p.add_argument("--dry-run", action="store_true",
                   help="Dry-run: print what would run, no EnergyPlus")
    args = p.parse_args()

    buildings = [args.building] if args.building else BUILD_ORDER
    total     = len(buildings) * len(CITIES_ORDERED)
    done      = 0
    crashed   = []
    t0        = time.time()

    for building in buildings:
        for city in CITIES_ORDERED:
            tag = f"{building}/{city}"
            final = RESULTS_DIR / f"multipliers_{building}_{city}.json"
            if final.exists() and not args.dry_run:
                print(f"[SKIP] {tag} — already done")
                done += 1
                continue

            elapsed = time.time() - t0
            if done > 0:
                eta_s = elapsed / done * (total - done)
                eta_h = eta_s / 3600
                print(f"\n[{done}/{total}] Starting {tag}  |  ETA ≈ {eta_h:.1f}h")
            else:
                print(f"\n[{done}/{total}] Starting {tag}")

            try:
                run_study(city, building, dry_run=args.dry_run)
                done += 1
            except (Exception, SystemExit) as exc:
                crashed.append((building, city, str(exc)))
                print(f"\n  *** CRASH: {tag}: {exc}")
                print(f"  Stopping {building} batch. Saving CSV with data collected so far.")
                # Write CSV from whatever we have, then continue to next building
                if not args.dry_run:
                    _flush_csv()
                break  # stop this building, move to next

        if not args.dry_run:
            _flush_csv()

    print(f"\n{'='*60}")
    print(f"Done. {done}/{total} simulations completed.")
    if crashed:
        print(f"Crashed ({len(crashed)}):")
        for b, c, e in crashed:
            print(f"  {b}/{c}: {e}")
    if not args.dry_run:
        csv_path = _flush_csv()
        print(f"CSV → {csv_path}")


def _flush_csv() -> pathlib.Path:
    """Aggregate all completed results to CSV and return path."""
    try:
        return aggregate()
    except Exception as e:
        print(f"  (CSV aggregation error: {e})")
        return pathlib.Path("(failed)")


if __name__ == "__main__":
    main()

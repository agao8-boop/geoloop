#!/usr/bin/env python3
"""Run controlled SHGC-only and U-only sensitivity sweeps across 8 cities × 3 building types.

Each (building, city) pair produces:
    data/envelope_study/results/multipliers_shgcu_{building}_{city}.json

Run from geosite_advisor/:
    python scripts/run_shgc_u_sensitivity.py                          # all 24 pairs
    python scripts/run_shgc_u_sensitivity.py --dry-run                # print plan, no EP
    python scripts/run_shgc_u_sensitivity.py --building medium_office --city miami
"""

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from envelope_study import run_shgc_u_study, CITY_ZONE_MAP, BUILDING_TYPE_MAP

REPR_CITIES = [
    "miami",               # 1A — extreme hot-humid
    "tampa",               # 2A — hot-humid
    "atlanta",             # 3A — warm-humid
    "san_diego",           # 3C — marine
    "new_york",            # 4A — mixed-humid
    "denver",              # 5B — cold-dry
    "buffalo",             # 5A — cold-humid
    "international_falls", # 7  — very cold
]

REPR_BUILDINGS = ["small_office", "medium_office", "large_office"]


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--building", choices=list(BUILDING_TYPE_MAP.keys()),
                   help="Single building type (default: all 3 office types)")
    p.add_argument("--city", choices=list(CITY_ZONE_MAP.keys()),
                   help="Single city (default: all 8 representative cities)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print variant list without running EnergyPlus")
    args = p.parse_args()

    cities    = [args.city]     if args.city     else REPR_CITIES
    buildings = [args.building] if args.building else REPR_BUILDINGS

    total = len(buildings) * len(cities)
    done  = 0
    for bt in buildings:
        for city in cities:
            done += 1
            print(f"\n[{done}/{total}] {bt} / {city}")
            run_shgc_u_study(city, building_type=bt, dry_run=args.dry_run)

    label = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{label}Done. {done} (building, city) pairs processed.")


if __name__ == "__main__":
    main()

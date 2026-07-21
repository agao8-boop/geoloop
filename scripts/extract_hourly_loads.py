#!/usr/bin/env python3
"""Extract 8760h hourly ground loads from EnergyPlus cache → prototype_loads_hourly.json.

Reads eplusout.eso from data/energyplus_cache/work/{type}_{zone}/ep_output/ for
every available work directory, then MERGES the results into prototype_loads_hourly.json
(existing entries are preserved if no new ESO is found for that type/zone).

Usage: python3 scripts/extract_hourly_loads.py [--dry-run]
Run from repo root.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR  = REPO_ROOT / "data/energyplus_cache/work"
OUT_PATH  = REPO_ROOT / "data/public/prototype_loads_hourly.json"

# Reference prototype areas. Matches PROTOTYPE_AREAS_M2 in s4_sizing/footprint.py.
PROTOTYPE_AREAS_M2 = {
    "small_office":          511.2,
    "medium_office":         4982.2,
    "large_office":          46320.0,
    "standalone_retail":     2294.0,
    "primary_school":        6871.0,
    "secondary_school":      19592.0,
    "hospital":              22422.0,
    "outpatient_healthcare": 3804.0,
    "small_hotel":           4014.0,
    "large_hotel":           11345.0,
    "warehouse":             4835.0,
    "midrise_apartment":     3135.0,
    "highrise_apartment":    11345.0,
    "retail_stripmall":      2090.0,
    "restaurant_fastfood":   232.0,
    "restaurant_sitdown":    511.0,
}

_DIR_RE = re.compile(r'^(.+?)_([0-9]+[A-C]?)$')


def _parse_dir(name: str):
    m = _DIR_RE.match(name)
    return (m.group(1), m.group(2)) if m else (None, None)


def _parse_eso(eso_path: Path):
    """Parse eplusout.eso → (q_heat_W, q_cool_W) as 8760-length lists.

    Sums all ZoneHVAC:IdealLoadsAirSystem heat/cool variables across zones.
    Returns None if file is missing or has unexpected row count.
    """
    HEAT_KEY = "ZONE IDEAL LOADS ZONE TOTAL HEATING ENERGY"
    COOL_KEY = "ZONE IDEAL LOADS ZONE TOTAL COOLING ENERGY"

    heat_codes, cool_codes = set(), set()
    rows_heat, rows_cool = [], []
    in_dict = True
    hour_heat = hour_cool = 0.0
    in_hour = False

    with eso_path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == "End of Data Dictionary":
                in_dict = False
                continue
            if line == "End of Data":
                if in_hour:
                    rows_heat.append(hour_heat)
                    rows_cool.append(hour_cool)
                break
            if in_dict:
                parts = line.split(",", 2)
                if len(parts) >= 3:
                    code = parts[0].strip()
                    desc = parts[2].upper()
                    if HEAT_KEY in desc:
                        heat_codes.add(code)
                    elif COOL_KEY in desc:
                        cool_codes.add(code)
            else:
                code = line.split(",", 1)[0]
                if code == "2":
                    if in_hour:
                        rows_heat.append(hour_heat)
                        rows_cool.append(hour_cool)
                    hour_heat = hour_cool = 0.0
                    in_hour = True
                elif code in heat_codes:
                    try:
                        hour_heat += float(line.split(",", 1)[1])
                    except (ValueError, IndexError):
                        pass
                elif code in cool_codes:
                    try:
                        hour_cool += float(line.split(",", 1)[1])
                    except (ValueError, IndexError):
                        pass

    if len(rows_heat) not in (8760, 8761):
        return None, None

    # EnergyPlus occasionally emits a trailing 8761st entry; trim to 8760.
    rows_heat = rows_heat[:8760]
    rows_cool = rows_cool[:8760]

    # Ground load sign convention: positive = cooling (injection), negative = heating (extraction)
    # Units: Joules/hr → Watts (divide by 3600)
    ground_W = [(c - h) / 3600.0 for h, c in zip(rows_heat, rows_cool)]
    return ground_W, len(heat_codes)


def main():
    dry_run = "--dry-run" in sys.argv

    # Load existing JSON (additive merge)
    existing = {}
    if OUT_PATH.exists():
        with open(OUT_PATH) as f:
            existing = json.load(f)

    result = {
        "_note":     existing.get("_note",
                     "Hourly ground loads in W. Positive = cooling (heat injection). Negative = heating (extraction)."),
        "_units":    existing.get("_units", "W"),
        "_areas_m2": PROTOTYPE_AREAS_M2,
    }

    # Copy existing per-type data
    for k, v in existing.items():
        if not k.startswith("_"):
            result[k] = v

    dirs = sorted(WORK_DIR.iterdir()) if WORK_DIR.exists() else []
    processed, skipped, errors = 0, 0, 0

    for d in dirs:
        if not d.is_dir():
            continue
        bt, cz = _parse_dir(d.name)
        if bt is None or bt not in PROTOTYPE_AREAS_M2:
            skipped += 1
            continue

        eso_path = d / "ep_output" / "eplusout.eso"
        if not eso_path.exists():
            skipped += 1
            continue

        # Skip if already in result (don't overwrite existing real data unless --force)
        if bt in result and cz in result[bt] and "--force" not in sys.argv:
            skipped += 1
            continue

        try:
            ground_W, n_vars = _parse_eso(eso_path)
        except Exception as e:
            print(f"  ERROR {d.name}: {e}", file=sys.stderr)
            errors += 1
            continue

        if ground_W is None:
            print(f"  SKIP (unexpected row count): {d.name}", file=sys.stderr)
            skipped += 1
            continue

        result.setdefault(bt, {})[cz] = [round(float(v), 2) for v in ground_W]
        processed += 1
        peak_h = min(ground_W)
        peak_c = max(ground_W)
        print(f"  OK {bt:25s} {cz:3s}  peak_heat={-peak_h/1000:.0f}kW  peak_cool={peak_c/1000:.0f}kW  vars={n_vars}")

    if not dry_run:
        OUT_PATH.write_text(json.dumps(result, separators=(',', ':')))
        print(f"\nWrote {OUT_PATH}")
    else:
        print("\n(dry-run — no file written)")

    print(f"{processed} processed, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()

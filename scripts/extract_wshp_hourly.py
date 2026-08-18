#!/usr/bin/env python3
"""Extract 8760h cooling/heating coil source-side arrays from completed WSHP ESO files.

Reads data/wshp_runs/{btype}_{City}/eplusout.eso for all 128 completed runs.
Saves data/public/hourly_ground_loads.npz (float32, compressed).

NPZ keys:
  "{btype}_{zone}_clg"  — cooling coil source-side W (heat injection, ≥0)
  "{btype}_{zone}_htg"  — heating coil source-side W (heat extraction, ≥0)

Net ground load: clg - htg  (positive = injection/cooling, negative = extraction/heating)

These arrays are used by geosite/s2_simulation/lookup.py to apply envelope multipliers
to the hourly arrays before extracting q_h, q_m, q_y — the correct order per Item 8.

Run once after run_energyplus_wshp_all.py completes:
    python scripts/extract_wshp_hourly.py
"""
import pathlib
import numpy as np

ROOT     = pathlib.Path(__file__).parent.parent
RUNS_DIR = ROOT / "data" / "wshp_runs"
OUT_NPZ  = ROOT / "data" / "public" / "hourly_ground_loads.npz"

CITY_ZONE = {
    "Miami": "1A", "Tampa": "2A", "Tucson": "2B",
    "Atlanta": "3A", "ElPaso": "3B", "SanDiego": "3C",
    "NewYork": "4A", "Albuquerque": "4B", "PortAngeles": "4C",
    "Buffalo": "5A", "Denver": "5B", "Seattle": "5C",
    "Rochester": "6A", "GreatFalls": "6B",
    "InternationalFalls": "7", "Fairbanks": "8",
}


def _parse_eso(eso_path: pathlib.Path):
    """Return (clg[8760], htg[8760]) float32 arrays or None."""
    clg_codes: set[int] = set()
    htg_codes: set[int] = set()
    in_dict = True
    hourly_data: dict[int, list[float]] = {}

    with open(eso_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if in_dict:
                if line.startswith("End of Data Dictionary"):
                    in_dict = False
                    continue
                parts = line.split(",", 3)
                if len(parts) < 3:
                    continue
                try:
                    code = int(parts[0].strip())
                except ValueError:
                    continue
                varname = parts[3] if len(parts) > 3 else ""
                if "Cooling Coil Source Side Heat Transfer Rate" in varname:
                    clg_codes.add(code)
                    hourly_data.setdefault(code, [])
                elif "Heating Coil Source Side Heat Transfer Rate" in varname:
                    htg_codes.add(code)
                    hourly_data.setdefault(code, [])
            else:
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

    n_hours = max((len(v) for v in hourly_data.values() if v), default=0)
    if n_hours < 8760:
        return None

    clg = np.zeros(8760, dtype=np.float32)
    htg = np.zeros(8760, dtype=np.float32)
    for code in clg_codes:
        vals = hourly_data.get(code, [])
        if vals:
            clg += np.array(vals[:8760], dtype=np.float32)
    for code in htg_codes:
        vals = hourly_data.get(code, [])
        if vals:
            htg += np.array(vals[:8760], dtype=np.float32)
    return clg, htg


def main():
    arrays: dict[str, np.ndarray] = {}
    n_ok = 0
    n_fail = 0

    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        eso = run_dir / "eplusout.eso"
        if not eso.exists():
            continue

        # run_dir: "{btype}_{City}" e.g. "large_office_Atlanta"
        name = run_dir.name
        city = zone = btype = None
        for c, z in CITY_ZONE.items():
            if name.endswith(f"_{c}"):
                city, zone, btype = c, z, name[: -len(c) - 1]
                break
        if city is None:
            print(f"  SKIP (unrecognized dir): {name}")
            continue

        result = _parse_eso(eso)
        if result is None:
            print(f"  FAIL extract: {name}")
            n_fail += 1
            continue

        clg, htg = result
        arrays[f"{btype}_{zone}_clg"] = clg
        arrays[f"{btype}_{zone}_htg"] = htg
        net_peak = max(clg.max(), htg.max()) / 1000
        print(f"  OK  {btype}/{zone:<3}  peak={net_peak:.0f}kW  ({city})")
        n_ok += 1

    OUT_NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT_NPZ, **arrays)
    size_kb = OUT_NPZ.stat().st_size / 1024
    print(f"\nSaved {n_ok} entries ({n_ok * 2} arrays) → {OUT_NPZ}  ({size_kb:.0f} KB)")
    if n_fail:
        print(f"Failed: {n_fail}")


if __name__ == "__main__":
    main()

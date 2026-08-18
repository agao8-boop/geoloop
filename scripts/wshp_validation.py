#!/usr/bin/env python3
"""Compare IdealLoads load profile to unmodified DOE prototype HVAC plant loads.

Validates the gap between our ZoneHVAC:IdealLoadsAirSystem approach and what a
real VAV+chiller+boiler HVAC system produces, as recommended by Peter's colleague.

For each (building_type, city):
  - Run A: Uses existing IdealLoads baseline from envelope_study results
  - Run B: Unmodified DOE prototype IDF — adds output meters, runs EnergyPlus as-is
    (native VAV system with chiller + boiler + real ventilation + economizer)

Deltas show:
  - Ventilation load contribution (always-on DOAS vs ideal-loads ventilation)
  - Economizer free-cooling effect (south-zone cooling in winter)
  - Real equipment staging vs theoretical ideal

Targets
-------
  medium_office × buffalo (5A) — cold climate, heating-dominant, DOAS HX matters most
  medium_office × miami   (1A) — warm climate, cooling-dominant, economizer effect visible
  large_office  × buffalo (5A)
  large_office  × miami   (1A)

Output
------
  data/wshp_validation/{type}_{city}_delta.json
  data/overnight_summary.txt   (appended)

Usage
-----
    python scripts/wshp_validation.py
    python scripts/wshp_validation.py --dry-run
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT       = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR  = ROOT / "data" / "doe_prototypes"
EPW_DIR    = ROOT / "data" / "epw"
OUT_DIR    = ROOT / "data" / "wshp_validation"
SUMMARY_LOG = ROOT / "data" / "overnight_summary.txt"
ENERGYPLUS = pathlib.Path(
    os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-22-1-0")
) / "energyplus"

TARGETS = [
    ("medium_office", "buffalo"),
    ("medium_office", "miami"),
    ("large_office",  "buffalo"),
    ("large_office",  "miami"),
]

CITY_META = {
    "buffalo": {
        "zone":  "5A",
        "epw":   "USA_NY_Buffalo.Niagara.Intl.AP.725280_TMY3.epw",
        "stem":  "Buffalo",
        "note":  "cold climate — DOAS heat recovery most impactful",
    },
    "miami": {
        "zone":  "1A",
        "epw":   "USA_FL_Miami.Intl.AP.722020_TMY3.epw",
        "stem":  "Miami",
        "note":  "warm climate — economizer free-cooling most visible",
    },
}

PROTO_MAP = {
    "medium_office": ("ASHRAE901_OfficeMedium_STD2022", "OfficeMedium"),
    "large_office":  ("ASHRAE901_OfficeLarge_STD2022",  "OfficeLarge"),
}

# Output meter requests to inject into the unmodified prototype IDF
_OUTPUT_METERS = """

  Output:Meter,Chiller Electricity Energy,Hourly;
  Output:Meter,Chiller COP,Hourly;
  Output:Meter,Boiler NaturalGas Energy,Hourly;
  Output:Meter,Boiler Electricity Energy,Hourly;
  Output:Meter,Cooling:Electricity,Hourly;
  Output:Meter,Heating:NaturalGas,Hourly;
  Output:Meter,Heating:Electricity,Hourly;

"""


def _inject_output_meters(idf_text: str) -> str:
    """Append output meter objects before end of file."""
    return idf_text.rstrip() + "\n" + _OUTPUT_METERS


def _parse_eso_meter(eso_path: pathlib.Path, meter_name: str) -> np.ndarray:
    """Extract hourly time-series for a named meter from an EnergyPlus ESO file.

    Returns a numpy array of length ≤ 8760; zeros if meter not found.
    """
    text   = eso_path.read_text(encoding="utf-8", errors="replace")
    lines  = text.splitlines()

    # Dictionary section: find variable index by name match
    var_idx = None
    in_dict = True
    for line in lines:
        if line.startswith("End of Data Dictionary"):
            in_dict = False
            break
        if in_dict and meter_name.lower() in line.lower():
            parts = line.split(",")
            if parts:
                try:
                    var_idx = int(parts[0].strip())
                    break
                except ValueError:
                    pass

    if var_idx is None:
        return np.zeros(8760)

    prefix = f"{var_idx},"
    values = []
    for line in lines:
        if line.startswith(prefix):
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    values.append(float(parts[1]))
                except ValueError:
                    pass

    arr = np.array(values, dtype=float)
    return arr[:8760] if len(arr) >= 8760 else arr


def run_prototype_energyplus(
    building_type: str, city: str,
    work_dir: pathlib.Path, dry_run: bool
) -> dict | None:
    meta  = CITY_META[city]
    proto_stem, idf_type = PROTO_MAP[building_type]
    city_stem = meta["stem"]

    idf_path = PROTO_DIR / proto_stem / f"{proto_stem}_{city_stem}.idf"
    epw_path = EPW_DIR / meta["epw"]

    if not idf_path.exists():
        print(f"  [WARN] IDF not found: {idf_path}")
        return None
    if not epw_path.exists():
        print(f"  [WARN] EPW not found: {epw_path}")
        return None

    run_dir = work_dir / f"{building_type}_{city}"
    run_dir.mkdir(parents=True, exist_ok=True)

    text     = idf_path.read_text(encoding="utf-8", errors="replace")
    text     = _inject_output_meters(text)
    mod_idf  = run_dir / "prototype_with_meters.idf"
    mod_idf.write_text(text, encoding="utf-8")

    if dry_run:
        print(f"  [DRY] would run EnergyPlus: {mod_idf.name} + {epw_path.name}")
        return {
            "peak_heat_W": 0.0, "peak_cool_W": 0.0,
            "annual_heat_Wh": 0.0, "annual_cool_Wh": 0.0,
            "source": "dry_run",
        }

    print(f"  [RUN] EnergyPlus → {run_dir.name} ...")
    t0 = time.time()
    result = subprocess.run(
        [str(ENERGYPLUS), "-w", str(epw_path), "-r", str(mod_idf)],
        cwd=run_dir, capture_output=True, text=True, timeout=7200,
    )
    elapsed = time.time() - t0
    print(f"  [RUN] done in {elapsed/60:.1f} min  rc={result.returncode}")

    if result.returncode != 0:
        err_snippet = (result.stderr or result.stdout or "")[-600:]
        print(f"  [FAIL] EnergyPlus error:\n{err_snippet}")
        return None

    eso_path = run_dir / "eplusout.eso"
    if not eso_path.exists():
        print(f"  [FAIL] No ESO output at {eso_path}")
        return None

    # Try multiple meter names — prototypes vary in how they report
    heat_arr = (
        _parse_eso_meter(eso_path, "Boiler NaturalGas Energy")
        + _parse_eso_meter(eso_path, "Boiler Electricity Energy")
    )
    cool_arr = _parse_eso_meter(eso_path, "Chiller Electricity Energy")

    # Fallback to aggregate meters if object-level meters empty
    if heat_arr.sum() < 1.0:
        heat_arr = _parse_eso_meter(eso_path, "Heating:NaturalGas") \
                 + _parse_eso_meter(eso_path, "Heating:Electricity")
    if cool_arr.sum() < 1.0:
        cool_arr = _parse_eso_meter(eso_path, "Cooling:Electricity")

    # ESO energy meters report in Joules per hour; divide by 3600 to get W/Wh
    return {
        "peak_heat_W":    float(heat_arr.max()) / 3600,
        "peak_cool_W":    float(cool_arr.max()) / 3600,
        "annual_heat_Wh": float(heat_arr.sum()) / 3600,
        "annual_cool_Wh": float(cool_arr.sum()) / 3600,
        "source":         "prototype_vav_chiller_boiler",
        "eso_meters_used": ["Boiler NaturalGas Energy", "Chiller Electricity Energy"],
    }


def load_ideal_baseline(building_type: str, city: str) -> dict | None:
    """Load IdealLoads baseline metrics from the envelope_study result JSON."""
    results_dir = ROOT / "data" / "envelope_study" / "results"
    # Only use building-type-prefixed file; legacy city-only files mix building types
    for fname in (
        f"multipliers_{building_type}_{city}.json",
    ):
        p = results_dir / fname
        if p.exists():
            data = json.loads(p.read_text())
            raw  = data.get("raw_metrics", {})
            bl   = data.get("baseline_label", "wwr_20pct")
            bm   = raw.get(bl)
            if bm:
                return {
                    "peak_heat_W":    bm["peak_heat_kW"] * 1000,
                    "peak_cool_W":    bm["peak_cool_kW"] * 1000,
                    "annual_heat_Wh": bm["annual_heat_MWh"] * 1e6,
                    "annual_cool_Wh": bm["annual_cool_MWh"] * 1e6,
                    "source": "ZoneHVAC:IdealLoadsAirSystem",
                    "json_file": fname,
                }
    return None


def _delta_pct(a: float, b: float) -> float:
    if abs(a) < 1.0:
        return 0.0
    return round((b - a) / abs(a) * 100.0, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary_lines = [
        "=" * 60,
        "WSHP / IDEAL-LOADS VALIDATION — OVERNIGHT SUMMARY",
        "=" * 60,
        "Compares ZoneHVAC:IdealLoadsAirSystem (our model) vs",
        "unmodified DOE prototype VAV+chiller+boiler system.",
        "delta_pct = (prototype - ideal) / |ideal| × 100",
        "-" * 60,
    ]

    with tempfile.TemporaryDirectory(prefix="wshp_val_") as tmpdir:
        work = pathlib.Path(tmpdir)

        for building_type, city in TARGETS:
            tag  = f"{building_type}_{city}"
            meta = CITY_META[city]
            print(f"\n{'='*50}")
            print(f"Target: {tag}  ({meta['zone']} — {meta['note']})")

            ideal = load_ideal_baseline(building_type, city)
            if ideal is None:
                print(f"  [WARN] No IdealLoads baseline for {tag} — run sensitivity study first")
                summary_lines.append(f"  ✗ {tag:<35} SKIPPED — no IdealLoads baseline")
                continue

            proto = run_prototype_energyplus(building_type, city, work, dry_run=args.dry_run)
            if proto is None:
                summary_lines.append(f"  ✗ {tag:<35} FAILED — EnergyPlus error")
                continue

            delta = {
                "peak_heat_ideal_kW":      round(ideal["peak_heat_W"]    / 1000, 1),
                "peak_heat_proto_kW":      round(proto["peak_heat_W"]    / 1000, 1),
                "peak_heat_delta_pct":     _delta_pct(ideal["peak_heat_W"],    proto["peak_heat_W"]),
                "peak_cool_ideal_kW":      round(ideal["peak_cool_W"]    / 1000, 1),
                "peak_cool_proto_kW":      round(proto["peak_cool_W"]    / 1000, 1),
                "peak_cool_delta_pct":     _delta_pct(ideal["peak_cool_W"],    proto["peak_cool_W"]),
                "annual_heat_ideal_MWh":   round(ideal["annual_heat_Wh"] / 1e6, 2),
                "annual_heat_proto_MWh":   round(proto["annual_heat_Wh"] / 1e6, 2),
                "annual_heat_delta_pct":   _delta_pct(ideal["annual_heat_Wh"], proto["annual_heat_Wh"]),
                "annual_cool_ideal_MWh":   round(ideal["annual_cool_Wh"] / 1e6, 2),
                "annual_cool_proto_MWh":   round(proto["annual_cool_Wh"] / 1e6, 2),
                "annual_cool_delta_pct":   _delta_pct(ideal["annual_cool_Wh"], proto["annual_cool_Wh"]),
                "climate_zone": meta["zone"],
                "climate_note":  meta["note"],
                "proto_system": "VAV + chiller + boiler (unmodified DOE prototype)",
                "ideal_system": "ZoneHVAC:IdealLoadsAirSystem (HVAC stripped)",
                "interpretation": (
                    "Positive delta = prototype uses MORE energy than IdealLoads predicts. "
                    "Negative delta = IdealLoads overpredicts (e.g. economizer effect). "
                    "If |delta| < 15% on peak loads, IdealLoads approach is acceptable for feasibility sizing."
                ),
            }

            out_path = OUT_DIR / f"{tag}_delta.json"
            out_path.write_text(json.dumps({"ideal": ideal, "prototype": proto, "delta": delta}, indent=2))
            print(f"  → Saved {out_path.name}")
            print(f"  peak_heat:   ideal={delta['peak_heat_ideal_kW']}kW  proto={delta['peak_heat_proto_kW']}kW  Δ={delta['peak_heat_delta_pct']:+.1f}%")
            print(f"  peak_cool:   ideal={delta['peak_cool_ideal_kW']}kW  proto={delta['peak_cool_proto_kW']}kW  Δ={delta['peak_cool_delta_pct']:+.1f}%")
            print(f"  annual_heat: ideal={delta['annual_heat_ideal_MWh']}MWh  proto={delta['annual_heat_proto_MWh']}MWh  Δ={delta['annual_heat_delta_pct']:+.1f}%")
            print(f"  annual_cool: ideal={delta['annual_cool_ideal_MWh']}MWh  proto={delta['annual_cool_proto_MWh']}MWh  Δ={delta['annual_cool_delta_pct']:+.1f}%")

            verdict = "ACCEPTABLE" if (
                abs(delta["peak_heat_delta_pct"]) < 20 and
                abs(delta["peak_cool_delta_pct"]) < 20
            ) else "REVIEW NEEDED"
            summary_lines.append(
                f"  {'✓' if verdict=='ACCEPTABLE' else '!'} {tag:<35} "
                f"heat_Δ={delta['peak_heat_delta_pct']:+.1f}%  "
                f"cool_Δ={delta['peak_cool_delta_pct']:+.1f}%  → {verdict}"
            )

    summary_lines += ["=" * 60, ""]
    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text)

    SUMMARY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_LOG, "a") as f:
        f.write("\n" + summary_text + "\n")
    print(f"[wshp_validation] Summary appended → {SUMMARY_LOG}")


if __name__ == "__main__":
    main()

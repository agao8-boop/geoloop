#!/usr/bin/env python3
"""Analyze SHGC vs U-factor sensitivity results across 8 cities × 3 building types.

Reads:   data/envelope_study/results/multipliers_shgcu_{building}_{city}.json
Outputs: outputs/shgc_u_sensitivity/
  - sensitivity_summary.csv  — one row per (city, building, param, level)
                               includes both multipliers AND absolute kWh deltas
  - winner_table.csv         — which parameter dominates each city×building×mode
                               uses absolute kWh when baseline heating < 0.5 MWh

Run from geosite_advisor/:
    python scripts/analyze_shgc_u_results.py
"""

import csv
import json
import pathlib
import sys

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"
OUT_DIR     = ROOT / "outputs" / "shgc_u_sensitivity"

REPR_CITIES = [
    "miami", "tampa", "atlanta", "san_diego",
    "new_york", "denver", "buffalo", "international_falls",
]
REPR_BUILDINGS = ["small_office", "medium_office", "large_office"]

CITY_ZONE = {
    "miami": "1A", "tampa": "2A", "atlanta": "3A", "san_diego": "3C",
    "new_york": "4A", "denver": "5B", "buffalo": "5A", "international_falls": "7",
}

# Multiplier range analysis is meaningless when baseline is this small
HEAT_DEGENERATE_THRESHOLD_MWH = 0.5


def _range_of(values: list) -> float:
    return (max(values) - min(values)) if values else 0.0


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    missing = []

    for bt in REPR_BUILDINGS:
        for city in REPR_CITIES:
            tag  = f"{bt}_{city}"
            path = RESULTS_DIR / f"multipliers_shgcu_{tag}.json"
            if not path.exists():
                missing.append(tag)
                continue

            data           = json.loads(path.read_text())
            cz             = data.get("climate_zone", CITY_ZONE.get(city, "?"))
            mults          = data.get("multipliers", {})
            raw_metrics    = data.get("raw_metrics", {})
            baseline_heat  = (raw_metrics.get("shgcu_baseline") or {}).get("annual_heat_MWh", 0.0)
            baseline_cool  = (raw_metrics.get("shgcu_baseline") or {}).get("annual_cool_MWh", 1.0)
            heat_degenerate = baseline_heat < HEAT_DEGENERATE_THRESHOLD_MWH

            for label, m in mults.items():
                if m["param"] == "baseline":
                    continue
                rm = raw_metrics.get(label) or {}
                rows.append({
                    "city":              city,
                    "climate_zone":      cz,
                    "building":          bt,
                    "param":             m["param"],
                    "level":             m["level"],
                    "u_factor":          m["u_factor"],
                    "shgc":              m["shgc"],
                    "annual_heat_mult":  m["annual_heat"],
                    "annual_cool_mult":  m["annual_cool"],
                    "peak_heat_mult":    m["peak_heat"],
                    "peak_cool_mult":    m["peak_cool"],
                    "annual_heat_MWh":   rm.get("annual_heat_MWh", ""),
                    "annual_cool_MWh":   rm.get("annual_cool_MWh", ""),
                    "delta_heat_MWh":    round((rm.get("annual_heat_MWh", baseline_heat) - baseline_heat), 4)
                                         if rm else "",
                    "delta_cool_MWh":   round((rm.get("annual_cool_MWh", baseline_cool) - baseline_cool), 4)
                                         if rm else "",
                    "heat_degenerate":   heat_degenerate,
                })

    if missing:
        print(f"WARNING: {len(missing)} result files not found yet.")
        for m in missing:
            print(f"  missing: {m}")
        if not rows:
            print("No data to analyze — run run_shgc_u_sensitivity.py first.")
            sys.exit(0)

    # sensitivity_summary.csv
    summary_path = OUT_DIR / "sensitivity_summary.csv"
    fields = ["city", "climate_zone", "building", "param", "level",
              "u_factor", "shgc",
              "annual_heat_mult", "annual_cool_mult",
              "peak_heat_mult", "peak_cool_mult",
              "annual_heat_MWh", "annual_cool_MWh",
              "delta_heat_MWh", "delta_cool_MWh",
              "heat_degenerate"]
    with open(summary_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {summary_path}  ({len(rows)} rows)")

    # winner_table.csv
    # Cooling: always use multiplier range (cooling is never degenerate in offices)
    # Heating: use absolute MWh delta range when baseline_heat < threshold; mult otherwise
    winner_rows = []
    for bt in REPR_BUILDINGS:
        for city in REPR_CITIES:
            cz  = CITY_ZONE.get(city, "?")
            sub = [r for r in rows if r["city"] == city and r["building"] == bt]
            if not sub:
                continue
            shgc_r = [r for r in sub if r["param"] == "shgc_sweep"]
            u_r    = [r for r in sub if r["param"] == "u_sweep"]
            if not shgc_r or not u_r:
                continue

            heat_deg = shgc_r[0]["heat_degenerate"]

            # Cooling: multiplier range
            shgc_cool = _range_of([r["annual_cool_mult"] for r in shgc_r])
            u_cool    = _range_of([r["annual_cool_mult"] for r in u_r])

            # Heating: absolute MWh delta range if degenerate, else multiplier range
            if heat_deg:
                shgc_heat = _range_of([abs(r["delta_heat_MWh"]) for r in shgc_r
                                       if r["delta_heat_MWh"] != ""])
                u_heat    = _range_of([abs(r["delta_heat_MWh"]) for r in u_r
                                       if r["delta_heat_MWh"] != ""])
                heat_metric = "abs_MWh"
            else:
                shgc_heat = _range_of([r["annual_heat_mult"] for r in shgc_r])
                u_heat    = _range_of([r["annual_heat_mult"] for r in u_r])
                heat_metric = "multiplier"

            winner_rows.append({
                "city":             city,
                "climate_zone":     cz,
                "building":         bt,
                "shgc_cool_range":  round(shgc_cool, 4),
                "u_cool_range":     round(u_cool,    4),
                "cooling_winner":   "SHGC" if shgc_cool > u_cool else "U-factor",
                "shgc_heat_range":  round(shgc_heat, 4),
                "u_heat_range":     round(u_heat,    4),
                "heating_winner":   "SHGC" if shgc_heat > u_heat else "U-factor",
                "heat_metric":      heat_metric,
                "heat_degenerate":  heat_deg,
            })

    winner_path = OUT_DIR / "winner_table.csv"
    wfields = ["city", "climate_zone", "building",
               "shgc_cool_range", "u_cool_range", "cooling_winner",
               "shgc_heat_range", "u_heat_range", "heating_winner",
               "heat_metric", "heat_degenerate"]
    with open(winner_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=wfields)
        w.writeheader()
        w.writerows(winner_rows)
    print(f"Wrote {winner_path}  ({len(winner_rows)} rows)")

    if not winner_rows:
        return

    print("\nSHGC vs U-factor sensitivity (annual load):")
    print(f"  * cooling: multiplier range  |  heating: mult range or abs MWh when baseline≈0")
    print(f"\n{'City':25s} {'Zone':4s} {'Bldg':20s} {'SHGC/cool':10s} {'U/cool':8s} {'Winner':8s} | "
          f"{'SHGC/heat':10s} {'U/heat':8s} {'Winner':8s} {'Metric':6s}")
    print(f"  {'-'*110}")
    for r in winner_rows:
        deg = " [!]" if r["heat_degenerate"] else ""
        print(f"  {r['city']:23s} {r['climate_zone']:4s} {r['building']:20s} "
              f"{r['shgc_cool_range']:10.4f} {r['u_cool_range']:8.4f} {r['cooling_winner']:8s} | "
              f"{r['shgc_heat_range']:10.4f} {r['u_heat_range']:8.4f} {r['heating_winner']:8s} "
              f"{r['heat_metric']}{deg}")

    degenerate = [r for r in winner_rows if r["heat_degenerate"]]
    if degenerate:
        print(f"\n  [!] {len(degenerate)} cases used abs MWh for heating (baseline heat < "
              f"{HEAT_DEGENERATE_THRESHOLD_MWH} MWh — multiplier unstable):")
        for r in degenerate:
            print(f"       {r['building']:20s} {r['city']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Aggregate all envelope study JSON results into one flat CSV.

Reads every multipliers_{building}_{city}.json in data/envelope_study/results/
and writes envelope_multipliers_all.csv with one row per (building, city, variant).

Usage:
    python scripts/aggregate_envelope_results.py
"""

import csv
import json
import pathlib
import sys

ROOT        = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "envelope_study" / "results"
OUT_CSV     = RESULTS_DIR / "envelope_multipliers_all.csv"

COLUMNS = [
    "climate_zone", "city", "building_type",
    "parameter", "variant",
    "wwr_target", "u_factor", "shgc", "infil_rate",
    "peak_heat_mult", "peak_cool_mult",
    "annual_heat_mult", "annual_cool_mult",
    "combined_peak_mult",
    # raw baseline loads for context
    "baseline_peak_heat_kW", "baseline_peak_cool_kW",
    "baseline_annual_heat_MWh", "baseline_annual_cool_MWh",
]


def aggregate() -> pathlib.Path:
    """Read all result JSONs and write the flat CSV. Returns output path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_files = sorted(RESULTS_DIR.glob("multipliers_*_*.json"))
    # Exclude partial files
    json_files = [f for f in json_files if "_partial" not in f.name]

    if not json_files:
        print("No completed result JSONs found in", RESULTS_DIR)
        return OUT_CSV

    rows = []
    for jf in json_files:
        try:
            d = json.loads(jf.read_text())
        except Exception as e:
            print(f"  Warning: could not read {jf.name}: {e}")
            continue

        building    = d.get("building_type", "unknown")
        city        = d.get("city", "unknown")
        zone        = d.get("climate_zone", "?")
        mults       = d.get("multipliers", {})
        raw         = d.get("raw_metrics", {})
        baseline_lbl = d.get("baseline_label", "wwr_20pct")

        # Baseline raw loads
        bl = raw.get(baseline_lbl, {})
        bl_ph  = bl.get("peak_heat_kW",    "")
        bl_pc  = bl.get("peak_cool_kW",    "")
        bl_ah  = bl.get("annual_heat_MWh", "")
        bl_ac  = bl.get("annual_cool_MWh", "")

        for variant_key, m in mults.items():
            rows.append({
                "climate_zone":    zone,
                "city":            city,
                "building_type":   building,
                "parameter":       m.get("param",  ""),
                "variant":         m.get("level",  variant_key),
                "wwr_target":      m.get("wwr_scale",  ""),
                "u_factor":        m.get("u_factor",   ""),
                "shgc":            m.get("shgc",        ""),
                "infil_rate":      m.get("infil_rate",  ""),
                "peak_heat_mult":       m.get("peak_heat",    ""),
                "peak_cool_mult":       m.get("peak_cool",    ""),
                "annual_heat_mult":     m.get("annual_heat",  ""),
                "annual_cool_mult":     m.get("annual_cool",  ""),
                "combined_peak_mult":   m.get("combined_peak",""),
                "baseline_peak_heat_kW":    bl_ph,
                "baseline_peak_cool_kW":    bl_pc,
                "baseline_annual_heat_MWh": bl_ah,
                "baseline_annual_cool_MWh": bl_ac,
            })

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Aggregated {len(rows)} rows from {len(json_files)} result files → {OUT_CSV}")
    return OUT_CSV


if __name__ == "__main__":
    aggregate()

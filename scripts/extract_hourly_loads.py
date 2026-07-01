#!/usr/bin/env python3
"""Extract 8760h hourly ground loads from EnergyPlus cache → prototype_loads_hourly.json.

Usage: python3 scripts/extract_hourly_loads.py
Run from repo root. Requires: pandas, numpy (already in venv).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR  = REPO_ROOT / "data/energyplus_cache/work"
OUT_PATH  = REPO_ROOT / "data/public/prototype_loads_hourly.json"

_PROTOTYPE_AREAS_M2 = {
    "small_office":  511,
    "medium_office": 4982,
    "large_office":  46320,
}

_DIR_RE = re.compile(r'^(.+)_([0-9]+[A-C]?)$')


def _parse_dir(name: str):
    m = _DIR_RE.match(name)
    return (m.group(1), m.group(2)) if m else (None, None)


def _extract_ground_load(csv_path: Path) -> np.ndarray:
    df = pd.read_csv(csv_path)
    heat_cols = [c for c in df.columns if "Zone Ideal Loads Zone Total Heating Energy [J]" in c]
    cool_cols = [c for c in df.columns if "Zone Ideal Loads Zone Total Cooling Energy [J]" in c]
    if not heat_cols or not cool_cols:
        raise ValueError(f"Cannot find IDEALLOADS columns in {csv_path}")
    heat_J = df[heat_cols].sum(axis=1).values
    cool_J = df[cool_cols].sum(axis=1).values
    ground_W = (cool_J - heat_J) / 3600.0
    if len(ground_W) != 8760:
        raise ValueError(f"Expected 8760 rows, got {len(ground_W)} in {csv_path}")
    return ground_W


def main():
    result: dict = {
        "_note":     "Hourly ground loads in W. Positive = cooling (heat injection). Negative = heating (extraction).",
        "_units":    "W",
        "_areas_m2": _PROTOTYPE_AREAS_M2,
    }

    dirs = sorted(WORK_DIR.iterdir()) if WORK_DIR.exists() else []
    processed, skipped = 0, 0

    for d in dirs:
        if not d.is_dir():
            continue
        bt, cz = _parse_dir(d.name)
        if bt is None or bt not in _PROTOTYPE_AREAS_M2:
            skipped += 1
            continue
        csv_path = d / "ep_output" / "eplusout.csv"
        if not csv_path.exists():
            print(f"  SKIP (no CSV): {d.name}", file=sys.stderr)
            skipped += 1
            continue
        try:
            ground_W = _extract_ground_load(csv_path)
        except Exception as e:
            print(f"  ERROR {d.name}: {e}", file=sys.stderr)
            skipped += 1
            continue
        result.setdefault(bt, {})[cz] = [round(float(v), 2) for v in ground_W]
        processed += 1
        print(f"  OK {d.name}: peak={ground_W.max():.0f}W min={ground_W.min():.0f}W", flush=True)

    OUT_PATH.write_text(json.dumps(result, separators=(',', ':')))
    print(f"\nWrote {OUT_PATH} — {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    main()

"""
scripts/collect_macrostrat_thermal.py
───────────────────────────────────────────────────────────────────────────────
Replace SGMC_CH1995 k estimates with Macrostrat-derived depth-weighted k_eff.

Method:
  For each SGMC_CH1995 county centroid, query Macrostrat API for the
  stratigraphic column (ordered youngest→oldest = shallowest→deepest).
  Use unit thicknesses to assign depth windows. Clip to borehole depth 0–150 m.
  Map each unit's lithology → Clauser & Huenges (1995) k_min/k_median/k_max.
  Compute effective k via series (harmonic) mean — physically correct for
  heat flow along a borehole:

      k_eff = H_total / Σ(H_i / k_i)

  Propagate Clauser k_min/k_max through the harmonic formula to get
  k_eff_min (pessimistic) and k_eff_max (optimistic).

Outputs:
  data/public/macrostrat_thermal_by_county.csv
  Columns: county_fips, state_abbrev, county_name,
           k_macro_base, k_macro_min, k_macro_max,
           macro_layers_n, coverage (full/partial/none),
           col_name, notes

References:
  Clauser, C., & Huenges, E. (1995). Thermal conductivity of rocks and
    minerals. AGU Reference Shelf 3, pp. 105–126.
  Macrostrat: Peters et al. (2018), J. Geophys. Res. https://macrostrat.org
"""

import csv
import pathlib
import time
import requests

ROOT      = pathlib.Path(__file__).parent.parent
SGMC_CSV  = ROOT / "data" / "ml" / "sgmc_by_county.csv"
DEEP_CSV  = ROOT / "data" / "public" / "deep_thermal_by_county.csv"
OUT_CSV   = ROOT / "data" / "public" / "macrostrat_thermal_by_county.csv"

BOREHOLE_DEPTH_M = 150.0
API_DELAY_S      = 0.25   # polite rate limit

# ── Lithology name/type/class → our k class ──────────────────────────────
_NAME_MAP = {
    # fine-grained siliciclastics
    "shale": "clay_shale", "mudstone": "clay_shale", "claystone": "clay_shale",
    "siltstone": "clay_shale", "marl": "clay_shale", "argillite": "clay_shale",
    "mudrock": "clay_shale",
    # carbonates
    "limestone": "limestone_carbonate", "dolostone": "limestone_carbonate",
    "dolomite": "limestone_carbonate", "chalk": "limestone_carbonate",
    "travertine": "limestone_carbonate", "calcarenite": "limestone_carbonate",
    "wackestone": "limestone_carbonate", "packstone": "limestone_carbonate",
    "grainstone": "limestone_carbonate", "boundstone": "limestone_carbonate",
    # coarse siliciclastics
    "sandstone": "sandstone", "arkose": "sandstone", "graywacke": "sandstone",
    "conglomerate": "sandstone", "breccia": "sandstone",
    "quartz arenite": "sandstone", "litharenite": "sandstone",
    # unconsolidated
    "sand": "alluvial_glacial", "gravel": "alluvial_glacial",
    "clay": "alluvial_glacial", "silt": "alluvial_glacial",
    "till": "alluvial_glacial", "diamictite": "alluvial_glacial",
    "loess": "alluvial_glacial", "diamicton": "alluvial_glacial",
    # organic
    "coal": "coal_organic", "peat": "coal_organic", "lignite": "coal_organic",
    # felsic igneous
    "granite": "granite_felsic", "granodiorite": "granite_felsic",
    "rhyolite": "granite_felsic", "tonalite": "granite_felsic",
    "diorite": "granite_felsic", "andesite": "granite_felsic",
    "syenite": "granite_felsic", "trachyte": "granite_felsic",
    # mafic igneous
    "basalt": "basalt_mafic", "gabbro": "basalt_mafic",
    "diabase": "basalt_mafic", "dolerite": "basalt_mafic",
    "dunite": "basalt_mafic", "peridotite": "basalt_mafic",
    "pyroxenite": "basalt_mafic",
    # metamorphic
    "gneiss": "metamorphic", "schist": "metamorphic",
    "phyllite": "metamorphic", "slate": "metamorphic",
    "marble": "metamorphic", "amphibolite": "metamorphic",
    "quartzite": "metamorphic", "hornfels": "metamorphic",
    "eclogite": "metamorphic", "migmatite": "metamorphic",
}

_TYPE_MAP = {
    "siliciclastic":  "clay_shale",          # fine-grained bias for siliciclastics
    "carbonate":      "limestone_carbonate",
    "unconsolidated": "alluvial_glacial",
    "evaporite":      "undifferentiated",
    "chemical":       "undifferentiated",
    "organic":        "coal_organic",
    "volcaniclastic": "basalt_mafic",
}

_CLASS_MAP = {
    "sedimentary":  "undifferentiated",
    "igneous":      "granite_felsic",
    "metamorphic":  "metamorphic",
    "metasedimentary": "metamorphic",
}

# k_min, k_median, k_max [W/m·K] — Clauser & Huenges (1995)
_K_TABLE = {
    "alluvial_glacial":    (0.50, 1.50, 2.20),
    "clay_shale":          (1.50, 2.00, 3.50),
    "limestone_carbonate": (2.50, 3.25, 4.00),
    "sandstone":           (1.50, 2.50, 5.50),
    "granite_felsic":      (2.50, 3.00, 4.50),
    "basalt_mafic":        (1.00, 1.70, 3.00),
    "metamorphic":         (1.50, 2.90, 4.50),
    "coal_organic":        (0.10, 0.30, 0.50),
    "undifferentiated":    (1.50, 2.50, 4.00),
}


def _lith_to_class(name: str, ltype: str, lclass: str) -> str:
    return (
        _NAME_MAP.get((name or "").lower().strip())
        or _TYPE_MAP.get((ltype or "").lower().strip())
        or _CLASS_MAP.get((lclass or "").lower().strip())
        or "undifferentiated"
    )


def _unit_k(lith_list: list) -> tuple[float, float, float]:
    """Proportion-weighted k for a unit from its lithology entries."""
    if not lith_list:
        return _K_TABLE["undifferentiated"]
    total_prop = sum(l.get("prop", 1.0) for l in lith_list) or 1.0
    k_min = k_med = k_max = 0.0
    for lith in lith_list:
        cls = _lith_to_class(lith.get("name",""), lith.get("type",""), lith.get("class",""))
        lo, md, hi = _K_TABLE[cls]
        w = lith.get("prop", 1.0) / total_prop
        k_min += w * lo
        k_med += w * md
        k_max += w * hi
    return k_min, k_med, k_max


def _harmonic_k(layers: list) -> tuple[float, float, float]:
    """
    layers = [(H_m, k_min, k_med, k_max), ...]
    Returns (k_eff_min, k_eff_base, k_eff_max) via harmonic mean.
    k_eff_min = H / Σ(H_i/k_min_i)  — worst case (low k in every layer)
    k_eff_max = H / Σ(H_i/k_max_i)  — best case
    """
    H_total = sum(h for h, *_ in layers)
    if H_total <= 0:
        return float("nan"), float("nan"), float("nan")
    r_worst = sum(H / klo for H, klo, kmd, khi in layers)
    r_base  = sum(H / kmd for H, klo, kmd, khi in layers)
    r_best  = sum(H / khi for H, klo, kmd, khi in layers)
    return (
        round(H_total / r_worst, 4),
        round(H_total / r_base,  4),
        round(H_total / r_best,  4),
    )


def fetch_column(lat: float, lon: float) -> dict:
    """Query Macrostrat. Returns dict with 'units' list or 'error' string."""
    try:
        r = requests.get(
            "https://macrostrat.org/api/v2/columns",
            params={"lat": lat, "lng": lon, "format": "json"},
            timeout=15,
        )
        r.raise_for_status()
        cols = r.json().get("success", {}).get("data", [])
        if not cols:
            return {"error": "no column at this location"}
        col_id = cols[0]["col_id"]
        col_name = cols[0].get("col_name", "")

        time.sleep(0.1)
        r2 = requests.get(
            "https://macrostrat.org/api/v2/units",
            params={"col_id": col_id, "response": "long", "format": "json"},
            timeout=15,
        )
        r2.raise_for_status()
        units = r2.json().get("success", {}).get("data", [])
        return {"col_id": col_id, "col_name": col_name, "units": units}
    except Exception as exc:
        return {"error": str(exc)}


def process_county(lat: float, lon: float) -> dict:
    col = fetch_column(lat, lon)
    if "error" in col or not col.get("units"):
        return {
            "coverage": "none", "k_macro_base": "", "k_macro_min": "",
            "k_macro_max": "", "macro_layers_n": 0,
            "col_name": col.get("col_name", ""),
            "notes": col.get("error", "no units"),
        }

    # Sort youngest (shallowest) first
    units = sorted(col["units"], key=lambda u: u.get("t_age", 0))

    layers = []
    depth = 0.0
    for u in units:
        max_t = float(u.get("max_thick") or 0)
        min_t = float(u.get("min_thick") or 0)
        H_unit = (min_t + max_t) / 2.0
        if H_unit <= 0:
            continue

        # Clip to borehole window
        clip_start = max(depth, 0.0)
        clip_end   = min(depth + H_unit, BOREHOLE_DEPTH_M)
        H_in = clip_end - clip_start

        if H_in > 0:
            klo, kmd, khi = _unit_k(u.get("lith") or [])
            layers.append((H_in, klo, kmd, khi))

        depth += H_unit
        if depth >= BOREHOLE_DEPTH_M:
            break

    if not layers:
        return {
            "coverage": "none", "k_macro_base": "", "k_macro_min": "",
            "k_macro_max": "", "macro_layers_n": 0,
            "col_name": col.get("col_name", ""),
            "notes": "no units with usable thickness",
        }

    H_covered = sum(h for h, *_ in layers)
    coverage  = "full" if H_covered >= 0.8 * BOREHOLE_DEPTH_M else "partial"
    k_min, k_base, k_max = _harmonic_k(layers)

    return {
        "coverage":      coverage,
        "k_macro_base":  k_base,
        "k_macro_min":   k_min,
        "k_macro_max":   k_max,
        "macro_layers_n": len(layers),
        "col_name":      col.get("col_name", ""),
        "notes":         f"{H_covered:.0f}m of {BOREHOLE_DEPTH_M:.0f}m covered",
    }


def main():
    # Load centroids from sgmc_by_county.csv (all 3221 counties)
    centroids = {}
    with open(SGMC_CSV) as f:
        for row in csv.DictReader(f):
            fips = row["county_fips"].zfill(5)
            centroids[fips] = (float(row["centroid_lat"]), float(row["centroid_lon"]))

    # Select only SGMC_CH1995 counties
    target = []
    with open(DEEP_CSV) as f:
        for row in csv.DictReader(f):
            if row["k_method"] == "SGMC_CH1995":
                fips = row["county_fips"].zfill(5)
                target.append((fips, row["state_abbrev"], row["county_name"],
                                row["k_wmpk"], row["k_class_min"], row["k_class_max"]))

    print(f"Processing {len(target)} SGMC_CH1995 counties via Macrostrat API...")
    print("Estimated time: ~8 min at 0.25 s/county\n")

    rows = []
    for i, (fips, state, name, k_old, k_old_min, k_old_max) in enumerate(target):
        lat, lon = centroids.get(fips, (None, None))
        if lat is None:
            res = {"coverage": "none", "k_macro_base": "", "k_macro_min": "",
                   "k_macro_max": "", "macro_layers_n": 0, "col_name": "", "notes": "no centroid"}
        else:
            res = process_county(lat, lon)

        rows.append({
            "county_fips":  fips,
            "state_abbrev": state,
            "county_name":  name,
            "k_sgmc_old":   k_old,
            "k_sgmc_min":   k_old_min,
            "k_sgmc_max":   k_old_max,
            **res,
        })

        if (i + 1) % 50 == 0 or (i + 1) == len(target):
            n_ok = sum(1 for r in rows if r["coverage"] != "none")
            print(f"  [{i+1:3d}/{len(target)}] {n_ok} with Macrostrat data "
                  f"({100*n_ok/(i+1):.0f}%)")

        time.sleep(API_DELAY_S)

    # Write CSV
    fields = [
        "county_fips", "state_abbrev", "county_name",
        "k_sgmc_old", "k_sgmc_min", "k_sgmc_max",
        "k_macro_base", "k_macro_min", "k_macro_max",
        "macro_layers_n", "coverage", "col_name", "notes",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # ── Summary stats ────────────────────────────────────────────────────
    n_full    = sum(1 for r in rows if r["coverage"] == "full")
    n_partial = sum(1 for r in rows if r["coverage"] == "partial")
    n_none    = sum(1 for r in rows if r["coverage"] == "none")
    print(f"\nCoverage: {n_full} full / {n_partial} partial / {n_none} none")

    import statistics
    valid = [r for r in rows if r["k_macro_base"] != ""]
    if valid:
        diffs = [float(r["k_macro_base"]) - float(r["k_sgmc_old"]) for r in valid]
        print(f"\nk comparison (Macrostrat base vs SGMC old), n={len(valid)}:")
        print(f"  mean  Δk = {statistics.mean(diffs):+.3f} W/m·K")
        print(f"  stdev Δk = {statistics.stdev(diffs):.3f} W/m·K")
        print(f"  min   Δk = {min(diffs):+.3f}  max Δk = {max(diffs):+.3f}")
        higher = sum(1 for d in diffs if d > 0.1)
        lower  = sum(1 for d in diffs if d < -0.1)
        same   = len(diffs) - higher - lower
        print(f"  Macro > SGMC by >0.1: {higher} counties")
        print(f"  Macro < SGMC by >0.1: {lower} counties")
        print(f"  Within ±0.1:          {same} counties")

    print(f"\nOutput: {OUT_CSV}")


if __name__ == "__main__":
    main()

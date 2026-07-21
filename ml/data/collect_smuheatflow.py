"""
ml/data/collect_smuheatflow.py
═══════════════════════════════════════════════════════════════════════════
Download and clean the SMU Geothermal Heat Flow Database for the US.

The SMU database is the largest publicly available compilation of US
geothermal measurements (~35,000 data points). Each row has:
  lat, lon, heat flow Q [mW/m²], temperature gradient [°C/km],
  depth [m], and sometimes a direct rock thermal conductivity k [W/m·K].

From Q and dT/dz we can derive: k = Q / (dT/dz)   [Fourier's Law]
  Q in [W/m²] = Q_mWm2 × 10⁻³
  dT/dz in [K/m] = dT/dz_per_km × 10⁻³
  → k = (Q × 10⁻³) / (dT/dz × 10⁻³) = Q / dT/dz  [W/m·K]

Ground temperature at depth z: T(z) = T_surface + dT/dz × z

Run from project root:
    python ml/data/collect_smuheatflow.py

Output: data/ml/smuheatflow_clean.csv
  Columns: lat, lon, state_fips, county_fips, k_wmpk, T_g_C,
           gradient_C_per_km, heatflow_mWm2, depth_m, source

NOTE: SMU requires direct download from their website. This script
processes the downloaded file if it exists, or prints instructions.
Download URL: https://www.smu.edu/dedman/research/institutes-and-centers/
              geothermal-lab/research/heatflow
Expected filename: data/ml/smuheatflow_raw.csv (or .xlsx)
═══════════════════════════════════════════════════════════════════════════
"""

import csv
import pathlib
import sys

ROOT     = pathlib.Path(__file__).parent.parent.parent
RAW_PATH = ROOT / "data" / "ml" / "smuheatflow_raw.csv"
OUT_PATH = ROOT / "data" / "ml" / "smuheatflow_clean.csv"

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Rock class k lookup [W/m·K] — from Clauser & Huenges (1995)
# Used when k is not directly measured (derived from Q/gradient instead)
# For validation only; the gradient-derived k is preferred when both Q and dT/dz known.
ROCK_K_LOOKUP = {
    "granite":     3.2,
    "basalt":      1.8,
    "limestone":   2.5,
    "sandstone":   2.8,
    "shale":       1.9,
    "quartzite":   5.5,
    "metamorphic": 2.5,
    "clay":        1.2,
    "alluvial":    1.8,
}

CONTINENTAL_US_BOUNDS = {
    "lat_min": 24.0, "lat_max": 50.0,
    "lon_min": -125.0, "lon_max": -66.0,
}


def in_conus(lat: float, lon: float) -> bool:
    b = CONTINENTAL_US_BOUNDS
    return (b["lat_min"] <= lat <= b["lat_max"] and
            b["lon_min"] <= lon <= b["lon_max"])


def process_smuheatflow(raw_path: pathlib.Path) -> None:
    """Parse SMU CSV and produce clean output with k and T_g derived."""
    rows_out = []

    with open(raw_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        print(f"Columns: {headers[:10]}")

        for row in reader:
            try:
                lat  = float(row.get("lat") or row.get("Lat") or row.get("latitude") or 0)
                lon  = float(row.get("lon") or row.get("Lon") or row.get("longitude") or 0)
                if not in_conus(lat, lon):
                    continue

                grad_s = (row.get("gradient") or row.get("Gradient_C_km") or "").strip()
                q_s    = (row.get("heatflow")  or row.get("HeatFlow_mWm2") or "").strip()
                k_s    = (row.get("k")          or row.get("Conductivity")  or "").strip()
                depth_s= (row.get("depth")      or row.get("Depth_m")       or "").strip()

                grad  = float(grad_s) if grad_s else None    # °C/km
                q     = float(q_s)    if q_s    else None    # mW/m²
                k     = float(k_s)    if k_s    else None    # W/m·K (direct)
                depth = float(depth_s)if depth_s else None   # m

                # Derive k from Fourier's law if not directly measured
                if k is None and grad and q and grad > 0:
                    k = (q * 1e-3) / (grad * 1e-3)    # W/m·K

                # Derive T_g at 150m depth (typical borehole depth for screening)
                T_surface_approx = 12.0    # will be replaced by NOAA value per location
                T_g_150 = T_surface_approx + (grad or 30.0) * 1e-3 * 150.0

                if k is None or not (0.3 <= k <= 8.0):
                    continue
                if grad is not None and not (5 <= grad <= 120):
                    continue

                rows_out.append({
                    "lat":              round(lat, 6),
                    "lon":              round(lon, 6),
                    "k_wmpk":           round(k, 3),
                    "T_g_150m_C":       round(T_g_150, 2),
                    "gradient_C_per_km":round(grad, 2) if grad else "",
                    "heatflow_mWm2":    round(q, 1) if q else "",
                    "depth_m":          round(depth, 0) if depth else "",
                    "source":           "SMU_heatflow",
                })
            except (ValueError, TypeError):
                continue

    if not rows_out:
        print("WARNING: No valid rows extracted. Check column names above vs. actual CSV headers.")
        return

    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out)} clean SMU records → {OUT_PATH}")


def main() -> None:
    if not RAW_PATH.exists():
        print("SMU Heat Flow database not found.")
        print(f"Expected at: {RAW_PATH}")
        print()
        print("To download:")
        print("  1. Visit https://www.smu.edu/dedman/research/institutes-and-centers/geothermal-lab/research/heatflow")
        print("  2. Download the North America heat flow database (CSV or Excel)")
        print(f"  3. Save as: {RAW_PATH}")
        print("  4. Re-run this script")
        sys.exit(0)

    print(f"Processing {RAW_PATH} …")
    process_smuheatflow(RAW_PATH)


if __name__ == "__main__":
    main()

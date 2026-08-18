"""
scripts/collect_deep_thermal.py
═══════════════════════════════════════════════════════════════════════════
Produce data/public/deep_thermal_by_county.csv — county-level k, α, T_g
for vertical closed-loop borehole sizing (30–150 m depth).

Two-track method for k and α:

  Track A — IDW from SMU quality A+B k measurements
    Applied when ≥3 SMU points exist within 200 km of county centroid.
    Source: data/public/smuhf_points.json
    IDW: power=2, search radius=200 km
    Reference: Blackwell, D.D., & Richards, M. (2004). Geothermal Map of
      North America. American Association of Petroleum Geologists.

  Track B — SGMC rock class → Clauser & Huenges (1995) median k
    Applied to counties with insufficient SMU coverage (<3 points in 200 km).
    Source: data/ml/sgmc_by_county.csv (run ml/data/collect_sgmc.py first)
    k medians: Clauser, C., & Huenges, E. (1995). Thermal conductivity of
      rocks and minerals. AGU Reference Shelf 3, pp. 105-126.
    α from k/ρCp: Banks, D. (2008). An Introduction to Thermogeology.
      Blackwell, Table A.1.
    Without SGMC: default k=2.5 W/m·K, α=0.098 m²/day (ASHRAE 2023,
      HVAC Applications Ch. 34, generic rock default)

T_g at 100 m borehole midpoint:
    T_g_100 = T_surface + 0.100 [km] × grad [°C/km]
    T_surface: from data/research/subsurface/horizontal_shallow_thermal_by_county.csv
      (Kusuda & Achenbach 1965 latitude approximation of mean annual ground temp)
    grad: IDW from SMU gradient measurements where ≥1 point in 300 km;
      national default 25 °C/km otherwise
      Reference: Blackwell & Richards (2004); Banks (2008) Section 2.3.

Output columns:
    county_fips, state_abbrev, county_name,
    k_wmpk, alpha_m2day, T_g_C,
    k_method,          — "SMU_IDW" | "SGMC_CH1995" | "default"
    T_g_method,        — "surface+SMU_grad" | "surface+default_grad"
    n_smu_pts_200km,   — SMU k points used in IDW (0 if Track B)
    rock_class_name    — SGMC class (blank if Track A or no SGMC)
═══════════════════════════════════════════════════════════════════════════
"""

import csv
import json
import math
import pathlib
import sys

ROOT        = pathlib.Path(__file__).parent.parent
PUBLIC_DIR  = ROOT / "data" / "public"
RESEARCH_DIR = ROOT / "data" / "research" / "subsurface"
ML_DIR      = ROOT / "data" / "ml"
OUT_CSV     = PUBLIC_DIR / "deep_thermal_by_county.csv"

# ── Clauser & Huenges (1995) AGU Ref Shelf 3, Table 1: k medians [W/m·K]
# ── Banks (2008) Table A.1: ρCp [MJ/m³·K] for each class
# α [m²/day] = k / (ρCp × 10^6) × 86400
_CH1995_K = {
    # class_id: (k_median [W/m·K], rho_Cp [MJ/m³·K])
    # Source: Clauser & Huenges (1995) Table 1; Banks (2008) Table A.1
    0: (0.60, 4.18),   # water/ice — water at 10°C
    1: (1.50, 2.00),   # alluvial/glacial — saturated unconsolidated (C&H range 0.2–2.2)
    2: (2.00, 2.40),   # clay/shale (C&H range 1.5–3.5; Banks median shale 1.8–2.3)
    3: (2.50, 2.20),   # limestone/carbonate (C&H range 2.5–4.0)
    4: (2.50, 2.00),   # sandstone (C&H range 1.5–5.5; wide — use midpoint)
    5: (3.00, 2.10),   # granite/felsic (C&H range 2.5–4.5)
    6: (1.70, 2.50),   # basalt/mafic (C&H range 1.0–3.0)
    7: (2.90, 2.20),   # metamorphic/gneiss (C&H range 1.5–4.5)
    8: (0.30, 1.20),   # coal/organic (C&H range 0.1–0.5)
    9: (2.50, 2.20),   # undifferentiated — ASHRAE (2023) generic rock default
}

# α [m²/day] = k [W/m·K] / (ρCp [MJ/m³·K] × 10^6) × 86400
def _alpha(k: float, rho_cp_mj: float) -> float:
    return k / (rho_cp_mj * 1e6) * 86400


# Pre-computed α table for convenience
_CH1995_ALPHA = {cid: _alpha(k, rho) for cid, (k, rho) in _CH1995_K.items()}

# Default geothermal gradient (US national mean)
# Reference: Blackwell & Richards (2004); Banks (2008) Section 2.3
_DEFAULT_GRAD_C_KM = 25.0  # °C/km


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _idw(query_lat: float, query_lon: float,
         points: list[tuple[float, float, float]],
         radius_km: float, power: float = 2.0) -> tuple[float | None, int]:
    """Inverse-distance-weighted interpolation.

    points: list of (lat, lon, value)
    Returns (idw_value, n_points_used) or (None, 0) if fewer than 3 in radius.
    """
    nearby = []
    for lat, lon, val in points:
        d = _haversine_km(query_lat, query_lon, lat, lon)
        if d <= radius_km:
            nearby.append((d, val))

    if len(nearby) < 3:
        return None, len(nearby)

    # Exact coincidence guard: if a point is within 0.01 km, return its value
    for d, val in nearby:
        if d < 0.01:
            return val, len(nearby)

    num = sum(v / (d ** power) for d, v in nearby)
    den = sum(1.0 / (d ** power) for d, v in nearby)
    return num / den, len(nearby)


def load_smu_points() -> tuple[list, list]:
    """Return (k_points, grad_points) where each is (lat, lon, value)."""
    smu_path = PUBLIC_DIR / "smuhf_points.json"
    if not smu_path.exists():
        print(f"WARNING: SMU heat flow file not found: {smu_path}")
        return [], []

    pts = json.loads(smu_path.read_text())["points"]
    k_pts   = [(p["lat"], p["lon"], p["k"])
               for p in pts if p.get("k") is not None]
    grad_pts = [(p["lat"], p["lon"], p["grad"])
                for p in pts if p.get("grad") is not None]
    return k_pts, grad_pts


def load_sgmc() -> dict[str, tuple[int, str]]:
    """Return {county_fips: (rock_class_id, rock_class_name)} from SGMC CSV."""
    sgmc_path = ML_DIR / "sgmc_by_county.csv"
    if not sgmc_path.exists():
        return {}
    result = {}
    with open(sgmc_path, newline="") as f:
        for row in csv.DictReader(f):
            fips = row["county_fips"].zfill(5)
            result[fips] = (int(row["rock_class_id"]), row["rock_class_name"])
    return result


def load_ssurgo_T_surface() -> dict[str, float]:
    """Build a {county_fips: T_surface_C} dict from SSURGO shallow CSV.

    T_g_C in the SSURGO CSV is the mean annual ground surface temperature
    estimated from latitude (Kusuda & Achenbach 1965 approximation).
    This is the best available T_surface estimate for most counties.

    Counties not in SSURGO (e.g., some CA, HI, AK counties) will use the
    latitude-based fallback in the main loop.
    """
    shallow_path = RESEARCH_DIR / "horizontal_shallow_thermal_by_county.csv"
    if not shallow_path.exists():
        return {}
    T_map = {}
    with open(shallow_path, newline="") as f:
        for row in csv.DictReader(f):
            fips = row["county_fips"].zfill(5)
            try:
                T_map[fips] = float(row["T_g_C"]) if row["T_g_C"] else None
            except ValueError:
                pass
    return {k: v for k, v in T_map.items() if v is not None}


def load_census_centroids() -> list[dict]:
    """Load all US counties from Census Gazetteer cache.

    Returns list of dicts with: county_fips, centroid_lat, centroid_lon,
    state_abbrev, county_name.

    Source: US Census Bureau (2020) County Gazetteer File.
    Run ml/data/collect_sgmc.py first to cache this file.
    """
    centroid_path = ML_DIR / "census_county_centroids.csv"
    if not centroid_path.exists():
        return []
    counties = []
    with open(centroid_path, newline="") as f:
        for row in csv.DictReader(f):
            counties.append({
                "county_fips":  row["county_fips"].zfill(5),
                "centroid_lat": float(row["centroid_lat"]),
                "centroid_lon": float(row["centroid_lon"]),
                "state_abbrev": row.get("state_abbrev", ""),
                "county_name":  row.get("county_name", ""),
            })
    return counties


def _latitude_T_surface(lat: float) -> float:
    """Approximate mean annual ground surface temperature from latitude.

    T_surface ≈ 50 - 0.88×lat (°C), calibrated to SSURGO T_g_C values.
    Fallback for counties without SSURGO T_g data.
    Reference: Kusuda, T., & Achenbach, P.R. (1965). Earth temperature and
      thermal diffusivity at selected stations in the United States.
      ASHRAE Transactions, 71, 61-74.
    """
    return max(5.0, 50.0 - 0.88 * lat)


def main() -> None:
    print("Loading data…")
    k_pts, grad_pts = load_smu_points()
    print(f"  SMU k points: {len(k_pts)}, gradient points: {len(grad_pts)}")

    sgmc_map = load_sgmc()
    if sgmc_map:
        print(f"  SGMC rock class: {len(sgmc_map)} counties")
    else:
        print("  SGMC data not available — Track B will use ASHRAE default k=2.5")
        print("  Run 'python ml/data/collect_sgmc.py' to enable SGMC fallback.")

    # Census Gazetteer is the authoritative county list (proper FIPS for all US counties)
    counties = load_census_centroids()
    if not counties:
        print("ERROR: Census Gazetteer not cached.")
        print("Run 'python ml/data/collect_sgmc.py' first.")
        sys.exit(1)
    print(f"  Census Gazetteer: {len(counties)} counties")

    # T_surface from SSURGO (Kusuda & Achenbach 1965 estimates); fallback = latitude formula
    T_surface_map = load_ssurgo_T_surface()
    print(f"  SSURGO T_surface values: {len(T_surface_map)} counties")

    IDW_RADIUS_KM  = 200.0
    GRAD_RADIUS_KM = 300.0

    rows = []
    track_counts = {"SMU_IDW": 0, "SGMC_CH1995": 0, "default": 0}

    for county in counties:
        fips = county["county_fips"]
        lat  = county["centroid_lat"]
        lon  = county["centroid_lon"]

        # T_surface: SSURGO lookup first, then latitude-based approximation
        T_surface = T_surface_map.get(fips) or _latitude_T_surface(lat)

        # ── k / α: Track A or B ──────────────────────────────────────────
        k_val = None
        alpha_val = None
        k_method = "default"
        n_smu = 0
        rock_class_name = ""

        if lat is not None and lon is not None and k_pts:
            k_idw, n_smu = _idw(lat, lon, k_pts, IDW_RADIUS_KM)
            if k_idw is not None:
                k_val = round(k_idw, 3)
                # α: for IDW k we derive α assuming median ρCp = 2.2 MJ/m³·K
                # (Banks 2008 Table A.1 generic rock value; used when rock class unknown)
                alpha_val = round(_alpha(k_val, 2.2), 4)
                k_method = "SMU_IDW"
                track_counts["SMU_IDW"] += 1

        if k_val is None:
            # Track B: SGMC → C&H 1995
            if fips in sgmc_map:
                class_id, rock_class_name = sgmc_map[fips]
                k_val, _ = _CH1995_K[class_id]
                alpha_val = round(_CH1995_ALPHA[class_id], 4)
                k_method = "SGMC_CH1995"
                track_counts["SGMC_CH1995"] += 1
            else:
                # Fallback: ASHRAE (2023) HVAC Applications Ch. 34 generic default
                k_val, rho_cp = _CH1995_K[9]
                alpha_val = round(_CH1995_ALPHA[9], 4)
                k_method = "default"
                track_counts["default"] += 1

        # ── T_g at 100 m borehole midpoint ───────────────────────────────
        # T_g_100 = T_surface + 0.100 km × grad [°C/km]
        # Reference: Banks (2008) Section 2.3 — geothermal gradient correction
        T_g_method = "surface+default_grad"
        grad = None
        if lat is not None and lon is not None and grad_pts:
            grad_idw, _ = _idw(lat, lon, grad_pts, GRAD_RADIUS_KM, power=2.0)
            if grad_idw is not None:
                grad = grad_idw
                T_g_method = "surface+SMU_grad"
        if grad is None:
            grad = _DEFAULT_GRAD_C_KM

        if T_surface is not None:
            T_g_100 = round(T_surface + 0.100 * grad, 2)
        else:
            T_g_100 = None

        rows.append({
            "county_fips":       fips,
            "state_abbrev":      county.get("state_abbrev", ""),
            "county_name":       county.get("county_name", ""),
            "k_wmpk":            k_val,
            "alpha_m2day":       alpha_val,
            "T_g_C":             T_g_100,
            "k_method":          k_method,
            "T_g_method":        T_g_method,
            "n_smu_pts_200km":   n_smu,
            "rock_class_name":   rock_class_name,
        })

    fieldnames = [
        "county_fips", "state_abbrev", "county_name",
        "k_wmpk", "alpha_m2day", "T_g_C",
        "k_method", "T_g_method", "n_smu_pts_200km", "rock_class_name",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} counties → {OUT_CSV}")
    print(f"\nk method breakdown:")
    for method, count in sorted(track_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(rows) if rows else 0
        print(f"  {method:20s}: {count:5d}  ({pct:.1f}%)")

    if not counties:
        print("\nNOTE: No county centroids available — SMU IDW was skipped.")
        print("Run 'python ml/data/collect_sgmc.py' to download Census centroids,")
        print("then re-run this script for Track A (IDW) coverage.")


if __name__ == "__main__":
    main()

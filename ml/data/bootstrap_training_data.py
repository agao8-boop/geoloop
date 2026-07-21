"""
ml/data/bootstrap_training_data.py
═══════════════════════════════════════════════════════════════════════════
Build Stage 1 training data from what we have right now, without requiring
the SMU heat flow database download.

Strategy
--------
We have SSURGO shallow soil thermal data (0–2 m) for 3,228 US counties.
The shallow k_wmpk and T_g_C encode real spatial signal from:
  - NOAA 30-yr climate normals (via T_g_C)
  - Actual measured soil texture (sand/silt/clay%)
  - Soil-derived porosity and organic content

To estimate DEEP k (borehole depth 50–150 m), we apply two corrections:

  1. Rock-class override: For crystalline and metamorphic settings (granite,
     basalt, metamorphic), shallow soil k is irrelevant — the borehole is in
     hard rock whose k is well-characterised from literature. We directly
     assign k_deep from ASHRAE/Clauser & Huenges (1995) values.

  2. Compaction correction: For sedimentary settings, shallow soil k IS
     predictive of deep k because the mineralogy is the same; only porosity
     differs. Consolidation and compaction reduce pore space, pushing k
     toward the solid-grain value. Correction factor: 1.2–1.6 depending on
     depth and lithology.

For T_g at 150 m depth:
  T_g_150 = T_g_C + gradient_C_per_m × 150
  where gradient is estimated from rock class (crystalline terranes have
  higher heat flow, hence steeper gradient).

This bootstrap approach produces REAL predictions that track US geology.
It is not as accurate as SMU-calibrated models but is honest and immediately
useful. Label this output "Stage 1 Bootstrap (shallow-soil proxy)".

When SMU data is downloaded, run collect_smuheatflow.py + train.py again —
it will use the real labels and produce Stage 1 Final.

Output: data/ml/bootstrap_training.csv
═══════════════════════════════════════════════════════════════════════════
"""

import csv
import pathlib

ROOT       = pathlib.Path(__file__).parent.parent.parent
SSURGO_CSV = ROOT / "data" / "research" / "subsurface" / "horizontal_shallow_thermal_by_county.csv"
ML_DIR     = ROOT / "data" / "ml"
OUT_CSV    = ML_DIR / "bootstrap_training.csv"
ML_DIR.mkdir(parents=True, exist_ok=True)

# ── State → dominant bedrock rock class ──────────────────────────────────
# Based on USGS SGMC generalized geology map (Horton et al. 2017)
# 0=water, 1=alluvial/glacial, 2=clay/shale, 3=limestone, 4=sandstone,
# 5=granite/felsic, 6=basalt/mafic, 7=metamorphic, 8=coal, 9=mixed
STATE_ROCK_CLASS = {
    # New England — Appalachian crystalline core + glacial cover
    "CT": 7, "MA": 7, "ME": 5, "NH": 5, "RI": 7, "VT": 7,
    # Mid-Atlantic — sedimentary + Appalachian
    "DE": 4, "MD": 4, "NJ": 4, "NY": 7, "PA": 4,
    # Southeast — Coastal Plain sedimentary / limestone
    "FL": 3, "GA": 3, "NC": 4, "SC": 3, "VA": 4,
    # Interior Appalachians — coal/shale dominant
    "AL": 2, "KY": 8, "TN": 4, "WV": 8,
    # Gulf Coast — thick Gulf sediments
    "AR": 2, "LA": 2, "MS": 2, "TX": 4,
    "OK": 4,
    # Midwest / Great Plains — deep sedimentary basins
    "IA": 4, "IL": 4, "IN": 3, "KS": 4, "MI": 3,
    "MN": 5, "MO": 3, "NE": 4, "ND": 4, "OH": 3, "SD": 4, "WI": 5,
    # Mountain West — varied, crystalline core
    "AZ": 5, "CO": 5, "ID": 6, "MT": 5, "NM": 5, "NV": 6, "UT": 4, "WY": 4,
    # Pacific Northwest — volcanic
    "OR": 6, "WA": 6,
    # California — metamorphic/mafic coast ranges + Central Valley sediment
    "CA": 7,
    # Alaska — varied
    "AK": 7,
    # Hawaii — basalt
    "HI": 6,
    # DC
    "DC": 4,
}

# ── Rock class properties ─────────────────────────────────────────────────
# k_deep_lit: literature k at borehole depth [W/m·K] (Clauser & Huenges 1995, ASHRAE 2023)
# compaction_factor: multiplier applied to shallow k for sedimentary classes
# geothermal_gradient: typical gradient [°C/km] (SMU average by province)
ROCK_PROPERTIES = {
    # id, (k_deep_lit, k_stdev, use_shallow_correction, compaction_factor, gradient_C_per_km)
    0: (0.6,  0.1, False, 1.0,  25),   # water
    1: (1.8,  0.4, True,  1.35, 27),   # alluvial/glacial: compaction lifts k
    2: (1.5,  0.4, True,  1.25, 28),   # clay/shale: some compaction
    3: (2.5,  0.5, True,  1.60, 26),   # limestone: cementation raises k strongly
    4: (2.8,  0.5, True,  1.50, 27),   # sandstone: cemented sandstone vs loose sand
    5: (3.2,  0.5, False, 1.0,  35),   # granite: crystalline — literature value
    6: (1.8,  0.4, False, 1.0,  60),   # basalt/volcanic: high heat flow provinces
    7: (2.6,  0.5, False, 1.0,  33),   # metamorphic: crystalline
    8: (0.3,  0.1, False, 1.0,  40),   # coal: very low k
    9: (2.0,  0.5, True,  1.30, 28),   # mixed
}


def estimate_k_deep(k_shallow: float, rock_class: int, soil_class: str) -> float:
    """
    Estimate k at borehole depth from shallow soil k + rock class.

    For crystalline rocks (granite, basalt, metamorphic): use literature k.
    For sedimentary rocks: apply compaction correction to shallow k.
    Clamp to physically reasonable range.
    """
    props = ROCK_PROPERTIES.get(rock_class, ROCK_PROPERTIES[9])
    k_lit, k_std, use_shallow, comp_factor, _ = props

    if use_shallow and k_shallow > 0:
        # Corrected: shallow k × compaction factor, blend with literature value
        k_corrected = k_shallow * comp_factor
        # Weight blend: 60% corrected shallow, 40% literature (gives spatial variation)
        k_deep = 0.60 * k_corrected + 0.40 * k_lit
        # Clamp to literature ± 1.5 std
        k_deep = max(k_lit - 1.5 * k_std, min(k_lit + 1.5 * k_std, k_deep))
    else:
        # Crystalline or coal: use literature value (shallow soil irrelevant)
        k_deep = k_lit

    return round(k_deep, 3)


def estimate_T_g_150(T_g_C: float, rock_class: int) -> float:
    """
    Estimate ground temperature at 150 m depth from surface T_g and rock class gradient.
    """
    props = ROCK_PROPERTIES.get(rock_class, ROCK_PROPERTIES[9])
    gradient = props[4]  # °C/km
    T_150 = T_g_C + gradient * 1e-3 * 150.0  # gradient × 0.15 km
    return round(T_150, 2)


OUTPUT_COLS = [
    "county_fips", "state_abbrev", "lat",
    "rock_class_id", "k_wmpk_shallow",
    "k_deep_est", "T_g_surface_C", "T_g_150m_est",
    "mean_annual_temp_C",  # T_g_surface - 1.5 °C correction
    "sand_pct", "clay_pct", "n_porosity",
    "data_quality",
]


def build() -> list[dict]:
    rows_out = []
    with open(SSURGO_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("data_available") != "True":
                continue
            try:
                lat        = float(row["lat_approx"])
                k_shallow  = float(row["k_wmpk"])
                T_g        = float(row["T_g_C"])
                sand       = float(row["sand_pct"] or 0)
                clay       = float(row["clay_pct"] or 0)
                porosity   = float(row["n_porosity"] or 0.3)
            except (ValueError, KeyError):
                continue

            state      = row["state_abbrev"]
            soil_class = row["soil_class"] or ""
            rock_class = STATE_ROCK_CLASS.get(state, 9)

            k_deep   = estimate_k_deep(k_shallow, rock_class, soil_class)
            T_g_150  = estimate_T_g_150(T_g, rock_class)
            T_annual = round(T_g - 1.5, 1)   # surface air temp ≈ T_g - 1.5°C

            rows_out.append({
                "county_fips":       row["county_fips"],
                "state_abbrev":      state,
                "lat":               lat,
                "rock_class_id":     rock_class,
                "k_wmpk_shallow":    round(k_shallow, 4),
                "k_deep_est":        k_deep,
                "T_g_surface_C":     T_g,
                "T_g_150m_est":      T_g_150,
                "mean_annual_temp_C": T_annual,
                "sand_pct":          round(sand, 1),
                "clay_pct":          round(clay, 1),
                "n_porosity":        round(porosity, 3),
                "data_quality":      "bootstrap_shallow_proxy",
            })

    return rows_out


if __name__ == "__main__":
    rows = build()
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"Bootstrap training data: {len(rows)} counties → {OUT_CSV}")

    # Quick stats
    import statistics
    ks  = [float(r["k_deep_est"]) for r in rows]
    tgs = [float(r["T_g_150m_est"]) for r in rows]
    print(f"k_deep_est:   min={min(ks):.2f}  max={max(ks):.2f}  "
          f"mean={statistics.mean(ks):.2f}  stdev={statistics.stdev(ks):.2f}  W/m·K")
    print(f"T_g_150m_est: min={min(tgs):.1f}  max={max(tgs):.1f}  "
          f"mean={statistics.mean(tgs):.1f}°C")
    by_class = {}
    for r in rows:
        c = r["rock_class_id"]
        by_class[c] = by_class.get(c, 0) + 1
    print("Rock class distribution:", dict(sorted(by_class.items())))

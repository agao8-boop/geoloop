"""
ml/data/collect_sgmc.py
═══════════════════════════════════════════════════════════════════════════
Assign a simplified rock class to each US county using the Macrostrat API.

Macrostrat (macrostrat.org) provides geological unit data at any lat/lon
point via a REST API. For the US, the underlying source is the USGS State
Geologic Map Compilation (SGMC, Horton et al. 2017), the same authoritative
national bedrock geology map we would use from the raw shapefiles — so the
scientific validity is identical.

Each county centroid is queried against the 1:500,000 scale ("medium")
geological map layer. The dominant lithology is parsed and mapped to one
of 10 simplified rock classes following Clauser & Huenges (1995).

Run from project root:
    python ml/data/collect_sgmc.py

Output: data/ml/sgmc_by_county.csv
  Columns: county_fips, rock_class_id, rock_class_name, dominant_lithology,
           centroid_lat, centroid_lon

Supports resume: if the output CSV already exists with partial results,
only missing counties are queried.

References:
  Peters, S.E., et al. (2018). Macrostrat: A platform for geological data
    integration and deep-time earth crust research. doi:10.1130/abs/2018AM-320179
  Horton, J.D. (2017). The State Geologic Map Compilation (SGMC). USGS.
    doi:10.5066/F7WH2N65
  Clauser, C., & Huenges, E. (1995). Thermal conductivity of rocks and
    minerals. AGU Reference Shelf 3, pp. 105-126.
═══════════════════════════════════════════════════════════════════════════
"""

import csv
import io
import pathlib
import sys
import time
import urllib.request
import urllib.parse
import zipfile

ROOT    = pathlib.Path(__file__).parent.parent.parent
ML_DIR  = ROOT / "data" / "ml"
OUT_CSV = ML_DIR / "sgmc_by_county.csv"
ML_DIR.mkdir(parents=True, exist_ok=True)

_MACROSTRAT_URL = (
    "https://macrostrat.org/api/v2/geologic_units/map"
    "?lat={lat}&lng={lon}&scale=medium&response=short"
)

# ── Rock class mapping ────────────────────────────────────────────────────
# Maps lithology keywords → 10-class scheme.
# Classes follow Clauser & Huenges (1995) AGU Handbook Table 1 groupings.
LITH_TO_CLASS = {
    # class 1: alluvial/glacial (unconsolidated sediment)
    "alluvial":       1, "glacial":        1, "colluvial":      1,
    "fluvial":        1, "lacustrine":      1, "eolian":         1,
    "unconsolidated": 1, "till":            1, "gravel":         1,
    "sand":           1,

    # class 2: clay/shale (fine-grained sedimentary)
    "shale":          2, "mudstone":       2, "claystone":      2,
    "argillite":      2, "siltstone":      2, "marl":           2,
    "clay":           2, "mudrock":        2,

    # class 3: limestone/carbonate
    "limestone":      3, "dolostone":      3, "carbonate":      3,
    "chalk":          3, "dolomite":       3,

    # class 4: sandstone (coarse-grained sedimentary)
    "sandstone":      4, "conglomerate":   4, "arkose":         4,
    "quartzite":      4, "graywacke":      4, "wacke":          4,

    # class 5: granite/felsic igneous
    "granite":        5, "granodiorite":   5, "rhyolite":       5,
    "felsic":         5, "tonalite":       5, "trondhjemite":   5,
    "syenite":        5, "monzonite":      5, "granitic":       5,
    "dacite":         5,

    # class 6: basalt/mafic igneous
    "basalt":         6, "gabbro":         6, "diabase":        6,
    "mafic":          6, "andesite":       6, "diorite":        6,
    "pyroclastic":    6, "volcanic":       6, "tuff":           6,
    "ultramafic":     6, "peridotite":     6,

    # class 7: metamorphic
    "metamorphic":    7, "schist":         7, "gneiss":         7,
    "phyllite":       7, "slate":          7, "migmatite":      7,
    "amphibolite":    7, "crystalline":    7, "hornfels":       7,

    # class 8: coal/organic
    "coal":           8, "peat":           8, "lignite":        8,

    # class 0: water/ice
    "water":          0, "ice":            0, "lake":           0,
}

CLASS_NAMES = {
    0: "water_ice",
    1: "alluvial_glacial",
    2: "clay_shale",
    3: "limestone_carbonate",
    4: "sandstone",
    5: "granite_felsic",
    6: "basalt_mafic",
    7: "metamorphic",
    8: "coal_organic",
    9: "undifferentiated",
}


def lith_to_class_id(lith_str: str) -> int:
    """Map a lithology string to a simplified rock class ID."""
    if not lith_str:
        return 9
    lith_lower = lith_str.lower()
    for keyword, class_id in LITH_TO_CLASS.items():
        if keyword in lith_lower:
            return class_id
    return 9  # undifferentiated


def parse_macrostrat_lith(lith_field: str) -> str:
    """Extract dominant lithology from Macrostrat lith field.

    Macrostrat returns lith as e.g.:
      'Major:{dolostone,limestone}, Minor:{shale}'
    We extract the Major lithologies and return the first recognizable one.
    """
    if not lith_field:
        return ""
    # Pull the Major:{...} block
    lith_lower = lith_field.lower()
    major_start = lith_lower.find("major:{")
    if major_start >= 0:
        major_end = lith_lower.find("}", major_start)
        if major_end >= 0:
            major_str = lith_field[major_start + 7:major_end]
            # Return the whole block for keyword matching
            return major_str
    # No Major block — return the full string
    return lith_field


def query_macrostrat(lat: float, lon: float) -> tuple[str, str]:
    """Query Macrostrat API for dominant lithology at a lat/lon point.

    Returns (dominant_lithology_string, unit_name).
    Returns ("", "") on API error or no data.
    """
    url = _MACROSTRAT_URL.format(lat=lat, lon=lon)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "GeoSiteAdvisor/1.0 (CEE299 research)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            d = json.load(resp)
    except Exception:
        return "", ""

    data = d.get("success", {}).get("data", [])
    if not data:
        return "", ""

    # Take the first (most relevant) unit
    unit = data[0]
    lith_raw  = unit.get("lith", "")
    unit_name = unit.get("name", "")
    dominant  = parse_macrostrat_lith(lith_raw)
    return dominant, unit_name


def get_county_centroids() -> "pd.DataFrame":
    """Download Census 2020 Gazetteer county centroids (~650 KB zip).

    Returns a DataFrame with columns: county_fips, centroid_lat, centroid_lon,
    state_abbrev, county_name.
    """
    import pandas as pd

    cache_path = ML_DIR / "census_county_centroids.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, dtype={"county_fips": str})
        if "state_abbrev" in df.columns:
            return df
        # Old cache without state_abbrev — delete and re-download
        cache_path.unlink()

    url = (
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
        "2020_Gazetteer/2020_Gaz_counties_national.zip"
    )
    print("Downloading Census 2020 county centroids (~650 KB)…")
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        txt_name = [n for n in zf.namelist() if n.endswith(".txt")][0]
        content = zf.read(txt_name).decode("utf-8")

    df = pd.read_csv(io.StringIO(content), sep="\t", dtype={"GEOID": str})
    df.columns = df.columns.str.strip()
    df = df.rename(columns={
        "GEOID":    "county_fips",
        "INTPTLAT": "centroid_lat",
        "INTPTLONG": "centroid_lon",
        "USPS":     "state_abbrev",
        "NAME":     "county_name",
    })
    df["county_fips"] = df["county_fips"].str.zfill(5)

    keep = [c for c in ["county_fips", "centroid_lat", "centroid_lon",
                         "state_abbrev", "county_name"] if c in df.columns]
    result = df[keep].copy()
    result.to_csv(cache_path, index=False)
    print(f"Cached {len(result)} county centroids → {cache_path}")
    return result


def load_existing_results() -> dict[str, dict]:
    """Load partially-completed output CSV for resume support."""
    if not OUT_CSV.exists():
        return {}
    done = {}
    with open(OUT_CSV, newline="") as f:
        for row in csv.DictReader(f):
            done[row["county_fips"]] = row
    return done


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas not installed.")
        sys.exit(1)

    centroids = get_county_centroids()
    print(f"Loaded {len(centroids)} county centroids")

    # Resume support: skip counties already in output CSV
    existing = load_existing_results()
    if existing:
        print(f"Resuming: {len(existing)} counties already processed, "
              f"{len(centroids) - len(existing)} remaining")

    fieldnames = [
        "county_fips", "rock_class_id", "rock_class_name",
        "dominant_lithology", "unit_name", "centroid_lat", "centroid_lon",
    ]

    # Open in append mode if resuming, write mode if starting fresh
    mode = "a" if existing else "w"
    with open(OUT_CSV, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not existing:
            writer.writeheader()

        total = len(centroids)
        processed = len(existing)
        errors = 0

        for _, row in centroids.iterrows():
            fips = str(row["county_fips"]).zfill(5)
            if fips in existing:
                continue

            lat = float(row["centroid_lat"])
            lon = float(row["centroid_lon"])

            dominant_lith, unit_name = query_macrostrat(lat, lon)
            if not dominant_lith:
                errors += 1

            class_id   = lith_to_class_id(dominant_lith)
            class_name = CLASS_NAMES[class_id]

            writer.writerow({
                "county_fips":       fips,
                "rock_class_id":     class_id,
                "rock_class_name":   class_name,
                "dominant_lithology": dominant_lith,
                "unit_name":         unit_name,
                "centroid_lat":      lat,
                "centroid_lon":      lon,
            })
            f.flush()

            processed += 1
            if processed % 50 == 0 or processed == total:
                pct = 100 * processed / total
                print(f"  {processed}/{total} ({pct:.0f}%) — last: {fips} → {class_name}")

            time.sleep(0.12)  # ~8 req/s, polite for a research API

    print(f"\nDone. {processed} counties written → {OUT_CSV}")
    if errors:
        print(f"  {errors} counties returned no lithology data (class 9 = undifferentiated)")

    # Print class distribution
    results = list(csv.DictReader(open(OUT_CSV)))
    from collections import Counter
    dist = Counter(r["rock_class_name"] for r in results)
    print("\nRock class distribution:")
    for cls, n in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {cls:25s}: {n:5d}  ({100*n/len(results):.1f}%)")


if __name__ == "__main__":
    main()

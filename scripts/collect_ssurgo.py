"""
scripts/collect_ssurgo.py
═════════════════════════════════════════════════════════════════════════════
DEVELOPER PIPELINE — HORIZONTAL CLOSED-LOOP REFERENCE DATA (0–200 cm depth)
Not called by the user tool. Not used for vertical borehole sizing.

SCOPE DECISION (Week 2, 2026-06-25):
  SSURGO surveys only cover the pedological soil profile to ~200 cm (2 m).
  This depth is INSUFFICIENT for vertical closed-loop geothermal systems
  (which require thermal properties to 30–150 m depth).
  This dataset is retained as reference for:
    - Horizontal closed-loop systems (buried at 1.2–2 m depth)
    - Shallow surface condition characterization
    - Future horizontal-loop feasibility screening
  For vertical borehole sizing, see scripts/collect_deep_thermal.py (TODO).

Queries USGS SSURGO Soil Data Access (SDA) API for every US county, applies
Côté & Konrad (2005) to derive soil thermal conductivity k and diffusivity α,
and writes the result to:
  data/research/subsurface/horizontal_shallow_thermal_by_county.csv

Run from project root:
    python scripts/collect_ssurgo.py [--state IL] [--resume] [--limit 20]

Estimated runtime: 2–4 hours for all ~3,200 US continental counties.
Progress printed every 10 counties; safe to interrupt and resume with --resume.
═════════════════════════════════════════════════════════════════════════════
"""

import argparse
import csv
import json
import math
import pathlib
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT     = pathlib.Path(__file__).parent.parent
OUT_DIR  = ROOT / "data" / "research" / "subsurface"
LOG_DIR  = ROOT / "data" / "research" / "collection_logs"
OUT_CSV  = OUT_DIR / "horizontal_shallow_thermal_by_county.csv"

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── SSURGO SDA endpoint ────────────────────────────────────────────────────
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"

# SSL context — macOS Python often lacks CA bundle; disable verification
# for local developer scripts (never used in production Flask routes).
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ── State abbreviation → FIPS ──────────────────────────────────────────────
STATE_ABBREV_TO_FIPS = {
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09",
    "DE":"10","FL":"12","GA":"13","HI":"15","ID":"16","IL":"17","IN":"18",
    "IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24","MA":"25",
    "MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31","NV":"32",
    "NH":"33","NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38","OH":"39",
    "OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46","TN":"47",
    "TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54","WI":"55",
    "WY":"56","DC":"11",
}

# ── Provisional S_r by state (degree of saturation) ──────────────────────
# Based on mean annual precipitation / aridity classification.
# Open Question Q1.1: replace with Saxton-Rawls field capacity method.
_HUMID   = {"AL","AR","CT","DE","FL","GA","IL","IN","IA","KY","LA","ME","MD",
             "MA","MI","MN","MS","MO","NH","NJ","NY","NC","OH","PA","RI","SC",
             "TN","VT","VA","WV","WI","DC"}
_SEMI    = {"AZ","CO","ID","KS","MT","NE","ND","OK","OR","SD","TX","UT","WA","WY"}
_ARID    = {"CA","NV","NM"}

def _S_r_for_state(state_abbrev: str) -> float:
    if state_abbrev in _HUMID: return 0.75
    if state_abbrev in _ARID:  return 0.35
    return 0.55  # semi-arid default

# ── Provisional T_g from latitude ────────────────────────────────────────
# T_g ≈ mean annual air temperature [°C] (Kusuda & Achenbach 1965 approx).
# Uses county centroid latitude queried from SSURGO.
def _T_g_from_lat(lat: float) -> float:
    # Linear approximation calibrated to US climate stations:
    #   lat≈26 (Miami)   → ~24°C
    #   lat≈38 (DC)      → ~14°C
    #   lat≈47 (Seattle) → ~11°C
    return max(2.0, 38.5 - 0.62 * lat)

# ── Côté & Konrad (2005) thermal conductivity ──────────────────────────────
_CK_PARAMS = {
    # soil_class: (chi, eta, kappa_unfrozen)
    "coarse_sand":      (1.70, 1.80, 4.50),
    "medium_fine_sand": (0.75, 1.20, 3.55),
    "silt_clay":        (0.75, 1.20, 1.90),
    "peat":             (0.30, 0.87, 0.60),
}

def _classify_soil(sand_pct: float, silt_pct: float,
                   clay_pct: float, om_pct: float) -> str:
    if om_pct > 30:              return "peat"
    if sand_pct >= 85:           return "coarse_sand"
    if sand_pct >= 50:           return "medium_fine_sand"
    return "silt_clay"

def cote_konrad(sand_pct: float, silt_pct: float, clay_pct: float,
                rho_d: float, om_pct: float, S_r: float) -> dict:
    """Return k [W/m·K], alpha [m²/day], and intermediate values.

    Implements eqs. 13, 14, 28 from Côté & Konrad (2005),
    Can. Geotech. J. 42:443–458.
    """
    soil_class = _classify_soil(sand_pct, silt_pct, clay_pct, om_pct)
    chi, eta, kappa = _CK_PARAMS[soil_class]

    # Quartz fraction (Johansen 1975 approximation from sand content)
    q = (sand_pct / 100.0) * 0.8

    # Porosity  (eq. 14)
    rho_s = 2.65  # solid particle density [g/cm³]
    n = 1.0 - rho_d / rho_s

    # k of solid particles  (Johansen 1975, eq. 27)
    if q > 0.20:
        k_s = (7.7 ** q) * (2.0 ** (1.0 - q))
    else:
        k_s = (7.7 ** q) * (3.0 ** (1.0 - q))

    # Saturated thermal conductivity  (eq. 14)
    k_w   = 0.60           # water [W/m·K]
    k_sat = (k_s ** (1.0 - n)) * (k_w ** n)

    # Dry thermal conductivity  (eq. 28)
    k_dry = chi * (10.0 ** (-eta * n))

    # Kersten number  (eq. 13)
    k_e = (kappa * S_r) / (1.0 + (kappa - 1.0) * S_r)

    # Final thermal conductivity
    k = (k_sat - k_dry) * k_e + k_dry

    # Thermal diffusivity [m²/day]
    c_p   = 750.0       # soil specific heat [J/kg·K]
    rho_d_si = rho_d * 1000.0  # g/cm³ → kg/m³
    alpha = k / (rho_d_si * c_p) * 86400.0

    return {
        "soil_class": soil_class,
        "q_quartz":   round(q, 4),
        "n_porosity": round(n, 4),
        "k_s":        round(k_s, 4),
        "k_sat":      round(k_sat, 4),
        "k_dry":      round(k_dry, 4),
        "k_e":        round(k_e, 4),
        "k_wmpk":     round(k, 4),
        "alpha_m2day":round(alpha, 5),
    }

# ── SDA helpers ───────────────────────────────────────────────────────────
def _sda_post(query: str) -> list[list]:
    payload = json.dumps({"query": query, "format": "JSON"}).encode()
    req = urllib.request.Request(
        SDA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as r:
        result = json.loads(r.read())
    return result.get("Table", [])

def _fetch_all_areas(state_filter: str | None) -> list[tuple[str, str]]:
    """Return [(areasymbol, areaname)] for continental US counties."""
    where = "areasymbol NOT LIKE 'US%' AND areasymbol NOT LIKE 'PR%' " \
            "AND areasymbol NOT LIKE 'VI%'"
    if state_filter:
        where += f" AND areasymbol LIKE '{state_filter.upper()}%'"
    rows = _sda_post(
        f"SELECT areasymbol, areaname FROM legend WHERE {where} ORDER BY areasymbol"
    )
    return [(r[0], r[1]) for r in rows]

def _query_county(areasymbol: str) -> dict | None:
    """Return raw SSURGO soil properties for one county area symbol.

    Queries weighted-average horizon properties over 0–200 cm depth.
    Returns None if the county has no usable data.

    UPGRADE NOTE: To switch to census-tract resolution, replace this
    function's body with a spatial query that uses the tract's centroid
    (lat, lon) in the SDA `SDA_Get_Mukey_from_intersection_with_WktWgs84`
    function. The return dict schema stays identical.
    """
    query = (
        "SELECT AVG(ch.sandtotal_r), AVG(ch.silttotal_r), AVG(ch.claytotal_r),"
        " AVG(ch.dbthirdbar_r), AVG(ch.om_r), COUNT(*)"
        " FROM component c"
        " JOIN chorizon ch ON c.cokey = ch.cokey"
        " JOIN mapunit mu  ON c.mukey = mu.mukey"
        " JOIN legend l    ON mu.lkey = l.lkey"
        f" WHERE l.areasymbol = '{areasymbol}'"
        " AND ch.hzdept_r BETWEEN 0 AND 200"
        " AND ch.sandtotal_r IS NOT NULL"
    )
    rows = _sda_post(query)
    if not rows or rows[0][0] is None:
        return None
    row = rows[0]
    return {
        "sand_pct":      float(row[0]),
        "silt_pct":      float(row[1]) if row[1] else 0.0,
        "clay_pct":      float(row[2]) if row[2] else 0.0,
        "rho_d_g_cm3":   float(row[3]),
        "om_pct":        float(row[4]) if row[4] else 0.0,
        "horizon_count": int(float(row[5])),
    }

# Approximate state centroid latitudes for T_g estimation.
# Avoids an extra SSURGO API call per county.
_STATE_LAT = {
    "AL":32.8,"AZ":34.3,"AR":34.8,"CA":37.2,"CO":39.0,"CT":41.6,
    "DE":39.0,"FL":28.6,"GA":32.2,"ID":44.5,"IL":40.0,"IN":40.3,
    "IA":42.0,"KS":38.5,"KY":37.5,"LA":30.8,"ME":45.4,"MD":39.0,
    "MA":42.2,"MI":44.3,"MN":46.4,"MS":32.7,"MO":38.4,"MT":47.0,
    "NE":41.5,"NV":39.5,"NH":43.7,"NJ":40.1,"NM":34.5,"NY":42.9,
    "NC":35.6,"ND":47.5,"OH":40.4,"OK":35.6,"OR":44.0,"PA":40.9,
    "RI":41.7,"SC":33.9,"SD":44.4,"TN":35.9,"TX":31.5,"UT":39.5,
    "VT":44.0,"VA":37.5,"WA":47.4,"WV":38.6,"WI":44.5,"WY":43.0,
    "DC":38.9,
}

def _county_lat(areasymbol: str) -> float | None:
    """Return approximate latitude for a county (from state centroid table)."""
    state = areasymbol[:2].upper()
    return _STATE_LAT.get(state)

# ── CSV helpers ───────────────────────────────────────────────────────────
OUTPUT_COLS = [
    "county_fips", "state_abbrev", "county_fips_3", "county_name",
    "areasymbol",
    "sand_pct", "silt_pct", "clay_pct", "rho_d_g_cm3", "om_pct",
    "horizon_count", "lat_approx",
    "soil_class", "q_quartz", "n_porosity", "k_s", "k_sat", "k_dry", "k_e",
    "k_wmpk", "alpha_m2day",
    "S_r_used", "T_g_C",
    "data_available", "queried_at",
]

def _load_existing(path: pathlib.Path) -> set[str]:
    """Return set of county_fips already in the output CSV (for --resume)."""
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return {row["county_fips"] for row in reader}

# ── Main ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Collect SSURGO county soil data")
    parser.add_argument("--state",  help="Process only this state abbrev, e.g. IL")
    parser.add_argument("--resume", action="store_true",
                        help="Skip counties already in output CSV")
    parser.add_argument("--limit",  type=int, default=0,
                        help="Stop after N counties (0 = no limit)")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"ssurgo_run_{ts}.log"
    log = open(log_path, "w", buffering=1)

    def emit(msg: str) -> None:
        print(msg)
        log.write(msg + "\n")

    emit(f"[{ts}] collect_ssurgo.py — start")
    emit(f"state filter: {args.state or 'all continental US'}")
    emit(f"resume: {args.resume}  limit: {args.limit or 'none'}")

    # Load existing results for resume
    done = _load_existing(OUT_CSV) if args.resume else set()
    emit(f"Skipping {len(done)} already-collected counties")

    # Fetch full county list
    emit("Fetching SSURGO survey area list…")
    areas = _fetch_all_areas(args.state)
    emit(f"{len(areas)} survey areas found")

    # Open output CSV (append if resuming, write-new otherwise)
    mode = "a" if args.resume and OUT_CSV.exists() else "w"
    csv_file = open(OUT_CSV, mode, newline="")
    writer   = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLS)
    if mode == "w":
        writer.writeheader()

    ok = err = skipped = 0
    for i, (areasymbol, areaname) in enumerate(areas, 1):

        if args.limit and ok >= args.limit:
            break

        # Parse areasymbol → state abbrev + 3-digit county FIPS
        state_abbrev = areasymbol[:2].upper()
        county_3     = areasymbol[2:]
        state_fips   = STATE_ABBREV_TO_FIPS.get(state_abbrev)
        if not state_fips or not county_3.isdigit():
            skipped += 1
            continue

        county_fips = state_fips + county_3

        if county_fips in done:
            skipped += 1
            continue

        # Query SSURGO
        try:
            soil = _query_county(areasymbol)
        except Exception as exc:
            emit(f"  ERROR {areasymbol}: {exc}")
            err += 1
            time.sleep(1)
            continue

        if soil is None:
            emit(f"  NO DATA {areasymbol} ({areaname})")
            row = {c: "" for c in OUTPUT_COLS}
            row.update({
                "county_fips":  county_fips,
                "state_abbrev": state_abbrev,
                "county_fips_3": county_3,
                "county_name":  areaname,
                "areasymbol":   areasymbol,
                "data_available": "False",
                "queried_at":   datetime.now(timezone.utc).isoformat(),
            })
            writer.writerow(row)
            ok += 1
            continue

        # Get latitude for T_g estimate
        try:
            lat = _county_lat(areasymbol)
        except Exception:
            lat = None

        T_g = _T_g_from_lat(lat) if lat else 13.0
        S_r = _S_r_for_state(state_abbrev)

        # Côté-Konrad
        ck = cote_konrad(
            sand_pct=soil["sand_pct"],
            silt_pct=soil["silt_pct"],
            clay_pct=soil["clay_pct"],
            rho_d=soil["rho_d_g_cm3"],
            om_pct=soil["om_pct"],
            S_r=S_r,
        )

        row = {
            "county_fips":   county_fips,
            "state_abbrev":  state_abbrev,
            "county_fips_3": county_3,
            "county_name":   areaname,
            "areasymbol":    areasymbol,
            "sand_pct":      round(soil["sand_pct"], 2),
            "silt_pct":      round(soil["silt_pct"], 2),
            "clay_pct":      round(soil["clay_pct"], 2),
            "rho_d_g_cm3":   round(soil["rho_d_g_cm3"], 4),
            "om_pct":        round(soil["om_pct"], 3),
            "horizon_count": soil["horizon_count"],
            "lat_approx":    round(lat, 4) if lat else "",
            "S_r_used":      S_r,
            "T_g_C":         round(T_g, 2),
            "data_available":"True",
            "queried_at":    datetime.now(timezone.utc).isoformat(),
        }
        row.update(ck)
        writer.writerow(row)
        ok += 1

        # Progress every 10 counties
        if ok % 10 == 0:
            emit(f"  [{i}/{len(areas)}] {ok} done, {err} errors — last: {areasymbol} k={ck['k_wmpk']}")

        time.sleep(0.3)   # polite rate-limiting (< 3 req/sec)

    csv_file.close()
    log.close()

    print(f"\nDone. {ok} counties written, {err} errors, {skipped} skipped.")
    print(f"Output: {OUT_CSV}")
    print(f"Log:    {log_path}")
    print(f"\nNext: run  python scripts/export_public.py  to expand to census tracts.")


if __name__ == "__main__":
    main()

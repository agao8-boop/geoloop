"""
scripts/collect_nwis.py
═════════════════════════════════════════════════════════════════════════════
DEVELOPER PIPELINE — OPEN-LOOP GEOTHERMAL REFERENCE DATA
Not called by the user tool directly.

SCOPE:
  Queries the USGS Water Quality Portal (WQP) for groundwater well data
  relevant to open-loop geothermal system screening. Open-loop systems
  pump groundwater directly through a heat exchanger, requiring:
    - Groundwater temperature T_gw [°C]  → heat pump sizing
    - Well depth [ft]                    → pumping cost estimate
    - Aquifer type                       → yield and reinjection feasibility
    - Well count per county              → proxy for aquifer accessibility

  Data is aggregated at county level and written to:
    data/research/subsurface/openloop_wells_by_county.csv

Run from project root:
    python scripts/collect_nwis.py [--state IL] [--resume] [--limit 5]

Estimated runtime: 10–20 minutes for all 50 states (2 API calls per state).
Progress printed every state; safe to interrupt and resume with --resume.

Output columns:
  county_fips, state_abbrev, county_name,
  well_count, temp_well_count,
  gw_temp_mean_c, gw_temp_min_c, gw_temp_max_c,
  well_depth_mean_ft, well_depth_median_ft,
  dominant_aquifer, aquifer_types_json,
  data_available, queried_at

Open-loop sizing parameters (from user's 390geothermal_calc.xlsx):
  Q_thermal = ṁ × Cp × ΔT   [kW]
  where ṁ = pumped flow rate [kg/s], Cp = 4.18 kJ/kg·K,
  ΔT = T_leaving − T_gw (for heating) or T_gw − T_leaving (for cooling)
  T_gw from this dataset feeds directly into that equation.
═════════════════════════════════════════════════════════════════════════════
"""

import argparse
import csv
import json
import io
import pathlib
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT    = pathlib.Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "research" / "subsurface"
LOG_DIR = ROOT / "data" / "research" / "collection_logs"
OUT_CSV = OUT_DIR / "openloop_wells_by_county.csv"

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── WQP endpoint ──────────────────────────────────────────────────────────
WQP_STATION = "https://www.waterqualitydata.us/data/Station/search"
WQP_RESULT  = "https://www.waterqualitydata.us/data/Result/search"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

# ── State / FIPS maps ─────────────────────────────────────────────────────
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
FIPS_TO_ABBREV = {v: k for k, v in STATE_ABBREV_TO_FIPS.items()}

ALL_STATES = list(STATE_ABBREV_TO_FIPS.keys())

# ── HTTP helper ───────────────────────────────────────────────────────────
def _wqp_csv(url: str, params: dict) -> list[dict]:
    """Fetch a WQP CSV endpoint and return list of row dicts."""
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers={"Accept": "text/csv"})
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=120) as r:
            content = r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"WQP request failed: {exc}")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)

import urllib.parse


def _fetch_stations(state_abbrev: str) -> list[dict]:
    """Return all groundwater well stations in the state that have temperature data."""
    state_fips = STATE_ABBREV_TO_FIPS[state_abbrev]
    return _wqp_csv(WQP_STATION, {
        "statecode":          f"US:{state_fips}",
        "characteristicName": "Temperature, water",
        "siteType":           "Well",
        "mimeType":           "csv",
        "zip":                "no",
    })


def _fetch_results_for_county(state_abbrev: str, county_3: str) -> list[dict]:
    """Return groundwater temperature measurements for a single county.
    Queries per county to keep response size manageable.
    """
    state_fips = STATE_ABBREV_TO_FIPS[state_abbrev]
    return _wqp_csv(WQP_RESULT, {
        "statecode":          f"US:{state_fips}",
        "countycode":         f"US:{state_fips}:{county_3}",
        "characteristicName": "Temperature, water",
        "siteType":           "Well",
        "mimeType":           "csv",
        "zip":                "no",
    })


# ── Aggregation ───────────────────────────────────────────────────────────
OUTPUT_COLS = [
    "county_fips", "state_abbrev", "county_fips_3", "county_name",
    "well_count", "temp_well_count",
    "gw_temp_mean_c", "gw_temp_min_c", "gw_temp_max_c",
    "well_depth_mean_ft", "well_depth_median_ft",
    "dominant_aquifer", "aquifer_types_json",
    "data_available", "queried_at",
]


def _aggregate_county(stations: list[dict], temp_by_site: dict[str, list[float]],
                       state_abbrev: str) -> dict[str, dict]:
    """Group station + temperature data by county FIPS. Returns county_fips → stats."""
    state_fips = STATE_ABBREV_TO_FIPS[state_abbrev]
    counties: dict[str, dict] = {}

    for s in stations:
        county_3 = (s.get("CountyCode") or "").strip().lstrip("0").zfill(3)
        if not county_3 or not county_3.isdigit():
            continue
        fips = state_fips + county_3

        if fips not in counties:
            counties[fips] = {
                "county_fips":   fips,
                "county_fips_3": county_3,
                "state_abbrev":  state_abbrev,
                "county_name":   "",   # filled later if needed
                "_depths":       [],
                "_aquifers":     [],
                "_temps":        [],
                "_temp_site_ids": set(),
            }

        loc_id = s.get("MonitoringLocationIdentifier", "")
        depth_s = s.get("WellDepthMeasure/MeasureValue", "").strip()
        if depth_s:
            try:
                counties[fips]["_depths"].append(float(depth_s))
            except ValueError:
                pass

        aquifer = (s.get("AquiferName") or "").strip()
        if aquifer:
            counties[fips]["_aquifers"].append(aquifer)

        if loc_id in temp_by_site:
            counties[fips]["_temps"].extend(temp_by_site[loc_id])

    return counties


def _finalize_county(fips: str, raw: dict, ts: str) -> dict:
    depths  = raw["_depths"]
    aquifers = raw["_aquifers"]
    temps   = raw["_temps"]

    # Aquifer stats
    aquifer_counts: dict[str, int] = {}
    for a in aquifers:
        aquifer_counts[a] = aquifer_counts.get(a, 0) + 1
    dominant = max(aquifer_counts, key=aquifer_counts.get) if aquifer_counts else ""
    unique_aquifers = list(aquifer_counts.keys())[:5]

    row = {
        "county_fips":       fips,
        "state_abbrev":      raw["state_abbrev"],
        "county_fips_3":     raw["county_fips_3"],
        "county_name":       raw["county_name"],
        "well_count":        len(raw["_depths"]) or len(aquifers),
        "temp_well_count":   len(raw["_temp_site_ids"]),
        "gw_temp_mean_c":    round(sum(temps) / len(temps), 2) if temps else "",
        "gw_temp_min_c":     round(min(temps), 2) if temps else "",
        "gw_temp_max_c":     round(max(temps), 2) if temps else "",
        "well_depth_mean_ft":  round(sum(depths) / len(depths), 1) if depths else "",
        "well_depth_median_ft": round(sorted(depths)[len(depths)//2], 1) if depths else "",
        "dominant_aquifer":  dominant,
        "aquifer_types_json": json.dumps(unique_aquifers),
        "data_available":    "True" if (depths or temps) else "False",
        "queried_at":        ts,
    }
    return row


# ── Resume helper ─────────────────────────────────────────────────────────
def _done_states(path: pathlib.Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {row["state_abbrev"] for row in csv.DictReader(f)}


# ── Main ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Collect NWIS open-loop well data by county")
    parser.add_argument("--state",  help="Process only this state, e.g. IL")
    parser.add_argument("--resume", action="store_true", help="Skip states already in output")
    parser.add_argument("--limit",  type=int, default=0, help="Stop after N states (0 = no limit)")
    args = parser.parse_args()

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"nwis_run_{ts}.log"
    log      = open(log_path, "w", buffering=1)

    def emit(msg: str) -> None:
        print(msg)
        log.write(msg + "\n")

    emit(f"[{ts}] collect_nwis.py — start")
    states = [args.state.upper()] if args.state else ALL_STATES
    emit(f"States to process: {len(states)}")

    done_st = _done_states(OUT_CSV) if args.resume else set()
    emit(f"Resuming — skipping {len(done_st)} already-collected states")

    mode     = "a" if (args.resume and OUT_CSV.exists()) else "w"
    csv_file = open(OUT_CSV, mode, newline="")
    writer   = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLS)
    if mode == "w":
        writer.writeheader()

    ok = err = 0
    for i, state in enumerate(states, 1):
        if args.limit and ok >= args.limit:
            break
        if state in done_st:
            continue
        if state not in STATE_ABBREV_TO_FIPS:
            emit(f"  SKIP {state} (not in FIPS table)")
            continue

        emit(f"  [{i}/{len(states)}] {state} — fetching stations…")
        try:
            stations = _fetch_stations(state)
            emit(f"    {len(stations)} groundwater wells with temp data")
            time.sleep(0.5)
        except Exception as exc:
            emit(f"  ERROR {state} (stations): {exc}")
            err += 1
            time.sleep(2)
            continue

        # Group stations by county first
        county_raw = _aggregate_county(stations, {}, state)

        # Per-county temperature query (small response per county)
        for fips, raw in county_raw.items():
            county_3 = raw["county_fips_3"]
            try:
                results = _fetch_results_for_county(state, county_3)
                temp_by_site: dict[str, list[float]] = defaultdict(list)
                for r in results:
                    loc_id = r.get("MonitoringLocationIdentifier", "")
                    val_s  = (r.get("ResultMeasureValue") or "").strip()
                    unit   = (r.get("ResultMeasure/MeasureUnitCode") or "").strip().lower()
                    if not val_s:
                        continue
                    try:
                        val = float(val_s)
                        if "f" in unit:
                            val = (val - 32) / 1.8
                        if -5 < val < 40:
                            temp_by_site[loc_id].append(val)
                    except ValueError:
                        pass
                for loc_id, temps in temp_by_site.items():
                    raw["_temps"].extend(temps)
                    raw["_temp_site_ids"].add(loc_id)
                time.sleep(0.2)
            except Exception:
                pass  # temperature is optional; proceed with station data only

        now_ts = datetime.now(timezone.utc).isoformat()
        for fips, raw in county_raw.items():
            row = _finalize_county(fips, raw, now_ts)
            writer.writerow(row)

        emit(f"    wrote {len(county_raw)} counties for {state}")
        ok += 1

    csv_file.close()
    log.close()
    print(f"\nDone. {ok} states processed, {err} errors.")
    print(f"Output: {OUT_CSV}")
    print(f"Log:    {log_path}")


if __name__ == "__main__":
    main()

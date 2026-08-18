"""
scripts/collect_macrostrat_all_counties.py
───────────────────────────────────────────────────────────────────────────────
Extend macrostrat_thermal_by_county.csv to ALL 3,221 US counties.

The existing CSV only has the 636 SGMC_CH1995 counties. This script adds
the remaining 2,585 SMU_IDW counties so every county gets Macrostrat-derived
subsurface k_eff bands (best/base/worst) from actual subsurface geology
instead of SGMC surface rock classification.

Resume-safe: skips counties already present in the output CSV.
Rate: 0.35 s/county (~15 min for 2585 counties). Run in background.

Output: appends to data/public/macrostrat_thermal_by_county.csv
"""

import csv, pathlib, time, requests, statistics

ROOT     = pathlib.Path(__file__).parent.parent
DEEP_CSV = ROOT / "data" / "public" / "deep_thermal_by_county.csv"
OUT_CSV  = ROOT / "data" / "public" / "macrostrat_thermal_by_county.csv"
SGMC_CSV = ROOT / "data" / "ml" / "sgmc_by_county.csv"

BOREHOLE_DEPTH_M = 150.0
API_DELAY_S      = 0.35

_NAME_MAP = {
    "shale":"clay_shale","mudstone":"clay_shale","claystone":"clay_shale",
    "siltstone":"clay_shale","marl":"clay_shale","argillite":"clay_shale","mudrock":"clay_shale",
    "limestone":"limestone_carbonate","dolostone":"limestone_carbonate","dolomite":"limestone_carbonate",
    "chalk":"limestone_carbonate","travertine":"limestone_carbonate","calcarenite":"limestone_carbonate",
    "wackestone":"limestone_carbonate","packstone":"limestone_carbonate","grainstone":"limestone_carbonate",
    "boundstone":"limestone_carbonate",
    "sandstone":"sandstone","arkose":"sandstone","graywacke":"sandstone",
    "conglomerate":"sandstone","breccia":"sandstone","quartz arenite":"sandstone","litharenite":"sandstone",
    "sand":"alluvial_glacial","gravel":"alluvial_glacial","clay":"alluvial_glacial",
    "silt":"alluvial_glacial","till":"alluvial_glacial","diamictite":"alluvial_glacial",
    "loess":"alluvial_glacial","diamicton":"alluvial_glacial",
    "coal":"coal_organic","peat":"coal_organic","lignite":"coal_organic",
    "granite":"granite_felsic","granodiorite":"granite_felsic","rhyolite":"granite_felsic",
    "tonalite":"granite_felsic","diorite":"granite_felsic","andesite":"granite_felsic",
    "syenite":"granite_felsic","trachyte":"granite_felsic",
    "basalt":"basalt_mafic","gabbro":"basalt_mafic","diabase":"basalt_mafic",
    "dolerite":"basalt_mafic","dunite":"basalt_mafic","peridotite":"basalt_mafic","pyroxenite":"basalt_mafic",
    "gneiss":"metamorphic","schist":"metamorphic","phyllite":"metamorphic","slate":"metamorphic",
    "marble":"metamorphic","amphibolite":"metamorphic","quartzite":"metamorphic",
    "hornfels":"metamorphic","eclogite":"metamorphic","migmatite":"metamorphic",
}
_TYPE_MAP = {
    "siliciclastic":"clay_shale","carbonate":"limestone_carbonate",
    "unconsolidated":"alluvial_glacial","evaporite":"undifferentiated",
    "chemical":"undifferentiated","organic":"coal_organic","volcaniclastic":"basalt_mafic",
}
_CLASS_MAP = {
    "sedimentary":"undifferentiated","igneous":"granite_felsic",
    "metamorphic":"metamorphic","metasedimentary":"metamorphic",
}
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

def _lith_to_class(name, ltype, lclass):
    return (_NAME_MAP.get((name or "").lower().strip())
            or _TYPE_MAP.get((ltype or "").lower().strip())
            or _CLASS_MAP.get((lclass or "").lower().strip())
            or "undifferentiated")

def _unit_k(lith_list):
    if not lith_list:
        return _K_TABLE["undifferentiated"]
    total = sum(l.get("prop", 1.0) for l in lith_list) or 1.0
    k_min = k_med = k_max = 0.0
    for l in lith_list:
        cls = _lith_to_class(l.get("name",""), l.get("type",""), l.get("class",""))
        lo, md, hi = _K_TABLE[cls]
        w = l.get("prop", 1.0) / total
        k_min += w*lo; k_med += w*md; k_max += w*hi
    return k_min, k_med, k_max

def _harmonic_k(layers):
    H = sum(h for h,*_ in layers)
    if H <= 0: return float("nan"), float("nan"), float("nan")
    return (
        round(H / sum(h/lo for h,lo,md,hi in layers), 4),
        round(H / sum(h/md for h,lo,md,hi in layers), 4),
        round(H / sum(h/hi for h,lo,md,hi in layers), 4),
    )

def fetch_column(lat, lon):
    try:
        r = requests.get("https://macrostrat.org/api/v2/columns",
                         params={"lat":lat,"lng":lon,"format":"json"}, timeout=15)
        r.raise_for_status()
        cols = r.json().get("success",{}).get("data",[])
        if not cols: return {"error":"no column"}
        col_id = cols[0]["col_id"]; col_name = cols[0].get("col_name","")
        time.sleep(0.1)
        r2 = requests.get("https://macrostrat.org/api/v2/units",
                          params={"col_id":col_id,"response":"long","format":"json"}, timeout=15)
        r2.raise_for_status()
        return {"col_id":col_id,"col_name":col_name,
                "units":r2.json().get("success",{}).get("data",[])}
    except Exception as e:
        return {"error": str(e)}

def process_county(lat, lon):
    col = fetch_column(lat, lon)
    if "error" in col or not col.get("units"):
        return {"coverage":"none","k_macro_base":"","k_macro_min":"","k_macro_max":"",
                "macro_layers_n":0,"col_name":col.get("col_name",""),
                "notes":col.get("error","no units")}
    units = sorted(col["units"], key=lambda u: u.get("t_age", 0))
    layers = []; depth = 0.0
    for u in units:
        H_unit = (float(u.get("max_thick") or 0) + float(u.get("min_thick") or 0)) / 2.0
        if H_unit <= 0: continue
        H_in = min(depth + H_unit, BOREHOLE_DEPTH_M) - max(depth, 0.0)
        if H_in > 0:
            layers.append((H_in, *_unit_k(u.get("lith") or [])))
        depth += H_unit
        if depth >= BOREHOLE_DEPTH_M: break
    if not layers:
        return {"coverage":"none","k_macro_base":"","k_macro_min":"","k_macro_max":"",
                "macro_layers_n":0,"col_name":col.get("col_name",""),
                "notes":"no usable thickness"}
    H_cov = sum(h for h,*_ in layers)
    k_min, k_base, k_max = _harmonic_k(layers)
    return {"coverage":"full" if H_cov >= 0.8*BOREHOLE_DEPTH_M else "partial",
            "k_macro_base":k_base,"k_macro_min":k_min,"k_macro_max":k_max,
            "macro_layers_n":len(layers),"col_name":col.get("col_name",""),
            "notes":f"{H_cov:.0f}m of {BOREHOLE_DEPTH_M:.0f}m covered"}

def main():
    # Load centroids
    centroids = {}
    with open(SGMC_CSV) as f:
        for row in csv.DictReader(f):
            centroids[row["county_fips"].zfill(5)] = (float(row["centroid_lat"]), float(row["centroid_lon"]))

    # Load already-done counties
    done = set()
    if OUT_CSV.exists():
        with open(OUT_CSV) as f:
            for row in csv.DictReader(f):
                done.add(row["county_fips"].zfill(5))
    print(f"Already done: {len(done)} counties. Skipping these.")

    # All counties
    all_counties = []
    with open(DEEP_CSV) as f:
        for row in csv.DictReader(f):
            fips = row["county_fips"].zfill(5)
            if fips not in done:
                all_counties.append((fips, row["state_abbrev"], row["county_name"],
                                     row["k_wmpk"], row["k_class_min"], row["k_class_max"]))

    print(f"Remaining: {len(all_counties)} counties to process")
    print(f"Estimated time: ~{len(all_counties)*API_DELAY_S/60:.0f} min\n")

    FIELDS = ["county_fips","state_abbrev","county_name",
              "k_sgmc_old","k_sgmc_min","k_sgmc_max",
              "k_macro_base","k_macro_min","k_macro_max",
              "macro_layers_n","coverage","col_name","notes"]

    write_header = not OUT_CSV.exists()
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()

        results = []
        for i, (fips, state, name, k_old, k_min, k_max) in enumerate(all_counties):
            lat, lon = centroids.get(fips, (None, None))
            if lat is None:
                res = {"coverage":"none","k_macro_base":"","k_macro_min":"","k_macro_max":"",
                       "macro_layers_n":0,"col_name":"","notes":"no centroid"}
            else:
                res = process_county(lat, lon)

            row = {"county_fips":fips,"state_abbrev":state,"county_name":name,
                   "k_sgmc_old":k_old,"k_sgmc_min":k_min,"k_sgmc_max":k_max,**res}
            w.writerow(row)
            f.flush()
            results.append(row)

            if (i+1) % 100 == 0 or (i+1) == len(all_counties):
                n_ok = sum(1 for r in results if r["coverage"] != "none")
                print(f"  [{i+1:4d}/{len(all_counties)}] {n_ok} with data ({100*n_ok/(i+1):.0f}%)")

            time.sleep(API_DELAY_S)

    # Final stats
    valid = [r for r in results if r["k_macro_base"] != ""]
    if valid:
        diffs = [float(r["k_macro_base"]) - float(r["k_sgmc_old"]) for r in valid]
        print(f"\nNew counties — k_macro_base vs k_old, n={len(valid)}:")
        print(f"  mean Δk = {statistics.mean(diffs):+.3f}  stdev = {statistics.stdev(diffs):.3f}")
        within = sum(1 for d in diffs if abs(d) <= 0.1)
        print(f"  Within ±0.1 W/mK: {within}/{len(valid)} ({100*within/len(valid):.0f}%)")
    print(f"\nDone. Output: {OUT_CSV}")
    print(f"Total rows now: {len(done) + len(results)}")

if __name__ == "__main__":
    main()

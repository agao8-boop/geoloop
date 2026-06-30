import sys
import os
import json
import pathlib
sys.path.insert(0, os.path.dirname(__file__))


from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import BadRequest
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s1_site import get_site_data
from geosite.s2_simulation import get_loads
from geosite.models import SiteData, LoadPulses
from geosite.s5_cost import estimate_cost

app = Flask(__name__)

_PUBLIC_DATA = pathlib.Path(__file__).parent / "data" / "public"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True)

    # --- parse all 19 fields ---
    fields = [
        "q_h", "q_m", "q_y",
        "k", "alpha", "T_g",
        "Cp", "mfls", "T_in_HP",
        "rbore", "rpin", "rpext", "kgrout", "kpipe", "LU", "hconv",
        "B", "NB", "A",
    ]
    values = {}
    for f in fields:
        if f not in data or str(data[f]).strip() == "":
            return jsonify({"error": "field", "field": f,
                            "message": f"'{f}' is required"}), 400
        try:
            values[f] = int(data[f]) if f == "NB" else float(data[f])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": f,
                            "message": f"'{f}' must be a number"}), 400

    # --- validate ranges ---
    if not (0.025 <= values["alpha"] <= 0.2):
        return jsonify({"error": "field", "field": "alpha",
                        "message": "α must be between 0.025 and 0.2 m²/day"}), 400
    if not (0.05 <= values["rbore"] <= 0.1):
        return jsonify({"error": "field", "field": "rbore",
                        "message": "Borehole radius must be between 0.05 and 0.1 m"}), 400
    if values["NB"] < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "Number of boreholes must be ≥ 1"}), 400
    if values["A"] < 1:
        return jsonify({"error": "field", "field": "A",
                        "message": "Aspect ratio must be ≥ 1"}), 400

    # --- calculate ---
    try:
        L = size_borefield(
            q_h=values["q_h"], q_m=values["q_m"], q_y=values["q_y"],
            k=values["k"], alpha=values["alpha"], T_g=values["T_g"],
            Cp=values["Cp"], mfls=values["mfls"], T_in_HP=values["T_in_HP"],
            rbore=values["rbore"], rpin=values["rpin"], rpext=values["rpext"],
            kgrout=values["kgrout"], kpipe=values["kpipe"],
            LU=values["LU"], hconv=values["hconv"],
            B=values["B"], NB=values["NB"], A=values["A"],
        )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    return jsonify({"L": round(L), "H": round(L / values["NB"]), "NB": values["NB"]})


# Engineering defaults for borehole/system parameters (Advanced tab values)
_ADVANCED_DEFAULTS = {
    "Cp":     4200.0,
    "mfls":   0.05,
    "rbore":  0.06,
    "rpin":   0.01365,
    "rpext":  0.0167,
    "kgrout": 1.5,
    "kpipe":  0.42,
    "LU":     0.0511,
    "hconv":  1000.0,
}
_T_IN_HP_DEFAULTS = {"heating": 5.0, "cooling": 40.2}

# Piecewise-linear breakpoints: (construction_year, load_factor vs 90.1-2019 prototype)
# Sources: DOE/PNNL ASHRAE 90.1 savings analyses; CBECS 2018 EUI vintage ratios (DOE EIA)
_VINTAGE_BP = [
    (2020, 1.00),  # 90.1-2019 prototype baseline
    (2017, 1.03),  # 90.1-2016
    (2014, 1.07),  # 90.1-2013
    (2011, 1.12),  # 90.1-2010
    (2008, 1.18),  # 90.1-2007
    (2005, 1.25),  # 90.1-2004
    (2000, 1.30),  # 90.1-2001/1999
    (1995, 1.35),  # 90.1-1989 (late adoption)
    (1980, 1.42),  # ASHRAE 90-1980
    (1960, 1.50),  # pre-energy-code era
]


def _year_to_load_factor(year_built: int) -> float:
    """Continuous load multiplier vs DOE 90.1-2019 prototype by construction year.

    Year 0 = new construction / planned (slightly better than 2019 prototype).
    Interpolates linearly between ASHRAE 90.1 code vintage breakpoints.
    """
    if year_built == 0:
        return 0.97
    if year_built >= 2020:
        return 1.00
    if year_built <= 1960:
        return 1.50
    for i in range(len(_VINTAGE_BP) - 1):
        y_hi, f_hi = _VINTAGE_BP[i]
        y_lo, f_lo = _VINTAGE_BP[i + 1]
        if y_lo <= year_built < y_hi:
            t = (year_built - y_lo) / (y_hi - y_lo)
            return round(f_lo + t * (f_hi - f_lo), 3)
    return 1.50


@app.route("/calculate/smart", methods=["POST"])
def calculate_smart():
    """Automated pipeline: ZIP + building type → soil + loads → borefield length.

    Required body fields: zip_code, building_type, NB, B, A
    Optional: year_built (int, 0=new/planned), floor_area_m2, soil_confidence,
              T_in_HP, mfls, Cp, rbore, rpin, rpext, kgrout, kpipe, LU, hconv
    Dominant mode (heating/cooling) is auto-detected from the DOE load profile sign.
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    # --- validate required fields ---
    required = {"zip_code": str, "building_type": str,
                "NB": int, "B": float, "A": float}
    for field, _ in required.items():
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    zip_code = str(data["zip_code"]).strip()
    building_type = str(data["building_type"]).strip()
    NB = int(data["NB"])
    B = float(data["B"])
    A = float(data["A"])

    # Optional: floor area scaling
    floor_area_m2 = None
    if data.get("floor_area_m2") and str(data["floor_area_m2"]).strip():
        try:
            floor_area_m2 = float(data["floor_area_m2"])
            if floor_area_m2 <= 0:
                return jsonify({"error": "field", "field": "floor_area_m2",
                                "message": "Floor area must be positive"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "floor_area_m2",
                            "message": "Floor area must be a number"}), 400

    # Optional: construction year → continuous load factor vs 90.1-2019 prototype
    year_built = 2020  # default: prototype baseline
    if "year_built" in data and str(data["year_built"]).strip() != "":
        try:
            year_built = int(data["year_built"])
            if year_built < 0:
                return jsonify({"error": "field", "field": "year_built",
                                "message": "Year must be 0 (new/planned) or a positive year"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "year_built",
                            "message": "Year must be an integer"}), 400
    year_factor = _year_to_load_factor(year_built)

    # Optional: soil confidence → safety factor on k
    _CONFIDENCE_K_FACTORS = {
        "high":   1.10,   # site investigation data — relax k 10% upward
        "medium": 1.00,   # county-level estimate — use as-is
        "low":    0.83,   # uncertain geology — reduce k 17% (≈ 20% longer L)
    }
    soil_confidence = str(data.get("soil_confidence", "low")).strip().lower()
    if soil_confidence not in _CONFIDENCE_K_FACTORS:
        soil_confidence = "medium"
    k_factor = _CONFIDENCE_K_FACTORS[soil_confidence]

    if NB < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "NB must be >= 1"}), 400
    if A < 1:
        return jsonify({"error": "field", "field": "A",
                        "message": "A must be >= 1"}), 400

    # --- s1: get site data ---
    try:
        site: SiteData = get_site_data(zip_code)
    except ValueError as exc:
        return jsonify({"error": "geocode", "message": str(exc)}), 422

    if not site.data_available:
        return jsonify({
            "error": "no_site_data",
            "message": (
                f"No soil data available for ZIP {zip_code}. "
                "The borefield cannot be sized without soil thermal properties."
            ),
        }), 422

    # --- s2: get building loads (with optional area scaling) ---
    try:
        loads: LoadPulses = get_loads(building_type, site.climate_zone,
                                      floor_area_m2=floor_area_m2)
    except KeyError as exc:
        return jsonify({"error": "field", "field": "building_type",
                        "message": str(exc)}), 400

    # Apply construction year correction factor to all three pulses
    loads = LoadPulses(
        q_h=loads.q_h * year_factor,
        q_m=loads.q_m * year_factor,
        q_y=loads.q_y * year_factor,
    )

    # Auto-detect dominant mode from load sign (negative = heating, positive = cooling)
    mode = "heating" if loads.q_h < 0 else "cooling"

    # --- resolve system parameters (user override or default) ---
    T_in_HP = float(data.get("T_in_HP", _T_IN_HP_DEFAULTS[mode]))
    params = {k: float(data.get(k, v)) for k, v in _ADVANCED_DEFAULTS.items()}

    # Apply soil confidence factor to k (conservative = lower k = longer L)
    effective_k = site.k * k_factor

    # --- s4: borefield sizing ---
    try:
        L = size_borefield(
            q_h=loads.q_h, q_m=loads.q_m, q_y=loads.q_y,
            k=effective_k, alpha=site.alpha, T_g=site.T_g,
            T_in_HP=T_in_HP,
            B=B, NB=NB, A=A,
            **params,
        )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    return jsonify({
        "L": round(L),
        "H": round(L / NB),
        "NB": NB,
        "site": {
            "k": site.k,
            "k_effective": round(effective_k, 3),
            "soil_confidence": soil_confidence,
            "alpha": site.alpha,
            "T_g": site.T_g,
            "climate_zone": site.climate_zone,
            "state_abbrev": site.state_abbrev,
            "data_available": site.data_available,
        },
        "loads": {
            "q_h": loads.q_h,
            "q_m": loads.q_m,
            "q_y": loads.q_y,
            "mode": mode,
            "year_built": year_built,
            "year_factor": year_factor,
            "floor_area_m2": floor_area_m2,
        },
    })


@app.route("/references")
def references():
    refs = json.loads((_PUBLIC_DATA / "references.json").read_text())
    return render_template("references.html", categories=refs)


_RESEARCH_SUBSURFACE = pathlib.Path(__file__).parent / "data" / "research" / "subsurface"


@app.route("/api/county_thermal")
def county_thermal_api():
    """Return county-level SSURGO shallow thermal data (0–200 cm) as JSON dict keyed by 5-digit FIPS.
    NOTE: This data covers shallow soil only (0–2 m). Intended for horizontal closed-loop
    system screening. NOT suitable for vertical borehole sizing (requires 30–150 m data).
    """
    import csv as csv_mod
    csv_path = _RESEARCH_SUBSURFACE / "horizontal_shallow_thermal_by_county.csv"
    data = {}
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                fips = row["county_fips"]
                data[fips] = {
                    "county_name":  row["county_name"],
                    "state_abbrev": row["state_abbrev"],
                    "soil_class":   row["soil_class"] or None,
                    "q_quartz":     row["q_quartz"] or None,
                    "n_porosity":   row["n_porosity"] or None,
                    "k_wmpk":       row["k_wmpk"] or None,
                    "k_sat":        row["k_sat"] or None,
                    "k_dry":        row["k_dry"] or None,
                    "k_s":          row["k_s"] or None,
                    "k_e":          row["k_e"] or None,
                    "alpha_m2day":  row["alpha_m2day"] or None,
                    "S_r_used":     row["S_r_used"] or None,
                    "T_g_C":        row["T_g_C"] or None,
                    "sand_pct":     row["sand_pct"] or None,
                    "silt_pct":     row["silt_pct"] or None,
                    "clay_pct":     row["clay_pct"] or None,
                    "rho_d_g_cm3":  row["rho_d_g_cm3"] or None,
                    "om_pct":       row["om_pct"] or None,
                    "horizon_count":row["horizon_count"] or None,
                    "data_available": row["data_available"] == "True",
                }
    return jsonify(data)


_PUBLIC_DATA = pathlib.Path(__file__).parent / "data" / "public"


@app.route("/api/deep_thermal")
def deep_thermal_api():
    """Return county-level deep borehole thermal properties (k, α, T_g) for vertical sizing.

    Two-track method (Blackwell & Richards 2004; Clauser & Huenges 1995):
      Track A — IDW from SMU quality A+B k measurements where ≥3 points in 200 km
      Track B — SGMC rock class → Clauser & Huenges (1995) median k (fallback)
    T_g at 100 m borehole midpoint = surface T_g + 0.100 km × geothermal gradient.

    Response: JSON dict keyed by 5-digit county FIPS.
    """
    import csv as csv_mod
    csv_path = _PUBLIC_DATA / "deep_thermal_by_county.csv"
    data = {}
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                fips = row.get("county_fips", "").zfill(5)
                if not fips:
                    continue
                data[fips] = {
                    "k_wmpk":          row.get("k_wmpk") or None,
                    "alpha_m2day":     row.get("alpha_m2day") or None,
                    "T_g_C":           row.get("T_g_C") or None,
                    "k_method":        row.get("k_method", ""),
                    "T_g_method":      row.get("T_g_method", ""),
                    "n_smu_pts_200km": row.get("n_smu_pts_200km") or None,
                    "rock_class_name": row.get("rock_class_name", "") or None,
                    "state_abbrev":    row.get("state_abbrev", ""),
                    "county_name":     row.get("county_name", ""),
                }
    return jsonify({
        "counties": data,
        "total": len(data),
        "method": "SMU_IDW+SGMC_CH1995",
        "references": [
            "Blackwell & Richards (2004) Geothermal Map of North America",
            "Clauser & Huenges (1995) AGU Reference Shelf 3 pp. 105-126",
            "Banks (2008) Introduction to Thermogeology Table A.1",
        ],
    })


@app.route("/api/ml/thermal")
def ml_thermal_api():
    """[DEPRECATED] Bootstrap ML thermal predictions — scientifically invalid.

    Labels were derived from SSURGO shallow soil data (0-2 m) misapplied to
    150 m depth. CV RMSE is circular. Uncertainty ±0.5-1.0 W/m·K.
    Use /api/deep_thermal instead (SMU IDW + Clauser & Huenges 1995).
    Retained for reference only.
    """
    import csv as csv_mod
    csv_path = _PUBLIC_DATA / "ml_thermal_by_county.csv"
    data = {}
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                fips = row.get("county_fips", "")
                if not fips:
                    continue
                data[fips] = {
                    "k_wmpk":      row.get("k_wmpk") or None,
                    "T_g_C":       row.get("T_g_C")  or None,
                    "alpha_m2day": row.get("alpha_m2day") or None,
                    "rock_class":  row.get("rock_class") or None,
                    "stage":       row.get("stage", "1_bootstrap"),
                    "state_abbrev":row.get("state_abbrev", ""),
                }
    return jsonify({
        "counties": data, "model_stage": "1_bootstrap_DEPRECATED",
        "total": len(data), "data_quality": "INVALID_shallow_proxy",
        "warning": "Use /api/deep_thermal — this endpoint uses invalid bootstrap labels",
    })


@app.route("/api/smuhf/points")
def smuhf_points_api():
    """Return SMU Heat Flow database quality A+B measured thermal conductivity points.
    Source: GDR OpenEI submission 1704 — SMU Geothermal Laboratory (Blackwell & Richards 2004).
    Filtered to equilibrium wells (quality A = high, B = medium) with valid measured k.
    These are MEASURED in-situ thermal conductivity values at borehole depth, NOT soil estimates.
    """
    import json as _json
    p = _PUBLIC_DATA / "smuhf_points.json"
    if p.exists():
        return _json.loads(p.read_text()), 200, {"Content-Type": "application/json"}
    return jsonify({"points": [], "count": 0, "error": "data not yet generated"}), 200


@app.route("/api/openloop_wells")
def openloop_wells_api():
    """Return county-level open-loop groundwater well data as JSON dict keyed by 5-digit FIPS.
    Data source: USGS Water Quality Portal (WQP) groundwater temperature + well depth measurements.
    Suitable for open-loop geothermal system screening.
    """
    import csv as csv_mod
    csv_path = _RESEARCH_SUBSURFACE / "openloop_wells_by_county.csv"
    data = {}
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                fips = row.get("county_fips", "")
                if not fips:
                    continue
                data[fips] = {
                    "county_name":        row.get("county_name", ""),
                    "state_abbrev":       row.get("state_abbrev", ""),
                    "well_count":         row.get("well_count", "") or None,
                    "temp_well_count":    row.get("temp_well_count", "") or None,
                    "gw_temp_mean_c":     row.get("gw_temp_mean_c", "") or None,
                    "gw_temp_min_c":      row.get("gw_temp_min_c", "") or None,
                    "gw_temp_max_c":      row.get("gw_temp_max_c", "") or None,
                    "well_depth_mean_ft": row.get("well_depth_mean_ft", "") or None,
                    "well_depth_median_ft": row.get("well_depth_median_ft", "") or None,
                    "dominant_aquifer":   row.get("dominant_aquifer", "") or None,
                    "data_available":     row.get("data_available", "False") == "True",
                }
    return jsonify(data)


@app.route("/api/cost", methods=["POST"])
def cost_api():
    """Estimate borefield installation cost given sizing output.

    Required body fields: L (meters), NB (int), B (meters), state (2-letter abbrev or null)
    Optional: rock_class (SGMC rock class name), distance_to_house_ft (float, default 100)
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    for field in ("L", "NB", "B"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    try:
        L_m = float(data["L"])
        NB = int(data["NB"])
        B_m = float(data["B"])
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "field", "message": str(exc)}), 400

    state = data.get("state") or None
    rock_class = data.get("rock_class") or None
    distance_to_house_ft = float(data.get("distance_to_house_ft", 100.0))

    try:
        result = estimate_cost(
            L_m=L_m, NB=NB, B_m=B_m, state=state,
            rock_class_name=rock_class,
            distance_to_house_ft=distance_to_house_ft,
        )
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    def _cr(cr):
        return {
            "total_usd": round(cr.total_usd, 2),
            "cost_per_ft": round(cr.cost_per_ft, 2),
            "L_ft": round(cr.L_ft, 1),
            "NB": cr.NB,
            "breakdown": [
                {**item, "cost_usd": round(item["cost_usd"], 2)}
                for item in cr.breakdown
            ],
            "region_used": cr.region_used,
            "rock_frac": cr.rock_frac,
            "scenario": cr.scenario,
        }

    return jsonify({
        "best":  _cr(result["best"]),
        "base":  _cr(result["base"]),
        "worst": _cr(result["worst"]),
        "headline_per_ft": round(result["headline_per_ft"], 2),
        "region_used": result["region_used"],
    })


@app.route("/api/cost/map")
def cost_map_api():
    """Return per-state base-scenario $/ft for Leaflet choropleth.

    Uses a representative project: NB=16, B=6.0m, L=1200m (small office baseline).
    """
    _REP_L_M = 1200.0
    _REP_NB = 16
    _REP_B_M = 6.0

    all_states = [
        "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID",
        "IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO",
        "MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA",
        "RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
    ]
    out = {}
    for state in all_states:
        res = estimate_cost(L_m=_REP_L_M, NB=_REP_NB, B_m=_REP_B_M, state=state)
        out[state] = {
            "best_per_ft":  round(res["best"].cost_per_ft, 2),
            "base_per_ft":  round(res["base"].cost_per_ft, 2),
            "worst_per_ft": round(res["worst"].cost_per_ft, 2),
            "region_used":  res["region_used"],
        }

    return jsonify({"states": out})


@app.route("/dev")
def developer():
    """Developer-only pipeline dashboard — not linked from the public UI."""
    return render_template("dev.html")

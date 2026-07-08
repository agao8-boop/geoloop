import sys
import os
import json
import math
import pathlib
sys.path.insert(0, os.path.dirname(__file__))


from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import BadRequest
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import compute_nb_range, find_optimal_nb
from geosite.s1_site import get_site_data
from geosite.s2_simulation import get_loads
from geosite.s2_simulation.envelope import (
    WWR_OPTIONS, ENVELOPE_OPTIONS, GLAZING_OPTIONS, compute_envelope_factor,
)
from geosite.models import SiteData, LoadPulses
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy import run_strategy

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

    design, err = _parse_design_fields(data)
    if err:
        return err
    wwr, envelope, glazing, envelope_factor = design
    for f in ("q_h", "q_m", "q_y"):
        values[f] *= envelope_factor

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

    return jsonify({"L": round(L), "H": round(L / values["NB"]),
                    "NB": values["NB"], "envelope_factor": envelope_factor})


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


def _parse_design_fields(data):
    """Return (wwr, envelope, glazing, envelope_factor) or a Flask 400 tuple."""
    wwr      = str(data.get("wwr", "medium")).strip().lower()
    envelope = str(data.get("envelope", "standard")).strip().lower()
    glazing  = str(data.get("glazing", "double")).strip().lower()
    for field, value, options in (("wwr", wwr, WWR_OPTIONS),
                                  ("envelope", envelope, ENVELOPE_OPTIONS),
                                  ("glazing", glazing, GLAZING_OPTIONS)):
        if value not in options:
            return None, (jsonify({"error": "field", "field": field,
                                   "message": f"'{field}' must be one of {sorted(options)}"}), 400)
    return (wwr, envelope, glazing, compute_envelope_factor(wwr, envelope, glazing)), None

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


def _resolve_site_and_loads(data):
    """Shared s1+s2 half of the pipeline. Returns (payload, None) or (None, error_response).

    payload = {
        "site": {...},          # exact dict /calculate/smart returns under "site"
        "loads": {...},         # smart's "loads" dict + q_m_heat/q_m_cool (NaN → None)
        "building_type": str,
        "floor_area_m2": float | None,
        "effective_k": float,   # unrounded, for sizing
        "loads_obj": LoadPulses # unrounded, for sizing
    }
    """
    for field in ("zip_code", "building_type"):
        if field not in data or str(data[field]).strip() == "":
            return None, (jsonify({"error": "field", "field": field,
                                   "message": f"'{field}' is required"}), 400)

    zip_code = str(data["zip_code"]).strip()
    building_type = str(data["building_type"]).strip()

    # Optional: floor area scaling
    floor_area_m2 = None
    if data.get("floor_area_m2") and str(data["floor_area_m2"]).strip():
        try:
            floor_area_m2 = float(data["floor_area_m2"])
            if floor_area_m2 <= 0:
                return None, (jsonify({"error": "field", "field": "floor_area_m2",
                                       "message": "Floor area must be positive"}), 400)
        except (ValueError, TypeError):
            return None, (jsonify({"error": "field", "field": "floor_area_m2",
                                   "message": "Floor area must be a number"}), 400)

    # Optional: construction year → continuous load factor vs 90.1-2019 prototype
    year_built = 2020  # default: prototype baseline
    if "year_built" in data and str(data["year_built"]).strip() != "":
        try:
            year_built = int(data["year_built"])
            if year_built < 0:
                return None, (jsonify({"error": "field", "field": "year_built",
                                       "message": "Year must be 0 (new/planned) or a positive year"}), 400)
        except (ValueError, TypeError):
            return None, (jsonify({"error": "field", "field": "year_built",
                                   "message": "Year must be an integer"}), 400)
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

    design, err = _parse_design_fields(data)
    if err:
        return None, err
    wwr, envelope, glazing, envelope_factor = design

    # --- s1: get site data ---
    try:
        site: SiteData = get_site_data(zip_code)
    except ValueError as exc:
        return None, (jsonify({"error": "geocode", "message": str(exc)}), 422)

    if not site.data_available:
        return None, (jsonify({
            "error": "no_site_data",
            "message": (
                f"No soil data available for ZIP {zip_code}. "
                "The borefield cannot be sized without soil thermal properties."
            ),
        }), 422)

    # --- s2: get building loads (with optional area scaling) ---
    try:
        loads: LoadPulses = get_loads(building_type, site.climate_zone,
                                      floor_area_m2=floor_area_m2,
                                      envelope_factor=envelope_factor)
    except KeyError as exc:
        return None, (jsonify({"error": "field", "field": "building_type",
                               "message": str(exc)}), 400)

    # Apply construction year correction factor to all pulses (NaN-safe)
    def _scale(v: float) -> float:
        return v * year_factor if v == v else float("nan")

    loads = LoadPulses(
        q_h=loads.q_h * year_factor,
        q_m=loads.q_m * year_factor,
        q_y=loads.q_y * year_factor,
        q_h_heat=_scale(loads.q_h_heat),
        q_m_heat=_scale(loads.q_m_heat),
        q_h_cool=_scale(loads.q_h_cool),
        q_m_cool=_scale(loads.q_m_cool),
    )

    # Dominant mode for backward-compat labels and single-pass fallback
    mode = "heating" if loads.q_h < 0 else "cooling"

    # Physics-grounded confidence: use Clauser-Huenges class bounds when available
    _k_min_ok = site.k_min == site.k_min  # True when not NaN
    _k_max_ok = site.k_max == site.k_max
    if _k_min_ok and _k_max_ok:
        if soil_confidence == "low":
            effective_k = site.k_min
        elif soil_confidence == "high":
            effective_k = min(site.k_max, site.k * 1.25)
        else:
            effective_k = site.k
    else:
        effective_k = site.k * k_factor

    def _nan_none(v: float):
        return None if v != v else v

    return {
        "site": {
            "k": site.k,
            "k_effective": round(effective_k, 3),
            "soil_confidence": soil_confidence,
            "alpha": site.alpha,
            "T_g": site.T_g,
            "climate_zone": site.climate_zone,
            "state_abbrev": site.state_abbrev,
            "data_available": site.data_available,
            "rock_class": site.rock_class,
            "k_min": None if (site.k_min != site.k_min) else round(site.k_min, 3),
            "k_max": None if (site.k_max != site.k_max) else round(site.k_max, 3),
            "shallow_soil_class": site.shallow_soil_class,
            "k_shallow": None if (site.k_shallow != site.k_shallow) else round(site.k_shallow, 3),
        },
        "loads": {
            "q_h": loads.q_h,
            "q_m": loads.q_m,
            "q_y": loads.q_y,
            "q_h_heat": _nan_none(loads.q_h_heat),
            "q_m_heat": _nan_none(loads.q_m_heat),
            "q_h_cool": _nan_none(loads.q_h_cool),
            "q_m_cool": _nan_none(loads.q_m_cool),
            "mode": mode,
            "year_built": year_built,
            "year_factor": year_factor,
            "floor_area_m2": floor_area_m2,
            "wwr": wwr,
            "envelope": envelope,
            "glazing": glazing,
            "envelope_factor": envelope_factor,
        },
        "building_type": building_type,
        "floor_area_m2": floor_area_m2,
        "effective_k": effective_k,
        "loads_obj": loads,
    }, None


def _run_sizing(*, q_pulses, effective_k, alpha, T_g, building_type,
                floor_area_m2, NB, H_min, B, A, params, data):
    """Shared s4 half. q_pulses = dict with q_h..q_m_cool (None allowed for mode split).
    Returns (result_dict, None) or (None, error_response).
    result_dict keys: L, H, NB, nb_min, nb_max, H_min, footprint, nb_source,
    governing, L_heat, L_cool, imbalance_m, solar_thermal_recommended.
    """
    q_h, q_m, q_y = q_pulses["q_h"], q_pulses["q_m"], q_pulses["q_y"]
    mode = "heating" if q_h < 0 else "cooling"

    nb_min = nb_max = None
    fp_meta = None
    if NB is None:
        try:
            nb_min, nb_max, fp_meta = compute_nb_range(
                floor_area_m2, building_type, spacing_m=B)
        except (KeyError, ValueError) as exc:
            return None, (jsonify({"error": "field", "field": "building_type",
                                   "message": str(exc)}), 400)

    # --- s4: two-pass borefield sizing ---
    # Run for both heating and cooling; the mode requiring more borefield governs.
    # A negative result from either pass means that mode's constraint is not binding.
    _has_both = all(q_pulses.get(key) is not None
                    for key in ("q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"))

    try:
        if _has_both:
            T_heat = float(data.get("T_in_HP_heat", _T_IN_HP_DEFAULTS["heating"]))
            T_cool = float(data.get("T_in_HP_cool", _T_IN_HP_DEFAULTS["cooling"]))
            if NB is not None:
                L_heat = size_borefield(
                    q_h=q_pulses["q_h_heat"], q_m=q_pulses["q_m_heat"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_heat, B=B, NB=NB, A=A, **params,
                )
                L_cool = size_borefield(
                    q_h=q_pulses["q_h_cool"], q_m=q_pulses["q_m_cool"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_cool, B=B, NB=NB, A=A, **params,
                )
                governing = "heating" if L_heat >= L_cool else "cooling"
                L = max(L_heat, L_cool)
                NB_out, H = NB, L / NB
            else:
                NB_h, L_heat, H_h = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=q_pulses["q_h_heat"], q_m=q_pulses["q_m_heat"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_heat, **params,
                )
                NB_c, L_cool, H_c = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=q_pulses["q_h_cool"], q_m=q_pulses["q_m_cool"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_cool, **params,
                )
                governing = "heating" if L_heat >= L_cool else "cooling"
                L, NB_out, H = ((L_heat, NB_h, H_h) if governing == "heating"
                                else (L_cool, NB_c, H_c))
        else:
            T_in_HP = float(data.get("T_in_HP", _T_IN_HP_DEFAULTS[mode]))
            L_heat = None
            L_cool = None
            governing = mode
            if NB is not None:
                L = size_borefield(
                    q_h=q_h, q_m=q_m, q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_in_HP, B=B, NB=NB, A=A, **params,
                )
                NB_out, H = NB, L / NB
            else:
                NB_out, L, H = find_optimal_nb(
                    nb_min, nb_max,
                    q_h=q_h, q_m=q_m, q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    H_min=H_min, B=B, A=A, T_in_HP=T_in_HP, **params,
                )
    except Exception as exc:
        return None, (jsonify({"error": "calculation", "message": str(exc)}), 500)

    if NB is not None:
        nb_source = "expert_override"
    elif NB_out < nb_min:
        nb_source = "depth_fallback"
    else:
        nb_source = "optimizer"

    # Thermal imbalance metrics (only meaningful when two-pass ran)
    imbalance_m = round(abs(L_heat - L_cool)) if (L_heat is not None and L_cool is not None) else None
    # Ground cools over time when net annual extraction (q_y < 0); solar thermal can offset
    solar_thermal_recommended = q_y < 0

    return {
        "L": round(L),
        "H": round(H),
        "NB": NB_out,
        "nb_min": nb_min,
        "nb_max": nb_max,
        "H_min": None if NB is not None else H_min,
        "footprint": fp_meta,
        "nb_source": nb_source,
        "governing": governing,
        "L_heat": round(L_heat) if L_heat is not None else None,
        "L_cool": round(L_cool) if L_cool is not None else None,
        "imbalance_m": imbalance_m,
        "solar_thermal_recommended": solar_thermal_recommended,
    }, None


@app.route("/calculate/smart", methods=["POST"])
def calculate_smart():
    """Automated pipeline: ZIP + building type → soil + loads → borefield length.

    Required body fields: zip_code, building_type, B, A
    Optional: year_built (int, 0=new/planned), floor_area_m2, soil_confidence,
              NB (expert override), H_min,
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
    for field in ("zip_code", "building_type", "B", "A"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    B = float(data["B"])
    A = float(data["A"])

    # NB fixed-count mode is legacy; footprint-derived NB is the default.
    # data["NB"] may be JSON null (dev.html sends NaN -> null when blank).
    NB = None
    if data.get("NB") not in (None, ""):
        try:
            NB = int(data["NB"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "NB",
                            "message": "NB must be an integer"}), 400
    try:
        H_min = float(data.get("H_min", 125.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be a number"}), 400
    if not (30.0 <= H_min <= 300.0):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be between 30 and 300 m"}), 400

    if NB is not None and NB < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "NB must be >= 1"}), 400
    if A < 1:
        return jsonify({"error": "field", "field": "A",
                        "message": "A must be >= 1"}), 400

    payload, err = _resolve_site_and_loads(data)
    if err:
        return err

    params = {k: float(data.get(k, v)) for k, v in _ADVANCED_DEFAULTS.items()}

    result, err = _run_sizing(
        q_pulses=payload["loads"],
        effective_k=payload["effective_k"],
        alpha=payload["site"]["alpha"],
        T_g=payload["site"]["T_g"],
        building_type=payload["building_type"],
        floor_area_m2=payload["floor_area_m2"],
        NB=NB, H_min=H_min, B=B, A=A,
        params=params, data=data,
    )
    if err:
        return err

    return jsonify({**result, "site": payload["site"], "loads": payload["loads"]})


@app.route("/calculate/stage1", methods=["POST"])
def calculate_stage1():
    """Stage 1 of the wizard: site + loads + footprint NB range. No sizing."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    payload, err = _resolve_site_and_loads(data)
    if err:
        return err

    try:
        nb_min, nb_max, fp_meta = compute_nb_range(
            payload["floor_area_m2"], payload["building_type"], spacing_m=6.0)
    except (KeyError, ValueError) as exc:
        return jsonify({"error": "field", "field": "building_type",
                        "message": str(exc)}), 400

    return jsonify({
        "site": payload["site"],
        "loads": payload["loads"],
        "nb_estimate": {
            "nb_min": nb_min, "nb_max": nb_max, "spacing_m": 6.0,
            "footprint": fp_meta,
            "note": "estimated at default 6.0 m spacing; recomputed in stage 2",
        },
    })


@app.route("/calculate/stage2", methods=["POST"])
def calculate_stage2():
    """Stage 2 of the wizard: NB optimization + sizing from echoed stage-1 numbers."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    _stage1_msg = "Stage 1 result is missing or corrupt — run Analyze Site & Loads again"

    site = data.get("site")
    if not isinstance(site, dict):
        return jsonify({"error": "field", "field": "site",
                        "message": _stage1_msg}), 400
    try:
        effective_k = float(site["k_effective"])
        alpha = float(site["alpha"])
        T_g = float(site["T_g"])
        if not all(math.isfinite(v) for v in (effective_k, alpha, T_g)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "field", "field": "site",
                        "message": _stage1_msg}), 400

    loads_in = data.get("loads")
    if not isinstance(loads_in, dict):
        return jsonify({"error": "field", "field": "loads",
                        "message": _stage1_msg}), 400
    q_pulses = {}
    try:
        for key in ("q_h", "q_m", "q_y"):
            v = float(loads_in[key])
            if not math.isfinite(v):
                raise ValueError
            q_pulses[key] = v
        for key in ("q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"):
            v = loads_in.get(key)
            if v is None:
                q_pulses[key] = None
            else:
                v = float(v)
                if not math.isfinite(v):
                    raise ValueError
                q_pulses[key] = v
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "field", "field": "loads",
                        "message": _stage1_msg}), 400

    if "building_type" not in data or str(data["building_type"]).strip() == "":
        return jsonify({"error": "field", "field": "building_type",
                        "message": "'building_type' is required"}), 400
    building_type = str(data["building_type"]).strip()

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

    try:
        H_min = float(data.get("H_min", 125.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be a number"}), 400
    if not (30.0 <= H_min <= 300.0):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be between 30 and 300 m"}), 400

    try:
        B = float(data.get("B", 6.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "B",
                        "message": "B must be a number"}), 400
    if B <= 0:
        return jsonify({"error": "field", "field": "B",
                        "message": "B must be > 0"}), 400

    try:
        A = float(data.get("A", 9.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "A",
                        "message": "A must be a number"}), 400
    if A < 1:
        return jsonify({"error": "field", "field": "A",
                        "message": "A must be >= 1"}), 400

    NB = None
    if data.get("NB") not in (None, ""):
        try:
            NB = int(data["NB"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "NB",
                            "message": "NB must be an integer"}), 400
        if NB < 1:
            return jsonify({"error": "field", "field": "NB",
                            "message": "NB must be >= 1"}), 400

    params = {k: float(data.get(k, v)) for k, v in _ADVANCED_DEFAULTS.items()}

    result, err = _run_sizing(
        q_pulses=q_pulses, effective_k=effective_k, alpha=alpha, T_g=T_g,
        building_type=building_type, floor_area_m2=floor_area_m2,
        NB=NB, H_min=H_min, B=B, A=A, params=params, data=data,
    )
    if err:
        return err
    return jsonify(result)


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
    p = _PUBLIC_DATA / "smuhf_points.json"
    if p.exists():
        return json.loads(p.read_text()), 200, {"Content-Type": "application/json"}
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

    if L_m <= 0 or NB < 1 or B_m <= 0:
        return jsonify({"error": "field", "message": "L, NB, B must be positive"}), 400

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


@app.route("/api/loads/hourly")
def hourly_loads_api():
    """Serve pre-extracted 8760h hourly ground load profiles (W) for all building × zone combos."""
    p = _PUBLIC_DATA / "prototype_loads_hourly.json"
    if not p.exists():
        return jsonify({"error": "data_not_found",
                        "message": "prototype_loads_hourly.json not generated yet"}), 404
    return json.loads(p.read_text()), 200, {"Content-Type": "application/json"}


@app.route("/api/strategy", methods=["POST"])
def strategy_api():
    """Run mandatory hybrid GSHP strategy analysis.

    Required: building_type, climate_zone, k, alpha, T_g, NB, B, A
    Optional: state (2-letter abbrev or null), ldc_cutoff_pct (default 10), imbalance_threshold (default 1.25),
              floor_area_m2, year_built (int), year_factor (float, overrides year_built)
              Advanced: Cp, mfls, rbore, rpin, rpext, kgrout, kpipe, LU, hconv
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    for field in ("building_type", "climate_zone", "k", "alpha", "T_g", "B"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    building_type = str(data["building_type"]).strip()
    climate_zone  = str(data["climate_zone"]).strip()
    state         = data.get("state") or None

    try:
        k     = float(data["k"])
        alpha = float(data["alpha"])
        T_g   = float(data["T_g"])
        B     = float(data["B"])
        A     = float(data.get("A", 9.0))
        NB    = int(data["NB"]) if data.get("NB") not in (None, "") else None
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "field", "message": str(exc)}), 400

    ldc_cutoff_pct      = float(data.get("ldc_cutoff_pct", 10.0))
    imbalance_threshold = float(data.get("imbalance_threshold", 1.25))
    H_min               = float(data.get("H_min", 125.0))
    ignore_top_pct      = float(data.get("ignore_top_pct", 0.4))

    floor_area_m2 = None
    if data.get("floor_area_m2"):
        floor_area_m2 = float(data["floor_area_m2"])

    year_factor = 1.0
    if data.get("year_factor"):
        year_factor = float(data["year_factor"])
    elif data.get("year_built"):
        year_factor = _year_to_load_factor(int(data["year_built"]))

    envelope_factor = 1.0
    if data.get("envelope_factor") not in (None, ""):
        try:
            envelope_factor = float(data["envelope_factor"])
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": "envelope_factor",
                            "message": "envelope_factor must be a number"}), 400
    if not (0.0 < envelope_factor <= 10.0):
        return jsonify({"error": "field", "field": "envelope_factor",
                        "message": "envelope_factor must be in (0, 10]"}), 400

    sizing_params = {
        k_: float(data.get(k_, v))
        for k_, v in {
            "Cp": 4200.0, "mfls": 0.05, "rbore": 0.06, "rpin": 0.01365,
            "rpext": 0.0167, "kgrout": 1.5, "kpipe": 0.42, "LU": 0.0511, "hconv": 1000.0,
        }.items()
    }

    try:
        result = run_strategy(
            building_type=building_type,
            climate_zone=climate_zone,
            k=k, alpha=alpha, T_g=T_g,
            NB=NB, B=B, A=A,
            H_min=H_min,
            ldc_cutoff_pct=ldc_cutoff_pct,
            ignore_top_pct=ignore_top_pct,
            imbalance_threshold=imbalance_threshold,
            floor_area_m2=floor_area_m2,
            year_factor=year_factor,
            envelope_factor=envelope_factor,
            state=state,
            **sizing_params,
        )
    except KeyError as exc:
        return jsonify({"error": "field", "message": f"Unknown building_type or climate_zone: {exc}"}), 400
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    return jsonify(result.to_dict())


@app.route("/dev")
def developer():
    """Developer-only pipeline dashboard — not linked from the public UI."""
    return render_template("dev.html")

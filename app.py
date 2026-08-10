import csv as csv_mod
import re
import sys
import os
import json
import math
import pathlib
sys.path.insert(0, os.path.dirname(__file__))


from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from werkzeug.exceptions import BadRequest
from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import (
    BUILDING_SHAPES, DEFAULT_SHAPE,
    compute_nb_range, find_optimal_nb, load_implied_nb_range,
)
from geosite.s4_sizing.defaults import ADVANCED_DEFAULTS, T_IN_HP_DEFAULTS
from geosite.s1_site import get_site_data
from geosite.s2_simulation import get_loads
from geosite.s2_simulation.envelope import (
    WWR_OPTIONS, ENVELOPE_OPTIONS, GLAZING_OPTIONS,
    compute_envelope_factor, get_envelope_factors,
)
from geosite.models import SiteData, LoadPulses
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy import run_strategy
from geosite.s7_report import build_report

app = Flask(__name__)
_is_production = os.environ.get("FLASK_ENV", "").lower() == "production"

# ── In-memory analytics log (resets on restart; good enough for demo) ──
import datetime
_analytics_log = []   # list of dicts, newest first
_DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "geoloop-admin")
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if _is_production and not _secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be set in production")
app.secret_key = _secret_key or "geosite-dev-local-only"
_DEV_PASSWORD = os.environ.get("DEV_PASSWORD", "")  # set DEV_PASSWORD in .env for local, env var in production

_PUBLIC_DATA = pathlib.Path(__file__).parent / "data" / "public"


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/log-analysis", methods=["POST", "OPTIONS"])
def log_analysis():
    """Record one analysis event for the dashboard."""
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
    try:
        ev = request.get_json(force=True, silent=True) or {}
    except Exception:
        ev = {}
    ev["_ts"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _analytics_log.insert(0, ev)
    if len(_analytics_log) > 500:          # keep last 500 events
        _analytics_log.pop()
    return _cors_headers(jsonify({"ok": True}))


@app.route("/dashboard")
def dashboard():
    pw = request.args.get("pw", "")
    if pw != _DASHBOARD_PASSWORD:
        return Response("Unauthorized — add ?pw=<password> to URL", status=401,
                        content_type="text/plain")
    return render_template("dashboard.html")


@app.route("/api/dashboard-data")
def dashboard_data():
    pw = request.args.get("pw", "")
    if pw != _DASHBOARD_PASSWORD:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"events": _analytics_log})


@app.after_request
def _no_cache_mobile_pages(response):
    """Ensure Safari does not retain an old hidden account-page shell."""
    if request.path == "/mobile" or request.path == "/app" or request.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/landing")
def landing():
    return render_template("landing.html")


@app.route("/tool")
def tool():
    return render_template("index.html")


@app.route("/mobile")
def mobile():
    """GeoLoop mobile wizard — phone preview with all wizard pages."""
    return render_template("phone_preview.html")


@app.route("/app")
def app_web():
    """GeoLoop mobile wizard — direct web access without phone frame."""
    return render_template("welcome.html")


@app.route("/<page>.html")
def serve_html_page(page):
    """Serve any mobile-flow template by its .html filename.
    Allows relative navigation links (e.g. stage1a.html → /stage1a.html) to work
    both inside the phone iframe and when accessed directly in a browser.
    """
    allowed = {
        "welcome", "onboarding_1", "onboarding_2", "units",
        "stage1a", "stage1b", "stage1c", "stage2",
        "result_1", "result_final", "result_strategy", "result_report",
        "signup", "account", "phone_preview",
    }
    if page not in allowed:
        from flask import abort
        abort(404)
    return render_template(f"{page}.html")


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
    if not (0.05 <= values["rbore"] <= 0.15):
        return jsonify({"error": "field", "field": "rbore",
                        "message": "Borehole radius must be between 0.05 and 0.15 m"}), 400
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


# Canonical defaults live in geosite.s4_sizing.defaults; aliases kept for
# backward compatibility with existing references.
_ADVANCED_DEFAULTS = ADVANCED_DEFAULTS
_T_IN_HP_DEFAULTS = T_IN_HP_DEFAULTS
_H_MAX = 400.0   # maximum practical drill-rig depth [m] for commercial rotary rigs (item 21)


def _parse_advanced_params(data):
    """Parse + range-validate advanced borehole/fluid overrides.

    Returns (params_dict, None) on success or (None, flask_error_tuple).
    T_in_HP* values stay in `data` (consumed by _run_sizing); they are only
    checked for numeric validity here.
    """
    params = {}
    for key, default in ADVANCED_DEFAULTS.items():
        raw = data.get(key, default)
        if raw is None or str(raw).strip() == "":
            raw = default
        try:
            params[key] = float(raw)
        except (ValueError, TypeError):
            label = _FIELD_LABELS.get(key, key)
            return None, (jsonify({"error": "field", "field": key,
                                   "message": f"{label} must be a number"}), 400)

    if not (0.05 <= params["rbore"] <= 0.15):
        return None, (jsonify({"error": "field", "field": "rbore",
                               "message": "Borehole radius must be between 0.05 and 0.15 m"}), 400)
    for key in ("Cp", "mfls", "kgrout", "kpipe", "hconv", "LU", "rpin", "rpext"):
        if params[key] <= 0:
            label = _FIELD_LABELS.get(key, key)
            return None, (jsonify({"error": "field", "field": key,
                                   "message": f"{label} must be positive"}), 400)
    if not (params["rpin"] < params["rpext"] < params["rbore"]):
        return None, (jsonify({"error": "field", "field": "rpext",
                               "message": "Pipe inner radius must be less than pipe outer radius, "
                                          "which must be less than the borehole radius"}), 400)
    if not (params["LU"] < 2 * params["rbore"]):
        return None, (jsonify({"error": "field", "field": "LU",
                               "message": "U-tube spacing must be less than the borehole diameter"}), 400)

    for key in ("T_in_HP", "T_in_HP_heat", "T_in_HP_cool"):
        if data.get(key) not in (None, ""):
            try:
                float(data[key])
            except (ValueError, TypeError):
                return None, (jsonify({"error": "field", "field": key,
                                       "message": f"'{key}' must be a number"}), 400)

    return params, None


def _parse_footprint_opts(data):
    """Parse optional footprint controls: num_floors and footprint_shape.

    Returns ((num_floors, shape), None) or (None, flask_error_tuple).
    num_floors is None when blank/absent (DOE prototype floor count used).
    """
    num_floors = None
    raw = data.get("num_floors")
    if raw is not None and str(raw).strip() != "":
        try:
            num_floors = int(raw)
        except (ValueError, TypeError):
            return None, (jsonify({"error": "field", "field": "num_floors",
                                   "message": "Number of floors must be an integer"}), 400)
        if num_floors < 1:
            return None, (jsonify({"error": "field", "field": "num_floors",
                                   "message": "Number of floors must be >= 1"}), 400)

    shape = str(data.get("footprint_shape") or DEFAULT_SHAPE).strip().lower()
    if shape not in BUILDING_SHAPES:
        return None, (jsonify({"error": "field", "field": "footprint_shape",
                               "message": f"'footprint_shape' must be one of {sorted(BUILDING_SHAPES)}"}), 400)
    return (num_floors, shape), None


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

# 3–4 tier shorthand for the UI dropdown (maps to a representative year_built)
VINTAGE_TIERS = {
    "new":      2022,   # < ~5 years old
    "recent":   2010,   # ~5–15 years old
    "existing": 1998,   # ~15–30 years old
    "old":      1975,   # 30+ years old
}

# Borehole field layout configurations; only "perimeter" is implemented in v1
BOREHOLE_CONFIGS = {"perimeter", "parking_lot", "under_building"}


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


_FIELD_LABELS = {
    "zip_code":        "ZIP Code",
    "building_type":   "Building Type",
    "floor_area_m2":   "Total Floor Area",
    "num_floors":      "Number of Floors",
    "footprint_shape": "Footprint Shape",
    "building_age":    "Building Age",
    "soil_confidence": "Thermal Conductivity Source",
    "H_min":           "Borehole Depth",
    "B":               "Borehole Spacing",
    "NB":              "Number of Boreholes",
    "rbore":           "Borehole Radius",
    "rpin":            "Pipe Inner Radius",
    "rpext":           "Pipe Outer Radius",
    "LU":              "U-tube Shank Spacing",
    "kgrout":          "Grout Conductivity",
    "kpipe":           "Pipe Conductivity",
    "hconv":           "Convection Coefficient",
    "Cp":              "Fluid Heat Capacity",
    "mfls":            "Flow Rate",
    "T_in_HP_heat":    "Minimum Loop Temperature (Heating)",
    "T_in_HP_cool":    "Maximum Loop Temperature (Cooling)",
    "wwr":             "Window-Wall Ratio",
    "envelope":        "Infiltration & Insulation",
    "glazing":         "Glazing Type",
    "load_scale":      "Load Scale Factor",
    "borehole_config": "Layout Configuration",
    "k":               "Ground Thermal Conductivity",
    "alpha":           "Ground Thermal Diffusivity",
    "T_g":             "Ground Temperature",
    "A":               "Aspect Ratio",
    "envelope_factor": "Envelope Factor",
    "q_h":             "Peak Ground Load (hourly)",
    "q_m":             "Peak Ground Load (monthly)",
    "q_y":             "Annual Ground Load",
}


_FIELD_REQUIRED_MSGS = {
    "zip_code":      "Location required — please enter a 5-digit US ZIP code.",
    "building_type": "Please select a building type to continue.",
}

def _field_err(field, msg=None):
    """Return a JSON 400 response with a human-readable field label."""
    if msg is None:
        msg = _FIELD_REQUIRED_MSGS.get(field) or f"{_FIELD_LABELS.get(field, field)} is required."
    return jsonify({"error": "field", "field": field, "message": msg}), 400


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
            return None, _field_err(field)

    zip_code = str(data["zip_code"]).strip()
    if not re.match(r'^\d{5}$', zip_code):
        return None, _field_err("zip_code", "Please enter a valid 5-digit US ZIP code (e.g. 60601).")
    building_type = str(data["building_type"]).strip()

    # Optional: floor area scaling
    floor_area_m2 = None
    if data.get("floor_area_m2") and str(data["floor_area_m2"]).strip():
        try:
            floor_area_m2 = float(data["floor_area_m2"])
            if floor_area_m2 <= 0:
                return None, _field_err("floor_area_m2", "Total Floor Area must be a positive number.")
        except (ValueError, TypeError):
            return None, _field_err("floor_area_m2", "Total Floor Area must be a number.")

    # Optional: number of floors + footprint shape
    fp_opts, err = _parse_footprint_opts(data)
    if err:
        return None, err
    num_floors, footprint_shape = fp_opts

    # Optional: construction year → continuous load factor vs 90.1-2019 prototype
    # Also accepts building_age tier ("new"/"recent"/"existing"/"old"); year_built takes precedence.
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
    elif "building_age" in data and str(data.get("building_age", "")).strip():
        tier = str(data["building_age"]).strip().lower()
        if tier in VINTAGE_TIERS:
            year_built = VINTAGE_TIERS[tier]
        # unknown tier → silently fall back to default 2020
    year_factor = _year_to_load_factor(year_built)

    # Soil confidence: always use the ML-predicted k value directly (no user input).
    # The tool's value proposition is the public dataset + ML model — no manual confidence tier needed.
    soil_confidence = "medium"
    k_factor = 1.00

    # Infer glazing/envelope defaults from building age when user omits them or selects "unknown".
    # Pre-1985: likely single pane + leaky; 1985+ double-pane clear (not low-E, which is post-2000).
    _data = dict(data)
    if not str(_data.get("glazing", "")).strip() or _data.get("glazing") == "unknown":
        _data["glazing"] = "single" if year_built < 1985 else "double_legacy"
    if not str(_data.get("envelope", "")).strip() or _data.get("envelope") == "unknown":
        _data["envelope"] = "low" if year_built < 1985 else "standard"
    if not str(_data.get("wwr", "")).strip() or _data.get("wwr") == "unknown":
        _data["wwr"] = "wwr_20_40"  # prototype default: ~30% glazing (midpoint of 20-40% bin)

    design, err = _parse_design_fields(_data)
    if err:
        return None, err
    wwr, envelope, glazing, envelope_factor = design

    # Optional: borehole field layout configuration
    borehole_config = str(data.get("borehole_config", "perimeter")).strip().lower()
    if borehole_config not in BOREHOLE_CONFIGS:
        return None, (jsonify({"error": "field", "field": "borehole_config",
                               "message": f"must be one of {sorted(BOREHOLE_CONFIGS)}"}), 400)
    if borehole_config != "perimeter":
        return None, (jsonify({"error": "field", "field": "borehole_config",
                               "message": f"'{borehole_config}' layout not yet implemented; "
                                          "only 'perimeter' is supported in v1"}), 400)

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
    # Use climate-specific heat/cool split factors now that climate_zone is known.
    heat_f, cool_f = get_envelope_factors(
        site.climate_zone, building_type, wwr, glazing, envelope
    )
    try:
        loads: LoadPulses = get_loads(building_type, site.climate_zone,
                                      floor_area_m2=floor_area_m2,
                                      heat_factor=heat_f, cool_factor=cool_f)
    except KeyError as exc:
        return None, (jsonify({"error": "field", "field": "building_type",
                               "message": str(exc)}), 400)

    # Optional: prototype load scale override — for specialty buildings where the
    # DOE prototype EUI is known to be off (e.g. high-intensity grocery vs restaurant_fastfood).
    # Range 0.1–10.0; default 1.0 (no correction).
    load_scale = 1.0
    if data.get("load_scale") not in (None, ""):
        try:
            load_scale = float(data["load_scale"])
        except (ValueError, TypeError):
            return None, (jsonify({"error": "field", "field": "load_scale",
                                   "message": "load_scale must be a number"}), 400)
        if not (0.1 <= load_scale <= 10.0):
            return None, (jsonify({"error": "field", "field": "load_scale",
                                   "message": "load_scale must be between 0.1 and 10.0"}), 400)

    # Apply construction year + prototype scale corrections to all pulses (NaN-safe)
    combined_scale = year_factor * load_scale

    def _scale(v: float) -> float:
        return v * combined_scale if v == v else float("nan")

    loads = LoadPulses(
        q_h=loads.q_h * combined_scale,
        q_m=loads.q_m * combined_scale,
        q_y=loads.q_y * combined_scale,
        q_h_heat=_scale(loads.q_h_heat),
        q_m_heat=_scale(loads.q_m_heat),
        q_h_cool=_scale(loads.q_h_cool),
        q_m_cool=_scale(loads.q_m_cool),
    )

    # Dominant mode for backward-compat labels and single-pass fallback
    mode = "heating" if loads.q_h < 0 else "cooling"

    # Use ML-predicted k directly as the effective value (no manual confidence factor).
    effective_k = site.k

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
            "heat_factor": heat_f,
            "cool_factor": cool_f,
            # envelope_factor for /api/strategy: conservative max(heat, cool) is correct
            # because strategy.py applies a single scalar to the full 8760h profile.
            # Using mode-dependent selection was wrong when energy-volume dominance
            # disagreed with L_h vs L_c dominance (item 27).
            "envelope_factor": max(heat_f, cool_f),
            "load_scale": load_scale,
        },
        "building_type": building_type,
        "floor_area_m2": floor_area_m2,
        "num_floors": num_floors,
        "footprint_shape": footprint_shape,
        "borehole_config": borehole_config,
        "effective_k": effective_k,
        "loads_obj": loads,
    }, None


def _load_density_check(q_pulses, H_min, nb_max):
    """Advisory load-density NB range (15-70 W/m rule) + footprint capacity flag.

    Uses the governing peak magnitude across both modes. Never re-bounds the
    geometric optimizer range.
    """
    q_gov = max(
        abs(q_pulses.get("q_h_heat") or 0.0),
        abs(q_pulses.get("q_h_cool") or 0.0),
        abs(q_pulses["q_h"]),
    )
    lo, hi = load_implied_nb_range(q_gov, H_min)
    return {
        "nb_load_min": lo,
        "nb_load_max": hi,
        "capacity_warning": bool(nb_max is not None and lo > nb_max),
    }


def _run_sizing(*, q_pulses, effective_k, alpha, T_g, building_type,
                floor_area_m2, NB, H_min, B, A, params, data):
    """Shared s4 half. q_pulses = dict with q_h..q_m_cool (None allowed for mode split).
    Returns (result_dict, None) or (None, error_response).
    result_dict keys: L, H, NB, nb_min, nb_max, H_min, footprint, nb_source,
    governing, L_heat, L_cool, imbalance_m, solar_thermal_recommended.
    """
    q_h, q_m, q_y = q_pulses["q_h"], q_pulses["q_m"], q_pulses["q_y"]
    mode = "heating" if q_h < 0 else "cooling"

    fp_opts, err = _parse_footprint_opts(data)
    if err:
        return None, err
    num_floors, footprint_shape = fp_opts

    nb_min = nb_max = None
    fp_meta = None
    capacity_capped = False
    if NB is None:
        try:
            nb_min, nb_max, fp_meta = compute_nb_range(
                floor_area_m2, building_type, spacing_m=B,
                shape=footprint_shape, num_floors=num_floors)
        except (KeyError, ValueError) as exc:
            return None, (jsonify({"error": "field", "field": "building_type",
                                   "message": str(exc)}), 400)
        # Capacity check: warns when load density exceeds what the footprint
        # can supply at H_min.  Advisory only — the optimizer uses nb_max as
        # the upper bound and will find the best NB within [nb_min, nb_max]
        # while still satisfying H_min ≤ H ≤ H_max.  We must NOT force
        # NB_fixed = nb_max here; doing so bypasses the optimizer and sends a
        # fixed-NB call to size_borefield(), which oscillates when NB is too
        # large relative to the load (Tp correction drives H below B → x > 1
        # → Tp = 0 → L collapses to a physically impossible 2-3 m depth).
        load_check = _load_density_check(q_pulses, H_min, nb_max)
        capacity_capped = bool(load_check["capacity_warning"])
    else:
        load_check = {"nb_load_min": None, "nb_load_max": None,
                      "capacity_warning": None}

    # NB_fixed is only set for explicit expert overrides (the NB field).
    # capacity_capped is advisory: the optimizer handles [nb_min, nb_max].
    NB_fixed = NB  # None unless user explicitly set a borehole count

    # --- s4: two-pass borefield sizing ---
    # Run for both heating and cooling; the mode requiring more borefield governs.
    # A negative result from either pass means that mode's constraint is not binding.
    _has_both = all(q_pulses.get(key) is not None
                    for key in ("q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"))

    try:
        if _has_both:
            T_heat = float(data.get("T_in_HP_heat", _T_IN_HP_DEFAULTS["heating"]))
            T_cool = float(data.get("T_in_HP_cool", _T_IN_HP_DEFAULTS["cooling"]))
            if NB_fixed is not None:
                L_heat = size_borefield(
                    q_h=q_pulses["q_h_heat"], q_m=q_pulses["q_m_heat"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_heat, B=B, NB=NB_fixed, A=A, **params,
                )
                L_cool = size_borefield(
                    q_h=q_pulses["q_h_cool"], q_m=q_pulses["q_m_cool"], q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_cool, B=B, NB=NB_fixed, A=A, **params,
                )
                governing = "heating" if L_heat >= L_cool else "cooling"
                L = max(L_heat, L_cool)
                NB_out, H = NB_fixed, L / NB_fixed
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
            if NB_fixed is not None:
                L = size_borefield(
                    q_h=q_h, q_m=q_m, q_y=q_y,
                    k=effective_k, alpha=alpha, T_g=T_g,
                    T_in_HP=T_in_HP, B=B, NB=NB_fixed, A=A, **params,
                )
                NB_out, H = NB_fixed, L / NB_fixed
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
    elif capacity_capped:
        nb_source = "capacity_capped"
    elif NB_out < nb_min:
        nb_source = "depth_fallback"
    elif H > _H_MAX:
        nb_source = "depth_too_deep"
    else:
        nb_source = "optimizer"

    # Thermal imbalance metrics (only meaningful when two-pass ran)
    imbalance_m = round(abs(L_heat - L_cool)) if (L_heat is not None and L_cool is not None) else None
    # Ground cools over time when net annual extraction (q_y < 0); solar thermal can offset
    solar_thermal_recommended = q_y < 0

    return {
        **load_check,
        "L": round(L),
        "H": round(H),
        "NB": NB_out,
        "nb_min": nb_min,
        "nb_max": nb_max,
        "H_min": None if NB is not None else H_min,
        "footprint": ({**fp_meta, "nb_min": nb_min, "nb_max": nb_max}
                      if fp_meta is not None else None),
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
    for field in ("zip_code", "building_type", "B"):
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    B = float(data["B"])
    # A (Tp polynomial aspect ratio) defaults to 9.0 — allows up to 3:1 elongation.
    # User tool omits this; dev tool can override explicitly.
    A = float(data["A"]) if data.get("A") not in (None, "") else 9.0

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
        H_min = float(data.get("H_min", 150.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be a number"}), 400
    if not (30.0 <= H_min <= 600.0):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "Borehole depth must be between 30 and 600 m"}), 400

    if NB is not None and NB < 1:
        return jsonify({"error": "field", "field": "NB",
                        "message": "NB must be >= 1"}), 400
    if A < 1:
        return jsonify({"error": "field", "field": "A",
                        "message": "A must be >= 1"}), 400

    payload, err = _resolve_site_and_loads(data)
    if err:
        return err

    params, err = _parse_advanced_params(data)
    if err:
        return err

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
            payload["floor_area_m2"], payload["building_type"], spacing_m=6.0,
            shape=payload["footprint_shape"], num_floors=payload["num_floors"])
    except (KeyError, ValueError) as exc:
        return jsonify({"error": "field", "field": "building_type",
                        "message": str(exc)}), 400

    load_check = _load_density_check(payload["loads"], 150.0, nb_max)

    return jsonify({
        "site": payload["site"],
        "loads": payload["loads"],
        "nb_estimate": {
            **fp_meta,                     # pts, shape_label, n_floors, spacing_m, …
            "nb_min": nb_min, "nb_max": nb_max, "spacing_m": 6.0,
            "footprint": fp_meta,
            **load_check,
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
        H_min = float(data.get("H_min", 150.0))
    except (ValueError, TypeError):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "H_min must be a number"}), 400
    if not (30.0 <= H_min <= 600.0):
        return jsonify({"error": "field", "field": "H_min",
                        "message": "Borehole depth must be between 30 and 600 m"}), 400

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

    params, err = _parse_advanced_params(data)
    if err:
        return err

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


@app.route("/api/deep_thermal")
def deep_thermal_api():
    """Return county-level deep borehole thermal properties (k, α, T_g) for vertical sizing.

    Two-track method (Blackwell & Richards 2004; Clauser & Huenges 1995):
      Track A — IDW from SMU quality A+B k measurements where ≥3 points in 200 km
      Track B — SGMC rock class → Clauser & Huenges (1995) median k (fallback)
    T_g at 100 m borehole midpoint = surface T_g + 0.100 km × geothermal gradient.

    Response: JSON dict keyed by 5-digit county FIPS.
    """
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


@app.route("/api/cost", methods=["POST", "OPTIONS"])
def cost_api():
    """Estimate borefield installation cost given sizing output.

    Required body fields: L (meters), NB (int), B (meters), state (2-letter abbrev or null)
    Optional: rock_class (SGMC rock class name), distance_to_house_ft (float, default 100)
    """
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
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

    # Optional: peak_load_kw → compute GSHP equipment cost estimate
    # $600/kW is the midpoint for commercial GSHP equipment ($1,500–$3,500/ton installed equipment)
    _HP_USD_PER_KW = 600.0
    # Peaker equipment: gas/electric boiler ~$150/kW, chiller ~$300/kW (installed, commercial)
    _PEAKER_USD_PER_KW = {"electric_heater": 150.0, "chiller": 300.0,
                          "electric_heater+chiller": 225.0}  # average when both
    peak_load_kw = None
    hp_equipment_usd = None
    peak_tons = None
    peaker_equipment_usd = None
    raw_peak = data.get("peak_load_kw")
    if raw_peak not in (None, ""):
        try:
            peak_load_kw = float(raw_peak)
            if peak_load_kw > 0:
                hp_equipment_usd = round(peak_load_kw * _HP_USD_PER_KW, 0)
                peak_tons = round(peak_load_kw / 3.517, 1)
        except (ValueError, TypeError):
            pass

    raw_peaker_kw   = data.get("peaker_kw")
    raw_peaker_type = str(data.get("peaker_type") or "").strip()
    if raw_peaker_kw not in (None, ""):
        try:
            pkw = float(raw_peaker_kw)
            if pkw > 0:
                rate = _PEAKER_USD_PER_KW.get(raw_peaker_type, 225.0)
                peaker_equipment_usd = round(pkw * rate, 0)
        except (ValueError, TypeError):
            pass

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

    out = {
        "best":  _cr(result["best"]),
        "base":  _cr(result["base"]),
        "worst": _cr(result["worst"]),
        "headline_per_ft": round(result["headline_per_ft"], 2),
        "region_used": result["region_used"],
    }
    if hp_equipment_usd is not None:
        out["hp_equipment_usd"] = hp_equipment_usd
        out["peak_tons"] = peak_tons
        out["peak_load_kw"] = round(peak_load_kw, 1)
    if peaker_equipment_usd is not None:
        out["peaker_equipment_usd"] = peaker_equipment_usd
        out["peaker_kw"] = round(float(raw_peaker_kw), 1)
        out["peaker_type"] = raw_peaker_type
    return _cors_headers(jsonify(out))


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


@app.route("/api/strategy", methods=["POST", "OPTIONS"])
def strategy_api():
    """Run mandatory hybrid GSHP strategy analysis.

    Required: building_type, climate_zone, k, alpha, T_g, NB, B, A
    Optional: state (2-letter abbrev or null), ldc_cutoff_pct (default 10), imbalance_threshold (default 1.25),
              floor_area_m2, year_built (int), year_factor (float, overrides year_built)
              Advanced: Cp, mfls, rbore, rpin, rpext, kgrout, kpipe, LU, hconv
    """
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
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
    H_min               = float(data.get("H_min") or 150.0)
    ignore_top_pct      = float(data.get("ignore_top_pct", 0.4))
    peaker_purpose      = str(data.get("peaker_purpose") or "auto").strip()
    if peaker_purpose not in ("auto", "heating", "cooling", "both", "none"):
        peaker_purpose = "auto"

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

    sizing_params, err = _parse_advanced_params(data)
    if err:
        return err

    # Accept pre-computed q values from the analyze pipeline so the strategy
    # uses the exact same thermal loads as /size (prevents H_before vs H mismatch).
    precomputed_q = {}
    for qkey in ("q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool", "q_y"):
        v = data.get(qkey)
        if v is not None:
            try:
                precomputed_q[qkey] = float(v)
            except (TypeError, ValueError):
                pass

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
            peaker_purpose=peaker_purpose,
            precomputed_q=precomputed_q if precomputed_q else None,
            **sizing_params,
        )
    except KeyError as exc:
        return jsonify({"error": "field", "message": f"Unknown building_type or climate_zone: {exc}"}), 400
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    # --- Hybrid two-option cost comparison ---
    # Option A: same NB boreholes, reduce depth (H_after = L_after/NB)
    # Option B: same depth as base (H_before), reduce borehole count
    d = result.to_dict()

    # Compute annual heat/cool from hourly profile server-side so result_report.html
    # doesn't need to loop 8760 values client-side (avoids sessionStorage truncation risks).
    _profile = result.hourly_profile
    _heat_kwh = round(sum(abs(w) for w in _profile if w < 0) / 1000, 1)
    _cool_kwh = round(sum(w for w in _profile if w > 0) / 1000, 1)
    d['annual_heat_kwh_th'] = _heat_kwh
    d['annual_cool_kwh_th'] = _cool_kwh
    try:
        _NB = result.NB
        _H_before = result.H_before
        _L_after = result.L_after
        _H_after = result.H_after

        _NB_b = max(1, math.ceil(_L_after / _H_before)) if _H_before > 0 else _NB
        _L_b = _NB_b * _H_before

        _ca = estimate_cost(L_m=_L_after, NB=_NB, B_m=B, state=state)
        _cb = estimate_cost(L_m=_L_b, NB=_NB_b, B_m=B, state=state)

        _cheaper = 'a' if _ca['base'].total_usd <= _cb['base'].total_usd else 'b'
        d['hybrid_opt_a'] = {
            'NB': _NB, 'H': round(_H_after), 'L': round(_L_after),
            'cost_usd': round(_ca['base'].total_usd),
        }
        d['hybrid_opt_b'] = {
            'NB': _NB_b, 'H': round(_H_before), 'L': round(_L_b),
            'cost_usd': round(_cb['base'].total_usd),
        }
        d['hybrid_cheaper'] = _cheaper
    except Exception:
        pass  # non-critical; frontend falls back to existing H_after/L_after

    return _cors_headers(jsonify(d))


@app.route("/api/report", methods=["POST", "OPTIONS"])
def report_api():
    """s7 — fixed-structure deterministic report + recommendation score.

    Body: {design, site, loads: dict; cost, strategy: dict|null;
           annual_heat_kwh_th, annual_cool_kwh_th: float}
    """
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    for field in ("design", "site", "loads"):
        if not isinstance(data.get(field), dict):
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' must be an object"}), 400
    for field in ("cost", "strategy"):
        if data.get(field) is not None and not isinstance(data[field], dict):
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' must be an object or null"}), 400
    for field in ("annual_heat_kwh_th", "annual_cool_kwh_th"):
        try:
            data[field] = float(data.get(field, 0.0))
            if not math.isfinite(data[field]):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' must be a number"}), 400

    try:
        report = build_report(data)
    except Exception as exc:
        return jsonify({"error": "calculation", "message": str(exc)}), 500

    return _cors_headers(jsonify({"report": report,
                                  "recommendation": report["recommendation"]}))


@app.route("/dev")
def developer():
    """Developer-only pipeline dashboard — password protected."""
    if not session.get("dev_auth"):
        return redirect(url_for("dev_login"))
    return render_template("dev.html")


_DEV_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Developer Access</title>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="/static/tool.css">
  <style>
    .dev-login-wrap { min-height: 100dvh; display: flex; align-items: center; justify-content: center; }
    .dev-login-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 40px 36px; width: 100%; max-width: 360px; box-shadow: var(--shadow); }
    .dev-login-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
    .dev-login-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 28px; }
    .dev-login-card input[type=password] { display: block; width: 100%; padding: 9px 12px; font-family: var(--font-sans); font-size: 14px; color: var(--text); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); margin-bottom: 14px; box-sizing: border-box; }
    .dev-login-card input[type=password]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(5,150,105,0.12); }
    .dev-login-card button { display: block; width: 100%; padding: 11px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-family: var(--font-sans); font-size: 14px; font-weight: 600; cursor: pointer; }
    .dev-login-card button:hover { background: var(--accent-hover); }
    .dev-login-err { color: #b91c1c; font-size: 13px; margin-top: 10px; }
    .dev-back { display: inline-block; margin-top: 18px; font-size: 13px; color: var(--text-muted); text-decoration: none; }
    .dev-back:hover { color: var(--text); }
  </style>
</head>
<body class="t-body">
  <div class="dev-login-wrap">
    <div class="dev-login-card">
      <div class="dev-login-title">Developer Mode</div>
      <div class="dev-login-sub">Enter the developer password to continue.</div>
      <form method="post" action="/dev-login">
        <input type="password" name="password" placeholder="Password" autofocus autocomplete="current-password">
        <button type="submit">Unlock</button>
        {% if error %}<div class="dev-login-err">Incorrect password. Try again.</div>{% endif %}
      </form>
      <a href="/" class="dev-back">&larr; Back to tool</a>
    </div>
  </div>
</body>
</html>"""


@app.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    error = False
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == _DEV_PASSWORD:
            session["dev_auth"] = True
            return redirect(url_for("developer"))
        error = True
    from flask import render_template_string
    return render_template_string(_DEV_LOGIN_HTML, error=error)


# ── Mobile UI routes ─────────────────────────────────────────────────────────
# Thin shims that bridge the GeoLoop mobile HTML field names to the existing
# pipeline endpoints.  Served at /analyze and /size; both accept CORS so the
# pages load correctly whether served from Flask (5001) or Live Server (5501).

def _cors_headers(resp):
    allowed = {item.strip() for item in os.environ.get("CORS_ORIGINS", "").split(",") if item.strip()}
    origin = request.headers.get("Origin")
    if origin and origin in allowed:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp

def _mobile_wwr_to_bin(s_wwr: str) -> str:
    """Map the mobile slider's ``wwr_NN`` value to the pipeline category."""
    try:
        pct = int(str(s_wwr).replace("wwr_", ""))
    except (ValueError, AttributeError):
        return "medium"
    if pct <= 20: return "low"
    if pct <= 40: return "medium"
    return "high"

def _suitability_score(k: float, T_g: float, climate_zone: str) -> int:
    """Heuristic 0-100 geothermal suitability score for the mobile results card."""
    k_score  = min(40, max(0, (k - 0.5) / 3.5 * 40))
    tg_score = max(0, 20 - abs(T_g - 13) * 2)
    zone_pts = {"4A":10,"4B":10,"4C":9,"5A":9,"5B":9,"5C":8,
                "3A":7,"3B":7,"3C":7,"6A":6,"6B":6,"2A":5,"2B":5}.get(climate_zone, 5)
    return int(min(100, 30 + k_score + tg_score + zone_pts))


@app.route("/analyze", methods=["POST", "OPTIONS"])
def mobile_analyze():
    """Mobile wizard stage-1 endpoint: site + loads.

    Accepts mobile UI field names (s_wwr / s_envelope / s_glazing) and returns
    a flattened response shaped for result_1.html.
    """
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))

    try:
        raw = request.get_json(force=True, silent=True) or {}
    except Exception:
        raw = {}

    # Remap mobile field names to the pipeline's expected names
    data = dict(raw)
    data["wwr"]           = _mobile_wwr_to_bin(str(raw.get("s_wwr", "wwr_30")))
    data["envelope"]      = str(raw.get("s_envelope", "standard"))
    data["glazing"]       = str(raw.get("s_glazing", "double_legacy"))
    data["borehole_config"] = "perimeter"

    # Normalise unknown/empty glazing/envelope so _resolve_site_and_loads auto-infers
    if data["glazing"]  in ("", "unknown"):  data["glazing"]  = "unknown"
    if data["envelope"] in ("", "unknown"):  data["envelope"] = "standard"

    payload, err = _resolve_site_and_loads(data)
    if err:
        return _cors_headers(err[0]), err[1]

    site  = payload["site"]
    loads = payload["loads"]

    # Borehole count hint from footprint (default 6 m spacing)
    nb_hint = None
    try:
        nb_min, nb_max, _ = compute_nb_range(
            payload["floor_area_m2"], payload["building_type"], spacing_m=6.0,
            shape=payload["footprint_shape"], num_floors=payload["num_floors"])
        nb_hint = round((nb_min + nb_max) / 2)
    except Exception:
        nb_min = nb_max = None

    q_h_display = loads.get("q_h_heat") or abs(loads.get("q_h", 0))
    q_c_display = loads.get("q_h_cool") or abs(loads.get("q_c", loads.get("q_h", 0)))

    result = {
        # Site fields
        "k":            round(site["k"], 2),
        "T_ground":     round(site["T_g"], 1),
        "climate_zone": site["climate_zone"],
        # Load fields — peaks only
        "q_h":  round(abs(q_h_display), 1),
        "q_c":  round(abs(q_c_display), 1),
        # Borehole capacity
        "n_boreholes_hint": nb_hint,
        "nb_min": nb_min,
        "nb_max": nb_max,
        # Pass-through for /size
        "site":  site,
        "loads": loads,
        "building_type":   payload["building_type"],
        "floor_area_m2":   payload["floor_area_m2"],
        "footprint_shape": payload["footprint_shape"],
        "num_floors":      payload["num_floors"],
    }
    return _cors_headers(jsonify(result))


@app.route("/size", methods=["POST", "OPTIONS"])
def mobile_size():
    """Mobile wizard stage-2 endpoint: borefield sizing + cost.

    Expects the echoed site/loads dicts from /analyze plus borehole parameters
    from stage2.html.  Returns a response shaped for result_final.html.
    """
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    # --- pull echoed stage-1 data ---
    site_in  = data.get("site")
    loads_in = data.get("loads")
    if not isinstance(site_in, dict) or not isinstance(loads_in, dict):
        return _cors_headers(jsonify({"error": "field",
                                      "message": "stage-1 site/loads missing"})), 400
    try:
        effective_k = float(site_in["k_effective"])
        alpha       = float(site_in["alpha"])
        T_g         = float(site_in["T_g"])
    except (KeyError, TypeError, ValueError):
        return _cors_headers(jsonify({"error": "field",
                                      "message": "site data incomplete"})), 400

    q_pulses = {}
    try:
        for key in ("q_h", "q_m", "q_y"):
            q_pulses[key] = float(loads_in[key])
        for key in ("q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"):
            v = loads_in.get(key)
            q_pulses[key] = float(v) if v is not None else None
    except (KeyError, TypeError, ValueError):
        return _cors_headers(jsonify({"error": "field",
                                      "message": "loads data incomplete"})), 400

    # --- borehole parameters ---
    try:
        H_min = float(data.get("borehole_depth", 150.0))
        B     = float(data.get("borehole_spacing", 6.0))
    except (ValueError, TypeError):
        H_min, B = 150.0, 6.0
    H_min = max(30.0, min(600.0, H_min))
    B     = max(3.0,  min(20.0, B))
    A     = 9.0   # default aspect ratio

    building_type  = str(data.get("building_type", "medium_office")).strip()
    floor_area_m2  = data.get("floor_area_m2")
    if floor_area_m2:
        try:
            floor_area_m2 = float(floor_area_m2)
        except (ValueError, TypeError):
            floor_area_m2 = None

    # Optional grout override
    adv_data = dict(data)
    if data.get("grout_k") not in (None, ""):
        adv_data["kgrout"] = data["grout_k"]

    params, err = _parse_advanced_params(adv_data)
    if err:
        return _cors_headers(err[0]), err[1]

    # --- sizing ---
    result, err = _run_sizing(
        q_pulses=q_pulses, effective_k=effective_k, alpha=alpha, T_g=T_g,
        building_type=building_type, floor_area_m2=floor_area_m2,
        NB=None, H_min=H_min, B=B, A=A, params=params, data=adv_data,
    )
    if err:
        return _cors_headers(err[0]), err[1]

    L, NB_out, H = result["L"], result["NB"], result["H"]

    # --- cost ---
    state = site_in.get("state_abbrev")
    rock_class = site_in.get("rock_class")
    try:
        cost_res = estimate_cost(L_m=float(L), NB=int(NB_out), B_m=B,
                                 state=state, rock_class_name=rock_class)
        def _fmt_k(usd): return "$" + str(round(usd / 1000)) + "k"
        cost_best  = _fmt_k(cost_res["best"].total_usd)
        cost_base  = _fmt_k(cost_res["base"].total_usd)
        cost_worst = _fmt_k(cost_res["worst"].total_usd)
    except Exception:
        cost_best = cost_base = cost_worst = "—"

    # --- thermal performance estimates ---
    cop_h = round(3.5 + max(0, (T_g - 5) / 15) * 1.0, 1)  # 3.5–4.5 COP vs T_g
    eer_c = round(14 + max(0, (20 - T_g) / 10) * 4)        # EER improves w/ lower T_g
    energy_savings_pct = 45   # typical GSHP vs gas+DX baseline

    # --- hybrid strategy text ---
    governing = result.get("governing", "heating")
    solar_rec = result.get("solar_thermal_recommended", False)
    imbalance = result.get("imbalance_m")
    if solar_rec:
        strategy = (
            f"Annual ground thermal imbalance detected (net extraction). "
            f"<span class='strategy-highlight'>Solar thermal recharge</span> is recommended "
            f"to maintain long-term ground temperature. Full geothermal covers "
            f"all peak {governing} demand."
        )
    elif imbalance and imbalance > 200:
        pct_red = round(min(30, imbalance / L * 100))
        strategy = (
            f"<span class='strategy-highlight'>Hybrid peak-shaving</span> boiler recommended "
            f"for the top ~{pct_red}% of {governing} load. This reduces borefield length "
            f"by ~{pct_red}% and improves economics without affecting 90%+ of annual "
            f"energy from the ground loop."
        )
    else:
        strategy = (
            f"Full geothermal coverage is cost-effective for this building. "
            f"A <span class='strategy-highlight'>single-stage GSHP</span> without supplemental "
            f"peak equipment is recommended. The ground loop handles 100% of "
            f"{governing}-dominated load."
        )

    # Land footprint estimate
    land_area = round(NB_out * B * B)

    out = {
        "n_boreholes":       NB_out,
        "borehole_depth":    round(H),
        "total_length":      L,
        "land_area":         land_area,
        "borehole_spacing":  B,
        "NB":                NB_out,
        "H":                 round(H),
        "L":                 L,
        "B":                 B,
        "A":                 A,
        "building_type":     building_type,
        "floor_area_m2":     floor_area_m2,
        "climate_zone":      site_in.get("climate_zone"),
        "governing":         result.get("governing"),
        "L_heat":            result.get("L_heat"),
        "L_cool":            result.get("L_cool"),
        "imbalance_m":       result.get("imbalance_m"),
        "nb_source":         result.get("nb_source"),
        "nb_min":            result.get("nb_min"),
        "nb_max":            result.get("nb_max"),
        "solar_thermal_recommended": result.get("solar_thermal_recommended"),
        "footprint":         result.get("footprint"),
        "site_passthrough":  site_in,
        "cost_best":         cost_best,
        "cost_base":         cost_base,
        "cost_worst":        cost_worst,
        "cop_heating":       cop_h,
        "eer_cooling":       eer_c,
        "energy_savings_pct": energy_savings_pct,
        "hybrid_strategy":   strategy,
    }
    return _cors_headers(jsonify(out))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False)

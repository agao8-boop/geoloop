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


@app.route("/calculate/smart", methods=["POST"])
def calculate_smart():
    """Automated pipeline: ZIP + building type → soil + loads → borefield length.

    Required body fields: zip_code, building_type, mode, NB, B, A
    Optional: T_in_HP, mfls, Cp, rbore, rpin, rpext, kgrout, kpipe, LU, hconv
    """
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    if data is None:
        return jsonify({"error": "field", "message": "Request body must be valid JSON"}), 400

    # --- validate required fields ---
    required = {"zip_code": str, "building_type": str, "mode": str,
                "NB": int, "B": float, "A": float}
    for field, _ in required.items():
        if field not in data or str(data[field]).strip() == "":
            return jsonify({"error": "field", "field": field,
                            "message": f"'{field}' is required"}), 400

    zip_code = str(data["zip_code"]).strip()
    building_type = str(data["building_type"]).strip()
    mode = str(data["mode"]).strip().lower()
    NB = int(data["NB"])
    B = float(data["B"])
    A = float(data["A"])

    if mode not in ("heating", "cooling"):
        return jsonify({"error": "field", "field": "mode",
                        "message": "mode must be 'heating' or 'cooling'"}), 400
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

    # --- s2: get building loads ---
    try:
        loads: LoadPulses = get_loads(building_type, site.climate_zone)
    except KeyError as exc:
        return jsonify({"error": "field", "field": "building_type",
                        "message": str(exc)}), 400

    # --- validate mode vs load sign ---
    heating_load = loads.q_h < 0
    if (mode == "heating" and not heating_load) or (mode == "cooling" and heating_load):
        return jsonify({
            "error": "field",
            "field": "mode",
            "message": (
                f"mode='{mode}' conflicts with the load profile for '{building_type}' "
                f"in climate zone '{site.climate_zone}'. "
                f"The loads are {'heating' if heating_load else 'cooling'}-dominant "
                f"(q_h={loads.q_h:.0f} W)."
            ),
        }), 422

    # --- resolve system parameters (user override or default) ---
    T_in_HP = float(data.get("T_in_HP", _T_IN_HP_DEFAULTS[mode]))
    params = {k: float(data.get(k, v)) for k, v in _ADVANCED_DEFAULTS.items()}

    # --- s4: borefield sizing ---
    try:
        L = size_borefield(
            q_h=loads.q_h, q_m=loads.q_m, q_y=loads.q_y,
            k=site.k, alpha=site.alpha, T_g=site.T_g,
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
            "alpha": site.alpha,
            "T_g": site.T_g,
            "climate_zone": site.climate_zone,
            "data_available": site.data_available,
        },
        "loads": {
            "q_h": loads.q_h,
            "q_m": loads.q_m,
            "q_y": loads.q_y,
        },
    })


@app.route("/references")
def references():
    refs = json.loads((_PUBLIC_DATA / "references.json").read_text())
    return render_template("references.html", categories=refs)


@app.route("/dev")
def developer():
    """Developer-only pipeline dashboard — not linked from the public UI."""
    return render_template("dev.html")


@app.route("/doc/workflow")
def workflow_doc():
    """Serve the master workflow markdown as readable HTML (developer only)."""
    import subprocess
    wf = pathlib.Path(__file__).parent / "docs" / "workflow.md"
    content = wf.read_text()
    # Simple markdown → HTML via basic transforms (no new package needed)
    import re, html
    lines = content.split('\n')
    body_html = []
    in_code = False
    for line in lines:
        if line.startswith('```'):
            if not in_code:
                body_html.append('<pre class="eq-block">')
                in_code = True
            else:
                body_html.append('</pre>')
                in_code = False
        elif in_code:
            body_html.append(html.escape(line))
        elif line.startswith('### '):
            body_html.append(f'<h3 style="margin:20px 0 8px;font-size:14px;color:#1a202c">{html.escape(line[4:])}</h3>')
        elif line.startswith('## '):
            body_html.append(f'<h2 style="margin:28px 0 10px;font-size:16px;font-weight:700;color:#1a202c;border-bottom:2px solid #dde1e7;padding-bottom:6px">{html.escape(line[3:])}</h2>')
        elif line.startswith('# '):
            body_html.append(f'<h1 style="font-size:22px;font-weight:700;margin-bottom:8px">{html.escape(line[2:])}</h1>')
        elif line.startswith('> '):
            body_html.append(f'<blockquote style="border-left:3px solid #2e7d5e;padding:8px 16px;margin:12px 0;color:#6b7280;font-style:italic;background:#f0faf5">{html.escape(line[2:])}</blockquote>')
        elif line.startswith('| '):
            body_html.append(f'<p style="font-family:monospace;font-size:12px;white-space:pre">{html.escape(line)}</p>')
        elif line.strip() == '---':
            body_html.append('<hr style="border:none;border-top:1px solid #dde1e7;margin:20px 0">')
        elif line.strip():
            body_html.append(f'<p style="margin:6px 0;font-size:13px;line-height:1.7;color:#374151">{html.escape(line)}</p>')
        else:
            body_html.append('<br>')
    html_content = '\n'.join(body_html)
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Workflow — GeoSite Advisor</title>
    <style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:820px;margin:0 auto;padding:40px 32px 80px;background:#f4f6f8;color:#1a202c}}
    .eq-block{{background:#1e2a38;color:#b0bec5;padding:16px;border-radius:6px;font-size:12px;line-height:1.8;overflow-x:auto;white-space:pre;margin:12px 0}}
    a{{color:#2e7d5e}}</style></head><body>
    <p style="font-size:12px;color:#6b7280;margin-bottom:24px"><a href="/dev">← Developer Dashboard</a></p>
    {html_content}
    </body></html>'''

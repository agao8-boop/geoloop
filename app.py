import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify
from geosite.s4_sizing.ashrae_sizing import size_borefield

app = Flask(__name__)


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

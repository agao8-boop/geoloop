#!/usr/bin/env python3
"""Build report-model case files (JSON) for report_model.html.

Each case is one simulation's content. Layout/blocks/fonts live in the model
HTML; only these values change per case.

- chicago.json : reproduces the original hand-made sample exactly (curve parsed
                 straight out of final_design.html so the model matches it 1:1).
- miami.json   : a second case. The load-profile curve and the heating/cooling
                 peaks are REAL, pulled from the precomputed EnergyPlus hourly
                 data (medium_office, zone 1A). Site/cost/sizing scalars are
                 representative placeholders (marked _note) until wired to the
                 full sizing+cost+strategy pipeline.
"""
import json, re, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CASES = HERE / "cases"
CASES.mkdir(exist_ok=True)
HOURLY = ROOT / "data" / "public" / "prototype_loads_hourly.json"


def chicago_curve_from_sample():
    """Parse the polyline out of final_design.html and convert y -> kW.
    Plot mapping in the sample: y=30 -> 400 kW, y=190 -> 0 kW (160 px / 400 kW)."""
    html = (HERE / "final_design.html").read_text()
    m = re.search(r'<polyline[^>]*points="([^"]+)"', html)
    pts = m.group(1).split()
    samples = []
    for p in pts:
        _x, y = p.split(",")
        kw = (190.0 - float(y)) / 160.0 * 400.0
        samples.append(round(max(0.0, kw), 1))
    return samples


def smooth(a, win=168):
    n = len(a)
    out = [0.0] * n
    half = win // 2
    csum = [0.0]
    for v in a:
        csum.append(csum[-1] + v)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half)
        out[i] = (csum[hi] - csum[lo]) / (hi - lo)
    return out


def real_case_loads(building_type, zone, n_points=200):
    """Return (samples_kw, peak_kw, peak_label, heat_kw, cool_kw) from real data."""
    data = json.loads(HOURLY.read_text())
    W = [float(v) for v in data[building_type][zone]]        # signed watts
    cool_kw = max(0.0, max(W)) / 1000.0                       # +ve = cooling
    heat_kw = max(0.0, -min(W)) / 1000.0                      # -ve = heating
    mag = [abs(v) / 1000.0 for v in W]                        # magnitude kW
    sm = smooth(mag, 168)
    step = len(sm) // n_points
    samples = [round(sm[min(i * step, len(sm) - 1)], 1) for i in range(n_points)]
    peak_idx = max(range(len(sm)), key=lambda i: sm[i])
    peak_kw = sm[peak_idx]
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    mlen = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    acc = 0
    mi = 0
    for j, h in enumerate(mlen):
        if acc + h > peak_idx:
            mi = j
            break
        acc += h
    day = (peak_idx - sum(mlen[:mi])) // 24 + 1
    return samples, round(peak_kw, 0), f"{months[mi]} {day}", round(heat_kw, 1), round(cool_kw, 0)


# ── Chicago: exact reproduction of the sample ──────────────────────────────
chicago = {
    "location": "Chicago, IL 60601",
    "site": {"climate_zone": "5A: Cool, Humid", "soil_k": "4.00",
             "ground_temp": "15.2", "diffusivity": "0.154"},
    "building": {"type": "Medium Office", "wwr": "30%", "infiltration": "Standard",
                 "glazing": "Double Low-E", "footprint_shape": "Rectangle (2:1)",
                 "floor_area_m2": "1,891", "n_floors": "6"},
    "cost": {"gshp_total": 1840000, "conv_total": 920000,
             "gshp_breakdown": [["Drilling & loops", 1120000], ["Heat pumps", 480000], ["Distribution", 240000]],
             "conv_breakdown": [["Boiler", 380000], ["Chiller", 410000], ["Distribution", 130000]],
             "net_savings": 620000},
    "feasibility": {"score": 81, "label": "Excellent", "benchmark": 70,
                    "bars": [["Soil conductivity", 32, 40], ["Climate balance", 22, 30],
                             ["Ground temperature", 17, 20], ["Building suitability", 10, 10]]},
    "hero": {"heating_kw": "78.7", "cooling_kw": "358", "boreholes": 23,
             "borehole_depth_m": 125, "peaker_kw": 149, "peaker_type": "Chiller"},
    "performance": {"dominant_mode": "cooling", "peaker_kw": 149, "peaker_type": "chiller",
                    "coverage_hours_pct": "98.2", "coverage_energy_pct": "87.5",
                    "borefield_reduction_pct": "42.3"},
    "borefield": {"nb": 23, "spacing_m": 6, "field_w_m": 61.5, "field_h_m": 30.7},
    "load_profile": {"ymax_kw": 400, "peak_kw": 238, "peak_label": "Jul 18",
                     "samples_kw": chicago_curve_from_sample()},
}

# ── Miami: real load curve + peaks, representative scalars ──────────────────
samples, peak_kw, peak_label, heat_kw, cool_kw = real_case_loads("medium_office", "1A")
miami = {
    "_note": "Load curve + heating/cooling peaks are REAL (medium_office, zone 1A). "
             "Site/cost/sizing/score values are representative placeholders until "
             "wired to the sizing+cost+strategy pipeline.",
    "location": "Miami, FL 33130",
    "site": {"climate_zone": "1A: Hot, Humid", "soil_k": "2.80",
             "ground_temp": "24.6", "diffusivity": "0.091"},
    "building": {"type": "Medium Office", "wwr": "30%", "infiltration": "Standard",
                 "glazing": "Double Low-E", "footprint_shape": "Rectangle (2:1)",
                 "floor_area_m2": "1,891", "n_floors": "6"},
    "cost": {"gshp_total": 2260000, "conv_total": 1060000,
             "gshp_breakdown": [["Drilling & loops", 1490000], ["Heat pumps", 520000], ["Distribution", 250000]],
             "conv_breakdown": [["Boiler", 210000], ["Chiller", 620000], ["Distribution", 230000]],
             "net_savings": -1200000},
    "feasibility": {"score": 63, "label": "Fair", "benchmark": 70,
                    "bars": [["Soil conductivity", 26, 40], ["Climate balance", 12, 30],
                             ["Ground temperature", 9, 20], ["Building suitability", 10, 10]]},
    "hero": {"heating_kw": heat_kw, "cooling_kw": cool_kw, "boreholes": 34,
             "borehole_depth_m": 130, "peaker_kw": 210, "peaker_type": "Chiller"},
    "performance": {"dominant_mode": "cooling", "peaker_kw": 210, "peaker_type": "chiller",
                    "coverage_hours_pct": "96.8", "coverage_energy_pct": "84.1",
                    "borefield_reduction_pct": "38.5"},
    "borefield": {"nb": 34, "spacing_m": 6, "field_w_m": 78.0, "field_h_m": 39.0},
    "load_profile": {"peak_kw": peak_kw, "peak_label": peak_label, "samples_kw": samples},
}

(CASES / "chicago.json").write_text(json.dumps(chicago, indent=2))
(CASES / "miami.json").write_text(json.dumps(miami, indent=2))
print("wrote", CASES / "chicago.json", "(", len(chicago["load_profile"]["samples_kw"]), "pts )")
print("wrote", CASES / "miami.json",
      f"(peak {peak_kw} kW {peak_label}, heat {heat_kw}, cool {cool_kw}, {len(samples)} pts)")

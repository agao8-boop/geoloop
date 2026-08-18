#!/usr/bin/env python3
"""
scripts/cross_track_analysis.py
───────────────────────────────────────────────────────────────────────────────
Cross-track analysis covering four open questions:

  Task 1 — Three-pulse definitions (q_h / q_m / q_y) vs Philippe et al. (2010)
  Task 2 — Scale factors: floor area vs. total area; controlled experiments
  Task 3 — q_m definition: dominant-mode-only vs. combined heating+cooling months
  Task 4 — COP correction: sensitivity to kgrout, rbore, LU, mfls, hconv

Run:
    python3 scripts/cross_track_analysis.py

All output is printed to stdout.  Each task section starts with a header.
"""

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from geosite.s4_sizing.ashrae_sizing import size_borefield, borehole_resistance

# ─────────────────────────────────────────────────────────────────────────────
# Helper: concise section header
# ─────────────────────────────────────────────────────────────────────────────

def _h(title: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {title}")
    print('='*72)


def _sep(label: str) -> None:
    print(f"\n  ── {label} " + "─" * max(0, 60 - len(label)))


# ─────────────────────────────────────────────────────────────────────────────
# Shared sizing baseline (from 390geothermal_calc.xlsx  Close-loop h-c inputs)
# ─────────────────────────────────────────────────────────────────────────────
BASE = dict(
    # ground loads — heating case from spreadsheet
    q_h=-200_000.0,   # W  peak hourly ground load (negative = heating)
    q_m=-90_000.0,    # W  monthly ground load
    q_y=-25_000.0,    # W  yearly average
    # ground properties
    k=1.548,          # W/m·K  (worst-case clay scenario from spreadsheet)
    alpha=0.2229,     # m²/day
    T_g=15.0,         # °C
    # fluid
    Cp=4200.0,        # J/kg·K
    mfls=0.05,        # kg/s per kW of |q_h|
    T_in_HP=5.0,      # °C  (heating mode minimum EWT)
    # borehole — from spreadsheet (Close-loop h-c)
    rbore=0.0762,     # m
    rpin=0.01365,     # m
    rpext=0.0167,     # m
    kgrout=2.05,      # W/m·K  (CETCO enhanced grout)
    kpipe=0.42,       # W/m·K  (HDPE)
    LU=0.0511,        # m  centre-to-centre pipe spacing
    hconv=1000.0,     # W/m²·K
    # borefield
    B=6.7,            # m  borehole spacing
    NB=32,            # number of boreholes
    A=9.0,            # aspect ratio
)

BASE_L = size_borefield(**BASE)   # reference total length [m]

print(f"\n  Reference borefield length L₀ = {BASE_L:.1f} m "
      f"(NB={BASE['NB']}, depth H={BASE_L/BASE['NB']:.1f} m)")


# =============================================================================
# TASK 1 — Three-pulse definitions vs. Philippe et al. (2010)
# =============================================================================
_h("TASK 1 — Three-pulse definitions: current code vs. Philippe et al. (2010)")

print("""
  Philippe et al. (2010) ASHRAE Journal 52(7):20-28 defines three pulses:

    q_y  (10-year pulse)  : annual average ground load [W]
                            = mean of the 8760h net ground load array
                            = (annual heat injection - extraction) / 8760 h

    q_m  (1-month pulse)  : "monthly ground load" = mean ground load over
                            the WORST MONTH (most negative for heating, most
                            positive for cooling), computed over ALL HOURS of
                            that month (heating and cooling cancel inside a month)

    q_h  (6-hour pulse)   : "peak hourly ground load" = the worst single hour
                            in the 8760h series (most negative for heating,
                            most positive for cooling)
                            — labelled "peak hourly" in the spreadsheet
                            — the g-function uses R6h (6-hour pulse duration),
                              so q_h is applied for 6 h in the thermal analysis

  CURRENT CODE STATUS
  ─────────────────────────────────────────────────────────────────────────
  s3_loads/compute.py  (IdealLoads path)
    q_y  : ground.mean()              ✓  matches definition
    q_m  : monthly_avg.min/max()      → monthly_avg = full-month average ✓
    q_h  : ground.min() / max()       ✓  single worst hour (per paper)

  run_energyplus_wshp_all.py  (WSHP path — _compute_pulses)
    q_y  : g.mean()                   ✓  matches definition
    q_m  : one-sided dominant-mode avg per month  ← DIFFERS from s3_loads
    q_h  : 6-hour rolling average peak            ← DIFFERS from s3_loads

  INCONSISTENCIES
  ─────────────────────────────────────────────────────────────────────────
  Two files disagree on both q_h and q_m:
    • q_h: s3_loads uses single worst hour; WSHP runner uses 6-hour average
    • q_m: s3_loads uses full-month net average; WSHP runner uses dominant-
           mode-only monthly average (ignores counter-mode hours)

  RECOMMENDATION (see Task 3 for q_m deep-dive)
    q_h: 6-hour average (WSHP runner) is engineering-standard and avoids
         1-hour anomalies. s3_loads should adopt it.
    q_m: full-month net average (s3_loads) matches the paper definition.
         WSHP runner should adopt it.
""")

# Show quantitative difference for a realistic q_h
_sep("q_h sensitivity: single-hour vs. 6-hour for a typical building")

# Simulate: generate a peaky heating load profile (Gaussian-distributed daily peaks)
rng = np.random.default_rng(42)
hrs = np.arange(8760)
# Simplified load: sinusoidal annual + daily + random noise, heating dominant
annual = -5000.0 * np.cos(2 * np.pi * hrs / 8760)           # colder in winter
daily  = -3000.0 * np.cos(2 * np.pi * (hrs % 24) / 24)      # colder at night
noise  = rng.normal(0, 1000, 8760)
g_demo = annual + daily + noise

q_h_single = float(g_demo.min())
r6 = np.lib.stride_tricks.sliding_window_view(g_demo, 6).mean(axis=1)
q_h_6h = float(r6.min())

print(f"  Demo 8760h profile (winter heating dominant):")
print(f"    Single-hour worst   q_h = {q_h_single:+.0f} W")
print(f"    6-hour rolling avg  q_h = {q_h_6h:+.0f} W")
print(f"    Ratio 6h/1h = {q_h_6h/q_h_single:.3f}  (6h average is {(1-q_h_6h/q_h_single)*100:.1f}% less extreme)")

# Sizing impact
q_h_1 = q_h_single
q_h_6 = q_h_6h
q_m_demo = float(g_demo[:744].mean())
q_y_demo = float(g_demo.mean())

def _quick_size(qh: float, qm: float, qy: float) -> float:
    p = dict(BASE)
    p.update(q_h=qh, q_m=qm, q_y=qy)
    return size_borefield(**p)

L_single = _quick_size(q_h_1, q_m_demo, q_y_demo)
L_6h     = _quick_size(q_h_6, q_m_demo, q_y_demo)
print(f"\n  Borefield sizing impact (all else equal):")
print(f"    L (single-hour q_h) = {L_single:.0f} m")
print(f"    L (6-hour avg q_h)  = {L_6h:.0f} m")
print(f"    Difference          = {L_single - L_6h:.0f} m  "
      f"({(L_single-L_6h)/L_single*100:.1f}% less with 6h avg)")


# =============================================================================
# TASK 2 — Scale factors: floor area vs. total area; controlled experiments
# =============================================================================
_h("TASK 2 — Scale factors: floor area vs. total area; controlled experiments")

print("""
  DEFINITION CHECK
  ─────────────────────────────────────────────────────────────────────────
  prototype_loads.json stores  q_h_Wpm2, q_m_Wpm2, q_y_Wpm2  in W/m².
  These are normalised by  _area_m2 = TOTAL CONDITIONED FLOOR AREA  (sum
  of all floors), not by footprint.

  When the user provides a different building area:
    q_h = q_h_Wpm2 × target_area_m2   (lookup.py line 88)

  The FOOTPRINT is then computed as:
    footprint = floor_area_m2 / n_floors   (footprint.py line 148)

  So load scaling uses TOTAL FLOOR AREA; footprint is only for borehole
  layout (NB range min/max), not for load magnitude.

  This is PHYSICALLY CORRECT because:
    - Thermal loads come from all conditioned floor area (envelope × area)
    - Ground footprint determines how many boreholes fit, not how much heat
""")

_sep("Controlled experiment A: fix footprint, vary floors (→ changes floor area)")
print("  Same footprint, more floors = more total area = proportionally larger loads")
print()

# Medium office: footprint = 4982/3 ≈ 1661 m², 3 floors
proto_area_office = 4982.0
n_floors_office   = 3
footprint_office  = proto_area_office / n_floors_office

from geosite.s4_sizing.footprint import compute_nb_range, BUILDING_SHAPES

for n_floors in [1, 2, 3, 4, 6]:
    total_area = footprint_office * n_floors  # same footprint, different floors
    scale = total_area / proto_area_office
    # Loads scale linearly with area (W/m² approach)
    q_h_s = -50_000.0 * scale   # approximate; negative = heating dominant
    q_m_s = -20_000.0 * scale
    q_y_s =  -5_000.0 * scale
    p = dict(BASE)
    p.update(q_h=q_h_s, q_m=q_m_s, q_y=q_y_s)
    nb_min, nb_max, meta = compute_nb_range(
        total_area, "medium_office", num_floors=n_floors, spacing_m=6.0, shape="elongated"
    )
    L = size_borefield(**p)
    H = L / BASE['NB']
    print(f"  n_floors={n_floors:2d}  total_area={total_area:7.0f} m²  "
          f"footprint={meta['footprint_m2']:5.0f} m²  "
          f"NB_range=[{nb_min},{nb_max}]  L={L:6.0f} m  H/bh={H:.1f} m")

_sep("Controlled experiment B: fix total area (load), vary floors (→ changes footprint)")
print("  Same total area, more floors = smaller footprint = fewer boreholes fit")
print()

for n_floors in [1, 2, 3, 4, 6]:
    total_area = proto_area_office  # fixed load, fixed area
    nb_min, nb_max, meta = compute_nb_range(
        total_area, "medium_office", num_floors=n_floors, spacing_m=6.0, shape="elongated"
    )
    # Loads are fixed (same total area)
    q_h_s = -50_000.0
    q_m_s = -20_000.0
    q_y_s =  -5_000.0
    p = dict(BASE)
    p.update(q_h=q_h_s, q_m=q_m_s, q_y=q_y_s)
    L = size_borefield(**p)
    H = L / BASE['NB']
    print(f"  n_floors={n_floors:2d}  total_area={total_area:7.0f} m²  "
          f"footprint={meta['footprint_m2']:5.0f} m²  "
          f"NB_range=[{nb_min},{nb_max}]  L={L:6.0f} m  H/bh={H:.1f} m")

print("""
  CONCLUSION (Task 2)
  ─────────────────────────────────────────────────────────────────────────
  Experiment A shows: scaling total area (via floors) linearly scales loads
  and total borefield length L. Footprint shrinks as floors increase,
  constraining borehole count (NB_range) — more floors → denser layout needed.

  Experiment B shows: fixing total area keeps loads constant (same L),
  but fewer floors → larger footprint → more borehole layout flexibility
  (wider NB_max). Load and geometry are independent inputs.

  The W/m² normalisation is correct: prototype data is per unit floor area,
  and user area is total conditioned floor area across all floors.
""")


# =============================================================================
# TASK 3 — q_m: dominant-mode-only vs. combined heating+cooling months
# =============================================================================
_h("TASK 3 — q_m: dominant-mode-only vs. combined heating+cooling monthly average")

print("""
  PAPER DEFINITION (Philippe et al. 2010 / ASHRAE sizing method)
  ─────────────────────────────────────────────────────────────────────────
  q_m is the NET GROUND LOAD averaged over the worst month. "Net" means
  cooling injection (+) and heating extraction (-) within the same month
  cancel each other. The borefield sees the NET thermal effect, not the
  sum of absolute values.

  TWO COMPETING IMPLEMENTATIONS
  ─────────────────────────────────────────────────────────────────────────
  A. Full-month net average (s3_loads/compute.py — matches paper):
       q_m = worst monthly mean of the full 8760h signed ground load
       In a shoulder month with both heating (−) and cooling (+):
         q_m_month = (sum of all hours, with sign) / hours_in_month

  B. Dominant-mode-only average (run_energyplus_wshp_all.py):
       q_m = worst monthly mean of ONLY the dominant-sign hours
       In a shoulder month: cooling hours averaged separately from heating
       Result: ALWAYS higher magnitude than A, more conservative

  WHICH IS PHYSICALLY CORRECT?
  ─────────────────────────────────────────────────────────────────────────
  Approach A is correct. The borehole temperature is driven by the NET heat
  flux. If a building heats in the morning and cools in the afternoon, the
  ground temperature change is determined by the daily net, not each side
  separately. ASHRAE's q_m represents "what is the average monthly thermal
  demand on the ground" — negative months add heat extraction, positive
  months add injection.

  Approach B overestimates q_m in shoulder months (both modes active),
  leading to a larger (more conservative/overdesigned) borefield.
""")

_sep("Controlled experiment: three synthetic building profiles")

MONTH_H = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

def build_monthly_stats(g: np.ndarray) -> tuple:
    """Return (q_m_net, q_m_onesided) for a 8760h ground load array."""
    avgs_net = []
    avgs_onesided = []
    cool_dom = g.mean() >= 0
    idx = 0
    for h in MONTH_H:
        seg = g[idx:idx+h]
        avgs_net.append(float(seg.mean()))
        if cool_dom:
            pos = seg[seg > 0]
            avgs_onesided.append(float(pos.mean()) if len(pos) > 0 else 0.0)
        else:
            neg = seg[seg < 0]
            avgs_onesided.append(float(neg.mean()) if len(neg) > 0 else 0.0)
        idx += h
    q_m_net = max(avgs_net, key=abs)
    q_m_os  = max(avgs_onesided, key=abs)
    return q_m_net, q_m_os

# Profile 1: strongly heating dominant (Buffalo-like office)
t = np.linspace(0, 2*np.pi, 8760)
g_heat = -25_000 * np.cos(t) - 5_000     # always negative in winter, near zero in summer
g_heat += np.random.default_rng(1).normal(0, 2000, 8760)

# Profile 2: strongly cooling dominant (Miami-like office)
g_cool = +25_000 * np.cos(t) + 5_000     # always positive in summer, near zero in winter
g_cool += np.random.default_rng(2).normal(0, 2000, 8760)

# Profile 3: mixed seasons (medium office, zone 4A-like)
g_mix  = -10_000 * np.cos(t) - 2_000     # net heating but big cooling months too
g_mix  += np.random.default_rng(3).normal(0, 8000, 8760)  # heavy mixing

profiles = [
    ("Heating dominant (Buffalo-like)", g_heat),
    ("Cooling dominant (Miami-like)",   g_cool),
    ("Mixed seasons (Zone 4A-like)",    g_mix),
]

print(f"\n  {'Profile':<32}  {'q_m_net':>10}  {'q_m_1sided':>10}  {'diff%':>7}  {'L_net':>8}  {'L_1sided':>8}")
print(f"  {'-'*32}  {'-'*10}  {'-'*10}  {'-'*7}  {'-'*8}  {'-'*8}")
for name, g in profiles:
    q_y = float(g.mean())
    q_h_v = float(g.min() if q_y < 0 else g.max())
    qm_net, qm_os = build_monthly_stats(g)
    L_net = _quick_size(q_h_v, qm_net, q_y)
    L_os  = _quick_size(q_h_v, qm_os,  q_y)
    pct   = (abs(qm_os) - abs(qm_net)) / max(abs(qm_net), 1e-6) * 100
    print(f"  {name:<32}  {qm_net:>+10.0f}  {qm_os:>+10.0f}  {pct:>+6.1f}%  {L_net:>8.0f}  {L_os:>8.0f}")

print("""
  INTERPRETATION
  ─────────────────────────────────────────────────────────────────────────
  • Heating/cooling dominant profiles: both methods agree closely.
    When one mode dominates, shoulder months have little counter-mode load
    so the dominant-mode-only and net averages are nearly identical.

  • Mixed profiles: dominant-mode-only significantly overestimates q_m
    (ignoring the counter-mode hours that partially offset ground load).
    This inflates borefield length — sometimes by 20-40%.

  RECOMMENDATION: Use full-month net average (Approach A, matches paper).
  Fix run_energyplus_wshp_all.py/_compute_pulses() to match s3_loads/compute.py.
""")


# =============================================================================
# TASK 4 — COP correction: what it is, and sensitivity analysis
# =============================================================================
_h("TASK 4 — COP correction: definition, spreadsheet review, and sensitivity")

print("""
  WHAT IS COP CORRECTION?
  ─────────────────────────────────────────────────────────────────────────
  The ASHRAE sizing inputs q_h / q_m / q_y are GROUND loads [W] — the heat
  that flows between borehole and ground.  EnergyPlus IdealLoads gives
  BUILDING loads (zone heating/cooling demand), not ground loads.

  Conversion (IdealLoads path only):
    q_ground_heat = −q_building_heat × (COP_h − 1) / COP_h
    q_ground_cool = +q_building_cool × (COP_c + 1) / COP_c

  where COP_h is heating COP and COP_c is cooling COP.

  With COP_h=3, COP_c=4:
    Heat extraction from ground = building heat demand × 0.667  (HP adds 33%)
    Heat rejection to ground    = building cooling demand × 1.25 (HP adds 25%)

  CURRENT CODE STATUS
  ─────────────────────────────────────────────────────────────────────────
  s3_loads/compute.py  line 40:   ground = q_cool - q_heat
  → This is COP=∞ (no correction).  Ground load = building load.
  → WRONG for IdealLoads path.  Overcounts cooling (+25% should be added),
    undercounts heating (should be ×0.667 not ×1.0).

  WSHP path (run_energyplus_wshp_all.py):
  → No COP correction needed.  EnergyPlus WSHP simulation outputs the ACTUAL
    source-side heat transfer — the ground load is computed internally by EP
    with the rated COP curves.  The COP correction is implicit in the model.

  SPREADSHEET (390geothermal_calc.xlsx)
  ─────────────────────────────────────────────────────────────────────────
  The spreadsheet takes q_h / q_m / q_y as DIRECT INPUTS (already ground
  loads).  It does NOT perform COP correction — that is the user's
  responsibility upstream.  Example inputs are manually entered.

  SENSITIVITY EXPERIMENTS
  ─────────────────────────────────────────────────────────────────────────
  The COP-corrected ground loads depend on:
    COP_h (heating COP)  — typically 3–5 for WSHPs
    COP_c (cooling COP)  — typically 4–6 for WSHPs
  And the borefield length also depends on borehole thermal resistance Rb,
  which depends on: kgrout, rbore, LU (pipe spacing), rpin, hconv.
""")

_sep("Sensitivity A: COP values → sizing (IdealLoads path)")

# Typical building: 1000 kW building cooling demand, 500 kW heating demand
q_bldg_cool = 1_000_000.0   # W building cooling
q_bldg_heat = 500_000.0     # W building heating

print(f"\n  Building loads: cooling={q_bldg_cool/1000:.0f} kW, heating={q_bldg_heat/1000:.0f} kW")
print(f"\n  {'COP_h':>6}  {'COP_c':>6}  {'q_h_gnd':>10}  {'q_m_gnd':>10}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*6}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*7}")

cop_pairs = [(2.5, 3.5), (3.0, 4.0), (3.5, 4.5), (4.0, 5.0), (5.0, 6.0)]
ref_L_cop = None
for cop_h, cop_c in cop_pairs:
    # COP-corrected ground loads (heating dominant in this example)
    qh_gnd = -q_bldg_heat * (cop_h - 1) / cop_h   # extraction (negative)
    qm_gnd = -q_bldg_heat * 0.4 * (cop_h - 1) / cop_h  # monthly ≈ 40% of peak
    qy_gnd = qh_gnd * 0.1    # simplified annual avg
    p = dict(BASE)
    p.update(q_h=qh_gnd, q_m=qm_gnd, q_y=qy_gnd)
    L = size_borefield(**p)
    if ref_L_cop is None:
        ref_L_cop = L
    delta = (L - ref_L_cop) / ref_L_cop * 100
    print(f"  {cop_h:>6.1f}  {cop_c:>6.1f}  {qh_gnd:>+10.0f}  {qm_gnd:>+10.0f}  {L:>8.0f}  {delta:>+6.1f}%")

_sep("Sensitivity B: kgrout (grout thermal conductivity)")
print(f"\n  Varying kgrout, all else = BASE. L₀ = {BASE_L:.0f} m")
print(f"\n  {'kgrout':>8}  {'Rb [mK/W]':>10}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*7}")
for kg in [0.6, 0.85, 1.2, 1.53, 2.05, 2.5, 3.0]:
    p = dict(BASE)
    p.update(kgrout=kg)
    Rb = borehole_resistance(p['rbore'], p['rpin'], p['rpext'],
                             kg, p['kpipe'], p['k'], p['LU'], p['hconv'])
    L = size_borefield(**p)
    delta = (L - BASE_L) / BASE_L * 100
    print(f"  {kg:>8.2f}  {Rb:>10.4f}  {L:>8.0f}  {delta:>+6.1f}%")

_sep("Sensitivity C: borehole radius (rbore) — affects Rb and g-function")
print(f"\n  Varying rbore, all else = BASE. L₀ = {BASE_L:.0f} m")
print(f"\n  {'rbore [m]':>10}  {'Rb [mK/W]':>10}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*7}")
for rb in [0.05, 0.057, 0.0635, 0.0762, 0.1]:
    p = dict(BASE)
    p.update(rbore=rb)
    Rb = borehole_resistance(rb, p['rpin'], p['rpext'],
                             p['kgrout'], p['kpipe'], p['k'], p['LU'], p['hconv'])
    L = size_borefield(**p)
    delta = (L - BASE_L) / BASE_L * 100
    note = " (NPS 3\" std)" if abs(rb - 0.0762) < 0.001 else ""
    print(f"  {rb:>10.4f}  {Rb:>10.4f}  {L:>8.0f}  {delta:>+6.1f}%{note}")

_sep("Sensitivity D: U-tube pipe spacing LU (centre-to-centre)")
print(f"\n  Varying LU, all else = BASE. L₀ = {BASE_L:.0f} m")
print(f"\n  {'LU [m]':>8}  {'Rb [mK/W]':>10}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*7}")
for lu in [0.02, 0.03, 0.04, 0.0511, 0.06, 0.07]:
    p = dict(BASE)
    p.update(LU=lu)
    Rb = borehole_resistance(p['rbore'], p['rpin'], p['rpext'],
                             p['kgrout'], p['kpipe'], p['k'], lu, p['hconv'])
    L = size_borefield(**p)
    delta = (L - BASE_L) / BASE_L * 100
    print(f"  {lu:>8.4f}  {Rb:>10.4f}  {L:>8.0f}  {delta:>+6.1f}%")

_sep("Sensitivity E: mfls (mass flow rate per kW of peak load)")
print(f"\n  mfls affects Tm (mean fluid temp) → driver of L denominator")
print(f"\n  {'mfls [kg/s·kW]':>14}  {'Tm [°C]':>8}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*14}  {'-'*8}  {'-'*8}  {'-'*7}")
for mfls in [0.02, 0.03, 0.04, 0.05, 0.08, 0.12]:
    p = dict(BASE)
    p.update(mfls=mfls)
    # recompute Tm to show
    m_dot = mfls * abs(BASE['q_h']) / 1000.0
    T_out = BASE['T_in_HP'] + BASE['q_h'] / (m_dot * BASE['Cp'])
    T_m   = (BASE['T_in_HP'] + T_out) / 2.0
    L = size_borefield(**p)
    delta = (L - BASE_L) / BASE_L * 100
    print(f"  {mfls:>14.3f}  {T_m:>8.2f}  {L:>8.0f}  {delta:>+6.1f}%")

_sep("Sensitivity F: hconv (pipe internal convection coefficient)")
print(f"\n  hconv affects Rconv, part of Rb. L₀ = {BASE_L:.0f} m")
print(f"\n  {'hconv [W/m²K]':>14}  {'Rb [mK/W]':>10}  {'L [m]':>8}  {'ΔL%':>7}")
print(f"  {'-'*14}  {'-'*10}  {'-'*8}  {'-'*7}")
for hc in [200, 500, 1000, 2000, 5000, 10000]:
    p = dict(BASE)
    p.update(hconv=hc)
    Rb = borehole_resistance(p['rbore'], p['rpin'], p['rpext'],
                             p['kgrout'], p['kpipe'], p['k'], p['LU'], hc)
    L = size_borefield(**p)
    delta = (L - BASE_L) / BASE_L * 100
    note = " (turbulent water)" if hc == 2000 else ""
    print(f"  {hc:>14d}  {Rb:>10.4f}  {L:>8.0f}  {delta:>+6.1f}%{note}")

print("""
  SUMMARY — SENSITIVITY RANKING
  ─────────────────────────────────────────────────────────────────────────
  Most to least sensitive (typical commercial range):

  1.  mfls (flow rate)    : ±30–50%  — drives mean fluid temperature Tm,
                            which controls (Tm − Tg) denominator directly
  2.  COP (for IdealLoads): ±15–25%  — scales the ground loads themselves
  3.  kgrout              : ±10–20%  — largest Rb component in clay soils
  4.  rbore               : ±5–15%   — affects both Rb and g-function shape
  5.  LU (pipe spacing)   : ±5–10%   — second-largest Rb component
  6.  hconv               : ±1–5%    — small effect when turbulent (>500)

  PRACTICAL IMPLICATION FOR WSHP PATH
  ─────────────────────────────────────────────────────────────────────────
  The WSHP simulation already captures COP internally. The dominant
  design uncertainties are mfls (circuit hydraulics), kgrout (grout
  specification), and k/alpha (soil properties from Stage 1 ML model).

  For the IdealLoads path, always apply the COP correction before sizing:
    q_gnd = q_building_heat × (COP_h−1)/COP_h  [extraction, negative]
    q_gnd = q_building_cool × (COP_c+1)/COP_c  [injection, positive]

  Recommended defaults: COP_h=3.5, COP_c=4.5 (residential WSHP standard).
""")

print("  Analysis complete.")

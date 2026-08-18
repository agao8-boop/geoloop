"""
Cross-validation: Python sizing vs Philippe (2010) spreadsheet.

Reference case: Chicago, IL (ASHRAE zone 5A), medium office, default envelope.
Run this script and compare printed intermediates against the Excel spreadsheet
cells documented inline. Any discrepancy > 1% in an intermediate value requires
root-cause investigation.

Usage:
    cd /Users/agao/Downloads/CEE299/geosite_advisor
    python3 scripts/validate_sizing.py
"""

import sys
import math
sys.path.insert(0, "/Users/agao/Downloads/CEE299/geosite_advisor")

from geosite.s4_sizing.ashrae_sizing import borehole_resistance, _g_poly, _peak_correction
from geosite.s4_sizing.gfunction_tables import A_F6H, A_F1M, A_F10Y
from geosite.s4_sizing.defaults import ADVANCED_DEFAULTS, T_IN_HP_DEFAULTS

# ---------------------------------------------------------------------------
# Reference inputs — Chicago medium office, zone 5A
# Source: prototype_loads.json (q values) + deep_thermal_by_county.csv (k, alpha, T_g)
# ---------------------------------------------------------------------------

# Ground thermal properties (Cook County, IL — from deep_thermal_by_county.csv)
k     = 3.997   # W/(m·K)  — thermal conductivity
alpha = 0.157   # m²/day   — thermal diffusivity (as stored in CSV)
T_g   = 15.19  # °C       — undisturbed ground temperature

# Prototype loads — medium office, zone 5A (from prototype_loads.json)
# Sign convention: positive = cooling (heat injection to ground), negative = heating (extraction)
q_h_raw =  159111.0   # W — peak hourly ground load  (positive = cooling dominant)
q_m_raw =   54113.0   # W — peak monthly ground load
q_y_raw =   19734.0   # W — annual average ground load

# Borefield layout (defaults matching Excel reference)
NB = 16          # number of boreholes
B  = 6.0         # m — borehole spacing
A  = 1.0         # aspect ratio (square array)

# Advanced parameters — from ADVANCED_DEFAULTS
p = ADVANCED_DEFAULTS
rbore  = p["rbore"]   # m — borehole radius (default 0.06 m)
rpin   = p["rpin"]    # m — pipe inner radius
rpext  = p["rpext"]   # m — pipe outer radius
kgrout = p["kgrout"]  # W/(m·K) — grout conductivity
kpipe  = p["kpipe"]   # W/(m·K) — HDPE pipe conductivity
LU     = p["LU"]      # m — U-tube leg half-spacing
hconv  = p["hconv"]   # W/(m²·K) — convective coefficient
Cp     = p["Cp"]      # J/(kg·K)
mfls   = p["mfls"]    # kg/s per kW

# Mode: cooling dominant (q values are positive)
mode   = "cooling"
T_in_HP = T_IN_HP_DEFAULTS["cooling"]  # 40.2°C max EWT in cooling mode

# ---------------------------------------------------------------------------
# Step-by-step sizing — printing every intermediate vs Excel cell reference
# ---------------------------------------------------------------------------

print("=" * 70)
print("GeoSite Sizing Cross-Validation — Chicago Medium Office (Zone 5A)")
print("=" * 70)
print()

# Step 1: Borehole resistance
Rb = borehole_resistance(rbore, rpin, rpext, kgrout, kpipe, k, LU, hconv)
print(f"INPUTS")
print(f"  k          = {k:.3f} W/(m·K)")
print(f"  alpha      = {alpha:.4f} m²/day")
print(f"  T_g        = {T_g:.2f} °C")
print(f"  rbore      = {rbore:.4f} m")
print(f"  rpin       = {rpin:.5f} m")
print(f"  rpext      = {rpext:.4f} m")
print(f"  kgrout     = {kgrout:.2f} W/(m·K)")
print(f"  kpipe      = {kpipe:.2f} W/(m·K)")
print(f"  LU         = {LU:.4f} m")
print(f"  hconv      = {hconv:.0f} W/(m²·K)")
print(f"  T_in_HP    = {T_in_HP:.1f} °C ({mode} mode)")
print(f"  NB         = {NB}")
print(f"  B          = {B:.1f} m")
print()

# Rb components (for verification)
R_conv  = 1.0 / (2.0 * math.pi * rpin * hconv)
R_pipe  = math.log(rpext / rpin) / (2.0 * math.pi * kpipe)
delta_k = (kgrout - k) / (kgrout + k)
rbore4  = rbore ** 4
lu2_4   = (LU / 2.0) ** 4
R_grout = (1.0 / (4.0 * math.pi * kgrout)) * (
    math.log(rbore / rpext)
    + math.log(rbore / LU)
    + delta_k * math.log(rbore4 / (rbore4 - lu2_4))
)
print(f"BOREHOLE RESISTANCE (Excel: bh_sizing!D24–D27)")
print(f"  R_conv  = {R_conv:.5f} m·K/W    (Excel D24)")
print(f"  R_pipe  = {R_pipe:.5f} m·K/W    (Excel D25)")
print(f"  R_grout = {R_grout:.5f} m·K/W    (Excel D26)")
print(f"  Rb      = {Rb:.5f} m·K/W    (Excel D27) ← verify against spreadsheet")
print()

# Step 2: g-function resistances
R_h = _g_poly(rbore, alpha, A_F6H)  / k
R_m = _g_poly(rbore, alpha, A_F1M)  / k
R_y = _g_poly(rbore, alpha, A_F10Y) / k

g_h_raw = _g_poly(rbore, alpha, A_F6H)
g_m_raw = _g_poly(rbore, alpha, A_F1M)
g_y_raw = _g_poly(rbore, alpha, A_F10Y)

print(f"G-FUNCTION RESISTANCES (Excel: bh_sizing!D29–D31)")
print(f"  g_6h_raw = {g_h_raw:.5f}    (g-poly before /k)")
print(f"  g_1m_raw = {g_m_raw:.5f}    (g-poly before /k)")
print(f"  g_10y_raw= {g_y_raw:.5f}    (g-poly before /k)")
print(f"  R_h = {R_h:.5f} m·K/W    (Excel D29) ← verify")
print(f"  R_m = {R_m:.5f} m·K/W    (Excel D30) ← verify")
print(f"  R_y = {R_y:.5f} m·K/W    (Excel D31) ← verify")
print()

# Step 3: Load inputs
q_h = q_h_raw   # W
q_m = q_m_raw   # W
q_y = q_y_raw   # W
print(f"LOAD INPUTS (from prototype_loads.json zone 5A)")
print(f"  q_h = {q_h:>12.1f} W   ({q_h/1000:.2f} kW) — peak hourly ({mode})")
print(f"  q_m = {q_m:>12.1f} W   ({q_m/1000:.2f} kW) — peak monthly ({mode})")
print(f"  q_y = {q_y:>12.1f} W   ({q_y/1000:.2f} kW) — annual average (net)")
print()

# Step 4: Mean fluid temperature
m_dot  = mfls * abs(q_h) / 1000.0
T_out  = T_in_HP + q_h / (m_dot * Cp)
T_m    = (T_in_HP + T_out) / 2.0
print(f"FLUID TEMPERATURE (Excel: bh_sizing!D32–D34)")
print(f"  m_dot  = {m_dot:.5f} kg/s    (Excel D32)")
print(f"  T_out  = {T_out:.3f} °C        (Excel D33)")
print(f"  T_m    = {T_m:.3f} °C        (Excel D34) ← verify")
print()

# Step 5: Numerator
numer = q_y * R_y + q_m * R_m + q_h * R_h + q_h * Rb
print(f"SIZING NUMERATOR (Excel: bh_sizing!D35)")
print(f"  q_y·R_y = {q_y * R_y:>12.2f} W·m·K/W")
print(f"  q_m·R_m = {q_m * R_m:>12.2f} W·m·K/W")
print(f"  q_h·R_h = {q_h * R_h:>12.2f} W·m·K/W")
print(f"  q_h·Rb  = {q_h * Rb:>12.2f} W·m·K/W")
print(f"  numer   = {numer:>12.2f} W·m     ← verify")
print()

# Step 6: Basic L without Tp
denom_0 = T_m - T_g
L_0 = numer / denom_0
print(f"INITIAL BOREFIELD LENGTH (no Tp)")
print(f"  T_m - T_g = {denom_0:.3f} °C")
print(f"  L_0       = {L_0:.1f} m   (Excel D35, no Tp iteration)")
print()

# Step 7: Iterative Tp correction
L = L_0
print(f"TP ITERATION (Excel: iterates 5 fixed passes; Python: tol=1.0 m)")
for i in range(200):
    Tp = _peak_correction(q_y, k, max(abs(L), 1.0), B, NB, A, alpha)
    H  = L / NB
    denom = T_m - T_g - Tp
    if abs(denom) < 1e-9:
        break
    L_new = numer / denom
    if i < 5:  # show first 5 iterations
        print(f"  iter {i+1:2d}: H={H:.2f}m  Tp={Tp:.4f}°C  denom={denom:.4f}  L={L_new:.2f}m")
    if abs(L_new - L) < 1.0:
        L = L_new
        print(f"  ... converged at iter {i+1}")
        break
    L = L_new

H_final = L / NB
print()
print(f"FINAL SIZING RESULT")
print(f"  L_total = {L:.1f} m   (total borefield length)")
print(f"  NB      = {NB}")
print(f"  H       = {H_final:.1f} m   (depth per borehole)")
print(f"  Tp      = {Tp:.4f} °C   (temperature penalty)")
print()

# ---------------------------------------------------------------------------
# COP correction note — shows what q values SHOULD be with COP applied
# ---------------------------------------------------------------------------
# NOTE: Current code uses building loads directly. This section shows
# what the corrected ground exchange loads would be.
print("=" * 70)
print("COP CORRECTION NOTE (item #14 — not yet applied in production code)")
print("=" * 70)

# For zone 5A medium office:
#   ann_heat_kWh = 39691, ann_cool_kWh = 212565 — cooling dominant
# The q_h, q_m, q_y above are from the 8760h ground exchange profile
# (output of compute_pulses which uses net ground = q_cool - q_heat)
# WITHOUT COP correction applied.

COP_h = 3.5   # typical GSHP heating COP at design conditions
COP_c = 4.5   # typical GSHP cooling COP at design conditions

# If we were to apply COP correction:
# ground_rejection = building_cool × (COP_c + 1)/COP_c = ×1.222
# ground_extraction = building_heat × (COP_h - 1)/COP_h = ×0.714
#
# For cooling-dominant case, q_h (cooling peak) would INCREASE by 22%:
q_h_cop_corrected = q_h * (COP_c + 1) / COP_c
q_m_cop_corrected = q_m * (COP_c + 1) / COP_c
q_y_cop_corrected = q_y  # q_y is net annual — needs separate calculation

print(f"  Without COP correction (current): q_h = {q_h/1000:.2f} kW")
print(f"  With COP correction (cooling):    q_h = {q_h_cop_corrected/1000:.2f} kW  (+{(q_h_cop_corrected/q_h-1)*100:.1f}%)")
print()
print(f"  Impact on L (rough estimate):")
numer_cop = q_y * R_y + q_m_cop_corrected * R_m + q_h_cop_corrected * R_h + q_h_cop_corrected * Rb
L_cop_approx = numer_cop / (T_m - T_g - Tp)
print(f"  L without COP correction = {L:.1f} m")
print(f"  L with COP correction    = {L_cop_approx:.1f} m   (rough, Tp not re-iterated)")
print(f"  Difference               = {L_cop_approx - L:+.1f} m ({(L_cop_approx/L - 1)*100:+.1f}%)")
print()
print("  ACTION: Verify Philippe (2010) spreadsheet inputs — are they")
print("  building loads or ground exchange loads? If building loads,")
print("  the spreadsheet handles COP correction internally. If ground")
print("  exchange loads, Python compute_pulses() must apply COP factors.")
print()

print("=" * 70)
print("VERIFICATION CHECKLIST — compare each ← value against Excel cells")
print("=" * 70)
print(f"  [ ] Rb      = {Rb:.5f} m·K/W    (Excel D27)")
print(f"  [ ] R_h     = {R_h:.5f} m·K/W    (Excel D29)")
print(f"  [ ] R_m     = {R_m:.5f} m·K/W    (Excel D30)")
print(f"  [ ] R_y     = {R_y:.5f} m·K/W    (Excel D31)")
print(f"  [ ] T_m     = {T_m:.3f} °C        (Excel D34)")
print(f"  [ ] numer   = {numer:.2f} W·m       (Excel D35 numerator)")
print(f"  [ ] L_0     = {L_0:.1f} m          (Excel D35 without Tp)")
print(f"  [ ] Tp      = {Tp:.4f} °C        (Excel E46 after 5 passes)")
print(f"  [ ] L_final = {L:.1f} m          (Excel final L)")
print(f"  [ ] H_final = {H_final:.1f} m/borehole (L / NB)")

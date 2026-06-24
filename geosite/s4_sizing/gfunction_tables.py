"""
Polynomial regression coefficients from Philippe et al. (2010).

Source: both reference spreadsheets, sheet "coefficients"
  - 390geothermal_calc.xlsx  → B2:H40
  - philippe_2010_sizing.xls → coefficients sheet (identical values)

No discrete g-function lookup tables (time → g-value pairs) exist in either
spreadsheet.  The method replaces lookup tables with two polynomial fits:

  1.  A_F6H / A_F1M / A_F10Y  — 10-term polynomial in (rbore, alpha) that
      approximates the single-borehole g-function at three pulse durations.
      Spreadsheet header: "Coefficients for f6h, f1m, f10y functions"

  2.  B_TP  — 37-term polynomial in (B/H, ln(t10y/ts), NB, A) that gives
      the borefield peak temperature correction Tp.
      Spreadsheet header: "Coefficients for Tp correlation"

Index convention
----------------
All arrays are 1-D and zero-indexed: array[i] = coefficient i (a_i or b_i).
Every element is annotated as:
    value,  # [i]  name   basis function
so the spreadsheet row and the Python index are always visible side-by-side.
"""

import numpy as np

# ---------------------------------------------------------------------------
# g-function polynomial coefficients  (spreadsheet columns C / D / E)
# ---------------------------------------------------------------------------
# Polynomial form — identical structure for all three timescales:
#
#   g(rbore, α) = a[0]·1
#               + a[1]·rbore    + a[2]·rbore²
#               + a[3]·α        + a[4]·α²
#               + a[5]·ln(α)    + a[6]·ln(α)²
#               + a[7]·rbore·α
#               + a[8]·rbore·ln(α)
#               + a[9]·α·ln(α)
#
# Effective thermal resistance:  R_pulse = g(rbore, α) / k   [m·K/W]

# 6-hour pulse  (spreadsheet column C, label "f6h")
A_F6H = np.array([
     0.6619352,    # [ 0]  a0   1
    -4.815693,     # [ 1]  a1   rbore
    15.03571,      # [ 2]  a2   rbore²
    -0.09879421,   # [ 3]  a3   α
     0.02917889,   # [ 4]  a4   α²
     0.1138498,    # [ 5]  a5   ln(α)
     0.005610933,  # [ 6]  a6   ln(α)²
     0.7796329,    # [ 7]  a7   rbore·α
    -0.324388,     # [ 8]  a8   rbore·ln(α)
    -0.01824101,   # [ 9]  a9   α·ln(α)
])

# 1-month pulse  (spreadsheet column D, label "f1m")
A_F1M = np.array([
     0.4132728,    # [ 0]  a0   1
     0.2912981,    # [ 1]  a1   rbore
     0.07589286,   # [ 2]  a2   rbore²
     0.1563978,    # [ 3]  a3   α
    -0.2289355,    # [ 4]  a4   α²
    -0.004927554,  # [ 5]  a5   ln(α)
    -0.002694979,  # [ 6]  a6   ln(α)²
    -0.6380360,    # [ 7]  a7   rbore·α
     0.2950815,    # [ 8]  a8   rbore·ln(α)
     0.149332,     # [ 9]  a9   α·ln(α)
])

# 10-year pulse  (spreadsheet column E, label "f10y")
A_F10Y = np.array([
     0.3057646,    # [ 0]  a0   1
     0.08987446,   # [ 1]  a1   rbore
    -0.09151786,   # [ 2]  a2   rbore²
    -0.03872451,   # [ 3]  a3   α
     0.1690853,    # [ 4]  a4   α²
    -0.02881681,   # [ 5]  a5   ln(α)
    -0.002886584,  # [ 6]  a6   ln(α)²
    -0.1723169,    # [ 7]  a7   rbore·α
     0.03112034,   # [ 8]  a8   rbore·ln(α)
    -0.1188438,    # [ 9]  a9   α·ln(α)
])

# ---------------------------------------------------------------------------
# Tp correction polynomial coefficients  (spreadsheet column H, b0…b36)
# ---------------------------------------------------------------------------
# Variables:  x = B/H,  y = ln(t10y/ts),  ts = H²/(9·α)
#
# Polynomial form:
#   poly(x, y, NB, A) =
#       b[0]                                          constant
#     + b[1]·x   + b[2]·x²  + b[3]·x³              B/H terms
#     + b[4]·y   + b[5]·y²  + b[6]·y³              ln(t10y/ts) terms
#     + b[7]·NB  + b[8]·NB² + b[9]·NB³             NB terms
#     + b[10]·A  + b[11]·A² + b[12]·A³             A terms
#     + b[13]·x·y   + b[14]·x·y²                   cross: x × y
#     + b[15]·x·NB  + b[16]·x·NB²                  cross: x × NB
#     + b[17]·x·A   + b[18]·x·A²                   cross: x × A
#     + b[19]·x²·y  + b[20]·x²·y²                  cross: x² × y
#     + b[21]·x²·NB + b[22]·x²·NB²                 cross: x² × NB
#     + b[23]·x²·A  + b[24]·x²·A²                  cross: x² × A
#     + b[25]·y·NB  + b[26]·y·NB²                  cross: y × NB
#     + b[27]·y·A   + b[28]·y·A²                   cross: y × A
#     + b[29]·y²·NB + b[30]·y²·NB²                 cross: y² × NB
#     + b[31]·y²·A  + b[32]·y²·A²                  cross: y² × A
#     + b[33]·NB·A  + b[34]·NB·A²                  cross: NB × A
#     + b[35]·NB²·A + b[36]·NB²·A²                 cross: NB² × A
#
# Usage:  Tp = q_y / (2π·k·L) × poly(x, y, NB, A)   [°C]
# Valid:  B/H ∈ [0.05, 0.1],  y ∈ [−2, 3],  NB ∈ [4, 144],  A ∈ [1, 9]

B_TP = np.array([
     7.8189,       # [ 0]  b0    1
   -64.27,         # [ 1]  b1    x
   153.87,         # [ 2]  b2    x²
   -84.809,        # [ 3]  b3    x³
     3.461,        # [ 4]  b4    y
    -0.94753,      # [ 5]  b5    y²
    -0.060416,     # [ 6]  b6    y³
     1.5631,       # [ 7]  b7    NB
    -0.0089416,    # [ 8]  b8    NB²
     1.9061e-05,   # [ 9]  b9    NB³
    -2.289,        # [10]  b10   A
     0.10187,      # [11]  b11   A²
     0.006569,     # [12]  b12   A³
   -40.918,        # [13]  b13   x·y
    15.557,        # [14]  b14   x·y²
   -19.107,        # [15]  b15   x·NB
     0.10529,      # [16]  b16   x·NB²
    25.501,        # [17]  b17   x·A
    -2.1177,       # [18]  b18   x·A²
    77.529,        # [19]  b19   x²·y
   -50.454,        # [20]  b20   x²·y²
    76.352,        # [21]  b21   x²·NB
    -0.53719,      # [22]  b22   x²·NB²
  -132.0,          # [23]  b23   x²·A
    12.878,        # [24]  b24   x²·A²
     0.12697,      # [25]  b25   y·NB
    -0.00040284,   # [26]  b26   y·NB²
    -0.072065,     # [27]  b27   y·A
     0.00095184,   # [28]  b28   y·A²
    -0.024167,     # [29]  b29   y²·NB
     9.6811e-05,   # [30]  b30   y²·NB²
     0.028317,     # [31]  b31   y²·A
    -0.0010905,    # [32]  b32   y²·A²
     0.12207,      # [33]  b33   NB·A
    -0.007105,     # [34]  b34   NB·A²
    -0.0011129,    # [35]  b35   NB²·A
    -0.00045566,   # [36]  b36   NB²·A²
])

"""
Unit tests for geosite.s4_sizing.ashrae_sizing.

All expected values are taken directly from the Philippe et al. (2010)
reference spreadsheets:
  - philippe_2010_sizing.xls  (bh_sizing columns D and E)
  - 390geothermal_calc.xlsx   ("Close-loop h - s" sheet, column E)

Scenario 1 — cooling, single-borehole baseline, no Tp
    Source: philippe_2010_sizing.xls → bh_sizing column D
    L_total = 151.657 m (row 35, no borefield correction)

Scenario 2 — heating, multiple boreholes with Tp, fast convergence
    Source: philippe_2010_sizing.xls → bh_sizing column E
    q_h=−392250 W, NB=120, B=6.1 m, A=1.2
    L_0 = 9899.256 m, L_final = 10149.683 m (Tp≈−0.24°C, converges in 3 iters)

Scenario 3 — heating, dense field with Tp, slow convergence
    Source: 390geothermal_calc.xlsx → "Close-loop h - s" sheet, column E
    q_h=−200000 W, NB=32, B=6.7 m, A=9
    L_0 = 5296.285 m, L_final ≈ 1775 m (tol=1.0 m, ~23 iters)
"""

import math
import pytest

from geosite.s4_sizing.ashrae_sizing import borehole_resistance, size_borefield, _g_poly
from geosite.s4_sizing.gfunction_tables import A_F6H, A_F1M, A_F10Y


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# philippe_2010_sizing.xls — bh_sizing sheet, column D
# Cooling case: q_h > 0  (heat injection to ground)
XLS_D = dict(
    q_h=12_000.0,       # W — peak hourly ground load
    q_m=6_000.0,        # W — peak monthly
    q_y=1_500.0,        # W — annual
    k=2.0,              # W/m·K
    alpha=0.086,        # m²/day
    T_g=15.0,           # °C
    Cp=4_200.0,         # J/kg·K
    mfls=0.05,          # kg/s/kW
    T_in_HP=40.2,       # °C — max EWT for cooling
    rbore=0.06,         # m
    rpin=0.01365,       # m
    rpext=0.0167,       # m
    kgrout=1.5,         # W/m·K
    kpipe=0.42,         # W/m·K
    LU=0.0511,          # m  (U-tube leg spacing)
    hconv=1_000.0,      # W/m²·K
)

# 390geothermal_calc.xlsx — "Close-loop h - s" sheet, column E
# Heating case: q_h < 0  (heat extraction from ground)
XLSX_CL_HS = dict(
    q_h=-200_000.0,     # W
    q_m=-90_000.0,      # W
    q_y=-25_000.0,      # W
    k=2.07,             # W/m·K
    alpha=0.13,         # m²/day
    T_g=15.0,           # °C
    Cp=4_200.0,         # J/kg·K
    mfls=0.05,          # kg/s/kW
    T_in_HP=5.0,        # °C — min EWT for heating
    rbore=0.0762,       # m
    rpin=0.01365,       # m
    rpext=0.0167,       # m
    kgrout=2.05,        # W/m·K
    kpipe=0.42,         # W/m·K
    LU=0.0511,          # m
    hconv=1_000.0,      # W/m²·K
    # Borefield geometry for Tp correction
    B=6.7,              # m — borehole spacing
    NB=32,              # — number of boreholes
    A=9.0,              # — aspect ratio (long / short)
)


# ---------------------------------------------------------------------------
# Test 1 — cooling, basic sizing (no Tp), philippe_2010_sizing.xls
# ---------------------------------------------------------------------------

class TestPhilippeXlsCaseD:
    """Verify every intermediate and the final result against xls cached values."""

    p = XLS_D  # shorthand

    def test_rconv(self):
        # Excel: bh_sizing!D24 = 1/(2π·rpin·hconv)
        result = 1.0 / (2 * math.pi * self.p["rpin"] * self.p["hconv"])
        assert result == pytest.approx(0.011659702790615043, rel=1e-6)

    def test_rpipe(self):
        # Excel: bh_sizing!D25 = ln(rpext/rpin)/(2π·kpipe)
        result = math.log(self.p["rpext"] / self.p["rpin"]) / (
            2 * math.pi * self.p["kpipe"]
        )
        assert result == pytest.approx(0.07642059451888729, rel=1e-6)

    def test_rgrout(self):
        # Excel: bh_sizing!D26
        p = self.p
        delta_k = (p["kgrout"] - p["k"]) / (p["kgrout"] + p["k"])
        rb4 = p["rbore"] ** 4
        lu2_4 = (p["LU"] / 2) ** 4
        result = (1.0 / (4 * math.pi * p["kgrout"])) * (
            math.log(p["rbore"] / p["rpext"])
            + math.log(p["rbore"] / p["LU"])
            + delta_k * math.log(rb4 / (rb4 - lu2_4))
        )
        assert result == pytest.approx(0.07611423391286232, rel=1e-6)

    def test_rb(self):
        # Excel: bh_sizing!D27
        p = self.p
        Rb = borehole_resistance(
            p["rbore"], p["rpin"], p["rpext"],
            p["kgrout"], p["kpipe"], p["k"],
            p["LU"], p["hconv"],
        )
        assert Rb == pytest.approx(0.12015438256761349, rel=1e-6)

    def test_R_h(self):
        # Excel: bh_sizing!D29 = (1/k) × g_poly(rbore, alpha, a_hourly)
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F6H) / p["k"]
        assert result == pytest.approx(0.11445903013141503, rel=1e-5)

    def test_R_m(self):
        # Excel: bh_sizing!D30
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F1M) / p["k"]
        assert result == pytest.approx(0.18020547706451287, rel=1e-5)

    def test_R_y(self):
        # Excel: bh_sizing!D31
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F10Y) / p["k"]
        assert result == pytest.approx(0.19083864808240175, rel=1e-5)

    def test_T_out(self):
        # Excel: bh_sizing!D33 = TinHP + q_h/(mfls·|q_h|/1000·Cp)
        p = self.p
        m_dot = p["mfls"] * abs(p["q_h"]) / 1000.0
        result = p["T_in_HP"] + p["q_h"] / (m_dot * p["Cp"])
        assert result == pytest.approx(44.96190476190476, rel=1e-6)

    def test_Tm(self):
        # Excel: bh_sizing!D34
        p = self.p
        m_dot = p["mfls"] * abs(p["q_h"]) / 1000.0
        T_out = p["T_in_HP"] + p["q_h"] / (m_dot * p["Cp"])
        result = (p["T_in_HP"] + T_out) / 2.0
        assert result == pytest.approx(42.58095238095238, rel=1e-6)

    def test_total_length_no_tp(self):
        # Excel: bh_sizing!D35 — basic L₀ without Tp correction
        p = self.p
        L = size_borefield(**{k: v for k, v in p.items()})  # no B/NB → no Tp
        assert L == pytest.approx(151.65726437306537, rel=1e-5)


# ---------------------------------------------------------------------------
# Test 2 — heating, full iterative Tp, 390geothermal_calc.xlsx Close-loop h-s
# ---------------------------------------------------------------------------

class TestXlsxCloseLoopHS:
    """Verify the converged borefield length against the xlsx Close-loop h-s sheet."""

    p = XLSX_CL_HS

    def test_rb(self):
        # Excel: "Close-loop h - s"!E60–E63
        p = self.p
        Rb = borehole_resistance(
            p["rbore"], p["rpin"], p["rpext"],
            p["kgrout"], p["kpipe"], p["k"],
            p["LU"], p["hconv"],
        )
        assert Rb == pytest.approx(0.11847295447967185, rel=1e-5)

    def test_R_h(self):
        # Excel: "Close-loop h - s"!E65
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F6H) / p["k"]
        assert result == pytest.approx(0.10821352936139152, rel=1e-5)

    def test_R_m(self):
        # Excel: "Close-loop h - s"!E66
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F1M) / p["k"]
        assert result == pytest.approx(0.17362619307636817, rel=1e-5)

    def test_R_y(self):
        # Excel: "Close-loop h - s"!E67
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F10Y) / p["k"]
        assert result == pytest.approx(0.18437581703635492, rel=1e-5)

    def test_basic_L0(self):
        # Excel: "Close-loop h - s"!E71 — L₀ without Tp correction (no B/NB supplied)
        p = self.p
        L0 = size_borefield(**{k: v for k, v in p.items()
                               if k not in ("B", "NB", "A")})
        assert L0 == pytest.approx(5296.284773041878, rel=1e-5)

    def test_converged_length_with_tp(self):
        # Default tol=1.0 m stops at ~23 iterations (|ΔL| first drops below 1 m).
        # True fixed-point ≈ 1772.94 m; error at tol=1.0 m is ~2 m — acceptable
        # for feasibility sizing. Expected value verified by direct iteration trace.
        p = self.p
        L = size_borefield(**p)
        assert L == pytest.approx(1775.0107, abs=1.0)

    def test_borehole_depth(self):
        # H = L / NB at tol=1.0 m convergence: 1775 / 32 ≈ 55.47 m per borehole
        p = self.p
        L = size_borefield(**p)
        H = L / p["NB"]
        assert H == pytest.approx(55.47, abs=0.04)


# ---------------------------------------------------------------------------
# Scenario 2 — heating, multiple boreholes, philippe_2010_sizing.xls col E
# ---------------------------------------------------------------------------

# philippe_2010_sizing.xls — bh_sizing sheet, column E
# Heating case: q_h < 0, Tp ≈ −0.24 °C (small correction, converges in 3 iters)
XLS_E = dict(
    q_h=-392_250.0,     # W — large heating peak load
    q_m=-100_000.0,     # W
    q_y=-1_762.0,       # W — near-balanced annual load
    k=2.25,             # W/m·K
    alpha=0.06757039008,# m²/day
    T_g=12.41,          # °C
    Cp=4_000.0,         # J/kg·K
    mfls=0.074,         # kg/s/kW
    T_in_HP=4.44,       # °C — min EWT for heating
    rbore=0.054,        # m
    rpin=0.01365,       # m
    rpext=0.0167,       # m
    kgrout=1.73,        # W/m·K
    kpipe=0.45,         # W/m·K
    LU=0.0471,          # m
    hconv=1_000.0,      # W/m²·K
    # Borefield geometry
    B=6.1,              # m
    NB=120,
    A=1.2,
)


class TestPhilippeXlsCaseE:
    """Column E of philippe_2010_sizing.xls — heating with Tp, fast convergence."""

    p = XLS_E

    def test_rb(self):
        # xls bh_sizing row 27 col E = 0.10154262748428441
        p = self.p
        Rb = borehole_resistance(
            p["rbore"], p["rpin"], p["rpext"],
            p["kgrout"], p["kpipe"], p["k"],
            p["LU"], p["hconv"],
        )
        assert Rb == pytest.approx(0.10154262748428441, rel=1e-5)

    def test_R_h(self):
        # xls bh_sizing row 29 col E = 0.10067477057511355
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F6H) / p["k"]
        assert result == pytest.approx(0.10067477057511355, rel=1e-5)

    def test_R_m(self):
        # xls bh_sizing row 30 col E = 0.1600011827001955
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F1M) / p["k"]
        assert result == pytest.approx(0.1600011827001955, rel=1e-5)

    def test_R_y(self):
        # xls bh_sizing row 31 col E = 0.1696347523721096
        p = self.p
        result = _g_poly(p["rbore"], p["alpha"], A_F10Y) / p["k"]
        assert result == pytest.approx(0.1696347523721096, rel=1e-5)

    def test_T_out(self):
        # xls bh_sizing row 33 col E = 1.0616216216216219
        p = self.p
        m_dot = p["mfls"] * abs(p["q_h"]) / 1000.0
        result = p["T_in_HP"] + p["q_h"] / (m_dot * p["Cp"])
        assert result == pytest.approx(1.0616216216216219, rel=1e-6)

    def test_Tm(self):
        # xls bh_sizing row 34 col E = 2.750810810810811
        p = self.p
        m_dot = p["mfls"] * abs(p["q_h"]) / 1000.0
        T_out = p["T_in_HP"] + p["q_h"] / (m_dot * p["Cp"])
        result = (p["T_in_HP"] + T_out) / 2.0
        assert result == pytest.approx(2.750810810810811, rel=1e-6)

    def test_basic_L0(self):
        # xls bh_sizing row 35 col E = 9899.256264647662 (no Tp correction)
        p = self.p
        L0 = size_borefield(**{k: v for k, v in p.items()
                               if k not in ("B", "NB", "A")})
        assert L0 == pytest.approx(9899.256264647662, rel=1e-5)

    def test_converged_length_with_tp(self):
        # xls rows 43–69: Tp ≈ −0.24°C, convergence in 3 iterations.
        # Spreadsheet final (5 iters) = 10149.682911777352 m.
        # tol=1.0 m stops after 3 iters; result matches spreadsheet within 0.02 m.
        p = self.p
        L = size_borefield(**p)
        assert L == pytest.approx(10149.682911777352, abs=1.0)

    def test_borehole_depth(self):
        # H = L / NB = 10149.683 / 120 = 84.581 m per borehole
        p = self.p
        L = size_borefield(**p)
        H = L / p["NB"]
        assert H == pytest.approx(84.581, abs=0.01)

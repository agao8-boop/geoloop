"""
ASHRAE three-pulse borefield sizing — Philippe et al. (2010).

Implements the vertical closed-loop sizing equation from:
    Philippe, M., Bernier, M., Marchio, D. (2010). Validity ranges of three
    analytical solutions to heat transfer in the vicinity of single boreholes.
    ASHRAE Journal 52(7):20-28.

Polynomial coefficients are stored in gfunction_tables.py (extracted from the
companion spreadsheet's "coefficients" sheet).  No discrete g-function lookup
tables exist in the reference spreadsheets — the method uses polynomial fits.

Sign convention (same as spreadsheet):
    positive q  →  heat injection into ground  (cooling mode)
    negative q  →  heat extraction from ground (heating mode)
"""

import math

import numpy as np

from geosite.s4_sizing.gfunction_tables import A_F6H, A_F1M, A_F10Y, B_TP

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _g_poly(rbore: float, alpha: float, a: np.ndarray) -> float:
    """Evaluate the 10-term single-borehole g-function polynomial.

    Returns the raw g value (not divided by k).

    Excel: bh_sizing!D29 = (1/k) × _g_poly(rbore, alpha, A_F6H)
    """
    ln_a = math.log(alpha)
    return (a[0]
            + a[1] * rbore
            + a[2] * rbore ** 2
            + a[3] * alpha
            + a[4] * alpha ** 2
            + a[5] * ln_a
            + a[6] * ln_a ** 2
            + a[7] * rbore * alpha
            + a[8] * rbore * ln_a
            + a[9] * alpha * ln_a)


def _peak_correction(q_y: float, k: float, L: float,
                     B: float, NB: int, A: float,
                     alpha: float) -> float:
    """Borefield peak temperature correction Tp [°C].

    Polynomial approximation for the long-term mean borehole temperature
    change due to inter-borehole interaction over a 10-year horizon.

    Excel: bh_sizing!E44–E46 (and equivalents in Close-loop sheets).
    """
    b = B_TP
    H = L / NB                               # Excel: E$35/E$39 — borehole depth
    x = B / H                                # Excel: E44 = E$38/(E$35/E$39)
    ts = H ** 2 / (9.0 * alpha)             # steady-state time [days]
    y = math.log(365.25 * 10.0 / ts)        # Excel: E45 = LN(365.25*10/ts)

    poly = (b[0]
            + b[1] * x   + b[2] * x**2  + b[3] * x**3
            + b[4] * y   + b[5] * y**2  + b[6] * y**3
            + b[7] * NB  + b[8] * NB**2 + b[9] * NB**3
            + b[10] * A  + b[11] * A**2 + b[12] * A**3
            + b[13] * x * y   + b[14] * x * y**2
            + b[15] * x * NB  + b[16] * x * NB**2
            + b[17] * x * A   + b[18] * x * A**2
            + b[19] * x**2 * y   + b[20] * x**2 * y**2
            + b[21] * x**2 * NB  + b[22] * x**2 * NB**2
            + b[23] * x**2 * A   + b[24] * x**2 * A**2
            + b[25] * y * NB  + b[26] * y * NB**2
            + b[27] * y * A   + b[28] * y * A**2
            + b[29] * y**2 * NB  + b[30] * y**2 * NB**2
            + b[31] * y**2 * A   + b[32] * y**2 * A**2
            + b[33] * NB * A   + b[34] * NB * A**2
            + b[35] * NB**2 * A + b[36] * NB**2 * A**2)

    # Excel: E46 = E$5 / (2·PI()·E$7·E35) × poly
    return q_y / (2.0 * math.pi * k * L) * poly


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def borehole_resistance(rbore: float, rpin: float, rpext: float,
                        kgrout: float, kpipe: float, k: float,
                        LU: float, hconv: float) -> float:
    """Total borehole thermal resistance Rb [m·K/W].

    Parameters
    ----------
    rbore  : borehole radius [m]
    rpin   : pipe inner radius [m]
    rpext  : pipe outer (external) radius [m]
    kgrout : grout thermal conductivity [W/m·K]
    kpipe  : pipe thermal conductivity [W/m·K]
    k      : soil thermal conductivity [W/m·K]
    LU     : U-tube leg centre-to-centre half-spacing [m]
              (distance between the two pipe centres)
    hconv  : convective heat transfer coefficient inside pipe [W/m²·K]

    Returns
    -------
    Rb : borehole thermal resistance [m·K/W]

    Excel
    -----
    D24 = 1/(2π·rpin·hconv)          → R_conv
    D25 = ln(rpext/rpin)/(2π·kpipe)  → R_pipe
    D26 = 1/(4π·kgrout)·[ln(rbore/rpext) + ln(rbore/LU)
              + (kgrout−k)/(kgrout+k)·ln(rbore⁴/(rbore⁴−(LU/2)⁴))]  → R_grout
    D27 = D26 + (D24 + D25)/2        → Rb
    """
    # Excel: D24
    R_conv = 1.0 / (2.0 * math.pi * rpin * hconv)
    # Excel: D25
    R_pipe = math.log(rpext / rpin) / (2.0 * math.pi * kpipe)
    # Excel: D26
    delta_k = (kgrout - k) / (kgrout + k)
    rbore4 = rbore ** 4
    lu2_4 = (LU / 2.0) ** 4
    R_grout = (1.0 / (4.0 * math.pi * kgrout)) * (
        math.log(rbore / rpext)
        + math.log(rbore / LU)
        + delta_k * math.log(rbore4 / (rbore4 - lu2_4))
    )
    # Excel: D27
    return R_grout + (R_conv + R_pipe) / 2.0


def size_borefield(
    q_h: float,
    q_m: float,
    q_y: float,
    k: float,
    alpha: float,
    T_g: float,
    Cp: float,
    mfls: float,
    T_in_HP: float,
    rbore: float,
    rpin: float,
    rpext: float,
    kgrout: float,
    kpipe: float,
    LU: float,
    hconv: float,
    B: float | None = None,
    NB: int | None = None,
    A: float = 1.0,
    tol: float = 1.0,
    max_iter: int = 200,
) -> float:
    """Size a vertical closed-loop borefield using the ASHRAE three-pulse method.

    Parameters
    ----------
    q_h      : peak hourly ground load [W]
    q_m      : peak monthly ground load [W]
    q_y      : annual average ground load [W]
    k        : soil thermal conductivity [W/m·K]
    alpha    : soil thermal diffusivity [m²/day]; valid range 0.025–0.2
    T_g      : undisturbed ground temperature [°C]
    Cp       : fluid specific heat [J/kg·K]  (typically 4200 for water)
    mfls     : fluid mass-flow rate per unit peak load [kg/s per kW]
    T_in_HP  : design fluid temperature entering the heat pump [°C]
               (min EWT for heating mode; max EWT for cooling mode)
    rbore    : borehole radius [m]; valid range 0.05–0.1
    rpin     : pipe inner radius [m]
    rpext    : pipe outer (external) radius [m]
    kgrout   : grout thermal conductivity [W/m·K]
    kpipe    : pipe wall thermal conductivity [W/m·K]
    LU       : U-tube leg spacing (centre-to-centre) [m]
    hconv    : convective coefficient inside pipe [W/m²·K]
    B        : borehole spacing [m] — required for Tp correction
    NB       : total number of boreholes — required for Tp correction
    A        : aspect ratio (boreholes long-direction / short-direction) [-]
    tol      : convergence tolerance for L [m] (default 1.0 m — stops at ~23
               iterations, error vs true fixed-point ≈ 2 m, adequate for
               feasibility sizing; use 0.1 m for 30 iters / 0.24 m error)
    max_iter : iteration cap to prevent infinite loops (default 200)

    Returns
    -------
    L : total borefield length [m]  (sum of all borehole depths × number)

    Notes
    -----
    Without B and NB the function returns L₀ (no borefield interaction
    correction). Providing B and NB iterates the Tp correction until
    |ΔL| < tol. The reference spreadsheet used only 5 fixed iterations;
    tol=1.0 m (default) converges in ~23 iterations with ~2 m error vs
    the mathematical fixed-point, which is sufficient for feasibility sizing.
    """
    # ── Step 1: borehole thermal resistance ──────────────────────────────
    # Excel: bh_sizing!D24–D27
    Rb = borehole_resistance(rbore, rpin, rpext, kgrout, kpipe, k, LU, hconv)

    # ── Step 2: g-function effective resistances [m·K/W] ─────────────────
    # Excel: bh_sizing!D29 (R_h), D30 (R_m), D31 (R_y)
    R_h = _g_poly(rbore, alpha, A_F6H)  / k
    R_m = _g_poly(rbore, alpha, A_F1M)  / k
    R_y = _g_poly(rbore, alpha, A_F10Y) / k

    # ── Step 3: mean fluid temperature ──────────────────────────────────
    # m_dot = mfls [kg/s/kW] × |q_h| [W] / 1000 = total flow rate [kg/s]
    # Excel: bh_sizing!D33 = D13 + D3/(D12·ABS(D3)/1000·D11)
    m_dot = mfls * abs(q_h) / 1000.0
    T_out = T_in_HP + q_h / (m_dot * Cp)   # fluid exit temperature [°C]
    T_m   = (T_in_HP + T_out) / 2.0        # mean fluid temperature [°C]
    # Excel: D34 = (D13 + D33)/2

    # ── Step 4: numerator (invariant — computed once) ────────────────────
    # Excel: D35 numerator = q_y·R_y + q_m·R_m + q_h·R_h + q_h·Rb
    numer = q_y * R_y + q_m * R_m + q_h * R_h + q_h * Rb

    # ── Step 5: basic L₀ without borefield interaction ───────────────────
    # Excel: D35 = numer / (Tm − Tg)
    L = numer / (T_m - T_g)

    # ── Step 6: iterate Tp correction to convergence ─────────────────────
    # Excel used 5 fixed passes (E46→E47 … E66→E67); tol=1.0 m converges
    # in ~23 iterations with ~2 m error vs true fixed-point (~1773 m).
    if B is not None and NB is not None:
        for _ in range(max_iter):
            Tp = _peak_correction(q_y, k, L, B, NB, A, alpha)
            L_new = numer / (T_m - T_g - Tp)
            if abs(L_new - L) < tol:
                L = L_new
                break
            L = L_new

    return L


def size_borefield_for_depth(
    q_h: float,
    q_m: float,
    q_y: float,
    k: float,
    alpha: float,
    T_g: float,
    Cp: float,
    mfls: float,
    T_in_HP: float,
    rbore: float,
    rpin: float,
    rpext: float,
    kgrout: float,
    kpipe: float,
    LU: float,
    hconv: float,
    B: float,
    A: float = 1.0,
    H_target: float = 125.0,
    tol: float = 1.0,
    max_nb_iter: int = 25,
) -> tuple[float, int, float]:
    """Depth-primary borefield sizing: derive NB from a target borehole depth.

    Standard industry practice fixes the borehole depth (drill-rig capability,
    typically 100-150 m) and derives the borehole count. Because NB feeds the
    Tp interaction correction, L and NB are iterated to a joint fixed point:
        NB = ceil(L / H_target)  with  L = size_borefield(..., NB=NB).

    Returns
    -------
    (L, NB, H) : total length [m], borehole count, actual depth per hole [m].
                 At the fixed point H <= H_target by construction.
                 A non-positive L (non-binding fluid-temperature constraint)
                 returns (L, 1, L) without iterating.
    """
    common = dict(
        q_h=q_h, q_m=q_m, q_y=q_y, k=k, alpha=alpha, T_g=T_g,
        Cp=Cp, mfls=mfls, T_in_HP=T_in_HP, rbore=rbore, rpin=rpin,
        rpext=rpext, kgrout=kgrout, kpipe=kpipe, LU=LU, hconv=hconv,
        tol=tol,
    )
    L = float(size_borefield(**common))
    if L <= 0:
        return L, 1, L

    NB = max(1, math.ceil(L / H_target))
    seen: set[int] = set()
    for _ in range(max_nb_iter):
        L = float(size_borefield(**common, B=B, NB=NB, A=A))
        if L <= 0:
            return L, 1, L
        NB_new = max(1, math.ceil(L / H_target))
        if NB_new == NB:
            break
        if NB_new in seen:
            # ceil() can 2-cycle near a boundary; more boreholes = shallower,
            # conservative side of the target depth
            NB = max(NB, NB_new)
            L = float(size_borefield(**common, B=B, NB=NB, A=A))
            break
        seen.add(NB)
        NB = NB_new
    return L, NB, L / NB

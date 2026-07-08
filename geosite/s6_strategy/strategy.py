from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import (
    PROTOTYPE_AREAS_M2 as _PROTOTYPE_AREAS_M2,
    compute_nb_range,
    find_optimal_nb,
)
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
)
from geosite.s6_strategy.models import StrategyResult
from geosite.s4_sizing.defaults import (
    ADVANCED_DEFAULTS as _ADVANCED_DEFAULTS,
    T_IN_HP_DEFAULTS as _T_IN_HP,
)


def _do_size(q_h, q_m, q_y, k, alpha, T_g, mode, NB, B, A, adv) -> float:
    return float(size_borefield(
        q_h=q_h, q_m=q_m, q_y=q_y,
        k=k, alpha=alpha, T_g=T_g,
        T_in_HP=_T_IN_HP[mode],
        B=B, NB=NB, A=A,
        **adv,
    ))


def _peaker_side(profile: list, cutoff_W: float, cap_W: float, side: str) -> float:
    """Peak excess [kW] above cutoff_W, capped at cap_W, for one load side."""
    if side == "cooling":
        return max(
            (min(h, cap_W) - cutoff_W for h in profile if h > cutoff_W),
            default=0.0,
        ) / 1000.0
    else:  # heating
        return max(
            (min(-h, cap_W) - cutoff_W for h in profile if h < -cutoff_W),
            default=0.0,
        ) / 1000.0


def run_strategy(
    building_type: str,
    climate_zone: str,
    k: float,
    alpha: float,
    T_g: float,
    NB: int | None = None,
    B: float = 6.0,
    A: float = 9.0,
    H_min: float = 125.0,
    ldc_cutoff_pct: float = 10.0,
    ignore_top_pct: float = 0.4,
    imbalance_threshold: float = 1.25,
    floor_area_m2=None,
    year_factor: float = 1.0,
    envelope_factor: float = 1.0,
    state=None,
    **sizing_params,
) -> StrategyResult:
    """Run mandatory hybrid GSHP strategy analysis with ASHRAE 99.6% cap and two LDC cutoff methods.

    NB: if None, computed from H_min (minimum depth per borehole); otherwise used as-is.
    A: borefield array aspect ratio (default 9.0, elongated arrangement).
    H_min: minimum borehole depth [m] used when computing NB (default 125 m).
    ignore_top_pct: top % of hours capped at ASHRAE design-condition load (default 0.4% → 99.6%).
    envelope_factor: building-design load multiplier (WWR x envelope x glazing); 1.0 until calibrated.
    """
    adv = {k_: sizing_params.get(k_, v) for k_, v in _ADVANCED_DEFAULTS.items()}

    # --- Load and scale profile ---
    raw_profile = load_hourly_profile(building_type, climate_zone)
    scale = year_factor * envelope_factor
    if floor_area_m2 is not None:
        proto_area = _PROTOTYPE_AREAS_M2[building_type]
        scale *= floor_area_m2 / proto_area
    profile = scale_profile(raw_profile, scale)

    # --- LDC: ASHRAE cap + both cutoff methods ---
    ldc = compute_ldc(profile, ldc_cutoff_pct, ignore_top_pct)
    cap_W = ldc["cap_W"]
    m1_cutoff_W = ldc["m1_cutoff_W"]
    m2_cutoff_W = ldc["m2_cutoff_W"]

    # --- Extract raw pulses ---
    q_h_heat_raw, q_m_heat, q_y_heat = extract_one_sided_pulses(profile, "heating")
    q_h_cool_raw, q_m_cool, q_y_cool = extract_one_sided_pulses(profile, "cooling")

    # Apply ASHRAE cap to q_h only (monthly/annual averages are unaffected by extreme peaks)
    q_h_heat = max(q_h_heat_raw, -cap_W) if q_h_heat_raw < 0 else q_h_heat_raw
    q_h_cool = min(q_h_cool_raw,  cap_W) if q_h_cool_raw > 0 else q_h_cool_raw

    # --- Quick noint sizing to determine dominant mode ---
    L_h_ni = _do_size(q_h_heat, q_m_heat, q_y_heat, k, alpha, T_g, "heating", None, None, A, adv) if q_h_heat < 0 else 0.0
    L_c_ni = _do_size(q_h_cool, q_m_cool, q_y_cool, k, alpha, T_g, "cooling", None, None, A, adv) if q_h_cool > 0 else 0.0

    if L_h_ni == 0.0 and L_c_ni == 0.0:
        imbalance_ratio = 1.0
        dominant_mode = "balanced"
    elif L_h_ni == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "cooling"
    elif L_c_ni == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "heating"
    else:
        imbalance_ratio = max(L_h_ni, L_c_ni) / min(L_h_ni, L_c_ni)
        dominant_mode = "heating" if L_h_ni >= L_c_ni else "cooling"

    # --- Compute NB from the building footprint (if not provided) ---
    nb_min = nb_max = None
    if NB is None:
        nb_min, nb_max, _fp = compute_nb_range(floor_area_m2, building_type,
                                               spacing_m=B)
        if dominant_mode in ("heating", "balanced"):
            q_h_d, q_m_d, q_y_d, d_mode = q_h_heat, q_m_heat, q_y_heat, "heating"
        else:
            q_h_d, q_m_d, q_y_d, d_mode = q_h_cool, q_m_cool, q_y_cool, "cooling"
        NB, _, _ = find_optimal_nb(
            nb_min, nb_max, q_h=q_h_d, q_m=q_m_d, q_y=q_y_d,
            k=k, alpha=alpha, T_g=T_g, H_min=H_min, B=B, A=A,
            T_in_HP=_T_IN_HP[d_mode], **adv,
        )

    # --- Full two-sided sizing with final NB ---
    L_h = _do_size(q_h_heat, q_m_heat, q_y_heat, k, alpha, T_g, "heating", NB, B, A, adv) if q_h_heat < 0 else 0.0
    L_c = _do_size(q_h_cool, q_m_cool, q_y_cool, k, alpha, T_g, "cooling", NB, B, A, adv) if q_h_cool > 0 else 0.0

    L_before = max(L_h, L_c)
    H_before = L_before / NB

    # Determine before_mode for trimmed sizing (use whichever side governs)
    if dominant_mode in ("heating", "balanced") and L_h >= L_c:
        q_h_before, q_m_before, q_y_before = q_h_heat, q_m_heat, q_y_heat
        before_mode = "heating"
    else:
        q_h_before, q_m_before, q_y_before = q_h_cool, q_m_cool, q_y_cool
        before_mode = "cooling"

    case = 1 if imbalance_ratio > imbalance_threshold else 2
    trim_mode = dominant_mode if case == 1 else "balanced"

    # --- Method 1: hours-based cutoff ---
    trimmed_m1 = trim_profile(profile, m1_cutoff_W, trim_mode)
    q_h_t1, q_m_t1, q_y_t1 = extract_one_sided_pulses(trimmed_m1, before_mode)
    if before_mode == "cooling":
        q_h_t1 = min(q_h_t1, cap_W)
    else:
        q_h_t1 = max(q_h_t1, -cap_W)
    L_after_m1 = _do_size(q_h_t1, q_m_t1, q_y_t1, k, alpha, T_g, before_mode, NB, B, A, adv)
    H_after_m1 = L_after_m1 / NB

    # Peakers m1
    if case == 1:
        peaker_heat_kW_m1 = _peaker_side(profile, m1_cutoff_W, cap_W, "heating")
        peaker_cool_kW_m1 = _peaker_side(profile, m1_cutoff_W, cap_W, "cooling")
        peaker_kW_m1 = peaker_cool_kW_m1 if dominant_mode == "cooling" else peaker_heat_kW_m1
    else:
        peaker_heat_kW_m1 = _peaker_side(profile, m1_cutoff_W, cap_W, "heating")
        peaker_cool_kW_m1 = _peaker_side(profile, m1_cutoff_W, cap_W, "cooling")
        peaker_kW_m1 = max(peaker_heat_kW_m1, peaker_cool_kW_m1)

    # --- Method 2: energy-based cutoff ---
    trimmed_m2 = trim_profile(profile, m2_cutoff_W, trim_mode)
    q_h_t2, q_m_t2, q_y_t2 = extract_one_sided_pulses(trimmed_m2, before_mode)
    if before_mode == "cooling":
        q_h_t2 = min(q_h_t2, cap_W)
    else:
        q_h_t2 = max(q_h_t2, -cap_W)
    L_after_m2 = _do_size(q_h_t2, q_m_t2, q_y_t2, k, alpha, T_g, before_mode, NB, B, A, adv)
    H_after_m2 = L_after_m2 / NB

    # Peakers m2
    if case == 1:
        peaker_heat_kW_m2 = _peaker_side(profile, m2_cutoff_W, cap_W, "heating")
        peaker_cool_kW_m2 = _peaker_side(profile, m2_cutoff_W, cap_W, "cooling")
        peaker_kW_m2 = peaker_cool_kW_m2 if dominant_mode == "cooling" else peaker_heat_kW_m2
    else:
        peaker_heat_kW_m2 = _peaker_side(profile, m2_cutoff_W, cap_W, "heating")
        peaker_cool_kW_m2 = _peaker_side(profile, m2_cutoff_W, cap_W, "cooling")
        peaker_kW_m2 = max(peaker_heat_kW_m2, peaker_cool_kW_m2)

    # --- Backward-compat legacy peaker fields (use M1) ---
    if case == 1:
        if dominant_mode == "heating":
            peaker_kW = peaker_kW_m1
            peaker_type = "electric_heater"
        else:
            peaker_kW = peaker_kW_m1
            peaker_type = "chiller"
    else:
        peaker_kW = peaker_kW_m1
        peaker_type = "electric_heater+chiller"

    peaker_heat_kW = peaker_heat_kW_m1
    peaker_cool_kW = peaker_cool_kW_m1

    # --- Costs ---
    def _cost(L_m: float) -> dict:
        res = estimate_cost(L_m=L_m, NB=NB, B_m=B, state=state)
        base = res["base"]
        return {
            "total_usd": round(base.total_usd, 2),
            "cost_per_ft": round(base.cost_per_ft, 2),
            "scenario": "base",
        }

    cost_before = _cost(L_before)
    cost_after  = _cost(L_after_m1)   # backward compat: legacy cost_after = M1

    return StrategyResult(
        case=case,
        imbalance_ratio=imbalance_ratio,
        dominant_mode=dominant_mode,
        L_h=L_h,
        L_c=L_c,
        ldc_cutoff_pct=ldc_cutoff_pct,
        cutoff_W=m1_cutoff_W,            # backward compat
        peaker_kW=peaker_kW,
        peaker_type=peaker_type,
        peaker_heat_kW=peaker_heat_kW,
        peaker_cool_kW=peaker_cool_kW,
        q_h_before=q_h_before,
        q_m_before=q_m_before,
        q_y_before=q_y_before,
        q_h_trimmed=q_h_t1,             # backward compat: M1 trimmed pulses
        q_m_trimmed=q_m_t1,
        q_y_trimmed=q_y_t1,
        L_before=L_before,
        H_before=H_before,
        L_after=L_after_m1,             # backward compat: M1
        H_after=H_after_m1,
        NB=NB,
        cost_before=cost_before,
        cost_after=cost_after,
        hourly_profile=profile,
        hourly_trimmed=trimmed_m1,      # backward compat: M1 trim
        # New fields
        cap_W=cap_W,
        ignore_top_pct=ignore_top_pct,
        H_min=H_min,
        nb_min=nb_min,
        nb_max=nb_max,
        m1_cutoff_W=m1_cutoff_W,
        m1_cutoff_h=ldc["m1_cutoff_idx"],
        m1_gshp_hours_pct=ldc["m1_gshp_hours_pct"],
        m1_gshp_energy_pct=ldc["m1_gshp_energy_pct"],
        m1_peaker_kW=peaker_kW_m1,
        m1_L_after=L_after_m1,
        m1_H_after=H_after_m1,
        m2_cutoff_W=m2_cutoff_W,
        m2_cutoff_h=ldc["m2_cutoff_idx"],
        m2_gshp_hours_pct=ldc["m2_gshp_hours_pct"],
        m2_gshp_energy_pct=ldc["m2_gshp_energy_pct"],
        m2_peaker_kW=peaker_kW_m2,
        m2_L_after=L_after_m2,
        m2_H_after=H_after_m2,
        m1_peaker_energy_Wh=ldc["m1_peaker_energy_Wh"],
        m2_peaker_energy_Wh=ldc["m2_peaker_energy_Wh"],
    )

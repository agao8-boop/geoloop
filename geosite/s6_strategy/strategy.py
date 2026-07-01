from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s5_cost import estimate_cost
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
)
from geosite.s6_strategy.models import StrategyResult

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
_T_IN_HP = {"heating": 5.0, "cooling": 40.2}
_PROTOTYPE_AREAS_M2 = {"small_office": 511, "medium_office": 4982, "large_office": 46320}


def _do_size(q_h, q_m, q_y, k, alpha, T_g, mode, NB, B, A, adv) -> float:
    return float(size_borefield(
        q_h=q_h, q_m=q_m, q_y=q_y,
        k=k, alpha=alpha, T_g=T_g,
        T_in_HP=_T_IN_HP[mode],
        B=B, NB=NB, A=A,
        **adv,
    ))


def run_strategy(
    building_type: str,
    climate_zone: str,
    k: float,
    alpha: float,
    T_g: float,
    NB: int,
    B: float,
    A: float = 1.0,
    ldc_cutoff_pct: float = 10.0,
    imbalance_threshold: float = 1.25,
    floor_area_m2=None,
    year_factor: float = 1.0,
    state=None,
    **sizing_params,
) -> StrategyResult:
    """Run mandatory hybrid GSHP strategy analysis.

    Loads 8760h profile, detects imbalance, applies LDC cutoff to size peaker,
    re-sizes borefield on trimmed profile, computes before/after cost.
    """
    adv = {k_: sizing_params.get(k_, v) for k_, v in _ADVANCED_DEFAULTS.items()}

    # --- Load and scale 8760h profile ---
    raw_profile = load_hourly_profile(building_type, climate_zone)
    scale = year_factor
    if floor_area_m2 is not None:
        proto_area = _PROTOTYPE_AREAS_M2.get(building_type, 1.0)
        scale *= floor_area_m2 / proto_area
    profile = scale_profile(raw_profile, scale)

    # --- Separate heating/cooling sizing to detect imbalance ---
    q_h_heat, q_m_heat, q_y_heat = extract_one_sided_pulses(profile, "heating")
    q_h_cool, q_m_cool, q_y_cool = extract_one_sided_pulses(profile, "cooling")

    # Guard: if one side has no load (all-heating or all-cooling building), use tiny value
    L_h = _do_size(q_h_heat, q_m_heat, q_y_heat, k, alpha, T_g, "heating", NB, B, A, adv) if q_h_heat < 0 else 0.0
    L_c = _do_size(q_h_cool, q_m_cool, q_y_cool, k, alpha, T_g, "cooling", NB, B, A, adv) if q_h_cool > 0 else 0.0

    # --- Imbalance detection ---
    if L_h == 0.0 and L_c == 0.0:
        imbalance_ratio = 1.0
        dominant_mode = "balanced"
    elif L_h == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "cooling"
    elif L_c == 0.0:
        imbalance_ratio = float("inf")
        dominant_mode = "heating"
    else:
        imbalance_ratio = max(L_h, L_c) / min(L_h, L_c)
        dominant_mode = "heating" if L_h >= L_c else "cooling"

    case = 1 if imbalance_ratio > imbalance_threshold else 2

    # --- LDC cutoff (from full mixed profile) ---
    ldc = compute_ldc(profile, ldc_cutoff_pct)
    cutoff_W = ldc["cutoff_W"]

    # --- Peaker sizing ---
    # Always trim both sides: cutoff_W is based on |load| across all hours,
    # so any hour exceeding cutoff_W in either direction goes to a peaker.
    trim_mode = "balanced"

    peaker_heat_kW = max(
        (abs(h) - cutoff_W for h in profile if h < 0 and abs(h) > cutoff_W), default=0.0
    ) / 1000.0
    peaker_cool_kW = max(
        (h - cutoff_W for h in profile if h > 0 and h > cutoff_W), default=0.0
    ) / 1000.0

    if case == 1:
        if dominant_mode == "heating":
            peaker_kW = peaker_heat_kW
            peaker_type = "electric_heater"
        else:
            peaker_kW = peaker_cool_kW
            peaker_type = "chiller"
    else:
        peaker_kW = max(peaker_heat_kW, peaker_cool_kW)
        peaker_type = "electric_heater+chiller"

    # --- Before sizing: use dominant mode's original three-pulse ---
    if dominant_mode in ("heating", "balanced") and L_h >= L_c:
        q_h_before, q_m_before, q_y_before = q_h_heat, q_m_heat, q_y_heat
        before_mode = "heating"
    else:
        q_h_before, q_m_before, q_y_before = q_h_cool, q_m_cool, q_y_cool
        before_mode = "cooling"

    L_before = _do_size(q_h_before, q_m_before, q_y_before, k, alpha, T_g, before_mode, NB, B, A, adv)
    H_before = L_before / NB

    # --- Trim profile + re-derive three-pulse (pinned to before_mode for sign consistency) ---
    trimmed = trim_profile(profile, cutoff_W, trim_mode)
    q_h_trimmed, q_m_trimmed, q_y_trimmed = extract_one_sided_pulses(trimmed, before_mode)

    # --- After sizing: trimmed profile uses same before_mode for T_in_HP ---
    L_after = _do_size(q_h_trimmed, q_m_trimmed, q_y_trimmed, k, alpha, T_g, before_mode, NB, B, A, adv)
    H_after = L_after / NB

    # --- Cost before/after ---
    def _cost(L_m: float) -> dict:
        res = estimate_cost(L_m=L_m, NB=NB, B_m=B, state=state)
        base = res["base"]
        return {
            "total_usd": round(base.total_usd, 2),
            "cost_per_ft": round(base.cost_per_ft, 2),
            "scenario": "base",
        }

    cost_before = _cost(L_before)
    cost_after = _cost(L_after)

    return StrategyResult(
        case=case,
        imbalance_ratio=imbalance_ratio,
        dominant_mode=dominant_mode,
        L_h=L_h,
        L_c=L_c,
        ldc_cutoff_pct=ldc_cutoff_pct,
        cutoff_W=cutoff_W,
        peaker_kW=peaker_kW,
        peaker_type=peaker_type,
        peaker_heat_kW=peaker_heat_kW,
        peaker_cool_kW=peaker_cool_kW,
        q_h_before=q_h_before,
        q_m_before=q_m_before,
        q_y_before=q_y_before,
        q_h_trimmed=q_h_trimmed,
        q_m_trimmed=q_m_trimmed,
        q_y_trimmed=q_y_trimmed,
        L_before=L_before,
        H_before=H_before,
        L_after=L_after,
        H_after=H_after,
        NB=NB,
        cost_before=cost_before,
        cost_after=cost_after,
        hourly_profile=profile,
        hourly_trimmed=trimmed,
    )

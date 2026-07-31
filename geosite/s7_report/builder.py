"""s7 — deterministic report assembly.

Pure functions, no I/O. Assembles the fixed-structure report (design,
performance, cost & savings) from data the client already holds after
stage1 -> stage2 -> cost -> strategy, plus a deterministic 0-100
GSHP feasibility recommendation score.
"""

# Economics constants.
# Sources: EIA commercial rates, industry cost surveys, Peter Rumsey (Jul 2026).
ELEC_USD_PER_KWH = 0.13      # EIA commercial average retail electricity
GAS_USD_PER_THERM = 1.20     # EIA commercial natural gas
KWH_PER_THERM = 29.3
BOILER_EFF = 0.85            # typical non-condensing gas boiler
CHILLER_COP = 3.0            # air-cooled chiller seasonal COP
GSHP_COP_HEAT = 4.0          # GSHP seasonal heating COP
GSHP_COP_COOL = 4.5          # GSHP seasonal cooling COP
# Conventional heating+cooling PLANT only — excludes interior distribution
# (air handlers, ductwork, VAV boxes). Confirmed scope: Peter Rumsey Jul 2026.
# Derived range: $20-45/sqft (all-in $32-58 minus distribution $8-14).
# $35/sqft = US commercial mid-upper; confirmed by Peter as screening default.
# Sources: Terrapin/RSMeans 2026, National Facility Contractors 2026.
CONV_USD_PER_SQFT_DEFAULT = 35.0
# GSHP inside-building package: HP units + MER pumps + piping + controls.
# Excludes ground loop (in borefield_usd). Commercial 30-200 ton scale:
#   Total GSHP system: $5,000-8,000/ton; ground loop = 60-65% of total.
#   HP + MER residual: $1,800-3,200/ton → $510-910/kW; mid ≈ $600/kW.
# Sources: Rafferty (2002) OSTI, geothermalfinder 2026, doctorheatpump.com.
HP_USD_PER_KW = 600.0


def _peak_kw(loads: dict) -> float:
    """Governing peak thermal load magnitude [kW] across both modes."""
    candidates = [loads.get("q_h_heat"), loads.get("q_h_cool"), loads.get("q_h")]
    return max(abs(v) for v in candidates if v is not None) / 1000.0


def _design_section(design: dict, site: dict) -> dict:
    fp = design.get("footprint") or {}
    return {
        "building_type": design.get("building_type"),
        "NB": design.get("NB"),
        "H_m": design.get("H"),
        "L_m": design.get("L"),
        "L_ft": round(design["L"] * 3.28084) if design.get("L") is not None else None,
        "B_m": design.get("B"),
        "A": design.get("A"),
        "governing": design.get("governing"),
        "L_heat_m": design.get("L_heat"),
        "L_cool_m": design.get("L_cool"),
        "imbalance_m": design.get("imbalance_m"),
        "solar_thermal_recommended": design.get("solar_thermal_recommended"),
        "nb_source": design.get("nb_source"),
        "nb_min": design.get("nb_min"),
        "nb_max": design.get("nb_max"),
        "capacity_warning": design.get("capacity_warning"),
        "footprint_shape": fp.get("shape_label"),
        "footprint_m2": fp.get("footprint_m2"),
        "n_floors": fp.get("n_floors"),
        "k_effective": site.get("k_effective"),
        "alpha": site.get("alpha"),
        "T_g": site.get("T_g"),
        "climate_zone": site.get("climate_zone"),
    }


def _performance_section(strategy: dict | None) -> dict:
    if not strategy:
        return {"available": False}
    comparison = strategy.get("comparison") or {}

    def _method(m: dict) -> dict:
        return {
            "gshp_hours_pct": m.get("gshp_hours_pct"),
            "gshp_energy_pct": m.get("gshp_energy_pct"),
            "peaker_kW": m.get("peaker_kW"),
            "peaker_energy_kwh": m.get("peaker_energy_kwh"),
            "L_after_m": m.get("L_after"),
            "savings_pct": m.get("savings_pct"),
        }

    return {
        "available": True,
        "peaker_kW": strategy.get("peaker_kW"),
        "peaker_type": strategy.get("peaker_type"),
        "cap_kW": (strategy["cap_W"] / 1000.0
                   if strategy.get("cap_W") is not None else None),
        "dominant_mode": strategy.get("dominant_mode"),
        "L_before_m": strategy.get("L_before"),
        "m1": _method(comparison.get("m1") or {}),
        "m2": _method(comparison.get("m2") or {}),
    }


def _cost_savings_section(cost: dict | None, peak_kw: float,
                          heat_kwh: float, cool_kwh: float,
                          floor_area_m2: float | None = None,
                          conv_usd_per_sqft: float = CONV_USD_PER_SQFT_DEFAULT) -> dict:
    if not cost:
        return {"available": False}

    borefield_usd = (cost.get("base") or {}).get("total_usd")
    if borefield_usd is None:
        return {"available": False}

    if not floor_area_m2:
        return {"available": False, "note": "Floor area required for cost estimate"}

    floor_area_sqft = floor_area_m2 * 10.7639
    conv_capex = floor_area_sqft * conv_usd_per_sqft
    gshp_capex = borefield_usd + peak_kw * HP_USD_PER_KW

    conv_opex = (heat_kwh / BOILER_EFF / KWH_PER_THERM * GAS_USD_PER_THERM
                 + cool_kwh / CHILLER_COP * ELEC_USD_PER_KWH)
    gshp_opex = (heat_kwh / GSHP_COP_HEAT * ELEC_USD_PER_KWH
                 + cool_kwh / GSHP_COP_COOL * ELEC_USD_PER_KWH)

    annual_savings = conv_opex - gshp_opex
    extra_capex = gshp_capex - conv_capex
    if annual_savings > 0:
        payback = extra_capex / annual_savings if extra_capex > 0 else 0.0
    else:
        payback = None

    return {
        "available": True,
        "borefield_best_usd": (cost.get("best") or {}).get("total_usd"),
        "borefield_base_usd": borefield_usd,
        "borefield_worst_usd": (cost.get("worst") or {}).get("total_usd"),
        "hp_equipment_usd": peak_kw * HP_USD_PER_KW,
        "gshp_capex_usd": gshp_capex,
        "conv_capex_usd": conv_capex,
        "conv_usd_per_sqft": conv_usd_per_sqft,
        "floor_area_sqft": round(floor_area_sqft),
        "conv_opex_usd_yr": conv_opex,
        "gshp_opex_usd_yr": gshp_opex,
        "annual_savings_usd_yr": annual_savings,
        "simple_payback_yr": payback,
        "note": ("Conventional scope: heating+cooling plant only — excludes "
                 "interior distribution (air handlers, ductwork). "
                 "GSHP operating cost excludes peaker energy (additional)."),
    }


def _review_input(design: dict, site: dict, loads: dict,
                  performance: dict, cost_savings: dict,
                  peak_kw: float) -> dict:
    ri = {
        "building_type": design.get("building_type"),
        "floor_area_m2": loads.get("floor_area_m2"),
        "climate_zone": site.get("climate_zone"),
        "k_eff": site.get("k_effective"),
        "NB": design.get("NB"),
        "H": design.get("H"),
        "L": design.get("L"),
        "B": design.get("B"),
        "governing": design.get("governing"),
        "imbalance_m": design.get("imbalance_m"),
        "solar_flag": design.get("solar_thermal_recommended"),
        "nb_source": design.get("nb_source"),
        "capacity_warning": design.get("capacity_warning"),
        "q_h_kW": round(peak_kw, 1),
    }
    if performance.get("available"):
        ri["coverage"] = {
            "m1": {"hours_pct": performance["m1"]["gshp_hours_pct"],
                   "energy_pct": performance["m1"]["gshp_energy_pct"]},
            "m2": {"hours_pct": performance["m2"]["gshp_hours_pct"],
                   "energy_pct": performance["m2"]["gshp_energy_pct"]},
        }
        ri["peaker_kW"] = performance.get("peaker_kW")
        ri["peaker_energy_kwh_m1"] = performance["m1"].get("peaker_energy_kwh")
    if cost_savings.get("available"):
        ri["borefield_cost_usd"] = {
            "best": cost_savings.get("borefield_best_usd"),
            "base": cost_savings.get("borefield_base_usd"),
            "worst": cost_savings.get("borefield_worst_usd"),
        }
        ri["gshp_capex_usd"] = cost_savings.get("gshp_capex_usd")
        ri["conv_capex_usd"] = cost_savings.get("conv_capex_usd")
        ri["simple_payback_yr"] = cost_savings.get("simple_payback_yr")
    return ri


# Climate zone → GSHP suitability baseline (0–35 pts).
# 5A/5B best: cold winters + near-balanced commercial loads → GSHP saves on both sides.
# 1A worst: near-zero heating, extreme imbalance, ground temperature rises over time.
_CLIMATE_SUITABILITY: dict[str, int] = {
    "1A": 3,  "1B": 3,
    "2A": 8,  "2B": 7,
    "3A": 18, "3B": 17, "3C": 12,
    "4A": 28, "4B": 26, "4C": 22,
    "5A": 35, "5B": 33, "5C": 30,
    "6A": 30, "6B": 29,
    "7":  25, "8":  20,
}

SCORE_BENCHMARK = 70  # zone-5A (Chicago/Buffalo) medium office reference


def compute_recommendation_score(report_data: dict) -> dict:
    """Deterministic 0-100 GSHP suitability score. Benchmark = 70.

    Three orthogonal factors (no overlapping inputs):
      1. Climate zone suitability (0–35): fixed per ASHRAE zone; cold balanced
         climates best (5A/5B), hot cooling-dominant climates worst (1A).
      2. Bilateral load index (0–40): min(heat_kwh, cool_kwh) / floor_area_m2.
         Rewards buildings where GSHP saves energy on BOTH heating and cooling.
         Near-zero nondominant load (Miami) → ~4 pts; Chicago strong both sides → 35-40.
      3. Footprint feasibility (0–25): can the required boreholes physically fit?

    Score ≥ 70: GSHP recommended (above benchmark).
    Score < 70: below benchmark — caution or alternative systems warranted.
    Cost is excluded from this score; see cost_savings section for economics.
    """
    design = report_data.get("design") or {}
    inputs_echo = report_data.get("inputs_echo") or {}
    review_input = report_data.get("review_input") or {}
    factors = []

    # 1. Climate zone suitability (0–35) ─────────────────────────────────
    climate_zone = design.get("climate_zone") or ""
    cz_pts = _CLIMATE_SUITABILITY.get(climate_zone)
    if cz_pts is not None:
        if cz_pts >= 30:
            cz_note = "cold/balanced climate — GSHP excels vs conventional"
        elif cz_pts >= 20:
            cz_note = "moderate climate — GSHP competitive"
        elif cz_pts >= 12:
            cz_note = "warm climate — GSHP benefit reduced; thermal imbalance risk"
        else:
            cz_note = "hot climate — extreme imbalance, ground warms over time"
    else:
        cz_pts, cz_note = 20, "climate zone unknown — assumed moderate"
    factors.append({"label": "Climate zone suitability",
                    "value": climate_zone or "unknown",
                    "contribution": cz_pts, "note": cz_note})

    # 2. Load suitability (0–40) ──────────────────────────────────────────
    # Two orthogonal sub-scores (each 0–20), summed to 0–40:
    #   A. Load intensity: (heat+cool)/floor_m2 — absolute load size matters;
    #      low-load mild-climate buildings don't justify GSHP capital cost.
    #   B. Thermal balance: min/max ratio — imbalanced ground loop degrades over time.
    heat_kwh = float(inputs_echo.get("annual_heat_kwh_th") or 0.0)
    cool_kwh = float(inputs_echo.get("annual_cool_kwh_th") or 0.0)
    floor_m2 = float(
        review_input.get("floor_area_m2") or design.get("footprint_m2") or 0.0
    )
    if floor_m2 > 0 and (heat_kwh + cool_kwh) > 0:
        total_intensity = (heat_kwh + cool_kwh) / floor_m2  # kWh/m²/yr
        balance_ratio   = min(heat_kwh, cool_kwh) / max(heat_kwh, cool_kwh)

        # A: intensity (0–20)
        if total_intensity >= 50:
            int_pts, int_note = 20, "high load intensity — GSHP capital well amortised"
        elif total_intensity >= 25:
            int_pts, int_note = 14, "moderate-high intensity — solid GSHP economics"
        elif total_intensity >= 10:
            int_pts, int_note = 8,  "moderate intensity — GSHP viable"
        elif total_intensity >= 3:
            int_pts, int_note = 4,  "low intensity — small loads limit GSHP payback"
        else:
            int_pts, int_note = 1,  "near-zero load — GSHP oversized for this building"

        # B: balance (0–20)
        if balance_ratio >= 0.70:
            bal_pts, bal_note = 20, "near-balanced — ground loop recovers well year-round"
        elif balance_ratio >= 0.45:
            bal_pts, bal_note = 14, "moderately balanced — acceptable long-term ground temperature"
        elif balance_ratio >= 0.25:
            bal_pts, bal_note = 10, "somewhat imbalanced — monitor ground temperature trend"
        elif balance_ratio >= 0.10:
            bal_pts, bal_note = 5,  "strongly imbalanced — thermal drift risk without supplemental"
        else:
            bal_pts, bal_note = 1,  "near-single-mode — ground loop will degrade; hybrid essential"

        bl_pts = int_pts + bal_pts
        bl_value = (f"{round(total_intensity, 1)} kWh/m²/yr total · "
                    f"balance {round(balance_ratio, 2)}")
        bl_note = f"Intensity: {int_note}. Balance: {bal_note}."
    else:
        bl_pts  = 18   # conservative mid-range default
        bl_value = "n/a"
        bl_note = "floor area or load data missing — assumed moderate"
    factors.append({"label": "Load suitability",
                    "value": bl_value,
                    "contribution": bl_pts, "note": bl_note})

    # 3. Footprint feasibility (0–25) ─────────────────────────────────────
    nb_source = design.get("nb_source")
    if nb_source == "optimizer":
        fp_pts, fp_note = 25, "optimal borehole count fits within footprint"
    elif nb_source == "depth_too_deep":
        fp_pts, fp_note = 3, "load exceeds drillable depth — nb_max boreholes still require >250 m; hybrid or larger footprint needed"
    elif nb_source == "capacity_capped":
        fp_pts, fp_note = 6, "load exceeds footprint — clamped to nb_max, deeper boreholes"
    elif nb_source == "depth_fallback":
        fp_pts, fp_note = 16, "small load — depth-primary sizing; footprint not a constraint"
    else:
        fp_pts, fp_note = 14, "footprint check not run"
    factors.append({"label": "Footprint feasibility",
                    "value": nb_source or "unknown",
                    "contribution": fp_pts, "note": fp_note})

    score = sum(f["contribution"] for f in factors)
    delta = score - SCORE_BENCHMARK
    if score >= 80:
        grade = "Excellent"
    elif score >= SCORE_BENCHMARK:
        grade = "Good"
    elif score >= 55:
        grade = "Fair"
    else:
        grade = "Poor"

    return {
        "score": score,
        "grade": grade,
        "benchmark": SCORE_BENCHMARK,
        "vs_benchmark": f"{'+' if delta >= 0 else ''}{delta}",
        "factors": factors,
    }


def build_report(data: dict) -> dict:
    """Assemble the fixed-structure report from the /api/report request body."""
    design = data.get("design") or {}
    site = data.get("site") or {}
    loads = data.get("loads") or {}
    heat_kwh = float(data.get("annual_heat_kwh_th") or 0.0)
    cool_kwh = float(data.get("annual_cool_kwh_th") or 0.0)

    peak_kw = _peak_kw(loads) if loads.get("q_h") is not None else 0.0
    floor_area_m2 = loads.get("floor_area_m2") or design.get("floor_area_m2")
    if not floor_area_m2:
        # Fall back to effective floor area from footprint meta (uses prototype if user omitted it)
        fp = design.get("footprint") or {}
        floor_area_m2 = fp.get("floor_area_m2")
    conv_usd_per_sqft = float(data.get("conv_usd_per_sqft") or CONV_USD_PER_SQFT_DEFAULT)

    design_section = _design_section(design, site)
    performance = _performance_section(data.get("strategy"))
    cost_savings = _cost_savings_section(data.get("cost"), peak_kw,
                                         heat_kwh, cool_kwh,
                                         floor_area_m2=floor_area_m2,
                                         conv_usd_per_sqft=conv_usd_per_sqft)

    report = {
        "design": design_section,
        "performance": performance,
        "cost_savings": cost_savings,
        "review_input": _review_input(design, site, loads, performance,
                                      cost_savings, peak_kw),
        "inputs_echo": {
            "annual_heat_kwh_th": heat_kwh,
            "annual_cool_kwh_th": cool_kwh,
            "peak_kw": peak_kw,
        },
    }
    report["recommendation"] = compute_recommendation_score(report)
    return report

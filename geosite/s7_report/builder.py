"""s7 — deterministic report assembly.

Pure functions, no I/O. Assembles the fixed-structure report (design,
performance, cost & savings) from data the client already holds after
stage1 -> stage2 -> cost -> strategy, and prepares the compact review_input
dict consumed by the AI design review (ai.py).
"""

# Economics constants.
# PLACEHOLDER — rough US commercial averages, pending professor calibration.
ELEC_USD_PER_KWH = 0.13      # EIA commercial average retail electricity
GAS_USD_PER_THERM = 1.20     # EIA commercial natural gas
KWH_PER_THERM = 29.3
BOILER_EFF = 0.85            # typical non-condensing gas boiler
CHILLER_COP = 3.0            # air-cooled chiller seasonal COP
GSHP_COP_HEAT = 4.0          # GSHP seasonal heating COP
GSHP_COP_COOL = 4.5          # GSHP seasonal cooling COP
# Gas boiler + air-cooled chiller plant installed (low, mid, high),
# ~= $1.2-2.5k/ton converted to $/kW thermal.
CONV_USD_PER_KW = (340.0, 500.0, 710.0)
# GSHP water-to-air units installed, ~= $2k/ton converted to $/kW thermal.
HP_USD_PER_KW = 570.0


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
        "footprint_length_m": fp.get("length_m"),
        "footprint_width_m": fp.get("width_m"),
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
                          heat_kwh: float, cool_kwh: float) -> dict:
    if not cost:
        return {"available": False}

    borefield_usd = (cost.get("base") or {}).get("total_usd")
    if borefield_usd is None:
        return {"available": False}

    conv_low, conv_mid, conv_high = (peak_kw * r for r in CONV_USD_PER_KW)
    gshp_capex = borefield_usd + peak_kw * HP_USD_PER_KW

    conv_opex = (heat_kwh / BOILER_EFF / KWH_PER_THERM * GAS_USD_PER_THERM
                 + cool_kwh / CHILLER_COP * ELEC_USD_PER_KWH)
    gshp_opex = (heat_kwh / GSHP_COP_HEAT * ELEC_USD_PER_KWH
                 + cool_kwh / GSHP_COP_COOL * ELEC_USD_PER_KWH)

    annual_savings = conv_opex - gshp_opex
    extra_capex = gshp_capex - conv_mid
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
        "conv_capex_low_usd": conv_low,
        "conv_capex_usd": conv_mid,
        "conv_capex_high_usd": conv_high,
        "conv_opex_usd_yr": conv_opex,
        "gshp_opex_usd_yr": gshp_opex,
        "annual_savings_usd_yr": annual_savings,
        "simple_payback_yr": payback,
        "note": ("Rough industry placeholders pending calibration; GSHP "
                 "operating cost excludes peaker energy (additional)."),
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


def build_report(data: dict) -> dict:
    """Assemble the fixed-structure report from the /api/report request body."""
    design = data.get("design") or {}
    site = data.get("site") or {}
    loads = data.get("loads") or {}
    heat_kwh = float(data.get("annual_heat_kwh_th") or 0.0)
    cool_kwh = float(data.get("annual_cool_kwh_th") or 0.0)

    peak_kw = _peak_kw(loads) if loads.get("q_h") is not None else 0.0

    design_section = _design_section(design, site)
    performance = _performance_section(data.get("strategy"))
    cost_savings = _cost_savings_section(data.get("cost"), peak_kw,
                                         heat_kwh, cool_kwh)

    return {
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

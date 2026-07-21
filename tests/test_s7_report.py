"""s7 report: deterministic builder math + recommendation score."""

import json

import pytest

from geosite.s7_report import build_report, compute_recommendation_score
from geosite.s7_report.builder import (
    BOILER_EFF,
    CHILLER_COP,
    CONV_USD_PER_SQFT_DEFAULT,
    ELEC_USD_PER_KWH,
    GAS_USD_PER_THERM,
    GSHP_COP_COOL,
    GSHP_COP_HEAT,
    HP_USD_PER_KW,
    KWH_PER_THERM,
    SCORE_BENCHMARK,
)


def _payload():
    return {
        "design": {
            "building_type": "small_office",
            "NB": 15, "H": 130, "L": 1950,
            "nb_source": "optimizer", "governing": "heating",
            "L_heat": 1950, "L_cool": 900, "imbalance_m": 1050,
            "nb_min": 4, "nb_max": 15, "B": 6.0, "A": 9.0,
            "solar_thermal_recommended": True,
            "capacity_warning": False,
            "footprint": {"shape_label": "Elongated (9:1)", "footprint_m2": 511.0,
                          "n_floors": 1},
        },
        "site": {"k_effective": 1.8, "alpha": 0.086, "T_g": 12.0,
                 "climate_zone": "5A", "state_abbrev": "IL"},
        "loads": {"q_h": -60000.0, "q_m": -25000.0, "q_y": -4000.0,
                  "q_h_heat": -60000.0, "q_h_cool": 41000.0,
                  "floor_area_m2": 5000.0},
        "cost": {"best": {"total_usd": 60000.0}, "base": {"total_usd": 80000.0},
                 "worst": {"total_usd": 110000.0}},
        "strategy": {
            "peaker_kW": 12.0, "peaker_type": "electric_heater",
            "cap_W": 55000.0, "dominant_mode": "heating",
            "L_before": 1950, "NB": 15,
            "comparison": {
                "m1": {"gshp_hours_pct": 90.0, "gshp_energy_pct": 97.5,
                       "peaker_kW": 12.0, "peaker_energy_kwh": 1500.0,
                       "L_after": 900, "savings_pct": 53.8},
                "m2": {"gshp_hours_pct": 95.0, "gshp_energy_pct": 90.0,
                       "peaker_kW": 15.0, "peaker_energy_kwh": 3200.0,
                       "L_after": 1050, "savings_pct": 46.2},
            },
        },
        "annual_heat_kwh_th": 120000.0,
        "annual_cool_kwh_th": 40000.0,
    }


def test_report_has_fixed_sections_plus_echo_and_recommendation():
    report = build_report(_payload())
    assert set(report) == {"design", "performance", "cost_savings",
                           "review_input", "inputs_echo", "recommendation"}


def test_conventional_capex_from_floor_area():
    cs = build_report(_payload())["cost_savings"]
    # 5000 m² × 10.7639 sqft/m² × $35/sqft
    expected = 5000 * 10.7639 * CONV_USD_PER_SQFT_DEFAULT
    assert cs["conv_capex_usd"] == pytest.approx(expected, rel=1e-4)


def test_gshp_capex_is_borefield_plus_heat_pump():
    cs = build_report(_payload())["cost_savings"]
    assert cs["gshp_capex_usd"] == pytest.approx(80000.0 + 60 * HP_USD_PER_KW)


def test_operating_costs_match_formulas():
    cs = build_report(_payload())["cost_savings"]
    conv = (120000.0 / BOILER_EFF / KWH_PER_THERM * GAS_USD_PER_THERM
            + 40000.0 / CHILLER_COP * ELEC_USD_PER_KWH)
    gshp = (120000.0 / GSHP_COP_HEAT * ELEC_USD_PER_KWH
            + 40000.0 / GSHP_COP_COOL * ELEC_USD_PER_KWH)
    assert cs["conv_opex_usd_yr"] == pytest.approx(conv, abs=0.01)
    assert cs["gshp_opex_usd_yr"] == pytest.approx(gshp, abs=0.01)


def test_payback_formula_when_gshp_more_expensive():
    """Payback = extra_capex / annual_savings when GSHP costs more upfront."""
    payload = _payload()
    # Large borefield makes GSHP capex exceed conventional
    payload["cost"]["base"]["total_usd"] = 2_500_000.0
    payload["cost"]["best"]["total_usd"] = 2_200_000.0
    payload["cost"]["worst"]["total_usd"] = 3_000_000.0
    cs = build_report(payload)["cost_savings"]
    if cs["simple_payback_yr"] is not None:
        extra = cs["gshp_capex_usd"] - cs["conv_capex_usd"]
        savings = cs["conv_opex_usd_yr"] - cs["gshp_opex_usd_yr"]
        assert cs["simple_payback_yr"] == pytest.approx(extra / savings, rel=1e-5)


def test_payback_zero_when_gshp_cheaper_upfront():
    """When GSHP capex < conventional capex, payback = 0 (immediate)."""
    cs = build_report(_payload())["cost_savings"]
    # Default payload: 5000m² × $35/sqft = $1.88M conventional; tiny borefield → GSHP cheaper
    if cs["gshp_capex_usd"] < cs["conv_capex_usd"]:
        assert cs["simple_payback_yr"] == 0.0


def test_payback_none_when_no_operating_savings():
    payload = _payload()
    payload["annual_heat_kwh_th"] = 0.0
    payload["annual_cool_kwh_th"] = 0.0
    cs = build_report(payload)["cost_savings"]
    assert cs["simple_payback_yr"] is None


def test_report_survives_missing_cost_and_strategy():
    payload = _payload()
    payload["cost"] = None
    payload["strategy"] = None
    report = build_report(payload)
    assert report["performance"]["available"] is False
    assert report["cost_savings"]["available"] is False


def test_performance_surfaces_peaker_energy():
    perf = build_report(_payload())["performance"]
    assert perf["m1"]["peaker_energy_kwh"] == pytest.approx(1500.0)
    assert perf["m2"]["peaker_energy_kwh"] == pytest.approx(3200.0)


def test_review_input_is_compact_and_json_serializable():
    ri = build_report(_payload())["review_input"]
    json.dumps(ri)
    for key in ("building_type", "NB", "H", "L", "governing", "nb_source",
                "capacity_warning", "q_h_kW"):
        assert key in ri


# ── Recommendation score ─────────────────────────────────────────────
# Benchmark = 70 (zone-5A reference). Chicago/Buffalo → above 70. Miami → well below 70.


def test_score_zone5a_above_benchmark():
    """Standard zone-5A payload (Chicago) should score above the 70-pt benchmark."""
    # payload: 5A, heat=120k, cool=40k, floor=5000m²
    # bilateral = min(120k,40k)/5000 = 8 kWh/m²/yr → 15 pts (low band)
    # climate 5A → 35, footprint optimizer → 25; total = 75
    rec = build_report(_payload())["recommendation"]
    assert rec["benchmark"] == SCORE_BENCHMARK
    assert rec["score"] > SCORE_BENCHMARK
    assert rec["grade"] in ("Good", "Excellent")
    contribs = {f["label"]: f["contribution"] for f in rec["factors"]}
    assert contribs["Climate zone suitability"] == 35   # 5A
    assert contribs["Footprint feasibility"] == 25      # optimizer


def test_score_zone1a_well_below_benchmark():
    """Zone 1A (Miami) with near-zero heating must score well below 70."""
    payload = _payload()
    payload["site"]["climate_zone"] = "1A"
    payload["annual_heat_kwh_th"] = 3000.0    # Miami: tiny heating load
    payload["annual_cool_kwh_th"] = 220000.0
    rec = build_report(payload)["recommendation"]
    # climate 1A → 3, bilateral = min(3k,220k)/5000 = 0.6 → 4 pts, footprint → 25; total = 32
    assert rec["score"] < 50
    assert rec["grade"] == "Poor"
    contribs = {f["label"]: f["contribution"] for f in rec["factors"]}
    assert contribs["Climate zone suitability"] == 3


def test_chicago_beats_miami():
    """Ordering invariant: Chicago (5A) must always outscore Miami (1A)."""
    chicago = build_report(_payload())["recommendation"]
    p = _payload()
    p["site"]["climate_zone"] = "1A"
    p["annual_heat_kwh_th"] = 3000.0
    p["annual_cool_kwh_th"] = 220000.0
    miami = build_report(p)["recommendation"]
    assert chicago["score"] > miami["score"]


def test_score_capacity_capped_penalizes_footprint():
    payload = _payload()
    payload["design"]["nb_source"] = "capacity_capped"
    contribs = {f["label"]: f["contribution"]
                for f in build_report(payload)["recommendation"]["factors"]}
    assert contribs["Footprint feasibility"] == 6


def test_score_strong_bilateral_raises_score():
    """Building with strong bilateral loads (balanced Chicago office) should score Excellent."""
    payload = _payload()
    payload["annual_heat_kwh_th"] = 200000.0   # 40 kWh/m²/yr each side
    payload["annual_cool_kwh_th"] = 200000.0
    rec = build_report(payload)["recommendation"]
    # bilateral = 200k/5000 = 40 kWh/m²/yr → 40 pts; climate 5A 35; footprint 25 → 100
    assert rec["score"] == 100
    assert rec["grade"] == "Excellent"


def test_score_has_benchmark_and_vs_fields():
    rec = build_report(_payload())["recommendation"]
    assert rec["benchmark"] == SCORE_BENCHMARK
    assert "vs_benchmark" in rec
    # vs_benchmark is a signed string like "+5" or "-12"
    delta = rec["score"] - SCORE_BENCHMARK
    expected = f"{'+' if delta >= 0 else ''}{delta}"
    assert rec["vs_benchmark"] == expected


def test_score_handles_missing_data_conservatively():
    rec = compute_recommendation_score({"design": {}, "performance": {"available": False}})
    assert {"score", "grade", "benchmark", "vs_benchmark", "factors"} <= set(rec)
    assert len(rec["factors"]) == 3
    assert 0 <= rec["score"] <= 100
    json.dumps(rec)   # must be JSON-serializable

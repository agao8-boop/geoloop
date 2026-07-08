"""s7 report: deterministic builder math + Claude review call (mocked)."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

import anthropic
from geosite.s7_report import build_report, generate_review
from geosite.s7_report.builder import (
    BOILER_EFF,
    CHILLER_COP,
    CONV_USD_PER_KW,
    ELEC_USD_PER_KWH,
    GAS_USD_PER_THERM,
    GSHP_COP_COOL,
    GSHP_COP_HEAT,
    HP_USD_PER_KW,
    KWH_PER_THERM,
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
            "footprint": {"length_m": 27.7, "width_m": 18.5, "n_floors": 1},
        },
        "site": {"k_effective": 1.8, "alpha": 0.086, "T_g": 12.0,
                 "climate_zone": "5A", "state_abbrev": "IL"},
        "loads": {"q_h": -60000.0, "q_m": -25000.0, "q_y": -4000.0,
                  "q_h_heat": -60000.0, "q_h_cool": 41000.0,
                  "floor_area_m2": None},
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


def test_report_has_exactly_four_sections_plus_echo():
    report = build_report(_payload())
    assert set(report) == {"design", "performance", "cost_savings",
                           "review_input", "inputs_echo"}


def test_conventional_capex_from_peak_load():
    cs = build_report(_payload())["cost_savings"]
    # governing peak 60 kW x (340, 500, 710) $/kW
    assert cs["conv_capex_low_usd"] == pytest.approx(60 * CONV_USD_PER_KW[0])
    assert cs["conv_capex_usd"] == pytest.approx(60 * CONV_USD_PER_KW[1])
    assert cs["conv_capex_high_usd"] == pytest.approx(60 * CONV_USD_PER_KW[2])
    assert cs["conv_capex_usd"] == pytest.approx(30000.0)


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


def test_payback_is_delta_capex_over_delta_opex():
    cs = build_report(_payload())["cost_savings"]
    d_capex = cs["gshp_capex_usd"] - cs["conv_capex_usd"]
    d_opex = cs["conv_opex_usd_yr"] - cs["gshp_opex_usd_yr"]
    assert cs["simple_payback_yr"] == pytest.approx(d_capex / d_opex, rel=1e-6)


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


_VALID_REVIEW = {
    "verdict": "Feasible with caveats.",
    "strengths": ["a", "b"],
    "concerns": ["c", "d"],
    "risks": ["pre-feasibility estimate; TRT required"],
    "next_steps": ["engage a licensed engineer"],
}


@patch("geosite.s7_report.ai.anthropic.Anthropic")
def test_generate_review_parses_structured_output(mock_cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = mock_cls.return_value
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=json.dumps(_VALID_REVIEW))])
    review, err = generate_review(build_report(_payload()))
    assert err is None
    assert review == _VALID_REVIEW
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] == 1500


@patch("geosite.s7_report.ai.anthropic.Anthropic")
def test_generate_review_degrades_on_connection_error(mock_cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = mock_cls.return_value
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com"))
    review, err = generate_review(build_report(_payload()))
    assert review is None
    assert isinstance(err, str) and err


@patch("geosite.s7_report.ai.anthropic.Anthropic")
def test_generate_review_short_circuits_without_key(mock_cls, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    review, err = generate_review(build_report(_payload()))
    assert review is None
    assert "not configured" in err
    mock_cls.assert_not_called()


@patch("geosite.s7_report.ai.anthropic.Anthropic")
def test_generate_review_degrades_on_unparseable_output(mock_cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = mock_cls.return_value
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text="not json at all")])
    review, err = generate_review(build_report(_payload()))
    assert review is None
    assert isinstance(err, str) and err

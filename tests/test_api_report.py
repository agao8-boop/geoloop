"""API tests: POST /api/report — contract + AI degradation paths."""

import json
from unittest.mock import patch

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


_BODY = {
    "design": {"building_type": "small_office", "NB": 15, "H": 130, "L": 1950,
               "nb_source": "optimizer", "governing": "heating",
               "capacity_warning": False},
    "site": {"k_effective": 1.8, "alpha": 0.086, "T_g": 12.0,
             "climate_zone": "5A"},
    "loads": {"q_h": -60000.0, "q_m": -25000.0, "q_y": -4000.0},
    "cost": {"best": {"total_usd": 60000.0}, "base": {"total_usd": 80000.0},
             "worst": {"total_usd": 110000.0}},
    "strategy": {"peaker_kW": 12.0, "peaker_type": "electric_heater",
                 "comparison": {"m1": {}, "m2": {}}},
    "annual_heat_kwh_th": 120000.0,
    "annual_cool_kwh_th": 40000.0,
}

_REVIEW = {"verdict": "ok", "strengths": ["a", "b"], "concerns": ["c", "d"],
           "risks": ["pre-feasibility"], "next_steps": ["hire an engineer"]}


def _post(client, body):
    return client.post("/api/report", data=json.dumps(body),
                       content_type="application/json")


@patch("app.generate_review", return_value=(_REVIEW, None))
def test_report_returns_report_and_review(mock_gen, client):
    resp = _post(client, _BODY)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert set(data) == {"report", "ai_review", "ai_error"}
    assert data["ai_review"] == _REVIEW
    assert data["ai_error"] is None
    assert data["report"]["design"]["NB"] == 15
    assert data["report"]["cost_savings"]["available"] is True


@patch("app.generate_review", return_value=(None, "timeout"))
def test_report_degrades_when_ai_fails(mock_gen, client):
    resp = _post(client, _BODY)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ai_review"] is None
    assert data["ai_error"] == "timeout"
    assert data["report"]["design"]["NB"] == 15


@patch("app.generate_review", side_effect=RuntimeError("boom"))
def test_report_never_500s_on_ai_exception(mock_gen, client):
    resp = _post(client, _BODY)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ai_review"] is None
    assert isinstance(data["ai_error"], str)


@patch("app.generate_review", return_value=(_REVIEW, None))
def test_report_allows_null_cost_and_strategy(mock_gen, client):
    body = dict(_BODY, cost=None, strategy=None)
    resp = _post(client, body)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["report"]["cost_savings"]["available"] is False
    assert data["report"]["performance"]["available"] is False


def test_report_rejects_missing_design(client):
    body = {k: v for k, v in _BODY.items() if k != "design"}
    resp = _post(client, body)
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "design"


def test_report_rejects_non_dict_design(client):
    resp = _post(client, dict(_BODY, design="nope"))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "design"


def test_report_rejects_non_numeric_annual_kwh(client):
    resp = _post(client, dict(_BODY, annual_heat_kwh_th="abc"))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "annual_heat_kwh_th"

"""Endpoint wiring for building-design parameters."""

import json
from unittest.mock import patch, MagicMock
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_geocode_mocks(geoid: str) -> list[MagicMock]:
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None
    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    tract_resp.raise_for_status.return_value = None
    return [zip_resp, tract_resp]


_SMART = {"zip_code": "60601", "building_type": "small_office",
          "NB": 16, "B": 6.0, "A": 9.0}

_MANUAL = {
    "q_h": 12000, "q_m": 6000, "q_y": 1500,
    "k": 2.0, "alpha": 0.086, "T_g": 15.0,
    "Cp": 4200, "mfls": 0.05, "T_in_HP": 40.2,
    "rbore": 0.06, "rpin": 0.01365, "rpext": 0.0167,
    "kgrout": 1.5, "kpipe": 0.42, "LU": 0.0511, "hconv": 1000,
    "B": 6.1, "NB": 5, "A": 1.0,
}

_STRATEGY = {"building_type": "small_office", "climate_zone": "5A",
             "k": 2.0, "alpha": 0.1, "T_g": 12.0, "NB": 16, "B": 6.0,
             "A": 9.0, "state": "IL"}


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_accepts_design_fields_and_echoes_factor(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    body = dict(_SMART, wwr="high", envelope="low", glazing="single")
    resp = client.post("/calculate/smart", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    loads = resp.get_json()["loads"]
    assert loads["wwr"] == "high"
    assert loads["envelope"] == "low"
    assert loads["glazing"] == "single"
    # New API: returns separate heat_factor and cool_factor (climate-specific lookup)
    assert "heat_factor" in loads
    assert "cool_factor" in loads
    assert loads["heat_factor"] > 1.0   # high-WWR + leaky + single-pane increases loads
    assert loads["cool_factor"] > 1.0


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_low_factors_reduce_borefield(mock_get, client):
    """Efficient envelope (low/high/triple) must produce a smaller borefield than default."""
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    r_default = client.post("/calculate/smart", data=json.dumps(_SMART),
                            content_type="application/json").get_json()
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    body = dict(_SMART, wwr="low", envelope="high", glazing="triple")
    r_efficient = client.post("/calculate/smart", data=json.dumps(body),
                              content_type="application/json").get_json()
    # efficient envelope (low WWR + tight + triple) should shrink borefield
    assert r_efficient["loads"]["heat_factor"] < 1.0
    assert r_efficient["L"] < r_default["L"]


def test_smart_rejects_unknown_wwr(client):
    body = dict(_SMART, wwr="enormous")
    resp = client.post("/calculate/smart", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "wwr"


def test_manual_accepts_design_fields(client):
    base = client.post("/calculate", data=json.dumps(_MANUAL),
                       content_type="application/json").get_json()
    body = dict(_MANUAL, wwr="high", envelope="low", glazing="single")
    resp = client.post("/calculate", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    # high × low × single increases loads → borefield grows
    assert data["envelope_factor"] > 1.0
    assert data["L"] > base["L"]


def test_manual_rejects_unknown_glazing(client):
    body = dict(_MANUAL, glazing="quintuple")
    resp = client.post("/calculate", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "glazing"


def test_strategy_accepts_envelope_factor(client):
    body = dict(_STRATEGY, envelope_factor=1.0)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()


def test_strategy_rejects_nonpositive_envelope_factor(client):
    body = dict(_STRATEGY, envelope_factor=0)
    resp = client.post("/api/strategy", data=json.dumps(body),
                       content_type="application/json")
    assert resp.status_code == 400

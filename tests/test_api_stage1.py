"""API tests: /calculate/stage1 — site + loads + NB range, no sizing."""

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


_BASE = {"zip_code": "60601", "building_type": "small_office"}


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_returns_site_loads_and_nb_estimate(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1", data=json.dumps(_BASE),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert set(data) == {"site", "loads", "nb_estimate"}
    assert data["site"]["k_effective"] > 0
    for key in ("q_h", "q_m", "q_y", "q_h_heat", "q_m_heat", "q_h_cool", "q_m_cool"):
        assert key in data["loads"]
    est = data["nb_estimate"]
    assert est["nb_min"] == 4 and est["nb_max"] == 15   # small_office proto, B=6.0
    assert est["spacing_m"] == 6.0
    assert est["footprint"]["n_floors"] == 1
    assert isinstance(est["nb_load_min"], int) and est["nb_load_min"] >= 1
    assert isinstance(est["nb_load_max"], int) and est["nb_load_max"] >= est["nb_load_min"]
    assert isinstance(est["capacity_warning"], bool)


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_never_returns_sizing_keys(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1", data=json.dumps(_BASE),
                       content_type="application/json")
    data = resp.get_json()
    for forbidden in ("L", "H", "NB"):
        assert forbidden not in data


@patch("geosite.s1_site.geocode.requests.get")
def test_stage1_floor_area_scales_range(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/stage1",
                       data=json.dumps(dict(_BASE, floor_area_m2=1022.0)),
                       content_type="application/json")
    est = resp.get_json()["nb_estimate"]
    assert (est["nb_min"], est["nb_max"]) == (5, 21)


def test_stage1_requires_zip_and_building_type(client):
    for missing in ("zip_code", "building_type"):
        body = dict(_BASE)
        del body[missing]
        resp = client.post("/calculate/stage1", data=json.dumps(body),
                           content_type="application/json")
        assert resp.status_code == 400
        assert resp.get_json()["field"] == missing

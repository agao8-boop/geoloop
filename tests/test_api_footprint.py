"""API tests: footprint-driven NB on /calculate/smart."""

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


_BASE = {"zip_code": "60601", "building_type": "small_office", "B": 6.0, "A": 9.0}


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_without_nb_uses_footprint(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart", data=json.dumps(_BASE),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["nb_min"] == 2      # small_office prototype, spacing 6 m
    assert data["nb_max"] == 25
    assert data["H_min"] == 125.0
    assert data["NB"] >= 1
    assert data["footprint"]["n_floors"] == 1
    assert data["H"] == pytest.approx(data["L"] / data["NB"], abs=1.0)


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_with_nb_stays_legacy(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart", data=json.dumps(dict(_BASE, NB=16)),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["NB"] == 16
    assert data["nb_min"] is None
    assert data["nb_max"] is None
    assert data["H_min"] is None
    assert data["H"] == round(data["L"] / 16)


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_floor_area_changes_range(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, floor_area_m2=1022.0)),
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert (data["nb_min"], data["nb_max"]) == (2, 35)


def test_smart_rejects_out_of_range_h_min(client):
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, H_min=1000)),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "H_min"


def test_smart_rejects_non_integer_nb(client):
    resp = client.post("/calculate/smart",
                       data=json.dumps(dict(_BASE, NB="abc")),
                       content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "NB"

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
    """Return [zip_resp, tract_resp] for the two-step geocode.

    Step 1: zippopotam.us → {"places": [{"latitude": ..., "longitude": ...}]}
    Step 2: Census geocoder → {"result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}}
    """
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None

    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    tract_resp.raise_for_status.return_value = None

    return [zip_resp, tract_resp]


@patch("geosite.s1_site.geocode.requests.get")
def test_full_pipeline_chicago_small_office(mock_get, client):
    mock_get.side_effect = _make_geocode_mocks("17031320101")

    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601",
            "building_type": "small_office",
            "mode": "heating",
            "NB": 16,
            "B": 6.0,
            "A": 1.0,
        }),
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()

    assert "L" in data
    assert "H" in data
    assert data["NB"] == 16
    assert data["L"] > 0
    # k from deep_thermal_by_county.csv for Cook County, IL (FIPS 17031):
    # SMU IDW from 10 nearby quality A+B measurements — Blackwell & Richards (2004)
    assert data["site"]["k"] == pytest.approx(3.997, rel=0.01)
    assert data["site"]["climate_zone"] == "5A"
    # Small office in 5A (Buffalo) is cooling-dominant — internal gains dominate
    assert data["loads"]["q_h"] == pytest.approx(17625.0)
    assert data["loads"]["mode"] == "cooling"


@patch("geosite.s1_site.geocode.requests.get")
def test_no_soil_data_returns_error(mock_get, client):
    # GEOID with county FIPS 99999 — not in any CSV
    mock_get.side_effect = _make_geocode_mocks("99999999999")

    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "99999",
            "building_type": "small_office",
            "mode": "heating",
            "NB": 16,
            "B": 6.0,
            "A": 1.0,
        }),
        content_type="application/json",
    )

    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "no_site_data"


def test_missing_required_field_returns_400(client):
    resp = client.post(
        "/calculate/smart",
        data=json.dumps({"zip_code": "60601"}),  # missing building_type, NB, B, A
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "field"


def test_non_json_body_returns_400(client):
    resp = client.post("/calculate/smart", data="not json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "field"


@patch("geosite.s1_site.geocode.requests.get")
def test_pipeline_auto_detects_cooling_mode_for_5a(mock_get, client):
    # Chicago 5A → small_office is cooling-dominant (internal gains dominate)
    # Pipeline ignores any caller-supplied mode and auto-detects from load sign.
    mock_get.side_effect = _make_geocode_mocks("17031320101")

    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601",
            "building_type": "small_office",
            "NB": 16, "B": 6.0, "A": 1.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["loads"]["mode"] == "cooling"
    assert body["loads"]["q_h"] > 0


@patch("geosite.s1_site.geocode.requests.get")
def test_census_api_network_error_returns_422(mock_get, client):
    import requests as req_lib
    mock_get.side_effect = req_lib.exceptions.ConnectionError("DNS failure")

    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601",
            "building_type": "small_office",
            "mode": "heating",
            "NB": 16, "B": 6.0, "A": 1.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error"] == "geocode"
    assert "unavailable" in body["message"].lower()

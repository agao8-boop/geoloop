import json
from unittest.mock import patch
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# Mock geocode so we don't hit the Census API in tests
@patch("geosite.s1_site.geocode.requests.get")
def test_full_pipeline_chicago_small_office(mock_get, client):
    # Make geocoder return Chicago census tract from Task 1 fixture
    mock_get.return_value.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": "17031010200"}]}}
    }
    mock_get.return_value.raise_for_status.return_value = None

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

    assert resp.status_code == 200
    data = resp.get_json()

    assert "L" in data
    assert "H" in data
    assert data["NB"] == 16
    assert data["L"] > 0
    assert data["site"]["k"] == pytest.approx(1.50)
    assert data["site"]["climate_zone"] == "5A"
    assert data["loads"]["q_h"] == pytest.approx(-78500.0)


@patch("geosite.s1_site.geocode.requests.get")
def test_no_soil_data_returns_error(mock_get, client):
    # Return a GEOID that is not in the fixture CSV
    mock_get.return_value.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": "99999999999"}]}}
    }
    mock_get.return_value.raise_for_status.return_value = None

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

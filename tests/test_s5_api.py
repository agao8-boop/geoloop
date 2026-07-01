import json
from unittest.mock import patch, MagicMock
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_cost_endpoint_returns_three_scenarios(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "IL"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "best" in data
    assert "base" in data
    assert "worst" in data
    assert "headline_per_ft" in data
    assert "region_used" in data


def test_cost_endpoint_breakdown_has_nine_items(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "IL"}),
        content_type="application/json",
    )
    data = resp.get_json()
    assert len(data["base"]["breakdown"]) == 9


def test_cost_endpoint_missing_required_field_returns_400(client):
    resp = client.post(
        "/api/cost",
        data=json.dumps({"NB": 32, "B": 6.7}),  # missing L and state
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_cost_endpoint_with_rock_class(client):
    resp_rock = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "CO",
                         "rock_class": "Igneous"}),
        content_type="application/json",
    )
    resp_soft = client.post(
        "/api/cost",
        data=json.dumps({"L": 2206.33, "NB": 32, "B": 6.7, "state": "CO"}),
        content_type="application/json",
    )
    assert resp_rock.status_code == 200
    assert resp_soft.status_code == 200
    # Igneous = more rock drilling = more expensive base scenario
    assert resp_rock.get_json()["base"]["total_usd"] > resp_soft.get_json()["base"]["total_usd"]


def test_cost_map_endpoint_returns_all_states(client):
    resp = client.get("/api/cost/map")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "states" in data
    # Should have at least the 9 Census divisions as representative entries
    assert len(data["states"]) >= 9


@patch("geosite.s1_site.geocode.requests.get")
def test_smart_run_includes_soil_class_fields(mock_get, client):
    """POST /calculate/smart returns rock_class, k_min, k_max, shallow_soil_class, k_shallow in site dict."""
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None
    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": "17031320101"}]}}
    }
    tract_resp.raise_for_status.return_value = None
    mock_get.side_effect = [zip_resp, tract_resp]

    resp = client.post("/calculate/smart", json={
        "zip_code": "60601",
        "building_type": "medium_office",
        "NB": 10, "B": 6.0, "A": 10.0,
        "soil_confidence": "medium",
    })
    assert resp.status_code == 200
    site = resp.get_json()["site"]
    assert "rock_class" in site
    assert "k_min" in site
    assert "k_max" in site
    assert "shallow_soil_class" in site
    assert "k_shallow" in site

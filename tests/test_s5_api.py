import json
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

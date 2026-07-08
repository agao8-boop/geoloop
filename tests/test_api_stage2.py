"""API tests: /calculate/stage2 — NB optimization from echoed stage-1 numbers."""

import json
from unittest.mock import patch, MagicMock
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


_SITE  = {"k_effective": 1.8, "alpha": 0.086, "T_g": 12.0}
_LOADS = {"q_h": -60000.0, "q_m": -25000.0, "q_y": -4000.0,
          "q_h_heat": -60000.0, "q_m_heat": -25000.0,
          "q_h_cool": 41000.0,  "q_m_cool": 17000.0}
_BASE  = {"building_type": "small_office", "site": _SITE, "loads": _LOADS}


def _post(client, body):
    return client.post("/calculate/stage2", data=json.dumps(body),
                       content_type="application/json")


def test_stage2_computes_nb_from_footprint(client):
    resp = _post(client, _BASE)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["nb_source"] in ("optimizer", "depth_fallback")
    assert data["NB"] >= 1
    assert data["nb_min"] == 4 and data["nb_max"] == 15
    assert data["H"] == pytest.approx(data["L"] / data["NB"], abs=1.0)
    # Advisory load-density cross-check (|q_h| = 60 kW at H_min 125):
    # lo = ceil(60000/8750) = 7; hi = ceil(60000/1875) = 32; 7 <= 15 -> no warning
    assert data["nb_load_min"] == 7
    assert data["nb_load_max"] == 32
    assert data["capacity_warning"] is False


def test_stage2_spacing_changes_nb_range(client):
    resp = _post(client, dict(_BASE, B=3.0))
    data = resp.get_json()
    assert data["nb_max"] > 15          # tighter spacing fits more boreholes


def test_stage2_expert_override_fixes_nb(client):
    resp = _post(client, dict(_BASE, NB=16))
    data = resp.get_json()
    assert data["NB"] == 16
    assert data["nb_source"] == "expert_override"
    assert data["nb_min"] is None and data["nb_max"] is None
    assert data["nb_load_min"] is None and data["nb_load_max"] is None
    assert data["capacity_warning"] is None


def test_stage2_single_pass_when_mode_split_null(client):
    loads = dict(_LOADS, q_h_heat=None, q_m_heat=None, q_h_cool=None, q_m_cool=None)
    resp = _post(client, dict(_BASE, loads=loads))
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["L_heat"] is None and data["L_cool"] is None
    assert data["governing"] == "heating"   # q_h < 0


def test_stage2_rejects_missing_stage1_echo(client):
    for missing in ("site", "loads"):
        body = {k: v for k, v in _BASE.items() if k != missing}
        resp = _post(client, body)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == missing


def test_stage2_rejects_out_of_range_rbore(client):
    resp = _post(client, dict(_BASE, rbore=0.2))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["field"] == "rbore"
    assert "0.05" in body["message"] and "0.1" in body["message"]


def test_stage2_rejects_nonpositive_kgrout(client):
    resp = _post(client, dict(_BASE, kgrout=0))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "kgrout"


def test_stage2_rejects_non_numeric_t_in_hp_heat(client):
    resp = _post(client, dict(_BASE, T_in_HP_heat="abc"))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "T_in_HP_heat"


def test_stage2_rejects_inconsistent_pipe_radii(client):
    resp = _post(client, dict(_BASE, rpin=0.02, rpext=0.0167))
    assert resp.status_code == 400


def test_stage2_rejects_out_of_range_h_min(client):
    resp = _post(client, dict(_BASE, H_min=1000))
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "H_min"


def _make_geocode_mocks(geoid):
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
def test_stage_chain_matches_smart_endpoint(mock_get, client):
    """stage1 → stage2 must reproduce /calculate/smart exactly."""
    smart_body = {"zip_code": "60601", "building_type": "small_office",
                  "B": 6.0, "A": 9.0, "H_min": 125.0}

    mock_get.side_effect = _make_geocode_mocks("17031320101")
    smart = client.post("/calculate/smart", data=json.dumps(smart_body),
                        content_type="application/json").get_json()

    mock_get.side_effect = _make_geocode_mocks("17031320101")
    s1 = client.post("/calculate/stage1",
                     data=json.dumps({"zip_code": "60601",
                                      "building_type": "small_office"}),
                     content_type="application/json").get_json()
    s2 = _post(client, {"building_type": "small_office",
                        "site": s1["site"], "loads": s1["loads"],
                        "B": 6.0, "A": 9.0, "H_min": 125.0}).get_json()

    for key in ("L", "H", "NB", "governing", "L_heat", "L_cool",
                "nb_min", "nb_max", "imbalance_m", "solar_thermal_recommended"):
        assert s2[key] == smart[key], f"{key}: chain={s2[key]} smart={smart[key]}"

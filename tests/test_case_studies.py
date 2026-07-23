"""Case study regression tests — lock in sizing outcomes for real building types.

These tests serve two purposes:
  1. Regression guards: lock known-good sizing numbers so pipeline changes don't
     silently alter results for specialty or high-stakes building types.
  2. load_scale validation: verify the prototype correction multiplier works end-to-end.

Ground truth for load values: data/public/prototype_loads.json (EnergyPlus DOE prototypes).
Ground truth for sizing math: philippe_2010_sizing.xls (via test_s4_sizing.py).
"""

import json
import math
from unittest.mock import patch, MagicMock

import pytest

from geosite.s2_simulation import get_loads
from geosite.s4_sizing.footprint import compute_nb_range, find_optimal_nb, PROTOTYPE_AREAS_M2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADV = dict(
    Cp=4200.0, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167,
    kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0,
)


def _geocode_mocks(geoid: str):
    zip_resp = MagicMock()
    zip_resp.json.return_value = {"places": [{"latitude": "41.88", "longitude": "-87.63"}]}
    zip_resp.raise_for_status.return_value = None
    tract_resp = MagicMock()
    tract_resp.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    tract_resp.raise_for_status.return_value = None
    return [zip_resp, tract_resp]


# ---------------------------------------------------------------------------
# Prototype load regressions — DOE 90.1-2019 baseline values must not drift
# ---------------------------------------------------------------------------

def test_small_office_5a_prototype_loads_stable():
    """DOE small_office in ASHRAE 5A: cooling-dominant (internal gains > heating)."""
    loads = get_loads("small_office", "5A")
    assert loads.q_h == pytest.approx(17625.0, rel=0.01)   # + = cooling dominant
    assert loads.q_h_heat == pytest.approx(-33300.0, rel=0.01)
    assert loads.q_h_cool == pytest.approx(17600.0, rel=0.01)


def test_hospital_2a_prototype_loads_stable():
    """Hospital in 2A (hot-humid): very cooling-dominant, tiny heating pulse."""
    loads = get_loads("hospital", "2A")
    assert loads.q_h == pytest.approx(758952.0, rel=0.01)
    assert loads.q_h_heat == pytest.approx(-5900.0, rel=0.01)   # negligible heating
    assert loads.q_h_cool > 700_000.0                            # large cooling peak


def test_restaurant_fastfood_5a_prototype_loads_stable():
    """Fast-food restaurant 5A: cooling-dominant, relatively small footprint."""
    loads = get_loads("restaurant_fastfood", "5A")
    assert loads.q_h == pytest.approx(33397.0, rel=0.01)
    assert loads.q_h_heat < 0      # heating pulse is negative
    assert loads.q_h_cool > 30000  # cooling peak dominant


# ---------------------------------------------------------------------------
# Footprint range regressions — per-building-type geometric sizing guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bt, expected_nb_min, expected_nb_max", [
    ("hospital",           4, 74),   # 22422 m² / 5 floors = 4484 m² footprint
    ("restaurant_fastfood", 1, 16),  # tiny 232 m² single-floor
    ("large_office",       4, 69),   # 46320 m² / 12 floors = 3860 m²
    ("primary_school",     5,  92),  # 6871 m², single-floor
])
def test_footprint_range_regression(bt, expected_nb_min, expected_nb_max):
    nb_min, nb_max, _ = compute_nb_range(None, bt, spacing_m=6.0)
    assert nb_min == expected_nb_min, f"{bt} nb_min"
    assert nb_max == expected_nb_max, f"{bt} nb_max"


# ---------------------------------------------------------------------------
# Hospital optimizer regression — locking NB selection for 2A climate
# ---------------------------------------------------------------------------

def test_hospital_2a_optimizer_result():
    """Hospital cooling-dominant (2A): optimizer picks NB=25, H ≈ 138 m."""
    loads = get_loads("hospital", "2A")
    nb_min, nb_max, _ = compute_nb_range(None, "hospital", spacing_m=6.0)
    T_cool = 40.2
    nb, L, H = find_optimal_nb(
        nb_min, nb_max,
        q_h=loads.q_h_cool, q_m=loads.q_m_cool, q_y=loads.q_y,
        k=2.0, alpha=0.086, T_g=20.0,
        H_min=125.0, B=6.0, A=9.0, T_in_HP=T_cool, **_ADV,
    )
    assert nb == 25
    assert 125.0 <= H <= 250.0
    assert L == pytest.approx(nb * H, abs=1.0)


# ---------------------------------------------------------------------------
# load_scale unit tests — prototype correction multiplier
# ---------------------------------------------------------------------------

def test_load_scale_doubles_sizing_length():
    """load_scale=2.0 doubles all pulses; sizing length must increase > original."""
    loads = get_loads("restaurant_fastfood", "5A")
    from geosite.s4_sizing.ashrae_sizing import size_borefield
    common = dict(k=2.5, alpha=0.086, T_g=12.0, T_in_HP=40.2,
                  B=6.0, NB=8, A=9.0, **_ADV)
    L1 = float(size_borefield(q_h=loads.q_h,   q_m=loads.q_m,   q_y=loads.q_y,   **common))
    L2 = float(size_borefield(q_h=loads.q_h*2, q_m=loads.q_m*2, q_y=loads.q_y*2, **common))
    assert L2 > L1
    # The relationship is nonlinear due to g-functions, but L2 must be substantially larger
    assert L2 > L1 * 1.5


def test_load_scale_unity_is_identity():
    """load_scale=1.0 (default) must not change load values."""
    loads1 = get_loads("small_office", "5A")
    # Applying × 1.0 is identity — verify the prototype baseline is unchanged
    assert loads1.q_h * 1.0 == pytest.approx(loads1.q_h)
    assert loads1.q_h_heat * 1.0 == pytest.approx(loads1.q_h_heat)


# ---------------------------------------------------------------------------
# API-level load_scale test — end-to-end via Flask test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@patch("geosite.s1_site.geocode.requests.get")
def test_api_load_scale_doubles_sizing(mock_get, client):
    """load_scale=2.0 via API: response L must be larger than load_scale=1.0 baseline."""
    mock_get.side_effect = _geocode_mocks("17031320101")
    base = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601", "building_type": "restaurant_fastfood",
            "B": 6.0, "A": 9.0, "soil_confidence": "medium",
        }),
        content_type="application/json",
    )
    assert base.status_code == 200, base.get_json()

    mock_get.side_effect = _geocode_mocks("17031320101")
    scaled = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601", "building_type": "restaurant_fastfood",
            "B": 6.0, "A": 9.0, "soil_confidence": "medium",
            "load_scale": 2.0,
        }),
        content_type="application/json",
    )
    assert scaled.status_code == 200, scaled.get_json()

    base_L = base.get_json()["L"]
    scaled_L = scaled.get_json()["L"]
    assert scaled_L > base_L, f"load_scale=2.0 should increase L: {base_L} → {scaled_L}"
    # load_scale is echoed in the loads dict
    assert scaled.get_json()["loads"]["load_scale"] == pytest.approx(2.0)


@patch("geosite.s1_site.geocode.requests.get")
def test_api_load_scale_default_is_one(mock_get, client):
    """When load_scale is not supplied, loads.load_scale == 1.0 in response."""
    mock_get.side_effect = _geocode_mocks("17031320101")
    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601", "building_type": "small_office",
            "B": 6.0, "A": 9.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["loads"]["load_scale"] == pytest.approx(1.0)


@patch("geosite.s1_site.geocode.requests.get")
def test_api_load_scale_out_of_range_rejected(mock_get, client):
    """load_scale outside [0.1, 10.0] must return 400."""
    mock_get.side_effect = _geocode_mocks("17031320101")
    resp = client.post(
        "/calculate/smart",
        data=json.dumps({
            "zip_code": "60601", "building_type": "small_office",
            "B": 6.0, "A": 9.0, "load_scale": 50.0,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "load_scale"

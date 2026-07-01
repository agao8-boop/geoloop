import json
import pathlib
import pytest
from app import app
from geosite.s6_strategy import run_strategy

_HOURLY_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads_hourly.json"

# Chicago small office ground params (from prior spreadsheet verification)
_CHICAGO_PARAMS = dict(
    building_type="small_office",
    climate_zone="5A",
    k=2.0, alpha=0.1, T_g=12.0,
    NB=16, B=6.0, A=1.0,
    state="IL",
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_run_strategy_returns_strategy_result():
    from geosite.s6_strategy.models import StrategyResult
    result = run_strategy(**_CHICAGO_PARAMS)
    assert isinstance(result, StrategyResult)


def test_small_office_5a_has_case_1_or_2():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.case in (1, 2)


def test_l_after_less_than_l_before():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.L_after < result.L_before, "Trimming must reduce borefield length"
    assert result.L_after > result.L_before * 0.05, "L_after must not be degenerate (>5% of L_before)"


def test_cost_after_per_ft_is_finite():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.cost_after["cost_per_ft"] < 1000, "cost_per_ft must be plausible (<$1000/ft)"


def test_peaker_kw_positive():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.peaker_kW > 0


def test_peaker_type_is_valid():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.peaker_type in ("electric_heater", "chiller", "electric_heater+chiller")


def test_hourly_profile_length():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert len(result.hourly_profile) == 8760
    assert len(result.hourly_trimmed) == 8760


def test_hourly_trimmed_max_le_cutoff():
    result = run_strategy(**_CHICAGO_PARAMS)
    cw = result.cutoff_W + 0.1
    if result.case == 1:
        # One-sided trim: only the dominant side is clipped; non-dominant passes through.
        if result.dominant_mode == "heating":
            # Heating hours (h < 0) must be clipped; cooling hours may exceed cutoff.
            assert all(h >= -cw for h in result.hourly_trimmed if h < 0)
        else:
            # Cooling hours (h > 0) must be clipped; heating hours may exceed cutoff.
            assert all(h <= cw for h in result.hourly_trimmed if h > 0)
    else:
        # Balanced trim: both sides clipped.
        assert max(abs(h) for h in result.hourly_trimmed) <= cw


def test_imbalance_ratio_gte_1():
    result = run_strategy(**_CHICAGO_PARAMS)
    assert result.imbalance_ratio >= 1.0


def test_floor_area_scaling_changes_result():
    result_default = run_strategy(**_CHICAGO_PARAMS)
    result_scaled = run_strategy(**_CHICAGO_PARAMS, floor_area_m2=1000.0)
    # Larger area → larger loads → larger borefield
    assert result_scaled.L_before != result_default.L_before


def test_api_strategy_endpoint_200(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({
            "building_type": "small_office",
            "climate_zone": "5A",
            "k": 2.0, "alpha": 0.1, "T_g": 12.0,
            "NB": 16, "B": 6.0, "A": 1.0,
            "state": "IL",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200


def test_api_strategy_response_has_required_keys(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({
            "building_type": "small_office",
            "climate_zone": "5A",
            "k": 2.0, "alpha": 0.1, "T_g": 12.0,
            "NB": 16, "B": 6.0, "A": 1.0,
            "state": "IL",
        }),
        content_type="application/json",
    )
    data = resp.get_json()
    for key in ("case", "L_before", "L_after", "peaker_kW", "peaker_type",
                "cost_before", "cost_after", "hourly_profile", "hourly_trimmed"):
        assert key in data, f"Missing key: {key}"


def test_api_strategy_missing_building_type_returns_400(client):
    resp = client.post(
        "/api/strategy",
        data=json.dumps({"climate_zone": "5A", "k": 2.0, "alpha": 0.1,
                         "T_g": 12.0, "NB": 16, "B": 6.0, "A": 1.0}),
        content_type="application/json",
    )
    assert resp.status_code == 400

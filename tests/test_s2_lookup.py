import pathlib
import pytest
from geosite.s2_simulation.lookup import lookup_prototype_loads
from geosite.models import LoadPulses

FIXTURE_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads.json"


def test_small_office_zone_5a_cooling_dominant():
    # Small office (511 m²) in Buffalo (5A) is cooling-dominant: internal gains
    # (people + equipment + lights) exceed the heating demand even in a cold climate.
    lp = lookup_prototype_loads("small_office", "5A", loads_json=FIXTURE_JSON)
    assert isinstance(lp, LoadPulses)
    assert lp.q_h > 0       # cooling dominant — positive
    assert lp.q_m > 0
    assert lp.q_y > 0
    assert lp.q_h == pytest.approx(17625.0)
    assert lp.q_m == pytest.approx(3873.0)
    assert lp.q_y == pytest.approx(522.0)


def test_small_office_zone_6a_heating_dominant():
    # Zone 6A (Rochester, MN) is cold enough that small office tips to heating-dominant.
    lp = lookup_prototype_loads("small_office", "6A", loads_json=FIXTURE_JSON)
    assert lp.q_h < 0       # heating dominant — negative


def test_small_office_zone_3b_cooling_dominant():
    lp = lookup_prototype_loads("small_office", "3B", loads_json=FIXTURE_JSON)
    assert lp.q_h > 0       # cooling dominant — positive
    assert lp.q_h == pytest.approx(25925.0)


def test_unknown_building_type_raises():
    with pytest.raises(KeyError, match="unknown_building"):
        lookup_prototype_loads("unknown_building", "5A", loads_json=FIXTURE_JSON)


def test_unknown_climate_zone_raises():
    with pytest.raises(KeyError, match="9Z"):
        lookup_prototype_loads("small_office", "9Z", loads_json=FIXTURE_JSON)


def test_get_loads_envelope_factor_default_is_identity():
    from geosite.s2_simulation import get_loads
    base = get_loads("small_office", "5A")
    same = get_loads("small_office", "5A", envelope_factor=1.0)
    assert same.q_h == base.q_h
    assert same.q_m == base.q_m
    assert same.q_y == base.q_y


def test_get_loads_envelope_factor_scales_linearly():
    from geosite.s2_simulation import get_loads
    base = get_loads("small_office", "5A")
    x2 = get_loads("small_office", "5A", envelope_factor=2.0)
    assert x2.q_h == pytest.approx(2.0 * base.q_h)
    assert x2.q_m == pytest.approx(2.0 * base.q_m)
    assert x2.q_y == pytest.approx(2.0 * base.q_y)


def test_get_loads_envelope_factor_nan_safe():
    from geosite.s2_simulation import get_loads
    loads = get_loads("small_office", "5A", envelope_factor=2.0)
    # cross-mode fields either scale or stay NaN — never crash
    for v in (loads.q_h_heat, loads.q_h_cool):
        assert (v != v) or isinstance(v, float)


def test_new_building_types_load():
    """All 4 newly-enabled building types must resolve for at least one zone."""
    from geosite.s2_simulation import get_loads
    for bt in ("retail_stripmall", "restaurant_fastfood", "restaurant_sitdown", "highrise_apartment"):
        loads = get_loads(bt, "5B")
        assert loads.q_h > 0, f"{bt}: q_h should be positive"
        assert loads.q_m > 0, f"{bt}: q_m should be positive"


def test_legacy_building_types_fall_back_to_hourly():
    """Legacy types (3 pre-computed zones) fall back to hourly profile for other zones."""
    from geosite.s2_simulation import get_loads
    for bt in ("hospital", "primary_school", "warehouse", "standalone_retail",
               "large_hotel", "small_hotel", "midrise_apartment"):
        loads = get_loads(bt, "5B")   # 5B (Denver) not in pre-computed table
        assert loads.q_h != 0.0, f"{bt}: q_h should be nonzero"
        assert len([v for v in (loads.q_h, loads.q_m, loads.q_y) if v == v]) == 3, \
            f"{bt}: all three pulses should be finite"

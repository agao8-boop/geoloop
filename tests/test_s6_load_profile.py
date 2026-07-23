import pathlib
import pytest
from geosite.s6_strategy.load_profile import load_hourly_profile, scale_profile

_HOURLY_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads_hourly.json"


def test_load_returns_8760_element_list():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert len(profile) == 8760


def test_load_profile_is_list_of_floats():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert isinstance(profile[0], float)


def test_load_small_office_5a_has_both_signs():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    assert any(h > 0 for h in profile), "no cooling hours"
    assert any(h < 0 for h in profile), "no heating hours"


def test_unknown_building_type_raises():
    with pytest.raises(KeyError):
        load_hourly_profile("unknown_type", "5A", _HOURLY_JSON)


def test_unknown_climate_zone_raises():
    with pytest.raises(KeyError):
        load_hourly_profile("small_office", "9Z", _HOURLY_JSON)


def test_scale_profile_multiplies_all_values():
    profile = [1.0, -2.0, 0.0, 3.0]
    scaled = scale_profile(profile, 2.0)
    assert scaled == pytest.approx([2.0, -4.0, 0.0, 6.0])


def test_scale_factor_one_returns_same_values():
    profile = load_hourly_profile("small_office", "5A", _HOURLY_JSON)
    scaled = scale_profile(profile, 1.0)
    assert scaled == pytest.approx(profile)


def test_all_16_building_types_return_8760_profile():
    """All 16 building types must return 8760h profiles (direct data or proxy fallback)."""
    from geosite.s4_sizing.footprint import BUILDING_FLOORS
    for bt in sorted(BUILDING_FLOORS):
        p = load_hourly_profile(bt, "5A", _HOURLY_JSON)
        assert len(p) == 8760, f"{bt}: expected 8760 hours"


def test_15_types_have_direct_hourly_profiles():
    """15/16 types have real EnergyPlus 8760h data; only midrise_apartment uses proxy."""
    import json, pathlib
    data = json.loads(pathlib.Path(_HOURLY_JSON).read_text())
    direct_types = [k for k in data if not k.startswith("_")]
    assert len(direct_types) == 15
    assert "midrise_apartment" not in direct_types  # still proxy
    # All others must be direct
    from geosite.s4_sizing.footprint import BUILDING_FLOORS
    for bt in sorted(BUILDING_FLOORS):
        if bt != "midrise_apartment":
            assert bt in direct_types, f"{bt} should have direct hourly data"


def test_midrise_apartment_uses_proxy_fallback():
    """midrise_apartment still proxies via medium_office until its EnergyPlus runs complete."""
    from geosite.s6_strategy.load_profile import _HOURLY_FALLBACK
    assert _HOURLY_FALLBACK == {"midrise_apartment": "medium_office"}
    p = load_hourly_profile("midrise_apartment", "5A", _HOURLY_JSON)
    assert len(p) == 8760

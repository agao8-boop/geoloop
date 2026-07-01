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

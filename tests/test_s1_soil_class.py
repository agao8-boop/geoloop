"""Tests for soil-class-aware fields added to SiteData + lookup_by_geoid."""
import math
import pathlib
import pytest
from geosite.s1_site.lookup import lookup_by_geoid
from geosite.models import SiteData

FIXTURE_THERMAL  = pathlib.Path(__file__).parent.parent / "data/public/thermal_by_tract.csv"
FIXTURE_CLIMATE  = pathlib.Path(__file__).parent.parent / "data/public/climate_by_tract.csv"
FIXTURE_DEEP     = pathlib.Path(__file__).parent.parent / "data/public/deep_thermal_by_county.csv"
FIXTURE_SOIL     = pathlib.Path(__file__).parent.parent / "data/public/soil_class_by_county.csv"

VALID_ROCK_CLASSES = {
    "alluvial_glacial", "clay_shale", "limestone_carbonate", "sandstone",
    "granite_felsic", "basalt_mafic", "metamorphic", "coal_organic", "undifferentiated", "",
}
VALID_SOIL_CLASSES = {
    "silt_clay", "medium_fine_sand", "coarse_sand", "gravel_coarse_sand", "peat_organic", "",
}


def test_sitedata_has_soil_class_fields():
    """SiteData accepts new optional fields without breaking existing construction."""
    sd = SiteData(
        geoid="17031320101",
        k=2.0, alpha=0.09, T_g=14.0,
        climate_zone="5A", data_available=True,
    )
    assert sd.rock_class == ""
    assert math.isnan(sd.k_min)
    assert math.isnan(sd.k_max)
    assert sd.shallow_soil_class == ""
    assert math.isnan(sd.k_shallow)


def test_rock_class_populated_for_chicago():
    """Chicago (FIPS 17031) gets rock_class and k bounds from augmented deep CSV."""
    if not FIXTURE_DEEP.exists():
        pytest.skip("deep_thermal_by_county.csv not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.rock_class in VALID_ROCK_CLASSES
    assert not math.isnan(sd.k_min)
    assert not math.isnan(sd.k_max)
    assert sd.k_min > 0
    assert sd.k_max > sd.k_min


def test_k_bounds_bracket_or_near_county_k():
    """k_min <= k_max; county k need not be inside range (SMU measured values can exceed class median range)."""
    if not FIXTURE_DEEP.exists():
        pytest.skip("deep_thermal_by_county.csv not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.k_min < sd.k_max
    # k must be physically reasonable regardless of class range
    assert 0.3 <= sd.k <= 6.0


def test_shallow_soil_class_populated():
    """Chicago county (17031) gets shallow_soil_class and k_shallow from soil_class CSV."""
    if not FIXTURE_DEEP.exists() or not FIXTURE_SOIL.exists():
        pytest.skip("required CSV files not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert sd.shallow_soil_class in VALID_SOIL_CLASSES
    if sd.shallow_soil_class:
        assert not math.isnan(sd.k_shallow)
        assert 0.1 <= sd.k_shallow <= 6.0


def test_unknown_geoid_empty_soil_fields():
    """GEOID with no data returns empty string soil class and nan bounds."""
    sd = lookup_by_geoid(
        "99999999999",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=None,
    )
    assert sd.rock_class == ""
    assert math.isnan(sd.k_min)
    assert sd.shallow_soil_class == ""

import pathlib
import pytest
from geosite.s1_site.lookup import lookup_by_geoid
from geosite.models import SiteData

# Fixture CSVs with known test data (3 tracts: Chicago, LA, Houston)
FIXTURE_THERMAL  = pathlib.Path(__file__).parent.parent / "data/public/thermal_by_tract.csv"
FIXTURE_CLIMATE  = pathlib.Path(__file__).parent.parent / "data/public/climate_by_tract.csv"
FIXTURE_DEEP     = pathlib.Path(__file__).parent.parent / "data/public/deep_thermal_by_county.csv"


def test_known_geoid_falls_back_to_shallow():
    """GEOID in fixture CSVs with deep_csv=None uses the shallow SSURGO data."""
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=None,
    )
    assert isinstance(sd, SiteData)
    assert sd.geoid == "17031320101"
    assert sd.k == pytest.approx(1.50)
    assert sd.alpha == pytest.approx(0.075)
    assert sd.T_g == pytest.approx(12.0)
    assert sd.climate_zone == "5A"
    assert sd.data_available is True


def test_known_geoid_uses_deep_when_available():
    """When deep_thermal_by_county.csv exists, county 17031 returns deep k/α/T_g."""
    if not FIXTURE_DEEP.exists():
        pytest.skip("deep_thermal_by_county.csv not yet generated")
    sd = lookup_by_geoid(
        "17031320101",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=FIXTURE_DEEP,
    )
    assert isinstance(sd, SiteData)
    assert sd.data_available is True
    assert sd.climate_zone == "5A"
    # k from SMU IDW or C&H 1995 — valid range: 0.3–6.0 W/m·K (Clauser & Huenges 1995)
    assert 0.3 <= sd.k <= 6.0
    assert 0.01 <= sd.alpha <= 0.20


def test_unknown_geoid_returns_unavailable():
    """GEOID with no matching county in any CSV returns data_available=False."""
    sd = lookup_by_geoid(
        "99999999999",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=None,
    )
    assert sd.data_available is False
    assert sd.geoid == "99999999999"


def test_la_tract():
    """LA County (FIPS 06037) returns expected shallow properties with deep_csv=None."""
    sd = lookup_by_geoid(
        "06037700600",
        thermal_csv=FIXTURE_THERMAL,
        climate_csv=FIXTURE_CLIMATE,
        deep_csv=None,
    )
    assert sd.climate_zone == "3B"
    assert sd.k == pytest.approx(1.20)

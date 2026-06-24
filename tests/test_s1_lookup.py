import pathlib
import pytest
from unittest.mock import patch
from geosite.s1_site.lookup import lookup_by_geoid
from geosite.models import SiteData

# Use the real fixture CSV from data/public/
FIXTURE_CSV = pathlib.Path(__file__).parent.parent / "data/public/thermal_by_tract.csv"
FIXTURE_CLIMATE = pathlib.Path(__file__).parent.parent / "data/public/climate_by_tract.csv"


def test_known_geoid_returns_site_data():
    sd = lookup_by_geoid(
        "17031010200",
        thermal_csv=FIXTURE_CSV,
        climate_csv=FIXTURE_CLIMATE,
    )
    assert isinstance(sd, SiteData)
    assert sd.geoid == "17031010200"
    assert sd.k == pytest.approx(1.50)
    assert sd.alpha == pytest.approx(0.075)
    assert sd.T_g == pytest.approx(12.0)
    assert sd.climate_zone == "5A"
    assert sd.data_available is True


def test_unknown_geoid_returns_unavailable():
    sd = lookup_by_geoid(
        "99999999999",
        thermal_csv=FIXTURE_CSV,
        climate_csv=FIXTURE_CLIMATE,
    )
    assert sd.data_available is False
    assert sd.geoid == "99999999999"


def test_la_tract():
    sd = lookup_by_geoid(
        "06037204510",
        thermal_csv=FIXTURE_CSV,
        climate_csv=FIXTURE_CLIMATE,
    )
    assert sd.climate_zone == "3B"
    assert sd.k == pytest.approx(1.20)

from unittest.mock import patch, MagicMock
import pytest
from geosite.s1_site.geocode import zip_to_geoid


def _zip_mock(lat: str = "41.88", lon: str = "-87.63") -> MagicMock:
    """Mock for zippopotam.us step: returns lat/lon for a ZIP centroid."""
    m = MagicMock()
    m.json.return_value = {"places": [{"latitude": lat, "longitude": lon}]}
    m.raise_for_status.return_value = None
    return m


def _tract_mock(geoid: str) -> MagicMock:
    """Mock for Census coordinates geocoder: returns a census tract GEOID."""
    m = MagicMock()
    m.json.return_value = {
        "result": {"geographies": {"Census Tracts": [{"GEOID": geoid}]}}
    }
    m.raise_for_status.return_value = None
    return m


def _empty_tract_mock() -> MagicMock:
    """Mock for Census geocoder returning no census tracts."""
    m = MagicMock()
    m.json.return_value = {"result": {"geographies": {"Census Tracts": []}}}
    m.raise_for_status.return_value = None
    return m


@patch("geosite.s1_site.geocode.requests.get")
def test_zip_returns_geoid(mock_get):
    # Two calls: first to zippopotam.us, then to Census geocoder
    mock_get.side_effect = [
        _zip_mock("41.88", "-87.63"),
        _tract_mock("17031010200"),
    ]
    result = zip_to_geoid("60601")
    assert result == "17031010200"
    assert len(result) == 11  # census tract GEOID is always 11 digits


@patch("geosite.s1_site.geocode.requests.get")
def test_unknown_zip_raises(mock_get):
    # Zippopotam returns 404 for unknown ZIP
    m = MagicMock()
    m.status_code = 404
    mock_get.return_value = m

    with pytest.raises(ValueError, match="not recognised"):
        zip_to_geoid("00000")


@patch("geosite.s1_site.geocode.requests.get")
def test_no_census_tract_raises(mock_get):
    # Valid ZIP → coordinates, but Census geocoder returns no matching tract
    mock_get.side_effect = [
        _zip_mock("41.88", "-87.63"),
        _empty_tract_mock(),
    ]
    with pytest.raises(ValueError, match="No census tract found"):
        zip_to_geoid("60601")

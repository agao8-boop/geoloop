from unittest.mock import patch, MagicMock
import pytest
from geosite.s1_site.geocode import zip_to_geoid


CENSUS_RESPONSE_CHICAGO = {
    "result": {
        "geographies": {
            "Census Tracts": [
                {"GEOID": "17031010200"}
            ]
        }
    }
}

CENSUS_RESPONSE_NO_TRACT = {
    "result": {
        "geographies": {
            "Census Tracts": []
        }
    }
}


@patch("geosite.s1_site.geocode.requests.get")
def test_zip_returns_geoid(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = CENSUS_RESPONSE_CHICAGO
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    result = zip_to_geoid("60601")

    assert result == "17031010200"
    assert len(result) == 11        # census tract GEOID is always 11 digits


@patch("geosite.s1_site.geocode.requests.get")
def test_unknown_zip_raises(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = CENSUS_RESPONSE_NO_TRACT
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    with pytest.raises(ValueError, match="No census tract found"):
        zip_to_geoid("00000")

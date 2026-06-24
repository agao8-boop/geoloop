import pathlib
import pytest
from geosite.s2_simulation.lookup import lookup_prototype_loads
from geosite.models import LoadPulses

FIXTURE_JSON = pathlib.Path(__file__).parent.parent / "data/public/prototype_loads.json"


def test_small_office_zone_5a_heating_dominant():
    lp = lookup_prototype_loads("small_office", "5A", loads_json=FIXTURE_JSON)
    assert isinstance(lp, LoadPulses)
    assert lp.q_h < 0       # heating dominant — negative
    assert lp.q_m < 0
    assert lp.q_y < 0
    assert lp.q_h == pytest.approx(-78500.0)
    assert lp.q_m == pytest.approx(-32000.0)
    assert lp.q_y == pytest.approx(-3800.0)


def test_small_office_zone_3b_cooling_dominant():
    lp = lookup_prototype_loads("small_office", "3B", loads_json=FIXTURE_JSON)
    assert lp.q_h > 0       # cooling dominant — positive
    assert lp.q_h == pytest.approx(45000.0)


def test_unknown_building_type_raises():
    with pytest.raises(KeyError, match="unknown_building"):
        lookup_prototype_loads("unknown_building", "5A", loads_json=FIXTURE_JSON)


def test_unknown_climate_zone_raises():
    with pytest.raises(KeyError, match="9Z"):
        lookup_prototype_loads("small_office", "9Z", loads_json=FIXTURE_JSON)

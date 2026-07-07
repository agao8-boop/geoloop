"""Footprint-driven NB range: geometry math and optimizer invariants."""

import math
import pytest

from geosite.s4_sizing.footprint import (
    BUILDING_FLOORS,
    PROTOTYPE_AREAS_M2,
    compute_nb_range,
)


def test_floor_table_covers_all_12_prototypes():
    assert set(BUILDING_FLOORS) == set(PROTOTYPE_AREAS_M2)
    assert len(BUILDING_FLOORS) == 12
    assert BUILDING_FLOORS["large_office"] == 12
    assert BUILDING_FLOORS["small_office"] == 1


def test_small_office_prototype_range():
    # footprint = 511/1; W = sqrt(511)/3 = 7.535 m; L = 3*sqrt(511) = 67.816 m
    # nb_min = ceil(7.535/6) = 2; perimeter = 150.70 m -> nb_max = floor(25.12) = 25
    nb_min, nb_max, meta = compute_nb_range(None, "small_office", spacing_m=6.0)
    assert nb_min == 2
    assert nb_max == 25
    assert meta["footprint_m2"] == pytest.approx(511.0)
    assert meta["n_floors"] == 1
    assert meta["width_m"] == pytest.approx(7.535, abs=0.01)
    assert meta["length_m"] == pytest.approx(9 * meta["width_m"])
    assert meta["prototype_area_used"] is True


def test_large_office_prototype_range():
    # footprint = 46320/12 = 3860; W = 20.710 m; L = 186.39 m
    # nb_min = ceil(20.710/6) = 4; perimeter = 414.19 m -> nb_max = 69
    nb_min, nb_max, meta = compute_nb_range(None, "large_office", spacing_m=6.0)
    assert nb_min == 4
    assert nb_max == 69
    assert meta["footprint_m2"] == pytest.approx(3860.0)


def test_medium_office_prototype_range():
    # footprint = 4982/3 = 1660.67; W = 13.584 m; nb_min = 3; nb_max = 45
    nb_min, nb_max, _ = compute_nb_range(None, "medium_office", spacing_m=6.0)
    assert (nb_min, nb_max) == (3, 45)


def test_user_area_overrides_prototype():
    # 1022 m2 small office: footprint 1022; W = 10.656 m -> nb_min 2;
    # L = 95.907; perimeter = 213.13 -> nb_max 35
    nb_min, nb_max, meta = compute_nb_range(1022.0, "small_office", spacing_m=6.0)
    assert (nb_min, nb_max) == (2, 35)
    assert meta["prototype_area_used"] is False


def test_tighter_spacing_expands_range():
    nb_min6, nb_max6, _ = compute_nb_range(None, "small_office", spacing_m=6.0)
    nb_min3, nb_max3, _ = compute_nb_range(None, "small_office", spacing_m=3.0)
    assert nb_min3 >= nb_min6
    assert nb_max3 > nb_max6
    assert (nb_min3, nb_max3) == (3, 50)


def test_nb_min_never_below_one_and_range_ordered():
    for bt in BUILDING_FLOORS:
        nb_min, nb_max, _ = compute_nb_range(None, bt, spacing_m=6.0)
        assert 1 <= nb_min <= nb_max


def test_unknown_building_type_raises():
    with pytest.raises(KeyError):
        compute_nb_range(None, "space_station")


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        compute_nb_range(-5.0, "small_office")
    with pytest.raises(ValueError):
        compute_nb_range(None, "small_office", spacing_m=0.0)

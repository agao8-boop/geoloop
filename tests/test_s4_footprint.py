"""Footprint-driven NB range: geometry math and optimizer invariants."""

import math
import pytest

from geosite.s4_sizing.footprint import (
    BUILDING_FLOORS,
    BUILDING_SHAPES,
    DEFAULT_SHAPE,
    PROTOTYPE_AREAS_M2,
    compute_nb_range,
    shape_geometry,
)


def test_floor_table_covers_all_prototypes():
    assert set(BUILDING_FLOORS) == set(PROTOTYPE_AREAS_M2)
    assert len(BUILDING_FLOORS) == 16
    assert BUILDING_FLOORS["large_office"] == 12
    assert BUILDING_FLOORS["small_office"] == 1


def test_default_shape_is_elongated_linear_array():
    # default keeps back-compat with the old 9:1 rectangle (linear borehole row)
    assert DEFAULT_SHAPE == "elongated"
    assert BUILDING_SHAPES["elongated"]["area_units"] == 9.0


@pytest.mark.parametrize("bt", sorted(BUILDING_FLOORS))
def test_meta_reports_default_shape(bt):
    _, _, meta = compute_nb_range(None, bt, spacing_m=6.0)
    assert meta["shape"] == DEFAULT_SHAPE
    assert meta["shape_label"] == BUILDING_SHAPES[DEFAULT_SHAPE]["label"]


@pytest.mark.parametrize("shape_key", sorted(BUILDING_SHAPES))
def test_shape_geometry_polygon_scales_to_footprint(shape_key):
    geom = shape_geometry(500.0, shape_key)
    sh = BUILDING_SHAPES[shape_key]
    assert geom["scale"] == pytest.approx(math.sqrt(500.0 / sh["area_units"]))
    assert len(geom["pts"]) == len(sh["polygon"])
    # shoelace area of the scaled polygon must equal the footprint
    pts = geom["pts"]
    n = len(pts)
    area = abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                   for i in range(n))) / 2.0
    assert area == pytest.approx(500.0)
    assert geom["perimeter_m"] > 0


def test_small_office_prototype_range():
    # footprint = 511/1; elongated (9 sq units); scale = sqrt(511/9) = 7.535 m
    # nb_min = ceil(7.535/6) = 2; perimeter = 150.70 m -> nb_max = floor(25.12) = 25
    nb_min, nb_max, meta = compute_nb_range(None, "small_office", spacing_m=6.0)
    assert nb_min == 2
    assert nb_max == 25
    assert meta["footprint_m2"] == pytest.approx(511.0)
    assert meta["n_floors"] == 1
    assert meta["scale_m"] == pytest.approx(7.535, abs=0.01)
    assert meta["perimeter_m"] == pytest.approx(20.0 * meta["scale_m"])
    assert meta["pts"][1][0] == pytest.approx(9.0 * meta["scale_m"])  # long side
    assert meta["prototype_area_used"] is True


def test_num_floors_override_changes_footprint():
    # small_office prototype is 1 floor; 2 floors halves the footprint
    _, _, meta1 = compute_nb_range(None, "small_office", spacing_m=6.0)
    _, _, meta2 = compute_nb_range(None, "small_office", spacing_m=6.0, num_floors=2)
    assert meta2["n_floors"] == 2
    assert meta2["footprint_m2"] == pytest.approx(meta1["footprint_m2"] / 2.0)


def test_square_shape_shrinks_perimeter_vs_elongated():
    _, nb_max_el, meta_el = compute_nb_range(None, "small_office", spacing_m=6.0,
                                             shape="elongated")
    _, nb_max_sq, meta_sq = compute_nb_range(None, "small_office", spacing_m=6.0,
                                             shape="square")
    assert meta_sq["perimeter_m"] < meta_el["perimeter_m"]
    assert nb_max_sq < nb_max_el
    # square: scale = sqrt(511) = 22.605; perimeter = 4*scale = 90.42
    assert meta_sq["scale_m"] == pytest.approx(math.sqrt(511.0))
    assert meta_sq["perimeter_m"] == pytest.approx(4.0 * meta_sq["scale_m"])


def test_unknown_shape_raises():
    with pytest.raises(KeyError):
        compute_nb_range(None, "small_office", shape="triangle")


def test_invalid_num_floors_raises():
    with pytest.raises(ValueError):
        compute_nb_range(None, "small_office", num_floors=0)


def test_large_office_prototype_range():
    # footprint = 46320/12 = 3860; aspect 9; W = 20.710 m; L = 186.39 m
    # nb_min = ceil(20.710/6) = 4; perimeter = 414.19 m -> nb_max = 69
    nb_min, nb_max, meta = compute_nb_range(None, "large_office", spacing_m=6.0)
    assert nb_min == 4
    assert nb_max == 69
    assert meta["footprint_m2"] == pytest.approx(3860.0)


def test_medium_office_prototype_range():
    # footprint = 4982/3 = 1660.67; aspect 9; W = 13.584 m; nb_min = 3; nb_max = 45
    nb_min, nb_max, _ = compute_nb_range(None, "medium_office", spacing_m=6.0)
    assert (nb_min, nb_max) == (3, 45)


def test_user_area_overrides_prototype():
    # 1022 m2 small office: footprint 1022; aspect 9; W = 10.656 m -> nb_min 2;
    # L = 95.91; perimeter = 213.13 -> nb_max 35
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


from geosite.s4_sizing.footprint import load_implied_nb_range


def test_load_implied_range_heating_peak():
    # |q_h| = 60 kW at H_min = 125 m:
    # lo = ceil(60000/(70*125)) = 7; hi = ceil(60000/(15*125)) = 32
    lo, hi = load_implied_nb_range(-60000.0, 125.0)
    assert (lo, hi) == (7, 32)


def test_load_implied_range_uses_absolute_value():
    assert load_implied_nb_range(60000.0, 125.0) == load_implied_nb_range(-60000.0, 125.0)


def test_load_implied_range_floors_at_one():
    lo, hi = load_implied_nb_range(0.0, 125.0)
    assert lo == 1
    assert hi >= lo
    lo_tiny, hi_tiny = load_implied_nb_range(-100.0, 125.0)
    assert lo_tiny == 1
    assert hi_tiny >= lo_tiny


def test_load_implied_range_ordered():
    lo, hi = load_implied_nb_range(-250000.0, 100.0)
    assert 1 <= lo <= hi


from geosite.s4_sizing.ashrae_sizing import size_borefield
from geosite.s4_sizing.footprint import find_optimal_nb

_ADV = dict(
    Cp=4200.0, mfls=0.05, rbore=0.06, rpin=0.01365, rpext=0.0167,
    kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0,
)
_GROUND = dict(k=2.0, alpha=0.086, T_g=15.0)
_BIG_COOL = dict(q_h=400_000.0, q_m=90_000.0, q_y=20_000.0, T_in_HP=40.2)
_SMALL_COOL = dict(q_h=8_000.0, q_m=4_000.0, q_y=1_000.0, T_in_HP=40.2)


def test_optimal_nb_within_range_and_meets_depth():
    nb, L, H = find_optimal_nb(4, 69, **_BIG_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert 4 <= nb <= 69
    assert H == pytest.approx(L / nb)
    assert H >= 125.0
    assert L > 0


def test_optimal_nb_minimizes_L_over_valid_range():
    nb, L, H = find_optimal_nb(4, 69, **_BIG_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    for cand in range(4, 70):
        L_c = float(size_borefield(**_BIG_COOL, **_GROUND, **_ADV,
                                   B=6.0, NB=cand, A=9.0))
        if L_c > 0 and L_c / cand >= 125.0:
            assert L <= L_c + 1e-9


def test_small_load_falls_back_to_depth_primary():
    # L0 ~ 101 m: even nb_min=4 gives H ~ 25 m < 125 -> no valid range NB;
    # depth-primary fallback gives NB=1 < nb_min
    nb, L, H = find_optimal_nb(4, 15, **_SMALL_COOL, **_GROUND,
                               H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert nb < 4          # fallback signalled by nb_opt < nb_min
    assert nb >= 1
    assert L > 0
    assert H == pytest.approx(L / nb)


def test_nonbinding_constraint_returns_L0():
    # Strong ground, tiny injection at high T_in_HP -> L can be non-positive
    nb, L, H = find_optimal_nb(
        2, 25, q_h=100.0, q_m=50.0, q_y=-5_000.0, T_in_HP=40.2,
        **_GROUND, H_min=125.0, B=6.0, A=9.0, **_ADV)
    assert nb == 1
    assert L <= 0

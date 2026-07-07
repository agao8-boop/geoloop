"""Footprint-driven NB inside run_strategy."""

import pytest
from geosite.s6_strategy import run_strategy
from geosite.s4_sizing.footprint import compute_nb_range

_CHI = dict(
    building_type="small_office", climate_zone="5A",
    k=2.0, alpha=0.1, T_g=12.0, B=6.0, A=9.0, state="IL",
)


def test_auto_nb_comes_from_footprint_range():
    r = run_strategy(**_CHI)
    nb_min, nb_max, _ = compute_nb_range(None, "small_office", spacing_m=6.0)
    assert r.nb_min == nb_min
    assert r.nb_max == nb_max
    assert (nb_min <= r.NB <= nb_max) or r.NB < nb_min  # in-range or fallback
    assert r.NB >= 1


def test_explicit_nb_bypasses_footprint():
    r = run_strategy(**_CHI, NB=16)
    assert r.NB == 16
    assert r.nb_min is None
    assert r.nb_max is None
    assert r.H_before == pytest.approx(r.L_before / 16)


def test_to_dict_has_range_keys():
    d = run_strategy(**_CHI).to_dict()
    assert "nb_min" in d
    assert "nb_max" in d


def test_floor_area_scaling_uses_full_area_table():
    # hospital was missing from the old 3-entry table (scale blew up to
    # floor_area/1.0); strategy must now use the full 12-type table
    from geosite.s6_strategy.strategy import _PROTOTYPE_AREAS_M2
    assert len(_PROTOTYPE_AREAS_M2) == 12
    assert _PROTOTYPE_AREAS_M2["hospital"] == 22422.0
    # at prototype area the scale must be ~1.0 (no hourly profile data exists
    # for hospital yet, so exercise the path with a type that has one)
    r_proto = run_strategy(**dict(_CHI, building_type="medium_office"), NB=16)
    r_same = run_strategy(**dict(_CHI, building_type="medium_office"), NB=16,
                          floor_area_m2=4982.0)
    assert r_same.L_before == pytest.approx(r_proto.L_before, rel=0.01)

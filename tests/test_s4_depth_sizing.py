"""Depth-primary sizing: NB derived from target borehole depth.

XLS_D inputs are the philippe_2010_sizing.xls bh_sizing column D cooling
case, which gives L0 = 151.657 m without borefield interaction.
"""

import math
import pytest

from geosite.s4_sizing.ashrae_sizing import size_borefield, size_borefield_for_depth

XLS_D = dict(
    q_h=12_000.0, q_m=6_000.0, q_y=1_500.0,
    k=2.0, alpha=0.086, T_g=15.0,
    Cp=4_200.0, mfls=0.05, T_in_HP=40.2,
    rbore=0.06, rpin=0.01365, rpext=0.0167,
    kgrout=1.5, kpipe=0.42, LU=0.0511, hconv=1000.0,
)


def test_depth_sizing_small_load_two_boreholes():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=125.0)
    assert NB == 2
    assert H == pytest.approx(L / NB)
    assert H <= 125.0
    assert 140 < L < 180


def test_depth_sizing_single_borehole_when_target_exceeds_L0():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=200.0)
    assert NB == 1
    assert 140 < L < 180
    assert H <= 200.0


def test_depth_sizing_large_load_fixed_point_invariant():
    big = dict(XLS_D, q_h=1_200_000.0, q_m=600_000.0, q_y=150_000.0)
    L, NB, H = size_borefield_for_depth(**big, B=6.1, A=1.0, H_target=125.0)
    assert NB == math.ceil(L / 125.0)
    assert H <= 125.0
    assert NB > 50


def test_depth_sizing_consistent_with_fixed_nb():
    L, NB, H = size_borefield_for_depth(**XLS_D, B=6.1, A=1.0, H_target=125.0)
    L_fixed = float(size_borefield(**XLS_D, B=6.1, NB=NB, A=1.0))
    assert L == pytest.approx(L_fixed, abs=1.5)

import math
import pytest
from geosite.s5_cost.line_items import calc_line_items

# Spreadsheet anchor: Close-loop h - s (best, 80% sand)
# NB=32, L_exact=2206.326m, B=6.7m, distance_to_house=435ft
# H_exact=68.9477m, H_rounded=230ft, Total=$269,933.79
BEST_L_M = 2206.326178192672
BEST_NB = 32
BEST_B_M = 6.7
BEST_DIST_FT = 435.0
BEST_RATES = {
    "drilling_soil": 30, "drilling_rock": 100, "well_casing": 20,
    "sand_bag": 10, "grout_bag": 20, "utube_pipe": 2,
    "horiz_pipe": 1, "horiz_trench": 5, "mobilization": 1000,
}

# Spreadsheet anchor: Close-loop h - c (worst, 80% clay)
WORST_L_M = 3662.5428199546277
WORST_NB = 32
WORST_B_M = 6.7
WORST_DIST_FT = 435.0


def _items_as_dict(items):
    return {i["name"]: i for i in items}


def test_best_scenario_matches_spreadsheet_total():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    total = sum(i["cost_usd"] for i in items)
    assert total == pytest.approx(269933.79, rel=0.005)


def test_worst_scenario_matches_spreadsheet_total():
    items = calc_line_items(
        L_m=WORST_L_M, NB=WORST_NB, B_m=WORST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=WORST_DIST_FT,
    )
    total = sum(i["cost_usd"] for i in items)
    assert total == pytest.approx(439533.79, rel=0.005)


def test_drilling_lf_uses_rounded_depth():
    # H_exact = 68.9477 m = 226.2 ft → rounds to 230 ft
    # Drilling LF = 32 × 230 = 7,360
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["drilling_soil"]["qty"] == pytest.approx(7360.0)


def test_grout_bags_per_borehole_matches_spreadsheet():
    # Spreadsheet: 8 bags/borehole × 32 = 256 total
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["grout_bag"]["qty"] == 256


def test_sand_bags_is_eight_times_grout_bags():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["sand_bag"]["qty"] == d["grout_bag"]["qty"] * 8


def test_utube_pipe_qty_equals_drilling_lf():
    # $2/LF covers both U-tube legs; qty = total drilling LF
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["utube_pipe"]["qty"] == pytest.approx(d["drilling_soil"]["qty"] + d["drilling_rock"]["qty"])


def test_horiz_trench_formula():
    # (NB-1) × B_ft + distance_to_house = 31 × 21.98 + 435 = 1116.26 LF
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["horiz_trench"]["qty"] == pytest.approx(1116.26, rel=0.002)


def test_horiz_pipe_is_double_trench():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=BEST_DIST_FT,
    )
    d = _items_as_dict(items)
    assert d["horiz_pipe"]["qty"] == pytest.approx(d["horiz_trench"]["qty"] * 2)


def test_rock_frac_affects_drilling_split():
    items_base = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.30, distance_to_house_ft=100.0,
    )
    d = _items_as_dict(items_base)
    total_drill_lf = d["drilling_soil"]["qty"] + d["drilling_rock"]["qty"]
    assert d["drilling_rock"]["qty"] == pytest.approx(total_drill_lf * 0.30, rel=0.01)
    assert d["drilling_soil"]["qty"] == pytest.approx(total_drill_lf * 0.70, rel=0.01)


def test_well_casing_is_zero_by_default():
    items = calc_line_items(
        L_m=BEST_L_M, NB=BEST_NB, B_m=BEST_B_M, rates=BEST_RATES,
        rock_frac=0.0, distance_to_house_ft=100.0,
    )
    d = _items_as_dict(items)
    assert d["well_casing"]["qty"] == 0
    assert d["well_casing"]["cost_usd"] == 0

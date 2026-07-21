import pytest
from geosite.s6_strategy.ldc import (
    compute_ldc,
    trim_profile,
    extract_one_sided_pulses,
)


def _flat_profile(n=8760, val=0.0):
    return [val] * n


def test_ldc_cutoff_idx_10pct():
    profile = list(range(1, 8761))  # 1 to 8760 W
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    assert result["cutoff_idx"] == 876


def test_ldc_cutoff_value_10pct():
    # Values 1..8760, sorted desc: 8760, 8759, ..., 7885 at index 876
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    assert result["cutoff_W"] == pytest.approx(7884.0, abs=1.0)


def test_ldc_sorted_abs_descending():
    profile = [3.0, -10.0, 5.0, -2.0] + [0.0] * 8756
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    # sorted by magnitude desc: 10, 5, 3, 2, 0, 0, ...
    assert result["sorted_abs"][0] == pytest.approx(10.0)
    assert result["sorted_abs"][1] == pytest.approx(5.0)


def test_trim_profile_balanced_clips_both_sides():
    profile = [-100.0, -50.0, 0.0, 50.0, 100.0] + [0.0] * 8755
    trimmed = trim_profile(profile, 75.0, "balanced")
    assert trimmed[0] == pytest.approx(-75.0)
    assert trimmed[1] == pytest.approx(-50.0)
    assert trimmed[2] == pytest.approx(0.0)
    assert trimmed[3] == pytest.approx(50.0)
    assert trimmed[4] == pytest.approx(75.0)


def test_trim_profile_heating_clips_heating_only():
    profile = [-100.0, -50.0, 200.0] + [0.0] * 8757
    trimmed = trim_profile(profile, 75.0, "heating")
    assert trimmed[0] == pytest.approx(-75.0)    # clipped
    assert trimmed[1] == pytest.approx(-50.0)    # unchanged
    assert trimmed[2] == pytest.approx(200.0)    # cooling unchanged


def test_trim_profile_cooling_clips_cooling_only():
    profile = [-200.0, 50.0, 100.0] + [0.0] * 8757
    trimmed = trim_profile(profile, 75.0, "cooling")
    assert trimmed[0] == pytest.approx(-200.0)   # heating unchanged
    assert trimmed[1] == pytest.approx(50.0)     # unchanged
    assert trimmed[2] == pytest.approx(75.0)     # clipped


def test_extract_heating_pulses_dominant_negative():
    profile = [-30000.0] * 100 + [5000.0] * 100 + [0.0] * 8560
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    assert q_h < 0                               # heating = negative
    assert q_h == pytest.approx(-30000.0)        # peak extraction


def test_extract_cooling_pulses_dominant_positive():
    profile = [20000.0] * 100 + [-5000.0] * 100 + [0.0] * 8560
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "cooling")
    assert q_h > 0                               # cooling = positive
    assert q_h == pytest.approx(20000.0)


def test_extract_one_sided_zeroes_opposite():
    # Heating only: cooling hours contribute 0 to annual average
    profile = [-10000.0] * 4380 + [15000.0] * 4380  # half heat, half cool
    q_h, q_m, q_y = extract_one_sided_pulses(profile, "heating")
    # q_y = mean of heating-only profile (cooling hours zeroed)
    # heating contribution: -10000 * 4380 / 8760 = -5000
    assert q_y == pytest.approx(-5000.0, rel=0.01)



def test_ashrae_cap_applied():
    # sorted desc [8760..1]; cap_idx = int(8760*0.4/100) = 35
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.4)
    assert result["cap_idx"] == 35
    # cap_W = sorted_abs[35] = 8760 - 35 = 8725
    assert result["cap_W"] == pytest.approx(8725.0, abs=1.0)
    # sorted_abs_capped[:35] should all equal cap_W
    assert all(v == pytest.approx(8725.0, abs=1.0) for v in result["sorted_abs_capped"][:35])


def test_m1_cutoff_beyond_cap_idx_unchanged():
    # For profile 1..8760, m1 cutoff idx=876 is well beyond cap_idx=35
    # so m1_cutoff_W should equal sorted_abs[876] = 7884 (uncapped region)
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.4)
    assert result["m1_cutoff_idx"] == 876
    assert result["m1_cutoff_W"] == pytest.approx(7884.0, abs=1.0)
    assert result["cutoff_W"] == pytest.approx(7884.0, abs=1.0)  # backward compat


def test_m2_energy_cutoff_peaker_area():
    # Verify method 2 gives approximately 10% of energy in peaker zone
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    total_Wh = sum(abs(h) for h in profile)
    peaker_Wh = result["m2_peaker_energy_Wh"]
    assert abs(peaker_Wh / total_Wh - 0.10) < 0.001  # within 0.1% of target


def test_m2_cutoff_hours_less_than_m1():
    # Energy-based method should have fewer peaker hours than hours-based
    # when energy is concentrated in a few high-load hours (typical convex
    # building LDC). NOTE: a linear ramp profile does NOT satisfy this —
    # for a triangular LDC the area above the cutoff grows quadratically,
    # so 10% of energy spans far more than 10% of hours. Use a peaked
    # profile instead: 50 hours at 10 kW, the rest at 100 W.
    profile = [10000.0] * 50 + [100.0] * 8710
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    assert result["m2_cutoff_idx"] < result["m1_cutoff_idx"]


def test_m1_gshp_hours_pct_is_90():
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    assert result["m1_gshp_hours_pct"] == pytest.approx(90.0, abs=0.1)


def test_m2_gshp_energy_pct_is_90():
    profile = list(range(1, 8761))
    result = compute_ldc(profile, 10.0, ignore_top_pct=0.0)
    assert result["m2_gshp_energy_pct"] == pytest.approx(90.0, abs=0.2)

"""Tests for climate-aware, heat/cool-split envelope factors."""
import pytest
from geosite.s2_simulation.envelope import (
    get_envelope_factors,
    compute_envelope_factor,
    GLAZING_OPTIONS, WWR_OPTIONS, ENVELOPE_OPTIONS,
)
from geosite.s2_simulation import get_loads


# ---------------------------------------------------------------------------
# get_envelope_factors
# ---------------------------------------------------------------------------

def test_baseline_returns_unity():
    h, c = get_envelope_factors("5B", "medium_office", "medium", "double", "standard")
    assert h == pytest.approx(1.0, abs=0.05)
    assert c == pytest.approx(1.0, abs=0.05)

def test_heat_cool_asymmetric_triple_cold_climate():
    # Denver (5B): triple low-E cuts heating more than cooling
    h, c = get_envelope_factors("5B", "medium_office", "medium", "triple", "standard")
    assert h < c, f"expected heat<cool in cold climate but h={h:.3f} c={c:.3f}"
    assert h < 0.80

def test_double_legacy_higher_cooling_than_double():
    # Pre-2000 clear glass → more solar gain → more cooling load
    _, c_leg = get_envelope_factors("5B", "medium_office", "medium", "double_legacy", "standard")
    _, c_dbl = get_envelope_factors("5B", "medium_office", "medium", "double",        "standard")
    assert c_leg > c_dbl, f"legacy should have higher cooling: {c_leg:.3f} vs {c_dbl:.3f}"

def test_double_legacy_in_options():
    assert "double_legacy" in GLAZING_OPTIONS

def test_unknown_climate_zone_falls_back_without_raising():
    h, c = get_envelope_factors("9", "medium_office", "medium", "double", "standard")
    assert isinstance(h, float) and isinstance(c, float)

def test_unknown_building_type_falls_back():
    h, c = get_envelope_factors("5B", "hospital_nonexistent", "medium", "double", "standard")
    assert isinstance(h, float) and isinstance(c, float)

def test_high_wwr_increases_load():
    h_lo, c_lo = get_envelope_factors("5B", "medium_office", "low",  "double", "standard")
    h_hi, c_hi = get_envelope_factors("5B", "medium_office", "high", "double", "standard")
    assert h_hi > h_lo and c_hi > c_lo

def test_single_pane_higher_than_double():
    h_s, c_s = get_envelope_factors("5B", "medium_office", "medium", "single", "standard")
    h_d, c_d = get_envelope_factors("5B", "medium_office", "medium", "double", "standard")
    assert h_s > h_d and c_s > c_d

def test_returns_tuple_of_two_floats():
    result = get_envelope_factors("3A", "medium_office")
    assert len(result) == 2
    assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# compute_envelope_factor (legacy shim)
# ---------------------------------------------------------------------------

def test_legacy_shim_returns_float():
    f = compute_envelope_factor("medium", "standard", "double")
    assert isinstance(f, float)
    assert f == pytest.approx(1.0, abs=0.10)

def test_legacy_shim_defaults():
    assert compute_envelope_factor() == pytest.approx(1.0, abs=0.10)


# ---------------------------------------------------------------------------
# get_loads — asymmetric factor application
# ---------------------------------------------------------------------------

def test_get_loads_asymmetric_factors():
    base   = get_loads("medium_office", "5B")
    scaled = get_loads("medium_office", "5B", heat_factor=2.0, cool_factor=0.5)
    assert scaled.q_h_heat == pytest.approx(base.q_h_heat * 2.0, rel=0.01)
    assert scaled.q_h_cool == pytest.approx(base.q_h_cool * 0.5, rel=0.01)

def test_get_loads_unity_factors_unchanged():
    base   = get_loads("medium_office", "5B")
    scaled = get_loads("medium_office", "5B", heat_factor=1.0, cool_factor=1.0)
    assert scaled.q_h == pytest.approx(base.q_h, rel=0.001)

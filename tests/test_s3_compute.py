import numpy as np
import pytest
from geosite.s3_loads.compute import compute_pulses, compute_pulses_from_ground
from geosite.models import LoadPulses


def _make_synthetic_8760():
    """Return (q_heat[8760], q_cool[8760]) for a heating-dominant building."""
    q_heat = np.zeros(8760)
    q_cool = np.zeros(8760)
    # Winter heating: hours 0–2159 (Jan–Mar) and 6552–8759 (Oct–Dec)
    # 12 hours of peak load per day, offset by hour-of-day
    for h in range(8760):
        month_approx = h // 730      # rough month (0–11)
        hour_of_day = h % 24
        if month_approx in (0, 1, 2, 9, 10, 11):   # winter
            if 8 <= hour_of_day < 20:               # occupied hours
                q_heat[h] = 10_000.0
        elif month_approx in (5, 6, 7):             # summer
            if 8 <= hour_of_day < 20:
                q_cool[h] = 8_000.0
    return q_heat, q_cool


def test_heating_dominant_sign():
    q_heat, q_cool = _make_synthetic_8760()
    result = compute_pulses(q_heat, q_cool)
    assert isinstance(result, LoadPulses)
    assert result.q_h < 0   # heating dominant → peak hourly is negative
    assert result.q_m < 0   # peak month average is negative
    # Annual average: heating dominant so q_y should be negative
    assert result.q_y < 0


def test_peak_hourly_magnitude():
    q_heat, q_cool = _make_synthetic_8760()
    result = compute_pulses(q_heat, q_cool)
    # Peak heating hour = -10,000 W (q_cool is 0 in winter)
    assert result.q_h == pytest.approx(-10_000.0, abs=1.0)


def test_cooling_only_is_positive():
    q_heat = np.zeros(8760)
    q_cool = np.full(8760, 5_000.0)  # constant 5 kW cooling all year
    result = compute_pulses(q_heat, q_cool)
    assert result.q_h > 0
    assert result.q_h == pytest.approx(5_000.0, abs=1.0)
    assert result.q_y == pytest.approx(5_000.0, abs=1.0)


def test_balanced_load_near_zero_annual():
    # Equal heating and cooling → q_y near 0
    q_heat = np.zeros(8760)
    q_cool = np.zeros(8760)
    # 6 months heating, 6 months cooling, same magnitude
    q_heat[:4380] = 5_000.0
    q_cool[4380:] = 5_000.0
    result = compute_pulses(q_heat, q_cool)
    assert abs(result.q_y) < 100.0   # near-zero annual average


def test_compute_pulses_from_ground_matches_compute_pulses():
    """compute_pulses_from_ground(q_cool - q_heat) must equal compute_pulses(q_heat, q_cool)."""
    q_heat, q_cool = _make_synthetic_8760()
    ref = compute_pulses(q_heat, q_cool)
    ground = q_cool - q_heat
    result = compute_pulses_from_ground(ground)
    assert result.q_h == pytest.approx(ref.q_h, rel=1e-9)
    assert result.q_m == pytest.approx(ref.q_m, rel=1e-9)
    assert result.q_y == pytest.approx(ref.q_y, rel=1e-9)
    assert result.q_h_heat == pytest.approx(ref.q_h_heat, rel=1e-9)
    assert result.q_h_cool == pytest.approx(ref.q_h_cool, rel=1e-9)


def test_compute_pulses_from_ground_wrong_length_raises():
    with pytest.raises(ValueError):
        compute_pulses_from_ground([0.0] * 8759)

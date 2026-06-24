"""Convert EnergyPlus 8760h zone loads to ASHRAE three-pulse ground loads.

This module is used only in the EnergyPlus real-time path (Plan B).
In the fast/pre-computed path, LoadPulses come directly from prototype_loads.json.

Sign convention (Philippe et al. 2010):
    negative → heat extraction from ground (heating mode)
    positive → heat injection into ground  (cooling mode)
"""

import numpy as np
from geosite.models import LoadPulses

# Approximate hours per month for a non-leap year
_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def compute_pulses(
    q_heat: np.ndarray,
    q_cool: np.ndarray,
) -> LoadPulses:
    """Aggregate 8760h EnergyPlus zone loads into three ASHRAE sizing pulses.

    Parameters
    ----------
    q_heat : array of shape (8760,), zone heating demand [W], always ≥ 0
    q_cool : array of shape (8760,), zone cooling demand [W], always ≥ 0

    Returns
    -------
    LoadPulses following the Philippe et al. (2010) sign convention.
    """
    q_heat = np.asarray(q_heat, dtype=float)
    q_cool = np.asarray(q_cool, dtype=float)

    if q_heat.shape != (8760,) or q_cool.shape != (8760,):
        raise ValueError("q_heat and q_cool must each have exactly 8760 values")

    # Net hourly ground load: heating extracts (negative), cooling rejects (positive)
    ground = q_cool - q_heat  # shape (8760,)

    # Determine dominant mode by annual energy
    heating_dominant = q_heat.sum() >= q_cool.sum()

    # Peak hourly load (q_h): worst single hour in dominant direction
    q_h = float(ground.min() if heating_dominant else ground.max())

    # Monthly averages
    monthly_avg = _monthly_averages(ground)

    # Peak monthly average (q_m): worst month in dominant direction
    q_m = float(monthly_avg.min() if heating_dominant else monthly_avg.max())

    # Annual average (q_y)
    q_y = float(ground.mean())

    return LoadPulses(q_h=q_h, q_m=q_m, q_y=q_y)


def _monthly_averages(ground: np.ndarray) -> np.ndarray:
    """Return 12-element array of monthly averages from an 8760h series."""
    avgs = np.empty(12)
    idx = 0
    for m, hours in enumerate(_MONTH_HOURS):
        avgs[m] = ground[idx : idx + hours].mean()
        idx += hours
    return avgs

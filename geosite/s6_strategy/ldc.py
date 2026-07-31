import math

import numpy as np

_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def _monthly_averages(arr: np.ndarray) -> np.ndarray:
    avgs = np.empty(12)
    idx = 0
    for m, hours in enumerate(_MONTH_HOURS):
        avgs[m] = arr[idx: idx + hours].mean()
        idx += hours
    return avgs


def compute_ldc(profile: list, cutoff_pct: float = 10.0, ignore_top_pct: float = 0.4) -> dict:
    """Sort 8760h profile by |load| descending; apply ASHRAE peak cap; return energy-based cutoff.

    ignore_top_pct:  top % of hours to cap at the design-condition load.
                     0.4% → 35 hours of 8760 (ASHRAE 99.6% design condition).
    cutoff_pct:      % of total annual energy handled by peaker (default 10%).

    Method 2 (energy-based):  cutoff where peaker excess energy = cutoff_pct% of total.
    Backward-compatible keys: "cutoff_idx" and "cutoff_W" alias Method 2 results.
    """
    arr = np.asarray(profile, dtype=float)
    sorted_abs = np.sort(np.abs(arr))[::-1].copy()
    n = len(sorted_abs)

    # ASHRAE cap: flatten the top ignore_top_pct% of hours at the cap load
    cap_idx = int(n * ignore_top_pct / 100)
    if 0 < cap_idx < n:
        cap_W = float(sorted_abs[cap_idx])
        sorted_abs_capped = sorted_abs.copy()
        sorted_abs_capped[:cap_idx] = cap_W
    else:
        cap_W = float(sorted_abs[0]) if n > 0 else 0.0
        cap_idx = 0
        sorted_abs_capped = sorted_abs.copy()

    total_Wh = float(sorted_abs_capped.sum())

    # --- Method 2: energy-based (binary search on cutoff_W) ---
    # excess(W) = sum(max(v - W, 0)) = total energy above the W threshold
    # excess is monotonically decreasing in W; binary search to hit target_excess_Wh
    target_excess_Wh = (cutoff_pct / 100.0) * total_Wh
    lo, hi = 0.0, float(sorted_abs_capped[0]) if n > 0 else 0.0
    for _ in range(60):   # 60 bisections → ~1e-18 relative precision
        mid = (lo + hi) / 2.0
        if float(np.maximum(sorted_abs_capped - mid, 0.0).sum()) > target_excess_Wh:
            lo = mid
        else:
            hi = mid
    m2_cutoff_W = (lo + hi) / 2.0
    # number of hours where capped load strictly exceeds the cutoff
    m2_idx = int(np.sum(sorted_abs_capped > m2_cutoff_W + 1e-3))
    m2_gshp_Wh = float(np.minimum(sorted_abs_capped, m2_cutoff_W).sum())
    m2_gshp_energy_pct = round(100.0 * m2_gshp_Wh / total_Wh, 2) if total_Wh > 0 else 100.0
    m2_gshp_hours_pct = round(100.0 * (n - m2_idx) / n, 2)
    m2_peaker_Wh = total_Wh - m2_gshp_Wh

    return {
        # ASHRAE cap
        "cap_W": cap_W,
        "cap_idx": cap_idx,
        # Raw LDC data (for visualization)
        "sorted_abs": sorted_abs.tolist(),
        "sorted_abs_capped": sorted_abs_capped.tolist(),
        # Method 2 — energy-based (only method)
        "m2_cutoff_W": m2_cutoff_W,
        "m2_cutoff_idx": m2_idx,
        "m2_gshp_hours_pct": m2_gshp_hours_pct,
        "m2_gshp_energy_pct": m2_gshp_energy_pct,
        "m2_peaker_energy_Wh": m2_peaker_Wh,
        # Backward-compat aliases → M2
        "cutoff_idx": m2_idx,
        "cutoff_W": m2_cutoff_W,
    }


def trim_profile(profile: list, cutoff_W: float, dominant_mode: str) -> list:
    """Clip loads to ±cutoff_W; 'heating'=clip negative only, 'cooling'=clip positive only, 'balanced'=clip both."""
    arr = np.asarray(profile, dtype=float)
    if dominant_mode == "heating":
        return np.where(arr < 0, np.maximum(arr, -cutoff_W), arr).tolist()
    if dominant_mode == "cooling":
        return np.where(arr > 0, np.minimum(arr, cutoff_W), arr).tolist()
    return np.clip(arr, -cutoff_W, cutoff_W).tolist()


def extract_one_sided_pulses(profile: list, mode: str) -> tuple:
    """Extract (q_h, q_m, q_y) for one-mode sizing; 'heating' zeroes positive hours (q_h<0), 'cooling' zeroes negative (q_h>0).

    q_y is the NET annual average of the full profile (Philippe et al. 2010 definition),
    not a one-sided average. A positive q_y means net cooling-dominant (net heat injection
    to ground); negative means net heating-dominant. This is the same value for both the
    heating-mode and cooling-mode sizing calls — it represents the long-term ground
    thermal imbalance, not a single-side contribution.
    """
    arr = np.asarray(profile, dtype=float)
    if mode == "heating":
        one_sided = np.where(arr < 0, arr, 0.0)
        q_h = float(one_sided.min())
        q_m = float(_monthly_averages(one_sided).min())
    else:
        one_sided = np.where(arr > 0, arr, 0.0)
        q_h = float(one_sided.max())
        q_m = float(_monthly_averages(one_sided).max())
    # q_y = net annual average (Philippe 2010): full profile mean, NOT one-sided mean.
    # Using one-sided.mean() would give ~120% error and wrong sign for non-dominant mode.
    q_y = float(arr.mean())
    return q_h, q_m, q_y

import numpy as np

_MONTH_HOURS = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]


def _monthly_averages(arr: np.ndarray) -> np.ndarray:
    avgs = np.empty(12)
    idx = 0
    for m, hours in enumerate(_MONTH_HOURS):
        avgs[m] = arr[idx: idx + hours].mean()
        idx += hours
    return avgs


def compute_ldc(profile: list, cutoff_pct: float) -> dict:
    arr = np.asarray(profile, dtype=float)
    sorted_abs = np.sort(np.abs(arr))[::-1]
    cutoff_idx = int(len(arr) * cutoff_pct / 100)
    cutoff_W = float(sorted_abs[cutoff_idx]) if cutoff_idx < len(sorted_abs) else 0.0
    return {
        "cutoff_idx": cutoff_idx,
        "cutoff_W": cutoff_W,
        "sorted_abs": sorted_abs.tolist(),
    }


def trim_profile(profile: list, cutoff_W: float, dominant_mode: str) -> list:
    result = []
    for h in profile:
        if dominant_mode == "heating":
            result.append(max(h, -cutoff_W) if h < 0 else h)
        elif dominant_mode == "cooling":
            result.append(min(h, cutoff_W) if h > 0 else h)
        else:
            result.append(max(-cutoff_W, min(cutoff_W, h)))
    return result


def extract_one_sided_pulses(profile: list, mode: str) -> tuple:
    arr = np.asarray(profile, dtype=float)
    if mode == "heating":
        one_sided = np.where(arr < 0, arr, 0.0)
        q_h = float(one_sided.min())
        q_m = float(_monthly_averages(one_sided).min())
    else:
        one_sided = np.where(arr > 0, arr, 0.0)
        q_h = float(one_sided.max())
        q_m = float(_monthly_averages(one_sided).max())
    q_y = float(one_sided.mean())
    return q_h, q_m, q_y


def rederive_three_pulse(trimmed: list) -> tuple:
    arr = np.asarray(trimmed, dtype=float)
    heat_energy = float(np.where(arr < 0, -arr, 0).sum())
    cool_energy = float(np.where(arr > 0, arr, 0).sum())
    heating_dominant = heat_energy >= cool_energy
    monthly_avgs = _monthly_averages(arr)
    q_h = float(arr.min() if heating_dominant else arr.max())
    q_m = float(monthly_avgs.min() if heating_dominant else monthly_avgs.max())
    q_y = float(arr.mean())
    return q_h, q_m, q_y

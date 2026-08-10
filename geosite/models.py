"""Shared data models for the s1–s3 pipeline."""

from dataclasses import dataclass


@dataclass
class SiteData:
    """Soil and climate properties for a census tract location."""
    geoid: str           # 11-digit census tract GEOID, e.g. "17031010200"
    k: float             # soil thermal conductivity [W/m·K]
    alpha: float         # soil thermal diffusivity [m²/day]
    T_g: float           # undisturbed ground temperature [°C]
    climate_zone: str    # ASHRAE climate zone, e.g. "5A"
    data_available: bool # False when no SSURGO data exists for this tract
    state_abbrev: str = ""  # 2-letter state abbreviation from deep_thermal_by_county.csv
    # Soil-class-aware fields (populated when deep_thermal_by_county.csv is available)
    rock_class: str = ""          # SGMC dominant rock class at depth
    k_min: float = float("nan")   # Clauser-Huenges lower bound for rock class [W/m·K]
    k_max: float = float("nan")   # Clauser-Huenges upper bound for rock class [W/m·K]
    shallow_soil_class: str = ""  # SSURGO Côté-Konrad soil class (0–2 m)
    k_shallow: float = float("nan")  # Côté-Konrad k at field saturation [W/m·K]


@dataclass
class LoadPulses:
    """Three-pulse ground loads for ASHRAE borefield sizing (Philippe et al. 2010).

    Sign convention (same as s4_sizing.size_borefield):
        negative → heat extraction from ground (heating mode)
        positive → heat injection into ground  (cooling mode)

    q_h / q_m / q_y are the dominant-mode peaks (backward-compatible).
    The four _heat / _cool fields support the rigorous two-pass sizing check:
    size for both modes independently, take the larger result.
    """
    q_h: float   # peak hourly ground load [W] — dominant mode
    q_m: float   # peak monthly average ground load [W] — dominant mode
    q_y: float   # annual average ground load [W] (positive = net cooling)
    # Both-mode peaks for two-pass sizing (nan when not available)
    q_h_heat: float = float("nan")   # peak heating extraction hour [W] (≤ 0)
    q_m_heat: float = float("nan")   # worst heating month average [W] (≤ 0)
    q_h_cool: float = float("nan")   # peak cooling injection hour [W] (≥ 0)
    q_m_cool: float = float("nan")   # worst cooling month average [W] (≥ 0)

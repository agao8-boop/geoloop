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


@dataclass
class LoadPulses:
    """Three-pulse ground loads for ASHRAE borefield sizing (Philippe et al. 2010).

    Sign convention (same as s4_sizing.size_borefield):
        negative → heat extraction from ground (heating mode)
        positive → heat injection into ground  (cooling mode)
    """
    q_h: float   # peak hourly ground load [W]
    q_m: float   # peak monthly average ground load [W]
    q_y: float   # annual average ground load [W]

"""s6_strategy: mandatory hybrid GSHP peak-shaving analysis.

Sizes supplemental peaker (electric heater or chiller) via Load Duration Curve,
trims borefield accordingly, and computes before/after cost comparison.
"""
from geosite.s6_strategy.strategy import run_strategy

__all__ = ["run_strategy"]

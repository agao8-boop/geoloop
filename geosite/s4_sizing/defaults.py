"""Canonical engineering defaults for borehole/system advanced parameters.

Single source of truth shared by app.py (smart/stage2 endpoints) and
geosite.s6_strategy.strategy — previously duplicated in both.
"""

ADVANCED_DEFAULTS = {
    "Cp":     4200.0,
    "mfls":   0.05,
    "rbore":  0.06,
    "rpin":   0.01365,
    "rpext":  0.0167,
    "kgrout": 1.5,
    "kpipe":  0.42,
    "LU":     0.0511,
    "hconv":  1000.0,
}

T_IN_HP_DEFAULTS = {"heating": 5.0, "cooling": 40.2}

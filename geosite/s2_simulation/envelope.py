"""Building-design load modifiers: WWR, envelope tightness, glazing type.

Structure-only placeholder: every factor is 1.0 until calibrated multipliers
arrive from the professor (input spreadsheet review, 2026-07-13). When they
do, ONLY the three dicts below change — no wiring code moves.

The combined factor scales the prototype heating/cooling loads (q_h, q_m,
q_y and the 8760h strategy profile) as a single scalar, the same mechanism
as the construction-year factor.
"""

WWR_FACTORS = {          # window-to-wall ratio
    "low":    1.0,       # <= 20%
    "medium": 1.0,       # 30-40% (DOE prototype baseline)
    "high":   1.0,       # >= 50%
}

ENVELOPE_FACTORS = {     # insulation + air sealing
    "high":     1.0,     # high performance
    "standard": 1.0,     # code baseline
    "low":      1.0,     # low performance / leaky
}

GLAZING_FACTORS = {      # glass quality
    "triple": 1.0,
    "double": 1.0,       # standard
    "single": 1.0,
}

WWR_OPTIONS = frozenset(WWR_FACTORS)
ENVELOPE_OPTIONS = frozenset(ENVELOPE_FACTORS)
GLAZING_OPTIONS = frozenset(GLAZING_FACTORS)


def compute_envelope_factor(
    wwr: str = "medium",
    envelope: str = "standard",
    glazing: str = "double",
) -> float:
    """Combined load multiplier for the selected building-design options."""
    if wwr not in WWR_FACTORS:
        raise ValueError(f"wwr must be one of {sorted(WWR_FACTORS)}, got '{wwr}'")
    if envelope not in ENVELOPE_FACTORS:
        raise ValueError(f"envelope must be one of {sorted(ENVELOPE_FACTORS)}, got '{envelope}'")
    if glazing not in GLAZING_FACTORS:
        raise ValueError(f"glazing must be one of {sorted(GLAZING_FACTORS)}, got '{glazing}'")
    return WWR_FACTORS[wwr] * ENVELOPE_FACTORS[envelope] * GLAZING_FACTORS[glazing]

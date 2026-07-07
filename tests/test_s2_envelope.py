"""Building-design load modifiers. All factors are 1.0 until the professor
supplies calibrated values (input spreadsheet review, 2026-07-13)."""

import itertools
import pytest

from geosite.s2_simulation.envelope import (
    WWR_FACTORS,
    ENVELOPE_FACTORS,
    GLAZING_FACTORS,
    compute_envelope_factor,
)


def test_option_sets_pinned():
    assert set(WWR_FACTORS) == {"low", "medium", "high"}
    assert set(ENVELOPE_FACTORS) == {"high", "standard", "low"}
    assert set(GLAZING_FACTORS) == {"triple", "double", "single"}


def test_all_factors_are_neutral_for_now():
    for combo in itertools.product(WWR_FACTORS, ENVELOPE_FACTORS, GLAZING_FACTORS):
        assert compute_envelope_factor(*combo) == 1.0


def test_defaults_are_medium_standard_double():
    assert compute_envelope_factor() == 1.0
    assert compute_envelope_factor("medium", "standard", "double") == 1.0


def test_unknown_option_raises_with_param_name():
    with pytest.raises(ValueError, match="wwr"):
        compute_envelope_factor(wwr="huge")
    with pytest.raises(ValueError, match="envelope"):
        compute_envelope_factor(envelope="passivhaus")
    with pytest.raises(ValueError, match="glazing"):
        compute_envelope_factor(glazing="quad")

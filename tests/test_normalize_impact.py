"""
Additional tests for impact normalisation and provider mapping.
"""

import pytest
from events.services import normalize_impact
from events.models import ImpactLevel


@pytest.mark.parametrize("raw,expected", [
    # Trading Economics values
    ("3", ImpactLevel.HIGH),
    ("2", ImpactLevel.MEDIUM),
    ("1", ImpactLevel.LOW),
    # Text values
    ("High", ImpactLevel.HIGH),
    ("HIGH", ImpactLevel.HIGH),
    ("high", ImpactLevel.HIGH),
    ("Medium", ImpactLevel.MEDIUM),
    ("Low", ImpactLevel.LOW),
    # Colour values
    ("red", ImpactLevel.HIGH),
    ("RED", ImpactLevel.HIGH),
    ("orange", ImpactLevel.MEDIUM),
    ("yellow", ImpactLevel.LOW),
    # Edge cases
    (None, ImpactLevel.UNKNOWN),
    ("", ImpactLevel.UNKNOWN),
    ("  ", ImpactLevel.UNKNOWN),
    ("unknown", ImpactLevel.UNKNOWN),
    ("purple", ImpactLevel.UNKNOWN),
    (999, ImpactLevel.UNKNOWN),
    (0, ImpactLevel.UNKNOWN),
])
def test_normalize_impact_parametrized(raw, expected):
    assert normalize_impact(raw) == expected

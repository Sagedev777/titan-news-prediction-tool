"""
Tests for the red-folder filter policy.

Proves that:
1. MEDIUM events are rejected.
2. LOW events are rejected.
3. UNKNOWN events are rejected.
4. Non-allowlisted HIGH events are rejected.
5. Allowlisted HIGH-impact events are accepted.
6. assert_red_folder raises for non-red events.
7. normalize_impact maps provider strings correctly.
8. is_red_folder is the single source of truth.
"""

import pytest
from unittest.mock import MagicMock

from events.models import (
    ALLOWLISTED_EVENT_CODES,
    EconomicEvent,
    ImpactLevel,
)
from events.services import (
    assert_red_folder,
    is_red_folder,
    normalize_impact,
)


# ── Helper factory ────────────────────────────────────────────────────────────

def make_event(
    code: str,
    normalized_impact: str,
    is_allowlisted: bool = None,
) -> EconomicEvent:
    """Create an in-memory EconomicEvent (not saved to DB)."""
    event = EconomicEvent.__new__(EconomicEvent)
    event.code = code
    event.normalized_impact_level = normalized_impact
    # is_allowlisted is normally set by model.save() but we set it manually here
    if is_allowlisted is None:
        event.is_allowlisted = code in ALLOWLISTED_EVENT_CODES
    else:
        event.is_allowlisted = is_allowlisted
    return event


# ── normalize_impact tests ────────────────────────────────────────────────────

class TestNormalizeImpact:
    def test_high_strings(self):
        for val in ("3", "high", "HIGH", "red", "RED"):
            assert normalize_impact(val) == ImpactLevel.HIGH, f"Failed for {val!r}"

    def test_medium_strings(self):
        for val in ("2", "medium", "MEDIUM", "orange"):
            assert normalize_impact(val) == ImpactLevel.MEDIUM, f"Failed for {val!r}"

    def test_low_strings(self):
        for val in ("1", "low", "LOW", "yellow"):
            assert normalize_impact(val) == ImpactLevel.LOW, f"Failed for {val!r}"

    def test_unknown_for_none(self):
        assert normalize_impact(None) == ImpactLevel.UNKNOWN

    def test_unknown_for_garbage(self):
        assert normalize_impact("purple") == ImpactLevel.UNKNOWN

    def test_unknown_for_empty(self):
        assert normalize_impact("") == ImpactLevel.UNKNOWN


# ── is_red_folder tests ───────────────────────────────────────────────────────

class TestIsRedFolder:
    """
    Core red-folder gate tests.
    These prove the filter works correctly at every impact level.
    """

    def test_high_allowlisted_is_red_folder(self):
        """An allowlisted HIGH event must pass the gate."""
        event = make_event("US_CPI", ImpactLevel.HIGH, is_allowlisted=True)
        assert is_red_folder(event) is True

    def test_high_not_allowlisted_is_rejected(self):
        """A HIGH impact event that is not allowlisted must be rejected."""
        event = make_event("SOME_UNKNOWN_HIGH_EVENT", ImpactLevel.HIGH, is_allowlisted=False)
        assert is_red_folder(event) is False

    def test_medium_event_is_rejected(self):
        """MEDIUM impact events must never enter the pipeline."""
        event = make_event("US_CPI", ImpactLevel.MEDIUM, is_allowlisted=True)
        assert is_red_folder(event) is False

    def test_low_event_is_rejected(self):
        """LOW impact events must never enter the pipeline."""
        event = make_event("US_CPI", ImpactLevel.LOW, is_allowlisted=True)
        assert is_red_folder(event) is False

    def test_unknown_event_is_rejected(self):
        """UNKNOWN impact events must never enter the pipeline."""
        event = make_event("US_CPI", ImpactLevel.UNKNOWN, is_allowlisted=True)
        assert is_red_folder(event) is False

    def test_medium_high_allowlisted_combination_rejected(self):
        """Medium impact + allowlisted = still rejected."""
        event = make_event("US_NFP", ImpactLevel.MEDIUM, is_allowlisted=True)
        assert is_red_folder(event) is False

    def test_all_allowlisted_codes_have_correct_type(self):
        """All codes in ALLOWLISTED_EVENT_CODES must be strings."""
        for code in ALLOWLISTED_EVENT_CODES:
            assert isinstance(code, str), f"Code {code!r} is not a string"
            assert len(code) > 0, f"Empty code found in ALLOWLISTED_EVENT_CODES"

    def test_non_allowlisted_high_various_codes(self):
        """Various non-allowlisted HIGH events must be rejected."""
        fake_codes = [
            "RANDOM_HIGH_EVENT",
            "UNLISTED_US_SPEECH",
            "UNMAPPED__UNITED_STATES__RANDOM_DATA",
        ]
        for code in fake_codes:
            event = make_event(code, ImpactLevel.HIGH, is_allowlisted=False)
            assert is_red_folder(event) is False, f"Expected rejection for {code!r}"


# ── assert_red_folder tests ───────────────────────────────────────────────────

class TestAssertRedFolder:
    def test_raises_for_medium(self):
        event = make_event("US_CPI", ImpactLevel.MEDIUM, is_allowlisted=True)
        with pytest.raises(ValueError, match="not a red-folder event"):
            assert_red_folder(event)

    def test_raises_for_low(self):
        event = make_event("US_CPI", ImpactLevel.LOW, is_allowlisted=False)
        with pytest.raises(ValueError):
            assert_red_folder(event)

    def test_raises_for_unknown(self):
        event = make_event("US_CPI", ImpactLevel.UNKNOWN, is_allowlisted=True)
        with pytest.raises(ValueError):
            assert_red_folder(event)

    def test_raises_for_high_not_allowlisted(self):
        event = make_event("MYSTERY_EVENT", ImpactLevel.HIGH, is_allowlisted=False)
        with pytest.raises(ValueError, match="not a red-folder event"):
            assert_red_folder(event)

    def test_does_not_raise_for_valid_red_folder(self):
        event = make_event("US_NFP", ImpactLevel.HIGH, is_allowlisted=True)
        # Should not raise
        assert_red_folder(event)


# ── ALLOWLISTED_EVENT_CODES coverage ─────────────────────────────────────────

class TestAllowlistedCodes:
    def test_known_codes_are_in_registry(self):
        """Key event codes from the specification must be in the registry."""
        required = [
            "US_CPI", "US_CORE_CPI", "US_NFP", "US_UNEMPLOYMENT_RATE",
            "US_FOMC_RATE_DECISION", "US_GDP", "US_PPI", "US_RETAIL_SALES",
            "EUROZONE_CPI", "ECB_RATE_DECISION",
            "UK_CPI", "BOE_RATE_DECISION",
            "CANADA_CPI", "BOC_RATE_DECISION",
            "AUSTRALIA_CPI", "RBA_RATE_DECISION",
            "NEW_ZEALAND_CPI", "RBNZ_RATE_DECISION",
            "JAPAN_CPI", "BOJ_RATE_DECISION",
        ]
        for code in required:
            assert code in ALLOWLISTED_EVENT_CODES, (
                f"{code!r} is missing from ALLOWLISTED_EVENT_CODES"
            )

    def test_no_orange_yellow_medium_in_allowlist(self):
        """No medium/low keywords should appear in allowlisted codes."""
        for code in ALLOWLISTED_EVENT_CODES:
            lower = code.lower()
            assert "medium" not in lower, f"'medium' found in allowlisted code {code!r}"
            assert "low" not in lower, f"'low' found in allowlisted code {code!r}"
            assert "orange" not in lower, f"'orange' found in allowlisted code {code!r}"
            assert "yellow" not in lower, f"'yellow' found in allowlisted code {code!r}"


# ── EconomicEvent.is_red_folder property ─────────────────────────────────────

class TestEventModelProperty:
    def test_is_red_folder_property_consistent_with_service(self):
        """EconomicEvent.is_red_folder property must agree with is_red_folder()."""
        test_cases = [
            ("US_CPI", ImpactLevel.HIGH, True),
            ("US_NFP", ImpactLevel.HIGH, True),
            ("UNKNOWN_EVENT", ImpactLevel.HIGH, False),
            ("US_CPI", ImpactLevel.MEDIUM, True),    # allowlisted but medium = not red
            ("US_CPI", ImpactLevel.LOW, True),
            ("US_CPI", ImpactLevel.UNKNOWN, True),
        ]

        for code, impact, allowlisted in test_cases:
            event = make_event(code, impact, is_allowlisted=allowlisted)
            prop_result = event.is_red_folder
            service_result = is_red_folder(event)
            assert prop_result == service_result, (
                f"Mismatch for {code} impact={impact} allowlisted={allowlisted}: "
                f"property={prop_result}, service={service_result}"
            )

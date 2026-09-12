"""Unit tests for code/evidence/confidence.py."""

from decimal import Decimal

import pytest

from evidence.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_MIN,
    CONFIDENCE_UNTRUSTED,
    validate_confidence,
)


def test_validate_confidence_valid():
    assert validate_confidence(Decimal("0.95")) == Decimal("0.95")
    assert validate_confidence(Decimal("0.0")) == Decimal("0.0")
    assert validate_confidence(Decimal("1.0")) == Decimal("1.0")
    assert validate_confidence("0.75") == Decimal("0.75")
    assert validate_confidence(0.5) == Decimal("0.5")


def test_validate_confidence_invalid():
    with pytest.raises(ValueError, match="out of bounds"):
        validate_confidence(Decimal("-0.1"))

    with pytest.raises(ValueError, match="out of bounds"):
        validate_confidence(Decimal("1.05"))

    with pytest.raises(ValueError, match="cannot be None"):
        validate_confidence(None)

    with pytest.raises(ValueError, match="cannot parse"):
        validate_confidence("not-a-number")

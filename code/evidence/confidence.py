"""Confidence model and bounding rules for Phase 3 evidence."""

from decimal import Decimal
from typing import Any

# Standard confidence levels
CONFIDENCE_MAX = Decimal("1.00")
CONFIDENCE_HIGH = Decimal("0.95")
CONFIDENCE_MEDIUM = Decimal("0.70")
CONFIDENCE_LOW = Decimal("0.30")
CONFIDENCE_UNTRUSTED = Decimal("0.10")
CONFIDENCE_MIN = Decimal("0.00")


def validate_confidence(confidence: Any) -> Decimal:
    """Validate that confidence is a Decimal bounded between 0.0 and 1.0.

    Raises:
        ValueError: If confidence is outside [0.0, 1.0] or cannot be parsed to Decimal.
    """
    if confidence is None:
        raise ValueError("Confidence cannot be None")

    if not isinstance(confidence, Decimal):
        try:
            conf_dec = Decimal(str(confidence))
        except Exception as exc:
            raise ValueError(f"Invalid confidence value '{confidence}': cannot parse to Decimal") from exc
    else:
        conf_dec = confidence

    if conf_dec < CONFIDENCE_MIN or conf_dec > CONFIDENCE_MAX:
        raise ValueError(f"Confidence {conf_dec} is out of bounds [0.0, 1.0]")

    return conf_dec

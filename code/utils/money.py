"""Monetary utilities ensuring exact Decimal precision and strict null handling."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def parse_money(val: Any) -> Decimal | None:
    """Parse a monetary value to Decimal, strictly preserving missing/null values.
    
    Returns None if val is None, pd.NA, np.nan, or empty string.
    Raises ValueError on invalid numeric formats.
    """
    if val is None:
        return None

    # Handle pandas/numpy NA / NaN
    if str(val).strip() in ("", "nan", "NaN", "None", "<NA>"):
        return None

    if isinstance(val, Decimal):
        return val

    # If int or float, convert cleanly via str to avoid float binary inaccuracy
    try:
        cleaned_str = str(val).strip().replace(",", "")
        if not cleaned_str:
            return None
        return Decimal(cleaned_str)
    except (InvalidOperation, ValueError) as err:
        raise ValueError(f"Cannot parse '{val}' into a valid monetary Decimal") from err


def quantize_money(amount: Decimal | None, decimals: int = 2) -> Decimal | None:
    """Safely round/quantize a Decimal amount to specified decimal places.
    
    Preserves None.
    """
    if amount is None:
        return None
    if decimals == 0:
        exp = Decimal("1")
    else:
        exp = Decimal(f"1e-{decimals}")
    return amount.quantize(exp, rounding=ROUND_HALF_UP)


def is_safe_amount(amount: Decimal | None) -> bool:
    """Check if a monetary amount is valid, non-null, and non-negative."""
    if amount is None:
        return False
    return amount >= Decimal("0")


def money_to_str(amount: Decimal | None, decimals: int | None = None) -> str:
    """Format a monetary Decimal to string, or empty string if None."""
    if amount is None:
        return ""
    if decimals is not None:
        return str(quantize_money(amount, decimals))
    return str(amount)

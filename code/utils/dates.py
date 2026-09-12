"""Deterministic date and datetime utilities for the BUYorNOT challenge."""

from datetime import date, datetime, timedelta
from typing import Any


def parse_date(val: Any) -> date | None:
    """Parse a date string formatted as YYYY-MM-DD into a datetime.date object.
    
    Returns None if val is empty or None.
    Raises ValueError on malformed date string.
    """
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    
    s = str(val).strip()
    if not s or s in ("nan", "NaN", "None", "<NA>"):
        return None
    
    # In case an ISO timestamp with time is passed
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    
    return date.fromisoformat(s)


def parse_datetime(val: Any) -> datetime | None:
    """Parse an ISO timestamp (e.g. '2025-07-29T09:30:00Z') into a datetime object.
    
    Returns None if val is empty or None.
    Raises ValueError on malformed string.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    
    s = str(val).strip()
    if not s or s in ("nan", "NaN", "None", "<NA>"):
        return None
    
    # Handle Zulu 'Z' suffix
    clean = s.replace("Z", "+00:00")
    return datetime.fromisoformat(clean)


def format_date(d: date | None) -> str:
    """Format a date into YYYY-MM-DD string, or empty string if None."""
    if d is None:
        return ""
    return d.isoformat()


def add_days(d: date, days: int) -> date:
    """Add a number of days to a date."""
    return d + timedelta(days=days)


def days_between(start_date: date, end_date: date) -> int:
    """Calculate the number of days between two dates (end_date - start_date)."""
    return (end_date - start_date).days


def date_range(start_date: date, end_date: date) -> list[date]:
    """Generate a list of dates from start_date to end_date (inclusive)."""
    if start_date > end_date:
        return []
    total_days = (end_date - start_date).days + 1
    return [start_date + timedelta(days=i) for i in range(total_days)]


def is_on_or_before(d1: date, d2: date) -> bool:
    """Check if d1 is chronologically on or before d2."""
    return d1 <= d2


def is_on_or_after(d1: date, d2: date) -> bool:
    """Check if d1 is chronologically on or after d2."""
    return d1 >= d2

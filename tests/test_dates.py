"""Unit tests for code/utils/dates.py."""

from datetime import date, datetime, timezone
import pytest

from utils.dates import (
    add_days,
    date_range,
    days_between,
    format_date,
    is_on_or_after,
    is_on_or_before,
    parse_date,
    parse_datetime,
)


def test_parse_valid_dates():
    assert parse_date("2024-03-03") == date(2024, 3, 3)
    assert parse_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert parse_date("2025-07-29T09:30:00Z") == date(2025, 7, 29)


def test_parse_missing_dates():
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("nan") is None
    assert parse_date("NaN") is None


def test_parse_invalid_dates():
    with pytest.raises(ValueError):
        parse_date("2024-02-30")
    with pytest.raises(ValueError):
        parse_date("invalid-date")


def test_parse_datetime_iso():
    dt = parse_datetime("2025-07-29T09:30:00Z")
    assert dt == datetime(2025, 7, 29, 9, 30, 0, tzinfo=timezone.utc)
    assert parse_datetime(None) is None


def test_date_arithmetic():
    d = date(2024, 2, 28)
    # Leap year 2024
    assert add_days(d, 1) == date(2024, 2, 29)
    assert add_days(d, 2) == date(2024, 3, 1)
    assert days_between(date(2024, 2, 28), date(2024, 3, 1)) == 2


def test_date_range():
    start = date(2024, 1, 1)
    end = date(2024, 1, 3)
    rng = date_range(start, end)
    assert rng == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    assert date_range(date(2024, 1, 2), date(2024, 1, 1)) == []


def test_date_comparisons():
    d1 = date(2024, 1, 1)
    d2 = date(2024, 1, 10)
    assert is_on_or_before(d1, d2) is True
    assert is_on_or_before(d2, d1) is False
    assert is_on_or_before(d1, d1) is True
    assert is_on_or_after(d2, d1) is True


def test_format_date():
    assert format_date(date(2024, 5, 12)) == "2024-05-12"
    assert format_date(None) == ""

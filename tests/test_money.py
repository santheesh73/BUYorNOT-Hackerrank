"""Unit tests for code/utils/money.py."""

from decimal import Decimal
import pytest

from utils.money import (
    is_safe_amount,
    money_to_str,
    parse_money,
    quantize_money,
)


def test_parse_money_valid_numeric_strings():
    assert parse_money("100") == Decimal("100")
    assert parse_money("1234.56") == Decimal("1234.56")
    assert parse_money("1,234.56") == Decimal("1234.56")
    assert parse_money(500) == Decimal("500")
    assert parse_money(Decimal("42.99")) == Decimal("42.99")


def test_parse_money_missing_and_null_values():
    assert parse_money(None) is None
    assert parse_money("") is None
    assert parse_money("   ") is None
    assert parse_money("nan") is None
    assert parse_money("NaN") is None
    assert parse_money("None") is None
    assert parse_money("<NA>") is None


def test_parse_money_preserves_precision():
    # Large numbers in IDR
    val = "60383889.2"
    parsed = parse_money(val)
    assert parsed == Decimal("60383889.2")
    assert str(parsed) == "60383889.2"

    small = "0.0001"
    assert parse_money(small) == Decimal("0.0001")


def test_parse_money_invalid_values():
    with pytest.raises(ValueError):
        parse_money("not_a_number")

    with pytest.raises(ValueError):
        parse_money("12.34.56")


def test_quantize_money():
    amt = Decimal("123.4567")
    assert quantize_money(amt, 2) == Decimal("123.46")
    assert quantize_money(amt, 0) == Decimal("123")
    assert quantize_money(None) is None


def test_is_safe_amount():
    assert is_safe_amount(Decimal("0")) is True
    assert is_safe_amount(Decimal("100.50")) is True
    assert is_safe_amount(Decimal("-1")) is False
    assert is_safe_amount(None) is False


def test_money_to_str():
    assert money_to_str(Decimal("10.5"), decimals=2) == "10.50"
    assert money_to_str(Decimal("10.5")) == "10.5"
    assert money_to_str(None) == ""

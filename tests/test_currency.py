"""Unit tests for code/finance/currency.py."""

from datetime import date
from decimal import Decimal
import pytest

from finance.currency import (
    CurrencyConverter,
    ExchangeRateNotFoundError,
    get_exchange_rate,
)


@pytest.fixture
def converter():
    return CurrencyConverter()


def test_convert_same_currency(converter):
    amt = Decimal("123.456")
    res = converter.convert(amt, "USD", "USD", Decimal("1.0"))
    assert res == amt


def test_convert_foreign_currency(converter):
    amt = Decimal("100")
    rate = Decimal("0.92")
    res = converter.convert(amt, "USD", "EUR", rate)
    assert res == Decimal("92.00")

    # High precision Decimal
    amt_zar = Decimal("2500.50")
    rate_zar = Decimal("18.4523")
    res_zar = converter.convert(amt_zar, "EUR", "ZAR", rate_zar)
    assert res_zar == Decimal("46139.98")


def test_get_exchange_rate_same_currency():
    rate = get_exchange_rate({}, date(2025, 1, 1), "USD", "USD")
    assert rate == Decimal("1.0")


def test_get_exchange_rate_from_dict():
    rates = {
        (date(2025, 1, 1), "USD", "EUR"): Decimal("0.92"),
    }
    rate = get_exchange_rate(rates, date(2025, 1, 1), "USD", "EUR")
    assert rate == Decimal("0.92")


def test_get_exchange_rate_missing_raises_error():
    rates = {
        (date(2025, 1, 1), "USD", "EUR"): Decimal("0.92"),
    }
    with pytest.raises(ExchangeRateNotFoundError):
        get_exchange_rate(rates, date(2025, 1, 2), "USD", "EUR")

    with pytest.raises(ExchangeRateNotFoundError):
        get_exchange_rate(rates, date(2025, 1, 1), "EUR", "USD")

"""Currency conversion and exchange-rate lookup utilities for BUYorNOT."""

from datetime import date
from decimal import Decimal
from typing import Any

from utils.money import quantize_money


class ExchangeRateNotFoundError(ValueError):
    """Raised when a required fixed exchange rate is not present in the dataset."""
    pass


class CurrencyConverter:
    """Deterministic, Decimal-based currency converter."""

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
    ) -> Decimal:
        """Convert an amount from one currency to another using the exact fixed rate."""
        if from_currency == to_currency:
            return amount
        if amount is None:
            raise ValueError("Cannot convert None amount")

        converted = amount * rate
        return quantize_money(converted, decimals=2)


def get_exchange_rate(
    rate_table: Any,
    rate_date: date,
    from_currency: str,
    to_currency: str,
) -> Decimal:
    """Retrieve the fixed exchange rate for a given date and currency pair.
    
    Raises ExchangeRateNotFoundError if no matching conversion rate is available.
    """
    if from_currency == to_currency:
        return Decimal("1.0")

    rate: Decimal | None = None

    # Handle DataStore or object with get_exchange_rate method
    if hasattr(rate_table, "get_exchange_rate"):
        rate = rate_table.get_exchange_rate(rate_date, from_currency, to_currency)
    # Handle dictionary mapping (rate_date, from_currency, to_currency) -> rate
    elif isinstance(rate_table, dict):
        rate = rate_table.get((rate_date, from_currency, to_currency))
        if rate is None and hasattr(rate_table, "exchange_rates_by_pair"):
            rate = rate_table.exchange_rates_by_pair.get((rate_date, from_currency, to_currency))

    if rate is None:
        raise ExchangeRateNotFoundError(
            f"Exchange rate not found for {from_currency} -> {to_currency} on {rate_date}"
        )

    return rate

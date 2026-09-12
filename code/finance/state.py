"""FinancialState and RecurringPattern models for Phase 4."""

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd


@dataclass(frozen=True)
class FinancialState:
    """Represents the daily or event-based financial state of a user.

    Invariants:
        inflows >= 0
        outflows >= 0
        net_cash_flow == inflows - outflows
        closing_balance == opening_balance + net_cash_flow
    """

    dt: pd.Timestamp
    opening_balance: Decimal
    inflows: Decimal
    outflows: Decimal
    net_cash_flow: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class RecurringPattern:
    """Represents an inferred recurring cash-flow pattern supported by historical events."""

    pattern_id: str
    category: str
    direction: str  # "credit" | "debit"
    amount: Decimal
    interval_days: int
    next_occurrence: pd.Timestamp
    source_event_ids: tuple[str, ...]

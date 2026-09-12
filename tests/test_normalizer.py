"""Unit tests for code/finance/normalizer.py."""

from datetime import date
from decimal import Decimal
import pytest

from data.models import FinancialEvent
from finance.normalizer import FinancialEventNormalizer, NormalizedFinancialEvent


@pytest.fixture
def normalizer():
    return FinancialEventNormalizer()


def test_normalizer_settled_expense(normalizer):
    raw = FinancialEvent(
        event_id="ev_01",
        user_id="usr_01",
        event_type="expense",
        description="Grocery shopping",
        category="groceries",
        direction="debit",
        amount=Decimal("150.75"),
        currency="USD",
        event_date=date(2025, 3, 1),
        settlement_date=date(2025, 3, 2),
        status="settled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    norm = normalizer.normalize(raw, home_currency="USD")

    assert norm.event_id == "ev_01"
    assert norm.user_id == "usr_01"
    assert norm.original_amount == Decimal("150.75")
    assert norm.home_currency_amount == Decimal("150.75")
    assert norm.effective_date == date(2025, 3, 2)
    assert norm.is_cash_flow is True
    assert norm.is_expense is True
    assert norm.is_income is False
    assert norm.is_transfer is False
    assert norm.is_pending is False
    assert norm.is_failed is False
    assert norm.is_cancelled is False
    assert norm.source_event_ids == ("ev_01",)


def test_normalizer_pending_credit_ignored_initially(normalizer):
    raw = FinancialEvent(
        event_id="ev_02",
        user_id="usr_01",
        event_type="refund",
        description="Pending merchant refund",
        category="shopping",
        direction="credit",
        amount=Decimal("50.00"),
        currency="USD",
        event_date=date(2025, 3, 10),
        settlement_date=date(2025, 3, 20),
        status="pending",
        linked_event_id="ev_01",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    norm = normalizer.normalize(raw, home_currency="USD")

    assert norm.is_pending is True
    # Pending credit is not counted until settled
    assert norm.is_cash_flow is False
    assert norm.is_transfer is True


def test_normalizer_missing_amount_preserved(normalizer):
    raw = FinancialEvent(
        event_id="ev_03",
        user_id="usr_02",
        event_type="income",
        description="Payroll credit",
        category="salary",
        direction="credit",
        amount=None,  # Missing amount to be extracted from image
        currency="IDR",
        event_date=date(2025, 8, 15),
        settlement_date=date(2025, 8, 15),
        status="scheduled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    norm = normalizer.normalize(raw, home_currency="IDR")

    assert norm.original_amount is None
    assert norm.home_currency_amount is None
    assert norm.is_income is True
    assert norm.is_cash_flow is True


def test_normalizer_failed_and_cancelled(normalizer):
    cancelled_ev = FinancialEvent(
        event_id="ev_04",
        user_id="usr_01",
        event_type="expense",
        description="Card auth",
        category="shopping",
        direction="debit",
        amount=Decimal("100"),
        currency="USD",
        event_date=date(2025, 1, 1),
        settlement_date=None,
        status="cancelled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    norm_c = normalizer.normalize(cancelled_ev, home_currency="USD")
    assert norm_c.is_cancelled is True
    assert norm_c.is_cash_flow is False

    failed_ev = FinancialEvent(
        event_id="ev_05",
        user_id="usr_01",
        event_type="debt_payment",
        description="Failed payment",
        category="debt_repayment",
        direction="debit",
        amount=Decimal("200"),
        currency="USD",
        event_date=date(2025, 1, 2),
        settlement_date=None,
        status="failed",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    norm_f = normalizer.normalize(failed_ev, home_currency="USD")
    assert norm_f.is_failed is True
    assert norm_f.is_cash_flow is False

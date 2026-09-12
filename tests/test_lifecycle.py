"""Unit tests for code/finance/lifecycle.py."""

from datetime import date
from decimal import Decimal
import pytest

from data.models import FinancialEvent
from finance.lifecycle import EventLifecycleResolver, ResolvedLifecycle


@pytest.fixture
def resolver():
    return EventLifecycleResolver()


def test_single_event_lifecycle(resolver):
    ev = FinancialEvent(
        event_id="ev_10",
        user_id="usr_01",
        event_type="expense",
        description="Utility bill",
        category="utilities",
        direction="debit",
        amount=Decimal("85.50"),
        currency="USD",
        event_date=date(2025, 4, 1),
        settlement_date=date(2025, 4, 1),
        status="settled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    lifecycles = resolver.resolve([ev])
    assert len(lifecycles) == 1
    lc = lifecycles[0]
    assert lc.lifecycle_id == "lc_ev_10"
    assert lc.source_event_ids == ("ev_10",)
    assert lc.effective_event_ids == ("ev_10",)
    assert lc.status == "settled"


def test_duplicate_charge_suppression(resolver):
    parent = FinancialEvent(
        event_id="ev_orig",
        user_id="usr_01",
        event_type="expense",
        description="Original card charge",
        category="shopping",
        direction="debit",
        amount=Decimal("134.75"),
        currency="USD",
        event_date=date(2026, 3, 26),
        settlement_date=date(2026, 3, 27),
        status="settled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    child = FinancialEvent(
        event_id="ev_dup",
        user_id="usr_01",
        event_type="expense",
        description="Possible duplicate card charge",
        category="shopping",
        direction="debit",
        amount=Decimal("134.75"),
        currency="USD",
        event_date=date(2026, 4, 6),
        settlement_date=date(2026, 4, 10),
        status="pending",
        linked_event_id="ev_orig",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lifecycles = resolver.resolve([parent, child])
    assert len(lifecycles) == 1
    lc = lifecycles[0]
    assert lc.status == "duplicate_suppressed"
    assert lc.source_event_ids == ("ev_orig", "ev_dup")
    # Duplicate child is excluded from effective cash flows
    assert lc.effective_event_ids == ("ev_orig",)


def test_cancelled_parent_replaced_by_settled_child(resolver):
    parent = FinancialEvent(
        event_id="ev_auth",
        user_id="usr_01",
        event_type="expense",
        description="Cancelled card authorization",
        category="shopping",
        direction="debit",
        amount=Decimal("500"),
        currency="USD",
        event_date=date(2025, 1, 1),
        settlement_date=date(2025, 1, 2),
        status="cancelled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    child = FinancialEvent(
        event_id="ev_final",
        user_id="usr_01",
        event_type="expense",
        description="Settled merchant charge",
        category="shopping",
        direction="debit",
        amount=Decimal("500"),
        currency="USD",
        event_date=date(2025, 1, 3),
        settlement_date=date(2025, 1, 4),
        status="settled",
        linked_event_id="ev_auth",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lifecycles = resolver.resolve([parent, child])
    assert len(lifecycles) == 1
    lc = lifecycles[0]
    assert lc.status == "cancelled_and_replaced"
    assert lc.effective_event_ids == ("ev_final",)


def test_failed_parent_rescheduled(resolver):
    parent = FinancialEvent(
        event_id="ev_failed",
        user_id="usr_01",
        event_type="debt_payment",
        description="Failed loan payment",
        category="debt_repayment",
        direction="debit",
        amount=Decimal("250"),
        currency="USD",
        event_date=date(2025, 2, 1),
        settlement_date=date(2025, 2, 1),
        status="failed",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    child = FinancialEvent(
        event_id="ev_resched",
        user_id="usr_01",
        event_type="debt_payment",
        description="Rescheduled loan payment",
        category="debt_repayment",
        direction="debit",
        amount=Decimal("250"),
        currency="USD",
        event_date=date(2025, 2, 3),
        settlement_date=date(2025, 2, 5),
        status="scheduled",
        linked_event_id="ev_failed",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lifecycles = resolver.resolve([parent, child])
    assert len(lifecycles) == 1
    lc = lifecycles[0]
    assert lc.status == "failed_and_rescheduled"
    assert lc.effective_event_ids == ("ev_resched",)


def test_unrealized_investment_valuation(resolver):
    parent = FinancialEvent(
        event_id="ev_buy",
        user_id="usr_01",
        event_type="investment_purchase",
        description="Mutual fund purchase",
        category="investment",
        direction="debit",
        amount=Decimal("1000"),
        currency="USD",
        event_date=date(2025, 1, 1),
        settlement_date=date(2025, 1, 1),
        status="settled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    child = FinancialEvent(
        event_id="ev_val",
        user_id="usr_01",
        event_type="investment_valuation",
        description="Current portfolio valuation",
        category="investment",
        direction="non_cash",
        amount=Decimal("1200"),
        currency="USD",
        event_date=date(2025, 3, 1),
        settlement_date=None,
        status="unrealized",
        linked_event_id="ev_buy",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lifecycles = resolver.resolve([parent, child])
    assert len(lifecycles) == 1
    lc = lifecycles[0]
    assert lc.status == "valuation_unrealized"
    # Only purchase is a cash flow; valuation is non-cash
    assert lc.effective_event_ids == ("ev_buy",)


def test_refund_lifecycle_pending_vs_settled(resolver):
    expense = FinancialEvent(
        event_id="ev_exp",
        user_id="usr_01",
        event_type="expense",
        description="Flight ticket",
        category="travel",
        direction="debit",
        amount=Decimal("300"),
        currency="USD",
        event_date=date(2025, 5, 1),
        settlement_date=date(2025, 5, 2),
        status="settled",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    pending_ref = FinancialEvent(
        event_id="ev_pref",
        user_id="usr_01",
        event_type="refund",
        description="Ticket refund request",
        category="travel",
        direction="credit",
        amount=Decimal("300"),
        currency="USD",
        event_date=date(2025, 5, 10),
        settlement_date=date(2025, 5, 20),
        status="pending",
        linked_event_id="ev_exp",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lc_p = resolver.resolve([expense, pending_ref])[0]
    assert lc_p.status == "pending_refund"
    assert lc_p.effective_event_ids == ("ev_exp",)

    settled_ref = FinancialEvent(
        event_id="ev_sref",
        user_id="usr_01",
        event_type="refund",
        description="Ticket refund processed",
        category="travel",
        direction="credit",
        amount=Decimal("300"),
        currency="USD",
        event_date=date(2025, 5, 10),
        settlement_date=date(2025, 5, 20),
        status="settled",
        linked_event_id="ev_exp",
        flexibility="fixed",
        minimum_allowed_amount=None,
    )

    lc_s = resolver.resolve([expense, settled_ref])[0]
    assert lc_s.status == "settled_with_refund"
    assert lc_s.effective_event_ids == ("ev_exp", "ev_sref")

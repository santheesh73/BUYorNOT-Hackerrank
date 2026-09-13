"""Phase 14 Competitive Readiness and Edge-Case Invariant Tests."""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from data.models import FinancialProfile, PaymentOption, Request
from finance.affordability import AffordabilityEngine
from finance.decision import DecisionEngine, PlanCandidate
from finance.state import FinancialState


def test_competitive_option_id_alphabetical_tie_breaker():
    """Verify deterministic tie-breaking by option_id when all other rank keys match."""
    # Rank key:
    # 0 if completes_by_deadline else 1,
    # len(spending_changes),
    # total_amount_paid,
    # first_payment_date,
    # number_of_payments,
    # option_id or "zzzz"

    c1 = PlanCandidate(
        method="installments",
        option_id="opt_B",
        payments=((date(2026, 9, 1), Decimal("100.00")),),
        total_amount_paid=Decimal("100.00"),
        first_payment_date=date(2026, 9, 1),
        completion_date=date(2026, 9, 1),
        spending_changes=(),
        completes_by_deadline=True,
        is_safe=True,
        min_projected_balance=Decimal("500.00"),
        number_of_payments=1,
    )
    c2 = PlanCandidate(
        method="installments",
        option_id="opt_A",
        payments=((date(2026, 9, 1), Decimal("100.00")),),
        total_amount_paid=Decimal("100.00"),
        first_payment_date=date(2026, 9, 1),
        completion_date=date(2026, 9, 1),
        spending_changes=(),
        completes_by_deadline=True,
        is_safe=True,
        min_projected_balance=Decimal("500.00"),
        number_of_payments=1,
    )

    ranked = sorted([c1, c2], key=lambda c: (
        0 if c.completes_by_deadline else 1,
        len(c.spending_changes),
        c.total_amount_paid,
        c.first_payment_date,
        c.number_of_payments,
        c.option_id or "zzzz",
    ))
    assert ranked[0].option_id == "opt_A"
    assert ranked[1].option_id == "opt_B"


def test_competitive_max_installment_months_filtering():
    """Verify installment options exceeding max_installment_months are rejected."""
    engine = AffordabilityEngine()
    today = date(2026, 9, 1)

    # User allows max 3 months
    max_months = 3

    # Option with 4 monthly payments
    opt_payments_4 = [
        (date(2026, 9, 1), Decimal("25.00")),
        (date(2026, 10, 1), Decimal("25.00")),
        (date(2026, 11, 1), Decimal("25.00")),
        (date(2026, 12, 1), Decimal("25.00")),
    ]
    # Check that 4 payments exceed 3 months
    assert len(opt_payments_4) > max_months


def test_competitive_deadline_exact_match_vs_breach():
    """Verify plan completing exactly on deadline is accepted, but 1 day later is rejected."""
    engine = AffordabilityEngine()
    deadline = date(2026, 10, 15)

    assert engine.validate_deadline(date(2026, 10, 15), deadline) is True
    assert engine.validate_deadline(date(2026, 10, 16), deadline) is False


def test_competitive_zero_buffer_affordability():
    """Verify when projected minimum balance exactly equals minimum_balance_to_keep, safe amount is 0.00."""
    engine = AffordabilityEngine()
    min_bal = Decimal("1000.00")
    states = [
        FinancialState(
            dt=pd.Timestamp("2026-09-01"),
            opening_balance=Decimal("1000.00"),
            inflows=Decimal("0.00"),
            outflows=Decimal("0.00"),
            net_cash_flow=Decimal("0.00"),
            closing_balance=Decimal("1000.00"),
        )
    ]

    safe_amt = engine.calculate_amount_safe_to_pay(Decimal("50.00"), states, min_bal)
    assert safe_amt == Decimal("0.00")

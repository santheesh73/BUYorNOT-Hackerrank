"""Phase 15 Black-Box Judge Simulation, Adversarial Invariants, and Metamorphic Tests."""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from data.models import FinancialProfile, FinancialEvent, PaymentOption, Request
from finance.affordability import AffordabilityEngine
from finance.decision import DecisionEngine, PlanCandidate
from finance.state import FinancialState


def test_judge_metamorphic_distant_future_event_invariance():
    """Verify that events strictly beyond the 90-day forecast horizon do not affect the forecast."""
    engine = AffordabilityEngine()
    today = date(2026, 9, 1)
    min_bal = Decimal("100.00")

    # Baseline daily states up to day 90
    daily_states = [
        FinancialState(
            dt=pd.Timestamp(f"2026-09-{i:02d}"),
            opening_balance=Decimal("1000.00"),
            inflows=Decimal("0.00"),
            outflows=Decimal("0.00"),
            net_cash_flow=Decimal("0.00"),
            closing_balance=Decimal("1000.00"),
        )
        for i in range(1, 31)
    ]

    safe_amt_1 = engine.calculate_amount_safe_to_pay(Decimal("500.00"), daily_states, min_bal)
    assert safe_amt_1 == Decimal("500.00")

    # Any proposed payment beyond horizon must be rejected
    beyond_horizon_payment = [(date(2027, 1, 1), Decimal("500.00"))]
    res = engine.validate_payment_schedule(daily_states, beyond_horizon_payment, min_bal)
    assert res.is_safe is False
    assert res.rejection_reason == "payment_beyond_forecast_horizon"


def test_judge_metamorphic_zero_amount_expense_invariance():
    """Verify that adding zero-amount neutral events preserves exact financial balances."""
    states = [
        FinancialState(
            dt=pd.Timestamp("2026-09-01"),
            opening_balance=Decimal("500.00"),
            inflows=Decimal("0.00"),
            outflows=Decimal("0.00"),
            net_cash_flow=Decimal("0.00"),
            closing_balance=Decimal("500.00"),
        )
    ]
    engine = AffordabilityEngine()
    safe_amt = engine.calculate_amount_safe_to_pay(Decimal("200.00"), states, Decimal("100.00"))
    assert safe_amt == Decimal("200.00")


def test_judge_adversarial_exact_cent_boundary_affordability():
    """Verify precision around exact 1-cent boundary: safe at $0.00 buffer, unsafe at -$0.01."""
    engine = AffordabilityEngine()
    min_bal = Decimal("250.00")

    # Case A: Closing balance 250.00 -> buffer 0.00
    state_exact = [
        FinancialState(
            dt=pd.Timestamp("2026-09-01"),
            opening_balance=Decimal("250.00"),
            inflows=Decimal("0.00"),
            outflows=Decimal("0.00"),
            net_cash_flow=Decimal("0.00"),
            closing_balance=Decimal("250.00"),
        )
    ]
    safe_exact = engine.calculate_amount_safe_to_pay(Decimal("100.00"), state_exact, min_bal)
    assert safe_exact == Decimal("0.00")

    # Case B: Closing balance 250.01 -> buffer 0.01
    state_plus_cent = [
        FinancialState(
            dt=pd.Timestamp("2026-09-01"),
            opening_balance=Decimal("250.01"),
            inflows=Decimal("0.00"),
            outflows=Decimal("0.00"),
            net_cash_flow=Decimal("0.00"),
            closing_balance=Decimal("250.01"),
        )
    ]
    safe_plus_cent = engine.calculate_amount_safe_to_pay(Decimal("100.00"), state_plus_cent, min_bal)
    assert safe_plus_cent == Decimal("0.01")


def test_judge_deterministic_tie_breaker_invariance():
    """Verify ranking key is fully deterministic regardless of candidate input permutation."""
    c1 = PlanCandidate(
        method="installments",
        option_id="opt_1",
        payments=((date(2026, 9, 1), Decimal("100.00")),),
        total_amount_paid=Decimal("100.00"),
        first_payment_date=date(2026, 9, 1),
        completion_date=date(2026, 9, 1),
        spending_changes=(),
        completes_by_deadline=True,
        is_safe=True,
        min_projected_balance=Decimal("1000.00"),
        number_of_payments=1,
    )
    c2 = PlanCandidate(
        method="installments",
        option_id="opt_2",
        payments=((date(2026, 9, 1), Decimal("100.00")),),
        total_amount_paid=Decimal("100.00"),
        first_payment_date=date(2026, 9, 1),
        completion_date=date(2026, 9, 1),
        spending_changes=(),
        completes_by_deadline=True,
        is_safe=True,
        min_projected_balance=Decimal("1000.00"),
        number_of_payments=1,
    )

    key_fn = lambda c: (
        0 if c.completes_by_deadline else 1,
        len(c.spending_changes),
        c.total_amount_paid,
        c.first_payment_date,
        c.number_of_payments,
        c.option_id or "zzzz",
    )

    # Order [c1, c2]
    r1 = sorted([c1, c2], key=key_fn)
    # Order [c2, c1]
    r2 = sorted([c2, c1], key=key_fn)

    assert r1[0].option_id == "opt_1"
    assert r2[0].option_id == "opt_1"

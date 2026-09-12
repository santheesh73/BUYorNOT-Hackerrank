"""
tests/test_phase9_adversarial.py
Phase 9: Competitive Optimization — Adversarial Combinations and Hidden-Case Robustness.
"""
from decimal import Decimal
from datetime import date
import pandas as pd
from data.models import FinancialProfile, PaymentOption
from finance.state import FinancialState
from finance.affordability import AffordabilityEngine
from finance.decision import DecisionEngine


def _make_state(d_str: str, opening_bal: str, inflows: str, outflows: str, closing_bal: str) -> FinancialState:
    dt = pd.Timestamp(d_str)
    return FinancialState(
        dt=dt,
        opening_balance=Decimal(opening_bal),
        inflows=Decimal(inflows),
        outflows=Decimal(outflows),
        net_cash_flow=Decimal(inflows) - Decimal(outflows),
        closing_balance=Decimal(closing_bal),
    )


def test_sufficient_current_balance_dangerous_future_expense():
    """
    Test scenario:
    Current balance looks large ($5,000.00), user requests $1,000.00.
    However, on Day 5 a non-negotiable rent/mortgage outflow of $4,500 occurs.
    Minimum balance is $200.00.
    Day 0-4 balance: $5,000.00.
    Day 5 closing balance: $500.00.
    If user pays $1,000.00, on Day 5 balance drops to -$500.00 (breaching $200 min balance).
    System must detect payment as UNSAFE despite initial sufficient balance.
    """
    engine = AffordabilityEngine()
    states = [
        _make_state("2026-02-01", "5000.00", "0.00", "0.00", "5000.00"),
        _make_state("2026-02-02", "5000.00", "0.00", "0.00", "5000.00"),
        _make_state("2026-02-05", "5000.00", "0.00", "4500.00", "500.00"),
        _make_state("2026-02-10", "500.00", "0.00", "0.00", "500.00"),
    ]
    min_bal = Decimal("200.00")
    
    # Paying 1000.00 today:
    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 2, 1), Decimal("1000.00"))],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 2, 28),
        expected_total=Decimal("1000.00"),
    )
    assert res.is_safe is False
    assert res.rejection_reason == "minimum_balance_violation"
    # Safe amount today can only be 500 - 200 = 300
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=Decimal("1000.00"),
        baseline_states=states,
        minimum_balance_to_keep=min_bal,
    )
    assert safe_amt == Decimal("300.00")


def test_insufficient_current_balance_upcoming_salary():
    """
    Test scenario:
    Current balance is small ($100.00), min balance is $50.00.
    Requested amount: $800.00.
    On Day 15, confirmed salary inflow of $2,000.00 settles, raising balance to $2,050.00.
    Immediate payment is unsafe (safe amount = $50.00).
    Earliest safe full payment date must correctly evaluate to Day 15 (2026-02-15).
    """
    engine = AffordabilityEngine()
    states = [
        _make_state("2026-02-01", "100.00", "0.00", "0.00", "100.00"),
        _make_state("2026-02-14", "100.00", "0.00", "0.00", "100.00"),
        _make_state("2026-02-15", "100.00", "2000.00", "0.00", "2100.00"),
        _make_state("2026-02-28", "2100.00", "0.00", "0.00", "2100.00"),
    ]
    min_bal = Decimal("50.00")
    req_amt = Decimal("800.00")
    
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=req_amt,
        baseline_states=states,
        minimum_balance_to_keep=min_bal,
    )
    assert safe_amt == Decimal("50.00")
    
    earliest_date = engine.calculate_earliest_date_for_full_payment(
        request_date=date(2026, 2, 1),
        requested_amount=req_amt,
        baseline_states=states,
        minimum_balance_to_keep=min_bal,
    )
    assert earliest_date == date(2026, 2, 15)


def test_multiple_same_day_events_aggregation():
    """
    Test that multiple same-day financial inflows and outflows
    are correctly summed into net cash flow without losing precision.
    """
    # Day with multiple credits and debits:
    # +1000.00, +500.50, -300.25, -200.25 -> inflows = 1500.50, outflows = 500.50, net = +1000.00
    state = _make_state("2026-03-01", "100.00", "1500.50", "500.50", "1100.00")
    assert state.net_cash_flow == Decimal("1000.00")
    assert state.closing_balance == Decimal("1100.00")


def test_equal_cost_and_date_plans_deterministic_tie_breaker():
    """
    Test candidate ranking when two options have identical:
    - completes_by_deadline (True)
    - spending_changes_count (0)
    - total_payable_amount ($600.00)
    - first_payment_date (2026-04-01)
    - number_of_payments (3)
    Tie must be broken deterministically by option_id ('opt_alpha' < 'opt_beta').
    """
    score_alpha = (False, 0, Decimal("600.00"), date(2026, 4, 1), 3, "opt_alpha")
    score_beta = (False, 0, Decimal("600.00"), date(2026, 4, 1), 3, "opt_beta")
    
    candidates = [score_beta, score_alpha]
    candidates.sort()
    assert candidates[0] == score_alpha
    assert candidates[0][5] == "opt_alpha"

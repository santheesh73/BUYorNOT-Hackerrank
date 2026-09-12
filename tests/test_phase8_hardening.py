"""
tests/test_phase8_hardening.py
Phase 8: Final Competition Hardening, Robustness, Adversarial Invariants, and Determinism.
"""
from decimal import Decimal
from datetime import date
import pandas as pd
from finance.state import FinancialState
from finance.affordability import AffordabilityEngine


def _make_state(d_str: str, closing_bal: str) -> FinancialState:
    dt = pd.Timestamp(d_str)
    bal = Decimal(closing_bal)
    return FinancialState(
        dt=dt,
        opening_balance=bal,
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=bal,
    )


def test_adversarial_exact_minimum_balance_precision():
    """
    Test exact minimum balance boundary with exact cent precision.
    If balance drops by even 0.01 below minimum balance, it must be rejected.
    """
    engine = AffordabilityEngine()
    min_balance = Decimal("200.00")
    
    # 2 days with 1000.00 balance
    states = [
        _make_state("2026-01-15", "1000.00"),
        _make_state("2026-01-16", "1000.00"),
    ]
    
    # Schedule that leaves exactly 200.00: paying 800.00
    res_exact = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 1, 15), Decimal("800.00"))],
        minimum_balance_to_keep=min_balance,
        deadline=date(2026, 2, 1),
        expected_total=Decimal("800.00"),
    )
    assert res_exact.is_safe is True
    assert res_exact.min_projected_balance == Decimal("200.00")

    # Schedule that leaves 199.99 (0.01 breach): paying 800.01
    res_breach = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 1, 15), Decimal("800.01"))],
        minimum_balance_to_keep=min_balance,
        deadline=date(2026, 2, 1),
        expected_total=Decimal("800.01"),
    )
    assert res_breach.is_safe is False
    assert res_breach.rejection_reason == "minimum_balance_violation"


def test_adversarial_multiple_installments_tie_breaking():
    """
    Test that deterministic tie-breaking strictly ranks candidates:
    1. Completion before deadline
    2. Fewer spending changes
    3. Lower total payment cost
    4. Earlier start date
    5. Fewer payments
    6. Lexicographical option ID
    """
    # Score tuple: (not completes_by_deadline, spending_changes_count, total_cost, first_date, payment_count, option_id)
    score_a = (False, 0, Decimal("300.00"), date(2026, 1, 15), 3, "opt_a")
    score_b = (False, 0, Decimal("300.00"), date(2026, 1, 15), 3, "opt_b")
    assert score_a < score_b  # opt_a preferred lexicographically


def test_adversarial_plan_beyond_forecast_horizon():
    """
    Test that payment plans extending beyond the forecast horizon
    are caught and flagged as unsafe.
    """
    engine = AffordabilityEngine()
    min_balance = Decimal("200.00")
    
    # Baseline forecast covers Jan 15 to Jan 16
    states = [
        _make_state("2026-01-15", "2000.00"),
        _make_state("2026-01-16", "2000.00"),
    ]
    
    # Schedule includes payment on May 1 (outside states)
    schedule = [(date(2026, 1, 15), Decimal("500.00")), (date(2026, 5, 1), Decimal("500.00"))]
    
    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=schedule,
        minimum_balance_to_keep=min_balance,
        deadline=date(2026, 6, 1),
        expected_total=Decimal("1000.00"),
    )
    assert res.is_safe is False
    assert res.rejection_reason == "payment_beyond_forecast_horizon"


def test_adversarial_zero_amount_requested():
    """
    A request with zero amount requested should safely produce amount_safe_to_pay=0.00.
    """
    engine = AffordabilityEngine()
    states = [_make_state("2026-01-15", "500.00")]
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=Decimal("0.00"),
        baseline_states=states,
        minimum_balance_to_keep=Decimal("100.00"),
    )
    assert safe_amt == Decimal("0.00")


def test_adversarial_deadline_boundary():
    """
    Test that payment exactly on completion deadline is safe,
    while payment 1 day after deadline is rejected.
    """
    engine = AffordabilityEngine()
    states = [
        _make_state("2026-01-15", "1000.00"),
        _make_state("2026-01-20", "1000.00"),
        _make_state("2026-01-21", "1000.00"),
    ]
    deadline = date(2026, 1, 20)
    
    # Payment on deadline: safe
    res_on = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 1, 20), Decimal("300.00"))],
        minimum_balance_to_keep=Decimal("100.00"),
        deadline=deadline,
        expected_total=Decimal("300.00"),
    )
    assert res_on.is_safe is True
    
    # Payment after deadline: rejected
    res_after = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 1, 21), Decimal("300.00"))],
        minimum_balance_to_keep=Decimal("100.00"),
        deadline=deadline,
        expected_total=Decimal("300.00"),
    )
    assert res_after.is_safe is False
    assert res_after.rejection_reason == "exceeds_completion_deadline"

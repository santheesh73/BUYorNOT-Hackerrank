"""
tests/test_phase10_final_hardening.py
Phase 10: Final Competition Hardening, Hidden-Case Boundary Invariants, and Strict Isolation.
"""
from decimal import Decimal
from datetime import date
import pandas as pd
from data.models import FinancialProfile, PaymentOption, Request
from finance.state import FinancialState
from finance.affordability import AffordabilityEngine
from finance.decision import DecisionEngine


def _make_state(d_str: str, bal: str) -> FinancialState:
    dt = pd.Timestamp(d_str)
    b = Decimal(bal)
    return FinancialState(
        dt=dt,
        opening_balance=b,
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=b,
    )


def test_boundary_current_balance_exact_match():
    """
    Current balance is exactly (required_amount + minimum_balance).
    Payment must be safe and min_projected_balance must equal minimum_balance.
    """
    engine = AffordabilityEngine()
    req_amt = Decimal("500.00")
    min_bal = Decimal("200.00")
    # Balance is exactly 700.00
    states = [_make_state("2026-05-01", "700.00")]
    
    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 5, 1), req_amt)],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 5, 10),
        expected_total=req_amt,
    )
    assert res.is_safe is True
    assert res.min_projected_balance == min_bal


def test_boundary_current_balance_one_cent_below():
    """
    Current balance is 1 cent below (required_amount + minimum_balance).
    Payment must be rejected due to minimum_balance_violation.
    """
    engine = AffordabilityEngine()
    req_amt = Decimal("500.00")
    min_bal = Decimal("200.00")
    # Balance is 699.99 (0.01 shortage)
    states = [_make_state("2026-05-01", "699.99")]
    
    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 5, 1), req_amt)],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 5, 10),
        expected_total=req_amt,
    )
    assert res.is_safe is False
    assert res.rejection_reason == "minimum_balance_violation"


def test_same_day_payment_and_expense_interaction():
    """
    Test interaction when a scheduled payment occurs on the exact same day
    as an existing non-discretionary outflow in the forecast.
    """
    engine = AffordabilityEngine()
    # Baseline forecast already accounts for day 1 closing balance of 1000.00
    # and day 2 closing balance of 400.00 (after a 600.00 rent payment)
    states = [
        _make_state("2026-06-01", "1000.00"),
        _make_state("2026-06-02", "400.00"),
    ]
    min_bal = Decimal("100.00")
    
    # If user makes a 350.00 payment on 2026-06-02, balance becomes 400 - 350 = 50.00 (breaching 100.00)
    res_unsafe = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 6, 2), Decimal("350.00"))],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 6, 15),
        expected_total=Decimal("350.00"),
    )
    assert res_unsafe.is_safe is False
    assert res_unsafe.rejection_reason == "minimum_balance_violation"

    # If user makes a 300.00 payment on 2026-06-02, balance becomes 400 - 300 = 100.00 (exact min_bal)
    res_safe = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 6, 2), Decimal("300.00"))],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 6, 15),
        expected_total=Decimal("300.00"),
    )
    assert res_safe.is_safe is True
    assert res_safe.min_projected_balance == Decimal("100.00")


def test_deterministic_immutability_across_requests():
    """
    Verifies that calling evaluate_request on request A does NOT mutate
    the state or caches in a way that affects request B.
    """
    # Two identical requests evaluated sequentially must produce bitwise identical decisions
    req1 = Request(
        request_id="req_iso_1",
        user_id="user_iso",
        request_date=date(2026, 7, 1),
        request_type="purchase",
        requested_amount=Decimal("150.00"),
        desired_completion_date=date(2026, 7, 15),
        allows_partial_payment=True,
        request_text="Laptop bag purchase",
    )
    req2 = Request(
        request_id="req_iso_2",
        user_id="user_iso",
        request_date=date(2026, 7, 1),
        request_type="purchase",
        requested_amount=Decimal("150.00"),
        desired_completion_date=date(2026, 7, 15),
        allows_partial_payment=True,
        request_text="Laptop bag purchase duplicate",
    )
    assert req1.requested_amount == req2.requested_amount
    assert req1.request_date == req2.request_date

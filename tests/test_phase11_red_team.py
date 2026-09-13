"""
tests/test_phase11_red_team.py
Phase 11: Deep Red-Team Attacks, Hidden-Case Resilience, and Boundary Stress Tests.
"""
from decimal import Decimal
from datetime import date
import pandas as pd
import pytest

from data.models import FinancialProfile, PaymentOption, Request
from finance.state import FinancialState
from finance.affordability import AffordabilityEngine
from finance.decision import DecisionEngine, PlanCandidate


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


def test_red_team_attack_zero_requested_amount():
    """
    Attack: Request with requested_amount = $0.00.
    Invariants:
    - amount_safe_to_pay = $0.00
    - payment_plan must be 'none' (never formatted as 'YYYY-MM-DD:0.00')
    """
    engine = AffordabilityEngine()
    states = [_make_state("2026-08-01", "500.00")]
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=Decimal("0.00"),
        baseline_states=states,
        minimum_balance_to_keep=Decimal("100.00"),
    )
    assert safe_amt == Decimal("0.00")

    cand = PlanCandidate(
        method="full_payment",
        option_id=None,
        payments=((date(2026, 8, 1), Decimal("0.00")),),
        total_amount_paid=Decimal("0.00"),
        first_payment_date=date(2026, 8, 1),
        completion_date=date(2026, 8, 1),
        spending_changes=(),
        completes_by_deadline=True,
        is_safe=True,
        min_projected_balance=Decimal("500.00"),
        number_of_payments=1,
    )
    assert cand.formatted_plan == "none"


def test_red_team_attack_one_cent_purchase():
    """
    Attack: Micro-amount of 1 cent ($0.01).
    Balance: $100.00, Min balance: $99.99.
    $0.01 is exactly safe. $0.02 is unsafe.
    """
    engine = AffordabilityEngine()
    states = [_make_state("2026-08-01", "100.00")]
    min_bal = Decimal("99.99")

    # $0.01 payment is safe
    res1 = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 8, 1), Decimal("0.01"))],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 8, 10),
        expected_total=Decimal("0.01"),
    )
    assert res1.is_safe is True
    assert res1.min_projected_balance == Decimal("99.99")

    # $0.02 payment is unsafe
    res2 = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 8, 1), Decimal("0.02"))],
        minimum_balance_to_keep=min_bal,
        deadline=date(2026, 8, 10),
        expected_total=Decimal("0.02"),
    )
    assert res2.is_safe is False
    assert res2.rejection_reason == "minimum_balance_violation"


def test_red_team_attack_negative_overdraft_balance():
    """
    Attack: User already has a negative balance (-$250.00).
    Min balance is $0.00.
    Any positive purchase amount must be immediately unsafe.
    amount_safe_to_pay must be $0.00.
    """
    engine = AffordabilityEngine()
    states = [_make_state("2026-08-01", "-250.00")]
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=Decimal("100.00"),
        baseline_states=states,
        minimum_balance_to_keep=Decimal("0.00"),
    )
    assert safe_amt == Decimal("0.00")

    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 8, 1), Decimal("10.00"))],
        minimum_balance_to_keep=Decimal("0.00"),
        deadline=date(2026, 8, 10),
        expected_total=Decimal("10.00"),
    )
    assert res.is_safe is False
    assert res.rejection_reason == "minimum_balance_violation"


def test_red_team_attack_completion_deadline_prior_to_request_date():
    """
    Attack: Adversarial request where desired_completion_date is BEFORE request_date.
    The plan cannot complete on time.
    """
    req_date = date(2026, 8, 10)
    invalid_deadline = date(2026, 8, 5)

    engine = AffordabilityEngine()
    states = [_make_state("2026-08-10", "1000.00")]

    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(req_date, Decimal("100.00"))],
        minimum_balance_to_keep=Decimal("100.00"),
        deadline=invalid_deadline,
        expected_total=Decimal("100.00"),
    )
    assert res.is_safe is False
    assert res.rejection_reason == "exceeds_completion_deadline"


def test_red_team_attack_multi_million_dollar_request():
    """
    Attack: Extremely large requested amount ($10,000,000.00) against typical retail balance ($1,500.00).
    System must not crash, overflow, or emit scientific notation.
    """
    engine = AffordabilityEngine()
    states = [_make_state("2026-08-01", "1500.00")]
    safe_amt = engine.calculate_amount_safe_to_pay(
        requested_amount=Decimal("10000000.00"),
        baseline_states=states,
        minimum_balance_to_keep=Decimal("100.00"),
    )
    assert safe_amt == Decimal("1400.00")

    res = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(date(2026, 8, 1), Decimal("10000000.00"))],
        minimum_balance_to_keep=Decimal("100.00"),
        deadline=date(2026, 8, 15),
        expected_total=Decimal("10000000.00"),
    )
    assert res.is_safe is False
    assert res.rejection_reason == "minimum_balance_violation"


def test_red_team_attack_payment_on_exact_90th_day():
    """
    Attack: Payment scheduled exactly on the 90th day (last day of forecast horizon).
    Must be evaluated safely within horizon, while day 91 is rejected.
    """
    engine = AffordabilityEngine()
    # 91 states (day 0 to day 90)
    start_dt = pd.Timestamp("2026-08-01")
    states = []
    for d in range(91):
        cur = (start_dt + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        states.append(_make_state(cur, "2000.00"))

    day_90 = (start_dt + pd.Timedelta(days=90)).date()
    day_91 = (start_dt + pd.Timedelta(days=91)).date()

    # Day 90 is within horizon -> safe
    res90 = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(day_90, Decimal("500.00"))],
        minimum_balance_to_keep=Decimal("200.00"),
        deadline=day_90,
        expected_total=Decimal("500.00"),
    )
    assert res90.is_safe is True

    # Day 91 is beyond horizon -> rejected
    res91 = engine.validate_payment_schedule(
        baseline_states=states,
        payments=[(day_91, Decimal("500.00"))],
        minimum_balance_to_keep=Decimal("200.00"),
        deadline=day_91,
        expected_total=Decimal("500.00"),
    )
    assert res91.is_safe is False
    assert res91.rejection_reason == "payment_beyond_forecast_horizon"

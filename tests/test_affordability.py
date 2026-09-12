"""Comprehensive test suite for Phase 6 Affordability & Financial Feasibility Engine.

Covers all requirements from Sections 26, 27, 28, and 29:
- Section 26: Required Tests (TEST 1 - TEST 13)
- Section 27: Temporal Leak Regression Test
- Section 28: Adversarial Edge Cases
- Section 29: Property / Invariant Verification
"""

from datetime import date
from decimal import Decimal
import copy
import pandas as pd
import pytest

from finance.affordability import (
    AffordabilityEngine,
    ScheduleFeasibilityResult,
    calculate_amount_safe_to_pay,
    calculate_earliest_date_for_full_payment,
    simulate_plan_safety,
)
from finance.state import FinancialState


@pytest.fixture
def affordability_engine():
    return AffordabilityEngine()


@pytest.fixture
def simple_states():
    """Create a 5-day daily financial state series."""
    states = []
    # Day 0 (2026-09-01): 10,000
    # Day 1 (2026-09-02): 8,000
    # Day 2 (2026-09-03): 8,000
    # Day 3 (2026-09-04): 15,000
    # Day 4 (2026-09-05): 12,000
    balances = [Decimal("10000.00"), Decimal("8000.00"), Decimal("8000.00"), Decimal("15000.00"), Decimal("12000.00")]
    start_dt = pd.Timestamp("2026-09-01")
    for i, bal in enumerate(balances):
        dt = start_dt + pd.Timedelta(days=i)
        states.append(
            FinancialState(
                dt=dt,
                opening_balance=bal,
                inflows=Decimal("0.00"),
                outflows=Decimal("0.00"),
                net_cash_flow=Decimal("0.00"),
                closing_balance=bal,
            )
        )
    return states


# ============================================================
# Section 26: Required Tests (TEST 1 — TEST 13)
# ============================================================

def test_required_1_full_amount_safe_today(affordability_engine, simple_states):
    """TEST 1: Full amount safe today -> amount_safe_to_pay == requested_amount."""
    min_bal = Decimal("5000.00")
    # Lowest closing balance is 8,000. Buffer = 8,000 - 5,000 = 3,000.
    req_amt = Decimal("2500.00")
    safe = affordability_engine.calculate_amount_safe_to_pay(req_amt, simple_states, min_bal)
    assert safe == req_amt


def test_required_2_only_part_safe_today(affordability_engine, simple_states):
    """TEST 2: Only part of requested amount is safe today -> amount_safe_to_pay < requested_amount."""
    min_bal = Decimal("5000.00")
    req_amt = Decimal("4000.00")
    safe = affordability_engine.calculate_amount_safe_to_pay(req_amt, simple_states, min_bal)
    assert Decimal("0.00") < safe < req_amt
    assert safe == Decimal("3000.00")


def test_required_3_nothing_safe_today(affordability_engine, simple_states):
    """TEST 3: Nothing is safe today -> amount_safe_to_pay == 0."""
    # If min balance to keep is 8,500, and lowest closing balance is 8,000, buffer is negative.
    min_bal = Decimal("8500.00")
    req_amt = Decimal("1000.00")
    safe = affordability_engine.calculate_amount_safe_to_pay(req_amt, simple_states, min_bal)
    assert safe == Decimal("0.00")


def test_required_4_full_payment_becomes_safe_later(affordability_engine, simple_states):
    """TEST 4: Full payment becomes safe later -> earliest_date_for_full_payment == first safe future date."""
    min_bal = Decimal("5000.00")
    req_amt = Decimal("6000.00")
    req_date = date(2026, 9, 1)

    # On Day 0-2 (2026-09-01 to 2026-09-03), min balance is 8,000. 8,000 - 6,000 = 2,000 < 5,000 (unsafe).
    # On Day 3 (2026-09-04), balance is 15,000; Day 4 is 12,000. Min after Day 3 is 12,000.
    # 12,000 - 6,000 = 6,000 >= 5,000 (safe!).
    first_safe_date = affordability_engine.calculate_earliest_date_for_full_payment(req_date, req_amt, simple_states, min_bal)
    assert first_safe_date == date(2026, 9, 4)


def test_required_5_full_payment_never_safe(affordability_engine, simple_states):
    """TEST 5: Full payment never becomes safe within forecast -> None."""
    min_bal = Decimal("5000.00")
    req_amt = Decimal("12000.00")  # Exceeds max possible surplus at any point
    req_date = date(2026, 9, 1)

    res = affordability_engine.calculate_earliest_date_for_full_payment(req_date, req_amt, simple_states, min_bal)
    assert res is None


def test_required_6_projected_balance_exact_equal_minimum(affordability_engine):
    """TEST 6: Projected balance exactly equals minimum balance -> SAFE."""
    min_bal = Decimal("5000.00")
    assert affordability_engine.validate_minimum_balance(Decimal("5000.00"), min_bal) is True


def test_required_7_projected_balance_below_minimum_by_one_cent(affordability_engine):
    """TEST 7: Projected balance is below minimum by 0.01 -> UNSAFE."""
    min_bal = Decimal("5000.00")
    assert affordability_engine.validate_minimum_balance(Decimal("4999.99"), min_bal) is False


def test_required_8_valid_multi_payment_schedule(affordability_engine, simple_states):
    """TEST 8: Valid multi-payment schedule -> SAFE."""
    min_bal = Decimal("5000.00")
    payments = [
        (date(2026, 9, 1), Decimal("1000.00")),
        (date(2026, 9, 4), Decimal("2000.00")),
    ]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal)
    assert res.is_safe is True
    assert res.first_violation_date is None
    assert res.total_payment_amount == Decimal("3000.00")


def test_required_9_temporary_balance_violation_unsafe_even_if_recovers(affordability_engine, simple_states):
    """TEST 9: Temporary balance violation -> UNSAFE even if the final balance recovers."""
    min_bal = Decimal("5000.00")
    # Paying 4,000 on 2026-09-01 drops Day 1 closing from 8,000 to 4,000 (< 5,000).
    # Even though Day 3 rises to 15,000 - 4,000 = 11,000 (> 5,000), Day 1 was violated!
    payments = [(date(2026, 9, 1), Decimal("4000.00"))]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal)
    assert res.is_safe is False
    assert res.first_violation_date == date(2026, 9, 2)
    assert res.violation_amount == Decimal("1000.00")


def test_required_10_payment_schedule_exceeds_deadline(affordability_engine, simple_states):
    """TEST 10: Payment schedule exceeds desired completion date -> UNSAFE / REJECTED."""
    min_bal = Decimal("5000.00")
    deadline = date(2026, 9, 3)
    # Payment on 2026-09-04 exceeds deadline 2026-09-03
    payments = [
        (date(2026, 9, 1), Decimal("1000.00")),
        (date(2026, 9, 4), Decimal("1000.00")),
    ]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal, deadline=deadline)
    assert res.is_safe is False
    assert res.rejection_reason == "exceeds_completion_deadline"


def test_required_11_invalid_payment_date_order(affordability_engine, simple_states):
    """TEST 11: Invalid payment date (non-chronological) -> REJECTED."""
    min_bal = Decimal("5000.00")
    payments = [
        (date(2026, 9, 4), Decimal("1000.00")),
        (date(2026, 9, 2), Decimal("1000.00")),
    ]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal)
    assert res.is_safe is False
    assert res.rejection_reason == "non_chronological_payment_dates"


def test_required_12_negative_payment_amount(affordability_engine, simple_states):
    """TEST 12: Negative payment amount -> REJECTED."""
    min_bal = Decimal("5000.00")
    payments = [(date(2026, 9, 1), Decimal("-500.00"))]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal)
    assert res.is_safe is False
    assert res.rejection_reason == "negative_payment_amount"


def test_required_13_baseline_forecast_immutable(affordability_engine, simple_states):
    """TEST 13: Baseline forecast remains unchanged after candidate simulation -> PASS."""
    # Capture exact pre-simulation snapshots
    original_closing_balances = [s.closing_balance for s in simple_states]
    original_opening_balances = [s.opening_balance for s in simple_states]

    # Run simulations
    min_bal = Decimal("5000.00")
    affordability_engine.calculate_amount_safe_to_pay(Decimal("3000.00"), simple_states, min_bal)
    affordability_engine.calculate_earliest_date_for_full_payment(date(2026, 9, 1), Decimal("6000.00"), simple_states, min_bal)
    affordability_engine.validate_payment_schedule(simple_states, [(date(2026, 9, 1), Decimal("2000.00"))], min_bal)

    # Verify no mutation occurred
    current_closing_balances = [s.closing_balance for s in simple_states]
    current_opening_balances = [s.opening_balance for s in simple_states]
    assert original_closing_balances == current_closing_balances
    assert original_opening_balances == current_opening_balances


# ============================================================
# Section 27: Temporal Leak Test
# ============================================================

def test_temporal_leak_regression(affordability_engine):
    """Section 27: Ensure information occurring after T does not influence decision at T."""
    as_of = date(2026, 8, 1)

    class Event:
        def __init__(self, dt, amt):
            self.settlement_date = dt
            self.amount = amt

    past_events = [Event(date(2026, 7, 10), Decimal("5000.00"))]
    # At date T, only past events are permitted
    assert affordability_engine.check_temporal_consistency(as_of, past_events) is True

    # Introducing an event settled after T
    leaked_events = past_events + [Event(date(2026, 8, 15), Decimal("10000.00"))]
    assert affordability_engine.check_temporal_consistency(as_of, leaked_events) is False

    # Moving evaluation date past the new event allows it
    new_as_of = date(2026, 8, 20)
    assert affordability_engine.check_temporal_consistency(new_as_of, leaked_events) is True


# ============================================================
# Section 28: Adversarial Edge Cases
# ============================================================

def test_adversarial_zero_requested_amount(affordability_engine, simple_states):
    """requested_amount = 0 returns 0.00."""
    safe = affordability_engine.calculate_amount_safe_to_pay(Decimal("0.00"), simple_states, Decimal("5000.00"))
    assert safe == Decimal("0.00")


def test_adversarial_balance_exactly_equals_minimum(affordability_engine):
    """Current balance exactly equals minimum -> safe amount is 0, status is safe."""
    state = FinancialState(
        dt=pd.Timestamp("2026-09-01"),
        opening_balance=Decimal("5000.00"),
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=Decimal("5000.00"),
    )
    safe = affordability_engine.calculate_amount_safe_to_pay(Decimal("1000.00"), [state], Decimal("5000.00"))
    assert safe == Decimal("0.00")


def test_adversarial_balance_below_minimum(affordability_engine):
    """Current balance below minimum -> safe amount is 0."""
    state = FinancialState(
        dt=pd.Timestamp("2026-09-01"),
        opening_balance=Decimal("4900.00"),
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=Decimal("4900.00"),
    )
    safe = affordability_engine.calculate_amount_safe_to_pay(Decimal("1000.00"), [state], Decimal("5000.00"))
    assert safe == Decimal("0.00")


def test_adversarial_very_large_requested_amount(affordability_engine, simple_states):
    """Very large requested amount is safely capped at buffer."""
    huge_amount = Decimal("1000000000.00")
    min_bal = Decimal("5000.00")
    # Buffer is 3000
    safe = affordability_engine.calculate_amount_safe_to_pay(huge_amount, simple_states, min_bal)
    assert safe == Decimal("3000.00")


def test_adversarial_fractional_cents(affordability_engine):
    """Monetary calculations preserve fractional cents and exact quantize."""
    state = FinancialState(
        dt=pd.Timestamp("2026-09-01"),
        opening_balance=Decimal("5000.55"),
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=Decimal("5000.55"),
    )
    min_bal = Decimal("5000.00")
    safe = affordability_engine.calculate_amount_safe_to_pay(Decimal("10.00"), [state], min_bal)
    assert safe == Decimal("0.55")


def test_adversarial_empty_forecast(affordability_engine):
    """Empty forecast returns 0 safe amount, None for date, unsafe for schedule."""
    assert affordability_engine.calculate_amount_safe_to_pay(Decimal("100.00"), [], Decimal("5000.00")) == Decimal("0.00")
    assert affordability_engine.calculate_earliest_date_for_full_payment(date(2026, 9, 1), Decimal("100.00"), [], Decimal("5000.00")) is None
    res = affordability_engine.validate_payment_schedule([], [(date(2026, 9, 1), Decimal("100.00"))], Decimal("5000.00"))
    assert res.is_safe is False
    assert res.rejection_reason == "empty_baseline_states"


def test_adversarial_same_day_multiple_payments(affordability_engine, simple_states):
    """Multiple payments on the same date accumulate correctly."""
    min_bal = Decimal("5000.00")
    # Lowest balance is 8,000. Two payments of 1,500 on 2026-09-01 sum to 3,000, leaving exactly 5,000 (safe).
    payments = [
        (date(2026, 9, 1), Decimal("1500.00")),
        (date(2026, 9, 1), Decimal("1500.00")),
    ]
    res = affordability_engine.validate_payment_schedule(simple_states, payments, min_bal)
    assert res.is_safe is True
    assert res.min_projected_balance == Decimal("5000.00")

    # Adding 0.01 more violates minimum balance
    payments_viol = [
        (date(2026, 9, 1), Decimal("1500.00")),
        (date(2026, 9, 1), Decimal("1500.01")),
    ]
    res_viol = affordability_engine.validate_payment_schedule(simple_states, payments_viol, min_bal)
    assert res_viol.is_safe is False


# ============================================================
# Section 29: Property / Invariant Tests
# ============================================================

def test_property_safe_amount_bounded(affordability_engine, simple_states):
    """Property: 0 <= safe_amount <= requested_amount."""
    min_bal = Decimal("5000.00")
    for amt in [Decimal("0"), Decimal("100"), Decimal("3000"), Decimal("5000"), Decimal("999999")]:
        safe = affordability_engine.calculate_amount_safe_to_pay(amt, simple_states, min_bal)
        assert Decimal("0.00") <= safe <= amt


def test_property_safe_amount_monotonicity(affordability_engine, simple_states):
    """Property: If X is safe, then every Y where 0 <= Y <= X must also be safe."""
    min_bal = Decimal("5000.00")
    max_safe = affordability_engine.calculate_amount_safe_to_pay(Decimal("10000.00"), simple_states, min_bal)

    # Test monotonic sub-amounts
    for sub_amt in [Decimal("0.00"), Decimal("500.00"), Decimal("1500.00"), max_safe]:
        res = affordability_engine.validate_payment_schedule(
            simple_states, [(date(2026, 9, 1), sub_amt)], min_bal
        )
        assert res.is_safe is True

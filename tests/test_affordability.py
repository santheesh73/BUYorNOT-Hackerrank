"""Unit tests for Phase 6 Affordability & Financial Feasibility Engine."""

from datetime import date
from decimal import Decimal
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
    # Day 0: 10,000
    # Day 1: 8,000 (after 2,000 outflow)
    # Day 2: 8,000
    # Day 3: 15,000 (after 7,000 inflow)
    # Day 4: 12,000 (after 3,000 outflow)
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
# Primitive 1: Immediate Safe Payment (amount_safe_to_pay)
# ============================================================

def test_amount_safe_to_pay_bounds(affordability_engine, simple_states):
    """Safe amount must be bounded between 0 and requested_amount, preserving minimum balance."""
    min_bal = Decimal("5000.00")
    # Minimum closing balance over all days is 8,000. Buffer = 8,000 - 5,000 = 3,000.

    # 1. Requested amount less than buffer
    safe_1 = affordability_engine.calculate_amount_safe_to_pay(Decimal("2000.00"), simple_states, min_bal)
    assert safe_1 == Decimal("2000.00")

    # 2. Requested amount greater than buffer
    safe_2 = affordability_engine.calculate_amount_safe_to_pay(Decimal("5000.00"), simple_states, min_bal)
    assert safe_2 == Decimal("3000.00")

    # 3. Buffer is negative or zero
    safe_3 = affordability_engine.calculate_amount_safe_to_pay(Decimal("1000.00"), simple_states, Decimal("9000.00"))
    assert safe_3 == Decimal("0.00")

    # 4. Zero or negative requested amount
    safe_4 = affordability_engine.calculate_amount_safe_to_pay(Decimal("0.00"), simple_states, min_bal)
    assert safe_4 == Decimal("0.00")

    # 5. Empty baseline states
    safe_5 = affordability_engine.calculate_amount_safe_to_pay(Decimal("1000.00"), [], min_bal)
    assert safe_5 == Decimal("0.00")


# ============================================================
# Primitive 2: Earliest Safe Full-Payment Date
# ============================================================

def test_earliest_date_for_full_payment(affordability_engine, simple_states):
    """Chronologically evaluate earliest date on which full payment is safe."""
    min_bal = Decimal("5000.00")
    req_date = date(2026, 9, 1)

    # If requested amount is 3,000, safe immediately on day 0 (2026-09-01)
    d_safe_now = affordability_engine.calculate_earliest_date_for_full_payment(req_date, Decimal("3000.00"), simple_states, min_bal)
    assert d_safe_now == req_date

    # If requested amount is 6,000:
    # Day 0-2 min balance is 8,000 - 6,000 = 2,000 < 5,000 (unsafe)
    # Day 3 balance rises to 15,000. From Day 3 onward, min balance is 12,000.
    # 12,000 - 6,000 = 6,000 >= 5,000 (safe!)
    # Therefore earliest date is Day 3 (2026-09-04).
    d_safe_later = affordability_engine.calculate_earliest_date_for_full_payment(req_date, Decimal("6000.00"), simple_states, min_bal)
    assert d_safe_later == date(2026, 9, 4)

    # If requested amount is 10,000:
    # Even after Day 3, 12,000 - 10,000 = 2,000 < 5,000. Full payment never becomes safe.
    d_never = affordability_engine.calculate_earliest_date_for_full_payment(req_date, Decimal("10000.00"), simple_states, min_bal)
    assert d_never is None


# ============================================================
# Primitive 3: Multi-Payment Schedule Feasibility Validation
# ============================================================

def test_validate_payment_schedule_safe_and_unsafe(affordability_engine, simple_states):
    """Validate payment schedule simulation returning ScheduleFeasibilityResult."""
    min_bal = Decimal("5000.00")

    # Safe 2-payment schedule: 1,500 on 2026-09-01, 1,500 on 2026-09-04
    safe_schedule = [
        (date(2026, 9, 1), Decimal("1500.00")),
        (date(2026, 9, 4), Decimal("1500.00")),
    ]
    res_safe = affordability_engine.validate_payment_schedule(simple_states, safe_schedule, min_bal)
    assert isinstance(res_safe, ScheduleFeasibilityResult)
    assert res_safe.is_safe is True
    assert res_safe.min_projected_balance >= min_bal
    assert res_safe.first_violation_date is None
    assert res_safe.violation_amount is None
    assert res_safe.total_payment_amount == Decimal("3000.00")

    # Unsafe payment schedule: 4,000 on 2026-09-01 (leaves 8,000 - 4,000 = 4,000 on 2026-09-02, violating 5,000 min bal)
    unsafe_schedule = [(date(2026, 9, 1), Decimal("4000.00"))]
    res_unsafe = affordability_engine.validate_payment_schedule(simple_states, unsafe_schedule, min_bal)
    assert res_unsafe.is_safe is False
    assert res_unsafe.first_violation_date == date(2026, 9, 2)
    assert res_unsafe.violation_amount == Decimal("1000.00")  # 5,000 - 4,000 = 1,000 deficit
    assert res_unsafe.min_projected_balance == Decimal("4000.00")


# ============================================================
# Primitive 4: Minimum Balance Boundary Validation
# ============================================================

def test_validate_minimum_balance(affordability_engine):
    """Test exact minimum balance boundary: balance == min_balance is safe, < is unsafe."""
    min_bal = Decimal("3500.00")

    assert affordability_engine.validate_minimum_balance(Decimal("3500.00"), min_bal) is True
    assert affordability_engine.validate_minimum_balance(Decimal("3500.01"), min_bal) is True
    assert affordability_engine.validate_minimum_balance(Decimal("3499.99"), min_bal) is False


# ============================================================
# Primitive 5: Deadline Boundary Validation
# ============================================================

def test_validate_deadline(affordability_engine):
    """Test completion deadline boundary: <= deadline is valid, > is invalid."""
    deadline = date(2026, 10, 15)

    assert affordability_engine.validate_deadline(date(2026, 10, 15), deadline) is True
    assert affordability_engine.validate_deadline(date(2026, 10, 14), deadline) is True
    assert affordability_engine.validate_deadline(date(2026, 10, 16), deadline) is False


# ============================================================
# Primitive 6: Temporal Cutoff Consistency
# ============================================================

def test_check_temporal_consistency(affordability_engine):
    """Test that events strictly after as_of date trigger temporal inconsistency."""
    class DummyEvent:
        def __init__(self, dt):
            self.settlement_date = dt

    as_of = date(2026, 8, 1)

    valid_events = [DummyEvent(date(2026, 7, 15)), DummyEvent(date(2026, 8, 1))]
    assert affordability_engine.check_temporal_consistency(as_of, valid_events) is True

    leaked_events = [DummyEvent(date(2026, 7, 15)), DummyEvent(date(2026, 8, 2))]
    assert affordability_engine.check_temporal_consistency(as_of, leaked_events) is False

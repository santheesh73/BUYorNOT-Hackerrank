"""Affordability and Financial Feasibility Engine for Phase 6.

Provides core deterministic feasibility primitives:
1. Immediate safe payment calculation (amount_safe_to_pay)
2. Earliest safe full-payment date determination (earliest_date_for_full_payment)
3. Multi-payment schedule simulation and feasibility validation
4. Strict minimum-balance boundary enforcement
5. Strict completion deadline validation
6. Temporal cutoff consistency checking
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Sequence
import pandas as pd

from finance.state import FinancialState
from utils.money import quantize_money


@dataclass(frozen=True)
class ScheduleFeasibilityResult:
    """Detailed financial feasibility outcome for a proposed payment schedule."""

    is_safe: bool
    min_projected_balance: Decimal
    first_violation_date: date | None
    violation_amount: Decimal | None
    total_payment_amount: Decimal
    rejection_reason: str | None = None


class AffordabilityEngine:
    """Deterministic financial feasibility and affordability engine."""

    def __init__(self) -> None:
        pass

    def calculate_amount_safe_to_pay(
        self,
        requested_amount: Decimal,
        baseline_states: Sequence[FinancialState],
        minimum_balance_to_keep: Decimal,
    ) -> Decimal:
        """Calculate the maximum amount safe to pay today before optional spending changes.

        Binds amount between 0 and requested_amount inclusive, ensuring paying this amount
        today preserves the closing balance at or above minimum_balance_to_keep across the
        full 90-day forecast.
        """
        if not baseline_states or requested_amount <= Decimal("0.00"):
            return Decimal("0.00")

        min_closing = min(s.closing_balance for s in baseline_states)
        buffer = min_closing - minimum_balance_to_keep
        safe = max(Decimal("0.00"), min(requested_amount, buffer))
        return quantize_money(safe, 2)

    def calculate_earliest_date_for_full_payment(
        self,
        request_date: date,
        requested_amount: Decimal,
        baseline_states: Sequence[FinancialState],
        minimum_balance_to_keep: Decimal,
    ) -> date | None:
        """Find the earliest chronological date T >= request_date where paying full amount is safe.

        Evaluates dates chronologically. For day T to be safe,
        min(closing_balance for t >= T) - requested_amount >= minimum_balance_to_keep.
        This field represents objective financial capacity and is independent of user payment preferences.
        """
        if not baseline_states:
            return None

        for i, state in enumerate(baseline_states):
            d = state.dt.date()
            if d < request_date:
                continue
            min_balance_after_t = min(s.closing_balance for s in baseline_states[i:])
            if min_balance_after_t - requested_amount >= minimum_balance_to_keep:
                return d
        return None

    def validate_payment_schedule(
        self,
        baseline_states: Sequence[FinancialState],
        payments: Sequence[tuple[date, Decimal]],
        minimum_balance_to_keep: Decimal,
        deadline: date | None = None,
        expected_total: Decimal | None = None,
        spending_relief_by_date: dict[date, Decimal] | None = None,
    ) -> ScheduleFeasibilityResult:
        """Simulate applying plan payments and optional spending relief across daily states.

        Returns ScheduleFeasibilityResult detailing safety, minimum projected balance,
        and first violation if unsafe.
        """
        total_amt = sum((amt for _, amt in payments), Decimal("0.00"))

        # 1. Validate payment amounts: reject negative amounts
        for _, amt in payments:
            if amt < Decimal("0.00"):
                return ScheduleFeasibilityResult(
                    is_safe=False,
                    min_projected_balance=Decimal("0.00"),
                    first_violation_date=None,
                    violation_amount=None,
                    total_payment_amount=total_amt,
                    rejection_reason="negative_payment_amount",
                )

        # 2. Validate chronological order of payment dates
        for i in range(len(payments) - 1):
            if payments[i][0] > payments[i + 1][0]:
                return ScheduleFeasibilityResult(
                    is_safe=False,
                    min_projected_balance=Decimal("0.00"),
                    first_violation_date=payments[i + 1][0],
                    violation_amount=None,
                    total_payment_amount=total_amt,
                    rejection_reason="non_chronological_payment_dates",
                )

        # 3. Validate completion deadline if provided
        if deadline is not None and payments:
            last_date = payments[-1][0]
            if not self.validate_deadline(last_date, deadline):
                return ScheduleFeasibilityResult(
                    is_safe=False,
                    min_projected_balance=Decimal("0.00"),
                    first_violation_date=last_date,
                    violation_amount=None,
                    total_payment_amount=total_amt,
                    rejection_reason="exceeds_completion_deadline",
                )

        # 4. Validate expected total if provided
        if expected_total is not None and total_amt != expected_total:
            return ScheduleFeasibilityResult(
                is_safe=False,
                min_projected_balance=Decimal("0.00"),
                first_violation_date=None,
                violation_amount=abs(total_amt - expected_total),
                total_payment_amount=total_amt,
                rejection_reason="total_amount_mismatch",
            )

        if not baseline_states:
            return ScheduleFeasibilityResult(
                is_safe=False,
                min_projected_balance=Decimal("0.00"),
                first_violation_date=None,
                violation_amount=minimum_balance_to_keep,
                total_payment_amount=total_amt,
                rejection_reason="empty_baseline_states",
            )

        max_forecast_date = baseline_states[-1].dt.date()
        for p_date, _ in payments:
            if p_date > max_forecast_date:
                return ScheduleFeasibilityResult(
                    is_safe=False,
                    min_projected_balance=Decimal("0.00"),
                    first_violation_date=p_date,
                    violation_amount=None,
                    total_payment_amount=total_amt,
                    rejection_reason="payment_beyond_forecast_horizon",
                )

        relief = spending_relief_by_date or {}
        payments_by_date: dict[date, Decimal] = {}
        for d, amt in payments:
            payments_by_date[d] = payments_by_date.get(d, Decimal("0.00")) + amt

        cumulative_payment_impact = Decimal("0.00")
        cumulative_relief_impact = Decimal("0.00")
        min_bal = Decimal("Infinity")
        is_safe = True
        first_violation_date: date | None = None
        violation_amount: Decimal | None = None

        for state in baseline_states:
            d = state.dt.date()
            if d in payments_by_date:
                cumulative_payment_impact += payments_by_date[d]
            if d in relief:
                cumulative_relief_impact += relief[d]

            projected_close = state.closing_balance - cumulative_payment_impact + cumulative_relief_impact
            if projected_close < min_bal:
                min_bal = projected_close

            if not self.validate_minimum_balance(projected_close, minimum_balance_to_keep):
                if is_safe:
                    is_safe = False
                    first_violation_date = d
                    violation_amount = minimum_balance_to_keep - projected_close

        final_min_bal = min_bal if min_bal != Decimal("Infinity") else Decimal("0.00")
        return ScheduleFeasibilityResult(
            is_safe=is_safe,
            min_projected_balance=final_min_bal,
            first_violation_date=first_violation_date,
            violation_amount=violation_amount,
            total_payment_amount=total_amt,
            rejection_reason=None if is_safe else "minimum_balance_violation",
        )

    def validate_minimum_balance(
        self,
        balance: Decimal,
        minimum_balance_to_keep: Decimal,
    ) -> bool:
        """Validate whether a balance respects the minimum balance requirement.

        Boundary:
        balance == minimum_balance_to_keep is SAFE (True).
        balance < minimum_balance_to_keep is UNSAFE (False).
        """
        return balance >= minimum_balance_to_keep

    def validate_deadline(
        self,
        completion_date: date,
        deadline: date,
    ) -> bool:
        """Validate whether a completion date satisfies the required completion deadline.

        Boundary:
        completion_date <= deadline is VALID (True).
        completion_date > deadline is INVALID (False).
        """
        return completion_date <= deadline

    def check_temporal_consistency(
        self,
        as_of: date | pd.Timestamp,
        candidate_events: Sequence[Any],
    ) -> bool:
        """Verify that no candidate event settles strictly after as_of date."""
        as_of_dt = as_of if isinstance(as_of, date) and not isinstance(as_of, pd.Timestamp) else as_of.date() if hasattr(as_of, "date") else as_of
        for ev in candidate_events:
            ev_dt = getattr(ev, "settlement_date", None) or getattr(ev, "dt", None)
            if ev_dt is not None:
                d = ev_dt.date() if hasattr(ev_dt, "date") and not isinstance(ev_dt, date) else ev_dt
                if d > as_of_dt:
                    return False
        return True


# Global default instance and top-level convenience functions
default_affordability_engine = AffordabilityEngine()


def calculate_amount_safe_to_pay(
    requested_amount: Decimal,
    baseline_states: Sequence[FinancialState],
    minimum_balance_to_keep: Decimal,
) -> Decimal:
    """Module-level convenience wrapper for AffordabilityEngine."""
    return default_affordability_engine.calculate_amount_safe_to_pay(
        requested_amount=requested_amount,
        baseline_states=baseline_states,
        minimum_balance_to_keep=minimum_balance_to_keep,
    )


def calculate_earliest_date_for_full_payment(
    request_date: date,
    requested_amount: Decimal,
    baseline_states: Sequence[FinancialState],
    minimum_balance_to_keep: Decimal,
) -> date | None:
    """Module-level convenience wrapper for AffordabilityEngine."""
    return default_affordability_engine.calculate_earliest_date_for_full_payment(
        request_date=request_date,
        requested_amount=requested_amount,
        baseline_states=baseline_states,
        minimum_balance_to_keep=minimum_balance_to_keep,
    )


def simulate_plan_safety(
    baseline_states: Sequence[FinancialState],
    payments: Sequence[tuple[date, Decimal]],
    minimum_balance_to_keep: Decimal,
    spending_relief_by_date: dict[date, Decimal] | None = None,
) -> tuple[bool, Decimal]:
    """Simulate applying plan payments, returning (is_safe, min_projected_balance)."""
    res = default_affordability_engine.validate_payment_schedule(
        baseline_states=baseline_states,
        payments=payments,
        minimum_balance_to_keep=minimum_balance_to_keep,
        spending_relief_by_date=spending_relief_by_date,
    )
    return res.is_safe, res.min_projected_balance

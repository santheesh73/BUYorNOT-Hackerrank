"""Decision and recommendation engine for Phase 5.

Evaluates affordability, safe payment amounts, payment plans (full payment, installments,
partial payment, wait, not recommended), flexible spending changes, and plan ranking.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Sequence
import itertools

import pandas as pd

from data.models import FinancialProfile, PaymentOption, Request
from finance.compat import ChangeAction
from finance.forecast import CashFlowForecaster
from finance.state import FinancialState
from utils.dates import parse_date
from utils.money import quantize_money


@dataclass(frozen=True)
class PlanCandidate:
    """Evaluated payment plan candidate."""

    method: str  # "full_payment" | "installments" | "partial_payment" | "wait" | "not_recommended"
    option_id: str | None
    payments: tuple[tuple[date, Decimal], ...]  # ((date, amount), ...)
    total_amount_paid: Decimal
    first_payment_date: date
    completion_date: date
    spending_changes: tuple[str, ...]  # ("stop:event_id", "reduce_to:event_id:amt")
    completes_by_deadline: bool
    is_safe: bool
    min_projected_balance: Decimal
    number_of_payments: int

    @property
    def formatted_plan(self) -> str:
        if self.method == "not_recommended" or not self.payments:
            return "none"
        return "|".join(f"{d.strftime('%Y-%m-%d')}:{amt}" for d, amt in self.payments)

    @property
    def formatted_spending_changes(self) -> str:
        if not self.spending_changes:
            return "none"
        return "|".join(self.spending_changes)


def calculate_amount_safe_to_pay(
    requested_amount: Decimal,
    baseline_states: Sequence[FinancialState],
    minimum_balance_to_keep: Decimal,
) -> Decimal:
    """Calculate the maximum amount safe to pay today before optional spending changes.

    amount_safe_to_pay is between 0 and requested_amount inclusive, such that paying
    this amount today never drops the closing balance below minimum_balance_to_keep
    over the 90-day forecast.
    """
    if not baseline_states:
        return Decimal("0.00")

    # The payment occurs on day 0 (request_date) and reduces the balance on every day t >= 0
    # Therefore, new_min_balance = min_closing_balance - safe_amount >= minimum_balance_to_keep
    # safe_amount <= min_closing_balance - minimum_balance_to_keep
    min_closing = min(s.closing_balance for s in baseline_states)
    buffer = min_closing - minimum_balance_to_keep
    safe = max(Decimal("0.00"), min(requested_amount, buffer))
    return quantize_money(safe, 2)


def calculate_earliest_date_for_full_payment(
    request_date: date,
    requested_amount: Decimal,
    baseline_states: Sequence[FinancialState],
    minimum_balance_to_keep: Decimal,
) -> date | None:
    """Find the first date T >= request_date where paying requested_amount in full is safe.

    A full payment on date T reduces the closing balance on all days t >= T by requested_amount.
    For day T to be safe, min(closing_balance for t >= T) - requested_amount >= minimum_balance_to_keep.
    """
    for i, state in enumerate(baseline_states):
        d = state.dt.date()
        if d < request_date:
            continue
        min_balance_after_t = min(s.closing_balance for s in baseline_states[i:])
        if min_balance_after_t - requested_amount >= minimum_balance_to_keep:
            return d
    return None


def simulate_plan_safety(
    baseline_states: Sequence[FinancialState],
    payments: Sequence[tuple[date, Decimal]],
    minimum_balance_to_keep: Decimal,
    spending_relief_by_date: dict[date, Decimal] | None = None,
) -> tuple[bool, Decimal]:
    """Simulate applying plan payments and spending relief across the 90-day daily states.

    Returns (is_safe, min_projected_balance).
    """
    relief = spending_relief_by_date or {}
    payments_by_date: dict[date, Decimal] = {}
    for d, amt in payments:
        payments_by_date[d] = payments_by_date.get(d, Decimal("0.00")) + amt

    cumulative_payment_impact = Decimal("0.00")
    cumulative_relief_impact = Decimal("0.00")
    min_bal = Decimal("Infinity")
    is_safe = True

    for state in baseline_states:
        d = state.dt.date()
        if d in payments_by_date:
            cumulative_payment_impact += payments_by_date[d]
        if d in relief:
            cumulative_relief_impact += relief[d]

        projected_close = state.closing_balance - cumulative_payment_impact + cumulative_relief_impact
        if projected_close < min_bal:
            min_bal = projected_close
        if projected_close < minimum_balance_to_keep:
            is_safe = False

    return is_safe, (min_bal if min_bal != Decimal("Infinity") else Decimal("0.00"))


class DecisionEngine:
    """Deterministic financial decision and recommendation engine."""

    def __init__(self, data_store: Any, forecaster: CashFlowForecaster) -> None:
        self.data_store = data_store
        self.forecaster = forecaster

    def evaluate_request(self, request: Request) -> dict[str, Any]:
        """Evaluate a single Request and produce the complete recommendation."""
        user_id = request.user_id
        profile = self.data_store.get_profile(user_id)
        if profile is None:
            raise ValueError(f"Profile not found for user_id={user_id}")

        req_date = request.request_date
        req_amt = request.requested_amount
        min_bal = profile.minimum_balance_to_keep
        deadline = request.desired_completion_date

        # 1. Generate 90-day baseline forecast
        baseline_states = self.forecaster.forecast(user_id, pd.Timestamp(req_date), horizon_days=90)

        # 2. Compute amount_safe_to_pay and earliest_date_for_full_payment
        safe_amount = calculate_amount_safe_to_pay(req_amt, baseline_states, min_bal)
        earliest_full_date = calculate_earliest_date_for_full_payment(req_date, req_amt, baseline_states, min_bal)

        # 3. Collect flexible spending options for the user
        flexible_events = self._get_adjustable_events(profile, req_date)

        # 4. Generate candidate payment plans
        candidates: list[PlanCandidate] = []
        user_methods = set(profile.payment_methods_user_will_consider)

        # Candidate A: Full Payment Today (request_date)
        if "full_payment" in user_methods:
            full_payments = ((req_date, req_amt),)
            safe_now, min_proj = simulate_plan_safety(baseline_states, full_payments, min_bal)
            completes_on_time = req_date <= deadline

            if safe_now:
                candidates.append(
                    PlanCandidate(
                        method="full_payment",
                        option_id=None,
                        payments=full_payments,
                        total_amount_paid=req_amt,
                        first_payment_date=req_date,
                        completion_date=req_date,
                        spending_changes=(),
                        completes_by_deadline=completes_on_time,
                        is_safe=True,
                        min_projected_balance=min_proj,
                        number_of_payments=1,
                    )
                )
            else:
                # Try spending changes to rescue full payment today
                rescued_plan = self._try_spending_changes(
                    baseline_states=baseline_states,
                    payments=full_payments,
                    minimum_balance_to_keep=min_bal,
                    flexible_events=flexible_events,
                    method="full_payment",
                    option_id=None,
                    total_amount_paid=req_amt,
                    first_payment_date=req_date,
                    completion_date=req_date,
                    completes_by_deadline=completes_on_time,
                )
                if rescued_plan:
                    candidates.append(rescued_plan)

        # Candidate B: Installment Options from request_payment_options.csv
        if "installments" in user_methods:
            options = self.data_store.get_payment_options(request.request_id)
            for opt in options:
                if opt.payment_method != "installments":
                    continue
                # Check user max_installment_months constraint
                if profile.max_installment_months is not None:
                    if opt.number_of_payments > profile.max_installment_months:
                        continue

                # Build installment payments schedule
                inst_payments = self._build_installment_schedule(opt)
                if not inst_payments:
                    continue

                last_payment_date = inst_payments[-1][0]
                completes_on_time = last_payment_date <= deadline

                safe_inst, min_proj = simulate_plan_safety(baseline_states, inst_payments, min_bal)
                if safe_inst:
                    candidates.append(
                        PlanCandidate(
                            method="installments",
                            option_id=opt.payment_option_id,
                            payments=inst_payments,
                            total_amount_paid=opt.total_payable_amount,
                            first_payment_date=opt.first_payment_date,
                            completion_date=last_payment_date,
                            spending_changes=(),
                            completes_by_deadline=completes_on_time,
                            is_safe=True,
                            min_projected_balance=min_proj,
                            number_of_payments=opt.number_of_payments,
                        )
                    )
                else:
                    # Try spending changes to rescue installment plan
                    rescued_inst = self._try_spending_changes(
                        baseline_states=baseline_states,
                        payments=inst_payments,
                        minimum_balance_to_keep=min_bal,
                        flexible_events=flexible_events,
                        method="installments",
                        option_id=opt.payment_option_id,
                        total_amount_paid=opt.total_payable_amount,
                        first_payment_date=opt.first_payment_date,
                        completion_date=last_payment_date,
                        completes_by_deadline=completes_on_time,
                    )
                    if rescued_inst:
                        candidates.append(rescued_inst)

        # Candidate C: Partial Payment (exactly 2 payments: safe_today, then remainder on earliest_full_date)
        if (
            request.allows_partial_payment
            and "partial_payment" in user_methods
            and Decimal("0.00") < safe_amount < req_amt
            and earliest_full_date is not None
            and earliest_full_date <= deadline
        ):
            remainder = req_amt - safe_amount
            partial_payments = (
                (req_date, safe_amount),
                (earliest_full_date, remainder),
            )
            safe_partial, min_proj = simulate_plan_safety(baseline_states, partial_payments, min_bal)
            if safe_partial:
                candidates.append(
                    PlanCandidate(
                        method="partial_payment",
                        option_id=None,
                        payments=partial_payments,
                        total_amount_paid=req_amt,
                        first_payment_date=req_date,
                        completion_date=earliest_full_date,
                        spending_changes=(),
                        completes_by_deadline=True,
                        is_safe=True,
                        min_projected_balance=min_proj,
                        number_of_payments=2,
                    )
                )

        # Candidate D: Wait (full payment on earliest_date_for_full_payment)
        if (
            "full_payment" in user_methods
            and earliest_full_date is not None
            and earliest_full_date > req_date
        ):
            wait_payments = ((earliest_full_date, req_amt),)
            safe_wait, min_proj = simulate_plan_safety(baseline_states, wait_payments, min_bal)
            if safe_wait:
                candidates.append(
                    PlanCandidate(
                        method="wait",
                        option_id=None,
                        payments=wait_payments,
                        total_amount_paid=req_amt,
                        first_payment_date=earliest_full_date,
                        completion_date=earliest_full_date,
                        spending_changes=(),
                        completes_by_deadline=(earliest_full_date <= deadline),
                        is_safe=True,
                        min_projected_balance=min_proj,
                        number_of_payments=1,
                    )
                )

        # 5. Filter to safe candidates and rank them
        safe_candidates = [c for c in candidates if c.is_safe]

        # Rank plans according to problem statement rules:
        # 1. Complete the full request by desired_completion_date.
        # 2. Require no spending changes (fewer changes).
        # 3. Minimize the total amount paid.
        # 4. Start payment earlier.
        # 5. Use fewer payments.
        # 6. Lowest payment_option_id.
        def _rank_key(c: PlanCandidate) -> tuple[Any, ...]:
            return (
                0 if c.completes_by_deadline else 1,
                len(c.spending_changes),
                c.total_amount_paid,
                c.first_payment_date,
                c.number_of_payments,
                c.option_id or "zzzz",
            )

        if safe_candidates:
            safe_candidates.sort(key=_rank_key)
            best_plan = safe_candidates[0]
        else:
            # Fallback: not_recommended
            best_plan = PlanCandidate(
                method="not_recommended",
                option_id=None,
                payments=(),
                total_amount_paid=Decimal("0.00"),
                first_payment_date=req_date,
                completion_date=req_date,
                spending_changes=(),
                completes_by_deadline=False,
                is_safe=False,
                min_projected_balance=Decimal("0.00"),
                number_of_payments=0,
            )

        # 6. Determine affordability_status
        if best_plan.method == "not_recommended":
            affordability_status = "not_affordable"
            earliest_str = "" if earliest_full_date is None else earliest_full_date.strftime("%Y-%m-%d")
            # If not recommended, problem statement specifies earliest_date_for_full_payment empty if not safe within forecast
            if earliest_full_date is None:
                earliest_out = ""
            else:
                earliest_out = earliest_full_date.strftime("%Y-%m-%d")
        elif best_plan.method == "wait":
            affordability_status = "affordable_later"
            earliest_out = earliest_full_date.strftime("%Y-%m-%d") if earliest_full_date else ""
        elif best_plan.method == "full_payment" and not best_plan.spending_changes:
            affordability_status = "affordable_now"
            earliest_out = req_date.strftime("%Y-%m-%d")
        else:
            # full_payment with spending changes, installments, or partial_payment
            affordability_status = "affordable_with_plan"
            earliest_out = earliest_full_date.strftime("%Y-%m-%d") if earliest_full_date else req_date.strftime("%Y-%m-%d")

        return {
            "request_id": request.request_id,
            "user_id": user_id,
            "amount_safe_to_pay": safe_amount,
            "affordability_status": affordability_status,
            "recommended_payment_method": best_plan.method,
            "payment_plan": best_plan.formatted_plan,
            "earliest_date_for_full_payment": earliest_out,
            "spending_changes_needed": best_plan.formatted_spending_changes,
            "selected_plan": best_plan,
            "profile": profile,
            "request": request,
        }

    def _build_installment_schedule(self, opt: PaymentOption) -> tuple[tuple[date, Decimal], ...]:
        """Build explicit chronological dates and amounts for an installment offer."""
        payments: list[tuple[date, Decimal]] = []
        d = opt.first_payment_date
        freq_days = opt.payment_frequency_days or 30
        for _ in range(opt.number_of_payments):
            payments.append((d, opt.payment_amount))
            d = d + pd.Timedelta(days=freq_days).to_pytimedelta()
        return tuple(payments)

    def _get_adjustable_events(
        self, profile: FinancialProfile, request_date: date
    ) -> list[dict[str, Any]]:
        """Identify flexible historical/recurring events eligible for stopping or reduction."""
        raw_events = self.data_store.get_user_events(profile.user_id)
        protected_cats = set(c.lower() for c in profile.expense_categories_to_protect)
        stop_cats = set(c.lower() for c in profile.expense_categories_user_is_willing_to_stop)
        reduce_cats = set(c.lower() for c in profile.expense_categories_user_is_willing_to_reduce)

        adjustable: list[dict[str, Any]] = []
        candidate_events = sorted(
            [e for e in raw_events if e.settlement_date is not None and e.settlement_date <= request_date and e.direction == "debit" and e.amount],
            key=lambda x: (x.settlement_date, x.event_id),
            reverse=True,
        )

        seen_cats: set[str] = set()
        for ev in candidate_events:
            cat = ev.category.lower()
            if cat in protected_cats:
                continue
            if cat in seen_cats:
                continue

            flex = (ev.flexibility or "fixed").lower()
            can_stop = (cat in stop_cats) and ("stop" in flex)
            can_reduce = (cat in reduce_cats) and ("reduc" in flex) and (ev.minimum_allowed_amount is not None)

            if not (can_stop or can_reduce):
                continue
            seen_cats.add(cat)

            adjustable.append({
                "event_id": ev.event_id,
                "category": ev.category,
                "amount": ev.amount,
                "can_stop": can_stop,
                "can_reduce": can_reduce,
                "min_amount": ev.minimum_allowed_amount,
                "description": ev.description,
            })
        return adjustable

    def _try_spending_changes(
        self,
        baseline_states: Sequence[FinancialState],
        payments: tuple[tuple[date, Decimal], ...],
        minimum_balance_to_keep: Decimal,
        flexible_events: list[dict[str, Any]],
        method: str,
        option_id: str | None,
        total_amount_paid: Decimal,
        first_payment_date: date,
        completion_date: date,
        completes_by_deadline: bool,
    ) -> PlanCandidate | None:
        """Explore stopping or reducing up to 3 flexible events to achieve financial safety."""
        if not flexible_events:
            return None

        # Build list of possible single actions
        possible_actions: list[tuple[str, dict[str, Any]]] = []
        for fe in flexible_events:
            if fe["can_stop"]:
                possible_actions.append(("stop", fe))
            if fe["can_reduce"]:
                possible_actions.append(("reduce_to", fe))

        best_rescued: PlanCandidate | None = None

        # Try 1, 2, then 3 actions
        for k in range(1, min(4, len(possible_actions) + 1)):
            for action_combo in itertools.combinations(possible_actions, k):
                # Ensure each event is modified at most once
                event_ids = set(a[1]["event_id"] for a in action_combo)
                if len(event_ids) != len(action_combo):
                    continue

                # Calculate relief across the 90 days
                # When a recurring/scheduled event is stopped or reduced, relief applies on its occurrences
                relief_by_date: dict[date, Decimal] = {}
                formatted_changes: list[str] = []

                for act_type, fe in action_combo:
                    ev_id = fe["event_id"]
                    if act_type == "stop":
                        formatted_changes.append(f"stop:{ev_id}")
                        saving_per_occurrence = fe["amount"]
                    else:
                        min_amt = fe["min_amount"]
                        formatted_changes.append(f"reduce_to:{ev_id}:{min_amt}")
                        saving_per_occurrence = fe["amount"] - min_amt

                    # Apply relief on all projected occurrences of this category
                    cat_lower = fe["category"].lower()
                    for state in baseline_states:
                        d = state.dt.date()
                        # Relief accumulates daily for the ongoing saved recurring expenses
                        # Conservative model: apply daily amortized or periodic relief
                        relief_by_date[d] = relief_by_date.get(d, Decimal("0.00")) + (saving_per_occurrence / Decimal("30.0"))

                is_safe, min_proj = simulate_plan_safety(
                    baseline_states=baseline_states,
                    payments=payments,
                    minimum_balance_to_keep=minimum_balance_to_keep,
                    spending_relief_by_date=relief_by_date,
                )

                if is_safe:
                    candidate = PlanCandidate(
                        method=method,
                        option_id=option_id,
                        payments=payments,
                        total_amount_paid=total_amount_paid,
                        first_payment_date=first_payment_date,
                        completion_date=completion_date,
                        spending_changes=tuple(formatted_changes),
                        completes_by_deadline=completes_by_deadline,
                        is_safe=True,
                        min_projected_balance=min_proj,
                        number_of_payments=len(payments),
                    )
                    return candidate

        return None

"""Decision explanation generator matching sample_requests.csv reference style."""

from datetime import date
from decimal import Decimal
from typing import Any

from data.models import FinancialProfile, Request
from finance.decision import PlanCandidate
from utils.dates import parse_date


def _format_money(amount: Decimal) -> str:
    """Format decimal amount with commas and proper precision."""
    # If it's an integer, format as integer
    if amount == amount.to_integral():
        return f"{int(amount):,}"
    # Otherwise format with up to 2 decimal places, removing trailing zeros if needed
    s = f"{amount:,.2f}"
    if s.endswith(".00"):
        return s[:-3]
    return s


def _format_date(d: date) -> str:
    """Format date as 'D Month YYYY' (e.g., '15 November 2019')."""
    return f"{d.day} {d.strftime('%B')} {d.year}"


def generate_decision_explanation(
    request: Request,
    profile: FinancialProfile,
    eval_result: dict[str, Any],
) -> str:
    """Generate concise, factual decision explanation for a recommendation."""
    curr = profile.home_currency
    req_amt = request.requested_amount
    min_bal = profile.minimum_balance_to_keep
    safe_amt = eval_result["amount_safe_to_pay"]
    status = eval_result["affordability_status"]
    method = eval_result["recommended_payment_method"]
    selected_plan: PlanCandidate = eval_result["selected_plan"]

    if status == "affordable_now":
        min_proj = max(min_bal, selected_plan.min_projected_balance)
        return (
            f"Pay {curr} {_format_money(req_amt)} today. "
            f"This leaves at least {curr} {_format_money(min_proj)} available over the next 90 days."
        )

    elif status == "affordable_with_plan":
        if method == "installments" and selected_plan.payments:
            n = selected_plan.number_of_payments
            first_amt = selected_plan.payments[0][1]
            first_dt_str = _format_date(selected_plan.first_payment_date)
            min_proj = max(min_bal, selected_plan.min_projected_balance)
            return (
                f"Use {n} installments of {curr} {_format_money(first_amt)}, starting {first_dt_str}. "
                f"This leaves at least {curr} {_format_money(min_proj)} available."
            )

        elif method == "partial_payment" and len(selected_plan.payments) == 2:
            pay1_date, pay1_amt = selected_plan.payments[0]
            pay2_date, pay2_amt = selected_plan.payments[1]
            pay2_date_str = _format_date(pay2_date)
            return (
                f"Pay {curr} {_format_money(pay1_amt)} today and the remaining {curr} {_format_money(pay2_amt)} "
                f"on {pay2_date_str}. This completes the full request and keeps the {curr} {_format_money(min_bal)} "
                f"minimum protected."
            )

        elif method == "full_payment" and selected_plan.spending_changes:
            # Action description
            actions_desc: list[str] = []
            for sc in selected_plan.spending_changes:
                parts = sc.split(":")
                ev_id = parts[1]
                event = getattr(profile, "_events_by_id", {}).get(ev_id)
                ev_desc = event.description.lower() if event else "subscription"
                if parts[0] == "stop":
                    actions_desc.append(f"Stop the {ev_desc}")
                else:
                    new_amt = Decimal(parts[2])
                    actions_desc.append(f"reduce the {ev_desc} to {curr} {_format_money(new_amt)}")

            action_str = " and ".join(actions_desc)
            return (
                f"{action_str}, then pay {curr} {_format_money(req_amt)} today. "
                f"This leaves at least {curr} {_format_money(min_bal)} available."
            )

        else:
            return (
                f"Proceed with {method.replace('_', ' ')}. "
                f"This keeps the {curr} {_format_money(min_bal)} minimum protected."
            )

    elif status == "affordable_later" or method == "wait":
        earliest_str = eval_result["earliest_date_for_full_payment"]
        if earliest_str:
            d = parse_date(earliest_str)
            d_str = _format_date(d) if d else earliest_str
        else:
            d_str = "a later date"
        return (
            f"Pay {curr} {_format_money(req_amt)} in full on {d_str}. "
            f"Paying earlier would take the balance below the {curr} {_format_money(min_bal)} minimum."
        )

    else:  # not_affordable / not_recommended
        deadline_str = _format_date(request.desired_completion_date)
        if safe_amt > Decimal("0.00"):
            return (
                f"Do not proceed with the {curr} {_format_money(req_amt)} request. "
                f"Although {curr} {_format_money(safe_amt)} is available today, the full amount cannot "
                f"be completed safely within 90 days."
            )
        else:
            return (
                f"Do not make this payment by {deadline_str}. "
                f"None of the available options keeps the {curr} {_format_money(min_bal)} minimum protected."
            )

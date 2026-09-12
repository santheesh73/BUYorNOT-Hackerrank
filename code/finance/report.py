"""Phase 4 report generation and diagnostic formatting."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from finance.compat import FX
from finance.forecast import CashFlowForecaster


@dataclass(frozen=True)
class Phase4Report:
    """Exact Phase 4 report dataclass required by project specification."""

    users_forecastable: int

    historical_cash_event_count: int
    projected_cash_event_count: int

    weekly_pattern_count: int
    biweekly_pattern_count: int
    monthly_pattern_count: int
    other_pattern_count: int

    forecast_state_count: int
    forecast_cash_event_count: int

    minimum_projected_balance: Decimal | None
    maximum_projected_balance: Decimal | None
    negative_balance_count: int

    future_information_leak_count: int
    invalid_forecast_date_count: int

    error_count: int
    warning_count: int

    status: str


def build_phase4_report(
    data_store: Any,
    error_count: int = 0,
    warning_count: int = 0,
) -> Phase4Report:
    """Construct Phase4Report across all evaluation requests in data_store."""
    fx = getattr(data_store, "fx", None) or FX()
    forecaster = CashFlowForecaster(data_store=data_store, fx=fx)

    requests = data_store.get_all_requests()
    users_seen: set[str] = set()

    total_historical_events = 0
    total_projected_events = 0
    total_forecast_states = 0
    total_forecast_events = 0

    weekly_patterns = 0
    biweekly_patterns = 0
    monthly_patterns = 0
    other_patterns = 0

    min_proj_balance: Decimal | None = None
    max_proj_balance: Decimal | None = None
    negative_balance_count = 0

    future_leaks = 0
    invalid_dates = 0

    for req in requests:
        user_id = req.user_id
        users_seen.add(user_id)
        as_of = pd.Timestamp(req.request_date)

        # Generate future cash events
        cash_events = forecaster.future_cash_events(user_id, as_of=as_of, horizon_days=90)
        total_forecast_events += len(cash_events)

        projected = [e for e in cash_events if e.source == "projected"]
        scheduled = [e for e in cash_events if e.source == "scheduled"]
        total_projected_events += len(projected)

        # Check temporal correctness
        for e in cash_events:
            if e.dt < as_of:
                future_leaks += 1
            if e.dt > as_of + pd.Timedelta(days=90):
                invalid_dates += 1

        # Count historical events
        raw_events = data_store.get_user_events(user_id)
        as_of_d = as_of.date() if hasattr(as_of, "date") else as_of
        hist_events = [e for e in raw_events if (e.event_date if isinstance(e.event_date, date) else e.event_date) <= as_of_d]
        total_historical_events += len(hist_events)

        # Run 90-day balance simulation
        states = forecaster.forecast(user_id, as_of=as_of, horizon_days=90)
        total_forecast_states += len(states)

        for s in states:
            if s.dt < as_of or s.dt > as_of + pd.Timedelta(days=90):
                invalid_dates += 1
            if min_proj_balance is None or s.closing_balance < min_proj_balance:
                min_proj_balance = s.closing_balance
            if max_proj_balance is None or s.closing_balance > max_proj_balance:
                max_proj_balance = s.closing_balance

        if forecaster.detect_negative_balance(states):
            negative_balance_count += 1

        # Count patterns
        patterns = forecaster.get_user_patterns(user_id, as_of=as_of)
        for p in patterns:
            if p.interval_days == 7:
                weekly_patterns += 1
            elif p.interval_days == 14:
                biweekly_patterns += 1
            elif p.interval_days == 30:
                monthly_patterns += 1
            else:
                other_patterns += 1

    status = "PASS" if error_count == 0 and future_leaks == 0 and invalid_dates == 0 else "FAIL"

    return Phase4Report(
        users_forecastable=len(users_seen),
        historical_cash_event_count=total_historical_events,
        projected_cash_event_count=total_projected_events,
        weekly_pattern_count=weekly_patterns,
        biweekly_pattern_count=biweekly_patterns,
        monthly_pattern_count=monthly_patterns,
        other_pattern_count=other_patterns,
        forecast_state_count=total_forecast_states,
        forecast_cash_event_count=total_forecast_events,
        minimum_projected_balance=min_proj_balance,
        maximum_projected_balance=max_proj_balance,
        negative_balance_count=negative_balance_count,
        future_information_leak_count=future_leaks,
        invalid_forecast_date_count=invalid_dates,
        error_count=error_count,
        warning_count=warning_count,
        status=status,
    )


def format_phase4_report(report: Phase4Report) -> str:
    """Format Phase4Report matching exact specification in §35."""
    min_bal_str = f"{report.minimum_projected_balance:,.2f}" if report.minimum_projected_balance is not None else "0.00"
    max_bal_str = f"{report.maximum_projected_balance:,.2f}" if report.maximum_projected_balance is not None else "0.00"

    lines = [
        "FINANCIAL FORECAST",
        "==================",
        "",
        f"Users forecastable: {report.users_forecastable}",
        "",
        f"Historical cash events: {report.historical_cash_event_count}",
        f"Projected cash events: {report.projected_cash_event_count}",
        "",
        "Recurring patterns:",
        f"- Weekly: {report.weekly_pattern_count}",
        f"- Biweekly: {report.biweekly_pattern_count}",
        f"- Monthly: {report.monthly_pattern_count}",
        f"- Other: {report.other_pattern_count}",
        "",
        "Forecast:",
        "- Horizon days: 90",
        f"- Forecast states: {report.forecast_state_count}",
        f"- Forecast cash events: {report.forecast_cash_event_count}",
        "",
        "BALANCE",
        f"- Minimum projected balance: {min_bal_str}",
        f"- Maximum projected balance: {max_bal_str}",
        f"- Negative-balance forecasts: {report.negative_balance_count}",
        "",
        "TEMPORAL VALIDATION",
        f"- Future-information leaks: {report.future_information_leak_count}",
        f"- Invalid forecast dates: {report.invalid_forecast_date_count}",
        "",
        "VALIDATION",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        "",
        "RESULT",
        f"Phase 4 status: {report.status}",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class Phase5Report:
    """Exact Phase 5 report dataclass conforming to Section 44 specification."""

    requests_evaluated: int
    affordable_now_count: int
    affordable_with_plan_count: int
    affordable_later_count: int
    not_affordable_count: int

    full_payment_count: int
    partial_payment_count: int
    installments_count: int
    wait_count: int
    not_recommended_count: int

    candidates_generated: int
    candidates_validated: int
    candidates_rejected: int

    safety_violations: int
    deadline_violations: int
    preference_violations: int
    payment_plan_violations: int
    spending_change_violations: int
    explanation_inconsistencies: int
    temporal_leaks: int

    output_requests: int
    output_rows: int
    output_columns: int

    status: str


def build_phase5_report(
    decisions: list[Any],
    decision_engine: Any,
    output_rows: int = 250,
    output_columns: int = 8,
) -> Phase5Report:
    """Construct Phase5Report from actual evaluation results and engine metrics."""
    import collections
    status_counts = collections.Counter(d.affordability_status for d in decisions)
    method_counts = collections.Counter(d.recommended_payment_method for d in decisions)

    has_errors = (
        decision_engine.safety_violations_count > 0
        or decision_engine.deadline_violations_count > 0
        or decision_engine.preference_violations_count > 0
        or decision_engine.payment_plan_violations_count > 0
        or decision_engine.spending_change_violations_count > 0
        or decision_engine.explanation_inconsistencies_count > 0
        or decision_engine.temporal_leaks_count > 0
        or len(decisions) != output_rows
    )

    return Phase5Report(
        requests_evaluated=len(decisions),
        affordable_now_count=status_counts["affordable_now"],
        affordable_with_plan_count=status_counts["affordable_with_plan"],
        affordable_later_count=status_counts["affordable_later"],
        not_affordable_count=status_counts["not_affordable"],
        full_payment_count=method_counts["full_payment"],
        partial_payment_count=method_counts["partial_payment"],
        installments_count=method_counts["installments"],
        wait_count=method_counts["wait"],
        not_recommended_count=method_counts["not_recommended"],
        candidates_generated=decision_engine.candidates_generated_count,
        candidates_validated=decision_engine.candidates_validated_count,
        candidates_rejected=decision_engine.candidates_rejected_count,
        safety_violations=decision_engine.safety_violations_count,
        deadline_violations=decision_engine.deadline_violations_count,
        preference_violations=decision_engine.preference_violations_count,
        payment_plan_violations=decision_engine.payment_plan_violations_count,
        spending_change_violations=decision_engine.spending_change_violations_count,
        explanation_inconsistencies=decision_engine.explanation_inconsistencies_count,
        temporal_leaks=decision_engine.temporal_leaks_count,
        output_requests=len(decisions),
        output_rows=output_rows,
        output_columns=output_columns,
        status="FAIL" if has_errors else "PASS",
    )


def format_phase5_report(report: Phase5Report) -> str:
    """Format Phase5Report conforming strictly to Section 44 CLI layout."""
    lines = [
        "DECISION ENGINE",
        "===============",
        "",
        f"Requests evaluated: {report.requests_evaluated}",
        "",
        "AFFORDABILITY",
        f"- Affordable now: {report.affordable_now_count}",
        f"- Affordable with plan: {report.affordable_with_plan_count}",
        f"- Affordable later: {report.affordable_later_count}",
        f"- Not affordable: {report.not_affordable_count}",
        "",
        "RECOMMENDATIONS",
        f"- Full payment: {report.full_payment_count}",
        f"- Partial payment: {report.partial_payment_count}",
        f"- Installments: {report.installments_count}",
        f"- Wait: {report.wait_count}",
        f"- Not recommended: {report.not_recommended_count}",
        "",
        "PLANS",
        f"- Candidates generated: {report.candidates_generated}",
        f"- Candidates validated: {report.candidates_validated}",
        f"- Candidates rejected: {report.candidates_rejected}",
        "",
        "VALIDATION",
        f"- Safety violations: {report.safety_violations}",
        f"- Deadline violations: {report.deadline_violations}",
        f"- Preference violations: {report.preference_violations}",
        f"- Payment-plan violations: {report.payment_plan_violations}",
        f"- Spending-change violations: {report.spending_change_violations}",
        f"- Explanation inconsistencies: {report.explanation_inconsistencies}",
        f"- Temporal leaks: {report.temporal_leaks}",
        "",
        "OUTPUT",
        f"- Requests: {report.output_requests}",
        f"- Output rows: {report.output_rows}",
        f"- Output columns: {report.output_columns}",
        "",
        "RESULT",
        f"Phase 5 status: {report.status}",
    ]
    return "\n".join(lines)


"""Phase 4 report generation and diagnostic formatting."""

from dataclasses import dataclass
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
        hist_events = [e for e in raw_events if pd.to_datetime(e.event_date) <= as_of]
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

"""Recurring cash-flow pattern detection for Phase 4."""

from collections import defaultdict
from decimal import Decimal
import statistics
from typing import Sequence

import pandas as pd

from finance.compat import CashEvent
from finance.state import RecurringPattern


def _advance_month(dt: pd.Timestamp, day: int) -> pd.Timestamp:
    """Advance timestamp by 1 month preserving day of month (clamping if necessary)."""
    year = dt.year
    month = dt.month + 1
    if month > 12:
        month = 1
        year += 1
    # Find max days in target month
    import calendar
    max_days = calendar.monthrange(year, month)[1]
    target_day = min(day, max_days)
    return pd.Timestamp(year=year, month=month, day=target_day, hour=dt.hour, minute=dt.minute, second=dt.second)


class RecurringPatternDetector:
    """Identifies genuine, conservative recurring financial patterns from historical CashEvents."""

    def detect_recurring_patterns(
        self,
        events: Sequence[CashEvent],
        as_of: pd.Timestamp,
    ) -> list[RecurringPattern]:
        """Detect recurring cash-flow patterns supported by history strictly on or before as_of."""
        # 1. Filter events occurring on or before as_of
        as_of_dt = pd.to_datetime(as_of)
        history = [e for e in events if e.dt <= as_of_dt and e.amount != Decimal("0")]

        # 2. Group by (category, direction)
        grouped: dict[tuple[str, str], list[CashEvent]] = defaultdict(list)
        for ev in history:
            direction = "credit" if ev.amount > 0 else "debit"
            grouped[(ev.category.lower(), direction)].append(ev)

        patterns: list[RecurringPattern] = []

        # 3. Analyze each candidate group
        for (cat, direction), cat_events in sorted(grouped.items()):
            # Must have at least 2 historical occurrences to infer recurrence
            if len(cat_events) < 2:
                continue

            # Sort chronologically
            sorted_evs = sorted(cat_events, key=lambda x: (x.dt, x.event_id))
            dates = [e.dt for e in sorted_evs]

            # Compute intervals in days between consecutive occurrences
            intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            if not intervals:
                continue

            avg_interval = sum(intervals) / len(intervals)
            stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0.0

            # Determine frequency
            is_weekly = (6 <= avg_interval <= 8) and (stdev <= 2.5)
            is_biweekly = (13 <= avg_interval <= 16) and (stdev <= 3.0)
            is_monthly = (27 <= avg_interval <= 33) and (stdev <= 4.0)

            if not (is_weekly or is_biweekly or is_monthly):
                # Irregular or single occurrences: do not promote to recurring pattern
                continue

            # Determine interval days and interval type
            if is_weekly:
                interval_days = 7
            elif is_biweekly:
                interval_days = 14
            else:
                interval_days = 30

            # Infer conservative amount
            amounts = [abs(e.amount) for e in sorted_evs]
            # Use mode if unique, else median
            try:
                inferred_amount = statistics.mode(amounts)
            except statistics.StatisticsError:
                inferred_amount = statistics.median(amounts)

            # Determine next occurrence strictly > as_of_dt
            last_dt = dates[-1]
            next_dt = last_dt
            day_of_month = last_dt.day

            while next_dt <= as_of_dt:
                if is_monthly:
                    next_dt = _advance_month(next_dt, day_of_month)
                else:
                    next_dt = next_dt + pd.Timedelta(days=interval_days)

            pattern_id = f"rec_{cat}_{direction}_{len(patterns) + 1:02d}"
            source_ids = tuple(e.event_id for e in sorted_evs if e.event_id)

            patterns.append(
                RecurringPattern(
                    pattern_id=pattern_id,
                    category=cat,
                    direction=direction,
                    amount=Decimal(str(inferred_amount)),
                    interval_days=interval_days,
                    next_occurrence=next_dt,
                    source_event_ids=source_ids,
                )
            )

        # Return deterministically ordered patterns
        return sorted(patterns, key=lambda p: (p.category, p.direction, p.pattern_id))

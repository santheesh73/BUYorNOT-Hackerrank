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

        # 2. Group events: isolate regular salary streams from one-off credits
        grouped: dict[tuple[str, str, str | None], list[CashEvent]] = defaultdict(list)
        for ev in history:
            cat_lower = ev.category.lower()
            desc_lower = (ev.description or "").lower()
            direction = "credit" if ev.amount > 0 else "debit"

            if cat_lower == "salary" and direction == "credit":
                # Exclude one-off bonuses, commissions, arrears, windfalls, temporary/seasonal/overtime items
                if any(k in desc_lower for k in [
                    "bonus", "arrears", "commission", "seasonal", "temporary", "prorated",
                    "payout", "earnings", "overtime", "performance", "net salary"
                ]):
                    continue

            grouped[(cat_lower, direction)].append(ev)

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
            med_interval = statistics.median(intervals)
            stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0.0

            # Count intervals matching standard frequencies with non-overlapping tolerances
            # 5-day cycle is strictly for workday transport commute
            is_every_5d = (cat == "transport") and (
                ((4 <= avg_interval <= 6) and (stdev <= 1.5))
                or (sum(1 for iv in intervals if abs(iv - 5) <= 1) >= max(2, int(0.6 * len(intervals))))
            )
            is_weekly = ((6 <= avg_interval <= 8) and (stdev <= 2.5)) or (
                sum(1 for iv in intervals if abs(iv - 7) <= 1) >= max(2, int(0.6 * len(intervals)))
            )
            is_every_10d = (cat in ("groceries", "dining")) and (
                ((9 <= avg_interval <= 11) and (stdev <= 2.0))
                or (sum(1 for iv in intervals if abs(iv - 10) <= 1) >= max(2, int(0.6 * len(intervals))))
            )
            is_biweekly = ((13 <= avg_interval <= 16) and (stdev <= 3.0)) or (
                sum(1 for iv in intervals if abs(iv - 14) <= 1) >= max(2, int(0.6 * len(intervals)))
            )
            is_every_21d = ((20 <= avg_interval <= 22) and (stdev <= 3.0)) or (
                sum(1 for iv in intervals if abs(iv - 21) <= 1) >= max(2, int(0.6 * len(intervals)))
            )
            is_monthly = ((27 <= avg_interval <= 33) and (stdev <= 4.0)) or (
                sum(1 for iv in intervals if abs(iv - 30) <= 2) >= max(2, int(0.6 * len(intervals)))
            )

            if not (is_every_5d or is_weekly or is_every_10d or is_biweekly or is_every_21d or is_monthly):
                # Irregular or single occurrences: do not promote to recurring pattern
                continue

            # Determine interval days and interval type
            if is_every_5d:
                interval_days = 5
            elif is_weekly:
                interval_days = 7
            elif is_every_10d:
                interval_days = 10
            elif is_biweekly:
                interval_days = 14
            elif is_every_21d:
                interval_days = 21
            else:
                interval_days = 30

            # If an income stream has missed its latest expected cycle, it is no longer active
            if direction == "credit":
                days_since_last = (as_of_dt - dates[-1]).days
                if days_since_last > max(interval_days + 7, 35):
                    continue

            # Infer conservative amount: use mode if repeated, else median
            amounts = [abs(e.amount) for e in sorted_evs]
            from collections import Counter
            counts = Counter(amounts)
            most_common = counts.most_common(2)
            if most_common and most_common[0][1] > 1 and (len(most_common) == 1 or most_common[0][1] > most_common[1][1]):
                inferred_amount = most_common[0][0]
            else:
                inferred_amount = Decimal(str(statistics.median(amounts)))

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

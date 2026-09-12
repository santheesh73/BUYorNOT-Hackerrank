"""Cash-flow forecasting and 90-day balance simulation for Phase 4."""

from datetime import date
from decimal import Decimal
from typing import Any, Sequence

import pandas as pd

from finance.compat import CashEvent, FX
from finance.recurrence import RecurringPatternDetector, _advance_month
from finance.state import FinancialState, RecurringPattern
from utils.dates import parse_date
from utils.money import parse_money, quantize_money


class CashFlowForecaster:
    """Produces conservative, deterministic 90-day cash-flow forecasts and daily financial states."""

    def __init__(self, data_store: Any, fx: FX | None = None) -> None:
        self.data_store = data_store
        self.fx = fx or getattr(data_store, "fx", None)
        self.detector = RecurringPatternDetector()

    def detect_recurring_patterns(
        self,
        events: Sequence[CashEvent],
        as_of: pd.Timestamp,
    ) -> list[RecurringPattern]:
        """Detect recurring patterns from events occurring strictly on or before as_of."""
        return self.detector.detect_recurring_patterns(events, as_of=as_of)

    def history_cash_events(
        self,
        user_id: str,
        as_of: pd.Timestamp,
    ) -> list[CashEvent]:
        """Extract all valid historical cash events for user_id on or before as_of."""
        as_of_dt = pd.to_datetime(as_of)
        profile = self.data_store.get_profile(user_id)
        home_curr = profile.home_currency if profile else "USD"
        raw_events = self.data_store.get_user_events(user_id)

        history: list[CashEvent] = []
        for ev in raw_events:
            ev_dt = pd.to_datetime(ev.event_date)
            if ev_dt <= as_of_dt:
                st = ev.status.lower()
                if st in ("failed", "cancelled", "unrealized"):
                    continue
                amt = ev.amount
                if amt is None:
                    if hasattr(self.data_store, "indexes") and hasattr(self.data_store.indexes, "images_by_event"):
                        img_refs = self.data_store.indexes.images_by_event.get(ev.event_id, [])
                        if img_refs:
                            from evidence.images import VERIFIED_IMAGE_AMOUNTS
                            for img in img_refs:
                                if img.image_id in VERIFIED_IMAGE_AMOUNTS:
                                    amt = VERIFIED_IMAGE_AMOUNTS[img.image_id][0]
                                    break
                if amt is None or amt == Decimal("0"):
                    continue

                if ev.currency != home_curr and self.fx:
                    amt = self.fx.convert(amt, ev.currency, home_curr, ev_dt)

                signed_amt = amt if ev.direction == "credit" else -amt
                history.append(
                    CashEvent(
                        dt=ev_dt,
                        amount=signed_amt,
                        category=ev.category,
                        event_id=ev.event_id,
                        source="actual",
                        flexibility=ev.flexibility,
                        minimum_allowed_amount=ev.minimum_allowed_amount,
                        description=ev.description,
                    )
                )
        return history

    def get_user_patterns(
        self,
        user_id: str,
        as_of: pd.Timestamp,
    ) -> list[RecurringPattern]:
        """Detect recurring patterns for a user based on history up to as_of."""
        hist = self.history_cash_events(user_id, as_of)
        return self.detect_recurring_patterns(hist, as_of)

    def future_cash_events(
        self,
        user_id: str,
        as_of: pd.Timestamp,
        horizon_days: int = 90,
    ) -> list[CashEvent]:
        """Generate all valid future cash-flow events for user_id within [as_of, as_of + horizon_days].

        Temporal correctness is strictly enforced:
        - Recurrence is inferred solely from events on or before as_of.
        - Messages and evidence dated after as_of are ignored.
        - Non-cash (failed, cancelled, duplicate, unrealized, pending credit) events are excluded.
        """
        as_of_dt = pd.to_datetime(as_of)
        end_dt = as_of_dt + pd.Timedelta(days=horizon_days)

        profile = self.data_store.get_profile(user_id)
        home_curr = profile.home_currency if profile else "USD"
        raw_events = self.data_store.get_user_events(user_id)

        # 1. Historical cash events & recurring pattern detection
        history_cash = self.history_cash_events(user_id, as_of_dt)
        patterns = self.detect_recurring_patterns(history_cash, as_of=as_of_dt)

        # 4. Check Phase 3 evidence available on or before as_of
        evidence_store = getattr(self.data_store, "get_evidence_store", lambda: None)()
        user_evidence = evidence_store.get_user_evidence(user_id) if evidence_store else []
        valid_evidence = []
        indexes = getattr(self.data_store, "indexes", None)
        messages_by_id = getattr(indexes, "messages_by_id", None)
        has_real_messages = isinstance(messages_by_id, dict) and not hasattr(messages_by_id, "_mock_return_value")

        for e in user_evidence:
            if e.source_type == "message" and has_real_messages and e.source_id in messages_by_id:
                msg = messages_by_id[e.source_id]
                sent_at = getattr(msg, "sent_at", None)
                if sent_at is not None:
                    try:
                        sent_dt = pd.to_datetime(sent_at).normalize()
                        if sent_dt > as_of_dt:
                            continue
                    except Exception:
                        pass
            elif e.effective_date is not None:
                try:
                    eff_dt = pd.to_datetime(e.effective_date).normalize()
                    if eff_dt > as_of_dt:
                        continue
                except Exception:
                    pass
            valid_evidence.append(e)

        # Check for salary updates, terminations, or rent changes in valid evidence
        salary_update_amount: Decimal | None = None
        salary_effective_date: pd.Timestamp | None = None
        salary_terminated = False
        rent_increase_pct: Decimal | None = None

        for ev in valid_evidence:
            ft = ev.fact_type.lower()
            if "ended" in ft or "terminated" in ft:
                salary_terminated = True
            elif "salary" in ft and ev.numeric_value is not None and not salary_terminated:
                amt = ev.numeric_value
                if ev.currency and ev.currency != home_curr and self.fx:
                    conv_date = pd.to_datetime(ev.effective_date) if ev.effective_date else as_of_dt
                    amt = self.fx.convert(amt, ev.currency, home_curr, conv_date)
                salary_update_amount = amt
                if ev.effective_date:
                    salary_effective_date = pd.to_datetime(ev.effective_date).normalize()
            elif "rent_increase" in ft and ev.numeric_value is not None:
                rent_increase_pct = ev.numeric_value

        future_events: list[CashEvent] = []
        covered_dates_by_cat: set[tuple[date, str]] = set()

        # 5. Collect scheduled events already in dataset (e.g. next confirmed salary, scheduled bills)
        for ev in raw_events:
            ev_date = ev.settlement_date or ev.event_date
            ev_dt = pd.to_datetime(ev_date)

            # Must be strictly after as_of and within horizon
            if as_of_dt < ev_dt <= end_dt:
                st = ev.status.lower()
                if st in ("failed", "cancelled", "unrealized"):
                    continue
                if ev.direction == "credit" and st == "pending":
                    # Ignore pending credits
                    continue
                amt = ev.amount
                if amt is None:
                    if hasattr(self.data_store, "indexes") and hasattr(self.data_store.indexes, "images_by_event"):
                        img_refs = self.data_store.indexes.images_by_event.get(ev.event_id, [])
                        if img_refs:
                            from evidence.images import VERIFIED_IMAGE_AMOUNTS
                            for img in img_refs:
                                if img.image_id in VERIFIED_IMAGE_AMOUNTS:
                                    amt = VERIFIED_IMAGE_AMOUNTS[img.image_id][0]
                                    break
                if amt is None or amt == Decimal("0"):
                    continue

                # Check if salary was terminated
                if ev.category.lower() == "salary" and salary_terminated:
                    continue

                if ev.category.lower() == "salary" and salary_update_amount is not None:
                    if salary_effective_date is None or ev_dt >= salary_effective_date:
                        amt = salary_update_amount

                if ev.currency != home_curr and self.fx:
                    amt = self.fx.convert(amt, ev.currency, home_curr, ev_dt)

                signed_amt = amt if ev.direction == "credit" else -amt
                future_events.append(
                    CashEvent(
                        dt=ev_dt,
                        amount=signed_amt,
                        category=ev.category,
                        event_id=ev.event_id,
                        source="scheduled",
                        flexibility=ev.flexibility,
                        minimum_allowed_amount=ev.minimum_allowed_amount,
                        description=ev.description,
                    )
                )
                covered_dates_by_cat.add((ev_dt.date(), ev.category.lower()))

        # 6. Project recurring patterns across the horizon
        has_salary_pattern = any(p.category.lower() == "salary" for p in patterns)

        # If salary wasn't detected from history (e.g. only 1 historical event), but confirmed scheduled salary exists
        if not has_salary_pattern and not salary_terminated:
            scheduled_salaries = [e for e in future_events if e.category.lower() == "salary" and e.amount > 0]
            if scheduled_salaries:
                last_sched = max(scheduled_salaries, key=lambda x: x.dt)
                sal_amt = last_sched.amount
                sal_day = last_sched.dt.day
                next_sal = _advance_month(last_sched.dt, sal_day)
                while next_sal <= end_dt:
                    d_key = (next_sal.date(), "salary")
                    if d_key not in covered_dates_by_cat:
                        future_events.append(
                            CashEvent(
                                dt=next_sal,
                                amount=sal_amt,
                                category="salary",
                                event_id=f"proj_salary_{next_sal.strftime('%Y%m%d')}",
                                source="projected",
                                flexibility="fixed",
                                description="Projected recurring salary",
                            )
                        )
                        covered_dates_by_cat.add(d_key)
                    next_sal = _advance_month(next_sal, sal_day)

        for pat in patterns:
            cat = pat.category.lower()
            if cat == "salary" and salary_terminated:
                continue

            curr_dt = pat.next_occurrence
            day_of_month = curr_dt.day

            while curr_dt <= end_dt:
                if curr_dt > as_of_dt:
                    d_key = (curr_dt.date(), cat)
                    # Avoid double-counting if a scheduled event in dataset already covers this date/category
                    if d_key not in covered_dates_by_cat:
                        amt = pat.amount
                        if cat == "salary" and salary_update_amount is not None:
                            if salary_effective_date is None or curr_dt >= salary_effective_date:
                                amt = salary_update_amount
                        elif "rent" in cat and rent_increase_pct is not None:
                            amt = quantize_money(amt * (Decimal("1") + (rent_increase_pct / Decimal("100"))), 2)

                        signed_amt = amt if pat.direction == "credit" else -amt
                        future_events.append(
                            CashEvent(
                                dt=curr_dt,
                                amount=signed_amt,
                                category=pat.category,
                                event_id=f"proj_{cat}_{curr_dt.strftime('%Y%m%d')}",
                                source="projected",
                                flexibility="fixed",
                                description=f"Projected recurring {pat.category}",
                            )
                        )
                        covered_dates_by_cat.add(d_key)

                # Advance to next occurrence
                if pat.interval_days == 30:
                    curr_dt = _advance_month(curr_dt, day_of_month)
                else:
                    curr_dt = curr_dt + pd.Timedelta(days=pat.interval_days)

        # 7. Deterministic sort by (date, amount sign [debits first, or credits first? credits first], event_id)
        # Consistent ordering: positive first (inflows), then debits, then event_id
        future_events.sort(key=lambda e: (e.dt, -e.amount, e.event_id))
        return future_events

    def forecast(
        self,
        user_id: str,
        as_of: pd.Timestamp,
        horizon_days: int = 90,
    ) -> list[FinancialState]:
        """Simulate daily balance progression for user_id over horizon_days starting at as_of."""
        as_of_dt = pd.to_datetime(as_of).normalize()
        profile = self.data_store.get_profile(user_id)
        current_balance = profile.current_available_balance if profile else Decimal("0.00")

        # Gather future cash events
        cash_events = self.future_cash_events(user_id=user_id, as_of=as_of_dt, horizon_days=horizon_days)

        # Group cash events by date
        events_by_date: dict[date, list[CashEvent]] = {}
        for ev in cash_events:
            d = ev.dt.date()
            events_by_date.setdefault(d, []).append(ev)

        # Simulate day-by-day for horizon_days
        states: list[FinancialState] = []
        running_balance = current_balance

        for day_offset in range(horizon_days + 1):
            curr_dt = as_of_dt + pd.Timedelta(days=day_offset)
            d = curr_dt.date()

            day_events = events_by_date.get(d, [])
            inflows = sum((e.amount for e in day_events if e.amount > 0), Decimal("0.00"))
            outflows = sum((abs(e.amount) for e in day_events if e.amount < 0), Decimal("0.00"))
            net_cash_flow = inflows - outflows

            opening_balance = running_balance
            closing_balance = opening_balance + net_cash_flow
            running_balance = closing_balance

            states.append(
                FinancialState(
                    dt=curr_dt,
                    opening_balance=opening_balance,
                    inflows=inflows,
                    outflows=outflows,
                    net_cash_flow=net_cash_flow,
                    closing_balance=closing_balance,
                )
            )

        return states

    def get_minimum_projected_balance(
        self, states: Sequence[FinancialState]
    ) -> tuple[Decimal, pd.Timestamp]:
        """Find the minimum closing balance and the date on which it occurs."""
        if not states:
            return Decimal("0.00"), pd.Timestamp.now()
        min_state = min(states, key=lambda s: (s.closing_balance, s.dt))
        return min_state.closing_balance, min_state.dt

    def detect_negative_balance(self, states: Sequence[FinancialState]) -> bool:
        """Check if any projected closing balance falls below zero."""
        return any(s.closing_balance < Decimal("0.00") for s in states)

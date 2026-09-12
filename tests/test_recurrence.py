"""Unit tests for recurrence detection in code/finance/recurrence.py."""

from decimal import Decimal
import pandas as pd
import pytest

from finance.compat import CashEvent
from finance.recurrence import RecurringPatternDetector


def test_detect_weekly_recurrence():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-02-01")
    # Weekly grocery purchases every 7 days
    events = [
        CashEvent(dt=pd.Timestamp("2025-01-03"), amount=Decimal("-100.00"), category="groceries"),
        CashEvent(dt=pd.Timestamp("2025-01-10"), amount=Decimal("-100.00"), category="groceries"),
        CashEvent(dt=pd.Timestamp("2025-01-17"), amount=Decimal("-100.00"), category="groceries"),
        CashEvent(dt=pd.Timestamp("2025-01-24"), amount=Decimal("-100.00"), category="groceries"),
        CashEvent(dt=pd.Timestamp("2025-01-31"), amount=Decimal("-100.00"), category="groceries"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    assert len(patterns) == 1
    p = patterns[0]
    assert p.category == "groceries"
    assert p.direction == "debit"
    assert p.interval_days == 7
    assert p.amount == Decimal("100.00")
    assert p.next_occurrence == pd.Timestamp("2025-02-07")


def test_detect_biweekly_recurrence():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-03-01")
    # Biweekly dining expenses every 14 days
    events = [
        CashEvent(dt=pd.Timestamp("2025-01-05"), amount=Decimal("-50.00"), category="dining"),
        CashEvent(dt=pd.Timestamp("2025-01-19"), amount=Decimal("-50.00"), category="dining"),
        CashEvent(dt=pd.Timestamp("2025-02-02"), amount=Decimal("-50.00"), category="dining"),
        CashEvent(dt=pd.Timestamp("2025-02-16"), amount=Decimal("-50.00"), category="dining"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    assert len(patterns) == 1
    p = patterns[0]
    assert p.category == "dining"
    assert p.direction == "debit"
    assert p.interval_days == 14
    assert p.next_occurrence == pd.Timestamp("2025-03-02")


def test_detect_monthly_recurrence():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-04-05")
    # Monthly rent on the 1st of each month
    events = [
        CashEvent(dt=pd.Timestamp("2025-01-01"), amount=Decimal("-1200.00"), category="rent"),
        CashEvent(dt=pd.Timestamp("2025-02-01"), amount=Decimal("-1200.00"), category="rent"),
        CashEvent(dt=pd.Timestamp("2025-03-01"), amount=Decimal("-1200.00"), category="rent"),
        CashEvent(dt=pd.Timestamp("2025-04-01"), amount=Decimal("-1200.00"), category="rent"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    assert len(patterns) == 1
    p = patterns[0]
    assert p.category == "rent"
    assert p.direction == "debit"
    assert p.interval_days == 30
    assert p.next_occurrence == pd.Timestamp("2025-05-01")


def test_irregular_events_not_detected_as_recurring():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-04-01")
    # Irregular shopping purchases: intervals are 3 days, then 25 days, then 2 days
    events = [
        CashEvent(dt=pd.Timestamp("2025-01-01"), amount=Decimal("-80.00"), category="shopping"),
        CashEvent(dt=pd.Timestamp("2025-01-04"), amount=Decimal("-120.00"), category="shopping"),
        CashEvent(dt=pd.Timestamp("2025-01-29"), amount=Decimal("-45.00"), category="shopping"),
        CashEvent(dt=pd.Timestamp("2025-01-31"), amount=Decimal("-300.00"), category="shopping"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    assert len(patterns) == 0


def test_single_event_not_detected_as_recurring():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-04-01")
    events = [
        CashEvent(dt=pd.Timestamp("2025-02-15"), amount=Decimal("5000.00"), category="salary"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    assert len(patterns) == 0


def test_temporal_cutoff_in_recurrence():
    detector = RecurringPatternDetector()
    as_of = pd.Timestamp("2025-01-15")
    # Event on Jan 20 occurs after as_of: must be strictly excluded
    events = [
        CashEvent(dt=pd.Timestamp("2025-01-01"), amount=Decimal("-100.00"), category="transport"),
        CashEvent(dt=pd.Timestamp("2025-01-08"), amount=Decimal("-100.00"), category="transport"),
        CashEvent(dt=pd.Timestamp("2025-01-20"), amount=Decimal("-100.00"), category="transport"),
    ]

    patterns = detector.detect_recurring_patterns(events, as_of=as_of)
    # Only 2 events before Jan 15 (Jan 1, Jan 8) with 7 days interval
    assert len(patterns) == 1
    p = patterns[0]
    # Next occurrence projected strictly after as_of (Jan 15 -> next is Jan 22)
    assert p.next_occurrence == pd.Timestamp("2025-01-22")

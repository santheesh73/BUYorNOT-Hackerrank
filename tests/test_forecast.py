"""Unit tests for code/finance/forecast.py covering all golden test cases and invariants."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data.models import FinancialEvent, FinancialProfile
from evidence.models import FinancialEvidence
from finance.compat import CashEvent, FX
from finance.forecast import CashFlowForecaster
from finance.state import FinancialState


def _make_mock_store(profile: FinancialProfile, events: list[FinancialEvent], evidence: list[FinancialEvidence] | None = None):
    store = MagicMock()
    store.get_profile = MagicMock(return_value=profile)
    store.get_user_events = MagicMock(return_value=events)

    ev_store = MagicMock()
    ev_store.get_user_evidence = MagicMock(return_value=evidence or [])
    store.get_evidence_store = MagicMock(return_value=ev_store)

    return store


def test_forecast_invariants_daily_simulation():
    profile = FinancialProfile(
        user_id="u_inv",
        home_currency="USD",
        current_available_balance=Decimal("1000.00"),
        minimum_balance_to_keep=Decimal("200.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    store = _make_mock_store(profile, [])
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-01-01")

    states = forecaster.forecast("u_inv", as_of=as_of, horizon_days=90)
    # Exact 91 daily financial states
    assert len(states) == 91
    assert states[0].dt == as_of
    assert states[-1].dt == as_of + pd.Timedelta(days=90)

    # Invariant: closing_balance == opening_balance + inflows - outflows
    for s in states:
        assert s.closing_balance == s.opening_balance + s.inflows - s.outflows
        assert s.net_cash_flow == s.inflows - s.outflows
        assert s.inflows >= Decimal("0.00")
        assert s.outflows >= Decimal("0.00")


def test_golden_case_1_stable_income_and_expenses():
    profile = FinancialProfile(
        user_id="u_case1",
        home_currency="USD",
        current_available_balance=Decimal("5000.00"),
        minimum_balance_to_keep=Decimal("1000.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    # Monthly salary 3000 on 15th, Monthly rent 1000 on 1st
    events = [
        FinancialEvent(
            event_id="e_s1", user_id="u_case1", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 1, 15), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_s2", user_id="u_case1", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 2, 15), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_r1", user_id="u_case1", event_type="rent", description="Rent",
            category="rent", direction="debit", amount=Decimal("1000.00"), currency="USD",
            event_date=date(2025, 1, 1), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_r2", user_id="u_case1", event_type="rent", description="Rent",
            category="rent", direction="debit", amount=Decimal("1000.00"), currency="USD",
            event_date=date(2025, 2, 1), status="settled", flexibility="fixed"
        ),
    ]

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-20")

    states = forecaster.forecast("u_case1", as_of=as_of, horizon_days=90)
    min_bal, _ = forecaster.get_minimum_projected_balance(states)

    # Net income is positive (+3000 - 1000 = +2000/month), balance stays above initial 5000
    assert min_bal >= Decimal("4000.00")
    assert not forecaster.detect_negative_balance(states)


def test_golden_case_2_income_termination():
    profile = FinancialProfile(
        user_id="u_case2",
        home_currency="USD",
        current_available_balance=Decimal("3000.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        FinancialEvent(
            event_id="e_s1", user_id="u_case2", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("2500.00"), currency="USD",
            event_date=date(2025, 1, 15), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_s2", user_id="u_case2", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("2500.00"), currency="USD",
            event_date=date(2025, 2, 15), status="settled", flexibility="fixed"
        ),
    ]
    # Evidence says employment ended
    evidence = [
        FinancialEvidence(
            evidence_id="ev_term", user_id="u_case2", source_type="message", source_id="m1",
            event_id=None, request_id=None, fact_type="income_employment_ended",
            value="Employment ended", numeric_value=None, currency=None,
            effective_date=None, confidence=Decimal("0.95"), source_text=None, source_path=None,
        )
    ]

    store = _make_mock_store(profile, events, evidence)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-20")

    future_evs = forecaster.future_cash_events("u_case2", as_of=as_of, horizon_days=90)
    salary_evs = [e for e in future_evs if e.category == "salary"]
    # Due to termination, no future salary is projected
    assert len(salary_evs) == 0


def test_golden_case_3_one_time_bonus_not_projected_repeatedly():
    profile = FinancialProfile(
        user_id="u_case3",
        home_currency="USD",
        current_available_balance=Decimal("2000.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    # One single bonus in scheduled events
    events = [
        FinancialEvent(
            event_id="e_b1", user_id="u_case3", event_type="bonus", description="Annual Bonus",
            category="bonus", direction="credit", amount=Decimal("1500.00"), currency="USD",
            event_date=date(2025, 3, 1), status="scheduled", flexibility="fixed"
        ),
    ]

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-01")

    future_evs = forecaster.future_cash_events("u_case3", as_of=as_of, horizon_days=90)
    bonus_evs = [e for e in future_evs if e.category == "bonus"]
    # Appears exactly once on 2025-03-01
    assert len(bonus_evs) == 1
    assert bonus_evs[0].amount == Decimal("1500.00")


def test_golden_case_4_recurring_rent_generated():
    profile = FinancialProfile(
        user_id="u_case4",
        home_currency="USD",
        current_available_balance=Decimal("4000.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        FinancialEvent(
            event_id="e_r1", user_id="u_case4", event_type="rent", description="Rent",
            category="rent", direction="debit", amount=Decimal("1200.00"), currency="USD",
            event_date=date(2025, 1, 1), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_r2", user_id="u_case4", event_type="rent", description="Rent",
            category="rent", direction="debit", amount=Decimal("1200.00"), currency="USD",
            event_date=date(2025, 2, 1), status="settled", flexibility="fixed"
        ),
    ]

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-05")

    future_evs = forecaster.future_cash_events("u_case4", as_of=as_of, horizon_days=90)
    rent_evs = [e for e in future_evs if e.category == "rent"]
    # Monthly rent on March 1, April 1, May 1 -> 3 occurrences
    assert len(rent_evs) == 3
    for r in rent_evs:
        assert r.amount == Decimal("-1200.00")


def test_golden_case_5_pending_failed_cancelled_excluded():
    profile = FinancialProfile(
        user_id="u_case5",
        home_currency="USD",
        current_available_balance=Decimal("2000.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        # Pending credit: must be excluded
        FinancialEvent(
            event_id="e_pc", user_id="u_case5", event_type="refund", description="Pending Refund",
            category="refund", direction="credit", amount=Decimal("500.00"), currency="USD",
            event_date=date(2025, 3, 1), status="pending", flexibility="fixed"
        ),
        # Failed debit: must be excluded
        FinancialEvent(
            event_id="e_fd", user_id="u_case5", event_type="utilities", description="Failed Bill",
            category="utilities", direction="debit", amount=Decimal("200.00"), currency="USD",
            event_date=date(2025, 3, 5), status="failed", flexibility="fixed"
        ),
        # Cancelled debit: must be excluded
        FinancialEvent(
            event_id="e_cd", user_id="u_case5", event_type="shopping", description="Cancelled Order",
            category="shopping", direction="debit", amount=Decimal("150.00"), currency="USD",
            event_date=date(2025, 3, 10), status="cancelled", flexibility="fixed"
        ),
    ]

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-01")

    future_evs = forecaster.future_cash_events("u_case5", as_of=as_of, horizon_days=90)
    assert len(future_evs) == 0


def test_golden_case_6_foreign_currency_conversion():
    profile = FinancialProfile(
        user_id="u_case6",
        home_currency="EUR",
        current_available_balance=Decimal("3000.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        # Scheduled USD salary: 1000 USD
        FinancialEvent(
            event_id="e_usd", user_id="u_case6", event_type="salary", description="USD Salary",
            category="salary", direction="credit", amount=Decimal("1000.00"), currency="USD",
            event_date=date(2025, 3, 15), status="scheduled", flexibility="fixed"
        ),
    ]

    rates_df = pd.DataFrame([
        {"rate_date": "2025-03-15", "from_currency": "USD", "to_currency": "EUR", "rate": "0.92"}
    ])
    fx = FX(rates_df)

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store, fx=fx)
    as_of = pd.Timestamp("2025-02-01")

    future_evs = forecaster.future_cash_events("u_case6", as_of=as_of, horizon_days=90)
    sal = [e for e in future_evs if e.category == "salary"][0]
    # 1000 USD * 0.92 = 920.00 EUR
    assert sal.amount == Decimal("920.00")


def test_golden_case_7_message_changes_salary():
    profile = FinancialProfile(
        user_id="u_case7",
        home_currency="USD",
        current_available_balance=Decimal("5000.00"),
        minimum_balance_to_keep=Decimal("1000.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        FinancialEvent(
            event_id="e_s1", user_id="u_case7", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 1, 15), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_s2", user_id="u_case7", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 2, 15), status="settled", flexibility="fixed"
        ),
    ]
    # Message before as_of updates salary to 4200
    evidence = [
        FinancialEvidence(
            evidence_id="ev_sal", user_id="u_case7", source_type="message", source_id="m1",
            event_id=None, request_id=None, fact_type="income_salary_update",
            value="Salary USD 4200", numeric_value=Decimal("4200.00"), currency="USD",
            effective_date=date(2025, 2, 1), confidence=Decimal("0.95"), source_text=None, source_path=None,
        )
    ]

    store = _make_mock_store(profile, events, evidence)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-20")

    future_evs = forecaster.future_cash_events("u_case7", as_of=as_of, horizon_days=90)
    salary_evs = [e for e in future_evs if e.category == "salary"]
    assert len(salary_evs) >= 1
    # Projected salary reflects the updated 4200 amount
    assert salary_evs[0].amount == Decimal("4200.00")


def test_golden_case_8_future_message_cannot_affect_earlier_request():
    profile = FinancialProfile(
        user_id="u_case8",
        home_currency="USD",
        current_available_balance=Decimal("5000.00"),
        minimum_balance_to_keep=Decimal("1000.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    events = [
        FinancialEvent(
            event_id="e_s1", user_id="u_case8", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 1, 15), status="settled", flexibility="fixed"
        ),
        FinancialEvent(
            event_id="e_s2", user_id="u_case8", event_type="salary", description="Salary",
            category="salary", direction="credit", amount=Decimal("3000.00"), currency="USD",
            event_date=date(2025, 2, 15), status="settled", flexibility="fixed"
        ),
    ]
    # Message dated in March: cannot affect February evaluation date!
    evidence = [
        FinancialEvidence(
            evidence_id="ev_fut", user_id="u_case8", source_type="message", source_id="m1",
            event_id=None, request_id=None, fact_type="income_employment_ended",
            value="Employment ended", numeric_value=None, currency=None,
            effective_date=date(2025, 3, 10), confidence=Decimal("0.95"), source_text=None, source_path=None,
        )
    ]

    store = _make_mock_store(profile, events, evidence)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-20")

    future_evs = forecaster.future_cash_events("u_case8", as_of=as_of, horizon_days=90)
    salary_evs = [e for e in future_evs if e.category == "salary"]
    # Future message ignored; recurring salary still projected
    assert len(salary_evs) >= 1
    assert salary_evs[0].amount == Decimal("3000.00")


def test_golden_case_10_large_future_expense_detects_balance_pressure():
    profile = FinancialProfile(
        user_id="u_case10",
        home_currency="USD",
        current_available_balance=Decimal("1500.00"),
        minimum_balance_to_keep=Decimal("500.00"),
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
    )
    # Large upcoming dental bill of 2000 USD on March 1
    events = [
        FinancialEvent(
            event_id="e_med", user_id="u_case10", event_type="healthcare", description="Dental surgery",
            category="healthcare", direction="debit", amount=Decimal("2000.00"), currency="USD",
            event_date=date(2025, 3, 1), status="scheduled", flexibility="fixed"
        ),
    ]

    store = _make_mock_store(profile, events)
    forecaster = CashFlowForecaster(store)
    as_of = pd.Timestamp("2025-02-01")

    states = forecaster.forecast("u_case10", as_of=as_of, horizon_days=90)
    min_bal, min_dt = forecaster.get_minimum_projected_balance(states)

    # 1500 - 2000 = -500.00 -> Negative balance detected!
    assert min_bal == Decimal("-500.00")
    assert min_dt == pd.Timestamp("2025-03-01")
    assert forecaster.detect_negative_balance(states) is True

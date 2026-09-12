"""Unit tests for code/finance/ledger.py and Phase 2 invariants."""

from datetime import date
from decimal import Decimal
import pytest

from data.store import DataStore
from finance.ledger import FinancialLedger, build_phase2_report
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def store():
    root = get_repo_root()
    return DataStore.load_from_repo(repo_root=root)


@pytest.fixture(scope="module")
def ledger(store):
    return store.get_ledger()


def test_ledger_user_events_and_cash_flows(ledger: FinancialLedger):
    # User 01 has events
    events = ledger.build_user_ledger("user_01")
    assert len(events) > 0

    # Test deterministic sorting: 1) effective_date, 2) settlement_date, 3) event_id
    for i in range(len(events) - 1):
        e1, e2 = events[i], events[i + 1]
        k1 = (e1.effective_date or e1.event_date, e1.settlement_date or date.max, e1.event_id)
        k2 = (e2.effective_date or e2.event_date, e2.settlement_date or date.max, e2.event_id)
        assert k1 <= k2

    cash_flows = ledger.get_cash_flows("user_01")
    assert len(cash_flows) <= len(events)
    assert all(cf.is_cash_flow for cf in cash_flows)


def test_ledger_get_event(ledger: FinancialLedger):
    ev = ledger.get_event("event_01")
    assert ev is not None
    assert ev.event_id == "event_01"
    assert ev.user_id == "user_01"
    assert ev.home_currency_amount is not None

    missing = ledger.get_event("non_existent_event")
    assert missing is None


def test_phase2_report_metrics(ledger: FinancialLedger, store: DataStore):
    report = build_phase2_report(ledger, store)
    assert report.status == "PASS"
    assert report.raw_event_count == 25342
    assert report.normalized_event_count == 25342
    assert report.cash_flow_count == 25275
    assert report.non_cash_flow_count == 67
    assert report.linked_lifecycle_count == 58
    assert report.single_event_lifecycle_count == 25226
    assert report.multi_event_lifecycle_count == 58
    assert report.pending_count == 71
    assert report.failed_count == 21
    assert report.cancelled_count == 22
    assert report.active_count == 25218
    assert report.home_currency_count == 25202
    assert report.foreign_currency_count == 140
    assert report.missing_fx_rate_count == 0
    assert report.missing_amount_count == 16
    assert report.normalized_amount_count == 25326
    assert report.evidence_resolution_count == 16
    assert report.error_count == 0


# --- Phase 2 Invariants ---

def test_invariant_1_raw_events_never_modified(store: DataStore, ledger: FinancialLedger):
    # Check that raw events in DataStore still have their original fields
    raw = store.get_event("event_01")
    assert raw is not None
    assert isinstance(raw.amount, Decimal)


def test_invariant_2_every_event_maps_to_source_ids(ledger: FinancialLedger):
    for ev in ledger.get_all_normalized_events():
        assert len(ev.source_event_ids) >= 1
        assert ev.event_id in ev.source_event_ids


def test_invariant_3_missing_amounts_remain_missing(ledger: FinancialLedger):
    # All 16 events with missing raw amounts must remain None
    missing_events = [e for e in ledger.get_all_normalized_events() if e.original_amount is None]
    assert len(missing_events) == 16
    for e in missing_events:
        assert e.home_currency_amount is None


def test_invariant_4_no_float_amounts(ledger: FinancialLedger):
    for e in ledger.get_all_normalized_events():
        if e.original_amount is not None:
            assert isinstance(e.original_amount, Decimal)
        if e.home_currency_amount is not None:
            assert isinstance(e.home_currency_amount, Decimal)


def test_invariant_5_correct_user_mapping(ledger: FinancialLedger):
    for user_id in ["user_01", "user_02", "user_10"]:
        events = ledger.build_user_ledger(user_id)
        assert all(e.user_id == user_id for e in events)


def test_invariant_6_and_7_duplicate_suppression(ledger: FinancialLedger):
    # Duplicate card charge event_12709 must NOT be a cash flow
    dup_ev = ledger.get_event("event_12709")
    assert dup_ev is not None
    assert dup_ev.is_cash_flow is False

    # Original event_12708 MUST be a cash flow
    orig_ev = ledger.get_event("event_12708")
    assert orig_ev is not None
    assert orig_ev.is_cash_flow is True


def test_invariant_8_foreign_currency_conversion(ledger: FinancialLedger):
    # Foreign currency event: event_2167 is USD for user_25 (home currency IDR) on 2023-10-15
    fe = ledger.get_event("event_2167")
    assert fe is not None
    assert fe.original_currency == "USD"
    # User 25 home currency is IDR, rate on 2023-10-15 is 15833.33
    assert fe.home_currency_amount is not None
    assert fe.home_currency_amount == Decimal("15833.33") * fe.original_amount


def test_invariant_9_deterministic_output(store: DataStore):
    # Running build_user_ledger twice produces identical sequence
    l1 = store.get_ledger().build_user_ledger("user_01")
    l2 = store.get_ledger().build_user_ledger("user_01")
    assert [e.event_id for e in l1] == [e.event_id for e in l2]
    assert [e.home_currency_amount for e in l1] == [e.home_currency_amount for e in l2]


def test_invariant_10_no_affordability_fields_present(ledger: FinancialLedger):
    # NormalizedFinancialEvent does not compute affordability or safe payment
    ev = ledger.get_event("event_01")
    assert not hasattr(ev, "amount_safe_to_pay")
    assert not hasattr(ev, "affordability_status")
    assert not hasattr(ev, "recommended_payment_method")

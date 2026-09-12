"""Unit tests for code/evidence/resolver.py and code/evidence/store.py."""

from datetime import date, datetime
from decimal import Decimal

from data.models import ImageReference, Message
from evidence.models import FinancialEvidence
from evidence.resolver import EvidenceResolver
from evidence.store import EvidenceStore


def test_resolver_caching():
    resolver = EvidenceResolver()
    msg = Message(
        message_id="msg_cache_test",
        user_id="user_test",
        request_id="req_test",
        related_event_id=None,
        sent_at=datetime(2025, 1, 1, 12, 0),
        source_type="employer",
        message_text="Gaji bulanan Anda naik menjadi IDR 20000000.",
    )

    facts1 = resolver.resolve_message(msg)
    facts2 = resolver.resolve_message(msg)

    # Identical list reference from cache
    assert facts1 is facts2
    assert len(facts1) >= 1


def test_evidence_store_indexes_and_ordering():
    ev1 = FinancialEvidence(
        evidence_id="ev_01",
        user_id="user_1",
        source_type="message",
        source_id="m1",
        event_id="e1",
        request_id="r1",
        fact_type="income_salary_update",
        value="Salary EUR 2000",
        numeric_value=Decimal("2000"),
        currency="EUR",
        effective_date=date(2025, 6, 1),
        confidence=Decimal("0.95"),
        source_text=None,
        source_path=None,
    )
    ev2 = FinancialEvidence(
        evidence_id="ev_02",
        user_id="user_1",
        source_type="message",
        source_id="m2",
        event_id="e2",
        request_id="r1",
        fact_type="expense_rent_increase",
        value="Rent +10%",
        numeric_value=Decimal("10"),
        currency=None,
        effective_date=date(2025, 5, 1),  # earlier date
        confidence=Decimal("0.95"),
        source_text=None,
        source_path=None,
    )

    store = EvidenceStore([ev1, ev2])

    user_ev = store.get_user_evidence("user_1")
    assert len(user_ev) == 2
    # Deterministic chronological order: ev2 (May) before ev1 (June)
    assert user_ev[0].evidence_id == "ev_02"
    assert user_ev[1].evidence_id == "ev_01"

    assert len(store.get_event_evidence("e1")) == 1
    assert store.get_event_evidence("e1")[0].evidence_id == "ev_01"

    assert len(store.get_request_evidence("r1")) == 2


def test_evidence_store_conflict_detection():
    ev_salary = FinancialEvidence(
        evidence_id="ev_s",
        user_id="user_conflict",
        source_type="message",
        source_id="m_s",
        event_id=None,
        request_id=None,
        fact_type="income_salary_update",
        value="Salary USD 4000",
        numeric_value=Decimal("4000"),
        currency="USD",
        effective_date=date(2025, 8, 1),
        confidence=Decimal("0.95"),
        source_text=None,
        source_path=None,
    )
    ev_term = FinancialEvidence(
        evidence_id="ev_t",
        user_id="user_conflict",
        source_type="message",
        source_id="m_t",
        event_id=None,
        request_id=None,
        fact_type="income_employment_ended",
        value="Employment ended",
        numeric_value=None,
        currency=None,
        effective_date=None,
        confidence=Decimal("0.95"),
        source_text=None,
        source_path=None,
    )

    store = EvidenceStore([ev_salary, ev_term])
    conflicts = store.get_conflict_groups()

    assert len(conflicts) >= 1
    conflicted_ids = {e.evidence_id for group in conflicts for e in group}
    assert "ev_s" in conflicted_ids
    assert "ev_t" in conflicted_ids

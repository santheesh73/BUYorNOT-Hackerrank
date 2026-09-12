"""Unit tests for code/evidence/models.py."""

from datetime import date
from decimal import Decimal

import pytest

from evidence.models import FinancialEvidence


def test_financial_evidence_creation_and_immutability():
    ev = FinancialEvidence(
        evidence_id="ev_001",
        user_id="user_01",
        source_type="message",
        source_id="msg_01",
        event_id="ev_10",
        request_id="req_01",
        fact_type="income_salary_update",
        value="Confirmed salary USD 5000",
        numeric_value=Decimal("5000"),
        currency="USD",
        effective_date=date(2025, 6, 1),
        confidence=Decimal("0.95"),
        source_text="Your confirmed salary is USD 5000.",
        source_path=None,
    )
    assert ev.evidence_id == "ev_001"
    assert ev.user_id == "user_01"
    assert ev.fact_category == "income"
    assert ev.is_high_confidence is True
    assert ev.is_medium_confidence is False
    assert ev.is_low_confidence is False

    # Immutability check
    with pytest.raises(Exception):
        ev.confidence = Decimal("0.50")  # type: ignore


def test_fact_categories():
    base_kwargs = {
        "evidence_id": "ev",
        "user_id": "u",
        "source_type": "message",
        "source_id": "s",
        "event_id": None,
        "request_id": None,
        "value": None,
        "numeric_value": None,
        "currency": None,
        "effective_date": None,
        "confidence": Decimal("0.90"),
        "source_text": None,
        "source_path": None,
    }

    assert FinancialEvidence(**{**base_kwargs, "fact_type": "income_salary_update"}).fact_category == "income"
    assert FinancialEvidence(**{**base_kwargs, "fact_type": "expense_rent_increase"}).fact_category == "expense"
    assert FinancialEvidence(**{**base_kwargs, "fact_type": "amount_extracted"}).fact_category == "amount"
    assert FinancialEvidence(**{**base_kwargs, "fact_type": "date_salary_reschedule"}).fact_category == "date"
    assert FinancialEvidence(**{**base_kwargs, "fact_type": "internal_transfer"}).fact_category == "other"

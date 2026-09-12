"""Unit tests for Part B compatibility classes."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from evidence.compat import EvidenceExtractor, MessageFacts
from finance.compat import CashEvent, ChangeAction, FinancialEngine, FX
from utils.paths import get_repo_root


def test_cash_event_contract():
    dt = pd.Timestamp("2025-07-01")
    ce = CashEvent(
        dt=dt,
        amount=Decimal("-150.00"),
        category="utilities",
        event_id="ev_test",
        source="actual",
        flexibility="flexible",
        minimum_allowed_amount=Decimal("-100.00"),
        description="Electricity bill",
    )
    assert ce.dt == dt
    assert ce.amount == Decimal("-150.00")
    assert ce.category == "utilities"
    assert ce.event_id == "ev_test"
    assert ce.flexibility == "flexible"


def test_change_action_contract():
    ca = ChangeAction(
        kind="reduce_to",
        event_id="ev_sub",
        category="entertainment",
        old_amount=Decimal("60.00"),
        new_amount=Decimal("20.00"),
        saving_per_occurrence=Decimal("40.00"),
    )
    assert ca.kind == "reduce_to"
    assert ca.old_amount == Decimal("60.00")
    assert ca.saving_per_occurrence == Decimal("40.00")


def test_message_facts_as_of_cutoff():
    df_msgs = pd.DataFrame([
        {
            "user_id": "u1",
            "sent_at": "2024-05-01T10:00:00Z",
            "message_text": "May message",
        },
        {
            "user_id": "u1",
            "sent_at": "2024-07-01T10:00:00Z",
            "message_text": "July message",
        },
    ])
    mf = MessageFacts(df_msgs)

    # Cutoff in June: only May message should appear
    msgs_june = mf.for_user("u1", pd.Timestamp("2024-06-01", tz="UTC"))
    assert msgs_june == ["May message"]

    # Cutoff in August: both messages should appear
    msgs_aug = mf.for_user("u1", pd.Timestamp("2024-08-01", tz="UTC"))
    assert msgs_aug == ["May message", "July message"]


def test_fx_conversion():
    df_rates = pd.DataFrame([
        {
            "rate_date": "2025-06-01",
            "from_currency": "USD",
            "to_currency": "EUR",
            "rate": "0.85",
        }
    ])
    fx = FX(df_rates)

    # Direct rate
    converted = fx.convert(Decimal("100.00"), "USD", "EUR", pd.Timestamp("2025-06-01"))
    assert converted == Decimal("85.00")

    # Same currency
    same = fx.convert(Decimal("100.00"), "USD", "USD", pd.Timestamp("2025-06-01"))
    assert same == Decimal("100.00")

    # Inverse rate
    inv = fx.convert(Decimal("85.00"), "EUR", "USD", pd.Timestamp("2025-06-01"))
    assert inv == Decimal("100.00")

    # Missing rate
    with pytest.raises(ValueError, match="Exchange rate not found"):
        fx.convert(Decimal("100.00"), "USD", "JPY", pd.Timestamp("2025-06-01"))


def test_financial_engine_initialization():
    root = get_repo_root()
    engine = FinancialEngine(root)

    assert hasattr(engine, "profiles")
    assert hasattr(engine, "events")
    assert hasattr(engine, "requests")
    assert hasattr(engine, "options")
    assert hasattr(engine, "messages")
    assert hasattr(engine, "images")
    assert hasattr(engine, "fx")
    assert hasattr(engine, "extractor")
    assert hasattr(engine, "msgfacts")

    assert len(engine.profiles) == 275
    assert len(engine.events) == 25342
    assert len(engine.messages) == 215
    assert len(engine.images) == 16

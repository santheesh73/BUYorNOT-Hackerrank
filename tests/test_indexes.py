"""Unit tests for code/data/indexes.py."""

from datetime import date
from decimal import Decimal
import pytest

from data.indexes import build_indexes
from data.loader import load_datasets
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def loaded_indexes():
    root = get_repo_root()
    datasets = load_datasets(repo_root=root)
    return build_indexes(datasets)


def test_user_lookup(loaded_indexes):
    idx = loaded_indexes
    # Check user_01 profile
    prof = idx.profiles_by_user.get("user_01")
    assert prof is not None
    assert prof.user_id == "user_01"
    assert prof.home_currency == "ZAR"

    # User events
    user_events = idx.events_by_user.get("user_01", [])
    assert len(user_events) > 0
    assert all(e.user_id == "user_01" for e in user_events)


def test_request_and_payment_options_lookup(loaded_indexes):
    idx = loaded_indexes
    # request_26 in eval requests
    req = idx.requests_by_id.get("request_26")
    assert req is not None
    assert req.user_id == "user_26"

    # Payment options for request_26
    opts = idx.payment_options_by_request.get("request_26", [])
    assert len(opts) > 0
    assert all(o.request_id == "request_26" for o in opts)


def test_event_and_linked_event_lookup(loaded_indexes):
    idx = loaded_indexes
    # Check linked event event_98 -> event_99
    ev_parent = idx.events_by_id.get("event_98")
    assert ev_parent is not None

    linked = idx.events_by_linked_event.get("event_98", [])
    assert len(linked) > 0
    assert any(e.event_id == "event_99" for e in linked)


def test_message_lookups(loaded_indexes):
    idx = loaded_indexes
    # message_01
    msg = idx.messages_by_id.get("message_01")
    assert msg is not None
    assert msg.user_id == "user_02"

    # User messages
    user_msgs = idx.messages_by_user.get("user_02", [])
    assert any(m.message_id == "message_01" for m in user_msgs)


def test_image_lookups(loaded_indexes):
    idx = loaded_indexes
    # image_01 is related to event_253
    img = idx.images_by_id.get("image_01")
    assert img is not None
    assert img.related_event_id == "event_253"

    event_imgs = idx.images_by_event.get("event_253", [])
    assert len(event_imgs) == 1
    assert event_imgs[0].image_id == "image_01"


def test_exchange_rate_lookup(loaded_indexes):
    idx = loaded_indexes
    # 2023-10-15, EUR -> ZAR is 20
    rate = idx.exchange_rates_by_pair.get((date(2023, 10, 15), "EUR", "ZAR"))
    assert rate == Decimal("20")

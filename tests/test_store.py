"""Unit tests for code/data/store.py (DataStore)."""

from datetime import date
from decimal import Decimal
import pytest

from data.store import DataStore
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def store():
    root = get_repo_root()
    return DataStore.load_from_repo(repo_root=root)


def test_datastore_requests(store: DataStore):
    req = store.get_request("request_26")
    assert req is not None
    assert req.request_id == "request_26"
    assert store.get_request("non_existent_request") is None

    sreq = store.get_sample_request("request_01")
    assert sreq is not None
    assert sreq.request_id == "request_01"

    all_reqs = store.get_all_requests()
    assert len(all_reqs) == 250

    all_samples = store.get_all_sample_requests()
    assert len(all_samples) == 25

    user_reqs = store.get_user_requests("user_26")
    assert len(user_reqs) >= 1
    assert any(r.request_id == "request_26" for r in user_reqs)


def test_datastore_profiles(store: DataStore):
    prof = store.get_profile("user_01")
    assert prof is not None
    assert prof.home_currency == "ZAR"
    assert store.get_profile("unknown_user") is None

    profiles = store.get_all_profiles()
    assert len(profiles) == 275


def test_datastore_events(store: DataStore):
    ev = store.get_event("event_01")
    assert ev is not None
    assert ev.event_id == "event_01"
    assert store.get_event("non_existent_event") is None

    user_events = store.get_user_events("user_01")
    assert len(user_events) > 0

    linked = store.get_linked_events("event_98")
    assert len(linked) > 0
    assert any(e.event_id == "event_99" for e in linked)

    all_events = store.get_all_events()
    assert len(all_events) == 25342


def test_datastore_payment_options(store: DataStore):
    opts = store.get_payment_options("request_26")
    assert len(opts) > 0
    assert all(o.request_id == "request_26" for o in opts)

    opt = store.get_payment_option(opts[0].payment_option_id)
    assert opt is not None
    assert opt.payment_option_id == opts[0].payment_option_id


def test_datastore_messages(store: DataStore):
    msg = store.get_message("message_01")
    assert msg is not None
    assert msg.message_id == "message_01"

    user_msgs = store.get_user_messages("user_02")
    assert any(m.message_id == "message_01" for m in user_msgs)

    # Message 02 is tied to request_03
    req_msgs = store.get_request_messages("request_03")
    assert any(m.message_id == "message_02" for m in req_msgs)

    # Message 14 is tied to event_1785
    ev_msgs = store.get_event_messages("event_1785")
    assert any(m.message_id == "message_14" for m in ev_msgs)


def test_datastore_images(store: DataStore):
    img = store.get_image("image_01")
    assert img is not None
    assert img.related_event_id == "event_253"

    ev_imgs = store.get_event_images("event_253")
    assert len(ev_imgs) == 1
    assert ev_imgs[0].image_id == "image_01"

    req_imgs = store.get_request_images("request_03")
    assert len(req_imgs) == 1
    assert req_imgs[0].image_id == "image_01"

    user_imgs = store.get_user_images("user_03")
    assert len(user_imgs) == 1


def test_datastore_exchange_rate(store: DataStore):
    rate = store.get_exchange_rate(date(2023, 10, 15), "EUR", "ZAR")
    assert rate == Decimal("20")

    # Same currency should return 1.0
    same_rate = store.get_exchange_rate(date(2023, 10, 15), "EUR", "EUR")
    assert same_rate == Decimal("1.0")

    # Unknown rate
    assert store.get_exchange_rate(date(2000, 1, 1), "EUR", "JPY") is None

"""Reusable in-memory indexes for fast entity lookup across datasets."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import logging

from data.loader import LoadedDatasets
from data.models import (
    ExchangeRate,
    FinancialEvent,
    FinancialProfile,
    ImageReference,
    Message,
    PaymentOption,
    Request,
    SampleRequest,
)

logger = logging.getLogger(__name__)


@dataclass
class DatasetIndexes:
    """Precomputed O(1) lookup tables across all datasets."""
    # Financial events
    events_by_id: dict[str, FinancialEvent] = field(default_factory=dict)
    events_by_user: dict[str, list[FinancialEvent]] = field(default_factory=lambda: defaultdict(list))
    events_by_linked_event: dict[str, list[FinancialEvent]] = field(default_factory=lambda: defaultdict(list))

    # Requests
    requests_by_id: dict[str, Request] = field(default_factory=dict)
    requests_by_user: dict[str, list[Request]] = field(default_factory=lambda: defaultdict(list))
    sample_requests_by_id: dict[str, SampleRequest] = field(default_factory=dict)
    sample_requests_by_user: dict[str, list[SampleRequest]] = field(default_factory=lambda: defaultdict(list))

    # Profiles
    profiles_by_user: dict[str, FinancialProfile] = field(default_factory=dict)

    # Payment Options
    payment_options_by_request: dict[str, list[PaymentOption]] = field(default_factory=lambda: defaultdict(list))
    payment_options_by_id: dict[str, PaymentOption] = field(default_factory=dict)

    # Messages
    messages_by_id: dict[str, Message] = field(default_factory=dict)
    messages_by_user: dict[str, list[Message]] = field(default_factory=lambda: defaultdict(list))
    messages_by_request: dict[str, list[Message]] = field(default_factory=lambda: defaultdict(list))
    messages_by_event: dict[str, list[Message]] = field(default_factory=lambda: defaultdict(list))

    # Images
    images_by_id: dict[str, ImageReference] = field(default_factory=dict)
    images_by_user: dict[str, list[ImageReference]] = field(default_factory=lambda: defaultdict(list))
    images_by_request: dict[str, list[ImageReference]] = field(default_factory=lambda: defaultdict(list))
    images_by_event: dict[str, list[ImageReference]] = field(default_factory=lambda: defaultdict(list))

    # Exchange Rates (keyed by (rate_date, from_currency, to_currency))
    exchange_rates_by_pair: dict[tuple[date, str, str], Decimal] = field(default_factory=dict)


def build_indexes(datasets: LoadedDatasets) -> DatasetIndexes:
    """Build all lookup indexes from loaded datasets in a single pass."""
    logger.info("Building dataset indexes...")
    idx = DatasetIndexes()

    # Profiles
    for prof in datasets.financial_profiles:
        idx.profiles_by_user[prof.user_id] = prof

    # Requests
    for req in datasets.requests:
        idx.requests_by_id[req.request_id] = req
        idx.requests_by_user[req.user_id].append(req)

    # Sample Requests
    for sreq in datasets.sample_requests:
        idx.sample_requests_by_id[sreq.request_id] = sreq
        idx.sample_requests_by_user[sreq.user_id].append(sreq)

    # Financial Events
    for ev in datasets.financial_events:
        idx.events_by_id[ev.event_id] = ev
        idx.events_by_user[ev.user_id].append(ev)
        if ev.linked_event_id:
            idx.events_by_linked_event[ev.linked_event_id].append(ev)

    # Payment Options
    for opt in datasets.payment_options:
        idx.payment_options_by_id[opt.payment_option_id] = opt
        idx.payment_options_by_request[opt.request_id].append(opt)

    # Messages
    for msg in datasets.messages:
        idx.messages_by_id[msg.message_id] = msg
        idx.messages_by_user[msg.user_id].append(msg)
        if msg.request_id:
            idx.messages_by_request[msg.request_id].append(msg)
        if msg.related_event_id:
            idx.messages_by_event[msg.related_event_id].append(msg)

    # Images
    for img in datasets.images:
        idx.images_by_id[img.image_id] = img
        idx.images_by_user[img.user_id].append(img)
        if img.request_id:
            idx.images_by_request[img.request_id].append(img)
        if img.related_event_id:
            idx.images_by_event[img.related_event_id].append(img)

    # Exchange Rates
    for fx in datasets.exchange_rates:
        idx.exchange_rates_by_pair[(fx.rate_date, fx.from_currency, fx.to_currency)] = fx.rate

    logger.info("Indexes built successfully.")
    return idx

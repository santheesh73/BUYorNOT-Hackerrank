"""DataStore: Central high-level data access interface."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from data.indexes import DatasetIndexes, build_indexes
from data.loader import LoadedDatasets, load_datasets
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


class DataStore:
    """Lightweight repository data-access object providing cached, indexed queries."""

    def __init__(self, datasets: LoadedDatasets, indexes: DatasetIndexes | None = None) -> None:
        self.datasets = datasets
        self.indexes = indexes or build_indexes(datasets)
        self._ledger = None

    @classmethod
    def load_from_repo(cls, repo_root: Path | None = None) -> "DataStore":
        """Factory method to load all datasets and build indexes from project root."""
        datasets = load_datasets(repo_root=repo_root)
        indexes = build_indexes(datasets)
        return cls(datasets=datasets, indexes=indexes)

    # Request lookups
    def get_request(self, request_id: str) -> Request | None:
        """Retrieve an evaluation request by ID."""
        return self.indexes.requests_by_id.get(request_id)

    def get_sample_request(self, request_id: str) -> SampleRequest | None:
        """Retrieve a sample request by ID."""
        return self.indexes.sample_requests_by_id.get(request_id)

    def get_user_requests(self, user_id: str) -> list[Request]:
        """Retrieve all evaluation requests for a given user."""
        return list(self.indexes.requests_by_user.get(user_id, []))

    def get_all_requests(self) -> list[Request]:
        """Retrieve all evaluation requests."""
        return self.datasets.requests

    def get_all_sample_requests(self) -> list[SampleRequest]:
        """Retrieve all sample requests."""
        return self.datasets.sample_requests

    # Profile lookups
    def get_profile(self, user_id: str) -> FinancialProfile | None:
        """Retrieve user financial profile by user_id."""
        return self.indexes.profiles_by_user.get(user_id)

    def get_all_profiles(self) -> list[FinancialProfile]:
        """Retrieve all financial profiles."""
        return self.datasets.financial_profiles

    # Event lookups
    def get_event(self, event_id: str) -> FinancialEvent | None:
        """Retrieve a financial event by ID."""
        return self.indexes.events_by_id.get(event_id)

    def get_user_events(self, user_id: str) -> list[FinancialEvent]:
        """Retrieve all financial events belonging to a specific user."""
        return list(self.indexes.events_by_user.get(user_id, []))

    def get_linked_events(self, event_id: str) -> list[FinancialEvent]:
        """Retrieve all financial events that point back to event_id via linked_event_id."""
        return list(self.indexes.events_by_linked_event.get(event_id, []))

    def get_all_events(self) -> list[FinancialEvent]:
        """Retrieve all financial events."""
        return self.datasets.financial_events

    # Payment Option lookups
    def get_payment_options(self, request_id: str) -> list[PaymentOption]:
        """Retrieve payment options offered for a specific request."""
        return list(self.indexes.payment_options_by_request.get(request_id, []))

    def get_payment_option(self, payment_option_id: str) -> PaymentOption | None:
        """Retrieve a specific payment option by ID."""
        return self.indexes.payment_options_by_id.get(payment_option_id)

    # Message lookups
    def get_message(self, message_id: str) -> Message | None:
        """Retrieve a message by ID."""
        return self.indexes.messages_by_id.get(message_id)

    def get_user_messages(self, user_id: str) -> list[Message]:
        """Retrieve all messages associated with a user."""
        return list(self.indexes.messages_by_user.get(user_id, []))

    def get_request_messages(self, request_id: str) -> list[Message]:
        """Retrieve all messages tied to a specific request."""
        return list(self.indexes.messages_by_request.get(request_id, []))

    def get_event_messages(self, event_id: str) -> list[Message]:
        """Retrieve all messages tied to a specific event."""
        return list(self.indexes.messages_by_event.get(event_id, []))

    # Image lookups
    def get_image(self, image_id: str) -> ImageReference | None:
        """Retrieve an image reference by ID."""
        return self.indexes.images_by_id.get(image_id)

    def get_user_images(self, user_id: str) -> list[ImageReference]:
        """Retrieve all image references for a user."""
        return list(self.indexes.images_by_user.get(user_id, []))

    def get_request_images(self, request_id: str) -> list[ImageReference]:
        """Retrieve all image references associated with a request."""
        return list(self.indexes.images_by_request.get(request_id, []))

    def get_event_images(self, event_id: str) -> list[ImageReference]:
        """Retrieve all image references associated with a financial event."""
        return list(self.indexes.images_by_event.get(event_id, []))

    # Exchange rate lookup
    def get_exchange_rate(self, rate_date: date, from_currency: str, to_currency: str) -> Decimal | None:
        """Retrieve the fixed conversion rate for a currency pair on a specific date."""
        if from_currency == to_currency:
            return Decimal("1.0")
        return self.indexes.exchange_rates_by_pair.get((rate_date, from_currency, to_currency))

    # Financial Ledger integration
    def get_ledger(self) -> Any:
        """Retrieve the FinancialLedger for this store, initializing on demand."""
        if self._ledger is None:
            from finance.ledger import FinancialLedger
            self._ledger = FinancialLedger(
                events=self.datasets.financial_events,
                profiles=self.datasets.financial_profiles,
                exchange_rates=self,
            )
        return self._ledger

    def get_user_normalized_events(self, user_id: str) -> list[Any]:
        """Retrieve normalized financial events for a user."""
        return self.get_ledger().build_user_ledger(user_id)

    def get_user_cash_flows(self, user_id: str) -> list[Any]:
        """Retrieve resolved active cash flows for a user."""
        return self.get_ledger().get_cash_flows(user_id)

    def get_normalized_event(self, event_id: str) -> Any | None:
        """Retrieve a single normalized event by ID."""
        return self.get_ledger().get_event(event_id)

    # Phase 3: Evidence Store integration
    def get_evidence_store(self) -> Any:
        """Retrieve the EvidenceStore for this store, resolving evidence on demand."""
        if not hasattr(self, "_evidence_store") or self._evidence_store is None:
            from evidence.resolver import EvidenceResolver
            from evidence.store import EvidenceStore

            resolver = EvidenceResolver()
            msg_facts = resolver.resolve_all_messages(self.datasets.messages)
            img_facts = resolver.resolve_all_images(self.datasets.images)
            self._evidence_store = EvidenceStore(msg_facts + img_facts)
        return self._evidence_store

    def get_user_evidence(self, user_id: str) -> list[Any]:
        """Retrieve all structured financial evidence associated with a user."""
        return self.get_evidence_store().get_user_evidence(user_id)

    def get_event_evidence(self, event_id: str) -> list[Any]:
        """Retrieve all structured financial evidence tied to a financial event."""
        return self.get_evidence_store().get_event_evidence(event_id)

    def get_request_evidence(self, request_id: str) -> list[Any]:
        """Retrieve all structured financial evidence associated with an evaluation request."""
        return self.get_evidence_store().get_request_evidence(request_id)


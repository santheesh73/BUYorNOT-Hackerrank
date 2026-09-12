"""Financial event normalization layer for BUYorNOT."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data.models import FinancialEvent


@dataclass(frozen=True)
class NormalizedFinancialEvent:
    """Normalized financial event representation."""
    event_id: str
    user_id: str
    event_type: str
    direction: str
    original_amount: Decimal | None
    original_currency: str
    home_currency_amount: Decimal | None
    event_date: date
    settlement_date: date | None
    effective_date: date | None
    status: str
    linked_event_id: str | None
    lifecycle_id: str | None
    flexibility: str | None
    minimum_allowed_amount: Decimal | None
    is_cash_flow: bool
    is_income: bool
    is_expense: bool
    is_transfer: bool
    is_pending: bool
    is_failed: bool
    is_cancelled: bool
    source_event_ids: tuple[str, ...]

    def with_lifecycle(
        self,
        lifecycle_id: str,
        is_cash_flow: bool,
    ) -> "NormalizedFinancialEvent":
        """Return a copy of this event with resolved lifecycle information."""
        return NormalizedFinancialEvent(
            event_id=self.event_id,
            user_id=self.user_id,
            event_type=self.event_type,
            direction=self.direction,
            original_amount=self.original_amount,
            original_currency=self.original_currency,
            home_currency_amount=self.home_currency_amount,
            event_date=self.event_date,
            settlement_date=self.settlement_date,
            effective_date=self.effective_date,
            status=self.status,
            linked_event_id=self.linked_event_id,
            lifecycle_id=lifecycle_id,
            flexibility=self.flexibility,
            minimum_allowed_amount=self.minimum_allowed_amount,
            is_cash_flow=is_cash_flow,
            is_income=self.is_income,
            is_expense=self.is_expense,
            is_transfer=self.is_transfer,
            is_pending=self.is_pending,
            is_failed=self.is_failed,
            is_cancelled=self.is_cancelled,
            source_event_ids=self.source_event_ids,
        )

    def with_home_amount(
        self,
        home_currency_amount: Decimal | None,
    ) -> "NormalizedFinancialEvent":
        """Return a copy of this event with converted home currency amount."""
        return NormalizedFinancialEvent(
            event_id=self.event_id,
            user_id=self.user_id,
            event_type=self.event_type,
            direction=self.direction,
            original_amount=self.original_amount,
            original_currency=self.original_currency,
            home_currency_amount=home_currency_amount,
            event_date=self.event_date,
            settlement_date=self.settlement_date,
            effective_date=self.effective_date,
            status=self.status,
            linked_event_id=self.linked_event_id,
            lifecycle_id=self.lifecycle_id,
            flexibility=self.flexibility,
            minimum_allowed_amount=self.minimum_allowed_amount,
            is_cash_flow=self.is_cash_flow,
            is_income=self.is_income,
            is_expense=self.is_expense,
            is_transfer=self.is_transfer,
            is_pending=self.is_pending,
            is_failed=self.is_failed,
            is_cancelled=self.is_cancelled,
            source_event_ids=self.source_event_ids,
        )


class FinancialEventNormalizer:
    """Normalizes raw financial events into NormalizedFinancialEvent records."""

    def normalize(
        self,
        event: FinancialEvent,
        home_currency: str | None = None,
    ) -> NormalizedFinancialEvent:
        """Convert one raw financial event into its normalized representation.
        
        Preserves original values without performing multi-event lifecycle decisions.
        """
        # Effective date: settlement date if available, else event date
        effective_date = event.settlement_date if event.settlement_date is not None else event.event_date

        status_lower = event.status.lower().strip()
        is_pending = status_lower == "pending"
        is_failed = status_lower == "failed"
        is_cancelled = status_lower == "cancelled"

        # Classification based on event_type and direction
        event_type_lower = event.event_type.lower().strip()
        direction_lower = event.direction.lower().strip()

        is_income = event_type_lower in ("income", "investment_sale") and direction_lower == "credit"
        is_expense = event_type_lower in ("expense", "debt_payment", "subscription", "investment_purchase") and direction_lower == "debit"
        is_transfer = event_type_lower == "refund"

        # Initial cash-flow eligibility:
        # Non-cash: direction == 'non_cash' or status == 'unrealized'
        # Ineligible: failed, cancelled, or pending credits (until settled)
        if is_failed or is_cancelled or status_lower == "unrealized" or direction_lower == "non_cash":
            is_cash_flow = False
        elif is_pending and direction_lower == "credit":
            is_cash_flow = False
        else:
            is_cash_flow = True

        # Home currency amount if same currency and amount is present
        home_currency_amount: Decimal | None = None
        if home_currency and event.currency == home_currency and event.amount is not None:
            home_currency_amount = event.amount

        return NormalizedFinancialEvent(
            event_id=event.event_id,
            user_id=event.user_id,
            event_type=event.event_type,
            direction=event.direction,
            original_amount=event.amount,
            original_currency=event.currency,
            home_currency_amount=home_currency_amount,
            event_date=event.event_date,
            settlement_date=event.settlement_date,
            effective_date=effective_date,
            status=event.status,
            linked_event_id=event.linked_event_id,
            lifecycle_id=None,
            flexibility=event.flexibility,
            minimum_allowed_amount=event.minimum_allowed_amount,
            is_cash_flow=is_cash_flow,
            is_income=is_income,
            is_expense=is_expense,
            is_transfer=is_transfer,
            is_pending=is_pending,
            is_failed=is_failed,
            is_cancelled=is_cancelled,
            source_event_ids=(event.event_id,),
        )

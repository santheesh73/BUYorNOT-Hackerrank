"""Pydantic data models for the BUYorNOT challenge."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from utils.dates import parse_date, parse_datetime
from utils.money import parse_money
from utils.paths import get_image_path


def _clean_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "nan", "NaN", "None", "<NA>") else s


def _split_pipe_str(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    s = str(v).strip()
    if s in ("", "nan", "NaN", "None", "<NA>"):
        return []
    return [item.strip() for item in s.split("|") if item.strip()]


class Request(BaseModel):
    """Evaluation request model."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str

    @field_validator("request_id", "user_id", "request_type", "request_text", mode="before")
    @classmethod
    def _validate_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required string field cannot be empty")
        return s

    @field_validator("request_date", "desired_completion_date", mode="before")
    @classmethod
    def _validate_date(cls, v: Any) -> date:
        d = parse_date(v)
        if d is None:
            raise ValueError("Date field cannot be empty")
        return d

    @field_validator("requested_amount", mode="before")
    @classmethod
    def _validate_money(cls, v: Any) -> Decimal:
        m = parse_money(v)
        if m is None:
            raise ValueError("requested_amount cannot be empty")
        return m

    @field_validator("allows_partial_payment", mode="before")
    @classmethod
    def _validate_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("true", "1", "t", "yes", "y"):
            return True
        if s in ("false", "0", "f", "no", "n"):
            return False
        raise ValueError(f"Cannot parse boolean from '{v}'")


class SampleRequest(Request):
    """Sample request model with completed reference solution fields."""
    amount_safe_to_pay: Decimal | None = None
    affordability_status: str | None = None
    recommended_payment_method: str | None = None
    payment_plan: str | None = None
    earliest_date_for_full_payment: date | None = None
    spending_changes_needed: str | None = None
    decision_explanation: str | None = None

    @field_validator("earliest_date_for_full_payment", mode="before")
    @classmethod
    def _validate_opt_date(cls, v: Any) -> date | None:
        return parse_date(v)

    @field_validator("amount_safe_to_pay", mode="before")
    @classmethod
    def _validate_opt_money(cls, v: Any) -> Decimal | None:
        return parse_money(v)

    @field_validator(
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "spending_changes_needed",
        "decision_explanation",
        mode="before",
    )
    @classmethod
    def _validate_opt_str(cls, v: Any) -> str | None:
        return _clean_str(v)


class FinancialProfile(BaseModel):
    """User financial profile."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: list[str]
    expense_categories_to_protect: list[str]
    expense_categories_user_is_willing_to_reduce: list[str]
    expense_categories_user_is_willing_to_stop: list[str]
    payment_methods_user_will_consider: list[str]
    max_installment_months: int | None = None

    @field_validator("user_id", "home_currency", mode="before")
    @classmethod
    def _validate_req_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required field cannot be empty")
        return s

    @field_validator("current_available_balance", "minimum_balance_to_keep", mode="before")
    @classmethod
    def _validate_req_money(cls, v: Any) -> Decimal:
        m = parse_money(v)
        if m is None:
            raise ValueError("Balance field cannot be empty")
        return m

    @field_validator(
        "financial_priorities",
        "expense_categories_to_protect",
        "expense_categories_user_is_willing_to_reduce",
        "expense_categories_user_is_willing_to_stop",
        "payment_methods_user_will_consider",
        mode="before",
    )
    @classmethod
    def _validate_pipe_lists(cls, v: Any) -> list[str]:
        return _split_pipe_str(v)

    @field_validator("max_installment_months", mode="before")
    @classmethod
    def _validate_int(cls, v: Any) -> int | None:
        s = _clean_str(v)
        if s is None:
            return None
        return int(float(s))


class FinancialEvent(BaseModel):
    """Financial event model representing past or future financial events."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Decimal | None = None
    currency: str
    event_date: date
    settlement_date: date | None = None
    status: str
    linked_event_id: str | None = None
    flexibility: str
    minimum_allowed_amount: Decimal | None = None

    @field_validator("event_id", "user_id", "event_type", "description", "category", "direction", "currency", "status", "flexibility", mode="before")
    @classmethod
    def _validate_req_event_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required string field cannot be empty")
        return s

    @field_validator("linked_event_id", mode="before")
    @classmethod
    def _validate_opt_event_str(cls, v: Any) -> str | None:
        return _clean_str(v)

    @field_validator("amount", "minimum_allowed_amount", mode="before")
    @classmethod
    def _validate_event_money(cls, v: Any) -> Decimal | None:
        return parse_money(v)

    @field_validator("event_date", mode="before")
    @classmethod
    def _validate_event_date(cls, v: Any) -> date:
        d = parse_date(v)
        if d is None:
            raise ValueError("event_date cannot be empty")
        return d

    @field_validator("settlement_date", mode="before")
    @classmethod
    def _validate_settlement_date(cls, v: Any) -> date | None:
        return parse_date(v)


class ExchangeRate(BaseModel):
    """Exchange rate model for fixed conversion rates."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal

    @field_validator("rate_date", mode="before")
    @classmethod
    def _validate_date(cls, v: Any) -> date:
        d = parse_date(v)
        if d is None:
            raise ValueError("rate_date cannot be empty")
        return d

    @field_validator("from_currency", "to_currency", mode="before")
    @classmethod
    def _validate_curr(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Currency field cannot be empty")
        return s

    @field_validator("rate", mode="before")
    @classmethod
    def _validate_rate(cls, v: Any) -> Decimal:
        m = parse_money(v)
        if m is None:
            raise ValueError("rate cannot be empty")
        return m


class PaymentOption(BaseModel):
    """Payment option offered by seller/provider."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: int | None = None
    financing_fee: Decimal
    total_payable_amount: Decimal

    @field_validator("payment_option_id", "request_id", "payment_method", mode="before")
    @classmethod
    def _validate_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required string field cannot be empty")
        return s

    @field_validator("payment_amount", "financing_fee", "total_payable_amount", mode="before")
    @classmethod
    def _validate_money(cls, v: Any) -> Decimal:
        m = parse_money(v)
        if m is None:
            raise ValueError("Monetary field cannot be empty")
        return m

    @field_validator("number_of_payments", mode="before")
    @classmethod
    def _validate_int(cls, v: Any) -> int:
        s = _clean_str(v)
        if s is None:
            raise ValueError("number_of_payments cannot be empty")
        return int(float(s))

    @field_validator("payment_frequency_days", mode="before")
    @classmethod
    def _validate_opt_int(cls, v: Any) -> int | None:
        s = _clean_str(v)
        if s is None:
            return None
        return int(float(s))

    @field_validator("first_payment_date", mode="before")
    @classmethod
    def _validate_date(cls, v: Any) -> date:
        d = parse_date(v)
        if d is None:
            raise ValueError("first_payment_date cannot be empty")
        return d


class Message(BaseModel):
    """Message related to user, request, or financial event."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    message_id: str
    user_id: str
    request_id: str | None = None
    related_event_id: str | None = None
    sent_at: datetime
    source_type: str
    message_text: str

    @field_validator("message_id", "user_id", "source_type", "message_text", mode="before")
    @classmethod
    def _validate_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required field cannot be empty")
        return s

    @field_validator("request_id", "related_event_id", mode="before")
    @classmethod
    def _validate_opt_str(cls, v: Any) -> str | None:
        return _clean_str(v)

    @field_validator("sent_at", mode="before")
    @classmethod
    def _validate_dt(cls, v: Any) -> datetime:
        dt = parse_datetime(v)
        if dt is None:
            raise ValueError("sent_at cannot be empty")
        return dt


class ImageReference(BaseModel):
    """Reference to an image linked to an event, request, and user."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    image_id: str
    user_id: str
    request_id: str | None = None
    related_event_id: str | None = None

    @field_validator("image_id", "user_id", mode="before")
    @classmethod
    def _validate_str(cls, v: Any) -> str:
        s = _clean_str(v)
        if s is None:
            raise ValueError("Required field cannot be empty")
        return s

    @field_validator("request_id", "related_event_id", mode="before")
    @classmethod
    def _validate_opt_str(cls, v: Any) -> str | None:
        return _clean_str(v)

    def resolved_path(self, repo_root: Path | None = None) -> Path:
        """Resolve the physical file path for this image."""
        return get_image_path(self.image_id, repo_root=repo_root)

    def file_exists(self, repo_root: Path | None = None) -> bool:
        """Check if the physical image file exists on disk."""
        return self.resolved_path(repo_root=repo_root).is_file()

"""Evidence domain models for Phase 3: Message & Image Evidence Resolution."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class FinancialEvidence:
    """Structured, traceable financial fact derived from unstructured evidence (messages or images)."""

    evidence_id: str
    user_id: str

    source_type: str  # "message" | "image"
    source_id: str    # e.g., "message_01", "image_01"

    event_id: str | None
    request_id: str | None

    fact_type: str    # e.g., "income_salary_update", "expense_rent_increase", "amount_extracted", "date_change"
    value: str | None
    numeric_value: Decimal | None
    currency: str | None

    effective_date: date | None

    confidence: Decimal

    source_text: str | None
    source_path: str | None

    @property
    def fact_category(self) -> str:
        """Categorize fact into one of: 'income', 'expense', 'amount', 'date', 'other'."""
        ft = self.fact_type.lower()
        if ft.startswith("date") or "reschedule" in ft:
            return "date"
        elif (
            ft.startswith("income")
            or "salary" in ft
            or "employment_ended" in ft
            or "seasonal_ended" in ft
            or "invoice_approved" in ft
        ):
            return "income"
        elif ft.startswith("expense") or "rent" in ft or "debit_retry" in ft:
            return "expense"
        elif ft.startswith("amount") or ft in ("image_amount", "invoice_amount", "bill_amount"):
            return "amount"
        else:
            return "other"

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= Decimal("0.80")

    @property
    def is_medium_confidence(self) -> bool:
        return Decimal("0.50") <= self.confidence < Decimal("0.80")

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < Decimal("0.50")

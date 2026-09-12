"""Unit tests for code/data/models.py."""

from datetime import date, datetime
from decimal import Decimal
import pytest

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


def test_request_model_parsing():
    raw = {
        "request_id": "req_100",
        "user_id": "user_100",
        "request_date": "2025-05-01",
        "request_type": "purchase",
        "requested_amount": "1500.50",
        "desired_completion_date": "2025-06-01",
        "allows_partial_payment": "true",
        "request_text": "Can I buy this?",
    }
    req = Request.model_validate(raw)
    assert req.request_id == "req_100"
    assert req.user_id == "user_100"
    assert req.request_date == date(2025, 5, 1)
    assert req.requested_amount == Decimal("1500.50")
    assert req.allows_partial_payment is True


def test_request_model_invalid_amount():
    raw = {
        "request_id": "req_100",
        "user_id": "user_100",
        "request_date": "2025-05-01",
        "request_type": "purchase",
        "requested_amount": "invalid_amount",
        "desired_completion_date": "2025-06-01",
        "allows_partial_payment": "true",
        "request_text": "Can I buy this?",
    }
    with pytest.raises(ValueError):
        Request.model_validate(raw)


def test_financial_profile_pipe_fields():
    raw = {
        "user_id": "user_01",
        "home_currency": "ZAR",
        "current_available_balance": "58481.1",
        "minimum_balance_to_keep": "18000",
        "financial_priorities": "education|debt_repayment",
        "expense_categories_to_protect": "rent|groceries",
        "expense_categories_user_is_willing_to_reduce": "dining",
        "expense_categories_user_is_willing_to_stop": "",
        "payment_methods_user_will_consider": "full_payment|installments",
        "max_installment_months": "6",
    }
    prof = FinancialProfile.model_validate(raw)
    assert prof.financial_priorities == ["education", "debt_repayment"]
    assert prof.expense_categories_to_protect == ["rent", "groceries"]
    assert prof.expense_categories_user_is_willing_to_reduce == ["dining"]
    assert prof.expense_categories_user_is_willing_to_stop == []
    assert prof.payment_methods_user_will_consider == ["full_payment", "installments"]
    assert prof.max_installment_months == 6


def test_financial_event_missing_amount_preserved():
    raw = {
        "event_id": "event_253",
        "user_id": "user_03",
        "event_type": "income",
        "description": "Salary payment",
        "category": "salary",
        "direction": "credit",
        "amount": "",  # Missing amount to be extracted from image
        "currency": "IDR",
        "event_date": "2019-09-25",
        "settlement_date": "2019-09-25",
        "status": "settled",
        "linked_event_id": "",
        "flexibility": "fixed",
        "minimum_allowed_amount": "",
    }
    ev = FinancialEvent.model_validate(raw)
    assert ev.amount is None  # NEVER fabricated as 0
    assert ev.linked_event_id is None
    assert ev.minimum_allowed_amount is None


def test_payment_option_model():
    raw = {
        "payment_option_id": "opt_01",
        "request_id": "req_01",
        "payment_method": "installments",
        "payment_amount": "500.00",
        "number_of_payments": "3",
        "first_payment_date": "2024-03-10",
        "payment_frequency_days": "30",
        "financing_fee": "25.00",
        "total_payable_amount": "1525.00",
    }
    opt = PaymentOption.model_validate(raw)
    assert opt.payment_amount == Decimal("500.00")
    assert opt.number_of_payments == 3
    assert opt.payment_frequency_days == 30
    assert opt.total_payable_amount == Decimal("1525.00")


def test_image_reference_model():
    raw = {
        "image_id": "image_01",
        "user_id": "user_03",
        "request_id": "request_03",
        "related_event_id": "event_253",
    }
    img = ImageReference.model_validate(raw)
    assert img.image_id == "image_01"
    assert img.file_exists() is True

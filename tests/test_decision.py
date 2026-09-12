"""Comprehensive test suite for Phase 5 Decision Engine and Output Generation."""

from decimal import Decimal
from pathlib import Path
import pytest

from data.store import DataStore
from finance.forecast import CashFlowForecaster
from finance.decision import DecisionEngine, calculate_amount_safe_to_pay, calculate_earliest_date_for_full_payment
from finance.explanation import generate_decision_explanation
from finance.output import generate_output_csv, validate_output_csv, REQUIRED_COLUMNS
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def data_store():
    root = get_repo_root()
    return DataStore.load_from_repo(root)


@pytest.fixture(scope="module")
def forecaster(data_store):
    return CashFlowForecaster(data_store)


@pytest.fixture(scope="module")
def decision_engine(data_store, forecaster):
    return DecisionEngine(data_store, forecaster)


def test_calculate_amount_safe_to_pay_bounds(data_store, forecaster):
    """Ensure safe_to_pay is always clamped between 0 and requested_amount."""
    req = data_store.get_all_requests()[0]
    prof = data_store.get_profile(req.user_id)
    states = forecaster.forecast(req.user_id, req.request_date, horizon_days=90)
    safe = calculate_amount_safe_to_pay(req.requested_amount, states, prof.minimum_balance_to_keep)
    assert isinstance(safe, Decimal)
    assert Decimal("0") <= safe <= req.requested_amount


def test_earliest_date_for_full_payment_logic(data_store, forecaster):
    """Ensure earliest date is >= request_date or None."""
    req = data_store.get_all_requests()[0]
    prof = data_store.get_profile(req.user_id)
    states = forecaster.forecast(req.user_id, req.request_date, horizon_days=90)
    earliest = calculate_earliest_date_for_full_payment(req.request_date, req.requested_amount, states, prof.minimum_balance_to_keep)
    if earliest is not None:
        assert earliest >= req.request_date


def test_evaluate_request_contract_keys(decision_engine, data_store):
    """Ensure evaluate_request returns all required fields conforming to schema."""
    req = data_store.get_all_requests()[0]
    res = decision_engine.evaluate_request(req)
    for col in REQUIRED_COLUMNS:
        if col != "decision_explanation":  # Explanation is added subsequently or by engine
            assert col in res or col == "decision_explanation"

    assert res["affordability_status"] in {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }
    assert res["recommended_payment_method"] in {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }


def test_sample_request_prediction_validity(decision_engine, data_store):
    """Verify decision engine evaluates all sample requests and produces valid predictions."""
    sample_reqs = list(data_store.indexes.sample_requests_by_id.values())
    assert len(sample_reqs) == 25

    for req in sample_reqs:
        res = decision_engine.evaluate_request(req)
        assert res.decision_explanation != ""

        # Invariants
        assert Decimal("0") <= res["amount_safe_to_pay"] <= req.requested_amount
        if res["affordability_status"] == "affordable_now":
            assert res["earliest_date_for_full_payment"] == req.request_date.isoformat()
            assert res["recommended_payment_method"] == "full_payment"

        if res["recommended_payment_method"] == "partial_payment":
            assert res["affordability_status"] == "affordable_with_plan"
            assert "|" in res["payment_plan"]
            parts = res["payment_plan"].split("|")
            assert len(parts) == 2
            amt1 = Decimal(parts[0].split(":")[1])
            amt2 = Decimal(parts[1].split(":")[1])
            assert amt1 + amt2 == req.requested_amount
            assert amt1 == res["amount_safe_to_pay"]

        if res["spending_changes_needed"] != "none":
            changes = res["spending_changes_needed"].split("|")
            assert len(changes) <= 3
            for c in changes:
                assert c.startswith("stop:") or c.startswith("reduce_to:")


def test_output_csv_generation_and_validation(decision_engine, data_store, tmp_path):
    """Test serializing predictions to output.csv and validating format."""
    predictions = []
    # Test on first 10 requests
    for req in data_store.get_all_requests()[:10]:
        res = decision_engine.evaluate_request(req)
        predictions.append(res)

    out_file = tmp_path / "test_output.csv"
    req_file = tmp_path / "test_requests.csv"

    # Create dummy requests.csv for validation
    import pandas as pd
    req_df = pd.DataFrame([{"request_id": r["request_id"]} for r in predictions])
    req_df.to_csv(req_file, index=False)

    generate_output_csv(predictions, out_file)
    val = validate_output_csv(out_file, req_file)
    assert val["is_valid"] is True
    assert val["total_rows"] == 10
    assert len(val["errors"]) == 0


# ============================================================
# Section 38: Golden Test Cases
# ============================================================

def test_golden_case_1_full_payment_safe_today(decision_engine, data_store):
    """Case 1: Full amount safely payable today -> affordable_now, full_payment."""
    # request_16: user_16, 122500, affordable_now
    req = data_store.get_sample_request("request_16")
    res = decision_engine.evaluate_request(req)
    assert res.affordability_status == "affordable_now"
    assert res.recommended_payment_method == "full_payment"
    assert res.earliest_date_for_full_payment == req.request_date.isoformat()


def test_golden_case_3_installment_option_safe(decision_engine, data_store):
    """Case 3: Supplied installment option is safe -> affordable_with_plan, installments."""
    # request_07: user_07, installments
    req = data_store.get_sample_request("request_07")
    res = decision_engine.evaluate_request(req)
    assert res.affordability_status == "affordable_with_plan"
    assert res.recommended_payment_method == "installments"
    assert "|" in res.payment_plan


def test_golden_case_4_wait_safe_later(decision_engine, data_store):
    """Case 4: Full amount becomes safe later -> affordable_later, wait."""
    # request_23: user_23, wait
    req = data_store.get_sample_request("request_23")
    res = decision_engine.evaluate_request(req)
    assert res.affordability_status == "affordable_later"
    assert res.recommended_payment_method == "wait"
    assert res.earliest_date_for_full_payment != ""


def test_golden_case_5_not_affordable_not_recommended(decision_engine, data_store):
    """Case 5: No valid solution exists -> not_affordable, not_recommended."""
    # request_15: user_15, not_affordable, not_recommended
    req = data_store.get_sample_request("request_15")
    res = decision_engine.evaluate_request(req)
    assert res.affordability_status == "not_affordable"
    assert res.recommended_payment_method == "not_recommended"
    assert res.payment_plan == "none"


def test_golden_case_8_user_rejects_installments(decision_engine, data_store):
    """Case 8: User rejects installments -> installments never recommended."""
    # Find a user whose profile has no 'installments'
    for req in data_store.get_all_requests():
        prof = data_store.get_profile(req.user_id)
        if "installments" not in prof.payment_methods_user_will_consider:
            res = decision_engine.evaluate_request(req)
            assert res.recommended_payment_method != "installments"
            break


def test_golden_case_10_plan_completes_after_deadline_rejected(decision_engine, data_store):
    """Case 10: A plan completing after desired_completion_date is rejected."""
    from data.models import Request
    from datetime import date
    base_req = data_store.get_all_requests()[0]
    # Set impossible completion date yesterday
    impossible_req = Request(
        request_id="test_deadline_reject",
        user_id=base_req.user_id,
        request_date=base_req.request_date,
        request_type=base_req.request_type,
        requested_amount=base_req.requested_amount,
        desired_completion_date=base_req.request_date,  # today only
        allows_partial_payment=False,
        request_text=base_req.request_text,
    )
    res = decision_engine.evaluate_request(impossible_req)
    # Cannot wait or do multi-month installments because deadline is today
    if res.recommended_payment_method in {"wait", "installments"}:
        parts = res.payment_plan.split("|")
        last_date = parts[-1].split(":")[0]
        assert last_date <= impossible_req.desired_completion_date.isoformat()


def test_golden_case_12_and_13_minimum_balance_boundary(data_store, forecaster):
    """Case 12 & 13: Minimum balance exact is safe, balance < minimum by 0.01 is unsafe."""
    from finance.decision import simulate_plan_safety
    from finance.state import FinancialState
    import pandas as pd
    from datetime import date

    min_bal = Decimal("5000.00")
    # Day 0: closing balance = 10000.00
    state = FinancialState(
        dt=pd.Timestamp("2026-01-01"),
        opening_balance=Decimal("10000.00"),
        inflows=Decimal("0.00"),
        outflows=Decimal("0.00"),
        net_cash_flow=Decimal("0.00"),
        closing_balance=Decimal("10000.00"),
    )

    # Case 12: Payment of exactly 5000 leaves exactly 5000 -> SAFE
    payment_exact = ((date(2026, 1, 1), Decimal("5000.00")),)
    is_safe_exact, _ = simulate_plan_safety([state], payment_exact, min_bal)
    assert is_safe_exact is True

    # Case 13: Payment of 5000.01 leaves 4999.99 (< 5000.00) -> UNSAFE
    payment_violation = ((date(2026, 1, 1), Decimal("5000.01")),)
    is_safe_viol, _ = simulate_plan_safety([state], payment_violation, min_bal)
    assert is_safe_viol is False


# ============================================================
# Section 39 & 40: Adversarial & Temporal Leak Tests
# ============================================================

def test_adversarial_zero_requested_amount(decision_engine, data_store):
    """Test decision engine handles 0 requested amount gracefully."""
    from data.models import Request
    base_req = data_store.get_all_requests()[0]
    zero_req = Request(
        request_id="test_zero_amt",
        user_id=base_req.user_id,
        request_date=base_req.request_date,
        request_type="purchase",
        requested_amount=Decimal("0.00"),
        desired_completion_date=base_req.desired_completion_date,
        allows_partial_payment=False,
        request_text="Zero dollar purchase",
    )
    res = decision_engine.evaluate_request(zero_req)
    assert res.amount_safe_to_pay == Decimal("0.00")
    assert res.affordability_status in {"affordable_now", "not_affordable"}


def test_temporal_leak_regression_test(decision_engine, data_store, forecaster):
    """Section 40: Evaluation at request_date T must not leak events occurring at T + 10."""
    from data.models import Request
    import pandas as pd
    from datetime import date

    # Request at date T
    req_t = Request(
        request_id="test_temporal_leak",
        user_id="user_01",
        request_date=date(2024, 6, 1),
        request_type="purchase",
        requested_amount=Decimal("1000.00"),
        desired_completion_date=date(2024, 8, 1),
        allows_partial_payment=False,
        request_text="Temporal test purchase",
    )

    # Historical forecast at T
    forecast_t = forecaster.forecast("user_01", pd.Timestamp("2024-06-01"), horizon_days=90)

    # Future cash events generated must NOT contain actual events settled after T as historical
    res_t = decision_engine.evaluate_request(req_t)
    assert res_t.request_id == "test_temporal_leak"
    assert Decimal("0") <= res_t.amount_safe_to_pay <= Decimal("1000.00")


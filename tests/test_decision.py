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
        profile = data_store.get_profile(req.user_id)
        expl = generate_decision_explanation(req, profile, res)
        res["decision_explanation"] = expl

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
        profile = data_store.get_profile(req.user_id)
        res["decision_explanation"] = generate_decision_explanation(req, profile, res)
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

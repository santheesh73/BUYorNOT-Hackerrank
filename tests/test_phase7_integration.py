"""Phase 7 end-to-end integration, optimization, and evaluation-readiness tests."""

from decimal import Decimal
from pathlib import Path
import pytest
import pandas as pd

from data.loader import load_datasets
from data.indexes import build_indexes
from data.store import DataStore
from finance.forecast import CashFlowForecaster
from finance.decision import DecisionEngine
from finance.output import validate_output_csv, REQUIRED_COLUMNS
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def data_store():
    root = get_repo_root()
    datasets = load_datasets(root)
    indexes = build_indexes(datasets)
    return DataStore(datasets, indexes)


@pytest.fixture(scope="module")
def forecaster(data_store):
    return CashFlowForecaster(data_store)


@pytest.fixture(scope="module")
def decision_engine(data_store, forecaster):
    return DecisionEngine(data_store=data_store, forecaster=forecaster)


# ============================================================
# 1. Determinism & State Safety Test
# ============================================================

def test_determinism_and_state_immutability(decision_engine, data_store):
    """Evaluating the same request repeatedly must return bitwise identical decisions."""
    requests = data_store.get_all_requests()[:5]

    for req in requests:
        res1 = decision_engine.evaluate_request(req)
        res2 = decision_engine.evaluate_request(req)

        assert res1.request_id == res2.request_id
        assert res1.amount_safe_to_pay == res2.amount_safe_to_pay
        assert res1.affordability_status == res2.affordability_status
        assert res1.recommended_payment_method == res2.recommended_payment_method
        assert res1.payment_plan == res2.payment_plan
        assert res1.earliest_date_for_full_payment == res2.earliest_date_for_full_payment
        assert res1.spending_changes_needed == res2.spending_changes_needed
        assert res1.decision_explanation == res2.decision_explanation


# ============================================================
# 2. Contract-First Invariants Test
# ============================================================

def test_decision_contract_invariants(decision_engine, data_store):
    """Test that all evaluated decisions strictly conform to contract invariants."""
    requests = data_store.get_all_requests()[:20]

    for req in requests:
        res = decision_engine.evaluate_request(req)

        # 1. Amount safe to pay bounds
        assert Decimal("0.00") <= res.amount_safe_to_pay <= req.requested_amount

        # 2. Status / method consistency
        if res.affordability_status == "affordable_now":
            assert res.recommended_payment_method == "full_payment"
            assert res.earliest_date_for_full_payment == req.request_date.isoformat()
        elif res.affordability_status == "not_affordable":
            assert res.recommended_payment_method == "not_recommended"
            assert res.payment_plan == "none"
        elif res.recommended_payment_method == "wait":
            assert res.affordability_status == "affordable_later"
            assert res.payment_plan != "none"
            assert res.earliest_date_for_full_payment != ""

        # 3. Explanation non-empty
        assert res.decision_explanation.strip() != ""


# ============================================================
# 3. Output Reconciliation & Schema Invariants
# ============================================================

def test_output_file_reconciliation(data_store):
    """Verify that dataset/output.csv exists, has exactly 250 rows, and satisfies contract."""
    root = get_repo_root()
    output_path = root / "dataset" / "output.csv"
    requests_path = root / "dataset" / "requests.csv"

    assert output_path.is_file(), "dataset/output.csv must exist"
    val = validate_output_csv(output_path, requests_path)

    assert val["is_valid"] is True, f"Output validation failed with errors: {val['errors']}"
    assert val["total_rows"] == 250
    assert len(val["errors"]) == 0

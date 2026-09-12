"""Unit tests for code/data/validators.py."""

from copy import deepcopy
from pathlib import Path
import pytest

from data.indexes import build_indexes
from data.loader import load_datasets
from data.models import Request
from data.store import DataStore
from data.validators import (
    generate_data_quality_report,
    validate_datasets,
)
from utils.paths import get_repo_root


@pytest.fixture(scope="module")
def real_store():
    root = get_repo_root()
    return DataStore.load_from_repo(repo_root=root)


def test_real_dataset_validation(real_store: DataStore):
    report = validate_datasets(store=real_store)
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert len(report.duplicate_ids) == 0
    assert len(report.referential_errors) == 0
    assert len(report.missing_image_files) == 0
    assert report.physical_images_count == 16
    assert len(report.blank_amount_events) == 16

    # Test report text generation
    report_text = generate_data_quality_report(report)
    assert "BUYorNOT DATA QUALITY REPORT" in report_text
    assert "PASSED" in report_text


def test_referential_integrity_violation_detected(real_store: DataStore):
    # Create a corrupted datasets copy with a request pointing to a missing user
    corrupted_datasets = deepcopy(real_store.datasets)
    corrupted_req = Request.model_validate({
        "request_id": "bad_req_999",
        "user_id": "non_existent_user_999",
        "request_date": "2025-01-01",
        "request_type": "purchase",
        "requested_amount": "100",
        "desired_completion_date": "2025-02-01",
        "allows_partial_payment": "false",
        "request_text": "Bad request",
    })
    corrupted_datasets.requests.append(corrupted_req)

    corrupted_store = DataStore(datasets=corrupted_datasets)
    report = validate_datasets(store=corrupted_store)

    assert report.is_valid is False
    assert any("non_existent_user_999" in err for err in report.referential_errors)


def test_missing_image_file_detected(real_store: DataStore, tmp_path: Path):
    # Validation against a temporary empty root where images don't exist
    report = validate_datasets(store=real_store, repo_root=tmp_path)
    assert report.is_valid is False
    assert len(report.missing_image_files) > 0

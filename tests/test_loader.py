"""Unit tests for code/data/loader.py."""

from pathlib import Path
import pytest

from data.loader import (
    REQUIRED_DATASETS,
    load_datasets,
    load_raw_csv,
)
from utils.paths import get_repo_root


def test_load_all_challenge_datasets():
    root = get_repo_root()
    datasets = load_datasets(repo_root=root)

    assert len(datasets.requests) == 250
    assert len(datasets.sample_requests) == 25
    assert len(datasets.financial_profiles) == 275
    assert len(datasets.financial_events) == 25342
    assert len(datasets.exchange_rates) == 134
    assert len(datasets.payment_options) == 790
    assert len(datasets.messages) == 215
    assert len(datasets.images) == 16

    # Verify raw_dfs contains all required filenames
    for filename in REQUIRED_DATASETS:
        assert filename in datasets.raw_dfs
        assert not datasets.raw_dfs[filename].empty


def test_load_missing_file_raises_error(tmp_path: Path):
    non_existent = tmp_path / "non_existent.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_raw_csv(non_existent)
    assert "not found" in str(exc_info.value)


def test_load_datasets_from_empty_dir_raises_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_datasets(repo_root=tmp_path)

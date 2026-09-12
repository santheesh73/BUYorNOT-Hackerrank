"""Central data loading layer for the BUYorNOT dataset."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

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
from utils.paths import get_csv_path, get_repo_root

logger = logging.getLogger(__name__)

REQUIRED_DATASETS = [
    "requests.csv",
    "sample_requests.csv",
    "financial_profiles.csv",
    "financial_events.csv",
    "exchange_rates.csv",
    "request_payment_options.csv",
    "messages.csv",
    "images.csv",
]


@dataclass
class LoadedDatasets:
    """Container for all loaded datasets (both typed models and raw DataFrames)."""
    requests: list[Request]
    sample_requests: list[SampleRequest]
    financial_profiles: list[FinancialProfile]
    financial_events: list[FinancialEvent]
    exchange_rates: list[ExchangeRate]
    payment_options: list[PaymentOption]
    messages: list[Message]
    images: list[ImageReference]
    raw_dfs: dict[str, pd.DataFrame] = field(default_factory=dict)


def load_raw_csv(file_path: Path) -> pd.DataFrame:
    """Load a CSV file with string typing for all columns to avoid loss of precision or ID truncation.
    
    Raises FileNotFoundError if the file does not exist.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Required dataset file not found at: {file_path}")
    
    return pd.read_csv(file_path, dtype=str, keep_default_na=False)


def load_datasets(repo_root: Path | None = None) -> LoadedDatasets:
    """Load all challenge CSV datasets from the dataset directory into memory.
    
    Reads each file once, parses into typed models, and stores raw DataFrames.
    """
    root = repo_root or get_repo_root()
    logger.info("Loading datasets from root: %s", root)

    raw_dfs: dict[str, pd.DataFrame] = {}

    for filename in REQUIRED_DATASETS:
        csv_path = get_csv_path(filename, repo_root=root)
        logger.debug("Loading %s...", csv_path)
        raw_dfs[filename] = load_raw_csv(csv_path)

    # Parse into typed models
    requests = [
        Request.model_validate(row)
        for row in raw_dfs["requests.csv"].to_dict(orient="records")
    ]

    sample_requests = [
        SampleRequest.model_validate(row)
        for row in raw_dfs["sample_requests.csv"].to_dict(orient="records")
    ]

    financial_profiles = [
        FinancialProfile.model_validate(row)
        for row in raw_dfs["financial_profiles.csv"].to_dict(orient="records")
    ]

    financial_events = [
        FinancialEvent.model_validate(row)
        for row in raw_dfs["financial_events.csv"].to_dict(orient="records")
    ]

    exchange_rates = [
        ExchangeRate.model_validate(row)
        for row in raw_dfs["exchange_rates.csv"].to_dict(orient="records")
    ]

    payment_options = [
        PaymentOption.model_validate(row)
        for row in raw_dfs["request_payment_options.csv"].to_dict(orient="records")
    ]

    messages = [
        Message.model_validate(row)
        for row in raw_dfs["messages.csv"].to_dict(orient="records")
    ]

    images = [
        ImageReference.model_validate(row)
        for row in raw_dfs["images.csv"].to_dict(orient="records")
    ]

    logger.info(
        "Successfully loaded %d requests, %d samples, %d profiles, %d events, "
        "%d FX rates, %d options, %d messages, %d image refs.",
        len(requests),
        len(sample_requests),
        len(financial_profiles),
        len(financial_events),
        len(exchange_rates),
        len(payment_options),
        len(messages),
        len(images),
    )

    return LoadedDatasets(
        requests=requests,
        sample_requests=sample_requests,
        financial_profiles=financial_profiles,
        financial_events=financial_events,
        exchange_rates=exchange_rates,
        payment_options=payment_options,
        messages=messages,
        images=images,
        raw_dfs=raw_dfs,
    )

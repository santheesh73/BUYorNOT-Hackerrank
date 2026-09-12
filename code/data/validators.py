"""Comprehensive dataset validation and data quality diagnostics for BUYorNOT."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from data.models import FinancialEvent
from data.store import DataStore
from utils.paths import get_images_dir, get_repo_root


@dataclass
class ValidationReport:
    """Detailed results of structural, type, and referential integrity checks."""
    is_valid: bool = True
    row_counts: dict[str, int] = field(default_factory=dict)
    physical_images_count: int = 0
    duplicate_ids: dict[str, list[str]] = field(default_factory=dict)
    referential_errors: list[str] = field(default_factory=list)
    missing_image_files: list[str] = field(default_factory=list)
    blank_amount_events: list[str] = field(default_factory=list)
    currencies: list[str] = field(default_factory=list)
    event_statuses: dict[str, int] = field(default_factory=dict)
    event_types: dict[str, int] = field(default_factory=dict)
    linked_events_count: int = 0
    date_ranges: dict[str, tuple[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_datasets(store: DataStore, repo_root: Path | None = None) -> ValidationReport:
    """Run thorough structural, referential, and data quality validation on the loaded DataStore."""
    root = repo_root or get_repo_root()
    report = ValidationReport()

    # 1. Dataset Row Counts
    report.row_counts = {
        "Requests": len(store.datasets.requests),
        "Sample Requests": len(store.datasets.sample_requests),
        "Financial Profiles": len(store.datasets.financial_profiles),
        "Financial Events": len(store.datasets.financial_events),
        "Exchange Rates": len(store.datasets.exchange_rates),
        "Payment Options": len(store.datasets.payment_options),
        "Messages": len(store.datasets.messages),
        "Images": len(store.datasets.images),
    }

    # Physical images on disk
    images_dir = get_images_dir(repo_root=root)
    if images_dir.is_dir():
        physical_files = list(images_dir.glob("*.png"))
        report.physical_images_count = len(physical_files)
    else:
        report.physical_images_count = 0
        report.errors.append(f"Images directory not found at: {images_dir}")

    # 2. Check Duplicate IDs
    raw_dfs = store.datasets.raw_dfs
    id_columns = {
        "requests.csv": "request_id",
        "sample_requests.csv": "request_id",
        "financial_profiles.csv": "user_id",
        "financial_events.csv": "event_id",
        "request_payment_options.csv": "payment_option_id",
        "messages.csv": "message_id",
        "images.csv": "image_id",
    }
    for file_name, id_col in id_columns.items():
        if file_name in raw_dfs and id_col in raw_dfs[file_name].columns:
            dups = raw_dfs[file_name][raw_dfs[file_name][id_col].duplicated()][id_col].tolist()
            if dups:
                report.duplicate_ids[file_name] = dups
                report.errors.append(f"Duplicate identifiers found in {file_name}: {dups}")

    # 3. Referential Integrity Checks
    all_user_ids = set(store.indexes.profiles_by_user.keys())
    all_request_ids = set(store.indexes.requests_by_id.keys()) | set(store.indexes.sample_requests_by_id.keys())
    all_event_ids = set(store.indexes.events_by_id.keys())

    # Requests -> Users
    for req in store.datasets.requests:
        if req.user_id not in all_user_ids:
            report.referential_errors.append(f"Request {req.request_id} references missing user: {req.user_id}")

    for sreq in store.datasets.sample_requests:
        if sreq.user_id not in all_user_ids:
            report.referential_errors.append(f"Sample request {sreq.request_id} references missing user: {sreq.user_id}")

    # Events -> Users & Linked Events
    for ev in store.datasets.financial_events:
        if ev.user_id not in all_user_ids:
            report.referential_errors.append(f"Event {ev.event_id} references missing user: {ev.user_id}")
        if ev.linked_event_id:
            report.linked_events_count += 1
            if ev.linked_event_id not in all_event_ids:
                report.referential_errors.append(
                    f"Event {ev.event_id} linked to non-existent event: {ev.linked_event_id}"
                )

    # Payment Options -> Requests
    for opt in store.datasets.payment_options:
        if opt.request_id not in all_request_ids:
            report.referential_errors.append(
                f"Payment option {opt.payment_option_id} references missing request: {opt.request_id}"
            )

    # Messages -> Users, Requests, Events
    for msg in store.datasets.messages:
        if msg.user_id not in all_user_ids:
            report.referential_errors.append(f"Message {msg.message_id} references missing user: {msg.user_id}")
        if msg.request_id and msg.request_id not in all_request_ids:
            report.referential_errors.append(f"Message {msg.message_id} references missing request: {msg.request_id}")
        if msg.related_event_id and msg.related_event_id not in all_event_ids:
            report.referential_errors.append(f"Message {msg.message_id} references missing event: {msg.related_event_id}")

    # Images -> Users, Requests, Events & Physical File Existence
    for img in store.datasets.images:
        if img.user_id not in all_user_ids:
            report.referential_errors.append(f"Image {img.image_id} references missing user: {img.user_id}")
        if img.request_id and img.request_id not in all_request_ids:
            report.referential_errors.append(f"Image {img.image_id} references missing request: {img.request_id}")
        if img.related_event_id and img.related_event_id not in all_event_ids:
            report.referential_errors.append(f"Image {img.image_id} references missing event: {img.related_event_id}")
        if not img.file_exists(repo_root=root):
            report.missing_image_files.append(img.image_id)
            report.errors.append(f"Physical image file missing for {img.image_id}: {img.resolved_path(root)}")

    # 4. Blank Financial Amounts Analysis
    for ev in store.datasets.financial_events:
        if ev.amount is None:
            report.blank_amount_events.append(ev.event_id)

    # 5. Domain Aggregations (Currencies, Statuses, Event Types)
    currencies_set = set()
    for prof in store.datasets.financial_profiles:
        currencies_set.add(prof.home_currency)
    for ev in store.datasets.financial_events:
        currencies_set.add(ev.currency)
    report.currencies = sorted(list(currencies_set))

    status_counts = Counter(ev.status for ev in store.datasets.financial_events)
    report.event_statuses = dict(status_counts)

    type_counts = Counter(ev.event_type for ev in store.datasets.financial_events)
    report.event_types = dict(type_counts)

    # 6. Date Ranges
    req_dates = [req.request_date for req in store.datasets.requests]
    if req_dates:
        report.date_ranges["Requests"] = (min(req_dates).isoformat(), max(req_dates).isoformat())

    ev_dates = [ev.event_date for ev in store.datasets.financial_events]
    if ev_dates:
        report.date_ranges["Financial Events (event_date)"] = (min(ev_dates).isoformat(), max(ev_dates).isoformat())

    settlement_dates = [ev.settlement_date for ev in store.datasets.financial_events if ev.settlement_date is not None]
    if settlement_dates:
        report.date_ranges["Financial Events (settlement_date)"] = (
            min(settlement_dates).isoformat(),
            max(settlement_dates).isoformat(),
        )

    fx_dates = [fx.rate_date for fx in store.datasets.exchange_rates]
    if fx_dates:
        report.date_ranges["Exchange Rates"] = (min(fx_dates).isoformat(), max(fx_dates).isoformat())

    # Final error collection
    if report.referential_errors:
        report.errors.extend(report.referential_errors)

    report.is_valid = len(report.errors) == 0
    return report


def generate_data_quality_report(report: ValidationReport) -> str:
    """Format validation and data quality results into a clean, human-readable terminal table."""
    lines = []
    lines.append("=" * 60)
    lines.append("               BUYorNOT DATA QUALITY REPORT")
    lines.append("=" * 60)
    lines.append(f"{'Dataset':<32} {'Rows / Count':>24}")
    lines.append("-" * 60)

    for name, count in report.row_counts.items():
        lines.append(f"{name:<32} {count:>24,}")
    lines.append(f"{'Physical Images on Disk':<32} {report.physical_images_count:>24,}")
    lines.append("-" * 60)

    lines.append("\n[FINANCIAL ATTRIBUTES & DOMAINS]")
    lines.append(f"  Currencies:             {', '.join(report.currencies)}")
    lines.append(f"  Linked Events Count:    {report.linked_events_count:,}")
    lines.append(f"  Blank Financial Amounts:{len(report.blank_amount_events):,} events")
    if report.blank_amount_events:
        lines.append(f"    IDs: {', '.join(report.blank_amount_events)}")

    lines.append("\n[EVENT STATUS DISTRIBUTION]")
    for status, count in sorted(report.event_statuses.items()):
        lines.append(f"  {status:<24} {count:>10,}")

    lines.append("\n[EVENT TYPE DISTRIBUTION]")
    for ev_type, count in sorted(report.event_types.items()):
        lines.append(f"  {ev_type:<24} {count:>10,}")

    lines.append("\n[DATE RANGES]")
    for scope, (start_d, end_d) in report.date_ranges.items():
        lines.append(f"  {scope:<32} {start_d} to {end_d}")

    lines.append("\n[INTEGRITY & VALIDATION STATUS]")
    lines.append(f"  Duplicate Identifiers:  {len(report.duplicate_ids)}")
    lines.append(f"  Invalid References:     {len(report.referential_errors)}")
    lines.append(f"  Missing Image Files:    {len(report.missing_image_files)}")
    lines.append(f"  Total Critical Errors:  {len(report.errors)}")
    lines.append(f"  Validation Status:      {'PASSED' if report.is_valid else 'FAILED'}")
    lines.append("=" * 60)

    return "\n".join(lines)

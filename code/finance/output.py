"""Prediction serialization and output validation for Phase 5."""

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence
import pandas as pd

from utils.dates import parse_date
from utils.money import parse_money

REQUIRED_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

ALLOWED_STATUSES = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}

ALLOWED_METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}


def format_amount_str(val: Decimal | Any) -> str:
    """Format decimal amount as string without unnecessary scientific notation or trailing zeros."""
    if val is None:
        return "0"
    d = Decimal(str(val))
    if d == d.to_integral():
        return str(int(d))
    s = f"{d:.2f}"
    if s.endswith("0"):
        s = s[:-1]
    return s


def generate_output_csv(
    predictions: Sequence[dict[str, Any]],
    output_path: Path,
) -> None:
    """Serialize predictions to output_path adhering strictly to the competition contract."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(REQUIRED_COLUMNS)

        for p in predictions:
            safe_str = format_amount_str(p["amount_safe_to_pay"])
            row = [
                p["request_id"],
                safe_str,
                p["affordability_status"],
                p["recommended_payment_method"],
                p["payment_plan"],
                p.get("earliest_date_for_full_payment", "") or "",
                p["spending_changes_needed"],
                p["decision_explanation"],
            ]
            writer.writerow(row)


def validate_output_csv(output_path: Path, requests_path: Path) -> dict[str, Any]:
    """Validate output_path against requests_path and competition specifications."""
    output_path = Path(output_path)
    requests_path = Path(requests_path)

    if not output_path.is_file():
        raise FileNotFoundError(f"Output file not found: {output_path}")

    req_df = pd.read_csv(requests_path)
    expected_ids = req_df["request_id"].tolist()

    out_df = pd.read_csv(output_path, dtype=str, keep_default_na=False)

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Column names and order
    actual_cols = list(out_df.columns)
    if actual_cols != REQUIRED_COLUMNS:
        errors.append(f"Column mismatch! Expected: {REQUIRED_COLUMNS}, Actual: {actual_cols}")

    # 2. Row count and IDs
    actual_ids = out_df["request_id"].tolist()
    if actual_ids != expected_ids:
        errors.append(f"Request IDs mismatch! Expected {len(expected_ids)} rows, got {len(actual_ids)}")

    # 3. Value validation
    for idx, row in out_df.iterrows():
        req_id = row["request_id"]
        status = row["affordability_status"]
        method = row["recommended_payment_method"]
        plan = row["payment_plan"]
        earliest = row["earliest_date_for_full_payment"]
        spend = row["spending_changes_needed"]
        expl = row["decision_explanation"]

        if status not in ALLOWED_STATUSES:
            errors.append(f"Row {idx} ({req_id}): Invalid status '{status}'")
        if method not in ALLOWED_METHODS:
            errors.append(f"Row {idx} ({req_id}): Invalid method '{method}'")

        if not expl.strip():
            errors.append(f"Row {idx} ({req_id}): Empty decision_explanation")

        if status == "affordable_now":
            if not earliest:
                errors.append(f"Row {idx} ({req_id}): earliest_date_for_full_payment must not be empty for affordable_now")

        if method == "not_recommended":
            if plan != "none":
                errors.append(f"Row {idx} ({req_id}): payment_plan must be 'none' for not_recommended")

        if method == "wait":
            if plan == "none":
                errors.append(f"Row {idx} ({req_id}): payment_plan must not be 'none' for wait")

    return {
        "total_rows": len(out_df),
        "errors": errors,
        "warnings": warnings,
        "is_valid": len(errors) == 0,
    }

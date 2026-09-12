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

    # Build request mapping for deep invariant checking
    req_map = {row["request_id"]: row for _, row in req_df.iterrows()}

    # 3. Value and Invariant validation
    for idx, row in out_df.iterrows():
        req_id = row["request_id"]
        status = row["affordability_status"]
        method = row["recommended_payment_method"]
        plan = row["payment_plan"]
        earliest = row["earliest_date_for_full_payment"]
        spend = row["spending_changes_needed"]
        expl = row["decision_explanation"]
        safe_str = row["amount_safe_to_pay"]

        req_row = req_map.get(req_id)
        if req_row is None:
            errors.append(f"Row {idx} ({req_id}): Unknown request_id")
            continue

        req_date = str(req_row["request_date"]).strip() if "request_date" in req_row else None
        req_amt = Decimal(str(req_row["requested_amount"])) if "requested_amount" in req_row else None

        # Check safe amount
        try:
            safe_amt = Decimal(safe_str)
            if safe_amt < Decimal("0.00"):
                errors.append(f"Row {idx} ({req_id}): amount_safe_to_pay {safe_amt} is negative")
            if req_amt is not None and safe_amt > req_amt:
                errors.append(f"Row {idx} ({req_id}): amount_safe_to_pay {safe_amt} exceeds requested amount {req_amt}")
        except Exception as e:
            errors.append(f"Row {idx} ({req_id}): Invalid amount_safe_to_pay numeric value '{safe_str}': {e}")

        # Check status and method
        if status not in ALLOWED_STATUSES:
            errors.append(f"Row {idx} ({req_id}): Invalid status '{status}'")
        if method not in ALLOWED_METHODS:
            errors.append(f"Row {idx} ({req_id}): Invalid method '{method}'")

        # Check explanation
        if not expl.strip():
            errors.append(f"Row {idx} ({req_id}): Empty decision_explanation")

        # Check earliest date for full payment
        if earliest:
            try:
                parse_date(earliest)
            except Exception:
                errors.append(f"Row {idx} ({req_id}): Invalid date format for earliest_date_for_full_payment '{earliest}'")

        if status == "affordable_now":
            if not earliest:
                errors.append(f"Row {idx} ({req_id}): earliest_date_for_full_payment must not be empty for affordable_now")
            elif req_date is not None and earliest != req_date:
                errors.append(f"Row {idx} ({req_id}): earliest_date_for_full_payment ({earliest}) must equal request_date ({req_date}) for affordable_now")
            if method != "full_payment":
                errors.append(f"Row {idx} ({req_id}): method must be full_payment for affordable_now, got '{method}'")

        if method == "not_recommended":
            if plan != "none":
                errors.append(f"Row {idx} ({req_id}): payment_plan must be 'none' for not_recommended")
            if status != "not_affordable":
                errors.append(f"Row {idx} ({req_id}): status must be 'not_affordable' for not_recommended, got '{status}'")

        if method == "wait":
            if plan == "none":
                errors.append(f"Row {idx} ({req_id}): payment_plan must not be 'none' for wait")
            if status != "affordable_later":
                errors.append(f"Row {idx} ({req_id}): status must be 'affordable_later' for wait, got '{status}'")

        # Check payment plan format & math
        if plan != "none":
            plan_parts = plan.split("|")
            plan_dates = []
            plan_total = Decimal("0.00")
            for p_part in plan_parts:
                if ":" not in p_part:
                    errors.append(f"Row {idx} ({req_id}): Invalid payment_plan format segment '{p_part}'")
                    continue
                p_date_str, p_amt_str = p_part.split(":", 1)
                try:
                    p_date = parse_date(p_date_str)
                    plan_dates.append(p_date)
                except Exception:
                    errors.append(f"Row {idx} ({req_id}): Invalid date in payment_plan '{p_date_str}'")
                try:
                    p_amt = Decimal(p_amt_str)
                    if p_amt <= Decimal("0.00"):
                        errors.append(f"Row {idx} ({req_id}): Non-positive amount in payment_plan '{p_amt_str}'")
                    plan_total += p_amt
                except Exception:
                    errors.append(f"Row {idx} ({req_id}): Invalid numeric amount in payment_plan '{p_amt_str}'")

            # Check chronological order
            for i in range(len(plan_dates) - 1):
                if plan_dates[i] > plan_dates[i + 1]:
                    errors.append(f"Row {idx} ({req_id}): payment_plan dates are not chronological: {plan_dates}")

            if method == "partial_payment":
                if len(plan_parts) != 2:
                    errors.append(f"Row {idx} ({req_id}): partial_payment plan must have exactly 2 payments, got {len(plan_parts)}")
                elif req_amt is not None and plan_total != req_amt:
                    errors.append(f"Row {idx} ({req_id}): partial_payment total {plan_total} does not match requested amount {req_amt}")

        # Check spending changes format
        if spend != "none":
            spend_parts = spend.split("|")
            if len(spend_parts) > 3:
                errors.append(f"Row {idx} ({req_id}): spending_changes_needed exceeds maximum of 3 changes: '{spend}'")
            seen_events = set()
            for s_part in spend_parts:
                if s_part.startswith("stop:"):
                    ev_id = s_part.split(":", 1)[1]
                elif s_part.startswith("reduce_to:"):
                    sub_parts = s_part.split(":")
                    if len(sub_parts) != 3:
                        errors.append(f"Row {idx} ({req_id}): Invalid reduce_to syntax '{s_part}'")
                        continue
                    ev_id = sub_parts[1]
                    try:
                        r_amt = Decimal(sub_parts[2])
                        if r_amt < Decimal("0.00"):
                            errors.append(f"Row {idx} ({req_id}): Negative amount in reduce_to '{s_part}'")
                    except Exception:
                        errors.append(f"Row {idx} ({req_id}): Invalid amount in reduce_to '{s_part}'")
                else:
                    errors.append(f"Row {idx} ({req_id}): Invalid spending change format '{s_part}'")
                    continue

                if ev_id in seen_events:
                    errors.append(f"Row {idx} ({req_id}): Duplicate event modified in spending changes '{ev_id}'")
                seen_events.add(ev_id)

    return {
        "total_rows": len(out_df),
        "errors": errors,
        "warnings": warnings,
        "is_valid": len(errors) == 0,
    }

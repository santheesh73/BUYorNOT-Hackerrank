"""Independent evaluation and verification runner for BUYorNOT.

Validates output.csv against the competition contract, schemas, financial invariants,
and referential integrity across all evaluation requests.
"""

from pathlib import Path
import sys
import pandas as pd
from decimal import Decimal

# Ensure code directory is in sys.path
code_dir = Path(__file__).resolve().parent.parent
repo_root = code_dir.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from finance.output import validate_output_csv, REQUIRED_COLUMNS, ALLOWED_STATUSES, ALLOWED_METHODS
from utils.paths import get_repo_root


def evaluate_submission(repo_root: Path | None = None) -> int:
    """Perform independent contract and financial verification on output predictions."""
    root = repo_root or get_repo_root()
    requests_path = root / "dataset" / "requests.csv"
    output_path = root / "output.csv"
    dataset_output_path = root / "dataset" / "output.csv"

    # Verify output file presence
    target_output = output_path if output_path.is_file() else dataset_output_path
    if not target_output.is_file():
        print(f"[ERROR] Neither {output_path} nor {dataset_output_path} exists!")
        return 1

    print("=" * 60)
    print("BUYorNOT — Independent Evaluation & Contract Verification")
    print("=" * 60)
    print(f"Target Output Path : {target_output}")
    print(f"Requests Path      : {requests_path}")

    # Run comprehensive contract validator
    val_res = validate_output_csv(target_output, requests_path)

    print("\nCONTRACT VALIDATION RESULTS:")
    print(f"- Total Requests Evaluated : {val_res['total_rows']}")
    print(f"- Total Errors             : {len(val_res['errors'])}")
    print(f"- Total Warnings           : {len(val_res['warnings'])}")

    if val_res["errors"]:
        print("\nERRORS DETECTED:")
        for err in val_res["errors"][:10]:
            print(f"  [!] {err}")
        if len(val_res["errors"]) > 10:
            print(f"  ... and {len(val_res['errors']) - 10} more errors")
        print("\nEvaluation Result: FAIL")
        return 1

    # Load output data for summary metrics
    out_df = pd.read_csv(target_output, dtype=str, keep_default_na=False)

    status_counts = out_df["affordability_status"].value_counts().to_dict()
    method_counts = out_df["recommended_payment_method"].value_counts().to_dict()
    spending_changes_count = (out_df["spending_changes_needed"] != "none").sum()

    print("\nSTATUS DISTRIBUTION:")
    for status in sorted(ALLOWED_STATUSES):
        count = status_counts.get(status, 0)
        pct = (count / len(out_df)) * 100
        print(f"  - {status:<22}: {count:3d} ({pct:5.1f}%)")

    print("\nMETHOD DISTRIBUTION:")
    for method in sorted(ALLOWED_METHODS):
        count = method_counts.get(method, 0)
        pct = (count / len(out_df)) * 100
        print(f"  - {method:<22}: {count:3d} ({pct:5.1f}%)")

    print(f"\nRequests requiring spending changes: {spending_changes_count} ({(spending_changes_count/len(out_df))*100:.1f}%)")

    print("\n" + "=" * 60)
    print("Evaluation Result: PASS (All contracts and invariants satisfied)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(evaluate_submission())

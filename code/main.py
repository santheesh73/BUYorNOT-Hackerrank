"""Main entry point for BUYorNOT — Phase 2: Financial Normalization & Lifecycle Resolution."""

import logging
import sys
from pathlib import Path

# Add 'code' directory to sys.path so 'data', 'utils', and 'finance' packages resolve cleanly
code_dir = Path(__file__).resolve().parent
repo_root = code_dir.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from data.indexes import build_indexes
from data.loader import load_datasets
from data.store import DataStore
from data.validators import validate_datasets
from finance.ledger import build_phase2_report, format_phase2_report
from utils.paths import get_repo_root

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("buy_or_not")


def main() -> int:
    """Execute Phase 2 Financial Normalization & Lifecycle Resolution pipeline."""
    root = get_repo_root()
    logger.info("Project root resolved: %s", root)

    logger.info("Loading datasets...")
    datasets = load_datasets(repo_root=root)

    logger.info("Building indexes...")
    indexes = build_indexes(datasets)

    store = DataStore(datasets=datasets, indexes=indexes)

    logger.info("Validating schemas and referential integrity...")
    validation_report = validate_datasets(store=store, repo_root=root)

    logger.info("Initializing Financial Ledger & resolving lifecycles...")
    ledger = store.get_ledger()

    logger.info("Generating Phase 2 diagnostic report...")
    report = build_phase2_report(ledger=ledger, store=store)
    report_text = format_phase2_report(report=report, store=store)
    print("\n" + report_text + "\n")

    if not validation_report.is_valid or report.status != "PASS":
        logger.error("Phase 2 execution encountered errors.")
        return 1

    logger.info("Phase 2 execution complete. Financial ledger verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

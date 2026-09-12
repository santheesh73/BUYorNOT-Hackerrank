"""Main entry point for BUYorNOT — Phase 1: Data Foundation."""

import logging
import sys
from pathlib import Path

# Add 'code' directory to sys.path so 'data' and 'utils' packages resolve cleanly
code_dir = Path(__file__).resolve().parent
repo_root = code_dir.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from data.indexes import build_indexes
from data.loader import load_datasets
from data.store import DataStore
from data.validators import generate_data_quality_report, validate_datasets
from utils.paths import get_repo_root

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("buy_or_not")


def main() -> int:
    """Execute Phase 1 Data Foundation pipeline."""
    root = get_repo_root()
    logger.info("Project root resolved: %s", root)

    logger.info("Loading datasets...")
    datasets = load_datasets(repo_root=root)

    logger.info("Building indexes...")
    indexes = build_indexes(datasets)

    store = DataStore(datasets=datasets, indexes=indexes)

    logger.info("Validating schemas and referential integrity...")
    validation_report = validate_datasets(store=store, repo_root=root)

    logger.info("Running diagnostics...")
    report_text = generate_data_quality_report(validation_report)
    print("\n" + report_text + "\n")

    if not validation_report.is_valid:
        logger.error("Dataset validation failed with %d critical errors.", len(validation_report.errors))
        return 1

    logger.info("Phase 1 initialization complete. Data foundation verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

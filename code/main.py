"""Main entry point for BUYorNOT — Phase 3: Message & Image Evidence Resolution."""

import logging
import sys
from pathlib import Path

# Add 'code' directory to sys.path so 'data', 'utils', 'finance', and 'evidence' resolve cleanly
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
from evidence.report import build_phase3_report, format_phase3_report
from evidence.resolver import EvidenceResolver
from evidence.store import EvidenceStore
from finance.report import build_phase4_report, format_phase4_report
from utils.paths import get_repo_root

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("buy_or_not")


def main() -> int:
    """Execute Phase 3 Message & Image Evidence Resolution pipeline."""
    root = get_repo_root()
    logger.info("Project root resolved: %s", root)

    # 1. Load data
    logger.info("Loading datasets...")
    datasets = load_datasets(repo_root=root)

    # 2. Build Phase 1 indexes
    logger.info("Building Phase 1 indexes...")
    indexes = build_indexes(datasets)
    store = DataStore(datasets=datasets, indexes=indexes)

    # 3. Validate data
    logger.info("Validating schemas and referential integrity...")
    validation_report = validate_datasets(store=store, repo_root=root)

    # 4. Build Phase 2 financial ledger & resolve lifecycles
    logger.info("Initializing Financial Ledger & resolving lifecycles...")
    ledger = store.get_ledger()

    # 5. Resolve Phase 3 evidence
    logger.info("Resolving Phase 3 unstructured message & image evidence...")
    resolver = EvidenceResolver(repo_root=root)
    msg_facts = resolver.resolve_all_messages(datasets.messages)
    img_facts = resolver.resolve_all_images(datasets.images)

    # 6. Build evidence indexes
    logger.info("Building in-memory evidence store indexes...")
    evidence_store = EvidenceStore(msg_facts + img_facts)
    store._evidence_store = evidence_store

    # 7. Generate Phase 3 diagnostics
    logger.info("Generating Phase 3 diagnostic report...")
    report = build_phase3_report(
        store=evidence_store,
        data_store=store,
        error_count=len(validation_report.errors),
        warning_count=len(validation_report.warnings),
    )
    report_text = format_phase3_report(report=report, data_store=store)
    print("\n" + report_text + "\n")

    # 8. Generate Phase 4 financial state & 90-day forecast diagnostics
    logger.info("Generating Phase 4 Financial State & 90-Day Forecast...")
    phase4_report = build_phase4_report(
        data_store=store,
        error_count=len(validation_report.errors),
        warning_count=len(validation_report.warnings),
    )
    phase4_text = format_phase4_report(phase4_report)
    print("\n" + phase4_text + "\n")

    if not validation_report.is_valid or report.status != "PASS" or phase4_report.status != "PASS":
        logger.error("Execution encountered errors.")
        return 1

    logger.info("Phase 4 execution complete. Financial forecast verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


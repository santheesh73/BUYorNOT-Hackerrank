"""Evidence package for BUYorNOT Phase 3: Message & Image Evidence Resolution."""

from evidence.compat import EvidenceExtractor, MessageFacts
from evidence.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_MIN,
    CONFIDENCE_UNTRUSTED,
    validate_confidence,
)
from evidence.images import ImageEvidenceExtractor
from evidence.messages import MessageEvidenceExtractor
from evidence.models import FinancialEvidence
from evidence.report import Phase3Report, build_phase3_report, format_phase3_report
from evidence.resolver import EvidenceResolver
from evidence.store import EvidenceStore

__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_MIN",
    "CONFIDENCE_UNTRUSTED",
    "EvidenceExtractor",
    "EvidenceResolver",
    "EvidenceStore",
    "FinancialEvidence",
    "ImageEvidenceExtractor",
    "MessageEvidenceExtractor",
    "MessageFacts",
    "Phase3Report",
    "build_phase3_report",
    "format_phase3_report",
    "validate_confidence",
]


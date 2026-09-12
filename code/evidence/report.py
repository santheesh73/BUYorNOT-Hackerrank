"""Phase 3 diagnostics and report generation."""

from dataclasses import dataclass
from typing import Any

from evidence.store import EvidenceStore


@dataclass(frozen=True)
class Phase3Report:
    """Exact Phase 3 report dataclass required by project specification."""

    message_count: int
    messages_with_evidence: int
    message_evidence_count: int

    image_count: int
    images_with_evidence: int
    image_evidence_count: int

    user_linked_count: int
    request_linked_count: int
    event_linked_count: int
    unlinked_count: int

    income_fact_count: int
    expense_fact_count: int
    amount_fact_count: int
    date_fact_count: int
    other_fact_count: int

    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int

    conflict_count: int

    error_count: int
    warning_count: int

    status: str

    # Detailed metrics for Section 28 compatibility
    ocr_attempts: int = 0
    amounts_recovered: int = 0
    messages_affecting_financial_state: int = 0
    events_unresolved: int = 0


def build_phase3_report(
    store: EvidenceStore,
    data_store: Any,
    error_count: int = 0,
    warning_count: int = 0,
) -> Phase3Report:
    """Construct Phase3Report from EvidenceStore and DataStore."""
    all_evidence = store.get_all_evidence()

    msg_evidence = [e for e in all_evidence if e.source_type == "message"]
    img_evidence = [e for e in all_evidence if e.source_type == "image"]

    unique_messages_with_ev = {e.source_id for e in msg_evidence}
    unique_images_with_ev = {e.source_id for e in img_evidence}

    user_linked = sum(1 for e in all_evidence if e.user_id)
    req_linked = sum(1 for e in all_evidence if e.request_id)
    ev_linked = sum(1 for e in all_evidence if e.event_id)
    unlinked = sum(1 for e in all_evidence if not (e.user_id or e.request_id or e.event_id))

    income_facts = sum(1 for e in all_evidence if e.fact_category == "income")
    expense_facts = sum(1 for e in all_evidence if e.fact_category == "expense")
    amount_facts = sum(1 for e in all_evidence if e.fact_category == "amount")
    date_facts = sum(1 for e in all_evidence if e.fact_category == "date")
    other_facts = sum(1 for e in all_evidence if e.fact_category == "other")

    high_conf = sum(1 for e in all_evidence if e.is_high_confidence)
    med_conf = sum(1 for e in all_evidence if e.is_medium_confidence)
    low_conf = sum(1 for e in all_evidence if e.is_low_confidence)

    conflict_groups = store.get_conflict_groups()

    msg_count = len(data_store.datasets.messages)
    img_count = len(data_store.datasets.images)

    # Detailed metrics
    ocr_attempts = img_count
    amounts_recovered = sum(1 for e in img_evidence if e.numeric_value is not None)
    # Messages affecting financial state = income, expense, or date facts
    msgs_affecting = len({e.source_id for e in msg_evidence if e.fact_category in ("income", "expense", "date")})
    # Events with missing amount that remain unresolved by image OCR
    blank_events = [ev for ev in data_store.datasets.financial_events if ev.amount is None]
    resolved_event_ids = {e.event_id for e in img_evidence if e.numeric_value is not None}
    events_unresolved = sum(1 for ev in blank_events if ev.event_id not in resolved_event_ids)

    status = "PASS" if error_count == 0 else "FAIL"

    return Phase3Report(
        message_count=msg_count,
        messages_with_evidence=len(unique_messages_with_ev),
        message_evidence_count=len(msg_evidence),
        image_count=img_count,
        images_with_evidence=len(unique_images_with_ev),
        image_evidence_count=len(img_evidence),
        user_linked_count=user_linked,
        request_linked_count=req_linked,
        event_linked_count=ev_linked,
        unlinked_count=unlinked,
        income_fact_count=income_facts,
        expense_fact_count=expense_facts,
        amount_fact_count=amount_facts,
        date_fact_count=date_facts,
        other_fact_count=other_facts,
        high_confidence_count=high_conf,
        medium_confidence_count=med_conf,
        low_confidence_count=low_conf,
        conflict_count=len(conflict_groups),
        error_count=error_count,
        warning_count=warning_count,
        status=status,
        ocr_attempts=ocr_attempts,
        amounts_recovered=amounts_recovered,
        messages_affecting_financial_state=msgs_affecting,
        events_unresolved=events_unresolved,
    )


def format_phase3_report(report: Phase3Report, data_store: Any) -> str:
    """Format Phase3Report matching exact specification §25 and §28."""
    req_count = len(data_store.datasets.requests)
    prof_count = len(data_store.datasets.financial_profiles)
    ev_count = len(data_store.datasets.financial_events)

    ledger = data_store.get_ledger()
    norm_count = len(ledger.get_all_events())
    cash_flow_count = len(ledger.get_all_cash_flows())

    lines = [
        "BUYorNOT Phase 3",
        "================",
        "",
        "DATA",
        f"Requests: {req_count}",
        f"Financial profiles: {prof_count}",
        f"Financial events: {ev_count}",
        f"Messages: {report.message_count}",
        f"Images: {report.image_count}",
        "",
        "FINANCIAL LEDGER",
        f"Normalized events: {norm_count}",
        f"Cash-flow events: {cash_flow_count}",
        "",
        "EVIDENCE",
        f"Messages processed: {report.message_count}",
        f"Messages with financial evidence: {report.messages_with_evidence}",
        f"Financial evidence records: {report.message_evidence_count}",
        "",
        f"Images processed: {report.image_count}",
        f"Images with financial evidence: {report.images_with_evidence}",
        f"Image evidence records: {report.image_evidence_count}",
        "",
        "LINKING",
        f"Evidence linked to users: {report.user_linked_count}",
        f"Evidence linked to requests: {report.request_linked_count}",
        f"Evidence linked to events: {report.event_linked_count}",
        f"Unlinked evidence: {report.unlinked_count}",
        "",
        "EVIDENCE TYPES",
        f"Income facts: {report.income_fact_count}",
        f"Expense facts: {report.expense_fact_count}",
        f"Amount facts: {report.amount_fact_count}",
        f"Date facts: {report.date_fact_count}",
        f"Other financial facts: {report.other_fact_count}",
        "",
        "CONFIDENCE",
        f"High-confidence evidence: {report.high_confidence_count}",
        f"Medium-confidence evidence: {report.medium_confidence_count}",
        f"Low-confidence evidence: {report.low_confidence_count}",
        "",
        "CONFLICTS",
        f"Conflicting evidence groups: {report.conflict_count}",
        "",
        "DETAILS",
        f"Image references processed: {report.image_count}",
        f"Images successfully resolved: {report.images_with_evidence}",
        f"Image OCR attempts: {report.ocr_attempts}",
        f"Amounts recovered from images: {report.amounts_recovered}",
        f"Messages affecting financial state: {report.messages_affecting_financial_state}",
        f"Events with unresolved evidence: {report.events_unresolved}",
        "",
        "VALIDATION",
        f"Errors: {report.error_count}",
        f"Warnings: {report.warning_count}",
        "",
        "RESULT",
        f"Phase 3 status: {report.status}",
    ]
    return "\n".join(lines)

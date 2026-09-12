"""In-memory indexed EvidenceStore for fast, deterministic querying of structured evidence."""

from collections import defaultdict
from datetime import date
from typing import Sequence

from evidence.models import FinancialEvidence


def _sort_evidence_key(ev: FinancialEvidence) -> tuple:
    """Deterministic sort key for FinancialEvidence."""
    dt = ev.effective_date or date.min
    return (dt, ev.source_type, ev.source_id, ev.evidence_id)


class EvidenceStore:
    """Lightweight in-memory evidence store with multi-index lookups and conflict detection."""

    def __init__(self, evidence_records: Sequence[FinancialEvidence] = ()) -> None:
        self.evidence_by_id: dict[str, FinancialEvidence] = {}
        self.evidence_by_user: dict[str, list[FinancialEvidence]] = defaultdict(list)
        self.evidence_by_event: dict[str, list[FinancialEvidence]] = defaultdict(list)
        self.evidence_by_request: dict[str, list[FinancialEvidence]] = defaultdict(list)

        self._all_records: list[FinancialEvidence] = []
        self._conflict_groups: list[list[FinancialEvidence]] = []

        for record in sorted(evidence_records, key=_sort_evidence_key):
            self.add_evidence(record)

        self._detect_conflicts()

    def add_evidence(self, record: FinancialEvidence) -> None:
        """Add a single FinancialEvidence record to the store and update indexes."""
        self.evidence_by_id[record.evidence_id] = record
        self._all_records.append(record)

        if record.user_id:
            self.evidence_by_user[record.user_id].append(record)
        if record.event_id:
            self.evidence_by_event[record.event_id].append(record)
        if record.request_id:
            self.evidence_by_request[record.request_id].append(record)

    def get_evidence(self, evidence_id: str) -> FinancialEvidence | None:
        """Retrieve an evidence record by ID."""
        return self.evidence_by_id.get(evidence_id)

    def get_all_evidence(self) -> list[FinancialEvidence]:
        """Retrieve all evidence records in deterministic order."""
        return sorted(self._all_records, key=_sort_evidence_key)

    def get_user_evidence(self, user_id: str) -> list[FinancialEvidence]:
        """Retrieve all evidence records associated with a user in deterministic order."""
        return sorted(self.evidence_by_user.get(user_id, []), key=_sort_evidence_key)

    def get_event_evidence(self, event_id: str) -> list[FinancialEvidence]:
        """Retrieve all evidence records tied to a financial event in deterministic order."""
        return sorted(self.evidence_by_event.get(event_id, []), key=_sort_evidence_key)

    def get_request_evidence(self, request_id: str) -> list[FinancialEvidence]:
        """Retrieve all evidence records associated with an evaluation request in deterministic order."""
        return sorted(self.evidence_by_request.get(request_id, []), key=_sort_evidence_key)

    def get_conflict_groups(self) -> list[list[FinancialEvidence]]:
        """Retrieve detected groups of conflicting evidence records."""
        return list(self._conflict_groups)

    def _detect_conflicts(self) -> None:
        """Detect conflicting evidence for the same user or event.

        Examples of conflicts:
        - One record indicates employment/salary termination while another indicates ongoing salary update
        - Multiple records report contradictory numeric amounts for the same event
        """
        self._conflict_groups.clear()

        # Check by user
        for user_id, records in self.evidence_by_user.items():
            salary_updates = [r for r in records if "salary_update" in r.fact_type and r.numeric_value is not None]
            terminations = [r for r in records if "ended" in r.fact_type]

            # Contradictory income amounts from different sources
            amounts = {r.numeric_value for r in salary_updates if r.numeric_value is not None}
            if len(amounts) > 1:
                self._conflict_groups.append(salary_updates)
            elif salary_updates and terminations:
                # Disagreement between ongoing salary and termination
                self._conflict_groups.append(salary_updates + terminations)

        # Check by event
        for event_id, records in self.evidence_by_event.items():
            amount_records = [r for r in records if r.numeric_value is not None]
            distinct_amounts = {r.numeric_value for r in amount_records}
            if len(distinct_amounts) > 1:
                self._conflict_groups.append(amount_records)

"""Event lifecycle resolution layer for BUYorNOT."""

from dataclasses import dataclass
from collections import defaultdict

from data.models import FinancialEvent


@dataclass(frozen=True)
class ResolvedLifecycle:
    """Represents the resolved financial lifecycle of one or more linked events."""
    lifecycle_id: str
    source_event_ids: tuple[str, ...]
    effective_event_ids: tuple[str, ...]
    status: str


class EventLifecycleResolver:
    """Resolves event linkage, lifecycle groups, and active cash-flow participation."""

    def resolve(
        self,
        events: list[FinancialEvent],
    ) -> list[ResolvedLifecycle]:
        """Resolve a collection of events into distinct lifecycle groups.
        
        Prevents double-counting, handles cancellations, failed transactions,
        unrealized valuations, duplicate card charges, and refund linkages.
        """
        event_map = {e.event_id: e for e in events}

        # Build bidirectional graph for linked events
        adjacency = defaultdict(set)
        for e in events:
            if e.linked_event_id and e.linked_event_id in event_map:
                adjacency[e.event_id].add(e.linked_event_id)
                adjacency[e.linked_event_id].add(e.event_id)

        visited = set()
        resolved_lifecycles: list[ResolvedLifecycle] = []

        # Process all events deterministically
        for e in sorted(events, key=lambda x: x.event_id):
            if e.event_id in visited:
                continue

            # Find all connected events
            component = []
            queue = [e.event_id]
            visited.add(e.event_id)

            while queue:
                curr_id = queue.pop(0)
                component.append(curr_id)
                for neighbor in sorted(adjacency[curr_id]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            # Resolve the component
            if len(component) == 1:
                # Single event lifecycle
                ev = event_map[component[0]]
                is_active = (
                    ev.status.lower() not in ("cancelled", "failed", "unrealized")
                    and ev.direction.lower() != "non_cash"
                    and not (ev.status.lower() == "pending" and ev.direction.lower() == "credit")
                )
                effective = (ev.event_id,) if is_active else ()
                resolved = ResolvedLifecycle(
                    lifecycle_id=f"lc_{ev.event_id}",
                    source_event_ids=(ev.event_id,),
                    effective_event_ids=effective,
                    status=ev.status,
                )
                resolved_lifecycles.append(resolved)
            else:
                # Multi-event lifecycle (sort events by event_date, settlement_date, event_id)
                comp_events = [event_map[eid] for eid in component]
                comp_events.sort(key=lambda x: (x.event_date, x.settlement_date or x.event_date, x.event_id))
                source_ids = tuple(x.event_id for x in comp_events)
                primary_id = comp_events[0].event_id

                lifecycle_id = f"lc_{'_'.join(source_ids)}"

                # Determine effective events and status based on challenge semantics
                effective_ids, lifecycle_status = self._resolve_multi_event_component(comp_events)

                resolved = ResolvedLifecycle(
                    lifecycle_id=lifecycle_id,
                    source_event_ids=source_ids,
                    effective_event_ids=tuple(effective_ids),
                    status=lifecycle_status,
                )
                resolved_lifecycles.append(resolved)

        return resolved_lifecycles

    def _resolve_multi_event_component(
        self,
        events: list[FinancialEvent],
    ) -> tuple[list[str], str]:
        """Determine effective events and lifecycle status for a linked group."""
        # Check for duplicate card charge suppression
        duplicate_child = next(
            (e for e in events if "duplicate" in e.description.lower() and e.status.lower() == "pending"),
            None,
        )
        if duplicate_child:
            # Effective is the non-duplicate event(s)
            effective = [e.event_id for e in events if e.event_id != duplicate_child.event_id]
            return effective, "duplicate_suppressed"

        # Check for cancelled parent replaced by settled child
        has_cancelled = any(e.status.lower() == "cancelled" for e in events)
        if has_cancelled:
            effective = [e.event_id for e in events if e.status.lower() not in ("cancelled", "failed")]
            return effective, "cancelled_and_replaced"

        # Check for failed parent rescheduled
        has_failed = any(e.status.lower() == "failed" for e in events)
        if has_failed:
            effective = [e.event_id for e in events if e.status.lower() not in ("cancelled", "failed")]
            return effective, "failed_and_rescheduled"

        # Check for investment purchase with unrealized valuation
        has_unrealized = any(e.status.lower() == "unrealized" or e.direction.lower() == "non_cash" for e in events)
        if has_unrealized:
            effective = [
                e.event_id for e in events
                if e.status.lower() != "unrealized" and e.direction.lower() != "non_cash"
            ]
            return effective, "valuation_unrealized"

        # Check for refund lifecycle
        refund_event = next((e for e in events if e.event_type.lower() == "refund"), None)
        if refund_event:
            if refund_event.status.lower() == "pending":
                # Pending refund not counted as cash flow yet
                effective = [e.event_id for e in events if e.event_id != refund_event.event_id]
                return effective, "pending_refund"
            else:
                # Settled refund: both original expense and settled refund are effective
                effective = [e.event_id for e in events]
                return effective, "settled_with_refund"

        # Check for realized investment (purchase + sale)
        has_sale = any(e.event_type.lower() == "investment_sale" for e in events)
        if has_sale:
            effective = [e.event_id for e in events if e.status.lower() == "settled"]
            return effective, "realized_investment"

        # Generic fallback
        effective = [
            e.event_id for e in events
            if e.status.lower() not in ("cancelled", "failed", "unrealized")
            and e.direction.lower() != "non_cash"
            and not (e.status.lower() == "pending" and e.direction.lower() == "credit")
        ]
        return effective, "resolved"

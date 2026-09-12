"""BUYorNOT Financial normalization, lifecycle resolution, and ledger package."""

from finance.currency import (
    CurrencyConverter,
    ExchangeRateNotFoundError,
    get_exchange_rate,
)
from finance.ledger import (
    FinancialLedger,
    Phase2Report,
    build_phase2_report,
    format_phase2_report,
)
from finance.lifecycle import (
    EventLifecycleResolver,
    ResolvedLifecycle,
)
from finance.normalizer import (
    FinancialEventNormalizer,
    NormalizedFinancialEvent,
)

from finance.compat import (
    CashEvent,
    ChangeAction,
    FinancialEngine,
    FX,
)

from finance.forecast import CashFlowForecaster
from finance.recurrence import RecurringPatternDetector
from finance.report import (
    Phase4Report,
    build_phase4_report,
    format_phase4_report,
)
from finance.state import (
    FinancialState,
    RecurringPattern,
)
from finance.decision import (
    DecisionEngine,
    PlanCandidate,
    calculate_amount_safe_to_pay,
    calculate_earliest_date_for_full_payment,
    simulate_plan_safety,
)
from finance.explanation import generate_decision_explanation
from finance.output import generate_output_csv, validate_output_csv

__all__ = [
    "FinancialEventNormalizer",
    "NormalizedFinancialEvent",
    "EventLifecycleResolver",
    "ResolvedLifecycle",
    "CurrencyConverter",
    "ExchangeRateNotFoundError",
    "get_exchange_rate",
    "FinancialLedger",
    "Phase2Report",
    "build_phase2_report",
    "format_phase2_report",
    "CashEvent",
    "ChangeAction",
    "FX",
    "FinancialEngine",
    "FinancialState",
    "RecurringPattern",
    "RecurringPatternDetector",
    "CashFlowForecaster",
    "Phase4Report",
    "build_phase4_report",
    "format_phase4_report",
    "DecisionEngine",
    "PlanCandidate",
    "calculate_amount_safe_to_pay",
    "calculate_earliest_date_for_full_payment",
    "simulate_plan_safety",
    "generate_decision_explanation",
    "generate_output_csv",
    "validate_output_csv",
]



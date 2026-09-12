"""Compatibility adapters for Part B: CashEvent, ChangeAction, FX, and FinancialEngine."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from evidence.compat import EvidenceExtractor, MessageFacts
from finance.currency import CurrencyConverter
from utils.dates import parse_date
from utils.money import parse_money


@dataclass
class CashEvent:
    """Cash flow event representing an actual or planned cash debit or credit."""

    dt: pd.Timestamp
    amount: Decimal
    category: str
    event_id: str = ""
    source: str = "actual"
    flexibility: str = "fixed"
    minimum_allowed_amount: Optional[Decimal] = None
    description: str = ""


@dataclass
class ChangeAction:
    """Proposed spending reduction or stop action."""

    kind: str  # "stop" | "reduce_to"
    event_id: str
    category: str
    old_amount: Decimal
    new_amount: Decimal
    saving_per_occurrence: Decimal


class FX:
    """Foreign exchange converter adhering to Part B specification."""

    def __init__(self, rates: pd.DataFrame | Any | None = None) -> None:
        if rates is None:
            from utils.paths import get_dataset_dir
            self.rates = pd.read_csv(get_dataset_dir() / "exchange_rates.csv")
        elif isinstance(rates, pd.DataFrame):
            self.rates = rates.copy()
        elif hasattr(rates, "datasets") and hasattr(rates.datasets, "exchange_rates"):
            from utils.paths import get_dataset_dir
            self.rates = pd.read_csv(get_dataset_dir() / "exchange_rates.csv")
        else:
            self.rates = pd.DataFrame()

        self._rates_map: dict[tuple[date, str, str], Decimal] = {}
        for _, row in self.rates.iterrows():
            d = parse_date(row.get("rate_date"))
            fc = str(row.get("from_currency", "")).strip().upper()
            tc = str(row.get("to_currency", "")).strip().upper()
            r = parse_money(row.get("rate"))
            if d and fc and tc and r:
                self._rates_map[(d, fc, tc)] = r

    def _find_rate(self, rate_date: date, fc: str, tc: str) -> Decimal | None:
        # 1. Exact match
        if (rate_date, fc, tc) in self._rates_map:
            return self._rates_map[(rate_date, fc, tc)]
        if (rate_date, tc, fc) in self._rates_map:
            inv = self._rates_map[(rate_date, tc, fc)]
            if inv and inv != 0:
                return Decimal("1.0") / inv

        # 2. 15th of the same month
        m15 = date(rate_date.year, rate_date.month, 15)
        if (m15, fc, tc) in self._rates_map:
            return self._rates_map[(m15, fc, tc)]
        if (m15, tc, fc) in self._rates_map:
            inv = self._rates_map[(m15, tc, fc)]
            if inv and inv != 0:
                return Decimal("1.0") / inv

        # 3. Nearest available date for (fc, tc) or (tc, fc)
        candidate_dates = [d for (d, f, t) in self._rates_map if (f == fc and t == tc) or (f == tc and t == fc)]
        if candidate_dates:
            nearest_d = min(candidate_dates, key=lambda d: abs((d - rate_date).days))
            if (nearest_d, fc, tc) in self._rates_map:
                return self._rates_map[(nearest_d, fc, tc)]
            if (nearest_d, tc, fc) in self._rates_map:
                inv = self._rates_map[(nearest_d, tc, fc)]
                if inv and inv != 0:
                    return Decimal("1.0") / inv

        return None

    def convert(
        self,
        amount: Decimal,
        from_cur: str,
        to_cur: str,
        dt: pd.Timestamp,
    ) -> Decimal:
        """Convert amount from from_cur to to_cur on date dt."""
        fc = from_cur.strip().upper()
        tc = to_cur.strip().upper()
        if fc == tc:
            return amount

        rate_date = dt.date() if hasattr(dt, "date") else dt
        rate = self._find_rate(rate_date, fc, tc)
        if rate is None:
            raise ValueError(f"Exchange rate not found for {fc}->{tc} on {rate_date}")

        return (amount * rate).quantize(Decimal("0.01"))



class FinancialEngine:
    """High-level financial orchestration engine adhering to Part B contract."""

    def __init__(self, data: Path) -> None:
        data_path = Path(data)
        dataset_dir = data_path / "dataset" if (data_path / "dataset").is_dir() else data_path

        self.profiles = pd.read_csv(dataset_dir / "financial_profiles.csv")
        self.events = pd.read_csv(dataset_dir / "financial_events.csv")
        self.requests = pd.read_csv(dataset_dir / "requests.csv")
        self.options = pd.read_csv(dataset_dir / "request_payment_options.csv")
        self.messages = pd.read_csv(dataset_dir / "messages.csv")
        self.images = pd.read_csv(dataset_dir / "images.csv")
        rates_df = pd.read_csv(dataset_dir / "exchange_rates.csv")

        self.fx = FX(rates_df)
        media_dir = dataset_dir / "media" / "images"
        self.extractor = EvidenceExtractor(media_dir)
        self.msgfacts = MessageFacts(self.messages)

        self.data_path = data_path
        self._forecaster = None

        # Resolve blank amounts from images
        self.events = self.extractor.resolve_blank_amounts(self.events, self.images)

    def get_forecaster(self) -> Any:
        """Retrieve CashFlowForecaster, initializing on demand."""
        if self._forecaster is None:
            from data.store import DataStore
            from finance.forecast import CashFlowForecaster
            store = DataStore.load_from_repo(self.data_path)
            self._forecaster = CashFlowForecaster(data_store=store, fx=self.fx)
        return self._forecaster

    def forecast(
        self,
        user_id: str,
        as_of: pd.Timestamp,
        horizon_days: int = 90,
    ) -> list[Any]:
        """Simulate daily balance progression for user_id over horizon_days."""
        return self.get_forecaster().forecast(user_id=user_id, as_of=as_of, horizon_days=horizon_days)

    def future_cash_events(
        self,
        user_id: str,
        as_of: pd.Timestamp,
        horizon_days: int = 90,
    ) -> list[CashEvent]:
        """Generate future cash-flow events for user_id over horizon_days."""
        return self.get_forecaster().future_cash_events(user_id=user_id, as_of=as_of, horizon_days=horizon_days)

    def detect_recurring_patterns(
        self,
        events: Sequence[CashEvent],
        as_of: pd.Timestamp,
    ) -> list[Any]:
        """Detect recurring patterns from events occurring on or before as_of."""
        return self.get_forecaster().detect_recurring_patterns(events=events, as_of=as_of)

    def get_affordability_engine(self) -> Any:
        """Retrieve AffordabilityEngine instance for Phase 6 feasibility primitives."""
        from finance.affordability import AffordabilityEngine
        return AffordabilityEngine()

    def decide(
        self,
        request: Any,
        profile: Any,
        forecast: Any,
        payment_options: Any,
    ) -> Any:
        """Evaluate financial decision conforming to Phase 5 specification."""
        from data.store import DataStore
        from finance.decision import DecisionEngine
        store = DataStore.load_from_repo(self.data_path)
        engine = DecisionEngine(
            data_store=store,
            forecaster=self.get_forecaster(),
            affordability=self.get_affordability_engine(),
        )
        return engine.decide(request, profile, forecast, payment_options)




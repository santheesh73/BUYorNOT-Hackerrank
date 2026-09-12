"""Compatibility adapters for Part B: CashEvent, ChangeAction, FX, and FinancialEngine."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

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

    def __init__(self, rates: pd.DataFrame) -> None:
        self.rates = rates.copy()
        self._rates_map: dict[tuple[date, str, str], Decimal] = {}
        for _, row in self.rates.iterrows():
            d = parse_date(row.get("rate_date"))
            fc = str(row.get("from_currency", "")).strip().upper()
            tc = str(row.get("to_currency", "")).strip().upper()
            r = parse_money(row.get("rate"))
            if d and fc and tc and r:
                self._rates_map[(d, fc, tc)] = r

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
        rate = self._rates_map.get((rate_date, fc, tc))
        if rate is None:
            # Check inverse
            inv = self._rates_map.get((rate_date, tc, fc))
            if inv and inv != 0:
                rate = Decimal("1.0") / inv

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

        # Resolve blank amounts from images
        self.events = self.extractor.resolve_blank_amounts(self.events, self.images)

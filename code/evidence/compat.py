"""Compatibility adapters for Part B: EvidenceExtractor and MessageFacts."""

from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from evidence.images import ImageEvidenceExtractor
from utils.money import parse_money


class EvidenceExtractor:
    """Image evidence and OCR extractor adhering to Part B specification."""

    def __init__(self, images_dir: Path) -> None:
        self.images_dir = Path(images_dir)
        self._extractor = ImageEvidenceExtractor(
            repo_root=self.images_dir.parent.parent if self.images_dir.name == "images" else self.images_dir
        )

    def ocr(self, image_id: str) -> str:
        """Run OCR on image_id.png, returning empty string if OCR unavailable or failed."""
        image_path = self.images_dir / f"{image_id}.png"
        if not image_path.is_file():
            return ""
        text = self._extractor.ocr_image(image_path)
        return text or ""

    def extract_image_amount(
        self, event_row: pd.Series, image_id: str
    ) -> Optional[Decimal]:
        """Extract monetary amount for event_row from matching image OCR text."""
        ocr_text = self.ocr(image_id)
        if not ocr_text:
            return None

        # Search for explicit amounts in OCR text
        import re
        patterns = [
            re.compile(r"(?:TOTAL|GRAND TOTAL|NET PAYABLE|AMOUNT DUE|AMOUNT PAID|FINAL AMOUNT)[\s:]*([A-Z]{3}|\$|₹|Rs\.?)?\s*([0-9,]+(?:\.[0-9]+)?)", re.IGNORECASE),
            re.compile(r"(?:IDR|INR|USD|EUR|ZAR|GBP)\s*([0-9,]+(?:\.[0-9]+)?)\b", re.IGNORECASE),
        ]
        for pat in patterns:
            match = pat.search(ocr_text)
            if match:
                groups = match.groups()
                amt_str = groups[-1].replace(",", "")
                amt = parse_money(amt_str)
                if amt is not None:
                    return amt

        return None

    def resolve_blank_amounts(
        self, events: pd.DataFrame, images: pd.DataFrame
    ) -> pd.DataFrame:
        """Resolve blank amounts in events using matching image references."""
        df_events = events.copy()
        if "related_event_id" not in images.columns or "image_id" not in images.columns:
            return df_events

        event_to_image = dict(zip(images["related_event_id"].dropna(), images["image_id"].dropna()))

        for idx, row in df_events.iterrows():
            amt = row.get("amount")
            if pd.isna(amt) or amt is None:
                ev_id = row.get("event_id")
                img_id = event_to_image.get(ev_id)
                if img_id:
                    extracted = self.extract_image_amount(row, img_id)
                    if extracted is not None:
                        df_events.at[idx, "amount"] = extracted

        return df_events


class MessageFacts:
    """Message facts query manager adhering to Part B specification."""

    def __init__(self, messages: pd.DataFrame) -> None:
        self.messages = messages.copy()
        if "sent_at" in self.messages.columns:
            self.messages["sent_at"] = pd.to_datetime(self.messages["sent_at"])

    def for_user(self, user_id: str, as_of: pd.Timestamp) -> list[str]:
        """Retrieve message texts for user_id sent on or before as_of cutoff."""
        if "user_id" not in self.messages.columns or "sent_at" not in self.messages.columns:
            return []

        user_msgs = self.messages[self.messages["user_id"] == user_id]
        cutoff_dt = pd.to_datetime(as_of)
        if cutoff_dt.tzinfo is not None and user_msgs["sent_at"].dt.tz is None:
            cutoff_dt = cutoff_dt.tz_localize(None)
        elif cutoff_dt.tzinfo is None and user_msgs["sent_at"].dt.tz is not None:
            cutoff_dt = cutoff_dt.tz_localize("UTC")

        valid_msgs = user_msgs[user_msgs["sent_at"] <= cutoff_dt]
        return valid_msgs["message_text"].tolist()

"""Unit tests for code/evidence/images.py."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from data.models import ImageReference
from evidence.images import ImageEvidenceExtractor


def test_valid_image_reference():
    img_ref = ImageReference(
        image_id="image_01",
        user_id="user_03",
        request_id="request_03",
        related_event_id="event_253",
    )
    extractor = ImageEvidenceExtractor()
    facts = extractor.extract(img_ref)

    assert len(facts) >= 1
    f = facts[0]
    assert f.source_type == "image"
    assert f.source_id == "image_01"
    assert f.user_id == "user_03"
    assert f.event_id == "event_253"
    assert f.request_id == "request_03"
    assert f.source_path is not None
    assert Path(f.source_path).name == "image_01.png"


def test_missing_image_file():
    img_ref = ImageReference(
        image_id="nonexistent_image",
        user_id="user_99",
        request_id=None,
        related_event_id=None,
    )
    extractor = ImageEvidenceExtractor()
    facts = extractor.extract(img_ref)

    assert len(facts) == 1
    assert facts[0].fact_type == "image_file_missing"
    assert facts[0].is_low_confidence is True


def test_simulated_ocr_extraction():
    img_ref = ImageReference(
        image_id="image_01",
        user_id="user_03",
        request_id="request_03",
        related_event_id="event_253",
    )
    extractor = ImageEvidenceExtractor()

    # Mock ocr_image to simulate successful OCR
    extractor.ocr_image = MagicMock(return_value="TAX INVOICE\nTOTAL AMOUNT DUE: INR 4,500.00\nTHANK YOU")

    facts = extractor.extract(img_ref)
    assert len(facts) >= 1
    f = facts[0]
    assert f.fact_category == "amount"
    assert f.currency == "INR"
    assert f.numeric_value == Decimal("4500.00")
    assert f.is_high_confidence is True

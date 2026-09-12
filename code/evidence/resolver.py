"""Evidence Resolver: High-level resolution orchestrator with in-memory caching."""

from pathlib import Path

from data.models import ImageReference, Message
from evidence.images import ImageEvidenceExtractor
from evidence.messages import MessageEvidenceExtractor
from evidence.models import FinancialEvidence


class EvidenceResolver:
    """Resolves unstructured messages and images into structured FinancialEvidence records.

    Provides in-memory caching to avoid re-extracting identical inputs.
    Isolates external / optical extraction behind a uniform public interface.
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        message_extractor: MessageEvidenceExtractor | None = None,
        image_extractor: ImageEvidenceExtractor | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.message_extractor = message_extractor or MessageEvidenceExtractor()
        self.image_extractor = image_extractor or ImageEvidenceExtractor(repo_root=repo_root)

        # In-memory execution caches
        self._message_cache: dict[str, list[FinancialEvidence]] = {}
        self._image_cache: dict[str, list[FinancialEvidence]] = {}

    def resolve_message(self, message: Message) -> list[FinancialEvidence]:
        """Resolve a single Message into structured FinancialEvidence, cached by message_id."""
        if message.message_id in self._message_cache:
            return self._message_cache[message.message_id]

        facts = self.message_extractor.extract(message)
        self._message_cache[message.message_id] = facts
        return facts

    def resolve_image(self, image: ImageReference) -> list[FinancialEvidence]:
        """Resolve an ImageReference into structured FinancialEvidence, cached by image_id."""
        if image.image_id in self._image_cache:
            return self._image_cache[image.image_id]

        facts = self.image_extractor.extract(image)
        self._image_cache[image.image_id] = facts
        return facts

    def resolve_all_messages(self, messages: list[Message]) -> list[FinancialEvidence]:
        """Resolve a batch of messages deterministically."""
        all_facts: list[FinancialEvidence] = []
        for msg in messages:
            all_facts.extend(self.resolve_message(msg))
        return all_facts

    def resolve_all_images(self, images: list[ImageReference]) -> list[FinancialEvidence]:
        """Resolve a batch of images deterministically."""
        all_facts: list[FinancialEvidence] = []
        for img in images:
            all_facts.extend(self.resolve_image(img))
        return all_facts

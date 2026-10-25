import re
from typing import Optional, Set
from spec1_engine.analysts.registry import load_all
from spec1_engine.schemas.models import AnalystRecord, Signal

class CredibilityAnalyst:
    """Scores signals by checking if author is a known high-credibility analyst."""

    def __init__(self) -> None:
        self._analysts: list[AnalystRecord] = load_all()
        # Sort by name length descending so long specific names protect shorter substring versions
        self._analysts.sort(key=lambda x: len(x.name), reverse=True)
        self._name_map: dict[str, AnalystRecord] = {
            a.name.lower(): a for a in self._analysts
        }

    def _normalize(self, author_str: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", author_str.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _normalize_and_tokenize(self, author_str: str) -> Set[str]:
        return set(self._normalize(author_str).split())

    def match_record(self, author_field: Optional[str]) -> Optional[AnalystRecord]:
        if not author_field:
            return None
        author_lower = author_field.lower().strip()
        if author_lower in self._name_map:
            return self._name_map[author_lower]

        cleaned = self._normalize(author_lower)
        author_tokens = set(cleaned.split())

        for name_lower, record in self._name_map.items():
            parts = name_lower.split()
            if len(parts) < 2:
                continue
            first, last_name = parts[0], parts[-1]

            # Bounded initial validation window
            initial_pattern = rf"\b{re.escape(first[0])}\.?\s*(?:\b[a-z]\b\.?\s*)*{re.escape(last_name)}\b"
            if re.search(initial_pattern, cleaned):
                return record
            if first in author_tokens and last_name in author_tokens:
                return record
        return None

    def score(self, signal: Signal) -> float:
        record = self.match_record(signal.author)
        return record.credibility_score if record else 0.50

    # --- Legacy Compatibility Interface Layer ---
    def identify_analyst(self, signal: Signal) -> Optional[AnalystRecord]:
        return self.match_record(signal.author)

    def score_batch(self, signals: list[Signal]) -> list[float]:
        return [self.score(s) for s in signals]

    def get_known_analysts(self) -> list[AnalystRecord]:
        return list(self._analysts)

    def count_known(self) -> int:
        return len(self._analysts)

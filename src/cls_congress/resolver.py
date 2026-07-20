from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cls_congress.models import Entity, Member

_MIN_CONFIDENCE = 0.6
_SUBSTRING_CONFIDENCE_FACTOR = 0.7


def _normalise(name: str) -> str:
    return " ".join(name.lower().split())


def _token_sort(name: str) -> str:
    return " ".join(sorted(_normalise(name).split()))


@dataclass(frozen=True)
class ResolveResult:
    canonical_id: str
    canonical_name: str
    confidence: float
    kind: str


class EntityResolver:
    def __init__(self, members: Optional[list[Member]] = None, entities: Optional[list[Entity]] = None) -> None:
        self._index: dict[str, ResolveResult] = {}
        self._token_sort_index: dict[str, ResolveResult] = {}
        self._all_results: list[ResolveResult] = []
        self.reload(members or [], entities or [])

    def _register(self, name: str, result: ResolveResult) -> None:
        key = _normalise(name)
        ts_key = _token_sort(name)
        self._index.setdefault(key, result)
        self._token_sort_index.setdefault(ts_key, result)
        if result not in self._all_results:
            self._all_results.append(result)

    def reload(self, members: list[Member], entities: list[Entity]) -> None:
        self._index = {}
        self._token_sort_index = {}
        self._all_results = []

        for member in members:
            result = ResolveResult(member.member_id, member.name, 1.0, "member")
            self._register(member.name, result)

        for entity in entities:
            result = ResolveResult(entity.entity_id, entity.canonical_name, 1.0, "entity")
            self._register(entity.canonical_name, result)
            for alias in entity.aliases:
                self._register(alias, result)

    def resolve(self, raw_name: str) -> Optional[ResolveResult]:
        if not raw_name or not raw_name.strip():
            return None

        key = _normalise(raw_name)
        if key in self._index:
            hit = self._index[key]
            return ResolveResult(hit.canonical_id, hit.canonical_name, 1.0, hit.kind)

        ts_key = _token_sort(raw_name)
        if ts_key in self._token_sort_index:
            hit = self._token_sort_index[ts_key]
            return ResolveResult(hit.canonical_id, hit.canonical_name, 0.9, hit.kind)

        best: Optional[ResolveResult] = None
        best_confidence = _MIN_CONFIDENCE
        for indexed, candidate in self._index.items():
            if key in indexed or indexed in key:
                overlap = min(len(key), len(indexed))
                longer = max(len(key), len(indexed))
                confidence = _SUBSTRING_CONFIDENCE_FACTOR * (overlap / longer) if longer else 0.0
                if confidence > best_confidence:
                    best_confidence = confidence
                    best = ResolveResult(
                        candidate.canonical_id,
                        candidate.canonical_name,
                        round(confidence, 3),
                        candidate.kind,
                    )
        return best

    def resolve_all(self, raw_names: list[str]) -> list[ResolveResult]:
        return [hit for hit in (self.resolve(name) for name in raw_names) if hit is not None]

    def size(self) -> int:
        return len(self._all_results)

# @domain:   citizens_source
# @module:   resolver
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Entity resolver for cls_pdx1.

Maps raw contributor/official name strings to canonical IDs in the PDX-1i graph.
Deterministic matching only — no external NLP dependencies.

Match tiers (descending confidence):
  1.0  exact match (case-normalised)
  0.9  token-sort match (word-order invariant)
  0.7  substring containment (shortest candidate wins)
  None no match above minimum threshold (0.6)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from cls_pdx1.models import Entity, Official

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE = 0.6


def _normalise(name: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation used in names."""
    return " ".join(name.lower().split())


def _token_sort(name: str) -> str:
    """Return lowercase tokens sorted alphabetically — order-invariant key."""
    return " ".join(sorted(_normalise(name).split()))


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolveResult:
    """Single resolution hit."""

    canonical_id: str
    canonical_name: str
    confidence: float       # 0.0–1.0; only emitted when >= _MIN_CONFIDENCE
    kind: str               # "official" | "entity"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class EntityResolver:
    """Resolves raw name strings to canonical Official or Entity IDs.

    Index is built once from lists of Official and Entity records.
    Re-instantiate (or call reload()) when the underlying roster changes.
    """

    def __init__(
        self,
        officials: Optional[list[Official]] = None,
        entities: Optional[list[Entity]] = None,
    ) -> None:
        # (normalised_name) → ResolveResult
        self._index: dict[str, ResolveResult] = {}
        self._token_sort_index: dict[str, ResolveResult] = {}
        self._all_results: list[ResolveResult] = []

        self.reload(officials or [], entities or [])

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def reload(
        self,
        officials: list[Official],
        entities: list[Entity],
    ) -> None:
        """Rebuild the name index from current rosters."""
        self._index = {}
        self._token_sort_index = {}
        self._all_results = []

        for off in officials:
            result = ResolveResult(
                canonical_id=off.official_id,
                canonical_name=off.name,
                confidence=1.0,
                kind="official",
            )
            self._register(off.name, result)

        for ent in entities:
            result = ResolveResult(
                canonical_id=ent.entity_id,
                canonical_name=ent.canonical_name,
                confidence=1.0,
                kind="entity",
            )
            self._register(ent.canonical_name, result)
            for alias in ent.aliases:
                self._register(alias, result)

        logger.debug(
            "EntityResolver: indexed %d officials, %d entities (%d name keys)",
            len(officials),
            len(entities),
            len(self._index),
        )

    def _register(self, name: str, result: ResolveResult) -> None:
        key = _normalise(name)
        ts_key = _token_sort(name)
        if key not in self._index:
            self._index[key] = result
        if ts_key not in self._token_sort_index:
            self._token_sort_index[ts_key] = result
        if result not in self._all_results:
            self._all_results.append(result)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, raw_name: str) -> Optional[ResolveResult]:
        """Resolve a raw name string to the best canonical match.

        Returns None when no candidate clears the minimum confidence threshold.
        """
        if not raw_name or not raw_name.strip():
            return None

        key = _normalise(raw_name)

        # Tier 1 — exact (case-normalised)
        if key in self._index:
            result = self._index[key]
            return ResolveResult(
                canonical_id=result.canonical_id,
                canonical_name=result.canonical_name,
                confidence=1.0,
                kind=result.kind,
            )

        # Tier 2 — token-sort (word-order invariant)
        ts_key = _token_sort(raw_name)
        if ts_key in self._token_sort_index:
            result = self._token_sort_index[ts_key]
            return ResolveResult(
                canonical_id=result.canonical_id,
                canonical_name=result.canonical_name,
                confidence=0.9,
                kind=result.kind,
            )

        # Tier 3 — substring containment
        best: Optional[ResolveResult] = None
        best_confidence = _MIN_CONFIDENCE

        for indexed_key, candidate in self._index.items():
            if key in indexed_key or indexed_key in key:
                # Prefer shorter candidates (more specific match)
                overlap = min(len(key), len(indexed_key))
                longer = max(len(key), len(indexed_key))
                confidence = 0.7 * (overlap / longer) if longer else 0.0
                if confidence > best_confidence:
                    best_confidence = confidence
                    best = ResolveResult(
                        canonical_id=candidate.canonical_id,
                        canonical_name=candidate.canonical_name,
                        confidence=round(confidence, 3),
                        kind=candidate.kind,
                    )

        if best is not None:
            logger.debug(
                "EntityResolver: fuzzy match '%s' → '%s' (%.2f)",
                raw_name,
                best.canonical_name,
                best.confidence,
            )

        return best

    def resolve_all(self, raw_names: list[str]) -> list[ResolveResult]:
        """Resolve a list of names; silently drops non-matches."""
        results = []
        for name in raw_names:
            hit = self.resolve(name)
            if hit:
                results.append(hit)
        return results

    def size(self) -> int:
        """Number of unique canonical records in the index."""
        return len(self._all_results)

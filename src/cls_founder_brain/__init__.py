# @domain:   product
# @module:   cls_founder_brain
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_labels

"""cls_founder_brain — Exited-Founder Cognitive Engine.

Encodes the decision architecture of a two-time exited founder as a
deterministic AI reasoning layer. Four cognitive layers:

  Layer 1: Pattern Recognition — matches current situation against
           canonical failure/success archetypes from startup history.
  Layer 2: Conviction Scorer — quantifies signal strength under
           uncertainty; separates noise from conviction-worthy signals.
  Layer 3: Fire Triage — classifies problems as IGNORE / DELEGATE /
           ATTACK based on existential-vs-cosmetic heuristics.
  Layer 4: Decision Synthesizer — produces an executive action with
           rationale, confidence, and time horizon.

Design constraints:
  - $0 cost: no API keys required; fully rule-based (Tier 3 compatible)
  - 7-day horizon: all outputs scoped to immediate actionable windows
  - No mentor dependency: encodes pattern libraries, not advice
  - Deterministic core logic: same inputs → same classifications/scores (IDs/timestamps are time-based)
  - Append-only JSONL persistence (spec-1 convention)
"""

from cls_founder_brain.schemas import (
    FounderDecision,
    ConvictionSignal,
    FireClassification,
    PatternMatch,
    Situation,
)
from cls_founder_brain.pipeline import run_founder_brain

__all__ = [
    "FounderDecision",
    "ConvictionSignal",
    "FireClassification",
    "PatternMatch",
    "Situation",
    "run_founder_brain",
]

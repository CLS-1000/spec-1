# @domain:   product
# @module:   pipeline
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain.recognizer, conviction, triage, synthesizer, store

"""Founder Brain Pipeline — full cognitive cycle.

Orchestrates all four layers:
  1. Pattern Recognition → which failure/success archetypes are active
  2. Conviction Scoring → how hard to lean into each signal
  3. Fire Triage → which problems to ignore
  4. Decision Synthesis → the ONE thing to do next

Zero cost: no API keys, no external calls, fully deterministic.
Persistence: append-only JSONL (optional).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cls_founder_brain.conviction import score_conviction
from cls_founder_brain.recognizer import recognize_patterns
from cls_founder_brain.schemas import (
    ConvictionSignal,
    FireClassification,
    FounderDecision,
    Situation,
)
from cls_founder_brain.store import FounderBrainStore
from cls_founder_brain.synthesizer import synthesize_decision
from cls_founder_brain.triage import classify_fire


def _make_situation_id(description: str) -> str:
    """Generate a unique (time-based) situation ID from description."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{description[:50]}_{ts}"
    return f"sit_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def run_founder_brain(
    description: str,
    context: str = "",
    constraints: list[str] | None = None,
    active_fires: list[str] | None = None,
    signals: list[str] | None = None,
    stage: str = "pre_revenue",
    runway_days: int = 7,
    store_path: Optional[str | Path] = None,
    persist: bool = True,
) -> FounderDecision:
    """Run the full founder-brain cognitive cycle.

    This is the main entry point. Feed it your current situation and get
    back what a two-time exited founder would do.

    Args:
        description: What's happening right now.
        context: Market, stage, resources available.
        constraints: Hard constraints (e.g. "$0 budget", "7 days").
        active_fires: Current problems demanding attention.
        signals: Opportunities, threats, data points.
        stage: Company stage (pre_revenue|revenue|scaling|exit_prep).
        runway_days: Days of cash/time remaining.
        store_path: Optional path for JSONL persistence.
        persist: Whether to write to store.

    Returns:
        FounderDecision with primary_action and full provenance.
    """
    constraints = constraints or []
    active_fires = active_fires or []
    signals = signals or []

    # Build situation
    situation = Situation(
        situation_id=_make_situation_id(description),
        description=description,
        context=context,
        constraints=constraints,
        active_fires=active_fires,
        signals=signals,
        stage=stage,
        runway_days=runway_days,
    )

    # ── Layer 1: Pattern Recognition ──
    pattern_matches = recognize_patterns(situation, threshold=0.2, max_matches=5)

    # ── Layer 2: Conviction Scoring ──
    conviction_signals: list[ConvictionSignal] = []
    for i, signal in enumerate(signals):
        cs = score_conviction(
            signal_id=f"sig_{i}",
            signal_description=signal,
            signal_clarity=0.5,  # Default: moderate clarity
            market_validation=0.3,  # Default: low validation (you're early)
            gut_alignment=0.6,  # Default: moderate gut feel
            downside_asymmetry=0.7 if runway_days <= 7 else 0.4,  # High asymmetry when runway is short
            time_decay=min(1.0, 7.0 / max(runway_days, 1)),  # Higher urgency with less runway
            pattern_matches=pattern_matches,
        )
        conviction_signals.append(cs)

    # ── Layer 3: Fire Triage ──
    fire_classifications: list[FireClassification] = []
    for i, fire in enumerate(active_fires):
        fc = classify_fire(
            fire_id=f"fire_{i}",
            description=fire,
            additional_context=f"stage={stage} days_remaining={runway_days}",
        )
        fire_classifications.append(fc)

    # ── Layer 4: Synthesis ──
    decision = synthesize_decision(
        situation=situation,
        pattern_matches=pattern_matches,
        conviction_signals=conviction_signals,
        fire_classifications=fire_classifications,
    )

    # ── Persist ──
    if persist:
        store = FounderBrainStore(path=store_path)
        store.append(decision)

    return decision


def format_decision(decision: FounderDecision) -> str:
    """Format a FounderDecision as human-readable markdown.

    This is the briefing format — what the founder reads.
    """
    lines = []
    lines.append("# 🧠 Founder Brain Decision")
    lines.append("")
    lines.append(f"**Decision ID:** `{decision.decision_id}`")
    lines.append(f"**Conviction Level:** {decision.conviction_level}")
    lines.append(f"**Confidence:** {decision.confidence:.0%}")
    lines.append(f"**Time Horizon:** {decision.time_horizon_hours}h")
    lines.append("")

    # Primary action (the ONE thing)
    lines.append("## ⚡ PRIMARY ACTION")
    lines.append("")
    lines.append(f"> {decision.primary_action}")
    lines.append("")
    lines.append(f"**Rationale:** {decision.action_rationale}")
    lines.append("")

    # Ignore list (equally important)
    if decision.ignore_list:
        lines.append("## 🚫 EXPLICITLY IGNORING")
        lines.append("")
        for item in decision.ignore_list:
            lines.append(f"- ~~{item}~~")
        lines.append("")

    # Pattern matches
    if decision.pattern_matches:
        lines.append("## 🔍 PATTERNS DETECTED")
        lines.append("")
        for pm in decision.pattern_matches:
            lines.append(f"- **{pm.get('pattern_name', '')}** ({pm.get('category', '')}) — "
                         f"strength: {pm.get('match_strength', 0):.0%}")
            if pm.get("counter_move"):
                lines.append(f"  - Counter-move: {pm['counter_move']}")
        lines.append("")

    # Fire triage
    if decision.fire_classifications:
        lines.append("## 🔥 FIRE TRIAGE")
        lines.append("")
        for fc in decision.fire_classifications:
            emoji = {"ATTACK": "🚨", "DELEGATE": "👋", "IGNORE": "🚫"}.get(
                fc.get("classification", ""), "❓"
            )
            lines.append(f"- {emoji} **{fc.get('classification', '')}**: {fc.get('description', '')}")
            lines.append(f"  - {fc.get('reasoning', '')}")
        lines.append("")

    # Conviction signals
    if decision.conviction_signals:
        lines.append("## 📊 CONVICTION SCORES")
        lines.append("")
        for cs in decision.conviction_signals:
            lines.append(f"- **{cs.get('signal_description', '')}**: "
                         f"{cs.get('conviction_score', 0):.0%} ({cs.get('conviction_level', '')})")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated: {decision.generated_at} | Model: {decision.cognitive_model}*")

    return "\n".join(lines)

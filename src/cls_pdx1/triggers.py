# @domain:   citizens_source
# @module:   triggers
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Publication trigger evaluation for Metro Citizens Brief.

The brief is signal-gated, not calendar-gated. This module evaluates
accumulated signals and anomalies and decides whether publication should fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Anomaly, AnomalyTier, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TriggerPolicy:
    """Configurable publication policy."""

    # Minimum accumulated signal weight to consider publication
    signal_weight_threshold: float = 5.0
    # Minimum spacing between issues (prevents firehose)
    min_spacing_days: int = 3
    # Floor cadence: publish anyway if this many days have passed without issue
    max_silence_days: int = 14
    # A TIER_1 anomaly alone can trigger publication
    tier1_auto_trigger: bool = True


@dataclass
class TriggerState:
    """Mutable state for the trigger evaluator."""

    last_published_at: Optional[datetime] = None
    pending_signals: list[Signal] = field(default_factory=list)
    pending_anomalies: list[Anomaly] = field(default_factory=list)

    def add_signal(self, signal: Signal) -> None:
        self.pending_signals.append(signal)

    def add_anomaly(self, anomaly: Anomaly) -> None:
        self.pending_anomalies.append(anomaly)

    def accumulated_weight(self) -> float:
        return sum(s.weight for s in self.pending_signals)

    def has_tier1_anomaly(self) -> bool:
        return any(a.tier == AnomalyTier.TIER_1 for a in self.pending_anomalies)

    def days_since_last_issue(self) -> Optional[float]:
        if self.last_published_at is None:
            return None
        last = self.last_published_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (_now() - last).total_seconds() / 86400


@dataclass
class TriggerDecision:
    should_publish: bool
    reason: str
    accumulated_weight: float
    pending_signal_count: int
    pending_anomaly_count: int


def evaluate_trigger(state: TriggerState, policy: Optional[TriggerPolicy] = None) -> TriggerDecision:
    """Evaluate whether conditions warrant publishing a new issue."""
    if policy is None:
        policy = TriggerPolicy()

    weight = state.accumulated_weight()
    days_since = state.days_since_last_issue()

    # Minimum spacing guard — never publish below this floor
    if days_since is not None and days_since < policy.min_spacing_days:
        return TriggerDecision(
            should_publish=False,
            reason=f"minimum spacing not met ({days_since:.1f}d < {policy.min_spacing_days}d)",
            accumulated_weight=weight,
            pending_signal_count=len(state.pending_signals),
            pending_anomaly_count=len(state.pending_anomalies),
        )

    # TIER_1 anomaly auto-triggers regardless of weight threshold
    if policy.tier1_auto_trigger and state.has_tier1_anomaly():
        return TriggerDecision(
            should_publish=True,
            reason="TIER_1 anomaly detected — auto-trigger",
            accumulated_weight=weight,
            pending_signal_count=len(state.pending_signals),
            pending_anomaly_count=len(state.pending_anomalies),
        )

    # Floor cadence: publish if too many days have passed
    if days_since is not None and days_since >= policy.max_silence_days:
        return TriggerDecision(
            should_publish=True,
            reason=f"floor cadence reached ({days_since:.1f}d >= {policy.max_silence_days}d)",
            accumulated_weight=weight,
            pending_signal_count=len(state.pending_signals),
            pending_anomaly_count=len(state.pending_anomalies),
        )

    # First-ever issue: publish when weight threshold met
    if days_since is None and weight >= policy.signal_weight_threshold:
        return TriggerDecision(
            should_publish=True,
            reason=f"weight threshold met ({weight:.1f} >= {policy.signal_weight_threshold})",
            accumulated_weight=weight,
            pending_signal_count=len(state.pending_signals),
            pending_anomaly_count=len(state.pending_anomalies),
        )

    if weight >= policy.signal_weight_threshold:
        return TriggerDecision(
            should_publish=True,
            reason=f"weight threshold met ({weight:.1f} >= {policy.signal_weight_threshold})",
            accumulated_weight=weight,
            pending_signal_count=len(state.pending_signals),
            pending_anomaly_count=len(state.pending_anomalies),
        )

    return TriggerDecision(
        should_publish=False,
        reason=f"insufficient weight ({weight:.1f} < {policy.signal_weight_threshold})",
        accumulated_weight=weight,
        pending_signal_count=len(state.pending_signals),
        pending_anomaly_count=len(state.pending_anomalies),
    )

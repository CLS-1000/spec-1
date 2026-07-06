from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cls_congress.models import Anomaly, AnomalyTier, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TriggerPolicy:
    signal_weight_threshold: float = 5.0
    min_spacing_days: int = 3
    max_silence_days: int = 14
    tier1_auto_trigger: bool = True


@dataclass
class TriggerState:
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
        ts = self.last_published_at if self.last_published_at.tzinfo else self.last_published_at.replace(tzinfo=timezone.utc)
        return (_now() - ts).total_seconds() / 86400


@dataclass
class TriggerDecision:
    should_publish: bool
    reason: str
    accumulated_weight: float
    pending_signal_count: int
    pending_anomaly_count: int


def evaluate_trigger(state: TriggerState, policy: Optional[TriggerPolicy] = None) -> TriggerDecision:
    policy = policy or TriggerPolicy()
    weight = state.accumulated_weight()
    days_since = state.days_since_last_issue()

    if days_since is not None and days_since < policy.min_spacing_days:
        return TriggerDecision(
            False,
            f"minimum spacing not met ({days_since:.1f}d < {policy.min_spacing_days}d)",
            weight,
            len(state.pending_signals),
            len(state.pending_anomalies),
        )

    if policy.tier1_auto_trigger and state.has_tier1_anomaly():
        return TriggerDecision(
            True,
            "TIER_1 anomaly detected — auto-trigger",
            weight,
            len(state.pending_signals),
            len(state.pending_anomalies),
        )

    if days_since is not None and days_since >= policy.max_silence_days:
        return TriggerDecision(
            True,
            f"floor cadence reached ({days_since:.1f}d >= {policy.max_silence_days}d)",
            weight,
            len(state.pending_signals),
            len(state.pending_anomalies),
        )

    if weight >= policy.signal_weight_threshold:
        return TriggerDecision(
            True,
            f"weight threshold met ({weight:.1f} >= {policy.signal_weight_threshold})",
            weight,
            len(state.pending_signals),
            len(state.pending_anomalies),
        )

    return TriggerDecision(
        False,
        f"insufficient weight ({weight:.1f} < {policy.signal_weight_threshold})",
        weight,
        len(state.pending_signals),
        len(state.pending_anomalies),
    )

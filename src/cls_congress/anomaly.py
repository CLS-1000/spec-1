from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from cls_congress.models import Anomaly, AnomalyTier, Provenance, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tier_from_sigma(sigma: float) -> AnomalyTier:
    if sigma >= 3.0:
        return AnomalyTier.TIER_1
    if sigma >= 2.0:
        return AnomalyTier.TIER_2
    if sigma >= 1.0:
        return AnomalyTier.TIER_3
    return AnomalyTier.TIER_4


class RollingBaseline:
    def __init__(self, window_days: int = 90) -> None:
        self.window_days = window_days
        self._observations: dict[str, list[tuple[datetime, float]]] = defaultdict(list)

    def ingest(self, signal: Signal) -> None:
        if not signal.entity_id:
            return
        occurred = signal.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        self._observations[signal.entity_id].append((occurred, signal.weight))

    def _window(self, entity_id: str) -> list[tuple[datetime, float]]:
        cutoff = _now() - timedelta(days=self.window_days)
        return [(ts, w) for ts, w in self._observations.get(entity_id, []) if ts >= cutoff]

    def stats(self, entity_id: str) -> tuple[float, float]:
        obs = self._window(entity_id)
        if not obs:
            return 0.0, 0.0

        by_day: dict[str, float] = defaultdict(float)
        for ts, weight in obs:
            by_day[ts.date().isoformat()] += weight

        values = list(by_day.values())
        if len(values) < 2:
            return values[0] if values else 0.0, 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return mean, math.sqrt(variance)

    def evaluate(
        self,
        entity_id: str,
        current_value: float,
        kind: str,
        provenance: Provenance,
        description: Optional[str] = None,
    ) -> Optional[Anomaly]:
        mean, std = self.stats(entity_id)

        if std == 0.0:
            if current_value > 0 and mean == 0.0:
                sigma = 3.0
            elif current_value > mean * 3:
                sigma = 3.0
            else:
                return None
        else:
            sigma = (current_value - mean) / std

        if sigma < 1.0:
            return None

        return Anomaly(
            entity_id=entity_id,
            tier=_tier_from_sigma(sigma),
            detected_at=_now(),
            kind=kind,
            description=description
            or f"{kind}: observed {current_value:.2f}, baseline {mean:.2f} ± {std:.2f} ({sigma:.2f}σ)",
            baseline_window_days=self.window_days,
            sigma=round(sigma, 3),
            observed_value=current_value,
            baseline_mean=round(mean, 4),
            baseline_std=round(std, 4),
            provenance=provenance,
        )

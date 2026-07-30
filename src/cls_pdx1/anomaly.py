# @domain:   citizens_source
# @module:   anomaly
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""90-day rolling baseline anomaly detector for PDX-1i watch entities."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from cls_pdx1.models import Anomaly, AnomalyTier, Provenance, Signal


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
    """Rolling N-day signal-weight baseline per entity — feeds the sigma detector."""

    def __init__(self, window_days: int = 90) -> None:
        self.window_days = window_days
        # entity_id → list of (datetime, weight)
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
        return [
            (ts, w)
            for ts, w in self._observations.get(entity_id, [])
            if ts >= cutoff
        ]

    def stats(self, entity_id: str) -> tuple[float, float]:
        """(mean, std) of daily-summed signal weights over the rolling window."""
        obs = self._window(entity_id)
        if not obs:
            return 0.0, 0.0

        by_day: dict[str, float] = defaultdict(float)
        for ts, w in obs:
            day = ts.date().isoformat()
            by_day[day] += w

        values = list(by_day.values())
        if len(values) < 2:
            return values[0] if values else 0.0, 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(variance)
        return mean, std

    def evaluate(
        self,
        entity_id: str,
        current_value: float,
        kind: str,
        provenance: Provenance,
        description: Optional[str] = None,
    ) -> Optional[Anomaly]:
        """Compare current_value against baseline — emit Anomaly if deviation >= 1σ."""
        mean, std = self.stats(entity_id)

        if std == 0.0:
            if current_value > 0 and mean == 0.0:
                sigma = 3.0
            elif current_value > mean * 3:
                # Uniform baseline suddenly spiked — treat as 3-sigma event.
                sigma = 3.0
            else:
                return None
        else:
            sigma = (current_value - mean) / std

        if sigma < 1.0:
            return None

        tier = _tier_from_sigma(sigma)
        desc = description or (
            f"{kind}: observed {current_value:.2f}, "
            f"baseline mean {mean:.2f} ± {std:.2f} ({sigma:.2f}σ)"
        )

        return Anomaly(
            entity_id=entity_id,
            tier=tier,
            detected_at=_now(),
            kind=kind,
            description=desc,
            baseline_window_days=self.window_days,
            sigma=round(sigma, 3),
            observed_value=current_value,
            baseline_mean=round(mean, 4),
            baseline_std=round(std, 4),
            provenance=provenance,
        )

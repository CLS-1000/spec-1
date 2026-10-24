"""Political signal gate scoring functions.

Four independent gates for the Portland Political Web signal loop:
  credibility  — domain trust score
  volume       — tag-weighted signal richness
  velocity     — exponential decay from published_at (half-life ~36 h)
  novelty      — 1 - max cosine similarity vs. recent summaries (pure Python)

Gate threshold (exclusive): every gate score must be STRICTLY GREATER THAN
GATE_THRESHOLD (0.40) for a signal to earn PASS status.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import List

# ── Single source of truth ────────────────────────────────────────────────────
GATE_THRESHOLD: float = 0.40  # exclusive — score must be > this value

# ── Credibility ───────────────────────────────────────────────────────────────

DOMAIN_CREDIBILITY: dict[str, float] = {
    "oregonlive.com":        0.82,
    "wweek.com":             0.80,
    "opb.org":               0.85,
    "portland.gov":          0.90,
    "portlandoregon.gov":    0.90,
    "portlandmercury.com":   0.78,
    "kgw.com":               0.75,
    "apnews.com":            0.88,
    "propublica.org":        0.87,
    "oregonian.com":         0.82,
    "koin.com":              0.72,
    "katu.com":              0.72,
    "oregon.gov":            0.88,
    "multco.us":             0.86,
}

_DOMAIN_DEFAULT: float = 0.35


def score_credibility(domain: str) -> float:
    """Return credibility score for *domain*. Default 0.35 for unknown domains."""
    key = domain.lower().removeprefix("www.")
    return DOMAIN_CREDIBILITY.get(key, _DOMAIN_DEFAULT)


# ── Volume (tag-weighted) ─────────────────────────────────────────────────────

_TAG_WEIGHTS: dict[str, float] = {
    "budget":        0.85,
    "homelessness":  0.82,
    "sweeps":        0.80,
    "housing":       0.83,
    "police":        0.84,
    "ethics":        0.78,
    "charter":       0.75,
    "rcv":           0.72,
    "business_tax":  0.76,
    "fire":          0.74,
    "irp":           0.80,
    "lwv":           0.70,
    "pba":           0.68,
    "psr":           0.68,
    "metro":         0.75,
    "county":        0.75,
    "legislation":   0.80,
    "election":      0.82,
    "zoning":        0.76,
    "infrastructure":0.74,
    "environment":   0.72,
    "crime":         0.78,
    "tax":           0.76,
    "funding":       0.78,
    "council":       0.80,
    "mayor":         0.82,
    "audit":         0.75,
}
_TAG_DEFAULT_WEIGHT: float = 0.50


def score_volume(tags: List[str]) -> float:
    """Return volume score as weighted average of tag scores (0.0–1.0).

    Unknown tags receive the default weight (0.50). An empty tag list
    returns the default weight directly.
    """
    if not tags:
        return _TAG_DEFAULT_WEIGHT
    weights = [_TAG_WEIGHTS.get(t.lower(), _TAG_DEFAULT_WEIGHT) for t in tags]
    return sum(weights) / len(weights)


# ── Velocity (exponential decay, half-life ~36 h) ─────────────────────────────

_HALF_LIFE_HOURS: float = 36.0


def score_velocity(published_at: datetime) -> float:
    """Return velocity score using exponential decay.

    Half-life is ~36 h: a brand-new signal scores ~1.0, a 36 h-old
    signal scores ~0.5, a 72 h-old signal scores ~0.25.
    Always returns a value in [0.0, 1.0].
    """
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - published_at).total_seconds() / 3600)
    return math.exp(-math.log(2) * age_hours / _HALF_LIFE_HOURS)


# ── Novelty (bag-of-words cosine similarity, no external deps) ────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z]+", text.lower())


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a if t in b)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def score_novelty(body: str, prior_summaries: List[str]) -> float:
    """Return novelty score: 1 - max cosine similarity vs. prior summaries.

    Returns 1.0 when there are no prior summaries (completely novel).
    Returns 0.0 when body is identical to a prior summary.
    Uses raw term-frequency bag-of-words — no external ML libraries required.
    """
    if not prior_summaries:
        return 1.0
    body_vec = Counter(_tokenize(body))
    max_sim = max(
        _cosine(body_vec, Counter(_tokenize(s)))
        for s in prior_summaries
    )
    return round(1.0 - max_sim, 4)

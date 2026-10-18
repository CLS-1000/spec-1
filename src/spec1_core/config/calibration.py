# @domain:   spec-1
# @module:   config_calibration
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""SPEC-1 Calibration Parameters.

Operational parameters — not published. Changes require operator sign-off.
"""

from __future__ import annotations

SOURCE_CREDIBILITY: dict[str, float] = {
    "war_on_the_rocks": 0.85,
    "cipher_brief":     0.88,
    "lawfare":          0.87,
    "rand":             0.90,
    "just_security":    0.85,
    "atlantic_council": 0.82,
    "defense_one":      0.83,
    "38_north":         0.89,
    "nk_news":          0.85,
    "csis_korea":       0.88,
    "yonhap":           0.82,
    "reuters_world":    0.90,
    "reuters_us":       0.90,
    "ap_top":           0.88,
    "propublica":       0.85,
    "politico":         0.78,
}

DEFAULT_CREDIBILITY:    float = 0.60
CREDIBILITY_THRESHOLD:  float = 0.65   # above DEFAULT_CREDIBILITY: unlisted sources are blocked
VOLUME_THRESHOLD:       float = 0.30
VELOCITY_THRESHOLD:     float = 0.50   # 0.50 = published within 72h (was 0.0: never blocked)
NOVELTY_THRESHOLD:      int   = 1
ARCHIVE_THRESHOLD:      float = 0.40
PRIORITY_ELEVATED:      float = 0.75
PRIORITY_STANDARD:      float = 0.55
DEFAULT_ANALYST_WEIGHT: float = 0.60

VOLUME_TIERS: list[tuple[int, float]] = [
    (500, 1.0),
    (200, 0.75),
    (80,  0.50),
    (30,  0.30),
    (0,   0.10),
]

COMPOSITE_WEIGHTS: dict[str, float] = {
    "credibility": 0.30,
    "volume":      0.20,
    "velocity":    0.20,
    "novelty":     0.30,
}

CLASSIFICATION_WEIGHTS: dict[str, float] = {
    "CORROBORATED": 1.0,
    "ESCALATE":     0.85,
    "INVESTIGATE":  0.70,
    "MONITOR":      0.55,
    "CONFLICTED":   0.35,
    "ARCHIVE":      0.15,
}

ANALYST_WEIGHTS: dict[str, float] = {
    "Julian E. Barnes":  0.90,
    "Ken Dilanian":      0.85,
    "Natasha Bertrand":  0.87,
    "Shane Harris":      0.88,
    "Phillips O'Brien":  0.85,
    "Michael Kofman":    0.92,
    "Dara Massicot":     0.91,
    "Thomas Rid":        0.89,
    "Melinda Haring":    0.86,
}

CONFIDENCE_BLEND: dict[str, float] = {
    "outcome_confidence":    0.50,
    "source_weight":         0.25,
    "analyst_weight":        0.15,
    "classification_weight": 0.10,
}

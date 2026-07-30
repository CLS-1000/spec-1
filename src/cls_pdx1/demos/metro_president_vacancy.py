# @domain:   citizens_source
# @module:   demos_metro_president_vacancy
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Metro president vacancy scenario — demonstration pipeline run.

Constructs a minimal fixture set for the Metro Council President vacancy event:
one vacancy signal, one official record, one affiliation edge. Runs the full
gate/anomaly/trigger stack without any live HTTP calls.

Intended for: integration tests, portfolio demos, onboarding walkthroughs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from cls_pdx1.anomaly import RollingBaseline
from cls_pdx1.gates import provenance_gate, run_gates, signal_freshness_gate
from cls_pdx1.models import (
    Affiliation,
    ConfidenceTier,
    EdgeType,
    Entity,
    Jurisdiction,
    Official,
    Provenance,
    Sector,
    Signal,
    _make_id,
)
from cls_pdx1.triggers import TriggerPolicy, TriggerState, evaluate_trigger


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Demo fixtures
# ---------------------------------------------------------------------------

_METRO_SOURCE = "https://www.oregonmetro.gov/news/metro-council-president"


def _make_provenance(note: str = "") -> Provenance:
    return Provenance(
        source_uri=_METRO_SOURCE,
        source_name="OregonMetro",
        fetched_at=_now(),
        notes=note or None,
    )


def _vacancy_official() -> Official:
    """Outgoing Metro Council President fixture."""
    return Official(
        official_id=_make_id("official", "Lynn Peterson", "Metro Council President", str(int(Jurisdiction.METRO))),
        name="Lynn Peterson",
        role="Metro Council President",
        jurisdiction=Jurisdiction.METRO,
        status="former",
        provenance=_make_provenance("Metro Council President — appointed 2023, vacancy 2026"),
    )


def _metro_entity() -> Entity:
    """Metro regional government entity fixture."""
    return Entity(
        entity_id=_make_id("entity", "Oregon Metro"),
        canonical_name="Oregon Metro",
        kind="agency",
        sectors=[Sector.GOVERNMENT, Sector.TRANSIT],
        aliases=["Metro", "TriMet Metro", "Portland Metro"],
        jurisdiction=Jurisdiction.METRO,
        provenance=_make_provenance(),
    )


def _vacancy_signal(official: Official, entity: Entity) -> Signal:
    """Leadership vacancy signal — weight 3.0 (executive seat, no caretaker named)."""
    return Signal(
        kind="metro_president_vacancy",
        occurred_at=_now(),
        detected_at=_now(),
        official_id=official.official_id,
        entity_id=entity.entity_id,
        weight=3.0,
        description=(
            "Metro Council President seat vacant. "
            "Governor appointment expected within 90 days per ORS 267.090."
        ),
        provenance=_make_provenance(),
    )


def _vacancy_affiliation(official: Official, entity: Entity) -> Affiliation:
    """BOARD_SEAT edge: Peterson → Oregon Metro (open-ended, term ended)."""
    return Affiliation(
        official_id=official.official_id,
        entity_id=entity.entity_id,
        edge_type=EdgeType.BOARD_SEAT,
        confidence=ConfidenceTier.HARD_RECORD,
        observed_at=_now(),
        valid_from=_now().date().replace(year=2023, month=1, day=1),
        valid_to=None,
        description="Metro Council President — board-equivalent executive seat",
        provenance=_make_provenance(),
        corroborating_uris=[_METRO_SOURCE],
    )


# ---------------------------------------------------------------------------
# Demo result type
# ---------------------------------------------------------------------------


@dataclass
class VacancyDemoResult:
    """Output of run_vacancy_demo()."""

    official: Official
    entity: Entity
    signal: Signal
    affiliation: Affiliation
    gate_ok: bool
    gate_failures: list[str]
    trigger_should_publish: bool
    trigger_reason: str
    anomaly_sigma: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_vacancy_demo() -> VacancyDemoResult:
    """Run the Metro president vacancy scenario end-to-end.

    No live HTTP calls. Returns VacancyDemoResult with all intermediate state
    so tests can inspect gates, trigger decisions, and anomaly detection.
    """
    official = _vacancy_official()
    entity = _metro_entity()
    signal = _vacancy_signal(official, entity)
    affiliation = _vacancy_affiliation(official, entity)

    # Gates
    prov_result = provenance_gate(signal)
    fresh_result = signal_freshness_gate(signal)
    all_ok, failures = run_gates(prov_result, fresh_result)

    # Anomaly baseline — evaluate on zero baseline FIRST, then ingest.
    # A fresh entity with no history and current_value > 0 registers as 3σ (TIER_1).
    baseline = RollingBaseline(window_days=90)
    anomaly = baseline.evaluate(
        entity_id=entity.entity_id,
        current_value=signal.weight,
        kind="metro_president_vacancy",
        provenance=signal.provenance,
        description="Metro executive vacancy — no prior baseline; treated as TIER_1 event",
    )
    baseline.ingest(signal)   # Record for future cycle comparisons
    sigma = anomaly.sigma if anomaly else 0.0

    # Trigger
    state = TriggerState()
    state.add_signal(signal)
    if anomaly:
        state.add_anomaly(anomaly)

    policy = TriggerPolicy(
        signal_weight_threshold=2.5,
        min_spacing_days=0,
        tier1_auto_trigger=True,
    )
    decision = evaluate_trigger(state, policy)

    return VacancyDemoResult(
        official=official,
        entity=entity,
        signal=signal,
        affiliation=affiliation,
        gate_ok=all_ok,
        gate_failures=failures,
        trigger_should_publish=decision.should_publish,
        trigger_reason=decision.reason or "",
        anomaly_sigma=sigma or 0.0,
    )

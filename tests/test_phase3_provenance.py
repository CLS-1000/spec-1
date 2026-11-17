"""Regression tests for Phase 3 record provenance fields."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from spec1_core.app.cycle import SPEC1_RECORD_SCHEMA_VERSION, build_record_dict
from spec1_core.schemas.models import (
    IntelligenceRecord,
    Investigation,
    Opportunity,
    Outcome,
    ParsedSignal,
    Signal,
)


def test_build_record_dict_stamps_provenance_and_raw_sha256() -> None:
    raw_text = "Federal oversight committee issued a subpoena on defense fuel contracts."
    pub = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    sig = Signal(
        signal_id="sig-prov-1",
        source="reuters",
        source_type="rss",
        text=raw_text,
        url="https://example.org/story/1",
        author="staff",
        published_at=pub,
        velocity=0.8,
        engagement=0.5,
        run_id="run-prov-1",
        environment="production",
    )
    ps = ParsedSignal(
        signal_id="sig-prov-1",
        cleaned_text=raw_text,
        keywords=["oversight", "subpoena"],
        entities=["Federal"],
        language="en",
        word_count=10,
    )
    opp = Opportunity(
        opportunity_id="opp-prov-1",
        signal_id="sig-prov-1",
        score=0.78,
        priority="STANDARD",
        gate_results={"credibility": True, "volume": True, "velocity": True, "novelty": True},
        run_id="run-prov-1",
    )
    inv = Investigation(
        investigation_id="inv-prov-1",
        opportunity_id="opp-prov-1",
        hypothesis="Subpoena targets fuel logistics.",
        queries=["subpoena fuel"],
        sources_to_check=["congress.gov"],
        analyst_leads=["lead-1"],
    )
    outcome = Outcome(
        outcome_id="out-prov-1",
        classification="INVESTIGATE",
        confidence=0.82,
        evidence=["LLM assessment: verified committee docket"],
        analysis_tier="llm_verified",
    )
    rec = IntelligenceRecord(
        record_id="rec-prov-1",
        pattern="[STANDARD] Oversight subpoena",
        classification="INVESTIGATE",
        confidence=0.82,
        source_weight=0.85,
        analyst_weight=0.90,
    )

    out = build_record_dict(
        rec, sig=sig, ps=ps, opp=opp, inv=inv, outcome=outcome,
        run_id="run-prov-1", environment="production",
    )
    assert out["schema_version"] == SPEC1_RECORD_SCHEMA_VERSION
    assert out["harvester_version"]
    assert out["raw_sha256"] == hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    assert out["source_type"] == "rss"
    assert out["signal_published_at"] == pub.isoformat()

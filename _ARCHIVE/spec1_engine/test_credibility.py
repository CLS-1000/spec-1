# @domain:   intelligence
# @module:   test_credibility
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

import pytest
from spec1_engine.schemas.models import AnalystRecord, Signal
from spec1_engine.analysts.credibility import CredibilityAnalyst

@pytest.fixture
def mock_analyst_registry(monkeypatch):
    # Populating all required schema properties to keep __init__ happy
    mock_records = [
        AnalystRecord(
            analyst_id="analyst-1",
            name="Julian E. Barnes",
            affiliation="The New York Times",
            domains=["intelligence", "national-security"],
            credibility_score=0.90
        ),
        AnalystRecord(
            analyst_id="analyst-2",
            name="Michael Kofman",
            affiliation="OSINT",
            domains=["military-analysis"],
            credibility_score=0.95
        ),
    ]
    monkeypatch.setattr("spec1_engine.analysts.registry.load_all", lambda: mock_records)
    return CredibilityAnalyst()

@pytest.mark.parametrize(
    "author_input,expected_score,should_match",
    [
        ("Julian Barnes", 0.90, True),
        ("Julian E. Barnes", 0.90, True),
        ("J. Barnes", 0.90, True),
        ("By Julian Barnes", 0.90, True),
        ("Julian Barnes, David Sanger, and Eric Schmitt", 0.90, True),
        ("Reporting by J.Barnes.", 0.90, True),
        ("Jonathan Barnes", 0.50, False),
        ("Barnes & Noble", 0.50, False),
        ("Mark Thompson", 0.50, False),
        ("J.E. Barnes and team", 0.90, True),
    ],
)
def test_credibility_matching_edge_cases(mock_analyst_registry, author_input, expected_score, should_match):
    analyst = mock_analyst_registry
    signal = Signal(
        signal_id="sig-1", source="mock", source_type="mock", text="mock",
        published_at="2026-05-30", velocity=1.0, engagement=1, run_id="mock-run",
        environment="test", author=author_input, url="https://spec1.internal/test"
    )

    assert analyst.score(signal) == expected_score

    record = analyst.match_record(author_input)
    if should_match:
        assert record is not None
        assert "Barnes" in record.name
    else:
        assert record is None

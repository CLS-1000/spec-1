# @domain:   spec-1
# @module:   test_e2e_metro_president_vacancy
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""End-to-end tests — Metro Council President vacancy scenario.

Exercises the full gate → anomaly → trigger stack via run_vacancy_demo().
No live HTTP calls. Validates that a high-weight executive vacancy signal
clears all structural gates and fires the publication trigger.
"""

from __future__ import annotations

from titan.demos.metro_president_vacancy import run_vacancy_demo
from titan.gates import provenance_gate, signal_freshness_gate


class TestMetroPresidentVacancyDemo:
    def test_demo_runs_without_error(self):
        result = run_vacancy_demo()
        assert result.errors == []

    def test_demo_produces_signal(self):
        result = run_vacancy_demo()
        assert result.signal is not None
        assert result.signal.kind == "metro_president_vacancy"
        assert result.signal.weight > 0

    def test_signal_passes_provenance_gate(self):
        result = run_vacancy_demo()
        ok, reason = provenance_gate(result.signal)
        assert ok, f"provenance gate failed: {reason}"

    def test_signal_passes_freshness_gate(self):
        result = run_vacancy_demo()
        ok, reason = signal_freshness_gate(result.signal)
        assert ok, f"freshness gate failed: {reason}"

    def test_cycle_result_has_no_fatal_errors(self):
        result = run_vacancy_demo()
        assert result.gate_ok, f"gate failures: {result.gate_failures}"

    def test_trigger_fires_on_vacancy_signal(self):
        result = run_vacancy_demo()
        assert result.trigger_should_publish, (
            f"trigger did not fire — reason: {result.trigger_reason}"
        )

    def test_official_record_is_populated(self):
        result = run_vacancy_demo()
        assert result.official.name == "Lynn Peterson"
        assert result.official.role == "Metro Council President"

    def test_entity_record_is_metro(self):
        result = run_vacancy_demo()
        assert "Metro" in result.entity.canonical_name

    def test_affiliation_edge_type_is_board_seat(self):
        from titan.models import EdgeType
        result = run_vacancy_demo()
        assert result.affiliation.edge_type == EdgeType.BOARD_SEAT

    def test_anomaly_detected_on_first_signal(self):
        """First signal on a zero baseline must register as anomaly (sigma > 0)."""
        result = run_vacancy_demo()
        assert result.anomaly_sigma > 0.0

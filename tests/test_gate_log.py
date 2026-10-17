"""Gate decisions are logged for every scored signal — passed and blocked."""

from __future__ import annotations

from datetime import datetime, timezone

from spec1_core.schemas.models import Signal
from spec1_core.signal.gate_log import (
    GATE_LOG_ENV,
    GateDecisionLog,
    build_decision,
    default_gate_log_path,
)
from spec1_core.signal.parser import parse_signal
from spec1_core.signal.scorer import evaluate_gates, score_signal

STRONG_TEXT = (
    "New RAND analysis examines Russia's military strategy and intelligence operations "
    "in Ukraine. The report assesses NATO alliance posture and defense capabilities "
    "against potential escalation scenarios. Cyber warfare and nuclear deterrence "
    "are discussed. Pentagon officials confirmed the assessment."
)


def _signal(**overrides) -> Signal:
    base = dict(
        signal_id="sig-gate-001",
        source="rand",
        source_type="rss",
        text=STRONG_TEXT,
        url="https://www.rand.org/blog/2024/test.html",
        author="Analyst",
        published_at=datetime.now(timezone.utc),
        velocity=0.9,
        engagement=0.0,
        run_id="run-test",
        environment="test",
    )
    base.update(overrides)
    return Signal(**base)


def test_evaluate_gates_reports_values_thresholds_and_results():
    sig = _signal()
    ev = evaluate_gates(sig, parse_signal(sig))
    assert set(ev["gates"]) == {"credibility", "volume", "velocity", "novelty"}
    for gate in ev["gates"].values():
        assert {"value", "threshold", "passed"} <= set(gate)
    assert ev["passed"] == all(g["passed"] for g in ev["gates"].values())
    assert ev["failed_gates"] == [n for n, g in ev["gates"].items() if not g["passed"]]


def test_evaluate_gates_agrees_with_score_signal():
    for sig in (_signal(), _signal(signal_id="sig-short", text="Too short.")):
        ps = parse_signal(sig)
        assert evaluate_gates(sig, ps)["passed"] == (score_signal(sig, ps) is not None)


def test_blocked_signal_records_which_gate_failed(tmp_path):
    # No novelty terms: blocked at the novelty gate.
    plain = _signal(
        signal_id="sig-plain",
        text="The weather was mild and the garden looked nice today. " * 6,
    )
    ev = evaluate_gates(plain, parse_signal(plain))
    assert not ev["passed"]
    assert ev["failed_gates"] == ["novelty"]

    log = GateDecisionLog(tmp_path / "gate.jsonl")
    log.append(build_decision(plain, ev, run_id="run-test"))
    (row,) = log.read_all()
    assert row["decision"] == "blocked"
    assert row["failed_gates"] == ["novelty"]
    assert row["opportunity_id"] is None
    assert row["gates"]["novelty"]["passed"] is False
    assert row["gates"]["novelty"]["value"] < row["gates"]["novelty"]["threshold"]


def test_log_is_append_only(tmp_path):
    log = GateDecisionLog(tmp_path / "gate.jsonl")
    sig = _signal()
    ev = evaluate_gates(sig, parse_signal(sig))
    log.append(build_decision(sig, ev, run_id="r1"))
    log.append(build_decision(sig, ev, run_id="r2"))
    assert [r["run_id"] for r in log.read_all()] == ["r1", "r2"]


def test_default_path_follows_store_and_env(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE_LOG_ENV, raising=False)
    assert default_gate_log_path(tmp_path / "intel.jsonl") == tmp_path / "intel_gate_decisions.jsonl"
    monkeypatch.setenv(GATE_LOG_ENV, str(tmp_path / "custom.jsonl"))
    assert default_gate_log_path(tmp_path / "intel.jsonl") == tmp_path / "custom.jsonl"

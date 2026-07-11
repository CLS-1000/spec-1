# @domain:   machine
# @module:   test_fallback_client
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the three-tier LLM fallback client."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec1_core.llm import tier3_rules
from spec1_core.llm.fallback_client import FallbackLLMClient


# ── Helpers ────────────────────────────────────────────────────────────────────

THREAT_SIGNAL = (
    "Armed forces launched missile attack on civilian infrastructure. "
    "Military strike confirmed. Weapons cache discovered near border."
)
ANOMALY_SIGNAL = (
    "Unusual troop movements detected near eastern frontier. "
    "Surveillance intelligence suggests potential mobilization."
)
CLEAR_SIGNAL = (
    "The annual trade conference in Geneva concluded with participants "
    "discussing sustainable agricultural policies."
)


def make_claude_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def make_client(tmp_path: Path) -> FallbackLLMClient:
    return FallbackLLMClient(
        ollama_model="llama3",
        ollama_url="http://localhost:11434",
        log_path=tmp_path / "llm_fallback.jsonl",
    )


# ── Tier 3 (rule-based) — unit tests ──────────────────────────────────────────

class TestTier3Rules:
    def test_threat_signal_returns_threat(self):
        verdict, confidence, _ = tier3_rules.score(THREAT_SIGNAL)
        assert verdict == "THREAT"

    def test_threat_confidence_above_floor(self):
        _, confidence, _ = tier3_rules.score(THREAT_SIGNAL)
        assert confidence > 0.4

    def test_anomaly_signal_returns_anomaly(self):
        verdict, confidence, _ = tier3_rules.score(ANOMALY_SIGNAL)
        assert verdict == "ANOMALY"

    def test_clear_signal_returns_clear(self):
        verdict, _, _ = tier3_rules.score(CLEAR_SIGNAL)
        assert verdict == "CLEAR"

    def test_confidence_in_range(self):
        for text in (THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL):
            _, confidence, _ = tier3_rules.score(text)
            assert 0.0 <= confidence <= 1.0, f"Out of range for: {text[:40]}"

    def test_reasoning_non_empty(self):
        for text in (THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL):
            _, _, reasoning = tier3_rules.score(text)
            assert reasoning

    def test_to_verifier_json_valid_json(self):
        raw = tier3_rules.to_verifier_json(THREAT_SIGNAL)
        data = json.loads(raw)
        assert "verified" in data
        assert "confidence" in data
        assert "reasoning" in data
        assert "classification" in data

    def test_to_verifier_json_threat_maps_to_escalate(self):
        data = json.loads(tier3_rules.to_verifier_json(THREAT_SIGNAL))
        assert data["classification"] == "ESCALATE"
        assert data["verified"] is True

    def test_to_verifier_json_anomaly_maps_to_investigate(self):
        data = json.loads(tier3_rules.to_verifier_json(ANOMALY_SIGNAL))
        assert data["classification"] == "INVESTIGATE"

    def test_to_verifier_json_clear_maps_to_monitor(self):
        data = json.loads(tier3_rules.to_verifier_json(CLEAR_SIGNAL))
        assert data["classification"] == "MONITOR"
        assert data["verified"] is False

    def test_empty_text_does_not_raise(self):
        verdict, confidence, reasoning = tier3_rules.score("")
        assert verdict == "CLEAR"
        assert reasoning


# ── FallbackLLMClient — Tier 1 success ────────────────────────────────────────

class TestTier1Claude:
    def test_complete_uses_claude_when_available(self, tmp_path):
        client = make_client(tmp_path)
        payload = json.dumps({"verified": True, "confidence": 0.8,
                              "reasoning": "Corroborated.", "classification": "CORROBORATED"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                result = client.complete(ANOMALY_SIGNAL, system="You are an analyst.")

        assert result == payload
        assert client.get_active_tier() == "claude"

    def test_analyze_tier1_returns_spec_dict(self, tmp_path):
        client = make_client(tmp_path)
        payload = json.dumps({"verified": True, "confidence": 0.75,
                              "reasoning": "High confidence.", "classification": "ESCALATE"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                result = client.analyze(THREAT_SIGNAL)

        assert result["verdict"] == "THREAT"
        assert result["tier_used"] == "claude"
        assert 0.0 <= result["confidence"] <= 1.0
        assert "latency_ms" in result
        assert "cost_estimate_usd" in result

    def test_cost_accumulates_after_claude_calls(self, tmp_path):
        client = make_client(tmp_path)
        payload = json.dumps({"confidence": 0.5, "reasoning": "ok",
                              "classification": "MONITOR"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                client.analyze(CLEAR_SIGNAL)
                client.analyze(CLEAR_SIGNAL)

        assert client.get_cost_estimate() > 0.0

    def test_no_api_key_falls_to_tier3(self, tmp_path):
        client = make_client(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                result = client.complete(ANOMALY_SIGNAL, system="")

        data = json.loads(result)
        assert "classification" in data
        assert client.get_active_tier() == "mock"


# ── FallbackLLMClient — Claude 401/failure → Ollama fallback ──────────────────

class TestTier2OllamaFallback:
    def test_claude_401_falls_to_ollama(self, tmp_path):
        client = make_client(tmp_path)
        ollama_response = json.dumps({"verified": True, "confidence": 0.65,
                                      "reasoning": "Ollama assessed.", "classification": "INVESTIGATE"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("401 Unauthorized")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_response):
                            result = client.complete(ANOMALY_SIGNAL, system="analyst")

        assert result == ollama_response
        assert client.get_active_tier() == "ollama"

    def test_claude_429_falls_to_ollama(self, tmp_path):
        client = make_client(tmp_path)
        ollama_json = json.dumps({"confidence": 0.5, "classification": "MONITOR", "reasoning": "ok"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("429 rate_limit_error")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                            client.complete(CLEAR_SIGNAL, system="")

        assert client.get_active_tier() == "ollama"

    def test_ollama_auto_spawned_when_not_running(self, tmp_path):
        client = make_client(tmp_path)
        ollama_json = json.dumps({"confidence": 0.4, "classification": "INVESTIGATE", "reasoning": "ok"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "OLLAMA_AUTO_SPAWN": "true"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("API error")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                    with patch("spec1_core.llm.ollama_manager.spawn", return_value=True) as mock_spawn:
                        with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                            with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                                client.complete(ANOMALY_SIGNAL)

        mock_spawn.assert_called_once()

    def test_analyze_ollama_returns_spec_dict(self, tmp_path):
        client = make_client(tmp_path)
        ollama_json = json.dumps({"confidence": 0.55, "classification": "INVESTIGATE",
                                  "reasoning": "Anomaly detected by Ollama."})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("Unavailable")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                            result = client.analyze(ANOMALY_SIGNAL)

        assert result["tier_used"] == "ollama"
        assert result["verdict"] == "ANOMALY"
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["cost_estimate_usd"] == 0.0


# ── FallbackLLMClient — Ollama unavailable → Tier 3 ──────────────────────────

class TestTier3MockFallback:
    def test_both_tiers_fail_uses_mock(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("Claude down")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                    with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                        result = client.complete(THREAT_SIGNAL, system="")

        data = json.loads(result)
        assert "classification" in data
        assert client.get_active_tier() == "mock"

    def test_analyze_mock_threat_returns_threat_verdict(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("down")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                    with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                        result = client.analyze(THREAT_SIGNAL)

        assert result["verdict"] == "THREAT"
        assert result["tier_used"] == "mock"
        assert result["cost_estimate_usd"] == 0.0

    def test_analyze_mock_never_raises(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    try:
                        client.analyze(CLEAR_SIGNAL)
                    except Exception as exc:
                        pytest.fail(f"analyze raised unexpectedly: {exc}")

    def test_complete_never_raises(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    try:
                        client.complete("anything")
                    except Exception as exc:
                        pytest.fail(f"complete raised unexpectedly: {exc}")


# ── Output schema consistency across tiers ────────────────────────────────────

class TestOutputSchemaConsistency:
    REQUIRED_KEYS = {"verdict", "confidence", "analysis", "tier_used",
                     "latency_ms", "cost_estimate_usd"}

    def _analyze_via_tier1(self, tmp_path, signal):
        client = make_client(tmp_path)
        payload = json.dumps({"confidence": 0.7, "reasoning": "Claude says so.",
                               "classification": "INVESTIGATE"})
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                return client.analyze(signal)

    def _analyze_via_tier2(self, tmp_path, signal):
        client = make_client(tmp_path)
        payload = json.dumps({"confidence": 0.6, "reasoning": "Ollama says so.",
                               "classification": "MONITOR"})
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.side_effect = Exception("fail")
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=payload):
                            return client.analyze(signal)

    def _analyze_via_tier3(self, tmp_path, signal):
        client = make_client(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    return client.analyze(signal)

    @pytest.mark.parametrize("signal", [THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL])
    def test_tier1_schema_complete(self, tmp_path, signal):
        result = self._analyze_via_tier1(tmp_path, signal)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    @pytest.mark.parametrize("signal", [THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL])
    def test_tier2_schema_complete(self, tmp_path, signal):
        result = self._analyze_via_tier2(tmp_path, signal)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    @pytest.mark.parametrize("signal", [THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL])
    def test_tier3_schema_complete(self, tmp_path, signal):
        result = self._analyze_via_tier3(tmp_path, signal)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    @pytest.mark.parametrize("signal", [THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL])
    def test_verdict_is_valid_across_tiers(self, tmp_path, signal):
        valid = {"THREAT", "ANOMALY", "CLEAR"}
        for result in [
            self._analyze_via_tier1(tmp_path, signal),
            self._analyze_via_tier2(tmp_path, signal),
            self._analyze_via_tier3(tmp_path, signal),
        ]:
            assert result["verdict"] in valid, f"Got {result['verdict']!r}"

    @pytest.mark.parametrize("signal", [THREAT_SIGNAL, ANOMALY_SIGNAL, CLEAR_SIGNAL])
    def test_confidence_in_range_across_tiers(self, tmp_path, signal):
        for result in [
            self._analyze_via_tier1(tmp_path, signal),
            self._analyze_via_tier2(tmp_path, signal),
            self._analyze_via_tier3(tmp_path, signal),
        ]:
            assert 0.0 <= result["confidence"] <= 1.0


# ── Latency logging ───────────────────────────────────────────────────────────

class TestLatencyLogging:
    def test_log_written_on_tier1_call(self, tmp_path):
        client = make_client(tmp_path)
        payload = json.dumps({"confidence": 0.7, "reasoning": "ok", "classification": "MONITOR"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                client.analyze(CLEAR_SIGNAL)

        log_file = tmp_path / "llm_fallback.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["tier"] == "claude"
        assert entry["success"] is True
        assert entry["latency_ms"] >= 0

    def test_log_written_on_tier3_call(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    client.analyze(THREAT_SIGNAL)

        log_file = tmp_path / "llm_fallback.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["tier"] == "mock"

    def test_latency_ms_is_non_negative(self, tmp_path):
        client = make_client(tmp_path)
        payload = json.dumps({"confidence": 0.5, "classification": "ARCHIVE", "reasoning": "old"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(payload)
                result = client.analyze(CLEAR_SIGNAL)

        assert result["latency_ms"] >= 0

    def test_multiple_calls_append_to_log(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    client.analyze(THREAT_SIGNAL)
                    client.analyze(CLEAR_SIGNAL)

        log_file = tmp_path / "llm_fallback.jsonl"
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


# ── investigate() ─────────────────────────────────────────────────────────────

class TestInvestigate:
    def test_investigate_returns_dict(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    result = client.investigate("What is the threat level in eastern Ukraine?")

        assert isinstance(result, dict)
        assert "verdict" in result

    def test_investigate_never_raises(self, tmp_path):
        client = make_client(tmp_path)

        with patch.dict("os.environ", {}, clear=True):
            import os; os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                    try:
                        client.investigate("test query")
                    except Exception as exc:
                        pytest.fail(f"investigate raised: {exc}")


# ── Markdown fence stripping ───────────────────────────────────────────────────

class TestFenceStripping:
    def test_json_in_fences_parsed_correctly(self, tmp_path):
        client = make_client(tmp_path)
        fenced = '```json\n{"confidence": 0.6, "classification": "ESCALATE", "reasoning": "ok"}\n```'

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(fenced)
                result = client.analyze(THREAT_SIGNAL)

        assert result["verdict"] == "THREAT"
        assert result["tier_used"] == "claude"

    def test_plain_fences_stripped(self, tmp_path):
        client = make_client(tmp_path)
        fenced = '```\n{"confidence": 0.3, "classification": "MONITOR", "reasoning": "quiet"}\n```'

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as MockCls:
                MockCls.return_value.messages.create.return_value = make_claude_response(fenced)
                result = client.analyze(CLEAR_SIGNAL)

        assert result["tier_used"] == "claude"


# ── SPEC1_DEV_MODE ────────────────────────────────────────────────────────────

class TestDevMode:
    def test_dev_mode_skips_claude_goes_to_ollama(self, tmp_path):
        ollama_json = json.dumps({"confidence": 0.6, "classification": "INVESTIGATE",
                                  "reasoning": "Ollama in dev mode."})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key",
                                        "SPEC1_DEV_MODE": "true"}):
            client = make_client(tmp_path)
            with patch("anthropic.Anthropic") as MockCls:
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                            result = client.analyze(ANOMALY_SIGNAL)

        MockCls.assert_not_called()
        assert result["tier_used"] == "ollama"

    def test_dev_mode_complete_skips_claude(self, tmp_path):
        ollama_json = json.dumps({"confidence": 0.5, "classification": "MONITOR",
                                  "reasoning": "ok"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key",
                                        "SPEC1_DEV_MODE": "true"}):
            client = make_client(tmp_path)
            with patch("anthropic.Anthropic") as MockCls:
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                        with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                            result = client.complete(CLEAR_SIGNAL)

        MockCls.assert_not_called()
        assert result == ollama_json

    def test_dev_mode_falls_to_tier3_when_ollama_down(self, tmp_path):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key",
                                        "SPEC1_DEV_MODE": "true"}):
            client = make_client(tmp_path)
            with patch("anthropic.Anthropic") as MockCls:
                with patch("spec1_core.llm.ollama_manager.is_running", return_value=False):
                    with patch("spec1_core.llm.ollama_manager.spawn", return_value=False):
                        result = client.analyze(THREAT_SIGNAL)

        MockCls.assert_not_called()
        assert result["tier_used"] == "mock"
        assert result["verdict"] in {"THREAT", "ANOMALY", "CLEAR"}

    def test_dev_mode_prints_alert(self, tmp_path, capsys):
        with patch.dict("os.environ", {"SPEC1_DEV_MODE": "true"}):
            make_client(tmp_path)

        captured = capsys.readouterr()
        assert "DEV MODE" in captured.out
        assert "Tier 1" in captured.out

    def test_no_dev_mode_no_alert(self, tmp_path, capsys):
        with patch.dict("os.environ", {"SPEC1_DEV_MODE": "false"}):
            make_client(tmp_path)

        captured = capsys.readouterr()
        assert "DEV MODE" not in captured.out

    def test_dev_mode_cost_is_zero(self, tmp_path):
        ollama_json = json.dumps({"confidence": 0.5, "classification": "MONITOR",
                                  "reasoning": "ok"})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key",
                                        "SPEC1_DEV_MODE": "true"}):
            client = make_client(tmp_path)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                        client.analyze(CLEAR_SIGNAL)

        assert client.get_cost_estimate() == 0.0

    def test_output_schema_identical_in_dev_mode(self, tmp_path):
        required = {"verdict", "confidence", "analysis", "tier_used",
                    "latency_ms", "cost_estimate_usd"}
        ollama_json = json.dumps({"confidence": 0.7, "classification": "ESCALATE",
                                  "reasoning": "Dev mode result."})

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key",
                                        "SPEC1_DEV_MODE": "true"}):
            client = make_client(tmp_path)
            with patch("spec1_core.llm.ollama_manager.is_running", return_value=True):
                with patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True):
                    with patch("spec1_core.llm.ollama_manager.chat", return_value=ollama_json):
                        result = client.analyze(THREAT_SIGNAL)

        assert required.issubset(result.keys())
        assert result["verdict"] in {"THREAT", "ANOMALY", "CLEAR"}
        assert 0.0 <= result["confidence"] <= 1.0

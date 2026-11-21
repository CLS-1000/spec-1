"""Tests for shared model_config, licensing notes, and num_ctx truncation guards."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec1_core.llm import fallback_client, model_config, ollama_manager


def test_mirrored_model_config_sha256_parity() -> None:
    """spec-1 and newsroom copies of model_config.py must stay byte-identical."""
    spec1_copy = Path(__file__).resolve().parents[1] / "src/spec1_core/llm/model_config.py"
    candidates = [
        Path.home() / "projects/notitia-civica/.claude/worktrees/model-config/spec1_bridge/model_config.py",
        Path.home() / "projects/notitia-civica/spec1_bridge/model_config.py",
    ]
    newsroom_copy = next((p for p in candidates if p.is_file()), None)
    if newsroom_copy is None:
        pytest.skip("Sibling newsroom checkout not present in this CI environment")
    assert hashlib.sha256(spec1_copy.read_bytes()).hexdigest() == hashlib.sha256(
        newsroom_copy.read_bytes()
    ).hexdigest()


def test_dotenv_has_top_priority_over_process_env_and_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "mistral")
    monkeypatch.setenv("SPEC1_OLLAMA_URL", "http://127.0.0.1:11434")
    (tmp_path / ".env").write_text(
        "OLLAMA_MODEL=llama3.2:triage\n"
        "OLLAMA_HOST=localhost:11434\n"
        "SPEC1_LLM_LOG_PATH=logs/custom_llm.jsonl\n",
        encoding="utf-8",
    )

    cfg = model_config.load(tmp_path)
    assert cfg.ollama_model == "llama3.2:triage"
    assert cfg.ollama_model_source == "dotenv"
    assert cfg.ollama_url == "http://localhost:11434"
    assert cfg.ollama_url_source == "dotenv"
    assert cfg.llm_log_path == tmp_path.resolve() / "logs/custom_llm.jsonl"
    assert cfg.call_timeout == 180.0
    assert cfg.chat_timeout == 600.0
    assert cfg.claude_model == "claude-haiku-5-5"
    assert cfg.claude_writer_model == "claude-sonnet-5-5"
    assert "source=dotenv" in cfg.format_cycle_summary()


def test_warns_when_ollama_host_and_spec1_ollama_url_disagree(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / ".env").write_text(
        "OLLAMA_HOST=localhost:11434\n"
        "SPEC1_OLLAMA_URL=http://127.0.0.1:11435\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        cfg = model_config.load(tmp_path)
    assert cfg.ollama_url == "http://127.0.0.1:11435"
    assert any("disagrees with SPEC1_OLLAMA_URL" in rec.message for rec in caplog.records)


def test_model_licensing_notes_and_qwen35_exclusion(tmp_path: Path) -> None:
    assert "commercial use: yes" in model_config.describe_model_license("llama3.2:triage")
    assert "Apache 2.0" in model_config.describe_model_license("mistral:latest")
    assert "commercial use: no" in model_config.describe_model_license("qwen2.5:3b")
    assert not model_config.is_model_allowed("Qwen3.5-9B-Uncensored-GGUF")
    assert "EXCLUDED" in model_config.describe_model_license("Qwen3.5-9B-Uncensored-GGUF")

    (tmp_path / ".env").write_text("OLLAMA_MODEL=Qwen3.5-Uncensored\n", encoding="utf-8")
    with pytest.raises(ValueError, match="excluded by licensing policy"):
        model_config.load(tmp_path)


def test_compute_num_ctx_scales_and_refuses_oversized_prompt() -> None:
    # Small prompt floors at 4096
    assert model_config.compute_num_ctx(300, available_bytes=8 * 1024**3) == 4096
    # Medium prompt rounds up to next 1024 boundary
    ctx = model_config.compute_num_ctx(15000, available_bytes=8 * 1024**3)
    assert ctx == 6144
    # Oversized prompt raises PromptTooLong instead of silently truncating
    with pytest.raises(model_config.PromptTooLong):
        model_config.compute_num_ctx(100_000, max_ctx=16384, available_bytes=8 * 1024**3)
    # Tight RAM cap also refuses prompts that exceed available memory headroom
    with pytest.raises(model_config.PromptTooLong):
        model_config.compute_num_ctx(20_000, max_ctx=16384, available_bytes=512 * 1024**2)


def test_fallback_client_refuses_oversized_prompt_and_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SPEC1_HOME", str(tmp_path))
    monkeypatch.setenv("SPEC1_LLM_ROUTE", "local,rules")
    monkeypatch.setenv("SPEC1_OLLAMA_MAX_CTX", "4096")

    client = fallback_client.FallbackLLMClient(
        ollama_model="llama3.2:triage",
        log_path=tmp_path / "llm.jsonl",
    )
    huge_prompt = "x" * 30_000  # ~10,000 tokens > 4,096 cap

    with (
        patch.object(ollama_manager, "is_running", return_value=True),
        patch.object(ollama_manager, "ensure_model", return_value=True),
        patch.object(ollama_manager, "model_context_length", return_value=16384),
        patch("urllib.request.urlopen") as mock_urlopen,
        caplog.at_level(logging.ERROR),
    ):
        result = client.analyze(huge_prompt)

    # Never sent truncated input over HTTP; fell through to rules cleanly
    mock_urlopen.assert_not_called()
    assert result["tier_used"] == "rules"
    assert any("Refusing oversized Ollama prompt" in rec.message for rec in caplog.records)

    entries = [json.loads(line) for line in (tmp_path / "llm.jsonl").read_text().splitlines()]
    assert entries[0]["tier"] == "ollama"
    assert entries[0]["model"] == "llama3.2:triage"
    assert entries[0]["success"] is False
    assert entries[0]["error"] == "PromptTooLong"


def test_post_call_truncation_check_raises_prompt_too_long() -> None:
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps({
        "message": {"content": "partial"},
        "prompt_eval_count": 4096,
    }).encode("utf-8")
    with (
        patch.object(ollama_manager, "model_context_length", return_value=16384),
        patch("urllib.request.urlopen", return_value=resp),
        pytest.raises(model_config.PromptTooLong, match="prompt_eval_count=4096 >= num_ctx=4096"),
    ):
        ollama_manager.chat("hello", "sys", "llama3.2:triage")

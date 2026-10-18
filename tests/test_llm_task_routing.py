"""Per-task LLM routing: local model runs the cycle, Claude reserved for writing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from spec1_core.llm.fallback_client import FallbackLLMClient, resolve_route

ROUTE_VARS = ("SPEC1_LLM_ROUTE", "SPEC1_LLM_ROUTE_ANALYZE", "SPEC1_DEV_MODE",
              "SPEC1_LOCAL_BACKEND", "SPEC1_LOCAL_URL", "SPEC1_LOCAL_MODEL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ROUTE_VARS:
        monkeypatch.delenv(var, raising=False)


def test_default_route_is_unchanged():
    assert resolve_route("analyze") == ["claude", "local", "mock"]
    assert resolve_route("analyze", dev_mode=True) == ["local", "mock"]


def test_task_route_overrides_global(monkeypatch):
    monkeypatch.setenv("SPEC1_LLM_ROUTE", "claude,local")
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local")
    assert resolve_route("analyze") == ["local", "mock"]
    assert resolve_route("write") == ["claude", "local", "mock"]


def test_route_accepts_aliases_and_always_ends_in_mock(monkeypatch):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "Ollama, rules, bogus, ollama")
    assert resolve_route("analyze") == ["local", "mock"]


def _openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp


def test_local_openai_backend_never_touches_claude(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local,mock")
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "openai")
    monkeypatch.setenv("SPEC1_LOCAL_URL", "http://localhost:5272/v1")
    monkeypatch.setenv("SPEC1_LOCAL_MODEL", "Qwen-7B-openvino-gpu:2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-be-used")
    body = json.dumps({"classification": "ESCALATE", "confidence": 0.8, "reasoning": "x"})

    with patch("requests.post", return_value=_openai_response(body)) as post, \
         patch("anthropic.Anthropic") as claude:
        client = FallbackLLMClient(task="analyze", log_path=tmp_path / "llm.jsonl")
        out = client.analyze("prompt", "system")

    claude.assert_not_called()
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert url == "http://localhost:5272/v1/chat/completions"
    assert payload["model"] == "Qwen-7B-openvino-gpu:2"
    assert payload["messages"][0] == {"role": "system", "content": "system"}
    assert out["tier_used"] == "local"
    assert out["verdict"] == "THREAT"
    assert out["cost_estimate_usd"] == 0.0

    logged = json.loads((tmp_path / "llm.jsonl").read_text().splitlines()[-1])
    assert logged["task"] == "analyze" and logged["tier"] == "local"


def test_local_failure_falls_to_rules_not_claude(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local,mock")
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "openai")
    monkeypatch.setenv("SPEC1_LOCAL_MODEL", "Qwen-7B-openvino-gpu:2")
    with patch("requests.post", side_effect=ConnectionError("server down")), \
         patch("anthropic.Anthropic") as claude:
        client = FallbackLLMClient(task="analyze", log_path=tmp_path / "llm.jsonl")
        text = client.complete("prompt")
    claude.assert_not_called()
    assert client.get_active_tier() == "mock"
    assert json.loads(text)["classification"]


def test_openai_backend_requires_model_name(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local")
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "openai")
    with patch("requests.post") as post:
        client = FallbackLLMClient(task="analyze", log_path=tmp_path / "llm.jsonl")
        client.complete("prompt")
    post.assert_not_called()
    assert client.get_active_tier() == "mock"


def test_verifier_runs_under_analyze_task(monkeypatch):
    from spec1_core.investigation import verifier

    seen = {}

    class Spy:
        def __init__(self, *a, **kw):
            seen["task"] = kw.get("task")

        def complete(self, prompt, system=""):
            return json.dumps({"classification": "MONITOR", "confidence": 0.5,
                               "evidence": ["e"]})

    monkeypatch.setattr("spec1_core.llm.fallback_client.FallbackLLMClient", Spy)
    inv = MagicMock()
    inv.investigation_id = "inv-1"
    inv.hypothesis = "h"
    inv.queries = []
    inv.sources_to_check = []
    inv.analyst_leads = []
    try:
        verifier.verify_investigation(inv)
    except Exception:
        pass
    assert seen.get("task") == "analyze"


def test_think_block_is_stripped_from_local_answers(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local")
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "openai")
    monkeypatch.setenv("SPEC1_LOCAL_MODEL", "/models/Qwen3.5-4B.gguf")
    body = '<think>\nlet me reason about this\n</think>\n{"classification": "MONITOR", "confidence": 0.4}'
    with patch("requests.post", return_value=_openai_response(body)) as post:
        client = FallbackLLMClient(task="analyze", log_path=tmp_path / "llm.jsonl")
        text = client.complete("prompt")
    assert json.loads(text)["classification"] == "MONITOR"
    assert client.get_active_tier() == "local"
    assert post.call_args.kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_think_block_is_stripped_on_ollama_backend_too(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local")
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    reply = '<think>\nreasoning\n</think>\n{"classification": "ESCALATE", "confidence": 0.7}'
    with patch("spec1_core.llm.ollama_manager.is_running", return_value=True), \
         patch("spec1_core.llm.ollama_manager.ensure_model", return_value=True), \
         patch("spec1_core.llm.ollama_manager.chat", return_value=reply):
        client = FallbackLLMClient(task="analyze", log_path=tmp_path / "llm.jsonl")
        text = client.complete("prompt")
    assert json.loads(text)["classification"] == "ESCALATE"
    assert client.get_active_tier() == "ollama"


def test_strip_reasoning_handles_unterminated_block():
    from spec1_core.llm.fallback_client import strip_reasoning
    assert strip_reasoning("<think>never closed") == ""
    assert strip_reasoning('{"a": 1}') == '{"a": 1}'

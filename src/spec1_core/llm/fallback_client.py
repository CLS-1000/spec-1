# @domain:   machine
# @module:   llm_fallback_client
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Task-routed LLM client with per-task fallback.

Backends:
  claude — Anthropic Claude (ANTHROPIC_API_KEY)
  local  — a local model: Ollama, or any OpenAI-compatible server such as
           Foundry Local / AI Toolkit, vLLM, LM Studio (SPEC1_LOCAL_BACKEND)
  mock   — rule-based Tier 3 (tier3_rules); always available

Each task has a route — the ordered list of backends it may use. Routes come
from SPEC1_LLM_ROUTE_<TASK> (e.g. SPEC1_LLM_ROUTE_ANALYZE=local,mock), then
SPEC1_LLM_ROUTE, else the historical order claude,local,mock (local,mock in
SPEC1_DEV_MODE). The cycle's analysis can run on a local model while Claude is
reserved for writing.

All public methods are exception-safe — they never propagate errors to callers.
Every LLM call is logged to logs/llm_fallback.jsonl with its task and backend.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from spec1_core.llm import ollama_manager, tier3_rules
from spec1_labels import VERIF_CORROBORATED, VERIF_CONFLICTED, THREAT_HIGH, THREAT_MEDIUM, THREAT_LOW

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OPENAI_COMPAT_URL = "http://localhost:5272/v1"   # Foundry Local / AI Toolkit
_VALID_BACKENDS = ("claude", "local", "mock")
_BACKEND_ALIASES = {"ollama": "local", "rules": "mock", "tier3": "mock"}


def resolve_route(task: str = "default", dev_mode: bool = False) -> list[str]:
    """Return the ordered backends for *task*. ``mock`` is always last."""
    env = os.environ.get
    raw = env(f"SPEC1_LLM_ROUTE_{task.upper()}") or env("SPEC1_LLM_ROUTE")
    if raw:
        route = []
        for part in raw.split(","):
            name = _BACKEND_ALIASES.get(part.strip().lower(), part.strip().lower())
            if name in _VALID_BACKENDS and name not in route:
                route.append(name)
    else:
        route = ["local"] if dev_mode else ["claude", "local"]
    route = [b for b in route if b != "mock"] + ["mock"]
    return route
_DEFAULT_LOG_PATH = Path("logs/llm_fallback.jsonl")

# Rough cost per 1 K tokens (Haiku pricing)
_INPUT_COST_PER_1K = 0.00025
_OUTPUT_COST_PER_1K = 0.00125

# Maps SPEC-1 verifier classifications → coarse verdict
_CLASSIFICATION_TO_VERDICT: dict[str, str] = {
    VERIF_CORROBORATED: "THREAT",
    "ESCALATE": "THREAT",
    "INVESTIGATE": "ANOMALY",
    VERIF_CONFLICTED: "ANOMALY",
    "MONITOR": "CLEAR",
    "ARCHIVE": "CLEAR",
}

# ── Client ────────────────────────────────────────────────────────────────────


class FallbackLLMClient:
    """Unified LLM client with automatic tier fallback."""

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_url: str | None = None,
        log_path: Path | None = None,
        task: str = "default",
    ) -> None:
        env = os.environ.get
        self._task = task
        self._ollama_url = ollama_url or env("SPEC1_OLLAMA_URL", _DEFAULT_OLLAMA_URL)
        self._ollama_model = (
            ollama_model
            or env("OLLAMA_MODEL")
            or ollama_manager.preferred_model()
        )
        self._log_path = log_path or Path(env("SPEC1_LLM_LOG_PATH", str(_DEFAULT_LOG_PATH)))
        self._dev_mode = env("SPEC1_DEV_MODE", "").lower() == "true"
        self._active_tier = "claude"
        self._session_cost: float = 0.0
        self._session_id = uuid.uuid4().hex[:8]
        self._local_backend = env("SPEC1_LOCAL_BACKEND", "ollama").lower()
        self._local_url = env("SPEC1_LOCAL_URL", _DEFAULT_OPENAI_COMPAT_URL)
        self._local_model = env("SPEC1_LOCAL_MODEL", "")
        self._route = resolve_route(task, self._dev_mode)

        if self._dev_mode:
            print(
                "[DEV MODE] Bypassing Tier 1 (Claude) -> "
                "Short-circuiting directly to Tier 2 (Local Ollama)"
            )
            logger.info("SPEC1_DEV_MODE active — Tier 1 skipped")

    # ── Public API ────────────────────────────────────────────────────────────

    def complete(self, prompt: str, system: str = "") -> str:
        """Return raw LLM text from the first backend on this task's route. Never raises."""
        t0 = time.monotonic()
        for backend in self._route:
            if backend == "mock":
                break
            try:
                text = self._backend_complete(backend, prompt, system)
                self._record(self._tier_name(backend), t0, len(prompt + text), success=True)
                return text
            except Exception as exc:
                logger.warning("%s backend failed for task %s: %s", backend, self._task, exc)

        text = tier3_rules.to_verifier_json(prompt)
        self._active_tier = "mock"
        self._record("mock", t0, len(text), success=True)
        return text

    def analyze(self, prompt: str, system: str = "") -> dict[str, Any]:
        """Run analysis and return the standard output dict. Never raises."""
        t0 = time.monotonic()
        for backend in self._route:
            if backend == "mock":
                break
            try:
                raw = self._backend_complete(backend, prompt, system)
                tier = self._tier_name(backend)
                result = self._parse_to_spec(raw, tier)
                latency_ms = int((time.monotonic() - t0) * 1000)
                cost = self._estimate_cost(prompt, raw) if backend == "claude" else 0.0
                self._session_cost += cost
                result.update(latency_ms=latency_ms, cost_estimate_usd=cost)
                self._record(tier, t0, len(prompt + raw), success=True)
                return result
            except Exception as exc:
                logger.warning("%s backend failed for task %s: %s", backend, self._task, exc)

        # Tier 3
        verdict, confidence, analysis = tier3_rules.score(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)
        self._active_tier = "mock"
        self._record("mock", t0, len(prompt), success=True)
        return {
            "verdict": verdict,
            "confidence": confidence,
            "analysis": analysis,
            "tier_used": "mock",
            "latency_ms": latency_ms,
            "cost_estimate_usd": 0.0,
        }

    def investigate(self, query: str) -> dict[str, Any]:
        """Investigate a query and return structured dict."""
        system = (
            "You are an OSINT analyst. Identify key entities, assess threat level, "
            "and return JSON only: "
            '{"entities": [], "threat_level": "' + THREAT_HIGH + '"|"' + THREAT_MEDIUM + '"|"' + THREAT_LOW + '", '
            '"assessment": str, "confidence": float}'
        )
        return self.analyze(prompt=query, system=system)

    def get_route(self) -> list[str]:
        """Return this task's ordered backends."""
        return list(self._route)

    def get_active_tier(self) -> str:
        """Return the tier used for the most recent call."""
        return self._active_tier

    def get_cost_estimate(self) -> float:
        """Return cumulative USD spent this session (Claude only)."""
        return round(self._session_cost, 6)

    # ── Tier implementations ──────────────────────────────────────────────────

    def _claude_complete(self, prompt: str, system: str) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip().lstrip("﻿")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        import anthropic  # lazy — optional dependency

        model = os.environ.get("SPEC1_LLM_CLAUDE_MODEL", _DEFAULT_CLAUDE_MODEL)
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self._active_tier = "claude"
        return message.content[0].text.strip()

    def _tier_name(self, backend: str) -> str:
        """Name logged/returned for a backend (keeps 'ollama' for the Ollama local)."""
        if backend == "local":
            return "ollama" if self._local_backend == "ollama" else "local"
        return backend

    def _backend_complete(self, backend: str, prompt: str, system: str) -> str:
        if backend == "claude":
            return self._claude_complete(prompt, system)
        if backend == "local":
            if self._local_backend == "ollama":
                return self._ollama_complete(prompt, system)
            return self._openai_compat_complete(prompt, system)
        raise ValueError(f"unknown backend {backend!r}")

    def _openai_compat_complete(self, prompt: str, system: str) -> str:
        """Call an OpenAI-compatible /chat/completions server (Foundry Local, vLLM, LM Studio)."""
        import requests  # already a core dependency

        if not self._local_model:
            raise RuntimeError("SPEC1_LOCAL_MODEL not set for the OpenAI-compatible backend")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        headers = {}
        key = os.environ.get("SPEC1_LOCAL_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.post(
            self._local_url.rstrip("/") + "/chat/completions",
            json={"model": self._local_model, "messages": messages,
                  "temperature": 0.0, "max_tokens": 512},
            headers=headers,
            timeout=float(os.environ.get("SPEC1_LOCAL_TIMEOUT", "120")),
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        self._active_tier = "local"
        return (text or "").strip()

    def _ollama_complete(self, prompt: str, system: str) -> str:
        auto_spawn = os.environ.get("OLLAMA_AUTO_SPAWN", "true").lower() != "false"

        if not ollama_manager.is_running(self._ollama_url):
            if not auto_spawn:
                raise RuntimeError("Ollama not running and auto-spawn disabled")
            logger.info("Spawning Ollama…")
            if not ollama_manager.spawn(self._ollama_url):
                raise RuntimeError("Failed to start Ollama")

        ollama_manager.ensure_model(self._ollama_model, self._ollama_url)
        text = ollama_manager.chat(
            prompt, system, self._ollama_model, self._ollama_url
        )
        self._active_tier = "ollama"
        return text

    # ── Parsing helpers ───────────────────────────────────────────────────────

    def _parse_to_spec(self, raw: str, tier: str) -> dict[str, Any]:
        """Convert raw LLM text to the standard spec output dict."""
        text = self._strip_fences(raw)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                data = json.loads(m.group())
            else:
                raise

        classification = data.get("classification", "")
        verdict_raw = data.get("verdict", "")

        if classification in _CLASSIFICATION_TO_VERDICT:
            verdict = _CLASSIFICATION_TO_VERDICT[classification]
        elif verdict_raw in ("THREAT", "ANOMALY", "CLEAR"):
            verdict = verdict_raw
        else:
            verdict = "ANOMALY"

        confidence = float(data.get("confidence", 0.3))
        confidence = round(min(max(confidence, 0.0), 1.0), 4)

        analysis = (
            data.get("reasoning")
            or data.get("analysis")
            or data.get("assessment")
            or ""
        )

        return {
            "verdict": verdict,
            "confidence": confidence,
            "analysis": str(analysis),
            "tier_used": tier,
            "latency_ms": 0,
            "cost_estimate_usd": 0.0,
        }

    @staticmethod
    def _strip_fences(text: str) -> str:
        if not text.startswith("```"):
            return text
        parts = text.split("```")
        inner = parts[1] if len(parts) >= 2 else text
        if "\n" in inner:
            tag, body = inner.split("\n", 1)
            return body.strip() if tag.strip().isalpha() else inner.strip()
        return inner.strip()

    # ── Cost & logging ────────────────────────────────────────────────────────

    def _estimate_cost(self, prompt: str, response: str) -> float:
        tokens_in = len(prompt) / 4
        tokens_out = len(response) / 4
        return round(
            tokens_in / 1000 * _INPUT_COST_PER_1K
            + tokens_out / 1000 * _OUTPUT_COST_PER_1K,
            6,
        )

    def _record(self, tier: str, t0: float, char_count: int, *, success: bool) -> None:
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session": self._session_id,
                "task": self._task,
                "tier": tier,
                "latency_ms": latency_ms,
                "char_count": char_count,
                "success": success,
            })
            with self._log_path.open("a") as fh:
                fh.write(entry + "\n")
        except Exception:
            pass  # logging must never crash the pipeline

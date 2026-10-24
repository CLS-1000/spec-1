"""Three-tier LLM fallback client.

Tier 1: Anthropic Claude (ANTHROPIC_API_KEY)
Tier 2: Local Ollama + Llama3 / Mistral
Tier 3: Rule-based mock (tier3_rules)

All public methods are exception-safe — they never propagate errors to callers.
Every LLM call is logged to logs/llm_fallback.jsonl.
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

from spec1_engine.llm import ollama_manager, tier3_rules
from spec1_labels import VERIF_CORROBORATED, VERIF_CONFLICTED, THREAT_HIGH, THREAT_MEDIUM, THREAT_LOW

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
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
    ) -> None:
        env = os.environ.get
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

        if self._dev_mode:
            print(
                "[DEV MODE] Bypassing Tier 1 (Claude) -> "
                "Short-circuiting directly to Tier 2 (Local Ollama)"
            )
            logger.info("SPEC1_DEV_MODE active — Tier 1 skipped")

    # ── Public API ────────────────────────────────────────────────────────────

    def complete(self, prompt: str, system: str = "") -> str:
        """Return raw LLM text from the first available tier. Never raises."""
        t0 = time.monotonic()

        # Tier 1 (skipped in dev mode)
        if not self._dev_mode:
            try:
                text = self._claude_complete(prompt, system)
                self._record("claude", t0, len(prompt + text), success=True)
                return text
            except Exception as exc:
                logger.warning("Tier 1 (Claude) failed: %s — trying Ollama", exc)

        # Tier 2
        try:
            text = self._ollama_complete(prompt, system)
            self._record("ollama", t0, len(prompt + text), success=True)
            return text
        except Exception as exc:
            logger.warning("Tier 2 (Ollama) failed: %s — using rule-based Tier 3", exc)

        # Tier 3
        text = tier3_rules.to_verifier_json(prompt)
        self._active_tier = "mock"
        self._record("mock", t0, len(text), success=True)
        return text

    def analyze(self, prompt: str, system: str = "") -> dict[str, Any]:
        """Run analysis and return the standard output dict. Never raises."""
        t0 = time.monotonic()

        # Tier 1 (skipped in dev mode)
        if not self._dev_mode:
            try:
                raw = self._claude_complete(prompt, system)
                result = self._parse_to_spec(raw, "claude")
                latency_ms = int((time.monotonic() - t0) * 1000)
                cost = self._estimate_cost(prompt, raw)
                self._session_cost += cost
                result.update(latency_ms=latency_ms, cost_estimate_usd=cost)
                self._record("claude", t0, len(prompt + raw), success=True)
                return result
            except Exception as exc:
                logger.warning("Tier 1 (Claude) failed: %s — trying Ollama", exc)

        # Tier 2
        try:
            raw = self._ollama_complete(prompt, system)
            result = self._parse_to_spec(raw, "ollama")
            latency_ms = int((time.monotonic() - t0) * 1000)
            result.update(latency_ms=latency_ms, cost_estimate_usd=0.0)
            self._record("ollama", t0, len(prompt + raw), success=True)
            return result
        except Exception as exc:
            logger.warning("Tier 2 (Ollama) failed: %s — using rule-based Tier 3", exc)

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
                "tier": tier,
                "latency_ms": latency_ms,
                "char_count": char_count,
                "success": success,
            })
            with self._log_path.open("a") as fh:
                fh.write(entry + "\n")
        except Exception:
            pass  # logging must never crash the pipeline

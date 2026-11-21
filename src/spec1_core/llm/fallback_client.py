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
  rules  — deterministic Tier 3 rules (tier3_rules); always available.
           "mock" and "tier3" are accepted as old names for it.

Each task has a route — the ordered list of backends it may use. Routes come
from SPEC1_LLM_ROUTE_<TASK> (e.g. SPEC1_LLM_ROUTE_ANALYZE=local,rules), then
SPEC1_LLM_ROUTE, else the historical order claude,local,rules (local,rules in
SPEC1_DEV_MODE). The cycle's analysis can run on a local model while Claude is
reserved for writing.

All public methods are exception-safe — they never propagate errors to callers.
Every backend attempt is logged to logs/llm_fallback.jsonl with its task and
backend: a model that fails or times out gets its own ``success: false`` entry,
and the rules fallback that follows gets a separate ``tier: "rules"`` entry.
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

import httpx
from pydantic import ValidationError

from spec1_core.intelligence.store import anchor_to_home, spec1_home
from spec1_core.llm import model_config, ollama_manager, tier3_rules
from spec1_core.schemas.models import Tier3TriageVerdict
from spec1_labels import (
    LLM_TIER_RULES,
    THREAT_HIGH,
    THREAT_LOW,
    THREAT_MEDIUM,
    VERIF_CONFLICTED,
    VERIF_CORROBORATED,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_DEFAULT_CLAUDE_MODEL = model_config.DEFAULT_CLAUDE_MODEL
_DEFAULT_OLLAMA_URL = model_config.DEFAULT_OLLAMA_URL
_DEFAULT_OPENAI_COMPAT_URL = "http://localhost:5272/v1"   # Foundry Local / AI Toolkit
_VALID_BACKENDS = ("claude", "local", LLM_TIER_RULES)
_BACKEND_ALIASES = {"ollama": "local", "mock": LLM_TIER_RULES, "tier3": LLM_TIER_RULES}


def strip_reasoning(text: str) -> str:
    """Remove <think>…</think> blocks that reasoning models (Qwen3, DeepSeek-R1) emit."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    if "<think>" in text:  # unterminated block: nothing usable follows
        text = ""
    return text.strip()


def resolve_route(task: str = "default", dev_mode: bool = False) -> list[str]:
    """Return the ordered backends for *task*. ``rules`` is always last."""
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
    route = [b for b in route if b != LLM_TIER_RULES] + [LLM_TIER_RULES]
    return route


_DEFAULT_LOG_PATH = Path(model_config.DEFAULT_LLM_LOG_RELPATH)

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
        cfg = model_config.load(spec1_home())
        self._cfg = cfg
        self._task = task
        self._ollama_url = (
            model_config.normalize_ollama_url(ollama_url)
            if ollama_url
            else cfg.ollama_url
        )
        self._ollama_model = ollama_model or cfg.ollama_model
        if not model_config.is_model_allowed(self._ollama_model):
            raise ValueError(f"Model {self._ollama_model!r} is excluded by licensing policy.")

        if log_path is not None:
            self._log_path = log_path
        elif cfg.llm_log_path != (cfg.home / model_config.DEFAULT_LLM_LOG_RELPATH):
            self._log_path = anchor_to_home(str(cfg.llm_log_path))
        else:
            self._log_path = anchor_to_home(str(_DEFAULT_LOG_PATH))

        self._dev_mode = env("SPEC1_DEV_MODE", "").lower() == "true"
        self._active_tier = "claude"
        self._active_model: str | None = None
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
        for backend in self._route:
            if backend == LLM_TIER_RULES:
                break
            t0 = time.monotonic()
            try:
                text = self._backend_complete(backend, prompt, system)
                self._active_tier = self._tier_name(backend)
                self._active_model = self._model_name(backend)
                self._record(
                    self._active_tier,
                    t0,
                    len(prompt + text),
                    success=True,
                    model=self._active_model,
                )
                return text
            except Exception as exc:
                self._record_failure(backend, t0, exc)

        t0 = time.monotonic()
        text = tier3_rules.to_verifier_json(prompt)
        self._active_tier = LLM_TIER_RULES
        self._active_model = None
        self._record(LLM_TIER_RULES, t0, len(text), success=True, model=None)
        return text

    def analyze(self, prompt: str, system: str = "") -> dict[str, Any]:
        """Run analysis and return the standard output dict. Never raises."""
        for backend in self._route:
            if backend == LLM_TIER_RULES:
                break
            t0 = time.monotonic()
            try:
                raw = self._backend_complete(backend, prompt, system)
                tier = self._tier_name(backend)
                result = self._parse_to_spec(raw, tier)
                self._active_tier = tier
                self._active_model = self._model_name(backend)
                latency_ms = int((time.monotonic() - t0) * 1000)
                cost = self._estimate_cost(prompt, raw) if backend == "claude" else 0.0
                self._session_cost += cost
                result.update(latency_ms=latency_ms, cost_estimate_usd=cost)
                self._record(
                    tier,
                    t0,
                    len(prompt + raw),
                    success=True,
                    model=self._active_model,
                )
                return result
            except Exception as exc:
                self._record_failure(backend, t0, exc)

        # Tier 3 rules
        t0 = time.monotonic()
        verdict, confidence, analysis = tier3_rules.score(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)
        self._active_tier = LLM_TIER_RULES
        self._active_model = None
        self._record(LLM_TIER_RULES, t0, len(prompt), success=True, model=None)
        return {
            "verdict": verdict,
            "confidence": confidence,
            "analysis": analysis,
            "tier_used": LLM_TIER_RULES,
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

    def get_active_model(self) -> str | None:
        """Return the model that answered the most recent call (None for rules)."""
        return self._active_model

    @property
    def session_id(self) -> str:
        """This client's id, as written in each logs/llm_fallback.jsonl entry."""
        return self._session_id

    def get_cost_estimate(self) -> float:
        """Return cumulative USD spent this session (Claude only)."""
        return round(self._session_cost, 6)

    # ── Tier implementations ──────────────────────────────────────────────────

    def _claude_complete(self, prompt: str, system: str) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip().lstrip("\ufeff")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        import anthropic  # lazy — optional dependency

        model = self._model_name("claude") or model_config.DEFAULT_CLAUDE_MODEL
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self._active_tier = "claude"
        return message.content[0].text.strip()

    def _model_name(self, backend: str) -> str | None:
        """The model a backend uses, as configured for this client."""
        if backend == "claude":
            return model_config.load(spec1_home()).claude_model
        if backend == "local":
            return self._ollama_model if self._local_backend == "ollama" else (self._local_model or None)
        return None

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
                raw = self._ollama_complete(prompt, system)
            else:
                raw = self._openai_compat_complete(prompt, system)
            return strip_reasoning(raw)
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
            json={
                "model": self._local_model,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 512,
                # Ask reasoning models to answer directly (ignored by others).
                "chat_template_kwargs": {"enable_thinking": False},
            },
            headers=headers,
            timeout=self._cfg.call_timeout,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"] or ""
        self._active_tier = "local"
        return text.strip()

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
            prompt,
            system,
            self._ollama_model,
            self._ollama_url,
            timeout=self._cfg.call_timeout,
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

    def _record_failure(self, backend: str, t0: float, exc: Exception) -> None:
        """Log one failed backend attempt as its own success:false entry."""
        logger.warning("%s backend failed for task %s: %s", backend, self._task, exc)
        self._record(
            self._tier_name(backend),
            t0,
            0,
            success=False,
            error=_error_kind(exc),
            model=self._model_name(backend),
        )

    def _record(
        self,
        tier: str,
        t0: float,
        char_count: int,
        *,
        success: bool,
        error: str | None = None,
        model: str | None = None,
    ) -> None:
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            fields: dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session": self._session_id,
                "task": self._task,
                "tier": tier,
                "model": model,
                "latency_ms": latency_ms,
                "char_count": char_count,
                "success": success,
            }
            if error is not None:
                fields["error"] = error
            entry = json.dumps(fields)
            with self._log_path.open("a") as fh:
                fh.write(entry + "\n")
        except Exception:
            pass  # logging must never crash the pipeline


def _error_kind(exc: Exception) -> str:
    """'timeout' for any timeout, else the exception's class name."""
    import socket

    if isinstance(exc, (TimeoutError, socket.timeout, httpx.TimeoutException)):
        return "timeout"
    reason = getattr(exc, "reason", None)  # urllib.error.URLError wraps the timeout
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    try:
        import requests

        if isinstance(exc, requests.Timeout):
            return "timeout"
    except ImportError:
        pass
    return type(exc).__name__


# ── Local Tier-3 client (Ollama via model_config) ─────────────────────────────

OLLAMA_BASE_URL = model_config.DEFAULT_OLLAMA_URL
DEFAULT_MODEL = model_config.DEFAULT_OLLAMA_MODEL
CHAT_MODEL = model_config.DEFAULT_OLLAMA_CHAT_MODEL
CHAT_TIMEOUT = model_config.DEFAULT_CHAT_TIMEOUT


class LocalTier3Client:
    """Direct Ollama client: schema-constrained triage verdicts and free-form chat.

    After each ``verify_triage_record`` call, ``last_tier`` says which backend
    produced the answer: ``"ollama"`` when the model answered, ``"rules"`` when
    it did not (unreachable, timed out, oversized prompt, or invalid output).
    """

    def __init__(self, base_url: str | None = None, model: str | None = None):
        cfg = model_config.load(spec1_home())
        self._cfg = cfg
        self.base_url = model_config.normalize_ollama_url(base_url or cfg.ollama_url)
        self.model = model or cfg.ollama_model
        if not model_config.is_model_allowed(self.model):
            raise ValueError(f"Model {self.model!r} is excluded by licensing policy.")
        self.client = httpx.Client(base_url=self.base_url, timeout=cfg.call_timeout)
        self.session_id = uuid.uuid4().hex[:8]
        self.last_tier: str = LLM_TIER_RULES

    def verify_triage_record(self, record: dict[str, Any]) -> Tier3TriageVerdict | None:
        """Runs candidate triage record through Ollama with constrained JSON schema."""
        system_prompt = (
            "You are an OSINT intelligence verifier. Output strictly valid JSON matching "
            "the requested schema. Do not add markdown backticks or preamble."
        )
        prompt = (
            f"You are the SPEC-1 Tier-3 verification engine. Audit this candidate triage record:\n"
            f"Record ID: {record.get('record_id')}\n"
            f"Source: {record.get('source')}\n"
            f"Composite Score: {record.get('composite', 0.0)}\n"
            f"Payload: {json.dumps(record.get('raw', {}))[:1500]}\n\n"
            f"SPEC-1 4-Gate Rubric: credibility=0.30, volume=0.20, velocity=0.20, novelty=0.30; "
            f"ingest composite floor=0.40; Tier-3 verification threshold=0.70.\n"
            f"Assess the record on its content. Flag the payload if it is corrupt, spam or test noise."
        )

        self.last_tier = LLM_TIER_RULES
        try:
            num_ctx = ollama_manager.resolve_num_ctx(
                len(system_prompt) + len(prompt),
                self.model,
                self.base_url,
            )
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "format": Tier3TriageVerdict.model_json_schema(),
                "options": {
                    "temperature": 0.0,
                    "top_p": 0.2,
                    "num_ctx": num_ctx,
                },
                "stream": False,
            }
            res = self.client.post("/api/chat", json=payload)
            res.raise_for_status()
            body = res.json()
            ollama_manager.verify_not_truncated(body, num_ctx, self.model)
            raw_content = body["message"]["content"]
            verdict = Tier3TriageVerdict.model_validate_json(raw_content)
            self.last_tier = "ollama"
            logger.info("Model verified record %s (model=%s)", verdict.record_id, self.model)
            return verdict

        except model_config.PromptTooLong:
            return None
        except httpx.ConnectError:
            logger.error("Ollama service unreachable on %s. Ensure 'ollama serve' is active.", self.base_url)
            return None
        except httpx.TimeoutException:
            logger.error(
                "Ollama request timed out after %ss. Check system resource allocation.",
                self.client.timeout.read,
            )
            return None
        except (ValidationError, KeyError, json.JSONDecodeError) as e:
            logger.error("Schema validation failed for record %s: %s", record.get("record_id"), e)
            return None

    def chat(self, user_prompt: str, system_prompt: str = "", temperature: float = 0.2) -> str:
        """Free-form markdown chat against the local Ollama model (brief writer).

        Refuses oversized prompts with :class:`PromptTooLong` and raises on
        connection, HTTP, truncation, or empty-response failures.
        """
        cfg = model_config.load(spec1_home())
        chat_model = cfg.ollama_chat_model
        if not model_config.is_model_allowed(chat_model):
            raise ValueError(f"Chat model {chat_model!r} is excluded by licensing policy.")

        num_ctx = ollama_manager.resolve_num_ctx(
            len(system_prompt) + len(user_prompt),
            chat_model,
            self.base_url,
            response_reserve=2048,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": chat_model,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
            "stream": False,
        }
        res = self.client.post("/api/chat", json=payload, timeout=cfg.chat_timeout)
        res.raise_for_status()
        body = res.json()
        ollama_manager.verify_not_truncated(body, num_ctx, chat_model)
        text = strip_reasoning(body.get("message", {}).get("content", ""))
        if not text:
            raise RuntimeError(f"Ollama returned an empty chat response ({chat_model})")
        return text

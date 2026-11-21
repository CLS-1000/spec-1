# @domain:   machine
# @module:   llm_ollama_manager
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Tier 2: Ollama lifecycle manager (spawn, health-check, model pull, chat)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from spec1_core.intelligence.store import spec1_home
from spec1_core.llm import model_config
from spec1_core.llm.model_config import PromptTooLong

logger = logging.getLogger(__name__)

DEFAULT_URL = model_config.DEFAULT_OLLAMA_URL
# Seconds one Ollama call may take before it counts as failed. A CPU-bound
# local model can need well over two minutes on a long article.
DEFAULT_TIMEOUT = model_config.DEFAULT_CALL_TIMEOUT

MODEL_HIGH_RAM = "llama3"
MODEL_LOW_RAM = model_config.DEFAULT_OLLAMA_CHAT_MODEL
RAM_THRESHOLD_GB = 8.0

_CONTEXT_LENGTH_CACHE: dict[tuple[str, str], int | None] = {}


def _settings() -> model_config.ModelSettings:
    return model_config.load(spec1_home())


def call_timeout() -> float:
    """Per-call Ollama timeout from model_config (.env > env > 180s default)."""
    return _settings().call_timeout


def preferred_model() -> str:
    """Effective local Ollama model from model_config (.env > env > default)."""
    return _settings().ollama_model


# ── Context length & num_ctx sizing ───────────────────────────────────────────

def model_context_length(model: str, base_url: str | None = None) -> int | None:
    """Return the model's advertised context_length via /api/show, or None."""
    url = model_config.normalize_ollama_url(base_url or _settings().ollama_url)
    key = (url, model)
    if key in _CONTEXT_LENGTH_CACHE:
        return _CONTEXT_LENGTH_CACHE[key]

    ctx_len: int | None = None
    try:
        req = urllib.request.Request(
            f"{url}/api/show",
            data=json.dumps({"name": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        model_info = data.get("model_info") or {}
        if isinstance(model_info, dict):
            for info_key, info_val in model_info.items():
                if info_key.endswith(".context_length") and isinstance(info_val, int) and info_val > 0:
                    ctx_len = info_val
                    break
        if ctx_len is None:
            params = str(data.get("parameters") or "")
            for line in params.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "num_ctx":
                    try:
                        parsed = int(parts[1])
                        if parsed > 0:
                            ctx_len = parsed
                            break
                    except ValueError:
                        pass
    except Exception:
        ctx_len = None

    _CONTEXT_LENGTH_CACHE[key] = ctx_len
    return ctx_len


def resolve_num_ctx(
    prompt_chars: int,
    model: str,
    base_url: str | None = None,
    *,
    response_reserve: int = 1024,
    max_ctx: int | None = None,
) -> int:
    """Compute explicit num_ctx for *prompt_chars* or log and raise PromptTooLong."""
    cfg = _settings()
    effective_max = cfg.max_ctx if max_ctx is None else max_ctx
    model_ctx = model_context_length(model, base_url or cfg.ollama_url)
    try:
        return model_config.compute_num_ctx(
            prompt_chars,
            response_reserve=response_reserve,
            max_ctx=effective_max,
            model_context_length=model_ctx,
        )
    except PromptTooLong as exc:
        logger.error("Refusing oversized Ollama prompt for model=%s: %s", model, exc)
        raise


def verify_not_truncated(data: dict[str, Any], num_ctx: int, model: str) -> None:
    """Raise PromptTooLong if Ollama reports prompt_eval_count >= num_ctx."""
    eval_count = data.get("prompt_eval_count")
    if isinstance(eval_count, int) and eval_count >= num_ctx:
        msg = (
            f"Ollama truncated prompt for model={model}: "
            f"prompt_eval_count={eval_count} >= num_ctx={num_ctx}"
        )
        logger.error(msg)
        raise PromptTooLong(msg)


# ── Health check ──────────────────────────────────────────────────────────────

def is_running(base_url: str | None = None) -> bool:
    """Return True if Ollama API is reachable."""
    url = model_config.normalize_ollama_url(base_url or _settings().ollama_url)
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Spawn ─────────────────────────────────────────────────────────────────────

def spawn(base_url: str | None = None, wait_seconds: int = 10) -> bool:
    """Attempt to start the Ollama server. Returns True on success."""
    url = model_config.normalize_ollama_url(base_url or _settings().ollama_url)
    if is_running(url):
        return True

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        logger.warning("ollama binary not found in PATH — Tier 2 unavailable")
        return False

    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        logger.error("Failed to spawn Ollama: %s", exc)
        return False

    for _ in range(wait_seconds):
        time.sleep(1)
        if is_running(url):
            logger.info("Ollama server started")
            return True

    logger.warning("Ollama did not respond within %ds", wait_seconds)
    return False


# ── Model management ──────────────────────────────────────────────────────────

def model_available(model: str, base_url: str | None = None) -> bool:
    """Return True if the model is already downloaded."""
    url = model_config.normalize_ollama_url(base_url or _settings().ollama_url)
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
            return any(model in m.get("name", "") for m in data.get("models", []))
    except Exception:
        return False


def pull_model(model: str, timeout: int = 600) -> bool:
    """Pull a model via the Ollama CLI. Returns True on success."""
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return False
    try:
        logger.info("Pulling Ollama model %s (may take several minutes)…", model)
        result = subprocess.run(
            [ollama_bin, "pull", model],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Model %s ready", model)
            return True
        logger.error("ollama pull %s failed: %s", model, result.stderr[:200])
        return False
    except Exception as exc:
        logger.error("Failed to pull model %s: %s", model, exc)
        return False


def ensure_model(model: str, base_url: str | None = None) -> bool:
    """Pull the model if not already present. Returns True when ready."""
    url = model_config.normalize_ollama_url(base_url or _settings().ollama_url)
    if model_available(model, url):
        return True
    return pull_model(model)


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(
    prompt: str,
    system: str,
    model: str,
    base_url: str | None = None,
    timeout: float | None = None,
) -> str:
    """Send a chat message to Ollama with explicit RAM-capped num_ctx.

    Refuses oversized prompts with :class:`PromptTooLong` rather than silently
    truncating. *timeout* defaults to :func:`call_timeout` (180s).
    """
    if not model_config.is_model_allowed(model):
        raise ValueError(f"Model {model!r} is excluded by licensing policy.")

    cfg = _settings()
    url = model_config.normalize_ollama_url(base_url or cfg.ollama_url)
    timeout = cfg.call_timeout if timeout is None else timeout
    num_ctx = resolve_num_ctx(len(system) + len(prompt), model, url)

    payload = json.dumps({
        "model": model,
        "stream": False,
        "think": False,  # reasoning models answer directly; ignored by others
        "options": {"num_ctx": num_ctx},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
        verify_not_truncated(data, num_ctx, model)
        return data["message"]["content"]

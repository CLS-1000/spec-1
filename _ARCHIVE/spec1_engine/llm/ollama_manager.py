"""Tier 2: Ollama lifecycle manager (spawn, health-check, model pull, chat)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:11434"
MODEL_HIGH_RAM = "llama3"
MODEL_LOW_RAM = "mistral"
RAM_THRESHOLD_GB = 8.0


# ── RAM detection ─────────────────────────────────────────────────────────────

def _available_ram_gb() -> float:
    try:
        import os
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
    except Exception:
        return RAM_THRESHOLD_GB  # assume sufficient


def preferred_model() -> str:
    return MODEL_HIGH_RAM if _available_ram_gb() >= RAM_THRESHOLD_GB else MODEL_LOW_RAM


# ── Health check ──────────────────────────────────────────────────────────────

def is_running(base_url: str = DEFAULT_URL) -> bool:
    """Return True if Ollama API is reachable."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Spawn ─────────────────────────────────────────────────────────────────────

def spawn(base_url: str = DEFAULT_URL, wait_seconds: int = 10) -> bool:
    """Attempt to start the Ollama server. Returns True on success."""
    if is_running(base_url):
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
        if is_running(base_url):
            logger.info("Ollama server started")
            return True

    logger.warning("Ollama did not respond within %ds", wait_seconds)
    return False


# ── Model management ──────────────────────────────────────────────────────────

def model_available(model: str, base_url: str = DEFAULT_URL) -> bool:
    """Return True if the model is already downloaded."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
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


def ensure_model(model: str, base_url: str = DEFAULT_URL) -> bool:
    """Pull the model if not already present. Returns True when ready."""
    if model_available(model, base_url):
        return True
    return pull_model(model)


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(
    prompt: str,
    system: str,
    model: str,
    base_url: str = DEFAULT_URL,
    timeout: int = 120,
) -> str:
    """Send a chat message to Ollama and return the response text."""
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
        return data["message"]["content"]

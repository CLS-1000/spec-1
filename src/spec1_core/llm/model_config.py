"""Shared stdlib-only LLM configuration, licensing, and context-window helpers.

Mirrored byte-for-byte between:
  - spec-1:   src/spec1_core/llm/model_config.py
  - newsroom: spec1_bridge/model_config.py

Precedence: <home>/.env > process os.environ > built-in defaults.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# ── Built-in Defaults ─────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL: Final[str] = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL: Final[str] = "llama3.2:triage"
DEFAULT_OLLAMA_CHAT_MODEL: Final[str] = "qwen2.5:3b"
DEFAULT_CALL_TIMEOUT: Final[float] = 180.0
DEFAULT_CHAT_TIMEOUT: Final[float] = 600.0  # brief writer only
DEFAULT_LLM_LOG_RELPATH: Final[str] = "logs/llm_fallback.jsonl"

# Verified current on platform.claude.com/docs/en/models/overview (2026-11-20).
# Note: No ANTHROPIC_API_KEY is configured today, so both Claude models are inactive.
DEFAULT_CLAUDE_MODEL: Final[str] = "claude-haiku-5-5"
DEFAULT_CLAUDE_WRITER_MODEL: Final[str] = "claude-sonnet-5-5"

DEFAULT_MIN_CTX: Final[int] = 4096
DEFAULT_MAX_CTX: Final[int] = 16384
CTX_STEP: Final[int] = 1024
DEFAULT_KV_BYTES_PER_TOKEN: Final[int] = 65536  # conservative upper bound (64 KiB/tok)
RAM_HEADROOM_FRACTION: Final[float] = 0.50      # reserve at least 50% of MemAvailable


# ── Model Licensing & Exclusions ──────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ModelLicense:
    model_prefix: str
    license_name: str
    commercial_use: bool
    note: str


MODEL_LICENSES: Final[tuple[ModelLicense, ...]] = (
    ModelLicense(
        model_prefix="llama3.2",
        license_name="Llama 3.2 Community License",
        commercial_use=True,
        note="Llama 3.2 Community License — commercial use: yes (subject to Meta MAU terms).",
    ),
    ModelLicense(
        model_prefix="llama3",
        license_name="Llama 3 Community License",
        commercial_use=True,
        note="Llama 3 Community License — commercial use: yes (subject to Meta MAU terms).",
    ),
    ModelLicense(
        model_prefix="mistral",
        license_name="Apache-2.0",
        commercial_use=True,
        note="Apache 2.0 License — commercial use: yes.",
    ),
    ModelLicense(
        model_prefix="qwen2.5",
        license_name="Qwen Research License",
        commercial_use=False,
        note="Qwen Research License (3B) — commercial use: no (non-commercial research only).",
    ),
    ModelLicense(
        model_prefix="claude-",
        license_name="Anthropic Commercial Terms",
        commercial_use=True,
        note="Anthropic Commercial API Terms — commercial use: yes (inactive without ANTHROPIC_API_KEY).",
    ),
)

# Unlicensed third-party fine-tunes / GGUF repacks explicitly excluded from use.
EXCLUDED_MODEL_PATTERNS: Final[tuple[str, ...]] = (
    "uncensored",
    "qwen3.5",
)


def describe_model_license(model: str) -> str:
    """Return the one-line license and commercial-use note for *model*."""
    lowered = model.strip().lower()
    for blocked in EXCLUDED_MODEL_PATTERNS:
        if blocked in lowered:
            return f"EXCLUDED ({model}): unlicensed/prohibited model family — commercial use: no."
    for entry in MODEL_LICENSES:
        if lowered.startswith(entry.model_prefix):
            return entry.note
    return f"Unverified license ({model}) — commercial use: no (verify before commercial use)."


def is_model_allowed(model: str) -> bool:
    """Return False if *model* matches an excluded unlicensed GGUF/fine-tune."""
    lowered = model.strip().lower()
    return not any(blocked in lowered for blocked in EXCLUDED_MODEL_PATTERNS)


# ── Context Window & Truncation Guard ─────────────────────────────────────────

class PromptTooLong(ValueError):
    """Raised when a prompt requires more context tokens than RAM or model limits allow."""


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: ceil(chars / 3)."""
    if not text:
        return 0
    return math.ceil(len(text) / 3)


def available_ram_bytes() -> int | None:
    """Read MemAvailable from /proc/meminfo in bytes, or None if unavailable."""
    meminfo = Path("/proc/meminfo")
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    except OSError:
        pass
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return int(pages * page_size)
    except (ValueError, OSError, AttributeError):
        pass
    return None


def compute_num_ctx(
    prompt_chars: int,
    *,
    response_reserve: int = 1024,
    min_ctx: int = DEFAULT_MIN_CTX,
    max_ctx: int = DEFAULT_MAX_CTX,
    model_context_length: int | None = None,
    available_bytes: int | None = None,
    kv_bytes_per_token: int = DEFAULT_KV_BYTES_PER_TOKEN,
) -> int:
    """Calculate explicit num_ctx for a call, capped by config, model limit, and RAM.

    Raises :class:`PromptTooLong` if the required context exceeds the effective cap.
    """
    prompt_tokens = math.ceil(max(0, prompt_chars) / 3)
    needed = prompt_tokens + max(0, response_reserve)
    rounded = max(min_ctx, math.ceil(needed / CTX_STEP) * CTX_STEP)

    effective_cap = max_ctx
    if model_context_length is not None and model_context_length > 0:
        effective_cap = min(effective_cap, model_context_length)

    if available_bytes is None:
        available_bytes = available_ram_bytes()
    if available_bytes is not None and available_bytes > 0 and kv_bytes_per_token > 0:
        usable_bytes = int(available_bytes * RAM_HEADROOM_FRACTION)
        ram_cap_tokens = max(min_ctx, (usable_bytes // kv_bytes_per_token // CTX_STEP) * CTX_STEP)
        effective_cap = min(effective_cap, ram_cap_tokens)

    if needed > effective_cap:
        raise PromptTooLong(
            f"Prompt requires ~{needed} tokens ({prompt_chars} chars + {response_reserve} reserve), "
            f"exceeding effective num_ctx cap of {effective_cap} tokens"
        )
    return min(rounded, effective_cap)


# ── .env Parsing & Normalization ──────────────────────────────────────────────

def parse_dotenv(dotenv_path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from *dotenv_path* without mutating os.environ."""
    if not dotenv_path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        raw_text = dotenv_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s: %s", dotenv_path, exc)
        return {}

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def normalize_ollama_url(raw: str) -> str:
    """Normalize host:port or full URLs (including legacy /api/* endpoints) to base URL."""
    url = raw.strip().rstrip("/")
    if not url:
        return DEFAULT_OLLAMA_URL
    if "://" not in url:
        url = f"http://{url}"
    for suffix in ("/api/chat", "/api/generate", "/api/tags", "/api/show"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


def _pick(
    keys: tuple[str, ...],
    dotenv_vals: dict[str, str],
    env_vals: dict[str, str],
    default: str,
) -> tuple[str, str]:
    """Return (value, source) checking .env first, then process env, then default."""
    for key in keys:
        val = dotenv_vals.get(key, "").strip()
        if val:
            return val, "dotenv"
    for key in keys:
        val = env_vals.get(key, "").strip()
        if val:
            return val, "env"
    return default, "default"


def _parse_positive_float(raw: str, default: float, label: str) -> float:
    try:
        val = float(raw)
        if val > 0:
            return val
    except ValueError:
        pass
    logger.warning("Invalid %s=%r; using default %ss", label, raw, default)
    return default


def _parse_positive_int(raw: str, default: int, label: str) -> int:
    try:
        val = int(raw)
        if val > 0:
            return val
    except ValueError:
        pass
    logger.warning("Invalid %s=%r; using default %s", label, raw, default)
    return default


# ── Loaded Settings Object ────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ModelSettings:
    home: Path
    ollama_url: str
    ollama_url_source: str
    ollama_model: str
    ollama_model_source: str
    ollama_chat_model: str
    ollama_chat_model_source: str
    call_timeout: float
    chat_timeout: float
    claude_model: str
    claude_model_source: str
    claude_writer_model: str
    claude_writer_model_source: str
    anthropic_api_key_present: bool
    max_ctx: int
    llm_log_path: Path

    def format_cycle_summary(self) -> str:
        """One-line summary logged at the start of each cycle."""
        claude_state = "active" if self.anthropic_api_key_present else "inactive (no ANTHROPIC_API_KEY)"
        return (
            f"LLM config: ollama_model={self.ollama_model} (source={self.ollama_model_source}, "
            f"{describe_model_license(self.ollama_model)}) | "
            f"chat_model={self.ollama_chat_model} (source={self.ollama_chat_model_source}) | "
            f"ollama_url={self.ollama_url} (source={self.ollama_url_source}) | "
            f"timeouts={self.call_timeout:.0f}s/{self.chat_timeout:.0f}s | "
            f"claude={self.claude_model}/{self.claude_writer_model} [{claude_state}]"
        )


def load(home: Path | str, environ: dict[str, str] | None = None) -> ModelSettings:
    """Load model settings anchored to *home* with precedence .env > env > default."""
    home_path = Path(home).expanduser().resolve()
    dotenv_vals = parse_dotenv(home_path / ".env")
    env_vals = dict(os.environ) if environ is None else dict(environ)

    # Warn if OLLAMA_HOST and SPEC1_OLLAMA_URL disagree in the same scope
    for scope_name, mapping in ((".env", dotenv_vals), ("process env", env_vals)):
        raw_host = mapping.get("OLLAMA_HOST", "").strip()
        raw_spec1 = mapping.get("SPEC1_OLLAMA_URL", "").strip()
        if raw_host and raw_spec1:
            norm_host = normalize_ollama_url(raw_host)
            norm_spec1 = normalize_ollama_url(raw_spec1)
            if norm_host != norm_spec1:
                logger.warning(
                    "OLLAMA_HOST (%s -> %s) disagrees with SPEC1_OLLAMA_URL (%s -> %s) in %s; "
                    "preferring SPEC1_OLLAMA_URL",
                    raw_host,
                    norm_host,
                    raw_spec1,
                    norm_spec1,
                    scope_name,
                )

    raw_url, url_source = _pick(
        ("SPEC1_OLLAMA_URL", "OLLAMA_HOST", "OLLAMA_CHAT_URL"),
        dotenv_vals,
        env_vals,
        DEFAULT_OLLAMA_URL,
    )
    ollama_url = normalize_ollama_url(raw_url)

    ollama_model, model_source = _pick(
        ("OLLAMA_MODEL",),
        dotenv_vals,
        env_vals,
        DEFAULT_OLLAMA_MODEL,
    )
    if not is_model_allowed(ollama_model):
        raise ValueError(f"Configured model {ollama_model!r} is excluded by licensing policy.")

    ollama_chat_model, chat_model_source = _pick(
        ("SPEC1_OLLAMA_CHAT_MODEL", "OLLAMA_MODEL"),
        dotenv_vals,
        env_vals,
        DEFAULT_OLLAMA_CHAT_MODEL,
    )
    if not is_model_allowed(ollama_chat_model):
        raise ValueError(f"Configured chat model {ollama_chat_model!r} is excluded by licensing policy.")

    raw_call_timeout, _ = _pick(
        ("SPEC1_OLLAMA_TIMEOUT", "SPEC1_LOCAL_TIMEOUT"),
        dotenv_vals,
        env_vals,
        str(DEFAULT_CALL_TIMEOUT),
    )
    call_timeout = _parse_positive_float(raw_call_timeout, DEFAULT_CALL_TIMEOUT, "SPEC1_OLLAMA_TIMEOUT")

    raw_chat_timeout, _ = _pick(
        ("SPEC1_LOCAL_CHAT_TIMEOUT",),
        dotenv_vals,
        env_vals,
        str(DEFAULT_CHAT_TIMEOUT),
    )
    chat_timeout = _parse_positive_float(raw_chat_timeout, DEFAULT_CHAT_TIMEOUT, "SPEC1_LOCAL_CHAT_TIMEOUT")

    claude_model, claude_source = _pick(
        ("SPEC1_LLM_CLAUDE_MODEL",),
        dotenv_vals,
        env_vals,
        DEFAULT_CLAUDE_MODEL,
    )
    claude_writer_model, claude_writer_source = _pick(
        ("SPEC1_LLM_CLAUDE_WRITER_MODEL",),
        dotenv_vals,
        env_vals,
        DEFAULT_CLAUDE_WRITER_MODEL,
    )

    api_key, _ = _pick(("ANTHROPIC_API_KEY",), dotenv_vals, env_vals, "")
    clean_key = api_key.strip().lstrip("\ufeff")
    has_key = len(clean_key) >= 20 and not clean_key.endswith("...")

    raw_max_ctx, _ = _pick(
        ("SPEC1_OLLAMA_MAX_CTX",),
        dotenv_vals,
        env_vals,
        str(DEFAULT_MAX_CTX),
    )
    max_ctx = _parse_positive_int(raw_max_ctx, DEFAULT_MAX_CTX, "SPEC1_OLLAMA_MAX_CTX")

    raw_log_path, _ = _pick(
        ("SPEC1_LLM_LOG_PATH",),
        dotenv_vals,
        env_vals,
        DEFAULT_LLM_LOG_RELPATH,
    )
    log_candidate = Path(raw_log_path)
    llm_log_path = log_candidate if log_candidate.is_absolute() else (home_path / log_candidate)

    return ModelSettings(
        home=home_path,
        ollama_url=ollama_url,
        ollama_url_source=url_source,
        ollama_model=ollama_model,
        ollama_model_source=model_source,
        ollama_chat_model=ollama_chat_model,
        ollama_chat_model_source=chat_model_source,
        call_timeout=call_timeout,
        chat_timeout=chat_timeout,
        claude_model=claude_model,
        claude_model_source=claude_source,
        claude_writer_model=claude_writer_model,
        claude_writer_model_source=claude_writer_source,
        anthropic_api_key_present=has_key,
        max_ctx=max_ctx,
        llm_log_path=llm_log_path,
    )

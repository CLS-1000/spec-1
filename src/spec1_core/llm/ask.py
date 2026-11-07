# @domain:   machine
# @module:   llm_ask
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core.llm.fallback_client

"""Free-text questions to spec-1's local model (e.g. Qwen via Ollama).

Shared by the MCP server's ``ask_model`` tool and the API's ``/lab/ask``.
Local only unless SPEC1_LLM_ROUTE_ASK_MODEL says otherwise: it never reaches
Claude by default, and never answers with Tier 3 rules — when the local model
is down the result carries an error instead.
"""

from __future__ import annotations

import os
from typing import Any

from spec1_core.llm.fallback_client import FallbackLLMClient, resolve_route


def ask_local_model(prompt: str, system: str = "") -> dict[str, Any]:
    """Return ``{text, tier, model, route}``, or ``{error, tier, route}``. Never raises."""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "prompt is required"}

    route = (
        resolve_route("ask_model")
        if os.environ.get("SPEC1_LLM_ROUTE_ASK_MODEL")
        else ["local", "mock"]
    )
    client = FallbackLLMClient(task="ask_model", route=route)
    text = client.complete(prompt, (system or "").strip())
    tier = client.get_active_tier()
    if tier == "mock":
        return {"error": "local model unavailable", "tier": tier, "route": client.get_route()}
    return {
        "text": text,
        "tier": tier,
        "model": client.get_active_model(),
        "route": client.get_route(),
    }

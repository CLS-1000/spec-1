import requests
from spec1_engine.core.settings import USE_LOCAL_INFRASTRUCTURE, OLLAMA_ENDPOINT, MODEL_ROUTING

def generate_completion(prompt: str, module_type: str = "analyzer") -> str:
    """
    Routes prompts dynamically to external APIs or local Ollama instances
    based on the SPEC-1 configuration architecture.
    """
    # Look up which local model to use (defaulting to qwen3.5 if not specified)
    local_model = MODEL_ROUTING.get(module_type, "qwen3.5:latest")

    # ──── TRACK 1: LOCAL OLLAMA ROUTE ────────────────────────────────────────
    if USE_LOCAL_INFRASTRUCTURE:
        try:
            payload = {
                "model": local_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.2  # Low temperature for analytical consistency
            }

            # Hitting Ollama's native OpenAI-compatible chat endpoint
            response = requests.post(
                f"{OLLAMA_ENDPOINT}/chat/completions",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

        except Exception as e:
            # Fallback handling or log to audit logs if connection drops
            raise RuntimeError(f"SPEC-1 Local Engine Failure on port 11434: {e}")

    # ──── TRACK 2: EXTERNAL CLAUDE ROUTE ─────────────────────────────────────
    else:
        # Your existing Anthropic/Claude integration logic lives here
        # e.g., return anthropic_client.messages.create(...)
        pass

# =====================================================================
# LOCAL INFRASTRUCTURE ROUTING (OLLAMA INTEGRATION)
# =====================================================================
USE_LOCAL_INFRASTRUCTURE = True

OLLAMA_ENDPOINT = "http://127.0.0.1:11434/v1"

MODEL_ROUTING = {
    "parser": "mistral:latest",
    "scorer": "llama3:latest",
    "analyzer": "qwen3.5:latest"
}

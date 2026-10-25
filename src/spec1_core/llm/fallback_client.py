"""Local LLM fallback client using Ollama and Qwen 2.5."""
import json
import logging
from typing import Any, Dict, Optional
import httpx
from pydantic import ValidationError

from spec1_core.schemas.models import Tier3TriageVerdict

logger = logging.getLogger("spec1.llm.fallback")

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:3b"


class LocalTier3Client:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # 120s timeout to allow cold-start model weight allocation
        self.client = httpx.Client(base_url=self.base_url, timeout=120.0)

    def verify_triage_record(self, record: Dict[str, Any]) -> Optional[Tier3TriageVerdict]:
        """Runs candidate triage record through Qwen 2.5 with constrained JSON schema."""
        prompt = (
            f"You are the SPEC-1 Tier-3 verification engine. Audit this candidate triage record:\n"
            f"Record ID: {record.get('record_id')}\n"
            f"Source: {record.get('source')}\n"
            f"Composite Score: {record.get('composite', 0.0)}\n"
            f"Payload: {json.dumps(record.get('raw', {}))[:1500]}\n\n"
            f"Evaluate credibility, gate thresholds, and classify domain."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an OSINT intelligence verifier. Output strictly valid JSON matching "
                        "the requested schema. Do not add markdown backticks or preamble."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "format": Tier3TriageVerdict.model_json_schema(),
            "options": {
                "temperature": 0.0,
                "top_p": 0.2,
                "num_ctx": 4096,
            },
            "stream": False,
        }

        try:
            res = self.client.post("/api/chat", json=payload)
            res.raise_for_status()
            raw_content = res.json()["message"]["content"]
            verdict = Tier3TriageVerdict.model_validate_json(raw_content)
            logger.info("Successfully verified record %s -> tier=%s", verdict.record_id, verdict.analysis_tier)
            return verdict

        except httpx.ConnectError:
            logger.error("Ollama service unreachable on %s. Ensure 'ollama serve' is active.", self.base_url)
            return None
        except httpx.ReadTimeout:
            logger.error("Ollama request timed out after 120s. Check system resource allocation.")
            return None
        except (ValidationError, KeyError, json.JSONDecodeError) as e:
            logger.error("Schema validation failed for record %s: %s", record.get("record_id"), e)
            return None

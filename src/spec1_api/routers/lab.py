# @domain:   machine
# @module:   routers_lab
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core

"""Lab router — POST /lab/ask.

Backs the chatbot lab page (/lab): sends a question to spec-1's local model
(e.g. Qwen via Ollama) and returns its reply. Never calls Claude by default and
never answers with Tier 3 rules; 503 when the local model is unavailable.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from spec1_core.llm.ask import ask_local_model

router = APIRouter(prefix="/lab", tags=["lab"])


class LabAskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=60000, description="Question, with any chat history")
    system: str = Field("", max_length=20000, description="Optional system instruction")


@router.post("/ask")
def ask(body: LabAskRequest) -> dict:
    """Ask the local model. Sync so the blocking model call runs in the threadpool."""
    result = ask_local_model(body.prompt, body.system)
    if "error" in result:
        status = 422 if result["error"] == "prompt is required" else 503
        raise HTTPException(status_code=status, detail=result["error"])
    return result

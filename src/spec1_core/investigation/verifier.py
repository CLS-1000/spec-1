# @domain:   intelligence
# @module:   investigation_verifier
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Investigation Verifier.

Uses the three-tier LLM fallback client (Claude → Ollama → rule-based mock)
to assess the investigation hypothesis and produce an Outcome record.
Falls back gracefully on any error.
"""

from __future__ import annotations

import json
import logging
import uuid

from spec1_core.schemas.models import Investigation, Outcome
from spec1_labels import VERIF_CORROBORATED, VERIF_CONFLICTED

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
VALID_CLASSIFICATIONS = {
    VERIF_CORROBORATED, "ESCALATE", "INVESTIGATE", "MONITOR", VERIF_CONFLICTED, "ARCHIVE"
}

_SYSTEM_PROMPT = (
    "You are an intelligence analyst verifying a hypothesis. "
    "Respond with JSON only — no prose, no markdown fences. "
    'Schema: {"verified": bool, "confidence": float, "reasoning": str, '
    '"classification": "' + VERIF_CORROBORATED + '"|"ESCALATE"|"INVESTIGATE"|"MONITOR"|"' + VERIF_CONFLICTED + '"|"ARCHIVE"}'
)


ARTICLE_CHARS = 2000


def _build_user_prompt(investigation: Investigation, article: str = "", source: str = "") -> str:
    lines: list[str] = []
    if article.strip():
        text = " ".join(article.split())
        if len(text) > ARTICLE_CHARS:
            text = text[:ARTICLE_CHARS].rsplit(" ", 1)[0] + " …"
        lines += [f"Article ({source or 'unknown source'}):", text, ""]
    lines += [
        f"Hypothesis: {investigation.hypothesis}",
        "",
        "Queries raised:",
    ]
    for q in investigation.queries:
        lines.append(f"  - {q}")
    lines.append("")
    lines.append("Sources to check:")
    for s in investigation.sources_to_check:
        lines.append(f"  - {s}")
    if investigation.analyst_leads:
        lines.append("")
        lines.append("Analyst leads:")
        for a in investigation.analyst_leads:
            lines.append(f"  - {a}")
    lines.append("")
    lines.append(
        "Based on the article (if given), hypothesis, queries, and sources, assess credibility. "
        "Return JSON only."
    )
    return "\n".join(lines)


def _fallback_outcome() -> Outcome:
    return Outcome(
        outcome_id=f"out-{uuid.uuid4().hex[:12]}",
        classification="INVESTIGATE",
        confidence=0.0,
        evidence=["Fallback: API error or parse failure — manual review required."],
    )


def _extract_json(raw: str) -> dict:
    """Parse the reply as JSON, or the first {...} object in it.

    Small local models often add a sentence before or after the JSON.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == "{":
                    depth += 1
                elif raw[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(raw[start:i + 1])
                            if isinstance(data, dict):
                                return data
                        except json.JSONDecodeError:
                            pass
                        break
            start = raw.find("{", start + 1)
        raise


def verify_investigation(investigation: Investigation, article: str = "", source: str = "") -> Outcome:
    """Verify an investigation hypothesis via 3-tier LLM fallback. Never raises.

    ``article`` is the signal's cleaned text; without it the model sees only
    the templated hypothesis and can't do more than guess.
    """
    from spec1_core.llm.fallback_client import FallbackLLMClient

    try:
        llm = FallbackLLMClient(task="analyze")
        raw = llm.complete(
            prompt=_build_user_prompt(investigation, article, source),
            system=_SYSTEM_PROMPT,
        )
        # Strip markdown fences that some tiers may include.
        if raw.startswith("```"):
            parts = raw.split("```")
            inner = parts[1] if len(parts) >= 2 else raw
            if "\n" in inner:
                tag, body = inner.split("\n", 1)
                raw = body.strip() if tag.strip().isalpha() else inner.strip()
            else:
                raw = inner.strip()
    except Exception as exc:
        logger.error("LLM fallback chain error: %s", exc)
        return _fallback_outcome()

    try:
        data = _extract_json(raw)
        classification = data.get("classification", "INVESTIGATE")
        if classification not in VALID_CLASSIFICATIONS:
            classification = "INVESTIGATE"
        confidence = float(data.get("confidence", 0.0))
        confidence = round(min(max(confidence, 0.0), 1.0), 4)
        verified = bool(data.get("verified", False))
        reasoning = str(data.get("reasoning", ""))
        evidence = [
            f"LLM assessment: {reasoning}",
            f"Verified: {verified}",
            f"Confidence: {confidence}",
            f"Hypothesis: {investigation.hypothesis}",
        ]
        return Outcome(
            outcome_id=f"out-{uuid.uuid4().hex[:12]}",
            classification=classification,
            confidence=confidence,
            evidence=evidence,
        )
    except Exception as exc:
        logger.error("Failed to parse Claude response %r: %s", raw, exc)
        return _fallback_outcome()

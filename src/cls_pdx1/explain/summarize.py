# @domain:   citizens_source
# @module:   explain_summarize
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Plain-language summarisation via Claude Sonnet with neutrality retry.

Falls back to a rule-based template on API error — the pipeline never crashes
on LLM failure. Output always passes through the neutrality section gate before
being accepted.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from cls_pdx1.models import Bill
from cls_pdx1.neutrality.tone import tone_gate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You write plain-language summaries of local government legislation for Portland-area residents
who have no background in law or politics.

Rules you MUST follow:
1. Maximum 4 sentences.
2. Use only neutral verbs: said, stated, proposed, voted, noted.
3. Do not characterise intent or motive — report only what the document says.
4. Do not use: admitted, claimed, alleged, denied, slammed, revealed, exposed, accused.
5. End with: "Source: [institution name]."
6. If you cannot summarise neutrally, respond with exactly: CANNOT_SUMMARISE
"""


def _llm_summarize(text: str, context: str) -> Optional[str]:
    """Call Claude Sonnet. Returns None on any error."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{context}\n\n{text}"}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("LLM summarise failed: %s", exc)
        return None


def _rule_based_summary(bill: Bill) -> str:
    """Deterministic fallback when LLM is unavailable."""
    status_text = bill.status.name.replace("_", " ").title()
    sponsor_text = f" Sponsor: {bill.sponsor}." if bill.sponsor else ""
    tags_text = f" Topics: {', '.join(bill.tags)}." if bill.tags else ""
    return (
        f"{bill.external_id}: {bill.title} — currently {status_text}."
        f"{sponsor_text}{tags_text} "
        f"Source: {bill.jurisdiction.name.replace('_', ' ').title()}."
    )


def summarize_bill(bill: Bill, max_retries: int = 2) -> str:
    """Return a neutral plain-language summary of a bill.

    Tries the LLM up to max_retries times. Each attempt is validated through
    the tone gate. Falls back to rule-based summary on exhaustion or API error.
    """
    prompt_text = f"Bill: {bill.external_id} — {bill.title}\n\nFull text (if available): {bill.plain_summary or 'Not available.'}"

    for attempt in range(max_retries):
        result = _llm_summarize(prompt_text, f"Jurisdiction: {bill.jurisdiction.name}")
        if result is None:
            break
        if result == "CANNOT_SUMMARISE":
            break
        ok, _ = tone_gate(result)
        if ok:
            return result
        logger.debug("Tone gate failed on attempt %d, retrying", attempt + 1)

    return _rule_based_summary(bill)


def summarize_decision(title: str, body: str, institution: str, max_retries: int = 2) -> str:
    """Summarise a council vote or agency decision."""
    prompt_text = f"Decision: {title}\n\nDetails: {body}"

    for attempt in range(max_retries):
        result = _llm_summarize(prompt_text, f"Institution: {institution}")
        if result is None:
            break
        if result == "CANNOT_SUMMARISE":
            break
        ok, _ = tone_gate(result)
        if ok:
            return result
        logger.debug("Tone gate failed on attempt %d, retrying", attempt + 1)

    # Rule-based fallback
    return f"{title} — {institution} took action on this matter. Source: {institution}."

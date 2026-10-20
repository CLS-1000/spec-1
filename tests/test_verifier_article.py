"""The verifier must see the article, and survive a model that talks around its JSON."""

from __future__ import annotations

import json

from spec1_core.briefing.generator import _format_record
from spec1_core.investigation import verifier
from spec1_core.schemas.models import Investigation

INV = Investigation(
    investigation_id="inv-1", opportunity_id="opp-1",
    hypothesis="The reporting from Nk News concerning Kim may indicate a development.",
    queries=["q"], sources_to_check=["s"], analyst_leads=[],
)
ARTICLE = "Kim Yo Jong threatened to restart North Korean loudspeakers. " * 80


class _Spy:
    reply = json.dumps({"classification": "ESCALATE", "confidence": 0.8,
                        "verified": True, "reasoning": "Direct threat by a named official."})

    def __init__(self, *a, **k):
        _Spy.seen = None

    def complete(self, prompt, system=""):
        _Spy.seen = prompt
        return _Spy.reply


def test_article_reaches_the_model_and_is_capped(monkeypatch):
    monkeypatch.setattr("spec1_core.llm.fallback_client.FallbackLLMClient", _Spy)
    out = verifier.verify_investigation(INV, article=ARTICLE, source="nk_news")
    assert "Article (nk_news):" in _Spy.seen
    assert "loudspeakers" in _Spy.seen
    body = _Spy.seen.split("Article (nk_news):\n", 1)[1].split("\n", 1)[0]
    assert len(body) <= verifier.ARTICLE_CHARS + 2
    assert out.classification == "ESCALATE" and out.confidence == 0.8


def test_no_article_keeps_old_prompt(monkeypatch):
    monkeypatch.setattr("spec1_core.llm.fallback_client.FallbackLLMClient", _Spy)
    verifier.verify_investigation(INV)
    assert not _Spy.seen.startswith("Article")


def test_json_wrapped_in_prose_is_still_read(monkeypatch):
    class Chatty(_Spy):
        def complete(self, prompt, system=""):
            return ('Here is my assessment:\n{"classification": "MONITOR", "confidence": 0.62, '
                    '"verified": false, "reasoning": "Routine {not escalatory}."}\nHope this helps.')
    monkeypatch.setattr("spec1_core.llm.fallback_client.FallbackLLMClient", Chatty)
    out = verifier.verify_investigation(INV, article="x")
    assert out.classification == "MONITOR" and out.confidence == 0.62


def test_unparseable_reply_still_falls_back(monkeypatch):
    class Junk(_Spy):
        def complete(self, prompt, system=""):
            return "I cannot answer that."
    monkeypatch.setattr("spec1_core.llm.fallback_client.FallbackLLMClient", Junk)
    out = verifier.verify_investigation(INV, article="x")
    assert out.classification == "INVESTIGATE" and out.confidence == 0.0


def test_brief_prompt_carries_excerpt_and_reasoning():
    rec = {"signal_source": "nk_news", "pattern": "p", "confidence": 0.7,
           "signal_excerpt": "Kim Yo Jong threatened...", "llm_reasoning": "Named official, direct threat."}
    text = _format_record(rec)
    assert "Excerpt: Kim Yo Jong threatened..." in text
    assert "Model assessment: Named official, direct threat." in text
    assert "Excerpt" not in _format_record({"signal_source": "x", "pattern": "p"})

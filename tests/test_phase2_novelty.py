"""Regression tests for Phase 2 novelty gate word-boundary & Unicode normalization."""

from __future__ import annotations

from spec1_core.signal.gates import score_novelty as cosine_novelty
from spec1_core.signal.parser import normalize_text
from spec1_core.signal.scorer import _score_novelty


def test_novelty_ignores_substrings_in_ordinary_words() -> None:
    text = "The senator gave a special social media update on financial harmony"
    score, hits = _score_novelty(text, [])
    assert hits == 0
    assert score == 0.0


def test_novelty_matches_whole_terms_and_phrases() -> None:
    score_single, hits_single = _score_novelty("NATO summit convened in Brussels.", [])
    assert hits_single == 1
    assert score_single == 0.40

    score_phrase, hits_phrase = _score_novelty(
        "Analysts tracked ship-to-ship transfer activity near North Korea.", []
    )
    assert hits_phrase == 2
    assert score_phrase == 0.65


def test_normalize_text_folds_cyrillic_and_greek_homoglyphs() -> None:
    # Cyrillic 'А' (\u0410) in NАTO and Cyrillic 'С'/'І'/'А' in СІА
    spoofed = "N\u0410TO issued a joint statement with \u0421\u0406\u0410."
    assert normalize_text(spoofed) == "nato issued a joint statement with cia."

    score, hits = _score_novelty(spoofed, [])
    assert hits == 2
    assert score == 0.65


def test_gates_novelty_tokenizes_non_latin_text() -> None:
    s1 = "Министерство обороны провело учения на восточном полигоне сегодня утром"
    s2 = "Министерство обороны провело учения на восточном полигоне сегодня вечером"
    nov = cosine_novelty(s1, [s2])
    assert nov < 0.5

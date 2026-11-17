# @domain:   intelligence
# @module:   signal_parser
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core/config/calibration.py

"""Signal Parser — ported from cls_osint/parsers/news.py.

Cleans HTML and extracts keywords/entities from Signal text.
Produces ParsedSignal dataclass instances.
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from spec1_core.schemas.models import ParsedSignal, Signal

# Cyrillic & Greek visual homoglyphs -> ASCII Latin equivalents (applied after NFKC)
_CONFUSABLES_MAP: dict[int, str] = str.maketrans({
    # Cyrillic uppercase & lowercase lookalikes
    "\u0410": "A", "\u0430": "a",  # А а -> A a
    "\u0412": "B", "\u0432": "b",  # В в -> B b
    "\u0421": "C", "\u0441": "c",  # С с -> C c
    "\u0415": "E", "\u0435": "e",  # Е е -> E e
    "\u0401": "E", "\u0451": "e",  # Ё ё -> E e
    "\u041d": "H", "\u043d": "h",  # Н н -> H h
    "\u0406": "I", "\u0456": "i",  # І і -> I i
    "\u0408": "J", "\u0458": "j",  # Ј ј -> J j
    "\u041a": "K", "\u043a": "k",  # К к -> K k
    "\u041c": "M", "\u043c": "m",  # М м -> M m
    "\u041e": "O", "\u043e": "o",  # О о -> O o
    "\u0420": "P", "\u0440": "p",  # Р р -> P p
    "\u0405": "S", "\u0455": "s",  # Ѕ ѕ -> S s
    "\u0422": "T", "\u0442": "t",  # Т т -> T t
    "\u0423": "Y", "\u0443": "y",  # У у -> Y y
    "\u0425": "X", "\u0445": "x",  # Х х -> X x
    # Greek uppercase & lowercase lookalikes
    "\u0391": "A", "\u03b1": "a",  # Α α -> A a
    "\u0392": "B", "\u03b2": "b",  # Β β -> B b
    "\u0395": "E", "\u03b5": "e",  # Ε ε -> E e
    "\u0396": "Z", "\u03b6": "z",  # Ζ ζ -> Z z
    "\u0397": "H", "\u03b7": "h",  # Η η -> H h
    "\u0399": "I", "\u03b9": "i",  # Ι ι -> I i
    "\u039a": "K", "\u03ba": "k",  # Κ κ -> K k
    "\u039c": "M", "\u03bc": "m",  # Μ μ -> M m
    "\u039d": "N", "\u03bd": "n",  # Ν ν -> N n
    "\u039f": "O", "\u03bf": "o",  # Ο ο -> O o
    "\u03a1": "P", "\u03c1": "p",  # Ρ ρ -> P p
    "\u03a4": "T", "\u03c4": "t",  # Τ τ -> T t
    "\u03a5": "Y", "\u03c5": "y",  # Υ υ -> Y y
    "\u03a7": "X", "\u03c7": "x",  # Χ χ -> X x
})


def normalize_text(text: str) -> str:
    """Normalize text for gate evaluation: NFKC -> homoglyph fold -> casefold."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).translate(_CONFUSABLES_MAP).casefold()
    return re.sub(r"\s+", " ", folded).strip()

STOPWORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "has", "have", "had", "will", "would", "could", "should", "may", "might",
    "that", "this", "it", "its", "as", "into", "than", "then", "so", "if",
    "not", "also", "about", "their", "they", "them", "what", "when", "who",
    "which", "more", "said", "over", "after", "before", "been", "between",
    "his", "her", "him", "she", "he", "we", "our", "your", "you", "can",
    "all", "one", "two", "three", "four", "five", "just", "new", "year",
    "says", "like", "some", "there", "where", "most",
}

# Named-entity patterns: capitalized words of 3+ chars that aren't stopwords
ENTITY_PATTERN = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b")

MAX_KEYWORDS = 15
MAX_ENTITIES = 10
MAX_TEXT_LENGTH = 8000


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode entities using BeautifulSoup."""
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "lxml")
        return soup.get_text(separator=" ")
    except Exception:
        # Fallback to regex stripping
        return re.sub(r"<[^>]+>", "", text)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def _extract_keywords(text: str, max_kw: int = MAX_KEYWORDS) -> list[str]:
    """Extract unique non-stopword words of 4+ chars."""
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if word not in STOPWORDS and word not in seen:
            seen.add(word)
            keywords.append(word)
        if len(keywords) >= max_kw:
            break
    return keywords


def _extract_entities(text: str, max_ent: int = MAX_ENTITIES) -> list[str]:
    """Extract capitalized proper-noun phrases as named entities."""
    matches = ENTITY_PATTERN.findall(text)
    seen: set[str] = set()
    entities: list[str] = []
    for m in matches:
        if m.lower() not in STOPWORDS and m not in seen:
            seen.add(m)
            entities.append(m)
        if len(entities) >= max_ent:
            break
    return entities


def _detect_language(text: str) -> str:
    """Naively detect language (always 'en' for this implementation)."""
    return "en"


def parse_signal(signal: Signal) -> ParsedSignal:
    """Clean and extract structured data from a Signal."""
    raw_text = signal.text or ""
    cleaned = _normalize_whitespace(_clean_html(raw_text))
    cleaned = _truncate(cleaned, MAX_TEXT_LENGTH)

    keywords = _extract_keywords(cleaned)
    entities = _extract_entities(cleaned)
    language = _detect_language(cleaned)
    word_count = len(cleaned.split()) if cleaned else 0

    return ParsedSignal(
        signal_id=signal.signal_id,
        cleaned_text=cleaned,
        keywords=keywords,
        entities=entities,
        language=language,
        word_count=word_count,
    )


def parse_batch(signals: list[Signal]) -> dict:
    """Parse a list of signals, returning parsed and failed."""
    parsed: list[ParsedSignal] = []
    failed: list[dict] = []
    for sig in signals:
        try:
            ps = parse_signal(sig)
            parsed.append(ps)
        except Exception as exc:
            failed.append({"signal_id": sig.signal_id, "error": str(exc)})
    return {"parsed": parsed, "failed": failed}

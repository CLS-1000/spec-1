# @domain:   product
# @module:   triage
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain.schemas, spec1_labels

"""Layer 3: Fire Triage Engine.

The defining skill of an exited founder: knowing which fires to IGNORE.

First-time founders fight every fire. Exited founders know:
  - 80% of fires are cosmetic — they burn out on their own
  - Only existential fires deserve founder attention
  - The opportunity cost of fighting the wrong fire is higher than the fire itself
  - Reversibility is the key discriminator: irreversible + existential = ATTACK

Classification rules:
  IGNORE   — cosmetic, reversible, low founder leverage
  DELEGATE — real but not existential, someone else can handle it
  ATTACK   — existential, irreversible, requires founder uniquely

The algorithm is purely deterministic — keyword/heuristic based.
"""

from __future__ import annotations

import re

from spec1_labels import (
    FOUNDER_FIRE_IGNORE,
    FOUNDER_FIRE_DELEGATE,
    FOUNDER_FIRE_ATTACK,
)

from cls_founder_brain.schemas import FireClassification


# ── Existential keywords ──────────────────────────────────────────────────────
# Terms that bump existential_score when they appear in fire description

_EXISTENTIAL_TRIGGERS = {
    "lawsuit", "sued", "legal", "compliance", "regulation", "shutdown",
    "bankrupt", "runway", "cash", "burn", "layoff", "cofounder leaving",
    "key hire leaving", "data breach", "security", "customer churn",
    "losing biggest customer", "competitor acquired", "patent",
    "cease and desist", "fraud", "SEC", "audit", "server down",
    "production outage", "revenue declining", "zero revenue",
}

_COSMETIC_TRIGGERS = {
    "logo", "branding", "color scheme", "font", "office space", "perks",
    "team lunch", "swag", "blog post", "newsletter format", "meeting cadence",
    "documentation style", "code formatting", "PR template", "social media",
    "conference talk", "podcast appearance", "advisor intro", "networking",
}

_DELEGATE_TRIGGERS = {
    "bug fix", "customer support", "onboarding", "documentation",
    "monitoring", "reporting", "metrics dashboard", "hiring process",
    "interview scheduling", "expense reports", "vendor negotiations",
    "infrastructure upgrade", "dependency update", "test coverage",
}

# ── Irreversibility indicators ────────────────────────────────────────────────

_IRREVERSIBLE_TRIGGERS = {
    "contract signed", "public statement", "launched", "announced",
    "employee left", "customer churned", "funding round closed",
    "equity granted", "data deleted", "legal filing", "patent expired",
    "market window", "competitor shipped", "regulation effective",
}


def _keyword_score(text: str, keywords: set[str]) -> float:
    """Compute keyword overlap score (0.0–1.0).

    Multi-word keywords require ALL words to appear in the text.
    Single-word keywords match directly.
    """
    text_lower = text.lower()
    text_words = set(re.findall(r"[a-z][a-z0-9]+", text_lower))

    matches = 0
    for keyword in keywords:
        # Check exact phrase match first
        if keyword in text_lower:
            matches += 1
        else:
            # For multi-word keywords, ALL words must appear
            kw_terms = set(keyword.split())
            if len(kw_terms) == 1:
                # Single-word: direct word match
                if kw_terms & text_words:
                    matches += 1
            else:
                # Multi-word: require all terms present
                if kw_terms.issubset(text_words):
                    matches += 1

    if not keywords:
        return 0.0
    return min(1.0, matches / 2.0)  # 2+ keyword hits = max score


def _estimate_founder_leverage(description: str) -> float:
    """Estimate whether the founder uniquely adds value here.

    High leverage: vision calls, key customer relationships, fundraising,
    co-founder conversations, strategic pivots.
    Low leverage: anything an employee/contractor/tool can do.
    """
    high_leverage_terms = {
        "vision", "strategy", "pivot", "fundrais", "investor", "board",
        "cofounder", "co-founder", "partner", "key customer", "enterprise deal",
        "acquisition", "exit", "equity", "culture", "mission",
    }
    text_lower = description.lower()
    hits = sum(1 for term in high_leverage_terms if term in text_lower)
    return min(1.0, hits * 0.25)


def classify_fire(
    fire_id: str,
    description: str,
    additional_context: str = "",
) -> FireClassification:
    """Classify a single fire as IGNORE / DELEGATE / ATTACK.

    Purely deterministic — uses keyword scoring + heuristics.

    Args:
        fire_id: Unique identifier for this fire.
        description: What's happening / what the fire is.
        additional_context: Extra context (stage, runway, etc.).

    Returns:
        FireClassification with scores and classification.
    """
    full_text = f"{description} {additional_context}"

    existential = _keyword_score(full_text, _EXISTENTIAL_TRIGGERS)
    cosmetic = _keyword_score(full_text, _COSMETIC_TRIGGERS)
    delegatable = _keyword_score(full_text, _DELEGATE_TRIGGERS)
    irreversible = _keyword_score(full_text, _IRREVERSIBLE_TRIGGERS)
    founder_leverage = _estimate_founder_leverage(full_text)

    # Reversibility is inverse of irreversibility signal
    reversibility = max(0.0, 1.0 - irreversible)

    # Opportunity cost: high when cosmetic fires pull founder from existential work
    opportunity_cost = cosmetic * 0.7 + (1.0 - founder_leverage) * 0.3

    # ── Classification decision tree ──
    # The exited-founder algorithm:
    if existential >= 0.5 and reversibility <= 0.5:
        # Existential + irreversible = ATTACK (no choice)
        classification = FOUNDER_FIRE_ATTACK
        reasoning = (
            "Existential threat with irreversible consequences. "
            "This requires direct founder attention NOW. Drop everything else."
        )
        time_to_irreversible = "48h"
    elif existential >= 0.3 and founder_leverage >= 0.5:
        # Real problem + founder uniquely helpful = ATTACK (but lower urgency)
        classification = FOUNDER_FIRE_ATTACK
        reasoning = (
            "Significant threat where founder uniquely adds value. "
            "Address this, but don't panic — you have a few days."
        )
        time_to_irreversible = "7d"
    elif existential >= 0.5:
        # Existential but reversible and no special founder leverage — still ATTACK
        classification = FOUNDER_FIRE_ATTACK
        reasoning = (
            "Existential threat. Even though partially reversible, "
            "the severity demands immediate attention."
        )
        time_to_irreversible = "72h"
    elif cosmetic >= 0.3 and existential < 0.2:
        # Clearly cosmetic
        classification = FOUNDER_FIRE_IGNORE
        reasoning = (
            "Cosmetic fire. Will burn itself out. "
            "Spending founder attention here is the real cost."
        )
        time_to_irreversible = "never"
    elif delegatable >= 0.3 or (existential < 0.3 and founder_leverage < 0.5):
        # Either explicitly delegatable OR not worth founder time
        classification = FOUNDER_FIRE_DELEGATE
        reasoning = (
            "Real issue but doesn't require founder. "
            "Assign to team/contractor. Check back in 48h."
        )
        time_to_irreversible = "never"
    else:
        # Default: unclear fires get delegated (exited founders don't fight ambiguous fires)
        classification = FOUNDER_FIRE_DELEGATE
        reasoning = (
            "Ambiguous fire — not clearly existential. "
            "Default to delegate. Revisit if it escalates."
        )
        time_to_irreversible = "14d"

    return FireClassification(
        fire_id=fire_id,
        description=description,
        existential_score=round(existential, 3),
        reversibility=round(reversibility, 3),
        founder_leverage=round(founder_leverage, 3),
        opportunity_cost=round(opportunity_cost, 3),
        classification=classification,
        reasoning=reasoning,
        time_to_irreversible=time_to_irreversible,
    )


def triage_fires(fires: list[tuple[str, str]], context: str = "") -> list[FireClassification]:
    """Classify multiple fires at once.

    Args:
        fires: List of (fire_id, description) tuples.
        context: Shared context for all fires.

    Returns:
        List of FireClassification, sorted: ATTACK first, then DELEGATE, then IGNORE.
    """
    classifications = [classify_fire(fid, desc, context) for fid, desc in fires]

    # Sort: ATTACK > DELEGATE > IGNORE
    priority = {FOUNDER_FIRE_ATTACK: 0, FOUNDER_FIRE_DELEGATE: 1, FOUNDER_FIRE_IGNORE: 2}
    classifications.sort(key=lambda f: (priority.get(f.classification, 3), -f.existential_score))

    return classifications

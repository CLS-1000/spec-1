# @domain:   product
# @module:   patterns
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_labels

"""Founder Pattern Library — canonical failure/success archetypes.

This is the encoded wisdom. Each pattern represents a situation that
two-time exited founders recognize INSTANTLY because they've lived it.
First-time founders see these as ambiguous; exited founders see them as
deterministic signals.

Categories:
  FAILURE    — patterns that killed companies (or almost did)
  SUCCESS    — patterns that preceded breakout
  PIVOT      — inflection points where the right move was non-obvious
  EXIT_SIGNAL — patterns that indicate it's time to sell/exit

Every pattern has:
  - triggers: what signals activate this pattern
  - naive_response: what first-time founders typically do (wrong)
  - exited_response: what two-time exited founders do (right)
  - kill_timeline: how fast this kills you if you get it wrong
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spec1_labels import (
    FOUNDER_PATTERN_FAILURE,
    FOUNDER_PATTERN_SUCCESS,
    FOUNDER_PATTERN_PIVOT,
    FOUNDER_PATTERN_EXIT_SIGNAL,
)


@dataclass
class FounderPattern:
    """A canonical pattern from the exited-founder knowledge base."""

    pattern_id: str
    name: str
    category: str  # FAILURE | SUCCESS | PIVOT | EXIT_SIGNAL
    description: str
    triggers: list[str] = field(default_factory=list)
    naive_response: str = ""
    exited_response: str = ""
    kill_timeline: str = ""  # e.g. "2 weeks", "3 months", "slow bleed"
    frequency: str = "common"  # common | uncommon | rare

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "triggers": list(self.triggers),
            "naive_response": self.naive_response,
            "exited_response": self.exited_response,
            "kill_timeline": self.kill_timeline,
            "frequency": self.frequency,
        }


# ── THE PATTERN LIBRARY ───────────────────────────────────────────────────────
# Organized by what exited founders recognize that first-timers miss.


FAILURE_PATTERNS: list[FounderPattern] = [
    FounderPattern(
        pattern_id="premature_scaling",
        name="Premature Scaling",
        category=FOUNDER_PATTERN_FAILURE,
        description="Hiring/spending before product-market fit is proven by revenue, not vanity metrics.",
        triggers=[
            "team size growing faster than revenue",
            "hiring for roles that don't directly touch customers",
            "burn rate increasing without proportional revenue growth",
            "celebrating user signups instead of paying customers",
        ],
        naive_response="Keep hiring because 'we need to be ready for growth'",
        exited_response="Freeze hiring. Cut to survival burn. Prove PMF with revenue from 10 paying customers, not 10,000 free users.",
        kill_timeline="3-6 months (burn compounds)",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="founder_market_fit_drift",
        name="Founder-Market Fit Drift",
        category=FOUNDER_PATTERN_FAILURE,
        description="Founder pivots away from their unfair advantage into a market they don't deeply understand.",
        triggers=[
            "building features requested by non-ICP users",
            "founder spending less time with customers, more with product",
            "competitive pressure causing reactive pivots",
            "advisor influence overriding founder intuition",
        ],
        naive_response="Chase the bigger market because 'TAM is everything'",
        exited_response="Return to the edge case YOU understand better than anyone. The niche IS the moat.",
        kill_timeline="2-4 months (slow bleed of differentiation)",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="burn_rate_denial",
        name="Burn Rate Denial",
        category=FOUNDER_PATTERN_FAILURE,
        description="Treating runway as infinite because 'the next raise will come'. It won't.",
        triggers=[
            "runway under 6 months with no term sheet",
            "spending on nice-to-haves (office, perks, tools)",
            "founder not checking bank balance weekly",
            "default alive calculation shows dead but nobody talks about it",
        ],
        naive_response="Keep spending because cutting feels like admitting failure",
        exited_response="Cut to 18-month runway TODAY. Default alive is the only state. Everything else is denial.",
        kill_timeline="Direct: whatever runway remains",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="consensus_seeking",
        name="Consensus-Seeking Paralysis",
        category=FOUNDER_PATTERN_FAILURE,
        description="Waiting for everyone to agree before acting. In startups, consensus = too late.",
        triggers=[
            "decisions taking more than 48 hours",
            "multiple meetings about the same topic",
            "waiting for more data when data won't change the decision",
            "team polling instead of deciding",
        ],
        naive_response="Get buy-in from everyone before committing",
        exited_response="Decide in < 24h with 70% information. Reversible decisions need zero consensus. Irreversible ones need one night's sleep.",
        kill_timeline="Cumulative: death by 1000 delayed decisions",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="feature_therapy",
        name="Feature Therapy",
        category=FOUNDER_PATTERN_FAILURE,
        description="Building features to avoid the real problem (usually distribution or positioning).",
        triggers=[
            "roadmap growing while conversion stays flat",
            "building what's fun to build rather than what moves metrics",
            "competitor feature-matching instead of positioning",
            "engineering velocity high but growth flat",
        ],
        naive_response="Ship more features because 'once we have X, customers will come'",
        exited_response="Stop building. The problem is NOT features. It's positioning, distribution, or pricing. Fix that first.",
        kill_timeline="3-6 months (opportunity cost while building the wrong thing)",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="cofounder_misalignment",
        name="Co-Founder Misalignment",
        category=FOUNDER_PATTERN_FAILURE,
        description="Founders diverging on vision/commitment but avoiding the conversation.",
        triggers=[
            "one founder doing 80% of the work",
            "different answers to 'where is this in 3 years'",
            "passive-aggressive Slack messages",
            "avoiding 1:1 conversations about the hard stuff",
        ],
        naive_response="Hope it resolves itself. Avoid the conversation.",
        exited_response=(
            "Force the conversation THIS WEEK. Misalignment doesn't heal with time. "
            "It metastasizes. One of you needs to leave or recommit."
        ),
        kill_timeline="1-3 months (accelerates under stress)",
        frequency="common",
    ),
    FounderPattern(
        pattern_id="investor_capture",
        name="Investor Capture",
        category=FOUNDER_PATTERN_FAILURE,
        description="Optimizing for what investors want to see rather than what customers need.",
        triggers=[
            "building features for the next pitch deck",
            "metrics chosen because they look good, not because they matter",
            "spending time on investor updates instead of customer conversations",
            "board meetings driving product decisions",
        ],
        naive_response="Investors know best — they've seen hundreds of companies",
        exited_response=(
            "Investors see patterns; you see YOUR customer. Build for the customer. "
            "The metrics will follow. Never let a board meeting set your roadmap."
        ),
        kill_timeline="Slow: 6-12 months of drift",
        frequency="uncommon",
    ),
    FounderPattern(
        pattern_id="perfection_paralysis",
        name="Perfection Before Launch",
        category=FOUNDER_PATTERN_FAILURE,
        description="Polishing endlessly instead of shipping ugly and iterating with real users.",
        triggers=[
            "launch date pushed more than twice",
            "refactoring before first user",
            "designing for scale at 0 users",
            "competitor launched ugly thing and is getting traction",
        ],
        naive_response="We need it to be great before anyone sees it",
        exited_response="Ship TODAY. Embarrassingly early. The market will tell you what matters. Everything you're polishing is probably wrong.",
        kill_timeline="Weeks to months (market moves without you)",
        frequency="common",
    ),
]


SUCCESS_PATTERNS: list[FounderPattern] = [
    FounderPattern(
        pattern_id="pull_not_push",
        name="Pull > Push (Organic Demand)",
        category=FOUNDER_PATTERN_SUCCESS,
        description="Customers finding you and pulling the product from you — not you pushing it.",
        triggers=[
            "inbound > outbound inquiries",
            "customers asking for features you planned to build",
            "word of mouth driving signups",
            "customers angry when you're slow, not indifferent",
        ],
        naive_response="Keep pushing marketing harder",
        exited_response="DOUBLE DOWN. This is PMF. Kill everything else. Feed the pull. Remove all friction between demand and delivery.",
        kill_timeline="N/A (positive signal)",
        frequency="uncommon",
    ),
    FounderPattern(
        pattern_id="hair_on_fire",
        name="Hair-On-Fire Problem",
        category=FOUNDER_PATTERN_SUCCESS,
        description="Solving a problem so urgent that customers accept ugly solutions immediately.",
        triggers=[
            "customers paying before product is finished",
            "manual processes they're desperate to replace",
            "compliance deadlines forcing adoption",
            "cost of NOT solving > any reasonable price",
        ],
        naive_response="Build the polished version before selling",
        exited_response="Sell the manual version NOW. Charge immediately. Build automation with their money. Urgency = pricing power.",
        kill_timeline="N/A (positive signal)",
        frequency="uncommon",
    ),
    FounderPattern(
        pattern_id="asymmetric_insight",
        name="Asymmetric Insight",
        category=FOUNDER_PATTERN_SUCCESS,
        description="You know something the market doesn't yet. Your timing is early, not wrong.",
        triggers=[
            "smart people saying 'that won't work' but can't articulate why",
            "regulatory/tech shift creating new possibility",
            "you've lived the problem personally",
            "incumbents ignoring the niche you're in",
        ],
        naive_response="Doubt yourself because experts disagree",
        exited_response="Conviction time. If your insight is from lived experience + structural shift, the experts are wrong. Ship fast, prove it.",
        kill_timeline="N/A (window may close in 6-18 months)",
        frequency="rare",
    ),
]


PIVOT_PATTERNS: list[FounderPattern] = [
    FounderPattern(
        pattern_id="adjacent_goldmine",
        name="Adjacent Goldmine",
        category=FOUNDER_PATTERN_PIVOT,
        description="Users using your product for something you didn't intend — and paying for THAT.",
        triggers=[
            "unexpected use case driving most revenue",
            "feature requests from a segment you didn't target",
            "analytics showing unintended workflow is the sticky one",
            "churn high in target segment, low in accidental segment",
        ],
        naive_response="Ignore it — it's not our vision",
        exited_response="Follow the money. The market is smarter than your vision. Pivot to serve the segment that's PULLING.",
        kill_timeline="3-6 months of ignoring revenue signal",
        frequency="uncommon",
    ),
    FounderPattern(
        pattern_id="platform_shift",
        name="Platform Shift Window",
        category=FOUNDER_PATTERN_PIVOT,
        description="A new platform/regulation/technology creates a 12-18 month window. Miss it and you're locked out.",
        triggers=[
            "new API/platform in early access",
            "regulation creating compliance gap",
            "incumbent's architecture can't adapt quickly",
            "developer tools just became available",
        ],
        naive_response="Wait for the platform to mature",
        exited_response="Move NOW. First-mover in platform shifts wins. The jank is the moat — by the time it's easy, everyone's doing it.",
        kill_timeline="6-18 months (window closes)",
        frequency="uncommon",
    ),
]


EXIT_SIGNAL_PATTERNS: list[FounderPattern] = [
    FounderPattern(
        pattern_id="acquihire_interest",
        name="Acqui-Hire Interest",
        category=FOUNDER_PATTERN_EXIT_SIGNAL,
        description="Larger company interested in your team, not your product. Can be an exit or a trap.",
        triggers=[
            "recruiter outreach to your engineers accelerating",
            "corporate dev 'coffee chats' increasing",
            "your tech stack matches their gap",
            "they're building competing feature internally",
        ],
        naive_response="Ignore it — we're building something bigger",
        exited_response="Take the meeting. Know your BATNA. If your runway is < 12 months and PMF isn't proven, this IS the exit. Negotiate hard.",
        kill_timeline="Window: 2-4 months (they'll build or buy someone else)",
        frequency="uncommon",
    ),
    FounderPattern(
        pattern_id="diminishing_returns",
        name="Diminishing Returns on Effort",
        category=FOUNDER_PATTERN_EXIT_SIGNAL,
        description="Each unit of effort produces less result. The business works but won't scale YOU.",
        triggers=[
            "revenue growing but founder energy declining",
            "same problems recurring despite fixes",
            "market becoming commoditized",
            "you're optimizing, not creating",
        ],
        naive_response="Push harder — success requires grinding",
        exited_response=(
            "Recognize the ceiling. Sell, hire a CEO, or restructure. "
            "Your next venture will compound this one's lessons, not extend its grind."
        ),
        kill_timeline="Slow: 1-2 years of declining returns on founder time",
        frequency="uncommon",
    ),
]


# ── Combined registry ─────────────────────────────────────────────────────────

ALL_PATTERNS: list[FounderPattern] = (
    FAILURE_PATTERNS + SUCCESS_PATTERNS + PIVOT_PATTERNS + EXIT_SIGNAL_PATTERNS
)

PATTERN_INDEX: dict[str, FounderPattern] = {p.pattern_id: p for p in ALL_PATTERNS}


def get_pattern(pattern_id: str) -> FounderPattern | None:
    """Look up a pattern by ID."""
    return PATTERN_INDEX.get(pattern_id)


def get_patterns_by_category(category: str) -> list[FounderPattern]:
    """Return all patterns in a given category."""
    return [p for p in ALL_PATTERNS if p.category == category]

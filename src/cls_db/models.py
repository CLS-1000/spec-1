"""SQLite table schemas for cls_db.

Defines CREATE TABLE statements for all SPEC-1 entities.
"""

from __future__ import annotations

# DDL for each table
SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'rss',
    text TEXT,
    url TEXT,
    author TEXT,
    published_at TEXT,
    velocity REAL DEFAULT 0.0,
    engagement REAL DEFAULT 0.0,
    run_id TEXT,
    environment TEXT DEFAULT 'production',
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

INTEL_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS intel_records (
    record_id TEXT PRIMARY KEY,
    pattern TEXT,
    classification TEXT,
    confidence REAL DEFAULT 0.0,
    source_weight REAL DEFAULT 0.0,
    analyst_weight REAL DEFAULT 0.0,
    run_id TEXT,
    written_at TEXT
)
"""

OSINT_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS osint_records (
    record_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT,
    content TEXT,
    url TEXT,
    collected_at TEXT,
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

FARA_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS fara_records (
    record_id TEXT PRIMARY KEY,
    registrant TEXT NOT NULL,
    foreign_principal TEXT,
    country TEXT,
    activities TEXT DEFAULT '[]',
    filed_at TEXT,
    doc_url TEXT,
    registration_number TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

CONGRESS_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS congress_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT,
    bill_id TEXT,
    title TEXT,
    sponsor TEXT,
    chamber TEXT,
    status TEXT,
    date TEXT,
    summary TEXT,
    url TEXT,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

LEADS_DDL = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    priority TEXT,
    category TEXT,
    source_record_ids TEXT DEFAULT '[]',
    action_items TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.5,
    generated_at TEXT,
    expires_at TEXT,
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

BRIEFS_DDL = """
CREATE TABLE IF NOT EXISTS briefs (
    brief_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    headline TEXT,
    summary TEXT,
    sections TEXT DEFAULT '[]',
    sources TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.7,
    produced_at TEXT,
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

PSYOP_SCORES_DDL = """
CREATE TABLE IF NOT EXISTS psyop_scores (
    score_id TEXT PRIMARY KEY,
    text_hash TEXT,
    text_excerpt TEXT,
    patterns_matched TEXT DEFAULT '[]',
    pattern_names TEXT DEFAULT '[]',
    score REAL DEFAULT 0.0,
    classification TEXT,
    threat_categories TEXT DEFAULT '[]',
    scored_at TEXT,
    metadata TEXT DEFAULT '{}',
    written_at TEXT
)
"""

VERDICTS_DDL = """
CREATE TABLE IF NOT EXISTS verdicts (
    verdict_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reviewer TEXT DEFAULT 'anonymous',
    reviewed_at TEXT,
    notes TEXT DEFAULT '',
    written_at TEXT
)
"""

VERDICTS_RECORD_ID_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_verdicts_record_id ON verdicts(record_id)"
)

POLITICAL_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS political_signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id        TEXT    UNIQUE NOT NULL,
    node_id          TEXT    NOT NULL,
    run_id           TEXT    NOT NULL,
    headline         TEXT    NOT NULL,
    summary          TEXT    NOT NULL,
    source_url       TEXT    NOT NULL,
    source_domain    TEXT    NOT NULL,
    published_at     TEXT    NOT NULL,
    retrieved_at     TEXT    NOT NULL,
    gate_status      TEXT    NOT NULL,
    gate_credibility REAL    NOT NULL,
    gate_volume      REAL    NOT NULL,
    gate_velocity    REAL    NOT NULL,
    gate_novelty     REAL    NOT NULL,
    signal_age_hours REAL    NOT NULL,
    freshness_label  TEXT    NOT NULL,
    analyst_voice    TEXT,
    conflict_score   REAL,
    tags             TEXT    DEFAULT '[]'
)
"""

# Ordered list of all DDL statements (for migration runner)
ALL_DDL: list[tuple[str, str]] = [
    ("signals", SIGNALS_DDL),
    ("intel_records", INTEL_RECORDS_DDL),
    ("osint_records", OSINT_RECORDS_DDL),
    ("fara_records", FARA_RECORDS_DDL),
    ("congress_records", CONGRESS_RECORDS_DDL),
    ("leads", LEADS_DDL),
    ("briefs", BRIEFS_DDL),
    ("psyop_scores", PSYOP_SCORES_DDL),
    ("verdicts", VERDICTS_DDL),
    ("political_signals", POLITICAL_SIGNALS_DDL),
]

# Auxiliary DDL — indexes and other idempotent statements run after table creation.
AUX_DDL: list[str] = [
    VERDICTS_RECORD_ID_INDEX_DDL,
    "CREATE INDEX IF NOT EXISTS idx_ps_node_id ON political_signals (node_id)",
    "CREATE INDEX IF NOT EXISTS idx_ps_gate_status ON political_signals (gate_status)",
    "CREATE INDEX IF NOT EXISTS idx_ps_published_at ON political_signals (published_at)",
    "CREATE INDEX IF NOT EXISTS idx_ps_node_gate_pub ON political_signals (node_id, gate_status, published_at)",
]

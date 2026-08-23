# SPEC-1 Public Weekly Intelligence Brief

## Overview

The **Public Weekly Intelligence Brief** (`cls_weekly_brief`) is a new publication surface that aggregates 7 days of intelligence records into a public-facing weekly report suitable for external distribution.

Unlike the daily `WorldBrief` (which uses topic-based clustering), the weekly brief:
- **Distinguishes evidence tiers**: Separates VERIFIED facts from INFERRED analysis from SPECULATION
- **Links all claims to sources**: Each evidence item includes source record IDs, timestamps, and confidence
- **Transparent methodology**: Includes a published disclaimer explaining classification rules
- **Evidence-focused structure**: Organizes by intelligence category (MILITARY, CYBER, GEOPOLITICAL, FARA, PSYOP, etc.)
- **Suitable for publication**: No unsupported claims; clear attribution and provenance

## Architecture

### Module: `cls_weekly_brief`

```
src/cls_weekly_brief/
├── __init__.py           # Module exports
├── schemas.py            # PublicWeeklyBrief, EvidenceTier, EvidenceItem, WeeklySection
├── producer.py           # produce_weekly_brief() — 7-day aggregation + classification
├── formatter.py          # to_markdown(), to_json_summary(), to_full_json()
└── store.py              # WeeklyBriefStore — JSONL append-only persistence
```

### Data Models

#### `EvidenceTier` (Enum)

Three-tier evidence classification:

- **VERIFIED** — Corroborated across ≥2 credible sources, confidence ≥ 0.8
- **INFERRED** — Analysis from credible signals, confidence 0.65–0.79
- **SPECULATION** — Preliminary hypothesis, requires validation (confidence < 0.65)

#### `EvidenceItem`

Single piece of evidence with:
- `content` — the claim or observation
- `tier` — EvidenceTier classification
- `source_ids` — IntelligenceRecord IDs backing this item
- `confidence` — confidence score (0.0–1.0)
- `published_at` — UTC timestamp of the source
- `source_url` — URL to original source (if available)
- `analyst_notes` — classification rationale

#### `WeeklySection`

Themed section (e.g., "Military Intelligence", "Cyber Intelligence") containing:
- `verified_items` — list of EvidenceItem (VERIFIED tier)
- `inferred_items` — list of EvidenceItem (INFERRED tier)
- `speculation_items` — list of EvidenceItem (SPECULATION tier)

#### `PublicWeeklyBrief`

Complete weekly brief with:
- `week_id` — ISO week "YYYY-W##"
- `week_start` / `week_end` — date range (ISO format)
- `executive_summary` — one-paragraph overview
- `methodology_note` — transparency disclaimer
- `sections` — list of WeeklySection
- `records_analyzed` — total signals processed
- `verified_count` / `inferred_count` / `speculation_count` — evidence tallies

## API Routes

All routes are under `/api/v1/weekly-brief`:

### `GET /api/v1/weekly-brief/latest`

Return the most recently produced weekly brief (summary view).

**Response:**
```json
{
  "brief_id": "pwb_abc123def456",
  "week_id": "2026-W34",
  "week_start": "2026-08-17",
  "week_end": "2026-08-24",
  "records_analyzed": 42,
  "verified_count": 12,
  "inferred_count": 18,
  "speculation_count": 12,
  "produced_at": "2026-08-24T23:00:00Z"
}
```

### `GET /api/v1/weekly-brief/history`

List weekly briefs in reverse chronological order (default: last 10 weeks).

**Query Parameters:**
- `limit` — max results (1–52, default 10)

**Response:**
```json
{
  "total": 52,
  "items": [
    { /* summary objects */ }
  ]
}
```

### `GET /api/v1/weekly-brief/{week_id}`

Return complete brief for a specific ISO week (e.g., `2026-W34`).

**Response:**
```json
{
  "brief_id": "pwb_abc123def456",
  "week_id": "2026-W34",
  "week_start": "2026-08-17",
  "week_end": "2026-08-24",
  "executive_summary": "...",
  "methodology_note": "...",
  "sections": [
    {
      "title": "Military Intelligence",
      "category": "MILITARY",
      "verified_items": [
        {
          "content": "Military deployment in region X",
          "tier": "VERIFIED",
          "confidence": 0.95,
          "source_ids": ["rec_123"],
          "published_at": "2026-08-20T10:30:00Z"
        }
      ],
      "inferred_items": [],
      "speculation_items": []
    }
  ]
}
```

### `GET /api/v1/weekly-brief/{week_id}/summary`

Return summary-only view of a specific week (lightweight).

### `POST /api/v1/weekly-brief/generate`

Generate a new weekly brief from the current intelligence store.

**Query Parameters:**
- `week_id` — ISO week format (optional; defaults to current week)

**Response:**
```json
{
  "status": "success",
  "brief_id": "pwb_abc123def456",
  "week_id": "2026-W34",
  "records_analyzed": 42,
  "verified_count": 12,
  "inferred_count": 18,
  "speculation_count": 12,
  "produced_at": "2026-08-24T23:00:00Z",
  "markdown_path": "briefs/markdown/weekly_2026-W34.md"
}
```

## CLI Tool

Generate weekly briefs from the command line:

```bash
PYTHONPATH=src python -m spec1_core.tools.generate_weekly_brief \
    --intel spec1_intelligence.jsonl \
    --week 2026-W34 \
    --out-dir generated/weekly_briefs
```

**Arguments:**
- `--intel` — Path to IntelligenceRecord JSONL store (default: `spec1_intelligence.jsonl`)
- `--week` — ISO week "YYYY-W##" (default: current week)
- `--out-dir` — Output directory (default: `generated/weekly_briefs`)

**Output:**
- `spec1_weekly_briefs.jsonl` — Append-only JSONL store
- `weekly_<week_id>.md` — Markdown brief (human-readable)
- `markdown/weekly_<week_id>.md` — Copy of markdown
- `weekly_brief_index.jsonl` — Index of all briefs

## MCP Tool

The public weekly brief generator is exposed as an MCP tool for Claude integration:

```python
{
    "generate_weekly_brief": {
        "description": (
            "Generate a public weekly intelligence brief from the current intel store. "
            "Aggregates the past 7 days, classifies evidence into VERIFIED/INFERRED/SPECULATION tiers. "
            "Operator tool — runs out of band from the cycle."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "week_id": {"type": "string", "description": "ISO week format YYYY-W##; defaults to current week"},
                "out": {"type": "string", "description": "Output JSONL path (default spec1_weekly_briefs.jsonl)"},
            },
        }
    }
}
```

**Example Claude usage:**
```
generate_weekly_brief { week_id: "2026-W34" }
```

## Evidence Classification Logic

### VERIFIED

A signal is classified as VERIFIED when:
1. Classification is "CORROBORATED"
2. Confidence score ≥ 0.8
3. Source weight ≥ 0.7

### INFERRED

A signal is classified as INFERRED when:
1. Confidence score 0.65–0.79
2. Source weight ≥ 0.6
3. Classification is typically "ESCALATE", "INVESTIGATE", or "MONITOR"

### SPECULATION

All other signals (low confidence, unverified sources, preliminary hypotheses).

## Markdown Output Example

```markdown
# SPEC-1 Public Weekly Intelligence Brief — 2026-W34

**Week of 2026-08-17 to 2026-08-24**

*Produced: 2026-08-24 23:00 UTC*

## Disclaimer & Methodology

This brief aggregates 42 intelligence signals from 5 domains over one week. Evidence is classified as follows:

• **VERIFIED** (12 items): Corroborated across ≥2 credible sources, high confidence (≥0.8)
• **INFERRED** (18 items): Analysis from credible signals, medium-high confidence (0.65–0.79)
• **SPECULATION** (12 items): Preliminary hypotheses requiring validation

All claims link to source records (IDs). Timestamps reflect UTC publication/receipt.

---

## Executive Summary

SPEC-1 weekly intelligence cycle 2026-W34 processed 42 signals across 5 domains. 
Key activity areas: MILITARY, CYBER, GEOPOLITICAL, FARA, PSYOP.

**Records Analyzed:** 42 | **Verified:** 12 | **Inferred:** 18 | **Speculation:** 12

---

## MILITARY Intelligence (MILITARY)

### ✓ VERIFIED

**[95% confidence]** Military deployment in Eastern Europe
  - Source: rec_123, rec_124
  - Date: 2026-08-20T10:30:00Z
  - Note: Classification: CORROBORATED

### ≈ INFERRED (Analysis)

**[72% confidence]** Likely escalation scenario based on deployment patterns
  - Basis: rec_125, rec_126
  - Date: 2026-08-21T15:45:00Z
  - Note: Classification: MONITOR

### ? SPECULATION (Requires Validation)

**[55% confidence]** Possible involvement of third party
  - Source: rec_127
  - Date: 2026-08-22T08:00:00Z

---

## Brief Metadata

- **Brief ID:** pwb_abc123def456
- **Week ID:** 2026-W34
- **Total Domains:** 5
- **Source Domains:** 28
- **Evidence Classification:** 12 VERIFIED, 18 INFERRED, 12 SPECULATION

*This brief is produced by SPEC-1, an open-source intelligence platform using rule-based aggregation and LLM-assisted analysis.*
```

## Persistence Model

Weekly briefs use **append-only JSONL** storage via `WeeklyBriefStore`:

- **File:** `spec1_weekly_briefs.jsonl` (configurable)
- **Semantics:** Each line is a complete brief JSON object
- **Immutability:** Never modify existing lines; only append
- **Threading:** Thread-safe via `threading.Lock`

This model preserves:
- Historical audit trail (every weekly brief ever generated)
- Temporal consistency (each line has `written_at` timestamp)
- Simple queryability (line-by-line JSON parsing)

## Testing

Comprehensive test suite in `tests/test_weekly_brief.py`:

- Schema validation
- Producer logic (categorization, evidence classification, aggregation)
- Formatter output (Markdown, JSON summary, full JSON)
- Store persistence (append, read, get by week_id, latest)
- Integration tests (full workflow)

Run tests:
```bash
pytest tests/test_weekly_brief.py -v
```

## Integration with Existing Systems

### Dual-Write Compatibility

The weekly brief store does **not** use `cls_db.dual_write` (unlike some other stores). Instead:
- Primary persistence is JSONL (spec1_weekly_briefs.jsonl)
- No SQLite backend (to keep the feature lightweight)
- Can be integrated into SQLite later if needed

### Reuses Existing Schemas

- `IntelligenceRecord` from `spec1_core.schemas.models`
- Classification constants from `spec1_labels`
- Same confidence/scoring thresholds

### Additive, No Breaking Changes

- New module `cls_weekly_brief` is fully isolated
- API routes added without modifying existing ones
- No changes to core engine or daily brief
- Backward compatible with all existing systems

## Configuration

No new environment variables required. Optional:

- `SPEC1_WEEKLY_BRIEFS_PATH` — Path to weekly brief store (default: `spec1_weekly_briefs.jsonl`)

## Future Enhancements

1. **Publish to PDF** — Render weekly briefs as PDFs for distribution
2. **Email delivery** — Send weekly briefs to subscriber list
3. **SQLite backend** — Dual-write weekly briefs to queryable database
4. **Trend analysis** — Week-over-week comparison and trend detection
5. **Analyst feedback** — Integrate with feedback loop for evidence tier calibration
6. **Multi-language** — Translate briefs to key languages for international stakeholders

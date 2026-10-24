# HANDOFF — SPEC-1 / ONE WORLD CITIZEN
Fresh Session Context — June 8, 2026

## WHO YOU ARE WORKING WITH
Operator: Matt (Ominous) · EVASTARARCANA LLC · Portland OR
Contact: spec1_ops@proton.me

## THE SYSTEM
SPEC-1            — the engine (internal, never rename)
ONE WORLD CITIZEN — the publication
SWITCHBOARD       — the city intelligence platform (cls_metro)

World State Brief     — daily geopolitical intelligence column
Metropolitan Source   — local civic intelligence column
PSYCHE-OPS            — internal name for influence op analysis

## REPO
github.com/mjlak1000/spec-1
Branch: develop (default, protected)
Working dir: ~/spec-1
Venv: ~/spec-1/venv — always activate first
Active namespace: spec1_core (not spec1_engine)

## FIRST THING — READ THIS
cat ~/spec-1/DESIGN_INTENT.md

Summarize these three before doing anything:
1. Where the publication gate runs
2. What neutrality means in this system
3. The cls_pdx1 preservation rule

## CURRENT STATE

Pipeline: Running clean
- make cycle or ~/spec-1/scripts/run.sh for daily run
- API key in ~/spec-1/.env
- export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY ~/spec-1/.env | cut -d= -f2 | tr -d '\r\n')
- alias owc='~/spec-1/scripts/run.sh'

Database: SQLite — spec1.db
- 8 migrations applied (001-008)
- 3,076 intelligence records across 22 runs
- Dual-write JSONL + SQLite both live

First published output:
- Issue 597 — World State Brief, June 6 2026
- PSYCHE-OPS: "The Missile That Wasn't a Copy" — DPRK missile indigenization
- Verdict: CONFIRMED · PUBLISHED
- Chain of custody: complete

Release: v0.6.1 — "The Loop Closes" — tagged and published on GitHub

## IMMEDIATE TASK — CI IS FAILING
CI is red on develop. Fix it before anything else.

gh run list --limit 3
gh run view [latest-failing-id] --log-failed 2>/dev/null | grep -E "Error|FAILED" | head -20

Known fixes already applied:
- Bandit HIGH: radar_dashboard.py os.system — fixed with # nosec
- drop_all missing from cls_db.migrate — fixed
- Still failing — check latest run

Fix whatever is failing. Run tests locally first:
cd ~/spec-1
source venv/bin/activate
PYTHONPATH=src pytest tests/ -q --tb=short 2>&1 | tail -20

## AFTER CI IS GREEN

1. Tag v0.6.2 — CI clean release
2. docs/spec1_demo.html — single page portfolio demo
3. cls_metro build verification
4. cls_analyst_loop audit wiring — FallbackLLMClient
5. spec1_engine cleanup — 4 unique files
6. README final verification

## ARCHITECTURE INVARIANTS — NEVER TOUCH
- Append-only store
- Single-writer per namespace
- Four-gate framework — all four must pass
- Gate thresholds — not modified by agents
- Failure-first — log and continue, never crash
- run_id — single source of truth per cycle
- cls_pdx1 — never move, rename, squash, or restructure

## DESIGN SYSTEM
Black canvas · IBM Plex Mono · Courier Prime (data)
Flower of Life 5% opacity · border-radius: 0 · no box-shadow
Color: #00FF00 (PASS) and #FF0000 (CAUTION) only
Severity = brightness not hue

## RULES FOR CLAUDE CODE
- Branch: develop only
- No PRs · No new branches · Commit directly to develop
- Read DESIGN_INTENT.md first, every session
- Do not touch cls_pdx1 structure
- Do not write to spec1_engine
- Do not modify calibration values
- Ask before any destructive operation

## KEY FILES
DESIGN_INTENT.md                      canonical architecture authority
docs/archive/audits/AUDIT_NOTES.md    dual engine finding (engine archived 2026-10-24)
src/spec1_core/config/calibration.py  operational parameters (not public)
src/cls_analyst_loop/                 analyst workflow chain of custody
src/cls_metro/                        SWITCHBOARD city intelligence platform
db/migrations/                        001-008 applied
scripts/run.sh                        daily automation — one command
PSYCHE-OPS/                           published column output

"""Targeted Tier-3 synthesis backfill for remaining high-value signals.

The tier written to each row comes from which backend answered (see
spec1_core.llm.triage_stamper), never from the model's reply. Each update also
writes provenance: tier_used, model, llm_session, stamped_by='backfill'.
"""
import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict

from spec1_core.llm.triage_stamper import evaluate_and_stamp_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spec1.tier3_backfill")

_REPO_ROOT = Path(__file__).resolve().parents[1]  # defaults mean the same file whatever the cwd
DB_FILE = _REPO_ROOT / "spec1.db"
# Fields the backfill writes to a row and mirrors into the JSONL store.
STAMP_FIELDS = ("analysis_tier", "tier_used", "model", "llm_session", "stamped_by")
JSONL_FILE = _REPO_ROOT / "data" / "spec1_intelligence.jsonl"


def backfill_high_priority(conn: sqlite3.Connection, limit: int = 25,
                           min_score: float = 0.70) -> Dict[str, Dict[str, Any]]:
    cursor = conn.cursor()

    query = (
        "SELECT id, record_id, signal_source, opportunity_score, signal_excerpt, gate_results "
        "FROM intelligence_records "
        "WHERE signal_source != 'rand' "
        "  AND (opportunity_priority IN ('ELEVATED', 'CRITICAL') OR opportunity_score >= ?) "
        "  AND analysis_tier != 'llm_verified' "
        "ORDER BY opportunity_score DESC "
    )
    if limit > 0:
        query += f" LIMIT {limit}"

    cursor.execute(query, (min_score,))
    rows = cursor.fetchall()
    logger.info("Found %d remaining candidate records (min_score=%.2f, limit=%d)", len(rows), min_score, limit)

    stamped_records = {}
    for idx, (row_id, rec_id, source, opp_score, excerpt, gate_raw) in enumerate(rows, 1):
        try:
            gate_data = json.loads(gate_raw) if gate_raw else {}
        except Exception:
            gate_data = {}

        candidate = {
            "record_id": rec_id,
            "source": source or "UNKNOWN",
            "composite": float(opp_score or 0.0),
            "raw": {
                "excerpt": excerpt or "",
                "gate_results": gate_data,
            },
        }

        stamped = evaluate_and_stamp_record(candidate)
        stamp = {field: stamped.get(field) for field in STAMP_FIELDS}
        tier = stamp["analysis_tier"]
        justification = stamped.get("triage_justification", "")
        stamped_records[rec_id] = stamp

        cursor.execute(
            "UPDATE intelligence_records SET analysis_tier = ?, llm_reasoning = ?, "
            "tier_used = ?, model = ?, llm_session = ?, stamped_by = ? WHERE id = ?",
            (tier, justification, stamp["tier_used"], stamp["model"],
             stamp["llm_session"], stamp["stamped_by"], row_id),
        )
        logger.info("[%d/%d] Verified %s (%s, score=%.2f) -> tier=%s (backend=%s, model=%s)",
                    idx, len(rows), rec_id, source, opp_score or 0.0, tier,
                    stamp["tier_used"], stamp["model"])
        conn.commit()

    return stamped_records


def sync_jsonl(stamped_lookup: Dict[str, Dict[str, Any]]):
    if not JSONL_FILE.exists() or not stamped_lookup:
        return

    temp_file = JSONL_FILE.with_suffix(".jsonl.tmp")
    synced = 0

    with open(JSONL_FILE, "r", encoding="utf-8") as infile, open(temp_file, "w", encoding="utf-8") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            rec_id = record.get("record_id")

            if rec_id in stamped_lookup:
                record.update(stamped_lookup[rec_id])
                synced += 1

            outfile.write(json.dumps(record) + "\n")

    temp_file.replace(JSONL_FILE)
    logger.info("JSONL: Synced %d stamped records into %s", synced, JSONL_FILE)


def main():
    parser = argparse.ArgumentParser(description="Targeted Tier-3 Backfill for Migration 011")
    parser.add_argument("--limit", type=int, default=25, help="Max records to audit (0 for all matching)")
    parser.add_argument("--min-score", type=float, default=0.70, help="Opportunity score floor (default: 0.70)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_FILE)
    try:
        stamps = backfill_high_priority(conn, limit=args.limit, min_score=args.min_score)
        sync_jsonl(stamps)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

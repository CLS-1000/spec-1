"""Targeted Tier-3 synthesis backfill for high-value signals."""
import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict

from spec1_core.llm.triage_stamper import evaluate_and_stamp_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spec1.tier3_backfill")

DB_FILE = Path("spec1.db")
JSONL_FILE = Path("data/spec1_intelligence.jsonl")


def backfill_high_priority(conn: sqlite3.Connection, limit: int = 25, min_score: float = 0.70) -> Dict[str, str]:
    cursor = conn.cursor()

    query = (
        "SELECT id, record_id, signal_source, opportunity_score, signal_excerpt, gate_results "
        "FROM intelligence_records "
        "WHERE signal_source != 'rand' "
        "  AND opportunity_score >= ? "
        "  AND (llm_reasoning IS NULL OR llm_reasoning = '') "
        "ORDER BY opportunity_score DESC "
    )
    if limit > 0:
        query += f" LIMIT {limit}"

    cursor.execute(query, (min_score,))
    rows = cursor.fetchall()
    logger.info("Found %d candidate records (min_score=%.2f, limit=%d)", len(rows), min_score, limit)

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
        tier = stamped.get("analysis_tier", "rule_based")
        justification = stamped.get("triage_justification", "")
        stamped_records[rec_id] = tier

        cursor.execute(
            "UPDATE intelligence_records SET analysis_tier = ?, llm_reasoning = ? WHERE id = ?",
            (tier, justification, row_id),
        )
        logger.info("[%d/%d] Evaluated %s (%s, score=%.2f) -> tier=%s", idx, len(rows), rec_id, source, opp_score or 0.0, tier)
        conn.commit()

    return stamped_records


def sync_jsonl(stamped_lookup: Dict[str, str]):
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
                record["analysis_tier"] = stamped_lookup[rec_id]
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

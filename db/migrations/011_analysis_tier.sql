-- 011: analysis_tier on every intelligence record, plus excerpt/reasoning on
-- the legacy intel_records table.
--
-- analysis_tier says how a record's classification was produced:
--   'llm_verified' — a real model (local Qwen/Ollama or Claude) answered
--   'rule_based'   — deterministic triage or the Tier 3 rule fallback
-- Rows written before this migration have NULL (unknown) and must be treated
-- as unverified.
ALTER TABLE intelligence_records ADD COLUMN analysis_tier TEXT;
CREATE INDEX IF NOT EXISTS idx_ir_analysis_tier ON intelligence_records (analysis_tier);

-- intel_records (backfill target, scripts/restore_stores.py) never got the
-- 010 columns; without them every backfilled cycle record was rejected.
ALTER TABLE intel_records ADD COLUMN signal_excerpt TEXT;
ALTER TABLE intel_records ADD COLUMN llm_reasoning TEXT;
ALTER TABLE intel_records ADD COLUMN analysis_tier TEXT;

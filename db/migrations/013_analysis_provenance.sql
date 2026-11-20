-- 013: who produced each record's analysis, and who stamped its tier.
--
-- analysis_tier (011) only says llm_verified / rule_based. It cannot show
-- which backend actually answered, so a rules fallback after a model timeout
-- looked the same as deliberate rule-based triage, and a backfill stamp looked
-- the same as a cycle stamp.
--
--   tier_used   — backend that produced the classification:
--                 'claude' | 'ollama' | 'local' | 'rules'
--   model       — model name for that backend (NULL for 'rules')
--   llm_session — FallbackLLMClient / LocalTier3Client session id; matches
--                 the "session" field in logs/llm_fallback.jsonl
--   stamped_by  — 'cycle' | 'backfill' (scripts/backfill_tier3_stamps.py)
--
-- Rows written before this migration keep NULL (unknown); nothing is backfilled.
ALTER TABLE intelligence_records ADD COLUMN tier_used TEXT;
ALTER TABLE intelligence_records ADD COLUMN model TEXT;
ALTER TABLE intelligence_records ADD COLUMN llm_session TEXT;
ALTER TABLE intelligence_records ADD COLUMN stamped_by TEXT;
CREATE INDEX IF NOT EXISTS idx_ir_tier_used ON intelligence_records (tier_used);

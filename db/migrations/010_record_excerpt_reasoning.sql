-- 010: article excerpt and model reasoning on each intelligence record.
-- The cycle stores both in the JSONL record (see verifier/cycle, 2026-10-19);
-- without these columns every SQLite mirror write of a new record failed.
ALTER TABLE intelligence_records ADD COLUMN signal_excerpt TEXT;
ALTER TABLE intelligence_records ADD COLUMN llm_reasoning TEXT;

-- 012: provenance columns on intelligence_records.
--
-- build_record_dict (e763302) stamps harvester_version, raw_sha256 and
-- signal_published_at on every record. Without columns for them,
-- Repository._fit dropped all three from the SQLite mirror, so the mirror
-- could not show which harvester produced a row or which source text it hashed.
-- schema_version and source_type already have columns.
--
-- Rows written before this migration keep NULL (unknown); nothing is backfilled.
ALTER TABLE intelligence_records ADD COLUMN harvester_version TEXT;
ALTER TABLE intelligence_records ADD COLUMN raw_sha256 TEXT;
ALTER TABLE intelligence_records ADD COLUMN signal_published_at TEXT;
CREATE INDEX IF NOT EXISTS idx_ir_raw_sha256 ON intelligence_records (raw_sha256);

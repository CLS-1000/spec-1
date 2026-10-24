# Audit Notes — Dual Engine Finding

spec1_core is the active pipeline namespace.
spec1_engine is a parallel copy created by agent sessions (Claude Code, Copilot).

Cross-namespace import in spec1_core/workspace/cli.py has been corrected.
spec1_engine now has zero external imports outside its own namespace.

Files unique to spec1_engine (not in spec1_core) — review before deletion:
- src/spec1_engine/core/settings.py
- src/spec1_engine/tools/radar_dashboard.py
- src/spec1_engine/tools/snapshot_manager.py
- src/spec1_engine/tools/workspace_sanitizer.py

Recommended action: review those four files, merge any unique logic into
spec1_core, then archive spec1_engine/ before deletion.

Do not delete spec1_engine until operator confirms.
